"""Resolve the live E2E session JSONL path safely (CodeQL path injection)."""

from __future__ import annotations

import os
from pathlib import Path

_ATMAN_HOME = Path.home() / ".atman"


def _atman_home() -> Path:
    return _ATMAN_HOME.resolve()


def resolve_session_log_path() -> Path:
    """Return session log path under ``~/.atman`` unless env override stays under that root."""
    base = _atman_home()
    override = os.environ.get("ATMAN_LIVE_SESSION_LOG")
    if not override:
        return base / "live-session.jsonl"
    return validate_session_log_path(Path(override))


def validate_session_log_path(path: Path) -> Path:
    """Ensure ``path`` resolves under ``~/.atman`` before read/write."""
    base = _atman_home()
    candidate = path.expanduser().resolve()
    if candidate != base and base not in candidate.parents:
        msg = f"Session log path must stay under {base}"
        raise ValueError(msg)
    return candidate
