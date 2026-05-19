"""Tests for span helpers — HLE-247 P2.1 acceptance criteria."""

from __future__ import annotations

import builtins
import sys
from unittest.mock import MagicMock, patch

import pytest

from atman.observability.spans import (
    ai_chat_span,
    ai_embeddings_span,
    ai_rerank_span,
    cron_span,
    db_span,
    memory_span,
    pipeline_span,
)


def _make_mock_span() -> MagicMock:
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    return span


@pytest.fixture()
def mock_sentry(monkeypatch):
    """Patch sentry_sdk.start_span to return a controllable mock span."""
    span = _make_mock_span()
    with patch("sentry_sdk.start_span", return_value=span) as mock_start:
        yield mock_start, span


# ---------------------------------------------------------------------------
# AC-1: each helper has correct op and required attributes
# ---------------------------------------------------------------------------


def test_ai_chat_span_op(mock_sentry):
    mock_start, span = mock_sentry
    with ai_chat_span("anthropic", "claude-opus-4-7") as _:
        pass
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["op"] == "gen_ai.chat"
    span.set_data.assert_any_call("gen_ai.operation.name", "chat")
    span.set_data.assert_any_call("gen_ai.provider.name", "anthropic")
    span.set_data.assert_any_call("gen_ai.request.model", "claude-opus-4-7")


def test_ai_chat_span_custom_op(mock_sentry):
    mock_start, span = mock_sentry
    with ai_chat_span("openai", "gpt-4o", op_name="stream") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "gen_ai.stream"
    span.set_data.assert_any_call("gen_ai.operation.name", "stream")


def test_ai_embeddings_span(mock_sentry):
    mock_start, span = mock_sentry
    with ai_embeddings_span("bge", "BAAI/bge-m3") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "gen_ai.embeddings"
    span.set_data.assert_any_call("gen_ai.operation.name", "embeddings")
    span.set_data.assert_any_call("gen_ai.provider.name", "bge")
    span.set_data.assert_any_call("gen_ai.request.model", "BAAI/bge-m3")


def test_ai_rerank_span(mock_sentry):
    mock_start, span = mock_sentry
    with ai_rerank_span("bge", "BAAI/bge-reranker-v2-m3", docs_in=20, top_n=5) as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "gen_ai.rerank"
    span.set_data.assert_any_call("rerank.docs_in", 20)
    span.set_data.assert_any_call("rerank.top_n", 5)


def test_memory_span(mock_sentry):
    mock_start, span = mock_sentry
    with memory_span("recall", "facts", agent_id="agent-1") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "memory.recall"
    span.set_data.assert_any_call("memory.action", "recall")
    span.set_data.assert_any_call("memory.namespace", "facts")
    span.set_data.assert_any_call("agent_id", "agent-1")


def test_db_span_postgresql(mock_sentry):
    mock_start, span = mock_sentry
    with db_span("postgresql", "SELECT", collection="facts") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "db"
    span.set_data.assert_any_call("db.system", "postgresql")
    span.set_data.assert_any_call("db.operation", "SELECT")
    span.set_data.assert_any_call("db.collection", "facts")


def test_db_span_no_collection(mock_sentry):
    _mock_start, span = mock_sentry
    with db_span("qdrant", "search") as _:
        pass
    calls = {call.args[0] for call in span.set_data.call_args_list}
    assert "db.collection" not in calls


def test_cron_span(mock_sentry):
    mock_start, span = mock_sentry
    with cron_span("atman-maintenance") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "cron"
    span.set_data.assert_any_call("cron.monitor_slug", "atman-maintenance")


def test_pipeline_span_uses_name_not_description(mock_sentry):
    mock_start, _span = mock_sentry
    with pipeline_span("atman.ner", "entity detection") as _:
        pass
    assert mock_start.call_args.kwargs["op"] == "atman.ner"
    assert mock_start.call_args.kwargs["name"] == "entity detection"
    assert "description" not in mock_start.call_args.kwargs


# ---------------------------------------------------------------------------
# AC-2: helpers do not raise when Sentry is uninitialised
# ---------------------------------------------------------------------------


def test_ai_chat_span_noop_when_uninit():
    """sentry_sdk.start_span is a no-op when Sentry is not initialised."""
    # Call without patching — SDK noop span is returned naturally
    with ai_chat_span("test-provider", "test-model") as span:
        assert span is not None  # SDK returns NoopSpan


def test_memory_span_noop_when_uninit():
    with memory_span("store", "experiences") as span:
        assert span is not None


def test_db_span_noop_when_uninit():
    with db_span("postgresql", "INSERT") as span:
        assert span is not None


def test_span_helpers_skip_sentry_import_when_off(monkeypatch):
    """ATMAN_OBS_LEVEL=off must not import sentry_sdk inside span helpers."""
    monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
    sentry_keys = [k for k in sys.modules if k.startswith("sentry_sdk")]
    saved = {k: sys.modules.pop(k) for k in sentry_keys}
    real_import = builtins.__import__
    imported: list[str] = []

    def tracking_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", tracking_import)
    try:
        with ai_chat_span("anthropic", "claude") as span:
            assert span is None
        assert imported == []
    finally:
        sys.modules.update(saved)


# ---------------------------------------------------------------------------
# Verify span context manager propagates exceptions
# ---------------------------------------------------------------------------


def test_span_propagates_exception(mock_sentry):
    _mock_start, _span = mock_sentry
    with pytest.raises(ValueError, match="boom"), ai_chat_span("x", "y"):
        raise ValueError("boom")
