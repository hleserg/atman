"""Regression tests for the synthetic Russian NER data generator."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast


def _load_generator() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "eval" / "generate_synthetic_ru.py"
    )
    spec = importlib.util.spec_from_file_location("generate_synthetic_ru", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pioneer_to_gliner_filters_bad_entities_and_keeps_token_spans() -> None:
    generator = _load_generator()
    pioneer_to_gliner = cast(
        Callable[[dict[str, object]], dict[str, object] | None],
        getattr(generator, "pioneer_to_gliner"),
    )

    converted = pioneer_to_gliner(
        {
            "text": "В марте проект Atman запустили в Яндекс Практикуме.",
            "entities": [
                ("марте", "date_time"),
                ("Atman", "project"),
                ("Яндекс Практикуме", "organization"),
                ("не найдено", "project"),
                ("Atman", "unsupported_label"),
                ("Atman", "project"),
                ("broken-entry",),
            ],
        }
    )

    assert converted == {
        "tokenized_text": [
            "В",
            "марте",
            "проект",
            "Atman",
            "запустили",
            "в",
            "Яндекс",
            "Практикуме.",
        ],
        "ner": [[1, 1, "date_time"], [3, 3, "project"], [6, 7, "organization"]],
    }


def test_pioneer_to_gliner_rejects_blank_text() -> None:
    generator = _load_generator()
    pioneer_to_gliner = cast(
        Callable[[dict[str, object]], dict[str, object] | None],
        getattr(generator, "pioneer_to_gliner"),
    )

    assert pioneer_to_gliner({"text": "   ", "entities": [("Atman", "project")]}) is None


def test_validate_jsonl_reports_line_level_data_errors(tmp_path: Path) -> None:
    generator = _load_generator()
    validate_jsonl = cast(
        Callable[[Path], tuple[int, list[str]]],
        getattr(generator, "validate_jsonl"),
    )
    rows: list[str] = [
        json.dumps(
            {"tokenized_text": ["Маша", "рада"], "ner": [[0, 0, "person"], [1, 1, "emotion_word"]]},
            ensure_ascii=False,
        ),
        "",
        "{not-json}",
        json.dumps({"tokenized_text": [], "ner": []}, ensure_ascii=False),
        json.dumps({"tokenized_text": ["Atman"]}, ensure_ascii=False),
        json.dumps({"tokenized_text": ["Atman"], "ner": [[1, 0, "project"]]}, ensure_ascii=False),
        json.dumps({"tokenized_text": ["Atman"], "ner": [[0, 0, "unknown"]]}, ensure_ascii=False),
    ]
    path = tmp_path / "synthetic.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    count, errors = validate_jsonl(path)

    assert count == 1
    assert len(errors) == 5
    assert errors[0].startswith("line 3: JSON error:")
    assert errors[1] == "line 4: missing or empty 'tokenized_text'"
    assert errors[2] == "line 5: missing 'ner'"
    assert errors[3] == "line 6: span [1,0] invalid for 1 tokens"
    assert errors[4] == "line 7: unknown label 'unknown'"
