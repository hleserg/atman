from __future__ import annotations

import importlib.util
import json
import sys
import types
from importlib.abc import Loader
from pathlib import Path
from typing import Protocol, cast

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "generate_synthetic_ru.py"


class _SyntheticRuModule(Protocol):
    def pioneer_to_gliner(self, row: dict[str, object]) -> dict[str, object] | None: ...

    def validate_jsonl(self, path: Path) -> tuple[int, list[str]]: ...


def _load_synthetic_ru_module(monkeypatch: pytest.MonkeyPatch) -> _SyntheticRuModule:
    fake_requests = types.ModuleType("requests")
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    spec = importlib.util.spec_from_file_location(
        "atman_eval_generate_synthetic_ru_for_tests",
        _SCRIPT_PATH,
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return cast(_SyntheticRuModule, module)


def test_pioneer_to_gliner_tokenizes_offsets_and_filters_invalid_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_synthetic_ru_module(monkeypatch)

    converted = module.pioneer_to_gliner(
        {
            "text": "Маша поехала в Санкт-Петербург.",
            "entities": [
                ("Маша", "person"),
                ("Санкт-Петербург", "location"),
                ("Маша", "person"),  # duplicate span should not be emitted twice
                ("не найдено", "person"),
                ("Санкт-Петербург", "unknown_label"),
                ("broken-entry",),
            ],
        }
    )

    assert converted == {
        "tokenized_text": ["Маша", "поехала", "в", "Санкт-Петербург."],
        "ner": [[0, 0, "person"], [3, 3, "location"]],
    }


def test_validate_jsonl_reports_bad_labels_and_spans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_synthetic_ru_module(monkeypatch)
    path = tmp_path / "synthetic.jsonl"
    rows = [
        {"tokenized_text": ["Маша"], "ner": [[0, 0, "person"]]},
        {"tokenized_text": ["Маша"], "ner": [[0, 0, "unknown_label"]]},
        {"tokenized_text": ["Маша"], "ner": [[0, 1, "person"]]},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    valid_count, errors = module.validate_jsonl(path)

    assert valid_count == 1
    assert errors == [
        "line 2: unknown label 'unknown_label'",
        "line 3: span [0,1] invalid for 1 tokens",
    ]
