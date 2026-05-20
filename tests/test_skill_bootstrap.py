"""Tests for pinned-skills bootstrap injection in build_instructions()."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from atman.skills.models import Skill, SkillKind, SkillOrigin, SkillStatus
from tests._fake_paths import fake_skill_manifest, fake_skill_root


def _now():
    return datetime.now(UTC)


def _make_skill(name: str, description: str, user_pinned: bool = True, agent_id=None) -> Skill:
    now = _now()
    return Skill(
        id=uuid4(),
        agent_id=agent_id or uuid4(),
        entity_id=uuid4(),
        name=name,
        description=description,
        version="0.1.0",
        kind=SkillKind.active,
        status=SkillStatus.active,
        origin=SkillOrigin.in_session,
        core=False,
        session_scoped=False,
        user_pinned=user_pinned,
        auto_pinned=False,
        invocations_count=5,
        success_count=4,
        failure_count=1,
        last_used_at=now,
        sessions_since_use=0,
        revision_needed=False,
        revision_priority=0,
        last_revised_at=None,
        manifest_inferred=False,
        skill_root=fake_skill_root(name),
        manifest_path=fake_skill_manifest(name),
        created_at=now,
        updated_at=now,
    )


def _make_deps(skill_manager=None, agent_id=None):
    """Build a minimal AtmanDeps-like mock (no spec to avoid frozen-dataclass conflicts)."""
    from unittest.mock import MagicMock

    deps = MagicMock()
    deps.agent_id = agent_id or uuid4()
    deps.skill_manager = skill_manager
    deps.injected_context = None
    deps.truncate_narrative_recent = 2000
    deps.truncate_narrative_core = 1000
    return deps


class TestPinnedSkillsBootstrap:
    def test_pinned_skills_appear_in_instructions(self):
        from atman.adapters.agent.instructions import _build_pinned_skills_section

        agent_id = uuid4()
        skill = _make_skill("outlet-control", "Controls smart outlets.", agent_id=agent_id)
        skill_manager = MagicMock()
        skill_manager.list_pinned.return_value = [skill]

        deps = _make_deps(skill_manager=skill_manager, agent_id=agent_id)
        section = _build_pinned_skills_section(deps)

        assert "outlet-control" in section
        assert "Controls smart outlets." in section

    def test_no_pinned_skills_returns_empty(self):
        from atman.adapters.agent.instructions import _build_pinned_skills_section

        skill_manager = MagicMock()
        skill_manager.list_pinned.return_value = []
        deps = _make_deps(skill_manager=skill_manager)

        assert _build_pinned_skills_section(deps) == ""

    def test_no_skill_manager_returns_empty(self):
        from atman.adapters.agent.instructions import _build_pinned_skills_section

        deps = _make_deps(skill_manager=None)
        assert _build_pinned_skills_section(deps) == ""

    def test_self_awareness_with_skills(self):
        from atman.adapters.agent.instructions import _build_self_awareness_section

        skill_manager = MagicMock()
        deps = _make_deps(skill_manager=skill_manager)
        section = _build_self_awareness_section(deps)

        assert "Навыки" in section
        assert "mark_result" in section or "навык" in section.lower()

    def test_self_awareness_without_skills(self):
        from atman.adapters.agent.instructions import _build_self_awareness_section

        deps = _make_deps(skill_manager=None)
        section = _build_self_awareness_section(deps)

        # Self-awareness block should still exist but without skills section
        assert "Atman" in section
        assert "памят" in section.lower() or "память" in section.lower()
        assert "atman_skills_mark_result" not in section

    def test_skill_manager_error_returns_empty_section(self):
        from atman.adapters.agent.instructions import _build_pinned_skills_section

        skill_manager = MagicMock()
        skill_manager.list_pinned.side_effect = RuntimeError("DB error")
        deps = _make_deps(skill_manager=skill_manager)

        # Should not raise
        section = _build_pinned_skills_section(deps)
        assert section == ""
