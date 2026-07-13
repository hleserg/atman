"""Regression tests for the GLiNER2 eval helpers added for Russian NER."""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import math
from pathlib import Path
from typing import Any, Protocol, cast

import pytest


class _DatasetModule(Protocol):
    LABELS: list[str]

    def _build_span(self, text: str, entity_text: str, label: str) -> dict[str, object]: ...

    def load_dataset(self) -> list[dict[str, object]]: ...


class _BaselineModule(Protocol):
    def _conclusion(self, f1: float) -> str: ...

    def _run_predictions(
        self,
        model: Any,
        model_type: str,
        dataset: list[dict[str, Any]],
        threshold: float,
    ) -> list[list[dict[str, Any]]]: ...

    def _save_results(
        self,
        output: Path,
        model_id: str,
        metrics: dict[str, Any],
        n_examples: int,
        threshold: float,
    ) -> None: ...


def _allow_missing_eval_canary(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(
        name: str,
        package: str | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if name == "alembic":
            return importlib.machinery.ModuleSpec("alembic", loader=None)
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def _load_dataset_module(monkeypatch: pytest.MonkeyPatch) -> _DatasetModule:
    _allow_missing_eval_canary(monkeypatch)
    module = importlib.import_module("atman.eval.gliner2.dataset")
    return cast(_DatasetModule, module)


def _load_baseline_module(monkeypatch: pytest.MonkeyPatch) -> _BaselineModule:
    _allow_missing_eval_canary(monkeypatch)
    module = importlib.import_module("atman.eval.gliner2.baseline")
    return cast(_BaselineModule, module)


def test_gliner2_dataset_spans_match_source_text_and_known_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _load_dataset_module(monkeypatch)

    examples = dataset.load_dataset()

    assert len(examples) == 130
    assert len(dataset.LABELS) == len(set(dataset.LABELS)) == 13
    for example in examples:
        text = example["text"]
        assert isinstance(text, str)
        entities = example["entities"]
        assert isinstance(entities, list)
        assert entities
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
            assert label in dataset.LABELS
            assert 0 <= start < end <= len(text)
            assert text[start:end] == entity_text


def test_gliner2_dataset_rejects_missing_entity_text(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _load_dataset_module(monkeypatch)

    with pytest.raises(ValueError, match="not found"):
        dataset._build_span("Маша пришла домой.", "Сергей", "person")


def test_gliner2_baseline_normalizes_gliner2_and_gliner_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _load_baseline_module(monkeypatch)
    examples = [{"text": "Маша дома"}]

    class _FakeGliner2Model:
        def extract_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
            include_spans: bool,
        ) -> dict[str, dict[str, list[dict[str, int]]]]:
            assert text == "Маша дома"
            assert "person" in labels
            assert math.isclose(threshold, 0.42)
            assert include_spans is True
            return {"entities": {"person": [{"start": 0, "end": 4}]}}

    class _FakeGlinerModel:
        def predict_entities(
            self,
            text: str,
            labels: list[str],
            *,
            threshold: float,
        ) -> list[dict[str, object]]:
            assert text == "Маша дома"
            assert "location" in labels
            assert math.isclose(threshold, 0.42)
            return [{"label": "location", "start": 5, "end": 9, "score": 0.9}]

    assert baseline._run_predictions(_FakeGliner2Model(), "gliner2", examples, 0.42) == [
        [{"label": "person", "start": 0, "end": 4}]
    ]
    assert baseline._run_predictions(_FakeGlinerModel(), "gliner", examples, 0.42) == [
        [{"label": "location", "start": 5, "end": 9}]
    ]


def test_gliner2_baseline_save_results_merges_model_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _load_baseline_module(monkeypatch)
    output = tmp_path / "baseline.json"
    output.write_text(
        json.dumps({"existing/model": {"model": "existing/model"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    metrics = {
        "overall": {"precision": 0.5, "recall": 0.75, "f1": 0.6},
        "per_entity": {"person": {"precision": 1.0, "recall": 0.5, "f1": 0.667}},
    }

    baseline._save_results(output, "new/model", metrics, n_examples=130, threshold=0.5)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["existing/model"]["model"] == "existing/model"
    assert math.isclose(float(saved["new/model"]["threshold"]), 0.5)
    assert saved["new/model"]["n_examples"] == 130
    assert saved["new/model"]["overall"] == metrics["overall"]
    assert saved["new/model"]["conclusion"] == baseline._conclusion(0.6)
