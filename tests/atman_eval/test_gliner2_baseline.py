from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def test_gliner2_dataset_spans_match_text_and_labels_are_covered() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    examples = load_dataset()
    seen_labels: set[str] = set()

    assert len(examples) == 130
    for example in examples:
        text = cast(str, example["text"])
        entities = cast(list[dict[str, Any]], example["entities"])
        assert text
        assert entities
        for entity in entities:
            start = cast(int, entity["start"])
            end = cast(int, entity["end"])
            label = cast(str, entity["label"])
            entity_text = cast(str, entity["text"])

            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text
            assert text.count(entity_text) == 1
            assert label in LABELS
            seen_labels.add(label)

    assert seen_labels == set(LABELS)


def test_gliner2_conclusion_threshold_boundaries() -> None:
    from atman.eval.gliner2.baseline import _conclusion

    assert _conclusion(0.7001) == "F1 > 0.7: fine-tune опционален"
    assert _conclusion(0.7) == "F1 0.4–0.7: fine-tune нужен"
    assert _conclusion(0.4) == "F1 0.4–0.7: fine-tune нужен"
    assert _conclusion(0.3999) == "F1 < 0.4: рассмотреть смену базовой модели"


def test_gliner2_run_predictions_normalizes_supported_model_outputs() -> None:
    from atman.eval.gliner2.baseline import _run_predictions

    dataset = [{"text": "Маша любит Atman"}]

    class Gliner2Model:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, dict[str, list[dict[str, int]]]]:
            assert text == "Маша любит Atman"
            assert "person" in labels
            assert threshold == 0.5
            assert include_spans is True
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4}],
                    "project": [{"start": 11, "end": 16}],
                }
            }

    class GlinerModel:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, str | int]]:
            assert text == "Маша любит Atman"
            assert "project" in labels
            assert threshold == 0.5
            return [
                {"label": "person", "start": 0, "end": 4},
                {"label": "project", "start": 11, "end": 16},
            ]

    expected = [
        [
            {"label": "person", "start": 0, "end": 4},
            {"label": "project", "start": 11, "end": 16},
        ]
    ]

    assert _run_predictions(Gliner2Model(), "gliner2", dataset, threshold=0.5) == expected
    assert _run_predictions(GlinerModel(), "gliner", dataset, threshold=0.5) == expected


def test_gliner2_save_results_merges_models_without_dropping_existing(
    tmp_path: Path,
) -> None:
    from atman.eval.gliner2.baseline import _save_results

    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(
        json.dumps(
            {
                "existing/model": {
                    "model": "existing/model",
                    "overall": {"f1": 0.5},
                }
            }
        ),
        encoding="utf-8",
    )

    metrics = {
        "overall": {"precision": 0.6, "recall": 0.7, "f1": 0.65},
        "per_entity": {
            "person": {"precision": 1.0, "recall": 0.5, "f1": 0.667},
        },
    }

    _save_results(
        output=output,
        model_id="new/model",
        metrics=metrics,
        n_examples=130,
        threshold=0.5,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"existing/model", "new/model"}
    assert saved["existing/model"]["overall"] == {"f1": 0.5}
    assert saved["new/model"]["threshold"] == 0.5
    assert saved["new/model"]["n_examples"] == 130
    assert saved["new/model"]["overall"] == metrics["overall"]
    assert saved["new/model"]["per_entity"] == metrics["per_entity"]
    assert saved["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
    assert saved["new/model"]["timestamp"]
