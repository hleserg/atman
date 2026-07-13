"""Regression tests for synthetic Russian NER data conversion and validation."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from importlib.abc import Loader
from pathlib import Path
from typing import Protocol, cast

_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR_PATH = _ROOT / "scripts" / "eval" / "generate_synthetic_ru.py"
_MISSING = object()


class _GeneratorModule(Protocol):
    def pioneer_to_gliner(self, row: dict[str, object]) -> dict[str, object] | None: ...

    def validate_jsonl(self, path: Path) -> tuple[int, list[str]]: ...


def _load_generator_file(path: Path, name: str) -> _GeneratorModule:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return cast(_GeneratorModule, module)


def _load_generator_module() -> _GeneratorModule:
    fake_requests = types.ModuleType("requests")
    previous_requests = sys.modules.get("requests", _MISSING)
    try:
        sys.modules["requests"] = fake_requests
        return _load_generator_file(_GENERATOR_PATH, "atman_synthetic_ru_generator_test")
    finally:
        if previous_requests is _MISSING:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = cast(types.ModuleType, previous_requests)


def test_pioneer_to_gliner_maps_token_spans_and_filters_bad_entities() -> None:
    generator = _load_generator_module()
    row = {
        "text": "Маша встретила кота Мурзика в Санкт-Петербурге.",
        "entities": [
            ["Маша", "person"],
            ["кота Мурзика", "animal"],
            ["Санкт-Петербурге", "location"],
            ["кота Мурзика", "animal"],
            ["несуществующая сущность", "event"],
            ["Маша", "unsupported_label"],
            ["malformed-only-one-item"],
        ],
    }

    converted = generator.pioneer_to_gliner(row)

    assert converted == {
        "tokenized_text": ["Маша", "встретила", "кота", "Мурзика", "в", "Санкт-Петербурге."],
        "ner": [[0, 0, "person"], [2, 3, "animal"], [5, 5, "location"]],
    }


def test_pioneer_to_gliner_returns_none_for_blank_text() -> None:
    generator = _load_generator_module()

    assert generator.pioneer_to_gliner({"text": "   ", "entities": []}) is None


def test_validate_jsonl_counts_valid_rows_and_reports_line_errors(tmp_path: Path) -> None:
    generator = _load_generator_module()
    jsonl_path = tmp_path / "synthetic.jsonl"
    rows = [
        {"tokenized_text": ["Маша", "дома"], "ner": [[0, 0, "person"]]},
        {"tokenized_text": ["кот"], "ner": [[0, 1, "animal"]]},
        {"tokenized_text": ["тайна"], "ner": [[0, 0, "unknown_label"]]},
        {"tokenized_text": [], "ner": []},
    ]
    jsonl_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n{bad json}\n",
        encoding="utf-8",
    )

    count, errors = generator.validate_jsonl(jsonl_path)

    assert count == 1
    assert errors == [
        "line 2: span [0,1] invalid for 1 tokens",
        "line 3: unknown label 'unknown_label'",
        "line 4: missing or empty 'tokenized_text'",
        (
            "line 5: JSON error: Expecting property name enclosed in double quotes: "
            "line 1 column 2 (char 1)"
        ),
    ]
