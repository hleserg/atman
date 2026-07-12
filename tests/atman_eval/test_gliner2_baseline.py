"""Tests for the GLiNER2 baseline eval helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner


@pytest.fixture
def gliner2_modules() -> tuple[Any, Any]:
    from atman.eval.gliner2 import baseline as baseline_module
    from atman.eval.gliner2 import dataset as dataset_module

    return baseline_module, dataset_module


def test_load_dataset_returns_valid_character_spans(gliner2_modules: tuple[Any, Any]) -> None:
    _baseline, dataset_module = gliner2_modules
    dataset = dataset_module.load_dataset()

    assert len(dataset) >= 100
    for example in dataset:
        text = example["text"]
        for entity in example["entities"]:
            assert entity["label"] in dataset_module.LABELS
            assert text[entity["start"] : entity["end"]] == entity["text"]


def test_build_span_rejects_missing_entity_text(gliner2_modules: tuple[Any, Any]) -> None:
    _baseline, dataset_module = gliner2_modules
    with pytest.raises(ValueError, match="not found"):
        dataset_module._build_span("Текст без сущности", "Сергей", "person")


def test_run_predictions_supports_gliner2_response_shape(
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, dataset_module = gliner2_modules

    class FakeGLiNER2:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, dict[str, list[dict[str, int]]]]:
            assert text == "Сергей пришёл"
            assert labels == dataset_module.LABELS
            assert threshold == 0.42
            assert include_spans is True
            return {"entities": {"person": [{"start": 0, "end": 6}]}}

    predictions = baseline._run_predictions(
        FakeGLiNER2(),
        "gliner2",
        [{"text": "Сергей пришёл", "entities": []}],
        0.42,
    )

    assert predictions == [[{"label": "person", "start": 0, "end": 6}]]


def test_run_predictions_supports_legacy_gliner_response_shape(
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, dataset_module = gliner2_modules

    class FakeGLiNER:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, int | str]]:
            assert text == "Москва ждёт"
            assert labels == dataset_module.LABELS
            assert threshold == 0.5
            return [{"label": "location", "start": 0, "end": 6, "score": "0.9"}]

    predictions = baseline._run_predictions(
        FakeGLiNER(),
        "gliner",
        [{"text": "Москва ждёт", "entities": []}],
        0.5,
    )

    assert predictions == [[{"label": "location", "start": 0, "end": 6}]]


def test_compute_metrics_normalizes_nervaluate_results(
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, dataset_module = gliner2_modules
    fake_module = ModuleType("nervaluate")

    class FakeEvaluator:
        def __init__(
            self,
            gold: list[list[dict[str, Any]]],
            pred: list[list[dict[str, Any]]],
            *,
            tags: list[str],
        ) -> None:
            assert gold == [[{"label": "person", "start": 0, "end": 6}]]
            assert pred == [[{"label": "person", "start": 0, "end": 6}]]
            assert tags == dataset_module.LABELS

        def evaluate(self) -> dict[str, Any]:
            return {
                "overall": {
                    "strict": SimpleNamespace(precision=0.98765, recall=0.87654, f1=0.76543)
                },
                "entities": {
                    "person": {
                        "strict": SimpleNamespace(precision=1.0, recall=0.5, f1=0.66666)
                    }
                },
            }

    setattr(fake_module, "Evaluator", FakeEvaluator)
    monkeypatch.setitem(sys.modules, "nervaluate", fake_module)

    metrics = baseline._compute_metrics(
        [[{"label": "person", "start": 0, "end": 6}]],
        [[{"label": "person", "start": 0, "end": 6}]],
    )

    assert metrics["overall"] == {"precision": 0.9877, "recall": 0.8765, "f1": 0.7654}
    assert metrics["per_entity"]["person"] == {"precision": 1.0, "recall": 0.5, "f1": 0.6667}
    assert metrics["per_entity"]["animal"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_save_results_merges_existing_model_entries(
    tmp_path: Path,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _dataset_module = gliner2_modules
    output = tmp_path / "results.json"
    output.write_text(json.dumps({"old-model": {"overall": {"f1": 0.1}}}), encoding="utf-8")
    metrics = {
        "overall": {"precision": 0.8, "recall": 0.7, "f1": 0.75},
        "per_entity": {"person": {"precision": 1.0, "recall": 0.5, "f1": 0.6667}},
    }

    baseline._save_results(output, "new-model", metrics, n_examples=2, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert sorted(saved) == ["new-model", "old-model"]
    assert saved["new-model"]["n_examples"] == 2
    assert saved["new-model"]["conclusion"].startswith("F1 > 0.7")


def test_load_gliner_prefers_gliner2_module(
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _dataset_module = gliner2_modules
    fake_module = ModuleType("gliner2")

    class FakeGLiNER2:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            assert model_id == "fastino/gliner2-multi-v1"
            return "gliner2-model"

    setattr(fake_module, "GLiNER2", FakeGLiNER2)
    monkeypatch.setitem(sys.modules, "gliner2", fake_module)

    model, model_type = baseline._load_gliner("fastino/gliner2-multi-v1")

    assert model == "gliner2-model"
    assert model_type == "gliner2"


def test_load_gliner_falls_back_to_legacy_gliner(
    monkeypatch: pytest.MonkeyPatch,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _dataset_module = gliner2_modules
    fake_gliner2 = ModuleType("gliner2")
    fake_gliner = ModuleType("gliner")

    class FakeGLiNER2:
        @classmethod
        def from_pretrained(cls, _model_id: str) -> str:
            raise RuntimeError("unsupported config")

    class FakeGLiNER:
        @classmethod
        def from_pretrained(cls, model_id: str) -> str:
            assert model_id == "urchade/gliner_multi-v2.1"
            return "legacy-model"

    setattr(fake_gliner2, "GLiNER2", FakeGLiNER2)
    setattr(fake_gliner, "GLiNER", FakeGLiNER)
    monkeypatch.setitem(sys.modules, "gliner2", fake_gliner2)
    monkeypatch.setitem(sys.modules, "gliner", fake_gliner)

    model, model_type = baseline._load_gliner("urchade/gliner_multi-v2.1")

    assert model == "legacy-model"
    assert model_type == "gliner"


def test_main_runs_with_fake_model_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    gliner2_modules: tuple[Any, Any],
) -> None:
    baseline, _dataset_module = gliner2_modules
    output = tmp_path / "baseline.json"
    dataset = [
        {
            "text": "Сергей пришёл",
            "entities": [{"label": "person", "start": 0, "end": 6, "text": "Сергей"}],
        }
    ]
    metrics = {
        "overall": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
        "per_entity": {"person": {"precision": 1.0, "recall": 1.0, "f1": 1.0}},
    }

    monkeypatch.setattr(baseline, "load_dataset", lambda: dataset)
    monkeypatch.setattr(baseline, "_load_gliner", lambda _model_id: (object(), "gliner"))
    monkeypatch.setattr(
        baseline,
        "_run_predictions",
        lambda _model, _model_type, _dataset, _threshold: [
            [{"label": "person", "start": 0, "end": 6}]
        ],
    )
    monkeypatch.setattr(baseline, "_compute_metrics", lambda _gold, _pred: metrics)
    monkeypatch.setattr(baseline, "_print_results", lambda _model_id, _metrics: None)

    result = CliRunner().invoke(
        baseline.main,
        ["--model", "fake-model", "--threshold", "0.4", "--output", str(output)],
    )

    assert result.exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["fake-model"]["threshold"] == 0.4
