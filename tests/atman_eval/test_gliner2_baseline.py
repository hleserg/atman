from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest


def test_gliner2_dataset_has_expected_schema() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    dataset = load_dataset()

    assert len(dataset) == 130
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

    first = dataset[0]
    assert first["text"] == "Маша позвонила мне вчера вечером."
    entities = cast(list[dict[str, object]], first["entities"])
    assert entities[0] == {"label": "person", "start": 0, "end": 4, "text": "Маша"}


def test_build_span_rejects_missing_entity_text() -> None:
    from atman.eval.gliner2.dataset import _build_span

    with pytest.raises(ValueError, match="not found"):
        _build_span("Маша позвонила.", "Алексей", "person")


def test_run_predictions_supports_gliner2_response_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    calls: list[dict[str, object]] = []

    class FakeGliner2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "text": text,
                    "labels": labels,
                    "threshold": threshold,
                    "include_spans": include_spans,
                }
            )
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4}],
                    "project": [{"start": 20, "end": 25}],
                }
            }

    predictions = baseline._run_predictions(
        FakeGliner2(),
        "gliner2",
        [{"text": "Маша работает над Atman."}],
        threshold=0.5,
    )

    assert calls == [
        {
            "text": "Маша работает над Atman.",
            "labels": LABELS,
            "threshold": 0.5,
            "include_spans": True,
        }
    ]
    assert predictions == [
        [
            {"label": "person", "start": 0, "end": 4},
            {"label": "project", "start": 20, "end": 25},
        ]
    ]


def test_run_predictions_supports_standard_gliner_response_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    calls: list[dict[str, object]] = []

    class FakeGliner:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, Any]]:
            calls.append({"text": text, "labels": labels, "threshold": threshold})
            return [{"label": "person", "start": 0, "end": 4}]

    predictions = baseline._run_predictions(
        FakeGliner(),
        "gliner",
        [{"text": "Маша работает над Atman."}],
        threshold=0.4,
    )

    assert calls == [
        {
            "text": "Маша работает над Atman.",
            "labels": LABELS,
            "threshold": 0.4,
        }
    ]
    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_compute_metrics_uses_strict_overall_and_per_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

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
            assert tags == LABELS

        def evaluate(self) -> dict[str, Any]:
            strict = SimpleNamespace(precision=0.44444, recall=0.55555, f1=0.66666)
            person = SimpleNamespace(precision=1.0, recall=0.5, f1=0.66666)
            return {
                "overall": {"strict": strict},
                "entities": {"person": {"strict": person}},
            }

    fake_module = types.ModuleType("nervaluate")
    fake_module.__dict__["Evaluator"] = FakeEvaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_module)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.4444, "recall": 0.5555, "f1": 0.6667}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        (0.71, "F1 > 0.7: fine-tune опционален"),
        (0.7, "F1 0.4–0.7: fine-tune нужен"),
        (0.39, "F1 < 0.4: рассмотреть смену базовой модели"),
    ],
)
def test_conclusion_thresholds(f1: float, expected: str) -> None:
    from atman.eval.gliner2 import baseline

    assert baseline._conclusion(f1) == expected


def test_save_results_merges_model_entries(tmp_path: Path) -> None:
    from atman.eval.gliner2 import baseline

    output = tmp_path / "gliner2_baseline_ru.json"
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

    baseline._save_results(
        output,
        "new/model",
        {
            "overall": {"precision": 0.4, "recall": 0.5, "f1": 0.6},
            "per_entity": {"person": {"precision": 0.4, "recall": 0.5, "f1": 0.6}},
        },
        n_examples=130,
        threshold=0.5,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"existing/model", "new/model"}
    assert saved["new/model"]["n_examples"] == 130
    assert saved["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
