from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from click.testing import CliRunner

from atman.eval.gliner2 import baseline as gliner2_baseline
from atman.eval.gliner2.baseline import _conclusion, _run_predictions, _save_results
from atman.eval.gliner2.dataset import _RAW, LABELS, load_dataset


def test_gliner2_dataset_spans_match_text_and_cover_all_labels() -> None:
    examples = load_dataset()
    seen_labels: set[str] = set()

    assert len(examples) == 130

    for example in examples:
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)

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
            assert text[start:end] == entity_text
            seen_labels.add(label)

    assert seen_labels == set(LABELS)


def test_gliner2_raw_entity_texts_are_unambiguous() -> None:
    for text, raw_entities in _RAW:
        for entity_text, _label in raw_entities:
            assert text.count(entity_text) == 1


def test_gliner2_conclusion_threshold_boundaries() -> None:
    assert _conclusion(0.7001).startswith("F1 > 0.7")
    assert _conclusion(0.7).startswith("F1 0.4")
    assert _conclusion(0.4).startswith("F1 0.4")
    assert _conclusion(0.3999).startswith("F1 < 0.4")


class _FakeGliner2Model:
    def extract_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
        include_spans: bool,
    ) -> dict[str, Any]:
        assert text == "Маша ведёт Atman"
        assert labels == LABELS
        assert threshold == 0.3
        assert include_spans is True
        return {
            "entities": {
                "person": [{"start": 0, "end": 4, "text": "Маша"}],
                "project": [{"start": 11, "end": 16, "text": "Atman"}],
            }
        }


class _FakeGlinerModel:
    def predict_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
    ) -> list[dict[str, Any]]:
        assert text == "Маша ведёт Atman"
        assert labels == LABELS
        assert threshold == 0.3
        return [
            {"label": "person", "start": 0, "end": 4, "score": 0.9},
            {"label": "project", "start": 11, "end": 16, "score": 0.8},
        ]


def test_gliner2_run_predictions_normalizes_supported_model_apis() -> None:
    dataset: list[dict[str, Any]] = [{"text": "Маша ведёт Atman", "entities": []}]
    expected = [
        [{"label": "person", "start": 0, "end": 4}, {"label": "project", "start": 11, "end": 16}]
    ]

    assert _run_predictions(_FakeGliner2Model(), "gliner2", dataset, 0.3) == expected
    assert _run_predictions(_FakeGlinerModel(), "gliner", dataset, 0.3) == expected


class _FakeMetric:
    def __init__(self, precision: float, recall: float, f1: float) -> None:
        self.precision = precision
        self.recall = recall
        self.f1 = f1


class _FakeEvaluator:
    def __init__(
        self,
        gold: list[list[dict[str, Any]]],
        pred: list[list[dict[str, Any]]],
        *,
        tags: list[str],
    ) -> None:
        assert gold == [[{"label": "person", "start": 0, "end": 4}]]
        assert pred == [[{"label": "person", "start": 0, "end": 4}]]
        assert tags == LABELS

    def evaluate(self) -> dict[str, Any]:
        return {
            "overall": {"strict": _FakeMetric(0.81234, 0.71234, 0.61234)},
            "entities": {
                "person": {"strict": _FakeMetric(1.0, 0.5, 0.66666)},
            },
        }


def test_gliner2_compute_metrics_rounds_scores_and_fills_missing_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_nervaluate = ModuleType("nervaluate")
    fake_nervaluate.Evaluator = _FakeEvaluator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = gliner2_baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.8123, "recall": 0.7123, "f1": 0.6123}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_gliner2_save_results_merges_without_dropping_existing_models(tmp_path: Path) -> None:
    output = tmp_path / "results" / "gliner2_baseline_ru.json"
    output.parent.mkdir()
    output.write_text(
        json.dumps(
            {
                "existing/model": {
                    "model": "existing/model",
                    "overall": {"f1": 0.9},
                }
            }
        ),
        encoding="utf-8",
    )
    metrics: dict[str, Any] = {
        "overall": {"precision": 0.5, "recall": 0.6, "f1": 0.55},
        "per_entity": {"person": {"precision": 1.0, "recall": 0.5, "f1": 0.667}},
    }

    _save_results(output, "new/model", metrics, n_examples=130, threshold=0.3)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"existing/model", "new/model"}
    assert saved["existing/model"]["overall"]["f1"] == 0.9
    assert saved["new/model"]["threshold"] == 0.3
    assert saved["new/model"]["n_examples"] == 130
    assert saved["new/model"]["conclusion"].startswith("F1 0.4")


def test_gliner2_cli_runs_offline_with_patched_model_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "gliner2_baseline_ru.json"
    monkeypatch.setattr(
        gliner2_baseline,
        "load_dataset",
        lambda: [
            {
                "text": "Маша ведёт Atman",
                "entities": [{"label": "person", "start": 0, "end": 4, "text": "Маша"}],
            }
        ],
    )
    monkeypatch.setattr(
        gliner2_baseline,
        "_load_gliner",
        lambda _model_id: (_FakeGlinerModel(), "gliner"),
    )
    monkeypatch.setattr(
        gliner2_baseline,
        "_compute_metrics",
        lambda _gold, _pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
        },
    )

    result = CliRunner().invoke(
        gliner2_baseline.main,
        ["--model", "fake/model", "--threshold", "0.3", "--output", str(output)],
    )

    assert result.exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake/model"]["overall"]["f1"] == 1.0
    assert saved["fake/model"]["conclusion"].startswith("F1 > 0.7")
