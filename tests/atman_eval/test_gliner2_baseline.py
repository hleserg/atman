from __future__ import annotations

from collections import Counter
from typing import Any

import pytest


def test_gold_dataset_has_valid_unique_spans_and_all_labels() -> None:
    from atman.eval.gliner2.dataset import LABELS, _RAW, load_dataset

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
            assert threshold == 0.5
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
            assert threshold == 0.5
            return [{"label": "person", "start": 0, "end": 4, "text": "Маша"}]

    dataset: list[dict[str, Any]] = [{"text": "Маша дома.", "entities": []}]
    expected = [[{"label": "person", "start": 0, "end": 4}]]

    assert _run_predictions(FakeGLiNER2(), "gliner2", dataset, 0.5) == expected
    assert _run_predictions(FakeGLiNER(), "gliner", dataset, 0.5) == expected


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
