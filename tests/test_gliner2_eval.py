"""Unit coverage for the GLiNER2 Russian NER eval helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = REPO_ROOT / "src" / "atman" / "eval" / "gliner2" / "dataset.py"
BASELINE_PATH = REPO_ROOT / "src" / "atman" / "eval" / "gliner2" / "baseline.py"


def _load_module(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gliner_modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    eval_pkg = ModuleType("atman.eval")
    gliner_pkg = ModuleType("atman.eval.gliner2")
    eval_pkg.__dict__["__path__"] = []
    gliner_pkg.__dict__["__path__"] = []
    monkeypatch.setitem(sys.modules, "atman.eval", eval_pkg)
    monkeypatch.setitem(sys.modules, "atman.eval.gliner2", gliner_pkg)

    dataset_module = _load_module("atman.eval.gliner2.dataset", DATASET_PATH, monkeypatch)
    baseline_module = _load_module("atman.eval.gliner2.baseline", BASELINE_PATH, monkeypatch)
    return baseline_module, dataset_module


def test_load_dataset_resolves_all_gold_spans(gliner_modules: tuple[Any, Any]) -> None:
    _, dataset_module = gliner_modules
    dataset = dataset_module.load_dataset()

    assert len(dataset) == 130
    for example in dataset:
        text = example["text"]
        entities = example["entities"]
        assert isinstance(text, str)
        assert isinstance(entities, list)
        for entity in entities:
            assert text[entity["start"] : entity["end"]] == entity["text"]
            assert entity["label"] in dataset_module.LABELS


def test_load_gliner_uses_gliner2_when_available(
    gliner_modules: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_module, _ = gliner_modules

    class FakeGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            return f"gliner2:{model_id}"

    fake_module = ModuleType("gliner2")
    fake_module.__dict__["GLiNER2"] = FakeGLiNER2
    monkeypatch.setitem(sys.modules, "gliner2", fake_module)

    model, model_type = baseline_module._load_gliner("fake/model")

    assert model == "gliner2:fake/model"
    assert model_type == "gliner2"


def test_load_gliner_falls_back_to_standard_gliner(
    gliner_modules: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_module, _ = gliner_modules

    class FailingGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            raise RuntimeError(f"cannot load {model_id}")

    class FakeGLiNER:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            return f"gliner:{model_id}"

    fake_gliner2 = ModuleType("gliner2")
    fake_gliner2.__dict__["GLiNER2"] = FailingGLiNER2
    fake_gliner = ModuleType("gliner")
    fake_gliner.__dict__["GLiNER"] = FakeGLiNER
    monkeypatch.setitem(sys.modules, "gliner2", fake_gliner2)
    monkeypatch.setitem(sys.modules, "gliner", fake_gliner)

    model, model_type = baseline_module._load_gliner("fallback/model")

    assert model == "gliner:fallback/model"
    assert model_type == "gliner"


def test_run_predictions_supports_gliner2_and_standard_gliner(
    gliner_modules: tuple[Any, Any],
) -> None:
    baseline_module, _ = gliner_modules
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

    assert baseline_module._run_predictions(gliner2_model, "gliner2", dataset, 0.5) == [
        [{"label": "person", "start": 0, "end": 5}]
    ]
    assert baseline_module._run_predictions(gliner_model, "gliner", dataset, 0.5) == [
        [{"label": "person", "start": 0, "end": 5}]
    ]


def test_compute_metrics_maps_overall_and_missing_labels(
    gliner_modules: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_module, _ = gliner_modules

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
    fake_nervaluate.__dict__["Evaluator"] = Evaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline_module._compute_metrics(
        [[{"label": "person", "start": 0, "end": 5}]],
        [[{"label": "person", "start": 0, "end": 5}]],
    )

    assert metrics["overall"] == {"precision": 0.1235, "recall": 0.5, "f1": 0.3333}
    assert metrics["per_entity"]["person"]["f1"] == pytest.approx(0.3333)
    assert metrics["per_entity"]["organization"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_model_entry(gliner_modules: tuple[Any, Any], tmp_path: Path) -> None:
    baseline_module, _ = gliner_modules
    output = tmp_path / "gliner2_baseline_ru.json"
    output.write_text(json.dumps({"old/model": {"model": "old/model"}}), encoding="utf-8")
    metrics = {
        "overall": {"precision": 0.1, "recall": 0.2, "f1": 0.5},
        "per_entity": {"person": {"precision": 0.1, "recall": 0.2, "f1": 0.5}},
    }

    baseline_module._save_results(output, "new/model", metrics, n_examples=130, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"old/model", "new/model"}
    assert saved["new/model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"


def test_baseline_cli_wires_evaluation_flow(
    gliner_modules: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baseline_module, _ = gliner_modules
    output = tmp_path / "out.json"
    monkeypatch.setattr(baseline_module, "load_dataset", lambda: [{"text": "Маша", "entities": []}])
    monkeypatch.setattr(baseline_module, "_load_gliner", lambda model: (object(), "gliner"))
    monkeypatch.setattr(baseline_module, "_run_predictions", lambda *args: [[]])
    monkeypatch.setattr(
        baseline_module,
        "_compute_metrics",
        lambda gold, pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 0.8},
            "per_entity": {},
        },
    )
    monkeypatch.setattr(baseline_module, "_print_results", lambda model, metrics: None)

    result = CliRunner().invoke(
        baseline_module.main,
        ["--model", "fake/model", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["fake/model"]["overall"][
        "f1"
    ] == pytest.approx(0.8)
