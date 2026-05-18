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
