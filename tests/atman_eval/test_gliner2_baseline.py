"""Regression tests for GLiNER2 Russian NER baseline helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


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
