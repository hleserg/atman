"""
SYSTEM_MAP §2.4 smoke tests: each demo entrypoint runs to completion.

Verifies that ``src/demo*.py`` modules execute end-to-end without errors and
without writing to ``$HOME``. This freezes the §3 scenario coverage that demos
exercise (factual memory, experience store, identity, reflection, web hint).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = REPO_ROOT / "src"

DEMO_SCRIPTS = [
    "demo.py",
    "demo_experience_store.py",
    "demo_identity.py",
    "demo_reflection.py",
    "demo_session_manager.py",
    "demo_web_dashboard.py",
]


@pytest.mark.parametrize("script", DEMO_SCRIPTS)
def test_demo_script_runs_to_completion(script: str):
    """SYSTEM_MAP §2.4: ``src/<script>`` exits zero with ``ATMAN_DEMO_PACE=off``."""
    path = DEMOS_DIR / script
    if not path.exists():  # pragma: no cover - guard for partial checkouts
        pytest.skip(f"Demo missing: {path}")

    env = {**os.environ, "ATMAN_DEMO_PACE": "off"}
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"{script} exited with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
