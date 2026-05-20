"""Resolve the live E2E session JSONL path safely (CodeQL path injection)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_ATMAN_HOME = Path.home() / ".atman"
_LOG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _atman_home() -> Path:
    return _ATMAN_HOME.resolve()


def _join_under_base(filename: str) -> Path:
    """Join a sanitized filename onto the trusted ``~/.atman`` root."""
    if not _LOG_NAME_RE.fullmatch(filename):
        msg = f"Invalid session log filename: {filename!r}"
        raise ValueError(msg)
    base = _atman_home()
    candidate = (base / filename).resolve()
    if not candidate.is_relative_to(base):
        msg = f"Session log path must stay under {base}"
        raise ValueError(msg)
    return candidate


def resolve_session_log_path() -> Path:
    """Return session log path under ``~/.atman`` (env override: basename only)."""
    override = os.environ.get("ATMAN_LIVE_SESSION_LOG")
    if not override:
        return _join_under_base("live-session.jsonl")
    return _join_under_base(Path(override).name)


def validate_session_log_path(path: Path) -> Path:
    """Ensure ``path`` resolves to a file under ``~/.atman`` before read/write."""
    base = _atman_home()
    candidate = path.expanduser().resolve()
    if not candidate.is_relative_to(base):
        msg = f"Session log path must stay under {base}"
        raise ValueError(msg)
    if not _LOG_NAME_RE.fullmatch(candidate.name):
        msg = f"Invalid session log filename: {candidate.name!r}"
        raise ValueError(msg)
    return candidate
