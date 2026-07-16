"""Tests for the GLiNER2 Russian NER baseline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from atman.eval.gliner2.baseline import (
    _compute_metrics,
    _conclusion,
    _print_results,
    _run_predictions,
    _save_results,
)
from atman.eval.gliner2.dataset import LABELS, load_dataset


def test_load_dataset_builds_valid_spans() -> None:
    dataset = load_dataset()

    assert len(dataset) >= 130
    assert len(LABELS) == 13
    for example in dataset:
        text = str(example["text"])
        entities = example["entities"]
        assert isinstance(entities, list)
        for entity in entities:
            assert isinstance(entity, dict)
            start = int(entity["start"])
            end = int(entity["end"])
            assert text[start:end] == entity["text"]
            assert entity["label"] in LABELS


def test_run_predictions_supports_both_model_formats() -> None:
    dataset: list[dict[str, Any]] = [{"text": "Маша", "entities": []}]

    class _GLiNER2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, object]:
            assert text == "Маша"
            assert labels == LABELS
            assert threshold == pytest.approx(0.5)
            assert include_spans is True
            return {"entities": {"person": [{"start": 0, "end": 4}]}}

    class _GLiNER:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, object]]:
            assert text == "Маша"
            assert labels == LABELS
            assert threshold == pytest.approx(0.5)
            return [{"label": "person", "start": 0, "end": 4}]

    expected = [[{"label": "person", "start": 0, "end": 4}]]
    assert _run_predictions(_GLiNER2(), "gliner2", dataset, 0.5) == expected
    assert _run_predictions(_GLiNER(), "gliner", dataset, 0.5) == expected


def test_compute_metrics_normalizes_scores_and_missing_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    score = SimpleNamespace(precision=0.87654, recall=0.76543, f1=0.81234)

    class _Evaluator:
        def __init__(
            self,
            gold: list[list[dict[str, Any]]],
            pred: list[list[dict[str, Any]]],
            *,
            tags: list[str],
        ) -> None:
            assert gold == [[]]
            assert pred == [[]]
            assert tags == LABELS

        def evaluate(self) -> dict[str, object]:
            return {
                "overall": {"strict": score},
                "entities": {"person": {"strict": score}},
            }

    monkeypatch.setitem(sys.modules, "nervaluate", SimpleNamespace(Evaluator=_Evaluator))

    metrics = _compute_metrics([[]], [[]])

    assert metrics["overall"] == {"precision": 0.8765, "recall": 0.7654, "f1": 0.8123}
    assert metrics["per_entity"]["person"]["f1"] == pytest.approx(0.8123)
    assert metrics["per_entity"]["organization"] == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        (0.71, "F1 > 0.7: fine-tune опционален"),
        (0.4, "F1 0.4–0.7: fine-tune нужен"),
        (0.39, "F1 < 0.4: рассмотреть смену базовой модели"),
    ],
)
def test_conclusion_thresholds(f1: float, expected: str) -> None:
    assert _conclusion(f1) == expected


def test_print_and_save_results_cover_all_verdict_bands(tmp_path: Path) -> None:
    output = tmp_path / "results" / "baseline.json"
    per_entity = {
        "high": {"precision": 0.9, "recall": 0.8, "f1": 0.8},
        "medium": {"precision": 0.6, "recall": 0.5, "f1": 0.5},
        "low": {"precision": 0.3, "recall": 0.2, "f1": 0.2},
    }

    for model_id, f1 in (("model/high", 0.8), ("model/medium", 0.5), ("model/low", 0.2)):
        metrics = {
            "overall": {"precision": f1, "recall": f1, "f1": f1},
            "per_entity": per_entity,
        }
        _print_results(model_id, metrics)
        _save_results(output, model_id, metrics, n_examples=130, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"model/high", "model/medium", "model/low"}
    assert saved["model/high"]["conclusion"] == "F1 > 0.7: fine-tune опционален"
    assert saved["model/medium"]["n_examples"] == 130
