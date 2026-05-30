"""Label schema, tokenizer and JSONL validation for the golden-set annotator.

This module is deliberately free of any UI / heavy dependency so it can be
imported and unit-tested in isolation.

The tokenizer and the GLiNER JSONL format MUST stay byte-compatible with
``scripts/eval/generate_synthetic_ru.py`` (the synthetic-data generator) so
that hand-labelled golden examples and machine-generated train examples share
the exact same shape:

    {"tokenized_text": ["word1", "word2", ...], "ner": [[start, end, "label"], ...]}

NER span indices are 0-based, inclusive, referencing ``tokenized_text``
positions. Tokenization is plain whitespace splitting — punctuation stays
attached to the adjacent token (e.g. ``"марафон."``), exactly as the generator
produces it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Label inventory — adapter `atman-ner-core` (13 labels).
# Mirrors docs/eval/gliner2_label_schema.md → Адаптер 1.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelSpec:
    """One NER label as it is presented to the human annotator."""

    key: str           # canonical label written into the JSONL
    emoji: str         # visual anchor for the button / legend
    title_ru: str      # short human-readable Russian name
    description: str    # what counts as this entity (boundary guidance)
    examples: str      # concrete examples
    color: str         # highlight colour in the preview


# Order matches the schema doc. Buttons and legend are rendered from this list.
LABELS: list[LabelSpec] = [
    LabelSpec(
        "person", "🧑", "Человек / агент",
        "Разумный субъект: человек, сам агент Atman, другие агенты. "
        "Местоимения (я, он) НЕ размечаем — это работа резолвера.",
        "Маша, брат, начальник, Atman, агент",
        "#FFD6A5",
    ),
    LabelSpec(
        "organization", "🏢", "Организация",
        "Компания, учреждение, заведение.",
        "Яндекс, университет, поликлиника",
        "#A0C4FF",
    ),
    LabelSpec(
        "location", "📍", "Место",
        "Физическое место.",
        "Москва, дома, на работе",
        "#BDB2FF",
    ),
    LabelSpec(
        "date_time", "🕒", "Время",
        "Дата, период или момент времени.",
        "вчера, в 2021, по утрам",
        "#9BF6FF",
    ),
    LabelSpec(
        "event", "🎉", "Событие",
        "Событие в жизни.",
        "свадьба, увольнение, переезд",
        "#FFC6FF",
    ),
    LabelSpec(
        "project", "🚀", "Проект",
        "Проект или начинание.",
        "Atman, ремонт, диссертация",
        "#CAFFBF",
    ),
    LabelSpec(
        "product", "📦", "Вещь / продукт",
        "Вещь, продукт, инструмент.",
        "телефон, Postgres, книга",
        "#FDFFB6",
    ),
    LabelSpec(
        "activity", "🏃", "Занятие",
        "Занятие, хобби, действие.",
        "бег, программирование, готовка",
        "#A3E635",
    ),
    LabelSpec(
        "profession", "💼", "Профессия",
        "Профессия или роль.",
        "разработчик, врач, студент",
        "#F9C74F",
    ),
    LabelSpec(
        "health", "🩺", "Здоровье",
        "Состояние здоровья, симптом, лекарство.",
        "простуда, головная боль, аспирин",
        "#FF9AA2",
    ),
    LabelSpec(
        "emotion_word", "💢", "Эмоция (слово)",
        "Прямо названная эмоция (само слово в тексте).",
        "злюсь, рад, тревожно",
        "#FFADAD",
    ),
    LabelSpec(
        "money", "💰", "Деньги",
        "Деньги, суммы, финансовые величины.",
        "зарплата, 1000 рублей, долг",
        "#B5E48C",
    ),
    LabelSpec(
        "animal", "🐾", "Животное",
        "Питомцы, животные.",
        "кот, собака Рекс",
        "#DDB892",
    ),
]

LABELS_BY_KEY: dict[str, LabelSpec] = {spec.key: spec for spec in LABELS}
VALID_LABELS: set[str] = set(LABELS_BY_KEY)
COLOR_MAP: dict[str, str] = {spec.key: spec.color for spec in LABELS}


# ---------------------------------------------------------------------------
# Tokenizer — identical to scripts/eval/generate_synthetic_ru.py
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Whitespace tokenizer. Punctuation stays attached to its token."""
    return [m.group() for m in re.finditer(r"\S+", text)]


# ---------------------------------------------------------------------------
# JSONL row helpers + validation (mirrors generator's validate_jsonl)
# ---------------------------------------------------------------------------

Span = list  # [start: int, end: int, label: str]


def make_row(tokens: list[str], spans: list[Span]) -> dict:
    """Build a GLiNER-format row, with deterministic span ordering."""
    ordered = sorted(
        ([int(s), int(e), str(lbl)] for s, e, lbl in spans),
        key=lambda x: (x[0], x[1]),
    )
    return {"tokenized_text": list(tokens), "ner": ordered}


def validate_row(row: dict) -> list[str]:
    """Validate a single in-memory row. Returns a list of error strings."""
    errors: list[str] = []
    toks = row.get("tokenized_text")
    if not isinstance(toks, list) or not toks:
        errors.append("missing or empty 'tokenized_text'")
        return errors

    ner = row.get("ner")
    if not isinstance(ner, list):
        errors.append("missing 'ner'")
        return errors

    n = len(toks)
    for span in ner:
        if not isinstance(span, (list, tuple)) or len(span) != 3:
            errors.append("ner span must be [start, end, label]")
            continue
        s, e, lbl = span
        if not isinstance(s, int) or not isinstance(e, int):
            errors.append("span indices must be int")
            continue
        if s < 0 or e < s or e >= n:
            errors.append(f"span [{s},{e}] invalid for {n} tokens")
            continue
        if lbl not in VALID_LABELS:
            errors.append(f"unknown label '{lbl}'")
    return errors


def validate_rows(rows: list[dict]) -> tuple[int, list[str]]:
    """Validate many rows. Returns (valid_count, error_messages)."""
    errors: list[str] = []
    valid = 0
    for i, row in enumerate(rows, 1):
        row_errors = validate_row(row)
        if row_errors:
            errors.extend(f"row {i}: {msg}" for msg in row_errors)
        else:
            valid += 1
    return valid, errors


def dump_jsonl(rows: list[dict], path: Path) -> None:
    """Write rows to a UTF-8 JSONL file (one compact JSON object per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of rows (blank lines skipped)."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                rows.append(json.loads(raw))
    return rows
