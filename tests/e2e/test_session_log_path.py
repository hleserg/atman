"""Tests for e2e.session_log_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from e2e.session_log_path import resolve_session_log_path, validate_session_log_path


def test_resolve_session_log_default_under_atman_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATMAN_LIVE_SESSION_LOG", raising=False)
    path = resolve_session_log_path()
    base = (Path.home() / ".atman").resolve()
    assert path == base / "live-session.jsonl"


def test_validate_session_log_path_rejects_outside_home(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must stay under"):
        validate_session_log_path(tmp_path / "outside.jsonl")


def test_validate_session_log_path_allows_under_atman_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("e2e.session_log_path._ATMAN_HOME", tmp_path / ".atman")
    base = (tmp_path / ".atman").resolve()
    base.mkdir()
    allowed = base / "live-session.jsonl"
    assert validate_session_log_path(allowed) == allowed.resolve()
