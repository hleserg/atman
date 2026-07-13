"""Regression tests for synthetic Russian NER dataset generation safety."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.eval import generate_synthetic_ru as gen


def _row(text: str = "Маша читает книгу.") -> dict[str, object]:
    return {
        "tokenized_text": text.split(),
        "ner": [[0, 0, "person"]],
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_download_dataset_rejects_malformed_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        text = '{"text": "ok", "entities": []}\n{bad json'

        def raise_for_status(self) -> None:
            return None

    def fake_get(*_args: Any, **_kwargs: Any) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(gen, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(gen.requests, "get", fake_get)

    with pytest.raises(ValueError, match="line 2"):
        gen._download_dataset("broken-dataset")


def test_validate_jsonl_enforces_minimum_count(tmp_path: Path) -> None:
    output = tmp_path / "small.jsonl"
    _write_jsonl(output, [_row()])

    count, errors = gen.validate_jsonl(output, min_count=2)

    assert count == 1
    assert errors == ["expected at least 2 valid examples, got 1"]


def test_atomic_write_preserves_existing_file_on_validation_failure(tmp_path: Path) -> None:
    output = tmp_path / "atman_ner_ru_synth.jsonl"
    original_rows = [_row("Катя любит бег.")]
    _write_jsonl(output, original_rows)
    original_content = output.read_text(encoding="utf-8")
    replacement_rows = [_row("Маша читает книгу.")]

    with pytest.raises(ValueError, match="expected at least 2 valid examples"):
        gen._write_validated_jsonl(replacement_rows, output, min_count=2)

    assert output.read_text(encoding="utf-8") == original_content
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_replaces_file_after_successful_validation(tmp_path: Path) -> None:
    output = tmp_path / "atman_ner_ru_synth.jsonl"
    _write_jsonl(output, [_row("Старые данные.")])
    replacement = [_row("Маша читает книгу."), _row("Катя любит бег.")]

    count = gen._write_validated_jsonl(replacement, output, min_count=2)

    assert count == 2
    assert [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ] == replacement
