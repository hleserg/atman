"""Regression tests for the synthetic Russian NER data generator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import patch

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
    with patch.dict(sys.modules, {"requests": requests_stub}):
        spec.loader.exec_module(module)
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


@pytest.mark.parametrize("status", ["ready", "failed"])
def test_poll_job_returns_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    response = _FakeResponse(json_data={"status": status})
    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator.requests, "get", lambda *args, **kwargs: response, raising=False)
    monkeypatch.setattr(generator.time, "monotonic", lambda: 0.0)

    assert generator._poll_job("job-123", max_wait=1) == status
    assert response.raise_for_status_called


def test_poll_job_returns_timeout_without_requesting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator.time, "monotonic", lambda: 0.0)

    assert generator._poll_job("job-123", max_wait=0) == "timeout"


def test_poll_job_retries_pending_status_until_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _FakeResponse(json_data={"status": "pending"}),
            _FakeResponse(json_data={"status": "ready"}),
        ]
    )
    monotonic_values = iter([0.0, 0.0, 1.0, 2.0, 3.0])
    sleeps: list[int] = []
    request_count = 0

    def fake_get(*args: object, **kwargs: object) -> _FakeResponse:
        nonlocal request_count
        request_count += 1
        return next(responses)

    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(generator.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(generator.time, "sleep", sleeps.append)

    assert generator._poll_job("job-123", max_wait=10) == "ready"
    assert request_count == 2
    assert sleeps == [10]


def test_poll_job_times_out_after_pending_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(json_data={"status": "pending"})
    monotonic_values = iter([0.0, 0.0, 1.0, 5.0])
    sleeps: list[int] = []

    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator.requests, "get", lambda *args, **kwargs: response, raising=False)
    monkeypatch.setattr(generator.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(generator.time, "sleep", sleeps.append)

    assert generator._poll_job("job-123", max_wait=5) == "timeout"
    assert response.raise_for_status_called
    assert sleeps == [10]


def test_main_aggregates_batches_and_writes_valid_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "synthetic.jsonl"
    submitted: list[tuple[str, int, str]] = []

    def fake_submit(dataset_name: str, num_examples: int, domain_description: str) -> str:
        submitted.append((dataset_name, num_examples, domain_description))
        return f"job-{len(submitted)}"

    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator, "DOMAIN_DESCRIPTIONS", ["diary", "chat"])
    monkeypatch.setattr(generator, "OUTPUT_PATH", output)
    monkeypatch.setattr(generator.time, "time", lambda: 1234.0)
    monkeypatch.setattr(generator, "_submit_job", fake_submit)
    monkeypatch.setattr(generator, "_poll_job", lambda job_id: "ready")
    monkeypatch.setattr(
        generator,
        "_download_dataset",
        lambda dataset_name: [{"text": f"Анна {dataset_name}", "entities": [["Анна", "person"]]}],
    )
    monkeypatch.setattr(generator, "spot_check", lambda path, n: None)

    generator.main()

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(submitted) == 2
    assert [item[2] for item in submitted] == ["diary", "chat"]
    assert rows == [
        {"tokenized_text": ["Анна", "atman-ner-ru-synth-v1-b1-1234"], "ner": [[0, 0, "person"]]},
        {"tokenized_text": ["Анна", "atman-ner-ru-synth-v1-b2-1234"], "ner": [[0, 0, "person"]]},
    ]


def test_main_exits_when_generation_job_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "synthetic.jsonl"
    monkeypatch.setattr(generator, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generator, "DOMAIN_DESCRIPTIONS", ["diary"])
    monkeypatch.setattr(generator, "OUTPUT_PATH", output)
    monkeypatch.setattr(generator, "_submit_job", lambda *args: "job-1")
    monkeypatch.setattr(generator, "_poll_job", lambda job_id: "failed")

    with pytest.raises(SystemExit) as exc_info:
        generator.main()

    assert exc_info.value.code == 1
    assert not output.exists()


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
    observed_labels: set[str] = set()
    for raw in SYNTHETIC_DATA_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        observed_labels.update(span[2] for span in row["ner"])

    assert errors == []
    assert count >= 1500
    assert observed_labels == generator.VALID_LABELS
