from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atman.eval.gliner2.baseline import _conclusion, _run_predictions, _save_results
from atman.eval.gliner2.dataset import LABELS, _RAW, load_dataset


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
    expected = [[{"label": "person", "start": 0, "end": 4}, {"label": "project", "start": 11, "end": 16}]]

    assert _run_predictions(_FakeGliner2Model(), "gliner2", dataset, 0.3) == expected
    assert _run_predictions(_FakeGlinerModel(), "gliner", dataset, 0.3) == expected


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
