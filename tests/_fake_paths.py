"""Non-world-writable fake paths for Skill model tests (Sonar S5443)."""

from __future__ import annotations

from pathlib import Path

_FAKE_SKILL_ROOT = Path("/var/atman-test/skills")
_TEST_CMD_CWD = Path("/var/atman-test/cmd-workspace")
_TEST_RUNNER_WORKSPACE = Path("/var/atman-test/runner-workspace")


def fake_skill_root(name: str) -> Path:
    return _FAKE_SKILL_ROOT / name


def fake_skill_manifest(name: str) -> Path:
    return fake_skill_root(name) / "SKILL.md"
