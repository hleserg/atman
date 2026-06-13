"""Unit coverage for the GLiNER2 Russian NER eval helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from click.testing import CliRunner

from atman.eval.gliner2 import baseline
from atman.eval.gliner2.dataset import LABELS, load_dataset


def test_load_dataset_resolves_all_gold_spans() -> None:
    dataset = load_dataset()

    assert len(dataset) == 130
    for example in dataset:
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)
        for entity in entities:
            assert text[entity["start"] : entity["end"]] == entity["text"]
            assert entity["label"] in LABELS


def test_load_gliner_uses_gliner2_when_available(monkeypatch) -> None:
    class FakeGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            return f"gliner2:{model_id}"

    fake_module = ModuleType("gliner2")
    fake_module.GLiNER2 = FakeGLiNER2
    monkeypatch.setitem(sys.modules, "gliner2", fake_module)

    model, model_type = baseline._load_gliner("fake/model")

    assert model == "gliner2:fake/model"
    assert model_type == "gliner2"


def test_load_gliner_falls_back_to_standard_gliner(monkeypatch) -> None:
    class FailingGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            raise RuntimeError(f"cannot load {model_id}")

    class FakeGLiNER:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            return f"gliner:{model_id}"

    fake_gliner2 = ModuleType("gliner2")
    fake_gliner2.GLiNER2 = FailingGLiNER2
    fake_gliner = ModuleType("gliner")
    fake_gliner.GLiNER = FakeGLiNER
    monkeypatch.setitem(sys.modules, "gliner2", fake_gliner2)
    monkeypatch.setitem(sys.modules, "gliner", fake_gliner)

    model, model_type = baseline._load_gliner("fallback/model")

    assert model == "gliner:fallback/model"
    assert model_type == "gliner"


def test_run_predictions_supports_gliner2_and_standard_gliner() -> None:
    dataset = [{"text": "Маша пишет"}]

    gliner2_model = SimpleNamespace(
        extract_entities=lambda *args, **kwargs: {
            "entities": {"person": [{"start": 0, "end": 5}], "project": []}
        }
    )
    gliner_model = SimpleNamespace(
        predict_entities=lambda *args, **kwargs: [
            {"label": "person", "start": 0, "end": 5, "score": 0.9}
        ]
    )

    assert baseline._run_predictions(gliner2_model, "gliner2", dataset, 0.5) == [
        [{"label": "person", "start": 0, "end": 5}]
    ]
    assert baseline._run_predictions(gliner_model, "gliner", dataset, 0.5) == [
        [{"label": "person", "start": 0, "end": 5}]
    ]


def test_compute_metrics_maps_overall_and_missing_labels(monkeypatch) -> None:
    class EvalResult:
        precision = 0.12345
        recall = 0.5
        f1 = 0.33335

    class Evaluator:
        def __init__(self, gold: list[Any], pred: list[Any], tags: list[str]) -> None:
            self.gold = gold
            self.pred = pred
            self.tags = tags

        def evaluate(self) -> dict[str, Any]:
            return {
                "overall": {"strict": EvalResult()},
                "entities": {"person": {"strict": EvalResult()}},
            }

    fake_nervaluate = ModuleType("nervaluate")
    fake_nervaluate.Evaluator = Evaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 5}]],
        [[{"label": "person", "start": 0, "end": 5}]],
    )

    assert metrics["overall"] == {"precision": 0.1235, "recall": 0.5, "f1": 0.3333}
    assert metrics["per_entity"]["person"]["f1"] == 0.3333
    assert metrics["per_entity"]["organization"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_model_entry(tmp_path: Path) -> None:
    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(json.dumps({"old/model": {"model": "old/model"}}), encoding="utf-8")
    metrics = {
        "overall": {"precision": 0.1, "recall": 0.2, "f1": 0.5},
        "per_entity": {"person": {"precision": 0.1, "recall": 0.2, "f1": 0.5}},
    }

    baseline._save_results(output, "new/model", metrics, n_examples=130, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"old/model", "new/model"}
    assert saved["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"


def test_baseline_cli_wires_evaluation_flow(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    monkeypatch.setattr(baseline, "load_dataset", lambda: [{"text": "Маша", "entities": []}])
    monkeypatch.setattr(baseline, "_load_gliner", lambda model: (object(), "gliner"))
    monkeypatch.setattr(baseline, "_run_predictions", lambda *args: [[]])
    monkeypatch.setattr(
        baseline,
        "_compute_metrics",
        lambda gold, pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 0.8},
            "per_entity": {},
        },
    )
    monkeypatch.setattr(baseline, "_print_results", lambda model, metrics: None)

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake/model", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["fake/model"]["overall"]["f1"] == 0.8
