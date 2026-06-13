from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_generator(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_requests = ModuleType("requests")
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    module = importlib.import_module("scripts.eval.generate_synthetic_ru")
    return importlib.reload(module)


def test_pioneer_to_gliner_maps_token_spans_and_filters_invalid_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator(monkeypatch)

    converted = generator.pioneer_to_gliner(
        {
            "text": "Маша  ведёт проект Atman в Санкт-Петербурге",
            "entities": [
                ["Маша", "person"],
                ["Маша", "person"],
                ["Atman", "project"],
                ["Санкт-Петербурге", "location"],
                ["не найдено", "person"],
                ["Atman", "unknown_label"],
                ["broken"],
                [123, "person"],
            ],
        }
    )

    assert converted == {
        "tokenized_text": ["Маша", "ведёт", "проект", "Atman", "в", "Санкт-Петербурге"],
        "ner": [[0, 0, "person"], [3, 3, "project"], [5, 5, "location"]],
    }


def test_find_span_respects_search_offset_for_repeated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator(monkeypatch)
    text = "Маша сказала: Маша придёт завтра"
    tokens, offsets = generator._tokenize_with_offsets(text)

    first = generator._find_span(tokens, offsets, text, "Маша")
    second = generator._find_span(tokens, offsets, text, "Маша", search_from=text.find("Маша", 1))

    assert first == (0, 0)
    assert second == (2, 2)


def test_validate_jsonl_accepts_valid_rows_and_reports_invalid_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator(monkeypatch)
    path = tmp_path / "synthetic.jsonl"
    rows = [
        {"tokenized_text": ["Маша", "дома"], "ner": [[0, 0, "person"]]},
        {"tokenized_text": ["Atman"], "ner": [[0, 2, "project"]]},
        {"tokenized_text": ["Atman"], "ner": [[0, 0, "not_a_label"]]},
        {"tokenized_text": [], "ner": []},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n{bad json}\n",
        encoding="utf-8",
    )

    count, errors = generator.validate_jsonl(path)

    assert count == 1
    assert len(errors) == 4
    assert any("span [0,2] invalid" in error for error in errors)
    assert any("unknown label 'not_a_label'" in error for error in errors)
    assert any("missing or empty 'tokenized_text'" in error for error in errors)
    assert any("JSON error" in error for error in errors)
