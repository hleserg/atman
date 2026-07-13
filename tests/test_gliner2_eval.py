"""Unit tests for deterministic GLiNER2 eval helpers."""

from __future__ import annotations

import json
import sys
import types
from importlib import util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "src" / "atman" / "eval" / "gliner2" / "dataset.py"
BASELINE_PATH = ROOT / "src" / "atman" / "eval" / "gliner2" / "baseline.py"


class FakeGliner2Model:
    def extract_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
        include_spans: bool,
    ) -> dict[str, Any]:
        assert text
        assert "person" in labels
        assert threshold == pytest.approx(0.5)
        assert include_spans is True
        return {"entities": {"person": [{"start": 0, "end": 4}]}}


class FakeGlinerModel:
    def predict_entities(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float,
    ) -> list[dict[str, Any]]:
        assert text
        assert "animal" in labels
        assert threshold == pytest.approx(0.25)
        return [{"label": "animal", "start": 5, "end": 10}]


def _load_module(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    spec = util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gliner2_modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    eval_pkg = types.ModuleType("atman.eval")
    gliner_pkg = types.ModuleType("atman.eval.gliner2")
    eval_pkg.__dict__["__path__"] = []
    gliner_pkg.__dict__["__path__"] = []
    monkeypatch.setitem(sys.modules, "atman.eval", eval_pkg)
    monkeypatch.setitem(sys.modules, "atman.eval.gliner2", gliner_pkg)

    dataset = _load_module("atman.eval.gliner2.dataset", DATASET_PATH, monkeypatch)
    baseline = _load_module("atman.eval.gliner2.baseline", BASELINE_PATH, monkeypatch)
    return baseline, dataset


def test_load_dataset_builds_valid_character_spans(gliner2_modules: tuple[Any, Any]) -> None:
    _, dataset = gliner2_modules
    examples = dataset.load_dataset()

    assert len(examples) == 130
    first = examples[0]
    assert first["text"] == "Маша позвонила мне вчера вечером."
    assert first["entities"][0] == {"label": "person", "start": 0, "end": 4, "text": "Маша"}

    for example in examples:
        text = example["text"]
        for entity in example["entities"]:
            assert text[entity["start"] : entity["end"]] == entity["text"]


def test_build_span_raises_when_entity_text_is_missing(gliner2_modules: tuple[Any, Any]) -> None:
    _, dataset = gliner2_modules

    with pytest.raises(ValueError, match="not found"):
        dataset._build_span("Маша пришла.", "Катя", "person")


def test_run_predictions_normalizes_gliner2_output(gliner2_modules: tuple[Any, Any]) -> None:
    baseline, _ = gliner2_modules
    predictions = baseline._run_predictions(
        FakeGliner2Model(),
        "gliner2",
        [{"text": "Маша пришла."}],
        threshold=0.5,
    )

    assert predictions == [[{"label": "person", "start": 0, "end": 4}]]


def test_run_predictions_normalizes_standard_gliner_output(
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _ = gliner2_modules
    predictions = baseline._run_predictions(
        FakeGlinerModel(),
        "gliner",
        [{"text": "Кот Мурзик спит."}],
        threshold=0.25,
    )

    assert predictions == [[{"label": "animal", "start": 5, "end": 10}]]


def test_conclusion_thresholds(gliner2_modules: tuple[Any, Any]) -> None:
    baseline, _ = gliner2_modules
    assert baseline._conclusion(0.71) == "F1 > 0.7: fine-tune опционален"
    assert baseline._conclusion(0.4) == "F1 0.4–0.7: fine-tune нужен"
    assert baseline._conclusion(0.39) == "F1 < 0.4: рассмотреть смену базовой модели"


def test_compute_metrics_uses_nervaluate_strict_results(
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _ = gliner2_modules

    class Metric:
        precision = 0.12345
        recall = 0.67891
        f1 = 0.54321

    class Evaluator:
        def __init__(
            self,
            gold: list[list[dict[str, Any]]],
            pred: list[list[dict[str, Any]]],
            *,
            tags: list[str],
        ) -> None:
            assert gold == [[{"label": "person", "start": 0, "end": 4}]]
            assert pred == [[{"label": "person", "start": 0, "end": 4}]]
            assert "person" in tags

        def evaluate(self) -> dict[str, Any]:
            return {
                "overall": {"strict": Metric()},
                "entities": {"person": {"strict": Metric()}},
            }

    fake_nervaluate = types.ModuleType("nervaluate")
    fake_nervaluate.__dict__["Evaluator"] = Evaluator
    monkeypatch.setitem(sys.modules, "nervaluate", fake_nervaluate)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 4}]],
        [[{"label": "person", "start": 0, "end": 4}]],
    )

    assert metrics["overall"] == pytest.approx(
        {"precision": 0.1235, "recall": 0.6789, "f1": 0.5432}
    )
    assert metrics["per_entity"]["person"] == pytest.approx(
        {
            "precision": 0.1235,
            "recall": 0.6789,
            "f1": 0.5432,
        }
    )
    assert metrics["per_entity"]["animal"] == pytest.approx(
        {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    )


def test_save_results_merges_model_entries(
    tmp_path: Path,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _ = gliner2_modules
    output = tmp_path / "baseline.json"
    existing = {
        "old-model": {
            "model": "old-model",
            "overall": {"f1": 0.1},
        }
    }
    output.write_text(json.dumps(existing), encoding="utf-8")

    baseline._save_results(
        output,
        "new-model",
        {
            "overall": {"precision": 0.5, "recall": 0.6, "f1": 0.55},
            "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
        },
        n_examples=2,
        threshold=0.5,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == {"old-model", "new-model"}
    assert saved["new-model"]["conclusion"] == "F1 0.4–0.7: fine-tune нужен"
    assert saved["new-model"]["n_examples"] == 2


def test_main_runs_with_fake_model_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _ = gliner2_modules
    output = tmp_path / "baseline.json"

    monkeypatch.setattr(
        baseline,
        "load_dataset",
        lambda: [
            {
                "text": "Маша пришла.",
                "entities": [{"label": "person", "start": 0, "end": 4}],
            }
        ],
    )
    monkeypatch.setattr(baseline, "_load_gliner", lambda _model: (object(), "fake"))
    monkeypatch.setattr(
        baseline,
        "_run_predictions",
        lambda _model, _model_type, _dataset, _threshold: [
            [{"label": "person", "start": 0, "end": 4}]
        ],
    )
    monkeypatch.setattr(
        baseline,
        "_compute_metrics",
        lambda _gold, _pred: {
            "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
        },
    )

    baseline.main.callback(model="fake-model", threshold=0.5, output=output)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake-model"]["overall"]["f1"] == pytest.approx(1.0)


def test_print_results_renders_table(gliner2_modules: tuple[Any, Any]) -> None:
    baseline, _ = gliner2_modules
    baseline._print_results(
        "fake/model",
        {
            "overall": {"precision": 1.0, "recall": 0.5, "f1": 0.67},
            "per_entity": {"person": {"precision": 1.0, "recall": 0.5, "f1": 0.67}},
        },
    )
