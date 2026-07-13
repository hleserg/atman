"""Tests for the GLiNER2 baseline eval helpers."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner


class _FakeGLiNER2Model:
    def extract_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
        include_spans: bool,
    ) -> dict[str, dict[str, list[dict[str, int]]]]:
        assert text == "Маша дома"
        assert "person" in labels
        assert threshold == pytest.approx(0.5)
        assert include_spans is True
        return {"entities": {"person": [{"start": 0, "end": 4}]}}


class _FakeStandardGLiNERModel:
    def predict_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
    ) -> list[dict[str, int | str]]:
        assert text == "Маша дома"
        assert "person" in labels
        assert threshold == pytest.approx(0.5)
        return [{"label": "person", "start": 0, "end": 4}]


class _FakeEvaluator:
    def __init__(
        self,
        gold: list[list[dict[str, Any]]],
        pred: list[list[dict[str, Any]]],
        tags: list[str],
    ) -> None:
        assert gold == [[{"label": "person", "start": 0, "end": 4}]]
        assert pred == [[{"label": "person", "start": 0, "end": 4}]]
        assert "person" in tags

    def evaluate(self) -> dict[str, Any]:
        strict = SimpleNamespace(precision=0.12345, recall=0.5, f1=0.75)
        person = SimpleNamespace(precision=1.0, recall=0.5, f1=0.66666)
        return {
            "overall": {"strict": strict},
            "entities": {"person": {"strict": person}},
        }


class _FakeNervaluateModule(ModuleType):
    Evaluator: type[_FakeEvaluator]


@pytest.fixture()
def gliner2_modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """Load GLiNER2 files without requiring the heavy atman[eval] extras."""
    repo_root = Path(__file__).resolve().parents[2]
    fake_eval = ModuleType("atman.eval")
    fake_eval.__path__ = [str(repo_root / "src" / "atman" / "eval")]
    monkeypatch.setitem(sys.modules, "atman.eval", fake_eval)
    for module_name in (
        "atman.eval.gliner2",
        "atman.eval.gliner2.baseline",
        "atman.eval.gliner2.dataset",
    ):
        monkeypatch.delitem(sys.modules, module_name, raising=False)
    dataset_module = importlib.import_module("atman.eval.gliner2.dataset")
    baseline_module = importlib.import_module("atman.eval.gliner2.baseline")
    return baseline_module, dataset_module


def test_load_dataset_resolves_declared_spans(gliner2_modules: tuple[Any, Any]) -> None:
    _baseline, dataset_module = gliner2_modules
    dataset = dataset_module.load_dataset()

    assert len(dataset) > 100
    for example in dataset:
        text = example["text"]
        assert isinstance(text, str)
        for entity in example["entities"]:
            label = entity["label"]
            start = entity["start"]
            end = entity["end"]
            entity_text = entity["text"]
            assert label in dataset_module.LABELS
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(entity_text, str)
            assert text[start:end] == entity_text


def test_run_predictions_supports_gliner2_output(gliner2_modules: tuple[Any, Any]) -> None:
    baseline_module, _dataset_module = gliner2_modules
    dataset: list[dict[str, Any]] = [{"text": "Маша дома", "entities": []}]

    predictions = baseline_module._run_predictions(_FakeGLiNER2Model(), "gliner2", dataset, 0.5)

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_run_predictions_supports_standard_gliner_output(
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline_module, _dataset_module = gliner2_modules
    dataset: list[dict[str, Any]] = [{"text": "Маша дома", "entities": []}]

    predictions = baseline_module._run_predictions(
        _FakeStandardGLiNERModel(), "gliner", dataset, 0.5
    )

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_compute_metrics_rounds_strict_scores(
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline_module, _dataset_module = gliner2_modules
    fake_nervaluate = _FakeNervaluateModule("nervaluate")
    fake_nervaluate.Evaluator = _FakeEvaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline_module._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.1235, "recall": 0.5, "f1": 0.75}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline_module, _dataset_module = gliner2_modules
    output = tmp_path / "results.json"
    output.write_text(json.dumps({"old-model": {"model": "old-model"}}), encoding="utf-8")
    monkeypatch.setattr(baseline_module, "print_ok", lambda _message: None)

    baseline_module._save_results(
        output,
        "new-model",
        {
            "overall": {"precision": 0.1, "recall": 0.2, "f1": 0.3},
            "per_entity": {"person": {"precision": 0.1, "recall": 0.2, "f1": 0.3}},
        },
        n_examples=2,
        threshold=0.5,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["old-model"]["model"] == "old-model"
    assert saved["new-model"]["n_examples"] == 2
    assert saved["new-model"]["conclusion"] == "F1 < 0.4: рассмотреть смену базовой модели"


def test_main_runs_with_patched_model_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline_module, _dataset_module = gliner2_modules
    output = tmp_path / "baseline.json"
    monkeypatch.setattr(baseline_module, "_load_gliner", lambda _model: (object(), "gliner"))
    monkeypatch.setattr(
        baseline_module,
        "_run_predictions",
        lambda _model, _model_type, dataset, _threshold: [[] for _ in dataset],
    )
    monkeypatch.setattr(
        baseline_module,
        "_compute_metrics",
        lambda _gold, _pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "per_entity": {},
        },
    )
    monkeypatch.setattr(baseline_module, "_print_results", lambda _model, _metrics: None)
    monkeypatch.setattr(baseline_module, "print_ok", lambda _message: None)

    result = CliRunner().invoke(
        baseline_module.main,
        ["--model", "fake/model", "--threshold", "0.5", "--output", str(output)],
    )

    assert result.exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake/model"]["conclusion"] == "F1 > 0.7: fine-tune опционален"
