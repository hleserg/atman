"""
SYSTEM_MAP §2.3 / §3 C-E integration: reflection CLI workflow.

Verifies that ``python -m atman.cli_reflection`` runs all three reflection
levels against the bundled fixtures.
"""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run cli_reflection with no demo pacing for fast tests."""
    return subprocess.run(
        [sys.executable, "-m", "atman.cli_reflection", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env={**__import__("os").environ, "ATMAN_DEMO_PACE": "off"},
    )


def test_cli_reflection_micro_with_fixtures():
    """SYSTEM_MAP §3 C: ``reflect micro --fixtures`` runs to completion."""
    result = _run("reflect", "micro", "--fixtures")
    assert result.returncode == 0, result.stderr
    assert "Reflection Complete" in result.stdout
    assert "MICRO" in result.stdout.upper()


def test_cli_reflection_daily_with_fixtures():
    """SYSTEM_MAP §3 D: ``reflect daily --fixtures`` runs and reports patterns/reframing."""
    result = _run("reflect", "daily", "--fixtures")
    assert result.returncode == 0, result.stderr
    assert "Reflection Complete" in result.stdout
    assert "Patterns detected" in result.stdout
    assert "Reframing notes added" in result.stdout


def test_cli_reflection_deep_with_fixtures():
    """SYSTEM_MAP §3 E: ``reflect deep --fixtures`` runs and reports a health score."""
    result = _run("reflect", "deep", "--fixtures")
    assert result.returncode == 0, result.stderr
    assert "Reflection Complete" in result.stdout
    assert "Health score" in result.stdout


def test_cli_reflection_unknown_command_exits_non_zero():
    """SYSTEM_MAP §4.1: invalid sub-command surfaces a non-zero exit."""
    result = _run("reflect", "unknown", "--fixtures")
    assert result.returncode != 0
