from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        (0.7001, "fine-tune опционален"),
        (0.7, "fine-tune нужен"),
        (0.4, "fine-tune нужен"),
        (0.3999, "смену базовой модели"),
    ],
)
def test_conclusion_thresholds_match_baseline_policy(f1: float, expected: str) -> None:
    from atman.eval.gliner2 import baseline

    assert expected in baseline._conclusion(f1)


def test_run_predictions_supports_gliner2_extract_entities_shape() -> None:
    from atman.eval.gliner2 import baseline

    class FakeGliner2Model:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, dict[str, list[dict[str, int]]]]:
            assert text == "Маша приехала в Москву."
            assert labels == baseline.LABELS
            assert threshold == 0.5
            assert include_spans is True
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4}],
                    "location": [{"start": 16, "end": 22}],
                }
            }

    predictions = baseline._run_predictions(
        FakeGliner2Model(),
        "gliner2",
        [{"text": "Маша приехала в Москву."}],
        0.5,
    )

    assert predictions == [
        [
            {"label": "person", "start": 0, "end": 4},
            {"label": "location", "start": 16, "end": 22},
        ]
    ]


def test_run_predictions_supports_standard_gliner_predict_entities_shape() -> None:
    from atman.eval.gliner2 import baseline

    class FakeGlinerModel:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, int | str | float]]:
            assert text == "Atman помогает агентам."
            assert labels == baseline.LABELS
            assert threshold == 0.4
            return [{"label": "project", "start": 0, "end": 5, "score": 0.9}]

    predictions = baseline._run_predictions(
        FakeGlinerModel(),
        "gliner",
        [{"text": "Atman помогает агентам."}],
        0.4,
    )

    assert predictions == [[{"label": "project", "start": 0, "end": 5}]]


def test_compute_metrics_rounds_values_and_fills_missing_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2 import baseline

    class EvalResult:
        def __init__(self, precision: float, recall: float, f1: float) -> None:
            self.precision = precision
            self.recall = recall
            self.f1 = f1

    class FakeEvaluator:
        def __init__(
            self,
            gold: list[list[dict[str, Any]]],
            pred: list[list[dict[str, Any]]],
            *,
            tags: list[str],
        ) -> None:
            assert gold == [[{"label": "person", "start": 0, "end": 4}]]
            assert pred == [[{"label": "person", "start": 0, "end": 4}]]
            assert tags == baseline.LABELS

        def evaluate(self) -> dict[str, Any]:
            return {
                "overall": {"strict": EvalResult(0.12345, 0.98765, 0.55555)},
                "entities": {"person": {"strict": EvalResult(0.22224, 0.33335, 0.44446)}},
            }

    monkeypatch.setitem(sys.modules, "nervaluate", SimpleNamespace(Evaluator=FakeEvaluator))

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.1235, "recall": 0.9877, "f1": 0.5555}
    assert metrics["per_entity"]["person"] == {
        "precision": 0.2222,
        "recall": 0.3333,
        "f1": 0.4445,
    }
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_model_entry_without_dropping_existing_results(
    tmp_path: Path,
) -> None:
    from atman.eval.gliner2 import baseline

    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(
        json.dumps(
            {
                "existing/model": {
                    "model": "existing/model",
                    "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    metrics = {
        "overall": {"precision": 0.5, "recall": 0.6, "f1": 0.7},
        "per_entity": {"person": {"precision": 0.5, "recall": 0.6, "f1": 0.7}},
    }

    baseline._save_results(output, "new/model", metrics, n_examples=130, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["existing/model"]["model"] == "existing/model"
    assert saved["new/model"]["model"] == "new/model"
    assert saved["new/model"]["threshold"] == 0.5
    assert saved["new/model"]["n_examples"] == 130
    assert saved["new/model"]["overall"] == metrics["overall"]
    assert saved["new/model"]["per_entity"] == metrics["per_entity"]
    assert saved["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"


def test_main_wires_dataset_predictions_metrics_and_save(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from atman.eval.gliner2 import baseline

    dataset = [
        {
            "text": "Маша позвонила вечером.",
            "entities": [{"label": "person", "start": 0, "end": 4, "text": "Маша"}],
        }
    ]
    metrics = {
        "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
        "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
    }
    output = tmp_path / "baseline.json"
    calls: dict[str, Any] = {}

    class FakeModel:
        pass

    def fake_load_gliner(model_id: str) -> tuple[FakeModel, str]:
        calls["load_model"] = model_id
        return FakeModel(), "gliner2"

    def fake_run_predictions(
        model: FakeModel,
        model_type: str,
        received_dataset: list[dict[str, object]],
        threshold: float,
    ) -> list[list[dict[str, object]]]:
        calls["model_type"] = model_type
        calls["dataset_identity"] = received_dataset is dataset
        calls["threshold"] = threshold
        return [[{"label": "person", "start": 0, "end": 4}]]

    def fake_compute_metrics(
        gold: list[list[dict[str, Any]]],
        pred: list[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        calls["gold"] = gold
        calls["pred"] = pred
        return metrics

    def fake_print_results(model_id: str, received_metrics: dict[str, Any]) -> None:
        calls["printed"] = (model_id, received_metrics)

    def fake_save_results(
        output_path: Path,
        model_id: str,
        received_metrics: dict[str, Any],
        n_examples: int,
        threshold: float,
    ) -> None:
        calls["saved"] = (output_path, model_id, received_metrics, n_examples, threshold)

    monkeypatch.setattr(baseline, "load_dataset", lambda: dataset)
    monkeypatch.setattr(baseline, "_load_gliner", fake_load_gliner)
    monkeypatch.setattr(baseline, "_run_predictions", fake_run_predictions)
    monkeypatch.setattr(baseline, "_compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(baseline, "_print_results", fake_print_results)
    monkeypatch.setattr(baseline, "_save_results", fake_save_results)

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake/model", "--threshold", "0.25", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert calls["load_model"] == "fake/model"
    assert calls["model_type"] == "gliner2"
    assert calls["dataset_identity"] is True
    assert calls["threshold"] == 0.25
    assert calls["gold"] == [[{"label": "person", "start": 0, "end": 4}]]
    assert calls["pred"] == [[{"label": "person", "start": 0, "end": 4}]]
    assert calls["printed"] == ("fake/model", metrics)
    assert calls["saved"] == (output, "fake/model", metrics, 1, 0.25)
