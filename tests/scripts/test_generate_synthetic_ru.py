"""Regression tests for the synthetic Russian NER generator."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.eval import generate_synthetic_ru


def test_main_preserves_existing_dataset_when_generation_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "atman_ner_ru_synth.jsonl"
    original_content = '{"tokenized_text":["existing"],"ner":[]}\n'
    output_path.write_text(original_content, encoding="utf-8")

    monkeypatch.setattr(generate_synthetic_ru, "PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(generate_synthetic_ru, "DOMAIN_DESCRIPTIONS", ["test-domain"])
    monkeypatch.setattr(generate_synthetic_ru, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(generate_synthetic_ru, "_submit_job", lambda *_args: "job-1")
    monkeypatch.setattr(generate_synthetic_ru, "_poll_job", lambda _job_id: "ready")
    monkeypatch.setattr(generate_synthetic_ru, "_download_dataset", lambda _name: [])

    with pytest.raises(SystemExit) as exc_info:
        generate_synthetic_ru.main()

    assert exc_info.value.code == 1
    assert output_path.read_text(encoding="utf-8") == original_content
