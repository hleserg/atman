"""Regression tests for the synthetic Russian NER data generator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "generate_synthetic_ru.py"
SYNTHETIC_DATA_PATH = REPO_ROOT / "eval" / "data" / "atman_ner_ru_synth.jsonl"


def _load_generator() -> Any:
    """Load the standalone script without requiring the optional requests package."""
    spec = importlib.util.spec_from_file_location("generate_synthetic_ru_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    requests_stub = ModuleType("requests")
    previous_requests = sys.modules.get("requests")
    sys.modules["requests"] = requests_stub
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = previous_requests
    return cast(Any, module)


generator = _load_generator()


class _FakeResponse:
    def __init__(self, *, json_data: dict[str, object] | None = None, text: str = "") -> None:
        self._json_data = json_data or {}
        self.text = text
        self.raise_for_status_called = False

    def raise_for_status(self) -> None:
        self.raise_for_status_called = True

    def json(self) -> dict[str, object]:
        return self._json_data


def _write_jsonl(path: Path, rows: list[dict[str, object] | str]) -> None:
    lines = [row if isinstance(row, str) else json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_pioneer_to_gliner_maps_multitoken_entities_and_deduplicates() -> None:
    row = {
        "text": "Анна работает в Новой Москве.",
        "entities": [
            ["Анна", "person"],
            ["Новой Москве", "location "],
            ["Новой Москве", "location"],
        ],
    }

    result = generator.pioneer_to_gliner(row)

    assert result == {
        "tokenized_text": ["Анна", "работает", "в", "Новой", "Москве."],
        "ner": [[0, 0, "person"], [3, 4, "location"]],
    }


def test_pioneer_to_gliner_ignores_malformed_or_unmappable_entities() -> None:
    row = {
        "text": "Анна начала проект.",
        "entities": [
            ["Анна", "person"],
            ["Анна", "unsupported_label"],
            ["Отсутствует", "person"],
            ["Анна"],
            {"text": "Анна", "label": "person"},
            ["Анна", None],
        ],
    }

    result = generator.pioneer_to_gliner(row)

    assert result == {
        "tokenized_text": ["Анна", "начала", "проект."],
        "ner": [[0, 0, "person"]],
    }


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_pioneer_to_gliner_rejects_blank_text(text: str) -> None:
    assert generator.pioneer_to_gliner({"text": text, "entities": []}) is None


def test_submit_job_sends_expected_pioneer_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(json_data={"job_id": "job-123"})
    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> _FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return response

    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator.requests, "post", fake_post, raising=False)

    job_id = generator._submit_job("dataset-1", 42, "Личные заметки")

    assert job_id == "job-123"
    assert response.raise_for_status_called
    assert request["url"] == "https://api.pioneer.ai/generate"
    assert request["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert request["json"] == {
        "task_type": "ner",
        "dataset_name": "dataset-1",
        "num_examples": 42,
        "labels": generator.LABELS,
        "domain_description": "Личные заметки",
        "generation_profile": "balanced",
        "negative_ratio": 10,
    }
    assert request["timeout"] == 30


def test_pioneer_headers_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generator, "PIONEER_API_KEY", "")

    with pytest.raises(RuntimeError, match="PIONEER_API_KEY"):
        generator._pioneer_headers()


def test_download_dataset_parses_valid_jsonl_and_skips_invalid_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        text='{"text": "Анна", "entities": []}\nnot-json\n\n{"text": "Борис", "entities": []}\n'
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> _FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return response

    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator.requests, "get", fake_get, raising=False)

    rows = generator._download_dataset("dataset-1")

    assert rows == [
        {"text": "Анна", "entities": []},
        {"text": "Борис", "entities": []},
    ]
    assert response.raise_for_status_called
    assert request["url"] == ("https://api.pioneer.ai/felix/datasets/dataset-1/latest/download")
    assert request["params"] == {"format": "jsonl"}
    assert request["timeout"] == 120


def test_validate_jsonl_counts_valid_rows_and_ignores_blanks(tmp_path: Path) -> None:
    path = tmp_path / "valid.jsonl"
    _write_jsonl(
        path,
        [
            {"tokenized_text": ["Анна", "пришла"], "ner": [[0, 0, "person"]]},
            "",
            {"tokenized_text": ["Тишина"], "ner": []},
        ],
    )

    count, errors = generator.validate_jsonl(path)

    assert count == 2
    assert errors == []


@pytest.mark.parametrize(
    ("row", "error_fragment"),
    [
        ({"tokenized_text": [], "ner": []}, "missing or empty 'tokenized_text'"),
        ({"tokenized_text": ["Анна"]}, "missing 'ner'"),
        (
            {"tokenized_text": ["Анна"], "ner": [[0, 0]]},
            "ner span must be [start, end, label]",
        ),
        ({"tokenized_text": ["Анна"], "ner": [[0.0, 0, "person"]]}, "indices must be int"),
        (
            {"tokenized_text": ["Анна"], "ner": [[0, 1, "person"]]},
            "span [0,1] invalid for 1 tokens",
        ),
        (
            {"tokenized_text": ["Анна"], "ner": [[0, 0, "unknown"]]},
            "unknown label 'unknown'",
        ),
    ],
)
def test_validate_jsonl_rejects_invalid_rows(
    tmp_path: Path,
    row: dict[str, object],
    error_fragment: str,
) -> None:
    path = tmp_path / "invalid.jsonl"
    _write_jsonl(path, [row])

    count, errors = generator.validate_jsonl(path)

    assert count == 0
    assert len(errors) == 1
    assert error_fragment in errors[0]


def test_validate_jsonl_reports_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "malformed.jsonl"
    _write_jsonl(path, ['{"tokenized_text":'])

    count, errors = generator.validate_jsonl(path)

    assert count == 0
    assert len(errors) == 1
    assert errors[0].startswith("line 1: JSON error:")


def test_committed_synthetic_dataset_meets_format_and_size_contract() -> None:
    count, errors = generator.validate_jsonl(SYNTHETIC_DATA_PATH)

    assert errors == []
    assert count >= 1500
