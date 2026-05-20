"""Resolve the live E2E session JSONL path safely (CodeQL path injection)."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_session_log_path() -> Path:
    """Return session log path under ``~/.atman`` unless env override stays under that root."""
    base = (Path.home() / ".atman").resolve()
    override = os.environ.get("ATMAN_LIVE_SESSION_LOG")
    if not override:
        return base / "live-session.jsonl"
    candidate = Path(override).expanduser().resolve()
    if candidate != base and base not in candidate.parents:
        msg = f"ATMAN_LIVE_SESSION_LOG must stay under {base}"
        raise ValueError(msg)
    return candidate
