# Atman linguistic-demo — final polish (3 items)

## Context

Демка `spaces/linguistic-demo/` функционально готова после нескольких раундов правок (Tier 2 + Tier 3 + Tier 1 + UI accordions + divergence signals). На ветке `agent/worker-1` solid 7/10 демка. Остались **три полировочных штриха**, которые в сумме поднимают восприятие до 8.5/10:

1. **Визуальная диаграмма** "4 точки анализа → 4 runtime-компонента" — самый сильный из трёх по эффекту. Сейчас связь объяснена только словами (таблица в README + аккордеоны), и пользователь должен в голове сложить картинку.
2. **Шапка-описание под H1** — 2-3 строки в UI + README, объясняющие что это сенсор Atman и зачем демка существует.
3. **OG image** — preview-картинка которая показывается соцсетями при шейринге ссылки. Сейчас HF Space шейрится с дефолтной жёлтой картинкой HuggingFace.

Все три — **asset + минимальный code-патч**, без новой логики и лексических правок.

## Decisions taken (user-confirmed)

- Делаем все 3 полировки.
- Пользователь сам генерит картинки через Claude Design / image gen.
- Мой результат — точные prompt'ы, спеки форматов, и код-патчи для встройки в демку.
- Диаграмма вставляется в **оба места** (README + верх UI).

---

# Polish #1 — Runtime diagram (the impactful one)

## Asset spec

- **Имя файла**: `assets/runtime-diagram.png`
- **Путь**: `spaces/linguistic-demo/assets/runtime-diagram.png` (нужно создать папку `assets/`)
- **Формат**: PNG, прозрачный фон ИЛИ светлый (HF Space — светлая тема)
- **Размер**: 1200×600 px (2:1 соотношение — хорошо вписывается в README + UI)
- **Вес**: ≤ 200 KB (HF Space CDN, мелочь должна быть быстрой)

## The Claude Design prompt (copy-paste ready)

Пользователь копирует это в Claude (Artifacts mode, "Generate an image") или другой image gen:

```
Create a clean technical architecture diagram, 1200x600 pixels,
light background (white or very light grey #FAFAFA).

TITLE (top center, large, indigo-to-purple gradient text):
"Atman Linguistic Layer"

SUBTITLE (below title, smaller, grey #666):
"4 analysis points → 4 runtime components"

LAYOUT: two columns of 4 boxes each, with arrows between matching pairs.

LEFT COLUMN — analysis points (4 boxes stacked vertically,
indigo accent border #4F46E5):

  ┌─────────────────────┐
  │  Point A            │
  │  agent message      │
  └─────────────────────┘

  ┌─────────────────────┐
  │  Point K            │
  │  key moment         │
  └─────────────────────┘

  ┌─────────────────────┐
  │  Relations          │
  │  mREBEL             │
  └─────────────────────┘

  ┌─────────────────────┐
  │  Affect             │
  │  rule-based         │
  └─────────────────────┘

RIGHT COLUMN — runtime components (4 boxes stacked vertically,
purple accent border #8B5CF6):

  ┌──────────────────────┐
  │  Experience Store    │
  └──────────────────────┘

  ┌──────────────────────┐
  │  Reflection Engine   │
  └──────────────────────┘

  ┌──────────────────────┐
  │  Identity Store      │
  └──────────────────────┘

  ┌──────────────────────┐
  │  Affective           │
  │  Regulation          │
  └──────────────────────┘

ARROWS (thin, grey #999, with arrowhead pointing right):
  Point A     → Experience Store
  Point K     → Reflection Engine
  Relations   → Identity Store
  Affect      → Affective Regulation

STYLE:
- Minimalist flat design, no 3D, no shadows beyond a subtle
  drop shadow under each box (0px 2px 4px rgba(0,0,0,0.06))
- Sans-serif font (Inter, Helvetica, or system default)
- Rounded corners on boxes (8-12px radius)
- Generous whitespace between boxes (24-32px gap)
- Color palette: indigo #4F46E5 + purple #8B5CF6 (matches Atman's
  brand colors from the HF Space frontmatter)
- Like a modern system architecture diagram from docs of
  Stripe / Linear / Notion / Vercel

EXPLICITLY AVOID:
- Photographs, faces, illustrations of people
- 3D rendering, isometric views
- Decorative elements unrelated to the diagram structure
- Multiple gradients beyond the title
- Background patterns or textures

This is a pure typographic + geometric architecture diagram for
technical documentation.
```

