"""Build command argv for subprocesses launched from the TUI."""

from __future__ import annotations

import shutil
import sys


def uv_or_python_argv(*parts: str) -> list[str]:
    """``uv run <parts>`` if ``uv`` is on PATH, else same interpreter as fallback."""
    if shutil.which("uv"):
        return ["uv", "run", *parts]
    if parts[0] == "pytest":
        return [sys.executable, "-m", "pytest", *parts[1:]]
    if parts[0] == "python":
        return [sys.executable, *parts[1:]]
    return [sys.executable, *parts]


def pytest_cmd(*pytest_args: str) -> list[str]:
    """Run pytest with **this** Python (``python -m pytest``).

    Avoids nested ``uv run pytest`` when the TUI itself was started via ``uv run devui``,
    which can stall or buffer stdout until the child exits.
    """
    return [sys.executable, "-m", "pytest", *pytest_args]


def python_script_cmd(*script_and_args: str) -> list[str]:
    """Run scripts with the same interpreter as the TUI (paths relative to repo root)."""
    return [sys.executable, *script_and_args]
