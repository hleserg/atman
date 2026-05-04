"""
SYSTEM_MAP §2.3 / §3 A,G integration: identity CLI workflow.

Verifies that ``python -m atman.cli_identity`` runs end-to-end against a
``FileStateStore`` workspace: bootstrap → show → snapshot → render.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


def _run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "atman.cli_identity", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_cli_identity_bootstrap_show_snapshot_render():
    """SYSTEM_MAP §3 A,G: full identity CLI workflow with FileStateStore workspace."""
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        agent_id = uuid4()

        # Bootstrap.
        boot = _run(
            [
                "init",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
            ]
        )
        assert boot.returncode == 0, boot.stderr
        assert (workspace / "identity.json").exists()

        # Show — must include the bootstrap self-description.
        show = _run(
            [
                "show",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
            ]
        )
        assert show.returncode == 0, show.stderr
        assert "Self-description" in show.stdout

        # Snapshot — produces an additional entry under identity_snapshots/.
        snapshots_before = list((workspace / "identity_snapshots").glob("*.json"))
        snap = _run(
            [
                "snapshot",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
                "--description",
                "manual checkpoint",
            ]
        )
        assert snap.returncode == 0, snap.stderr
        snapshots_after = list((workspace / "identity_snapshots").glob("*.json"))
        assert len(snapshots_after) == len(snapshots_before) + 1

        # Render NARRATIVE.md.
        rendered = _run(
            [
                "render",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
            ]
        )
        assert rendered.returncode == 0, rendered.stderr
        narrative_md = workspace / "NARRATIVE.md"
        assert narrative_md.exists()
        content = narrative_md.read_text(encoding="utf-8")
        assert "# NARRATIVE" in content


def test_cli_identity_show_unknown_agent_returns_error():
    """SYSTEM_MAP §4.1: ``show`` on an unknown agent exits with non-zero status."""
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        result = _run(
            [
                "show",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(uuid4()),
            ]
        )
        assert result.returncode != 0


def test_cli_identity_init_twice_for_same_agent_rejects_second():
    """SYSTEM_MAP §4.2: bootstrapping the same ``agent_id`` twice fails the second time."""
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        agent_id = uuid4()
        first = _run(
            [
                "init",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
            ]
        )
        assert first.returncode == 0, first.stderr

        second = _run(
            [
                "init",
                "--workspace",
                str(workspace),
                "--agent-id",
                str(agent_id),
            ]
        )
        assert second.returncode != 0
