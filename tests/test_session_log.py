"""Tests for optional session debug logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atman.core import session_log


def test_slog_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATMAN_SESSION_LOG", "0")
    session_log._ENABLED = None
    session_log._LOG_PATH = None

    session_log.slog("test_event", foo="bar")  # must not raise


def test_slog_writes_json_line_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_file = tmp_path / "session.jsonl"
    monkeypatch.setenv("ATMAN_SESSION_LOG", "1")
    monkeypatch.setenv("ATMAN_SESSION_LOG_FILE", str(log_file))
    session_log._ENABLED = None
    session_log._LOG_PATH = None

    session_log.slog("hello", answer=42)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "hello"
    assert payload["answer"] == 42


def test_get_display_hook_returns_registered_hook() -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    def hook(event: str, data: dict[str, object]) -> None:
        seen.append((event, data))

    session_log.set_display_hook(hook)
    try:
        assert session_log.get_display_hook() is hook
        session_log.slog("hooked", value=1)
        assert seen and seen[0][0] == "hooked"
    finally:
        session_log.set_display_hook(None)
        assert session_log.get_display_hook() is None


def test_install_slog_hook_chains_previous_display_hook() -> None:
    from atman.web_dashboard.utils.chat_deps import install_slog_hook

    seen: list[tuple[str, dict[str, object]]] = []

    def previous(event: str, data: dict[str, object]) -> None:
        seen.append((event, data))

    session_log.set_display_hook(previous)
    events_log: list[dict] = []
    try:
        install_slog_hook(events_log)
        session_log.slog("dashboard_event", count=2)
        assert seen and seen[0][0] == "dashboard_event"
        assert events_log and events_log[0]["event"] == "dashboard_event"
    finally:
        session_log.set_display_hook(None)