If Claude/image-gen produces something off-target, ask the user to
iterate with: "Make it cleaner / less decorative / more like
docs.stripe.com architecture diagrams."

## Code patch — wiring the image in

### File 1: `spaces/linguistic-demo/README.md`

Insert the image **after the frontmatter, before the H1 title**, or
right after the H1. Best placement: directly under the H1 title for
maximum visibility on the HF Space front page.

Current (line 22):
```markdown
# Atman — Psychological Linguistic Layer

*What your AI agent's **own text** reveals about its internal state.*
```

After change:
```markdown
# Atman — Psychological Linguistic Layer

*What your AI agent's **own text** reveals about its internal state.*

![Atman Linguistic Layer — 4 analysis points feeding the runtime](assets/runtime-diagram.png)
```

### File 2: `spaces/linguistic-demo/app.py`

Insert `gr.Image(...)` between the title Markdown and `lang_radio`.
Current (around line 380):

```python
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman Linguistic Demo", theme=gr.themes.Soft()) as demo:
        gr.Markdown("Atman — Psychological Telemetry for AI Agents")

        lang_radio = gr.Radio(...)
```

Add the diagram right after the Markdown:

```python
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman Linguistic Demo", theme=gr.themes.Soft()) as demo:
        gr.Markdown("Atman — Psychological Telemetry for AI Agents")

        diagram_path = _HERE / "assets" / "runtime-diagram.png"
        if diagram_path.exists():
            gr.Image(
                value=str(diagram_path),
                show_label=False,
                interactive=False,
                container=False,
                show_download_button=False,
                height=320,  # ~half scaled, fits without dominating
            )

        lang_radio = gr.Radio(...)
```

The `if diagram_path.exists()` guard means the demo still launches
gracefully if the user hasn't generated the image yet — just no
diagram shown. Once the PNG appears in `assets/`, it lights up
without further code changes.

---

# Polish #2 — Header description under H1

## Цель

Сейчас под `gr.Markdown("Atman — Psychological Telemetry for AI Agents")` в UI и под H1 в README ничего нет, кроме первого функционального блока. Хочется чтобы юзер за 3 секунды понял "это сенсор Atman, AI runtime layer, и почему он тут".

## Asset spec

Нет ассета — это чистый текст в `UI_STRINGS` + Markdown в README.

## Контент

### EN

> **What you're looking at**: a sensor of [Atman](https://github.com/hleserg/atman) — a psychological runtime layer that gives AI agents continuous identity, first-person memory, and reflection. This Space shows the **linguistic block** — 4 analysis points scanning what the agent says (and thinks) for signals that feed Experience, Identity, and Reflection.
>
> *The lower agent acts. Atman exists.*

### RU

