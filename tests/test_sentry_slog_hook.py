"""Tests for Sentry slog breadcrumb hook chaining."""

from __future__ import annotations

from collections.abc import Generator
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
