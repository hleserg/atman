"""Regression tests for GLiNER2 eval artifact writes.

SYSTEM_MAP §5 regression freeze: eval data/results generation must not corrupt
previous artifacts when validation fails, downloads are malformed, or writes are
interrupted.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from importlib.abc import Loader
from pathlib import Path
from typing import Any, cast

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR_PATH = _ROOT / "scripts" / "eval" / "generate_synthetic_ru.py"
_BASELINE_PATH = _ROOT / "src" / "atman" / "eval" / "gliner2" / "baseline.py"


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def _load_generator(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_requests = types.ModuleType("requests")
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    spec = importlib.util.spec_from_file_location("atman_eval_generator_test", _GENERATOR_PATH)
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _load_baseline(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_eval = types.ModuleType("atman.eval")
    fake_eval.__path__ = []  # type: ignore[attr-defined]
    fake_gliner2 = types.ModuleType("atman.eval.gliner2")
    fake_gliner2.__path__ = []  # type: ignore[attr-defined]
    fake_dataset = types.ModuleType("atman.eval.gliner2.dataset")
    fake_dataset_any = cast(Any, fake_dataset)
    fake_dataset_any.LABELS = ["person"]
    fake_dataset_any.load_dataset = lambda: []

    monkeypatch.setitem(sys.modules, "atman.eval", fake_eval)
    monkeypatch.setitem(sys.modules, "atman.eval.gliner2", fake_gliner2)
    monkeypatch.setitem(sys.modules, "atman.eval.gliner2.dataset", fake_dataset)

    spec = importlib.util.spec_from_file_location("atman_eval_baseline_test", _BASELINE_PATH)
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_generator_preserves_existing_jsonl_when_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator(monkeypatch)
    output = tmp_path / "atman_ner_ru_synth.jsonl"
    original = {"tokenized_text": ["Маша"], "ner": [[0, 0, "person"]]}
    output.write_text(json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8")

    invalid_examples = [{"tokenized_text": ["Маша"], "ner": [[1, 0, "person"]]}]

    with pytest.raises(ValueError, match="generated JSONL failed validation"):
        generator.write_validated_jsonl(output, invalid_examples)

    assert output.read_text(encoding="utf-8") == json.dumps(original, ensure_ascii=False) + "\n"
    assert list(tmp_path.glob(".atman_ner_ru_synth.jsonl.*.tmp")) == []


def test_generator_rejects_malformed_download_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = _load_generator(monkeypatch)
    generator.PIONEER_API_KEY = "test-key"

    def fake_get(*_args: object, **_kwargs: object) -> _Response:
        return _Response('{"text":"ok","entities":[]}\n{not-json}\n')

    monkeypatch.setattr(generator.requests, "get", fake_get, raising=False)

    with pytest.raises(ValueError, match="Malformed JSONL from Pioneer download at line 2"):
        generator._download_dataset("dataset-name")


def test_baseline_atomic_write_preserves_existing_json_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _load_baseline(monkeypatch)
    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(_src: Path | str, _dst: Path | str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(baseline.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        baseline._atomic_write_json(output, {"new": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob(".gliner2_baseline_ru.json.*.tmp")) == []


def test_baseline_save_results_merges_existing_model_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _load_baseline(monkeypatch)
    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text('{"existing/model": {"model": "existing/model"}}\n', encoding="utf-8")
    metrics = {
        "overall": {"precision": 1.0, "recall": 0.5, "f1": 0.6667},
        "per_entity": {"person": {"precision": 1.0, "recall": 0.5, "f1": 0.6667}},
    }

    baseline._save_results(output, "new/model", metrics, n_examples=2, threshold=0.5)

    data = cast(dict[str, Any], json.loads(output.read_text(encoding="utf-8")))
    assert set(data) == {"existing/model", "new/model"}
    assert data["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
