from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest


def test_gliner2_dataset_spans_match_source_text() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    examples = load_dataset()

    assert len(examples) == 130
    assert set(LABELS) == {
        "person",
        "organization",
        "location",
        "date_time",
        "event",
        "project",
        "product",
        "activity",
        "profession",
        "health",
        "emotion_word",
        "money",
        "animal",
    }

    for example in examples:
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)
        assert entities
        for entity in entities:
            assert entity["label"] in LABELS
            assert isinstance(entity["start"], int)
            assert isinstance(entity["end"], int)
            assert entity["start"] < entity["end"]
            assert text[entity["start"] : entity["end"]] == entity["text"]


def test_run_predictions_normalizes_gliner2_response_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGliner2Model:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str], float, bool]] = []

        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, dict[str, list[dict[str, object]]]]:
            self.calls.append((text, labels, threshold, include_spans))
            return {
                "entities": {
                    "person": [{"text": "Маша", "start": 0, "end": 4, "score": 0.99}],
                    "project": [{"text": "Atman", "start": 15, "end": 20, "score": 0.75}],
                }
            }

    model = FakeGliner2Model()
    predictions = baseline._run_predictions(
        model,
        "gliner2",
        [{"text": "Маша работает над Atman"}],
        threshold=0.42,
    )

    assert predictions == [
        [
            {"label": "person", "start": 0, "end": 4},
            {"label": "project", "start": 15, "end": 20},
        ]
    ]
    assert model.calls == [("Маша работает над Atman", LABELS, 0.42, True)]


def test_run_predictions_normalizes_standard_gliner_response_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGlinerModel:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str], float]] = []

        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, object]]:
            self.calls.append((text, labels, threshold))
            return [{"text": "Маша", "label": "person", "start": 0, "end": 4, "score": 0.91}]

    model = FakeGlinerModel()
    predictions = baseline._run_predictions(
        model,
        "gliner",
        [{"text": "Маша работает"}],
        threshold=0.7,
    )

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]
    assert model.calls == [("Маша работает", LABELS, 0.7)]


def test_compute_metrics_maps_strict_nervaluate_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeEvalResult:
        def __init__(self, precision: float, recall: float, f1: float) -> None:
            self.precision = precision
            self.recall = recall
            self.f1 = f1

    class FakeEvaluator:
        def __init__(
            self,
            gold: list[list[dict[str, object]]],
            pred: list[list[dict[str, object]]],
            *,
            tags: list[str],
        ) -> None:
            self.gold = gold
            self.pred = pred
            self.tags = tags

        def evaluate(self) -> dict[str, object]:
            assert self.tags == LABELS
            return {
                "overall": {"strict": FakeEvalResult(0.91234, 0.81234, 0.86234)},
                "entities": {
                    "person": {"strict": FakeEvalResult(1.0, 0.5, 0.66666)},
                },
            }

    class FakeNervaluateModule(types.ModuleType):
        Evaluator: type[FakeEvaluator]

    fake_nervaluate = FakeNervaluateModule("nervaluate")
    fake_nervaluate.Evaluator = FakeEvaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline._compute_metrics(
        gold=[[{"label": "person", "start": 0, "end": 4}]],
        pred=[[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.9123, "recall": 0.8123, "f1": 0.8623}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_models_instead_of_overwriting(tmp_path: Path) -> None:
    from atman.eval.gliner2 import baseline

    output = tmp_path / "gliner2_results.json"
    output.write_text(
        json.dumps(
            {
                "existing-model": {
                    "model": "existing-model",
                    "overall": {"f1": 0.9},
                }
            }
        ),
        encoding="utf-8",
    )

    baseline._save_results(
        output,
        "new-model",
        metrics={
            "overall": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
            "per_entity": {"person": {"precision": 0.5, "recall": 0.5, "f1": 0.5}},
        },
        n_examples=2,
        threshold=0.42,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"existing-model", "new-model"}
    assert saved["existing-model"]["overall"] == {"f1": 0.9}
    assert saved["new-model"]["threshold"] == 0.42
    assert saved["new-model"]["n_examples"] == 2
    assert saved["new-model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
