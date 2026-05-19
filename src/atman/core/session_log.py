"""Session debug log — toggle with ATMAN_SESSION_LOG=1.

Each line written to the log file is a JSON object:
    {"ts": "...", "event": "...", <extra fields>}

Usage:
    ATMAN_SESSION_LOG=1 python3 ...
    tail -f ~/.atman/session_debug.log | python3 -m json.tool
    tail -f ~/.atman/session_debug.log | jq .

Log file location:
    Default: ~/.atman/session_debug.log
    Override: ATMAN_SESSION_LOG_FILE=/path/to/file

To remove this instrumentation entirely:
    grep -r "session_log" src/ --include="*.py" -l
    # then remove the import lines and slog() calls from each file listed
    # and delete this file
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_ENABLED: bool | None = None
_LOG_PATH: Path | None = None

# Optional display hook: set_display_hook(fn) to receive every slog event in real-time.
# fn(event: str, data: dict) — must not raise.
_DISPLAY_HOOK: Callable[[str, dict[str, Any]], None] | None = None


def set_display_hook(fn: Callable[[str, dict[str, Any]], None] | None) -> None:
    """Register (or clear) a callable that is invoked on every slog() call.

    Pass None to unregister. The hook is called with the full record dict
    (including 'ts' and 'event'). Useful for live UIs — hook receives events
    synchronously so it should be fast.
    """
    global _DISPLAY_HOOK
    _DISPLAY_HOOK = fn


def _init() -> bool:
    global _ENABLED, _LOG_PATH
    if _ENABLED is not None:
        return _ENABLED
    # Enabled by default; set ATMAN_SESSION_LOG=0 to disable.
    val = os.environ.get("ATMAN_SESSION_LOG", "1").strip().lower()
    _ENABLED = val not in ("0", "false", "no", "off")
    if _ENABLED:
        path_str = os.environ.get("ATMAN_SESSION_LOG_FILE", "")
        _LOG_PATH = Path(path_str) if path_str else Path.home() / ".atman" / "session_debug.log"
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _ENABLED


def slog(event: str, **data: Any) -> None:
    """Emit one JSON-line to the session debug log.

    No-op when ATMAN_SESSION_LOG is not set. Also calls the display hook (if any).
    Never raises.
    """
    try:
        record: dict[str, Any] = {"ts": datetime.now(UTC).isoformat(), "event": event}
        record.update(data)
        if _DISPLAY_HOOK is not None:
            with contextlib.suppress(Exception):
                _DISPLAY_HOOK(event, record)
        if not _init():
            return
        line = json.dumps(record, default=str, ensure_ascii=False) + "\n"
        with _LOCK, _LOG_PATH.open("a", encoding="utf-8") as f:  # type: ignore[union-attr]
            f.write(line)
    except Exception:  # nosec B110 — slog must never raise
        return
