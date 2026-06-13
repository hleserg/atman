"""Regression tests for the Russian synthetic NER data generator."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "generate_synthetic_ru.py"


def _load_generator_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_requests = types.ModuleType("requests")
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    spec = importlib.util.spec_from_file_location("generate_synthetic_ru_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return cast(Any, module)


def _valid_example() -> dict[str, Any]:
    return {"tokenized_text": ["Маша", "пишет"], "ner": [[0, 0, "person"]]}


def test_validate_jsonl_rejects_empty_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _load_generator_module(monkeypatch)
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    count, errors = generator.validate_jsonl(path)

    assert count == 0
    assert "expected at least 1 valid examples, got 0" in errors


def test_validate_jsonl_rejects_conflicting_and_overlapping_spans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _load_generator_module(monkeypatch)
    path = tmp_path / "bad.jsonl"
    rows = [
        {"tokenized_text": ["Atman"], "ner": [[0, 0, "project"], [0, 0, "product"]]},
        {"tokenized_text": ["кот", "Тимоша"], "ner": [[0, 1, "animal"], [1, 1, "person"]]},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    count, errors = generator.validate_jsonl(path, min_count=0)

    assert count == 0
    assert any("conflicting labels" in error for error in errors)
    assert any("overlapping spans" in error for error in errors)


def test_pioneer_to_gliner_drops_ambiguous_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = _load_generator_module(monkeypatch)

    assert (
        generator.pioneer_to_gliner(
            {
                "text": "Atman помогает агенту помнить Atman.",
                "entities": [["Atman", "project"], ["Atman", "product"]],
            }
        )
        is None
    )
    assert (
        generator.pioneer_to_gliner(
            {
                "text": "кот Тимоша спит",
                "entities": [["кот Тимоша", "animal"], ["Тимоша", "person"]],
            }
        )
        is None
    )


def test_download_dataset_fails_on_malformed_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = _load_generator_module(monkeypatch)

    class FakeResponse:
        text = '{"text": "ok", "entities": []}\nnot-json\n'

        def raise_for_status(self) -> None:
            return None

    fake_requests = SimpleNamespace(get=lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(generator, "requests", fake_requests)
    monkeypatch.setattr(generator, "_pioneer_headers", lambda: {})

    with pytest.raises(RuntimeError, match="malformed JSONL"):
        generator._download_dataset("dataset-name")


def test_atomic_write_preserves_existing_file_on_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _load_generator_module(monkeypatch)
    output = tmp_path / "atman_ner_ru_synth.jsonl"
    output.write_text("sentinel\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        generator._write_jsonl_atomic(output, [_valid_example()])

    assert output.read_text(encoding="utf-8") == "sentinel\n"
    assert not output.with_name(f".{output.name}.tmp").exists()


def test_atomic_write_replaces_file_after_successful_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _load_generator_module(monkeypatch)
    monkeypatch.setattr(generator, "MIN_REQUIRED_EXAMPLES", 1)
    output = tmp_path / "atman_ner_ru_synth.jsonl"
    output.write_text("old\n", encoding="utf-8")

    generator._write_jsonl_atomic(output, [_valid_example()])

    count, errors = generator.validate_jsonl(output)
    assert count == 1
    assert errors == []
