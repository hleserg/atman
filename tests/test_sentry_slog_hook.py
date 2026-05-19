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
