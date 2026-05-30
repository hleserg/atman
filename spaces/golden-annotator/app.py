"""Atman — Golden Set Annotator (HuggingFace Space).

A click-only UI for hand-labelling the held-out Russian golden test set
(T5 / HLE-382). Workflow per example:

    read the text → click the words of an entity → click its label button → next

The 13-label legend and a short boundary guide are always on screen so the
annotator does not have to memorise the schema.

Output is GLiNER-format JSONL, byte-compatible with the synthetic generator
(`scripts/eval/generate_synthetic_ru.py`) and validated with the same rules,
so golden and synthetic data share one shape.

Run locally:  python app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure `lib.*` resolves when the Space runs `python app.py`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gradio as gr  # noqa: E402

from lib.schema import (  # noqa: E402
    COLOR_MAP,
    LABELS,
    LABELS_BY_KEY,
    dump_jsonl,
    load_jsonl,
    make_row,
    tokenize,
    validate_rows,
)
from lib.seed_texts import SEED_TEXTS  # noqa: E402

OUTPUT_DIR = _HERE / "output"
OUTPUT_FILE = OUTPUT_DIR / "atman_ru_golden_test.jsonl"


# ---------------------------------------------------------------------------
# Static content: legend + instruction (built from the label schema)
# ---------------------------------------------------------------------------


def _legend_md() -> str:
    rows = [
        "| Метка | Кнопка | Что размечать | Примеры |",
        "|---|---|---|---|",
    ]
    for spec in LABELS:
        rows.append(
            f"| `{spec.key}` | {spec.emoji} {spec.title_ru} | "
            f"{spec.description} | _{spec.examples}_ |"
        )
    return "\n".join(rows)


INSTRUCTION_MD = """\
### Как размечать

1. **Прочитай** текст сверху.
2. **Отметь галочками** слова, которые образуют одну сущность (они должны идти
   подряд — это один непрерывный спан).
3. **Нажми кнопку** нужной метки ниже — спан добавится и подсветится.
4. Повтори для остальных сущностей. Если в примере сущностей нет — жми
   **«✅ Нет сущностей / пример готов»**.
5. Перейди к следующему примеру (**Вперёд ➡️**).
6. В конце — **«💾 Собрать и проверить»**, затем скачай JSONL.

### Правила границ

- Метим **только то, что реально написано в тексте**. Местоимения (я, он, она)
  НЕ метим — их разрешает резолвер по автору.
- Спан = минимальная осмысленная фраза сущности (имя + фамилия — один спан;
  «кот Тимоша» — кличка `животное` = `Тимоша`, слово «кот» можно включить если
  это часть наименования сущности, иначе только кличку — будь последователен).
- Пунктуация прилипает к слову (токенизация по пробелам), это нормально:
  токен может быть `«марафон.»`.
- Один токен — не больше одной метки. Перекрытия запрещены: чтобы переразметить,
  сначала удали старый спан в блоке справа.
- Сомневаешься между `знакомый`/`родственник`, `проект`/`продукт` — сверься с
  легендой и держись одного решения во всём наборе.
