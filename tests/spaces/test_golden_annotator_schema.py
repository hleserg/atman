"""Contract tests for the golden-set annotator's data layer.

Guards the byte-compatibility between hand-labelled golden examples and the
synthetic generator (`scripts/eval/generate_synthetic_ru.py`):

  * the 13 NER labels match the documented `atman-ner-core` inventory,
  * tokenization is whitespace splitting (punctuation stays attached),
  * the JSONL row shape + validation rules match the generator's, and
  * dump/load round-trips losslessly.

Imports only `lib.schema` (no gradio), so it runs in the standard test env.
The Space lives outside src/ and is added to sys.path at runtime, so static
import resolution is disabled for this file only.
"""
# pyright: reportMissingImports=false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SPACE_LIB = Path(__file__).resolve().parents[2] / "spaces" / "golden-annotator"
if str(_SPACE_LIB) not in sys.path:
    sys.path.insert(0, str(_SPACE_LIB))

from lib.schema import (  # noqa: E402
    LABELS,
    VALID_LABELS,
    dump_jsonl,
    load_jsonl,
    make_row,
    tokenize,
    validate_row,
    validate_rows,
)

_EXPECTED_LABELS = {
    "person",
    "organization",
    "location",
    "date_time",
    "event",
    "project",
    "product",
    "activity",
    "profession",
    "health",
    "emotion_word",
    "money",
    "animal",
}


def test_label_inventory_matches_schema_doc() -> None:
    assert VALID_LABELS == _EXPECTED_LABELS
    assert len(LABELS) == 13
    # every label carries presentation metadata
    for spec in LABELS:
        assert spec.emoji and spec.title_ru and spec.description and spec.examples


def test_tokenizer_is_whitespace_split_with_attached_punctuation() -> None:
    tokens = tokenize("Связи с командой из «ИнфоТек» сбиваются, дедлайны.")
    assert tokens == [
        "Связи",
        "с",
        "командой",
        "из",
        "«ИнфоТек»",
        "сбиваются,",
        "дедлайны.",
    ]


def test_make_row_orders_spans_and_validates() -> None:
    tokens = tokenize("Маша работает в Яндексе с 2021")
    row = make_row(tokens, [[5, 5, "date_time"], [0, 0, "person"], [3, 3, "organization"]])
    assert row["tokenized_text"] == tokens
    # spans sorted by (start, end)
    assert row["ner"] == [[0, 0, "person"], [3, 3, "organization"], [5, 5, "date_time"]]
    assert validate_row(row) == []


@pytest.mark.parametrize(
    "ner, expect_error",
    [
        ([[0, 0, "person"]], False),
        ([], False),  # an example with no entities is valid
        ([[0, 5, "person"]], True),  # end out of range (only 2 tokens)
        ([[1, 0, "person"]], True),  # end < start
        ([[0, 0, "memory_item"]], True),  # forbidden / unknown label
        ([[0, 0]], True),  # malformed span
    ],
)
def test_validate_row_rejects_bad_spans(ner, expect_error) -> None:
    row = {"tokenized_text": ["я", "рад"], "ner": ner}
    errors = validate_row(row)
    assert bool(errors) is expect_error


def test_validate_rows_and_roundtrip(tmp_path: Path) -> None:
    rows = [
        make_row(tokenize("Кот Тимоша спит"), [[1, 1, "animal"]]),
        make_row(tokenize("Уехал в Москву вчера"), [[2, 2, "location"], [3, 3, "date_time"]]),
    ]
    valid, errors = validate_rows(rows)
    assert valid == 2
    assert errors == []

    path = tmp_path / "golden.jsonl"
    dump_jsonl(rows, path)
    assert load_jsonl(path) == rows
