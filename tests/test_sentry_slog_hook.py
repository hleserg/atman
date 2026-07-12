"""Tests for Sentry slog breadcrumb hook chaining."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest

from atman.adapters.observability import sentry as sentry_module
from atman.core import session_log


@pytest.fixture(autouse=True)
def _reset_slog_and_sentry_hook() -> Generator[None, None, None]:
    session_log.set_display_hook(None)
    sentry_module._slog_hook_installed = False
    sentry_module._initialized = False
    yield
    session_log.set_display_hook(None)
    sentry_module._slog_hook_installed = False
    sentry_module._initialized = False


def test_install_slog_breadcrumb_hook_chains_previous_hook() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    def previous(event: str, data: dict[str, Any]) -> None:
        seen.append((event, data))

    session_log.set_display_hook(previous)
    sentry_module._initialized = True
    sentry_module.install_slog_breadcrumb_hook()

    session_log.slog("pipeline_stage", count=3)

    assert len(seen) == 1
    assert seen[0][0] == "pipeline_stage"
    assert seen[0][1]["count"] == 3


def test_install_slog_breadcrumb_hook_is_idempotent() -> None:
    calls = 0

    def previous(event: str, data: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1

    session_log.set_display_hook(previous)
    sentry_module._initialized = True
    sentry_module.install_slog_breadcrumb_hook()
    sentry_module.install_slog_breadcrumb_hook()

    session_log.slog("once")

    assert calls == 1


def test_sentry_slog_attrs_redacts_memory_and_user_text() -> None:
    attrs = sentry_module._sentry_slog_attrs(
        "ambient_injection",
        {
            "ts": "2026-07-12T11:00:00Z",
            "event": "ambient_injection",
            "agent_id": "agent-1",
            "content": "User shared a private fact",
            "what_happened": "A private journal excerpt",
            "query": "raw user message",
            "anchor": "Sergey",
            "anchors": ["Sergey"],
            "text": "Sergey",
            "items_total": 3,
        },
    )

    assert attrs == {
        "event": "ambient_injection",
        "agent_id": "agent-1",
        "items_total": "3",
        "redacted_fields": "anchor,anchors,content,query,text,what_happened",
    }


def test_sentry_slog_hook_keeps_sensitive_data_out_of_breadcrumb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sentry_sdk

    breadcrumbs: list[dict[str, Any]] = []
    previous_seen: list[dict[str, Any]] = []

    def previous(_event: str, data: dict[str, Any]) -> None:
        previous_seen.append(data)

    def add_breadcrumb(**kwargs: Any) -> None:
        breadcrumbs.append(kwargs)

    session_log.set_display_hook(previous)
    sentry_module._initialized = True
    monkeypatch.setattr(sentry_sdk, "add_breadcrumb", add_breadcrumb)
    sentry_module.install_slog_breadcrumb_hook()

    session_log.slog(
        "fact_added",
        agent_id="agent-1",
        content="User shared a private fact",
        source="session",
    )

    assert previous_seen[0]["content"] == "User shared a private fact"
    assert breadcrumbs[0]["data"] == {
        "event": "fact_added",
        "agent_id": "agent-1",
        "source": "session",
        "redacted_fields": "content",
    }


def test_session_transaction_propagates_body_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing session body must not be masked by a fallback yield in the CM."""
    sentry_module._initialized = True
    calls = {"entered": False, "exited": False}

    class _FakeTx:
        def set_tag(self, *_args: object, **_kwargs: object) -> None:
            return None

    @contextmanager
    def _fake_start_transaction(**_kwargs: object):
        calls["entered"] = True
        yield _FakeTx()

    monkeypatch.setattr(
        "sentry_sdk.start_transaction",
        _fake_start_transaction,
        raising=False,
    )

    with (
        pytest.raises(RuntimeError, match="session failed"),
        sentry_module.session_transaction("sid", "aid"),
    ):
        raise RuntimeError("session failed")

    assert calls["entered"] is True


def test_pipeline_span_noops_when_sentry_disabled() -> None:
    with sentry_module.pipeline_span("atman.ner", "entity detection"):
        pass


def test_metric_increment_falls_back_to_incr(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    sentry_module._initialized = True
    calls: list[str] = []

    class _Metrics:
        def count(self, *_args: object, **_kwargs: object) -> None:
            raise TypeError("attributes unsupported")

        def incr(self, *_args: object, **_kwargs: object) -> None:
            calls.append("incr")

    monkeypatch.setattr(sentry_sdk, "metrics", _Metrics(), raising=True)

    sentry_module.metric_increment("atman.turn", 1.0, {"agent": "a1"})

    assert calls == ["incr"]
