"""Regression tests for GLiNER2 Russian NER baseline helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest


def test_dataset_spans_resolve_to_labeled_text_and_cover_all_labels() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    dataset = load_dataset()
    labels_seen: set[str] = set()

    assert len(dataset) >= 130
    for example in dataset:
        text = cast(str, example["text"])
        entities = cast(list[dict[str, object]], example["entities"])
        assert text
        for entity in entities:
            label = cast(str, entity["label"])
            start = cast(int, entity["start"])
            end = cast(int, entity["end"])
            entity_text = cast(str, entity["text"])

            assert label in LABELS
            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text
            labels_seen.add(label)

    assert labels_seen == set(LABELS)


def test_run_predictions_normalizes_gliner2_entities() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGliner2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, Any]:
            assert text == "Маша ведёт проект Atman."
            assert labels == LABELS
            assert threshold == 0.42
            assert include_spans is True
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4}],
                    "project": [{"start": 19, "end": 24}],
                }
            }

    predictions = baseline._run_predictions(
        FakeGliner2(),
        "gliner2",
        [{"text": "Маша ведёт проект Atman."}],
        threshold=0.42,
    )

    assert predictions == [
        [{"label": "person", "start": 0, "end": 4}, {"label": "project", "start": 19, "end": 24}]
    ]


def test_run_predictions_normalizes_standard_gliner_entities() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGliner:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, Any]]:
            assert text == "Atman помогает Сергею."
            assert labels == LABELS
            assert threshold == 0.7
            return [
                {"label": "project", "start": 0, "end": 5, "score": 0.91},
                {"label": "person", "start": 16, "end": 22, "score": 0.82},
            ]

    predictions = baseline._run_predictions(
        FakeGliner(),
        "gliner",
        [{"text": "Atman помогает Сергею."}],
        threshold=0.7,
    )

    assert predictions == [
        [{"label": "project", "start": 0, "end": 5}, {"label": "person", "start": 16, "end": 22}]
    ]


def test_save_results_merges_model_entries_and_records_threshold_verdict(tmp_path: Path) -> None:
    from atman.eval.gliner2 import baseline

    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(
        json.dumps(
            {
                "old/model": {
                    "model": "old/model",
                    "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
                }
            }
        ),
        encoding="utf-8",
    )
    metrics = {
        "overall": {"precision": 0.5, "recall": 0.25, "f1": 0.3333},
        "per_entity": {"project": {"precision": 0.5, "recall": 0.25, "f1": 0.3333}},
    }

    baseline._save_results(output, "new/model", metrics, n_examples=130, threshold=0.55)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"old/model", "new/model"}
    assert saved["old/model"]["model"] == "old/model"
    new_result = saved["new/model"]
    assert new_result["model"] == "new/model"
    assert new_result["threshold"] == 0.55
    assert new_result["n_examples"] == 130
    assert new_result["overall"] == metrics["overall"]
    assert new_result["per_entity"] == metrics["per_entity"]
    assert new_result["conclusion"] == "F1 < 0.4: рассмотреть смену базовой модели"
    assert isinstance(new_result["timestamp"], str)


def test_main_wires_gold_spans_predictions_metrics_and_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    from atman.eval.gliner2 import baseline

    fake_model = object()
    dataset = [
        {
            "text": "Atman помогает Сергею.",
            "entities": [
                {"label": "project", "start": 0, "end": 5, "text": "Atman"},
                {"label": "person", "start": 16, "end": 22, "text": "Сергею"},
            ],
        }
    ]
    predictions = [[{"label": "project", "start": 0, "end": 5}]]
    metrics = {
        "overall": {"precision": 1.0, "recall": 0.5, "f1": 0.6667},
        "per_entity": {"project": {"precision": 1.0, "recall": 0.5, "f1": 0.6667}},
    }
    calls: dict[str, Any] = {}

    def fake_load_dataset() -> list[dict[str, Any]]:
        calls["load_dataset"] = True
        return dataset

    def fake_load_gliner(model_id: str) -> tuple[object, str]:
        calls["model_id"] = model_id
        return fake_model, "gliner"

    def fake_run_predictions(
        model: object,
        model_type: str,
        dataset_arg: list[dict[str, Any]],
        threshold: float,
    ) -> list[list[dict[str, Any]]]:
        calls["prediction_args"] = (model, model_type, dataset_arg, threshold)
        return predictions

    def fake_compute_metrics(
        gold: list[list[dict[str, Any]]],
        pred: list[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        calls["gold"] = gold
        calls["pred"] = pred
        return metrics

    def fake_print_results(model_id: str, metrics_arg: dict[str, Any]) -> None:
        calls["printed"] = (model_id, metrics_arg)

    def fake_save_results(
        output: Path,
        model_id: str,
        metrics_arg: dict[str, Any],
        n_examples: int,
        threshold: float,
    ) -> None:
        calls["saved"] = (output, model_id, metrics_arg, n_examples, threshold)

    monkeypatch.setattr(baseline, "load_dataset", fake_load_dataset)
    monkeypatch.setattr(baseline, "_load_gliner", fake_load_gliner)
    monkeypatch.setattr(baseline, "_run_predictions", fake_run_predictions)
    monkeypatch.setattr(baseline, "_compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(baseline, "_print_results", fake_print_results)
    monkeypatch.setattr(baseline, "_save_results", fake_save_results)

    output = tmp_path / "results.json"
    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake/model", "--threshold", "0.6", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert calls["load_dataset"] is True
    assert calls["model_id"] == "fake/model"
    assert calls["prediction_args"] == (fake_model, "gliner", dataset, 0.6)
    assert calls["gold"] == [
        [{"label": "project", "start": 0, "end": 5}, {"label": "person", "start": 16, "end": 22}]
    ]
    assert calls["pred"] == predictions
    assert calls["printed"] == ("fake/model", metrics)
    assert calls["saved"] == (output, "fake/model", metrics, 1, 0.6)


def test_print_results_renders_threshold_verdict_and_entity_rows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from atman.eval.gliner2 import baseline

    metrics = {
        "overall": {"precision": 0.8, "recall": 0.7, "f1": 0.71},
        "per_entity": {
            "animal": {"precision": 0.3, "recall": 0.2, "f1": 0.24},
            "person": {"precision": 0.8, "recall": 0.7, "f1": 0.71},
            "project": {"precision": 0.5, "recall": 0.4, "f1": 0.44},
        },
    }

    baseline._print_results("fake/model", metrics)

    output = capsys.readouterr().out
    assert "fake/model" in output
    assert "fine-tune опционален" in output
    assert "animal" in output
    assert "person" in output
    assert "project" in output