> **Что ты сейчас видишь**: сенсор [Atman](https://github.com/hleserg/atman) — психологического runtime-слоя, который даёт AI-агентам непрерывную идентичность, память от первого лица и рефлексию. Этот Space показывает **лингвистический блок** — 4 точки анализа, сканирующие что агент говорит (и думает) на предмет сигналов, питающих Experience, Identity и Reflection.
>
> *Нижний агент действует. Atman существует.*

## Code patch

### File 1: `spaces/linguistic-demo/app.py`

Добавить в `UI_STRINGS["en"]` и `UI_STRINGS["ru"]` ключ `"header_blurb"` с текстом выше.

В `build_ui()` после `gr.Markdown("Atman — Psychological Telemetry...")` и **до** диаграммы:

```python
header_md = gr.Markdown(value=UI_STRINGS["en"]["header_blurb"])

diagram_path = _HERE / "assets" / "runtime-diagram.png"
if diagram_path.exists():
    gr.Image(...)
```

В `update_ui_language` и `ui_lang_outputs` добавить `header_md` для переключения языка.

### File 2: `spaces/linguistic-demo/README.md`

Вставить EN-вариант шапки **прямо под** `*What your AI agent's **own text** reveals about its internal state.*` и **до** строки с диаграммой:

```markdown
# Atman — Psychological Linguistic Layer

*What your AI agent's **own text** reveals about its internal state.*

**What you're looking at**: a sensor of [Atman](https://github.com/hleserg/atman) — a psychological runtime layer ...

*The lower agent acts. Atman exists.*

![Atman Linguistic Layer — 4 analysis points feeding the runtime](assets/runtime-diagram.png)
```

---

# Polish #3 — OG image (social preview)

## Цель

Когда кто-то шейрит ссылку на этот HF Space в Twitter/Telegram/Slack/Discord — соцсети показывают дефолтную жёлтую картинку HuggingFace, ничего узнаваемого. С OG image превью — узнаваемое, продаёт демку само.

## Asset spec

- **Имя файла**: `assets/og-image.png`
- **Путь**: `spaces/linguistic-demo/assets/og-image.png`
- **Формат**: PNG, обязательно непрозрачный фон (соцсети плохо рендерят transparent)
- **Размер**: 1200×630 px (стандарт Open Graph)
- **Вес**: ≤ 300 KB

## The Claude Design prompt (copy-paste ready)

```
Create a social media preview image, 1200x630 pixels, designed to
catch attention when shared on Twitter, LinkedIn, Telegram, Slack.

BACKGROUND: deep indigo-to-purple gradient (#312E81 to #6D28D9),
with subtle abstract neural-network-like pattern at low opacity.

CENTERED CONTENT:

Large title (top-third of image, white text, bold, sans-serif):
"Atman"

Subtitle directly below (smaller, white at 80% opacity):
"Psychological Linguistic Layer"

Tagline in middle (one line, monospace or italic, light grey #D1D5DB):
"What your AI's own text reveals about its internal state."

Bottom-right corner, small (white at 60% opacity):
"🧠  github.com/hleserg/atman"

STYLE:
- Modern, technical, calm
- Like the OG images of Stripe, Linear, Vercel
- Plenty of negative space
- One central focal point (the title)
- No diagrams, no boxes, no faces, no 3D rendering

The image must be readable as a thumbnail at 600x315 (Twitter scaled).
```

## Code patch

### File: `spaces/linguistic-demo/README.md`

Добавить в YAML frontmatter (вверху файла) поле `thumbnail`:

```yaml
---
title: Atman — Psychological Linguistic Layer
emoji: 🧠
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
python_version: "3.11"
license: mit
thumbnail: assets/og-image.png  # ← NEW
tags:
  ...
---
```

HF Space автоматически использует это поле для OG preview.

---

# Polish #4 — Presets: EN category labels

## Контекст

Пользователь только что (commit `4cdecfa0`) переписал `examples/presets.py` — теперь категории организованы как `dict[category_key, dict[locale, list[examples]]]` с `random.choice` выбором при каждом клике. Огромный плюс — больше вариативности.

**Bug**: ключи категорий — только русские строки (`"1. Thinking и сообщение совпадают"`, `"Биография"`, и т.д.). При locale="en" `preset_labels()` отфильтрует EN-контент, но **в дропдауне выведет русские имена категорий**. EN-юзер видит:

```
1. Thinking и сообщение совпадают
2. Thinking и сообщение расходятся
3. Эмоционально нестабильная ситуация
4. Технический разговор об Atman
```

Это решено пользователем: **"добавить EN-перевод рядом"**.

## Design — минимально инвазивно

Сохраняем русские ключи как **canonical id** (минимум disruption), добавляем `_EN_LABELS` dict для перевода UI:

```python
# В каждом из _POINT_A / _POINT_K / _RELATIONS / _AFFECT — без изменений
# (RU labels остаются ключами dict'а).

# NEW: EN labels parallel to category keys
_POINT_A_EN_LABELS: dict[str, str] = {
    "1. Thinking и сообщение совпадают": "1. Thinking and message align",
    "2. Thinking и сообщение расходятся": "2. Thinking and message diverge",
    "3. Эмоционально нестабильная ситуация": "3. Emotionally unstable situation",
    "4. Технический разговор об Atman": "4. Technical talk about Atman",
}

_POINT_K_EN_LABELS: dict[str, str] = {
    "1. Отказ по ценности": "1. Value-based refusal",
    "2. Накопление доверия": "2. Trust accumulation",
    "3. Расхождение с пользователем": "3. Disagreement with the user",
}

_RELATIONS_EN_LABELS: dict[str, str] = {
    "1. Биография": "1. Biography",
    "2. Проектная связь": "2. Project relations",
}

_AFFECT_EN_LABELS: dict[str, str] = {
    "1. Отказ по ценности": "1. Value refusal",
    "2. Отказ по возможностям": "2. Capability refusal",
    "3. Честное сомнение": "3. Sincere uncertainty",
}
```

`preset_labels()` теперь принимает опциональный en_labels dict:

```python
def preset_labels(
    presets: list[tuple[str, ...]],
    locale: str,
    en_labels: dict[str, str] | None = None,
) -> list[str]:
    """Return deduplicated dropdown labels for the given UI locale."""
    seen: set[str] = set()
    result: list[str] = []
    for row in presets:
        if row[0] == locale and row[1] not in seen:
            seen.add(row[1])
            display = row[1]
            if locale == "en" and en_labels is not None:
                display = en_labels.get(row[1], row[1])
            result.append(display)
    return result
```

`lookup_*()` принимает label и en_labels — сначала пытается прямой lookup в RU keys, если не нашёл и есть en_labels — обратное mapping `EN→RU` и повторный lookup:

```python
def lookup_point_a(
    locale: str,
    label: str,
    en_labels: dict[str, str] | None = None,
) -> tuple[str, str | None] | None:
    canonical = label
    if locale == "en" and en_labels is not None:
        # Reverse-map EN label back to RU canonical key
        for ru_key, en_label in en_labels.items():
            if en_label == label:
                canonical = ru_key
                break
    examples = _POINT_A.get(canonical, {}).get(locale)
    if not examples:
        return None
    return random.choice(examples)
```

И в `app.py` все вызовы передают соответствующий `*_EN_LABELS`:

```python
# update_ui_language:
gr.update(choices=preset_labels(POINT_A_PRESETS, target, _POINT_A_EN_LABELS), ...),
gr.update(choices=preset_labels(POINT_K_PRESETS, target, _POINT_K_EN_LABELS), ...),
gr.update(choices=preset_labels(RELATIONS_PRESETS, target, _RELATIONS_EN_LABELS), ...),
gr.update(choices=preset_labels(AFFECT_PRESETS, target, _AFFECT_EN_LABELS), ...),

# _apply_a_preset:
found = lookup_point_a(locale, name, _POINT_A_EN_LABELS)

# Same for _apply_k_preset, _apply_r_preset, _apply_af_preset.
```

Также добавить экспорт `_POINT_A_EN_LABELS, _POINT_K_EN_LABELS, _RELATIONS_EN_LABELS, _AFFECT_EN_LABELS` из `examples/presets.py` (импорт в `app.py`).

---

# Critical files

- `spaces/linguistic-demo/assets/runtime-diagram.png` — NEW, user-generated (Polish #1)
- `spaces/linguistic-demo/assets/og-image.png` — NEW, user-generated (Polish #3)
- `spaces/linguistic-demo/README.md` — markdown image + header blurb + thumbnail frontmatter
- `spaces/linguistic-demo/app.py` — `gr.Image` block, header markdown, UI_STRINGS additions, EN-labels wiring
- `spaces/linguistic-demo/examples/presets.py` — 4 EN-labels dicts + `preset_labels`/`lookup_*` signature updates

## Order of operations & **HARD GATE before handoff**

Не все четыре полировки требуют ассетов от пользователя. Порядок:

1. **Сразу** (мне, без ожидания):
   - Polish #2 (header description) — текст готов, никаких ассетов
   - Polish #4 (EN labels) — код-only
2. **HARD GATE — preset sweep**:
   - Запустить `$CLAUDE_JOB_DIR/preset_sweep.py` (скрипт ниже в секции "Automated preset sweep")
   - Прочитать вывод
   - **Если есть ⚠️** — сначала докручиваем лексикон/правила пока не все ✅, и только потом push.
   - **Если все ✅** — push в `agent/worker-1`
3. **Уведомить пользователя**: "первая партия готова, прошли все 136 пресетов на rule-based слое, подтяни и проверь руками". Пользователь делает ручной тест в браузере.
4. **После того как пользователь сгенерил картинки** (отдельный заход):
   - Polish #1 (диаграмма) — нужен `runtime-diagram.png`
   - Polish #3 (OG image) — нужен `og-image.png`
   - Повторить HARD GATE — `python -m py_compile` + проверка что демка стартует
   - Push

**Главный принцип**: я НЕ отдаю пользователю на ручной тест ничего, что не прошло автоматический preset sweep. Если sweep выявил `⚠️` — я молча докручиваю, не дёргая пользователя итерациями.

## Plan persistence

Этот план продублировать в репо как `spaces/linguistic-demo/docs/POLISH_PLAN.md` (одним из первых шагов исполнения) — чтобы он не потерялся после ExitPlanMode и был виден в PR/в Git-истории. Master-копия остаётся в `/root/.claude/plans/snazzy-spinning-honey.md`.

## Automated preset sweep — sanity & coverage report

После Polish #4 (EN labels) у нас будет валидный билингвальный набор: ~40 Point A + 36 Point K + 24 Relations + 36 Affect = **~136 примеров**. Прежде чем пушить — прогнать всё через rule-based слой и собрать сводку: какие сигналы где сработали, нет ли категорических misses.

### Что прогоняем (без загрузки тяжёлых моделей)

Цель — проверить **rule-based слой** на ВСЕХ примерах сразу. ML-инференс (GLiNER + MiniLM + mREBEL) намеренно не трогаем — это интеграционный тест, гонять при каждом изменении дорого. Тут — точечная проверка лексиконов и алгоритмов рассогласования.

| Часть | Что прогоняем | Что проверяем |
|---|---|---|
| **Point A** | `_heuristic_point_a_spans(msg)`, `_detect_divergence(thinking, msg)`, `_detect_boundary_markers(msg)` | Категория 1 → 0 divergence signals; Категория 2 → ≥1 из {thinking_suppression, evaluation_flip, tone_mismatch, length_compression}; Категория 3 → boundary markers ≥1; Категория 4 → 0 divergence signals |
| **Point K** | `_heuristic_point_a_spans(text)` на склейке what_happened + why_it_matters | На каждой категории должны находиться spans (≥1) — это просто signal that the rule layer engages с текстом, без претензий на правильную классификацию |
| **Relations** | структурная валидация: непустые тексты, ≥2 named entities по простому regex (заглавные слова) | Что mREBEL получит на вход осмысленный текст |
| **Affect** | `score_refusal(text)`, `emotion_score(text, lang)`, `hedge_density`, `disclaimer_density`, `sincerity_score`, `self_reference_density` | Категория 1 (ценностный отказ) → `score_refusal.confidence` ≥ 0.45; Категория 2 (capability refusal) → confidence < 0.45; Категория 3 (честное сомнение) → hedge_density > 0 ИЛИ disclaimer_density > 0; emotion_score не падает |

### Скрипт прогона (создаётся в `$CLAUDE_JOB_DIR/preset_sweep.py`, не коммитится)

```python
"""Run all bilingual presets through the rule-based analysis layer.

Outputs a per-category summary and flags anomalies (categories where
expected signals did NOT fire on a majority of examples).
"""
import sys
from collections import defaultdict
sys.path.insert(0, '/atman/atman/.worktrees/worker-1/spaces/linguistic-demo')

import unittest.mock as mock
sys.modules['gliner'] = mock.MagicMock()
sys.modules['transformers'] = mock.MagicMock()

from lib.linguistic import GLiNERPlusMiniLMAnalyzer
from lib.affect.refusal_detector import score_refusal
from lib.affect.emolex.emolex import emotion_score, tokenize
from lib.affect.metrics import (
    hedge_density, disclaimer_density,
    self_reference_density, sincerity_score,
)
from examples.presets import (
    _POINT_A, _POINT_K, _RELATIONS, _AFFECT,
)

a = GLiNERPlusMiniLMAnalyzer()

# ── Point A ─────────────────────────────────────────────────────────────
print("\n" + "═" * 72)
print("POINT A — divergence + heuristic spans")
print("═" * 72)
for category, langs in _POINT_A.items():
    for locale, examples in langs.items():
        results = []
        for msg, thinking in examples:
            sigs = a._detect_divergence(thinking or "", msg)
            spans = a._heuristic_point_a_spans(msg)
            bnd = a._detect_boundary_markers(msg)
            results.append((sigs, len(spans), bnd))
        sig_count = sum(1 for r in results if r[0])
        avg_spans = sum(r[1] for r in results) / len(results)
        bnd_count = sum(1 for r in results if r[2])
        print(f"\n  {locale} · {category}")
        print(f"    examples: {len(results)}")
        print(f"    examples with divergence signals: {sig_count}/{len(results)}")
        print(f"    avg heuristic spans: {avg_spans:.1f}")
        print(f"    examples with boundary markers: {bnd_count}/{len(results)}")
        # show one example's signals
        if results[0][0]:
            print(f"    sample signals: {results[0][0]}")

# Анализ — ожидания по категориям (assertions)
print("\n── EXPECTATIONS CHECK ──")
ok = True
for locale in ("ru", "en"):
    # Category 1 (align): expect <50% divergence
    cat1 = _POINT_A["1. Thinking и сообщение совпадают"][locale]
    div1 = sum(1 for m, t in cat1 if a._detect_divergence(t or "", m))
    if div1 > len(cat1) // 2:
        print(f"⚠️  Cat1 [{locale}]: {div1}/{len(cat1)} have divergence — should be near-zero")
        ok = False
    else:
        print(f"✅ Cat1 [{locale}]: {div1}/{len(cat1)} divergence (clean)")

    # Category 2 (diverge): expect >80% divergence
    cat2 = _POINT_A["2. Thinking и сообщение расходятся"][locale]
    div2 = sum(1 for m, t in cat2 if a._detect_divergence(t or "", m))
    if div2 < len(cat2) * 0.8:
        print(f"⚠️  Cat2 [{locale}]: only {div2}/{len(cat2)} have divergence — should be ≥80%")
        ok = False
    else:
        print(f"✅ Cat2 [{locale}]: {div2}/{len(cat2)} divergence (correct)")

    # Category 3 (refusal): expect >70% boundary markers
    cat3 = _POINT_A["3. Эмоционально нестабильная ситуация"][locale]
    bnd3 = sum(1 for m, _ in cat3 if a._detect_boundary_markers(m))
    if bnd3 < len(cat3) * 0.7:
        print(f"⚠️  Cat3 [{locale}]: only {bnd3}/{len(cat3)} have boundary markers — should be ≥70%")
        ok = False
    else:
        print(f"✅ Cat3 [{locale}]: {bnd3}/{len(cat3)} boundary markers (correct)")

    # Category 4 (atman tech): expect <30% divergence (mostly no thinking, technical content)
    cat4 = _POINT_A["4. Технический разговор об Atman"][locale]
    div4 = sum(1 for m, t in cat4 if a._detect_divergence(t or "", m))
    if div4 > len(cat4) * 0.3:
        print(f"⚠️  Cat4 [{locale}]: {div4}/{len(cat4)} have divergence — should be low")
        ok = False
    else:
        print(f"✅ Cat4 [{locale}]: {div4}/{len(cat4)} divergence (clean)")

# ── Affect ──────────────────────────────────────────────────────────────
print("\n" + "═" * 72)
print("AFFECT — refusal detector + metrics")
print("═" * 72)
for category, langs in _AFFECT.items():
    for locale, texts in langs.items():
        confs = []
        for text in texts:
            try:
                r = score_refusal(text)
                confs.append(r.confidence)
            except Exception as e:
                confs.append(None)
                print(f"    ❌ score_refusal failed: {e}")
        valid = [c for c in confs if c is not None]
        avg_conf = sum(valid) / len(valid) if valid else 0
        high_conf = sum(1 for c in valid if c >= 0.45)
        print(f"\n  {locale} · {category}")
        print(f"    avg refusal confidence: {avg_conf:.2f}")
        print(f"    confident refusals (≥0.45): {high_conf}/{len(valid)}")

# Expectations
print("\n── AFFECT EXPECTATIONS CHECK ──")
for locale in ("ru", "en"):
    val_refusal = _AFFECT["1. Отказ по ценности"][locale]
    val_conf = [score_refusal(t).confidence for t in val_refusal]
    val_high = sum(1 for c in val_conf if c >= 0.45)
    if val_high < len(val_refusal) * 0.6:
        print(f"⚠️  Value refusal [{locale}]: only {val_high}/{len(val_refusal)} confident — expected ≥60%")
        ok = False
    else:
        print(f"✅ Value refusal [{locale}]: {val_high}/{len(val_refusal)} confident")

    cap_refusal = _AFFECT["2. Отказ по возможностям"][locale]
    cap_conf = [score_refusal(t).confidence for t in cap_refusal]
    cap_high = sum(1 for c in cap_conf if c >= 0.45)
    if cap_high > len(cap_refusal) * 0.3:
        print(f"⚠️  Capability refusal [{locale}]: {cap_high}/{len(cap_refusal)} are scored as value refusals — capability discount not working")
        ok = False
    else:
        print(f"✅ Capability refusal [{locale}]: {cap_high}/{len(cap_refusal)} false-positive (correct — discounted)")

# ── Point K + Relations: lightweight ────────────────────────────────────
print("\n" + "═" * 72)
print("POINT K + RELATIONS — structural validation")
print("═" * 72)
for category, langs in _POINT_K.items():
    for locale, examples in langs.items():
        non_empty = sum(1 for w, why in examples if w.strip() and why.strip())
        print(f"  {locale} · {category}: {non_empty}/{len(examples)} non-empty pairs")
for category, langs in _RELATIONS.items():
    for locale, texts in langs.items():
        long_enough = sum(1 for t in texts if len(t.split()) >= 5)
        print(f"  {locale} · {category}: {long_enough}/{len(texts)} have ≥5 words")

print("\n" + "═" * 72)
if ok:
    print("✅ ALL CATEGORY EXPECTATIONS MET")
else:
    print("⚠️  SOME EXPECTATIONS FAILED — see warnings above")
print("═" * 72)
```

### Анализ результатов прогона

После запуска скрипта:

1. **Если все ✅** — лексический слой работает, можно пушить с уверенностью.
2. **Если ⚠️ на категории 2 (divergence не ловится)** — нужно расширять `_SUPPRESSION_PATTERNS` / `_NEG_EVAL_PATTERNS` / `_POS_EVAL_PATTERNS` под конкретные примеры из пресета.
3. **Если ⚠️ на категории 3 (нет boundary)** — расширять `_BOUNDARY_MARKERS`.
4. **Если ⚠️ на capability refusal (categ.2 affect)** — capability discount слабый, ужесточить.
5. **Если ⚠️ на value refusal (categ.1 affect)** — morphology/moral context не срабатывает на наших формулировках, докручиваем.

Любая ⚠️ — это **точная карта где докручивать перед финальным push'ем**. Никакого "наугад": конкретные категории, конкретные примеры.

## Verification end-to-end

### После первого push (header + presets EN + лексические доделки если нужны)

1. Offline smoke test:
   ```bash
   cd /atman/atman/.worktrees/worker-1/spaces/linguistic-demo
   python -m py_compile app.py examples/presets.py
   python << 'EOF'
   import sys; sys.path.insert(0, '.')
   from examples.presets import (
       preset_labels, lookup_point_a, lookup_point_k,
       lookup_relations, lookup_affect,
       POINT_A_PRESETS, POINT_K_PRESETS, RELATIONS_PRESETS, AFFECT_PRESETS,
       _POINT_A_EN_LABELS, _POINT_K_EN_LABELS,
       _RELATIONS_EN_LABELS, _AFFECT_EN_LABELS,
   )

   en_a = preset_labels(POINT_A_PRESETS, "en", _POINT_A_EN_LABELS)
   ru_a = preset_labels(POINT_A_PRESETS, "ru")
   assert all("Thinking" in lbl or "Technical" in lbl or "Emotionally" in lbl for lbl in en_a), en_a
   assert any("Thinking и сообщение" in lbl for lbl in ru_a), ru_a

   # Roundtrip: EN label → lookup returns valid example
   en_label = en_a[0]
   found = lookup_point_a("en", en_label, _POINT_A_EN_LABELS)
   assert found is not None and isinstance(found, tuple), found

   print("✅ EN labels + lookup roundtrip OK")
   EOF
   ```
2. Локально пользователь:
   - Открыть демку, переключиться на EN — категории в дропдаунах все английские
   - Выбрать категорию — внутри английский пример (random)
   - Переключиться на RU — категории русские
3. Push в `agent/worker-1`.

### После второго push (diagram + OG image)

1. `ls assets/` — оба файла на месте.
2. `python -m py_compile app.py` — syntax OK.
3. `grep "runtime-diagram" README.md` и `grep "thumbnail" README.md` — оба референса есть.
4. Локально:
   - В UI вверху — диаграмма под шапкой
   - На странице HF Space — диаграмма в README
   - Шеринг ссылки в твиттер показывает OG image
   - Демка запускается даже если файла нет (graceful guard сохраняем)
5. Push в `agent/worker-1`.

## Что НЕ делаем в этом раунде

- **Перевод лексических лейблов** анализа (hedge → хедж и т.д.) — пользователь отказался, semantic canon важнее.
- **Sync с upstream `src/atman/`** — отложено до момента PR.
