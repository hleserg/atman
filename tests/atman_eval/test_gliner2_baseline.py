from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def test_gold_dataset_has_valid_unique_spans_and_all_labels() -> None:
    from atman.eval.gliner2.dataset import _RAW, LABELS, load_dataset

    dataset = load_dataset()
    label_counts: Counter[str] = Counter()

    assert len(dataset) == 130
    assert len(_RAW) == len(dataset)

    for (raw_text, raw_entities), example in zip(_RAW, dataset, strict=True):
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)
        assert text == raw_text
        assert len(entities) == len(raw_entities)

        for entity_text, label in raw_entities:
            assert text.count(entity_text) == 1
            label_counts[label] += 1

        for entity in entities:
            assert isinstance(entity, dict)
            label = entity["label"]
            start = entity["start"]
            end = entity["end"]
            entity_text = entity["text"]
            assert isinstance(label, str)
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(entity_text, str)
            assert label in LABELS
            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text

    assert set(label_counts) == set(LABELS)
    assert all(label_counts[label] >= 10 for label in LABELS)


def test_build_span_rejects_missing_entity_text() -> None:
    from atman.eval.gliner2.dataset import _build_span

    with pytest.raises(ValueError, match="Entity text 'Алексей' not found"):
        _build_span("Маша позвонила вчера.", "Алексей", "person")


def test_run_predictions_normalizes_both_model_formats() -> None:
    from atman.eval.gliner2.baseline import _run_predictions

    class FakeGLiNER2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, object]:
            assert text == "Маша дома."
            assert "person" in labels
            assert threshold == pytest.approx(0.5)
            assert include_spans is True
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4, "text": "Маша"}],
                }
            }

    class FakeGLiNER:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, object]]:
            assert text == "Маша дома."
            assert "person" in labels
            assert threshold == pytest.approx(0.5)
            return [{"label": "person", "start": 0, "end": 4, "text": "Маша"}]

    dataset: list[dict[str, Any]] = [{"text": "Маша дома.", "entities": []}]
    expected = [[{"label": "person", "start": 0, "end": 4}]]

    assert _run_predictions(FakeGLiNER2(), "gliner2", dataset, 0.5) == expected
    assert _run_predictions(FakeGLiNER(), "gliner", dataset, 0.5) == expected


def test_compute_metrics_normalizes_nervaluate_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2.baseline import _compute_metrics
    from atman.eval.gliner2.dataset import LABELS

    class Metric:
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
            assert gold == pred
            assert tags == LABELS

        def evaluate(self) -> dict[str, object]:
            return {
                "overall": {"strict": Metric(0.55555, 0.44444, 0.49382)},
                "entities": {
                    "person": {"strict": Metric(1.0, 0.5, 0.66666)},
                },
            }

    nervaluate = ModuleType("nervaluate")
    nervaluate.Evaluator = FakeEvaluator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nervaluate", nervaluate)
    entities = [[{"label": "person", "start": 0, "end": 4}]]

    metrics = _compute_metrics(entities, entities)

    assert metrics["overall"] == {"precision": 0.5555, "recall": 0.4444, "f1": 0.4938}
    assert metrics["per_entity"]["person"] == {
        "precision": 1.0,
        "recall": 0.5,
        "f1": 0.6667,
    }
    assert metrics["per_entity"]["organization"] == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


def test_save_results_accumulates_model_runs(tmp_path: Path) -> None:
    from atman.eval.gliner2.baseline import _save_results

    output = tmp_path / "nested" / "results.json"
    first_metrics: dict[str, Any] = {
        "overall": {"precision": 0.5, "recall": 0.6, "f1": 0.55},
        "per_entity": {"person": {"precision": 0.5, "recall": 0.6, "f1": 0.55}},
    }
    second_metrics: dict[str, Any] = {
        "overall": {"precision": 0.8, "recall": 0.7, "f1": 0.75},
        "per_entity": {"person": {"precision": 0.8, "recall": 0.7, "f1": 0.75}},
    }

    _save_results(output, "first/model", first_metrics, n_examples=130, threshold=0.5)
    _save_results(output, "second/model", second_metrics, n_examples=130, threshold=0.6)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"first/model", "second/model"}
    assert saved["first/model"]["overall"] == first_metrics["overall"]
    assert saved["first/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
    assert saved["second/model"]["threshold"] == pytest.approx(0.6)
    assert saved["second/model"]["n_examples"] == 130
    assert saved["second/model"]["conclusion"] == "F1 > 0.7: fine-tune опционален"
    assert saved["second/model"]["timestamp"]


def test_print_results_handles_every_verdict_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2 import baseline

    class FakeConsole:
        def __init__(self) -> None:
            self.items: list[object] = []

        def print(self, item: object) -> None:
            self.items.append(item)

    fake_console = FakeConsole()
    monkeypatch.setattr(baseline, "console", fake_console)
    monkeypatch.setattr(baseline, "print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(baseline, "print_info", lambda *_args, **_kwargs: None)

    for f1 in (0.75, 0.55, 0.25):
        metrics = {
            "overall": {"precision": f1, "recall": f1, "f1": f1},
            "per_entity": {
                "person": {"precision": f1, "recall": f1, "f1": f1},
            },
        }
        baseline._print_results("test/model", metrics)

    verdicts = [item for item in fake_console.items if isinstance(item, str)]
    tables = [item for item in fake_console.items if not isinstance(item, str)]
    assert verdicts == [
        "[bold green]F1 > 0.7: fine-tune опционален[/bold green]",
        "[bold yellow]F1 0.4–0.7: fine-tune нужен[/bold yellow]",
        "[bold red]F1 < 0.4: рассмотреть смену базовой модели[/bold red]",
    ]
    assert len(tables) == 3


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        pytest.param(0.7001, "F1 > 0.7: fine-tune опционален", id="above-high-threshold"),
        pytest.param(0.7, "F1 0.4–0.7: fine-tune нужен", id="at-high-threshold"),
        pytest.param(0.4, "F1 0.4–0.7: fine-tune нужен", id="at-low-threshold"),
        pytest.param(
            0.3999,
            "F1 < 0.4: рассмотреть смену базовой модели",
            id="below-low-threshold",
        ),
    ],
)
def test_conclusion_respects_decision_boundaries(f1: float, expected: str) -> None:
    from atman.eval.gliner2.baseline import _conclusion

    assert _conclusion(f1) == expected
