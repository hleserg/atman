from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from atman.eval.gliner2 import baseline
from atman.eval.gliner2.dataset import LABELS, load_dataset


def test_load_dataset_builds_valid_spans() -> None:
    dataset = load_dataset()

    assert dataset
    first = dataset[0]
    assert isinstance(first["text"], str)
    entities = first["entities"]
    assert isinstance(entities, list)
    assert entities
    for entity in entities:
        text = first["text"]
        assert isinstance(text, str)
        assert text[entity["start"] : entity["end"]] == entity["text"]
        assert entity["label"] in LABELS


def test_run_predictions_supports_gliner2_shape() -> None:
    class FakeGLiNER2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, Any]:
            assert text == "Маша пришла"
            assert "person" in labels
            assert threshold == pytest.approx(0.5)
            assert include_spans is True
            return {"entities": {"person": [{"start": 0, "end": 4}]}}

    predictions = baseline._run_predictions(
        FakeGLiNER2(),
        "gliner2",
        [{"text": "Маша пришла", "entities": []}],
        0.5,
    )

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_run_predictions_supports_standard_gliner_shape() -> None:
    class FakeGLiNER:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, Any]]:
            assert text == "Google открыл офис"
            assert "organization" in labels
            assert threshold == pytest.approx(0.4)
            return [{"label": "organization", "start": 0, "end": 6}]

    predictions = baseline._run_predictions(
        FakeGLiNER(),
        "gliner",
        [{"text": "Google открыл офис", "entities": []}],
        0.4,
    )

    assert predictions == [[{"label": "organization", "start": 0, "end": 6}]]


def test_compute_metrics_with_nervaluate_result(monkeypatch: pytest.MonkeyPatch) -> None:
    strict = SimpleNamespace(precision=0.75, recall=0.5, f1=0.6)

    class FakeEvaluator:
        def __init__(
            self,
            gold: list[list[dict[str, Any]]],
            pred: list[list[dict[str, Any]]],
            *,
            tags: list[str],
        ) -> None:
            self.gold = gold
            self.pred = pred
            self.tags = tags

        def evaluate(self) -> dict[str, Any]:
            assert self.tags == LABELS
            return {
                "overall": {"strict": strict},
                "entities": {"person": {"strict": strict}},
            }

    monkeypatch.setitem(sys.modules, "nervaluate", SimpleNamespace(Evaluator=FakeEvaluator))

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.75, "recall": 0.5, "f1": 0.6}
    assert metrics["per_entity"]["person"]["f1"] == pytest.approx(0.6)
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_model_entries(tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    output.write_text(json.dumps({"old-model": {"overall": {"f1": 0.1}}}), encoding="utf-8")

    baseline._save_results(
        output,
        "new-model",
        {
            "overall": {"precision": 0.8, "recall": 0.7, "f1": 0.75},
            "per_entity": {"person": {"precision": 0.8, "recall": 0.7, "f1": 0.75}},
        },
        n_examples=3,
        threshold=0.5,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert "old-model" in saved
    assert saved["new-model"]["n_examples"] == 3
    assert saved["new-model"]["conclusion"] == "F1 > 0.7: fine-tune опционален"


def test_cli_main_writes_results_without_loading_real_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(baseline, "_load_gliner", lambda model_id: (object(), "fake"))
    monkeypatch.setattr(
        baseline,
        "_run_predictions",
        lambda model, model_type, dataset, threshold: [[] for _ in dataset],
    )
    monkeypatch.setattr(
        baseline,
        "_compute_metrics",
        lambda gold, pred: {
            "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "per_entity": {label: {"precision": 0.0, "recall": 0.0, "f1": 0.0} for label in LABELS},
        },
    )
    output = tmp_path / "baseline.json"

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake/model", "--threshold", "0.42", "--output", str(output)],
    )

    assert result.exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake/model"]["threshold"] == pytest.approx(0.42)
    assert saved["fake/model"]["n_examples"] == len(load_dataset())
