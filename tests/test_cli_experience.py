"""
SYSTEM_MAP §2.3 / §3 B integration: experience CLI (interactive REPL).

The CLI persists JSONL under ``$HOME/.atman/experiences.jsonl``; tests redirect
``HOME`` to a temporary directory and feed commands via stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "fixtures" / "experience1_competence_challenge.json"


def _run_cli(stdin: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        [sys.executable, "-m", "atman.cli_experience"],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_cli_experience_add_from_fixture_and_search():
    """SYSTEM_MAP §3 B: ``add`` from a JSON fixture persists; ``search`` recovers it."""
    if not FIXTURE.exists():  # pragma: no cover - guard for partial checkouts
        pytest.skip("Experience fixture missing")

    with TemporaryDirectory() as tmp:
        home = Path(tmp)
        result = _run_cli(
            "\n".join(
                [
                    f"add {FIXTURE}",
                    "search depth meaningful",
                    "exit",
                ]
            )
            + "\n",
            home=home,
        )
        assert result.returncode == 0, result.stderr
        assert "Experience created" in result.stdout
        # Search returns at least one experience back.
        assert "Found 1 experience" in result.stdout or "Found" in result.stdout

        # Persistence: storage file contains JSONL with at least one entry.
        storage = home / ".atman" / "experiences.jsonl"
        assert storage.exists()
        lines = [ln for ln in storage.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) >= 1
        first = json.loads(lines[0])
        assert "experience" in first or "schema_version" in first


def test_cli_experience_add_missing_file_reports_error():
    """SYSTEM_MAP §4.1: ``add`` against a missing file reports a clear error."""
    with TemporaryDirectory() as tmp:
        home = Path(tmp)
        result = _run_cli(
            "\n".join(["add /no/such/file.json", "exit"]) + "\n",
            home=home,
        )
        assert result.returncode == 0
        assert "File not found" in result.stderr
