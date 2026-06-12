"""Tests for the GLiNER2 baseline eval helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from click.testing import CliRunner

from atman.eval.gliner2 import baseline
from atman.eval.gliner2.dataset import LABELS, load_dataset


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
        assert labels == LABELS
        assert threshold == 0.5
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
        assert labels == LABELS
        assert threshold == 0.5
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
        assert tags == LABELS

    def evaluate(self) -> dict[str, Any]:
        strict = SimpleNamespace(precision=0.12345, recall=0.5, f1=0.75)
        person = SimpleNamespace(precision=1.0, recall=0.5, f1=0.66666)
        return {
            "overall": {"strict": strict},
            "entities": {"person": {"strict": person}},
        }


def test_load_dataset_resolves_declared_spans() -> None:
    dataset = load_dataset()

    assert len(dataset) > 100
    for example in dataset:
        text = example["text"]
        assert isinstance(text, str)
        for entity in example["entities"]:
            label = entity["label"]
            start = entity["start"]
            end = entity["end"]
            entity_text = entity["text"]
            assert label in LABELS
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(entity_text, str)
            assert text[start:end] == entity_text


def test_run_predictions_supports_gliner2_output() -> None:
    dataset: list[dict[str, Any]] = [{"text": "Маша дома", "entities": []}]

    predictions = baseline._run_predictions(_FakeGLiNER2Model(), "gliner2", dataset, 0.5)

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_run_predictions_supports_standard_gliner_output() -> None:
    dataset: list[dict[str, Any]] = [{"text": "Маша дома", "entities": []}]

    predictions = baseline._run_predictions(_FakeStandardGLiNERModel(), "gliner", dataset, 0.5)

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_compute_metrics_rounds_strict_scores(monkeypatch: Any) -> None:
    fake_nervaluate = ModuleType("nervaluate")
    setattr(fake_nervaluate, "Evaluator", _FakeEvaluator)
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.1235, "recall": 0.5, "f1": 0.75}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_existing_output(tmp_path: Path, monkeypatch: Any) -> None:
    output = tmp_path / "results.json"
    output.write_text(json.dumps({"old-model": {"model": "old-model"}}), encoding="utf-8")
    monkeypatch.setattr(baseline, "print_ok", lambda _message: None)

    baseline._save_results(
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


def test_main_runs_with_patched_model_pipeline(tmp_path: Path, monkeypatch: Any) -> None:
    output = tmp_path / "baseline.json"
    monkeypatch.setattr(baseline, "_load_gliner", lambda _model: (object(), "gliner"))
    monkeypatch.setattr(
        baseline,
        "_run_predictions",
        lambda _model, _model_type, dataset, _threshold: [[] for _ in dataset],
    )
    monkeypatch.setattr(
        baseline,
        "_compute_metrics",
        lambda _gold, _pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "per_entity": {},
        },
    )
    monkeypatch.setattr(baseline, "_print_results", lambda _model, _metrics: None)
    monkeypatch.setattr(baseline, "print_ok", lambda _message: None)

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake/model", "--threshold", "0.5", "--output", str(output)],
    )

    assert result.exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake/model"]["conclusion"] == "F1 > 0.7: fine-tune опционален"
