from __future__ import annotations

import builtins
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


def test_dataset_spans_resolve_to_known_labels_and_exact_text() -> None:
    from atman.eval.gliner2.dataset import LABELS, load_dataset

    examples = load_dataset()
    seen_labels: set[str] = set()

    assert examples
    for example in examples:
        text = example["text"]
        assert isinstance(text, str)
        entities = example["entities"]
        assert isinstance(entities, list)

        for entity in entities:
            assert isinstance(entity, dict)
            label = entity["label"]
            start = entity["start"]
            end = entity["end"]
            entity_text = entity["text"]

            assert label in LABELS
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(entity_text, str)
            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text
            seen_labels.add(label)

    assert seen_labels == set(LABELS)


def test_run_predictions_normalizes_gliner2_extractor_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGliner2Model:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, Any]:
            assert text == "Маша работает в Atman."
            assert labels == LABELS
            assert threshold == 0.42
            assert include_spans is True
            return {
                "entities": {
                    "person": [{"start": 0, "end": 4, "text": "Маша"}],
                    "project": [{"start": 16, "end": 21, "text": "Atman"}],
                }
            }

    predictions = baseline._run_predictions(
        FakeGliner2Model(),
        "gliner2",
        [{"text": "Маша работает в Atman.", "entities": []}],
        threshold=0.42,
    )

    assert predictions == [
        [
            {"label": "person", "start": 0, "end": 4},
            {"label": "project", "start": 16, "end": 21},
        ]
    ]


def test_run_predictions_normalizes_standard_gliner_shape() -> None:
    from atman.eval.gliner2 import baseline
    from atman.eval.gliner2.dataset import LABELS

    class FakeGlinerModel:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, Any]]:
            assert text == "Использую Postgres."
            assert labels == LABELS
            assert threshold == 0.7
            return [{"label": "product", "start": 11, "end": 19, "score": 0.91, "text": "Postgres"}]

    predictions = baseline._run_predictions(
        FakeGlinerModel(),
        "gliner",
        [{"text": "Использую Postgres.", "entities": []}],
        threshold=0.7,
    )

    assert predictions == [[{"label": "product", "start": 11, "end": 19}]]


def test_compute_metrics_rounds_overall_and_defaults_missing_labels(
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
            return {
                "overall": {
                    "strict": SimpleNamespace(
                        precision=0.98765,
                        recall=0.87654,
                        f1=0.76543,
                    )
                },
                "entities": {
                    "person": {
                        "strict": SimpleNamespace(
                            precision=1.0,
                            recall=0.5,
                            f1=0.66666,
                        )
                    }
                },
            }

    fake_nervaluate = ModuleType("nervaluate")
    fake_nervaluate.__dict__["Evaluator"] = FakeEvaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == {"precision": 0.9877, "recall": 0.8765, "f1": 0.7654}
    assert metrics["per_entity"]["person"] == {
        "precision": 1.0,
        "recall": 0.5,
        "f1": 0.6667,
    }
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_load_gliner_falls_back_to_standard_gliner_when_gliner2_loader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2 import baseline

    fallback_model = object()

    class FakeGliner2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> object:
            assert model_id == "fallback/model"
            raise RuntimeError("unsupported config")

    class FakeGliner:
        @classmethod
        def from_pretrained(cls, model_id: str) -> object:
            assert model_id == "fallback/model"
            return fallback_model

    fake_gliner2 = ModuleType("gliner2")
    fake_gliner2.__dict__["GLiNER2"] = FakeGliner2
    fake_gliner = ModuleType("gliner")
    fake_gliner.__dict__["GLiNER"] = FakeGliner
    monkeypatch.setitem(sys.modules, "gliner2", fake_gliner2)
    monkeypatch.setitem(sys.modules, "gliner", fake_gliner)

    model, model_type = baseline._load_gliner("fallback/model")

    assert model is fallback_model
    assert model_type == "gliner"


def test_load_gliner_exits_when_no_gliner_package_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.eval.gliner2 import baseline

    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        if name in {"gliner2", "gliner"}:
            raise ImportError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "gliner2", raising=False)
    monkeypatch.delitem(sys.modules, "gliner", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(SystemExit) as exc_info:
        baseline._load_gliner("missing/model")

    assert exc_info.value.code == 1


@pytest.mark.parametrize(
    ("f1", "expected"),
    [
        (0.71, "F1 > 0.7: fine-tune опционален"),
        (0.7, "F1 0.4–0.7: fine-tune нужен"),
        (0.4, "F1 0.4–0.7: fine-tune нужен"),
        (0.39, "F1 < 0.4: рассмотреть смену базовой модели"),
    ],
)
def test_conclusion_uses_documented_thresholds(f1: float, expected: str) -> None:
    from atman.eval.gliner2 import baseline

    assert baseline._conclusion(f1) == expected


def test_save_results_merges_model_entries_without_overwriting_existing(
    tmp_path: Path,
) -> None:
    from atman.eval.gliner2 import baseline

    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(
        json.dumps(
            {
                "previous/model": {
                    "model": "previous/model",
                    "overall": {"f1": 0.1},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    baseline._save_results(
        output,
        "new/model",
        {
            "overall": {"precision": 0.9, "recall": 0.8, "f1": 0.75},
            "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
        },
        n_examples=3,
        threshold=0.42,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["previous/model"]["overall"] == {"f1": 0.1}
    assert payload["new/model"]["model"] == "new/model"
    assert payload["new/model"]["threshold"] == 0.42
    assert payload["new/model"]["n_examples"] == 3
    assert payload["new/model"]["overall"] == {"precision": 0.9, "recall": 0.8, "f1": 0.75}
    assert payload["new/model"]["conclusion"] == "F1 > 0.7: fine-tune опционален"
    assert isinstance(payload["new/model"]["timestamp"], str)
