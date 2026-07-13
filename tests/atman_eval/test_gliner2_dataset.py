from __future__ import annotations

from collections import Counter

import pytest


def test_gliner2_labels_are_stable_and_unique() -> None:
    from atman.eval.gliner2.dataset import LABELS

    assert LABELS == [
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
    ]
    assert len(LABELS) == len(set(LABELS)) == 13


def test_gliner2_dataset_has_expected_size_and_label_coverage() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    examples = load_dataset()

    assert len(examples) == 130

    label_counts: Counter[str] = Counter()
    for example in examples:
        entities = example["entities"]
        assert isinstance(entities, list)
        for entity in entities:
            assert isinstance(entity, dict)
            label = entity["label"]
            assert isinstance(label, str)
            label_counts[label] += 1

    assert set(label_counts) == set(LABELS)
    assert all(label_counts[label] >= 10 for label in LABELS)


def test_gliner2_dataset_spans_round_trip_to_entity_text() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    for example in load_dataset():
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)

        for entity in entities:
            assert isinstance(entity, dict)
            start = entity["start"]
            end = entity["end"]
            label = entity["label"]
            entity_text = entity["text"]

            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(label, str)
            assert isinstance(entity_text, str)
            assert label in LABELS
            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text


def test_build_span_rejects_missing_entity_text() -> None:
    from atman.eval.gliner2.dataset import _build_span

    with pytest.raises(ValueError, match="not found"):
        _build_span("Маша позвонила вечером.", "Алексей", "person")