- Цель: ≥ 200 примеров, ≥ 20% перепроверить вторым проходом (см. HLE-382).
"""


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------


def _clamp(cur: int, n: int) -> int:
    if n <= 0:
        return 0
    return max(0, min(int(cur), n - 1))


def _build_highlight(tokens: list[str], spans: list[list]) -> list[tuple[str, str | None]]:
    """Render tokens as HighlightedText segments, colouring labelled spans."""
    # token index -> (label, span_start) so distinct spans never merge.
    label_at: dict[int, tuple[str, int]] = {}
    for s, e, lbl in spans:
        for t in range(s, e + 1):
            label_at[t] = (lbl, s)

    segments: list[tuple[str, str | None]] = []
    n = len(tokens)
    j = 0
    while j < n:
        marker = label_at.get(j)
        start = j
        if marker is None:
            while j < n and label_at.get(j) is None:
                j += 1
            segments.append((" ".join(tokens[start:j]) + " ", None))
        else:
            while j < n and label_at.get(j) == marker:
                j += 1
            segments.append((" ".join(tokens[start:j]) + " ", marker[0]))
    return segments


def _span_choices(tokens: list[str], spans: list[list]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for s, e, lbl in sorted(spans, key=lambda x: (x[0], x[1])):
        spec = LABELS_BY_KEY.get(lbl)
        emoji = spec.emoji if spec else "•"
        out.append((f"«{' '.join(tokens[s:e + 1])}» → {emoji} {lbl}", f"{s}|{e}|{lbl}"))
    return out


def view(pool: list[str], ann: dict, cur: int):
    """Recompute every example-dependent component for the current index."""
    n = len(pool)
    if n == 0:
        return (
            "_Пул пуст. Вставьте текст ниже или загрузите JSONL для продолжения._",
            gr.update(choices=[], value=[]),
            [],
            gr.update(choices=[], value=None),
            "**Пул пуст**",
        )
    cur = _clamp(cur, n)
    text = pool[cur]
    tokens = tokenize(text)
    spans = ann.get(cur, [])
    choices = [(tok, i) for i, tok in enumerate(tokens)]
    done = len(ann)
    state = "✅ помечен готовым" if cur in ann else "⏳ ещё не сохранён"
    progress = (
        f"**Пример {cur + 1} / {n}**  ·  готовых: **{done}**  ·  "
        f"статус: {state}  ·  спанов в примере: {len(spans)}"
    )
    return (
        f"### 📄 Текст\n\n{text}",
        gr.update(choices=choices, value=[]),
        _build_highlight(tokens, spans),
        gr.update(choices=_span_choices(tokens, spans), value=None),
        progress,
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def assign(selected, pool, ann, cur, label):
    if not pool:
        return (*view(pool, ann, cur), ann, "⚠️ Пул пуст.")
    cur = _clamp(cur, len(pool))
    tokens = tokenize(pool[cur])
    sel = sorted(int(x) for x in (selected or []))
    if not sel:
        return (*view(pool, ann, cur), ann, "⚠️ Сначала отметьте слова, потом метку.")
    if sel != list(range(sel[0], sel[-1] + 1)):
        return (
            *view(pool, ann, cur), ann,
            "⚠️ Выделение должно быть непрерывным — выберите соседние слова одной сущности.",
        )
    s, e = sel[0], sel[-1]
    spans = list(ann.get(cur, []))
    occupied: set[int] = set()
    for cs, ce, _ in spans:
        occupied.update(range(cs, ce + 1))
    if occupied.intersection(range(s, e + 1)):
        return (
            *view(pool, ann, cur), ann,
            "⚠️ Эти токены уже размечены — удалите старый спан справа, затем переразметьте.",
        )
    spans.append([s, e, label])
    new_ann = {**ann, cur: spans}
    spec = LABELS_BY_KEY[label]
    msg = f"➕ {spec.emoji} `{label}`: «{' '.join(tokens[s:e + 1])}»"
    return (*view(pool, new_ann, cur), new_ann, msg)


def mark_done(pool, ann, cur):
    if not pool:
        return (*view(pool, ann, cur), ann, "⚠️ Пул пуст.")
    cur = _clamp(cur, len(pool))
    new_ann = dict(ann)
    new_ann.setdefault(cur, [])
    n_spans = len(new_ann[cur])
    note = "без сущностей" if n_spans == 0 else f"{n_spans} спан(ов)"
    return (*view(pool, new_ann, cur), new_ann, f"✅ Пример {cur + 1} помечен готовым ({note}).")


def remove_span(span_value, pool, ann, cur):
    if not pool or not span_value:
        return (*view(pool, ann, cur), ann, "⚠️ Выберите спан для удаления.")
    cur = _clamp(cur, len(pool))
    try:
        s_str, e_str, lbl = span_value.split("|", 2)
        target = [int(s_str), int(e_str), lbl]
    except ValueError:
        return (*view(pool, ann, cur), ann, "⚠️ Не удалось разобрать спан.")
    spans = [sp for sp in ann.get(cur, []) if list(sp) != target]
    new_ann = {**ann, cur: spans}
    return (*view(pool, new_ann, cur), new_ann, f"🗑 Удалён спан → `{lbl}`.")


def go(pool, ann, cur, delta):
    new_cur = _clamp(int(cur) + delta, len(pool))
    return (*view(pool, ann, new_cur), new_cur)


def goto(pool, ann, value):
    try:
        new_cur = _clamp(int(value) - 1, len(pool))
    except (TypeError, ValueError):
        new_cur = _clamp(0, len(pool))
    return (*view(pool, ann, new_cur), new_cur)


def add_text(new_text, pool, ann, cur):
    text = (new_text or "").strip()
    if not text:
        return (*view(pool, ann, cur), pool, cur, "⚠️ Пустой текст.", gr.update())
    new_pool = list(pool) + [text]
    new_cur = len(new_pool) - 1
    return (
        *view(new_pool, ann, new_cur),
        new_pool, new_cur,
        "➕ Текст добавлен, перешёл к нему.",
        gr.update(value=""),
    )


def collect_and_save(pool, ann):
    if not ann:
        return None, "⚠️ Нечего сохранять — пометьте хотя бы один пример как готовый."
    rows = [make_row(tokenize(pool[i]), ann[i]) for i in sorted(ann)]
    valid, errors = validate_rows(rows)
    dump_jsonl(rows, OUTPUT_FILE)
    total_spans = sum(len(r["ner"]) for r in rows)
    lines = [
        f"💾 Сохранено **{len(rows)}** примеров, **{total_spans}** спанов → `{OUTPUT_FILE.name}`.",
        f"✅ Прошли валидацию: **{valid} / {len(rows)}** (формат validate_jsonl).",
    ]
    if errors:
        lines.append("\n**Ошибки валидации:**")
        lines.extend(f"- {err}" for err in errors[:20])
        if len(errors) > 20:
            lines.append(f"- … и ещё {len(errors) - 20}")
    else:
        lines.append("Цель T5: ≥ 200 примеров (см. HLE-382).")
    return str(OUTPUT_FILE), "\n".join(lines)


def resume_upload(file_obj, pool, ann, cur):
    if file_obj is None:
        return (*view(pool, ann, cur), pool, ann, cur, "⚠️ Файл не выбран.")
    try:
        rows = load_jsonl(Path(file_obj.name))
    except Exception as exc:  # noqa: BLE001 — surface any parse error to the user
        return (*view(pool, ann, cur), pool, ann, cur, f"⚠️ Не удалось прочитать JSONL: {exc}")
    new_pool: list[str] = []
    new_ann: dict[int, list[list]] = {}
    for i, row in enumerate(rows):
        new_pool.append(" ".join(row.get("tokenized_text", [])))
        new_ann[i] = [list(sp) for sp in row.get("ner", [])]
    return (
        *view(new_pool, new_ann, 0),
        new_pool, new_ann, 0,
        f"📥 Загружено {len(new_pool)} примеров из JSONL — можно продолжать разметку.",
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman — Golden Set Annotator", theme=gr.themes.Soft()) as demo:
        pool_state = gr.State(list(SEED_TEXTS))
        ann_state = gr.State({})
        cur_state = gr.State(0)

        gr.Markdown(
            "# 🏷️ Atman — разметка golden test set\n"
            "Ручная разметка held-out набора (T5 / HLE-382). Читай → кликай слова → "
            "жми метку. Легенда и инструкция всегда ниже."
        )

        with gr.Accordion("📖 Легенда меток (13 — adapter atman-ner-core)", open=True):
            gr.Markdown(_legend_md())
        with gr.Accordion("📝 Инструкция и правила границ", open=False):
            gr.Markdown(INSTRUCTION_MD)

        progress_md = gr.Markdown("**Пример —**")

        with gr.Row():
            with gr.Column(scale=3):
                read_md = gr.Markdown("### 📄 Текст")
                tokens_cb = gr.CheckboxGroup(
                    label="Отметьте слова сущности (подряд), затем нажмите метку",
                    choices=[],
                    value=[],
                )
                gr.Markdown("**Метки:**")
                label_buttons: list[tuple[gr.Button, str]] = []
                # 13 buttons in rows of 4.
                for start in range(0, len(LABELS), 4):
                    with gr.Row():
                        for spec in LABELS[start:start + 4]:
                            btn = gr.Button(f"{spec.emoji} {spec.title_ru}", size="sm")
                            label_buttons.append((btn, spec.key))
                with gr.Row():
                    done_btn = gr.Button("✅ Нет сущностей / пример готов", variant="primary")
                    reset_btn = gr.Button("↩️ Сбросить выделение")

            with gr.Column(scale=2):
                preview = gr.HighlightedText(
                    label="Текущая разметка",
                    color_map=COLOR_MAP,
                    combine_adjacent=False,
                    show_legend=False,
                )
                span_dd = gr.Dropdown(label="Спаны в примере", choices=[], value=None)
                remove_btn = gr.Button("🗑 Удалить выбранный спан")

        status_md = gr.Markdown("")

        with gr.Row():
            prev_btn = gr.Button("⬅️ Назад")
            goto_num = gr.Number(label="Перейти к №", value=1, precision=0, scale=0)
            goto_btn = gr.Button("Перейти")
            next_btn = gr.Button("Вперёд ➡️", variant="primary")

        with gr.Accordion("➕ Добавить свой текст в пул", open=False):
            new_text = gr.Textbox(label="Текст (на русском)", lines=3)
            add_btn = gr.Button("➕ Добавить в пул")

        with gr.Accordion("💾 Сохранение / экспорт / resume", open=True):
            with gr.Row():
                save_btn = gr.Button("💾 Собрать и проверить", variant="primary")
                upload = gr.File(label="📥 Загрузить JSONL (resume)", file_types=[".jsonl"])
            download_file = gr.File(label="Скачать atman_ru_golden_test.jsonl")
            save_status = gr.Markdown("")

        # --- wiring -------------------------------------------------------
        refresh_outputs = [read_md, tokens_cb, preview, span_dd, progress_md]
        assign_outputs = [*refresh_outputs, ann_state, status_md]

        for btn, key in label_buttons:
            btn.click(
                fn=lambda sel, p, a, c, lbl=key: assign(sel, p, a, c, lbl),
                inputs=[tokens_cb, pool_state, ann_state, cur_state],
                outputs=assign_outputs,
            )

        done_btn.click(
            mark_done,
            inputs=[pool_state, ann_state, cur_state],
            outputs=assign_outputs,
        )
        reset_btn.click(lambda: gr.update(value=[]), outputs=tokens_cb)
        remove_btn.click(
            remove_span,
            inputs=[span_dd, pool_state, ann_state, cur_state],
            outputs=assign_outputs,
        )

        prev_btn.click(
            lambda p, a, c: go(p, a, c, -1),
            inputs=[pool_state, ann_state, cur_state],
            outputs=[*refresh_outputs, cur_state],
        )
        next_btn.click(
            lambda p, a, c: go(p, a, c, +1),
            inputs=[pool_state, ann_state, cur_state],
            outputs=[*refresh_outputs, cur_state],
        )
        goto_btn.click(
            goto,
            inputs=[pool_state, ann_state, goto_num],
            outputs=[*refresh_outputs, cur_state],
        )

        add_btn.click(
            add_text,
            inputs=[new_text, pool_state, ann_state, cur_state],
            outputs=[*refresh_outputs, pool_state, cur_state, status_md, new_text],
        )

        save_btn.click(
            collect_and_save,
            inputs=[pool_state, ann_state],
            outputs=[download_file, save_status],
        )
        upload.upload(
            resume_upload,
            inputs=[upload, pool_state, ann_state, cur_state],
            outputs=[*refresh_outputs, pool_state, ann_state, cur_state, status_md],
        )

        demo.load(
            view,
            inputs=[pool_state, ann_state, cur_state],
            outputs=refresh_outputs,
        )

    return demo


if __name__ == "__main__":
    build_ui().launch()
