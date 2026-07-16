"""Offline regression tests for the GLiNER2 Russian baseline evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
from click.testing import CliRunner


@pytest.fixture
def baseline() -> Any:
    from atman.eval.gliner2 import baseline as baseline_module

    return baseline_module


def test_dataset_annotations_have_valid_unique_spans() -> None:
    from atman.eval.gliner2 import dataset

    examples = dataset.load_dataset()

    assert len(examples) == 130
    assert {entity["label"] for example in examples for entity in example["entities"]} == set(
        dataset.LABELS
    )
    for example in examples:
        text = example["text"]
        entity_texts: list[str] = []
        for entity in example["entities"]:
            assert text[entity["start"] : entity["end"]] == entity["text"]
            entity_texts.append(entity["text"])
        assert len(entity_texts) == len(set(entity_texts))

    with pytest.raises(ValueError, match="not found"):
        dataset._build_span("Анна пришла", "Борис", "person")


def test_load_gliner_prefers_gliner2(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_model = object()
    gliner2_module = ModuleType("gliner2")

    class FakeGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> object:
            assert model_id == "model-id"
            return expected_model

    gliner2_module.GLiNER2 = FakeGLiNER2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gliner2", gliner2_module)

    model, model_type = baseline._load_gliner("model-id")

    assert model is expected_model
    assert model_type == "gliner2"


def test_load_gliner_falls_back_to_standard_gliner(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_model = object()
    gliner2_module = ModuleType("gliner2")
    gliner_module = ModuleType("gliner")

    class FailingGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> object:
            raise RuntimeError(f"unsupported format: {model_id}")

    class FakeGLiNER:
        @classmethod
        def from_pretrained(cls, model_id: str) -> object:
            assert model_id == "model-id"
            return expected_model

    gliner2_module.GLiNER2 = FailingGLiNER2  # type: ignore[attr-defined]
    gliner_module.GLiNER = FakeGLiNER  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gliner2", gliner2_module)
    monkeypatch.setitem(sys.modules, "gliner", gliner_module)

    model, model_type = baseline._load_gliner("model-id")

    assert model is expected_model
    assert model_type == "gliner"


def test_load_gliner_exits_when_both_packages_are_unavailable(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "gliner2", cast(Any, None))
    monkeypatch.setitem(sys.modules, "gliner", cast(Any, None))

    with pytest.raises(SystemExit) as exc_info:
        baseline._load_gliner("model-id")

    assert exc_info.value.code == 1


def test_run_predictions_normalizes_both_model_formats(baseline: Any) -> None:
    dataset = [{"text": "Анна пришла", "entities": []}]

    class FakeGLiNER2Model:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, object]:
            assert (text, labels, threshold, include_spans) == (
                "Анна пришла",
                baseline.LABELS,
                0.6,
                True,
            )
            return {"entities": {"person": [{"start": 0, "end": 4}]}}

    class FakeGLiNERModel:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, object]]:
            assert (text, labels, threshold) == ("Анна пришла", baseline.LABELS, 0.4)
            return [{"label": "person", "start": 0, "end": 4}]

    gliner2_predictions = baseline._run_predictions(FakeGLiNER2Model(), "gliner2", dataset, 0.6)
    gliner_predictions = baseline._run_predictions(FakeGLiNERModel(), "gliner", dataset, 0.4)

    expected = [[{"label": "person", "start": 0, "end": 4}]]
    assert gliner2_predictions == expected
    assert gliner_predictions == expected


def test_compute_metrics_normalizes_overall_and_missing_entity_scores(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    score = SimpleNamespace(precision=0.55555, recall=0.66666, f1=0.60606)
    evaluator_calls: list[tuple[object, object, object]] = []
    nervaluate_module = ModuleType("nervaluate")

    class FakeEvaluator:
        def __init__(self, gold: object, pred: object, *, tags: object) -> None:
            evaluator_calls.append((gold, pred, tags))

        def evaluate(self) -> dict[str, object]:
            return {
                "overall": {"strict": score},
                "entities": {"person": {"strict": score}},
            }

    nervaluate_module.Evaluator = FakeEvaluator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nervaluate", nervaluate_module)
    gold = [[{"label": "person", "start": 0, "end": 4}]]
    pred = [[{"label": "person", "start": 0, "end": 4}]]

    metrics = baseline._compute_metrics(gold, pred)

    assert evaluator_calls == [(gold, pred, baseline.LABELS)]
    assert metrics["overall"] == {"precision": 0.5555, "recall": 0.6667, "f1": 0.6061}
    assert metrics["per_entity"]["person"] == metrics["overall"]
    assert metrics["per_entity"]["animal"] == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


def test_compute_metrics_exits_when_nervaluate_is_unavailable(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "nervaluate", cast(Any, None))

    with pytest.raises(SystemExit) as exc_info:
        baseline._compute_metrics([], [])

    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        (0.71, "fine-tune опционален"),
        (0.7, "fine-tune нужен"),
        (0.4, "fine-tune нужен"),
        (0.39, "смену базовой модели"),
    ],
)
def test_conclusion_boundaries(baseline: Any, f1: float, expected: str) -> None:
    assert expected in baseline._conclusion(f1)


def test_print_results_renders_all_score_bands(
    baseline: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    metrics = {
        "overall": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
        "per_entity": {
            "high": {"precision": 0.8, "recall": 0.8, "f1": 0.8},
            "medium": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
            "low": {"precision": 0.2, "recall": 0.2, "f1": 0.2},
        },
    }

    baseline._print_results("model[unsafe]", metrics)

    output = capsys.readouterr().out
    assert "model[unsafe]" in output
    assert "Overall" in output
    assert "high" in output
    assert "medium" in output
    assert "low" in output


def test_save_results_merges_model_runs(baseline: Any, tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    metrics = {
        "overall": {"precision": 0.5, "recall": 0.6, "f1": 0.55},
        "per_entity": {"person": {"precision": 0.5, "recall": 0.6, "f1": 0.55}},
    }

    baseline._save_results(output, "model-a", metrics, 130, 0.5)
    baseline._save_results(output, "model-b", metrics, 130, 0.6)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"model-a", "model-b"}
    assert saved["model-a"]["n_examples"] == 130
    assert saved["model-a"]["threshold"] == 0.5
    assert saved["model-a"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
    assert saved["model-a"]["timestamp"]


def test_cli_orchestrates_baseline_pipeline(
    baseline: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset = [{"text": "Анна", "entities": [{"label": "person", "start": 0, "end": 4}]}]
    predictions = [[{"label": "person", "start": 0, "end": 4}]]
    metrics = {
        "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
        "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
    }
    calls: dict[str, object] = {}

    monkeypatch.setattr(baseline, "load_dataset", lambda: dataset)
    monkeypatch.setattr(baseline, "_load_gliner", lambda model_id: ("model", "gliner2"))
    monkeypatch.setattr(
        baseline,
        "_run_predictions",
        lambda model, model_type, examples, threshold: predictions,
    )
    monkeypatch.setattr(baseline, "_compute_metrics", lambda gold, pred: metrics)
    monkeypatch.setattr(baseline, "_print_results", lambda model_id, result: None)

    def fake_save(
        output: Path,
        model_id: str,
        result: dict[str, object],
        n_examples: int,
        threshold: float,
    ) -> None:
        calls.update(
            output=output,
            model_id=model_id,
            result=result,
            n_examples=n_examples,
            threshold=threshold,
        )

    monkeypatch.setattr(baseline, "_save_results", fake_save)
    output = tmp_path / "baseline.json"

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "model-id", "--threshold", "0.65", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert calls == {
        "output": output,
        "model_id": "model-id",
        "result": metrics,
        "n_examples": 1,
        "threshold": 0.65,
    }
