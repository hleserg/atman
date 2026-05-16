"""Tests for MicroReflectionService skill-loop hook integration."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from atman.skills.noop import NoopSkillManager


class TestMicroReflectionSkillHook:
    """Verify that MicroReflectionService calls process_session_skills correctly."""

    def _make_micro_reflection(self, skill_manager=None):
        from unittest.mock import MagicMock

        from atman.adapters.storage.in_memory_reflection_store import InMemoryReflectionEventStore
        from atman.core.models import NarrativeDocument
        from atman.core.models.narrative import LayerType, NarrativeLayer
        from atman.core.services.narrative_revision import NarrativeRevisionService
        from atman.core.services.reflection_service import MicroReflectionService

        # Mock session repo (R-Micro uses SessionRepository)
        session_repo = MagicMock()
        session_repo.get_session.return_value = MagicMock()
        session_repo.get_key_moments_for_session.return_value = [MagicMock()]

        # Mock narrative revision
        narrative_revision = MagicMock(spec=NarrativeRevisionService)
        narrative_revision.update_recent_layer.return_value = "recent layer updated"
        narrative_doc = NarrativeDocument(
            identity_id=uuid4(),
            core_layer=NarrativeLayer(content="core", layer_type=LayerType.CORE),
            recent_layer=NarrativeLayer(content="recent", layer_type=LayerType.RECENT),
        )
        narrative_revision.narrative_repo = MagicMock()
        narrative_revision.narrative_repo.get_current.return_value = narrative_doc

        service = MicroReflectionService(
            session_repo=session_repo,
            narrative_revision=narrative_revision,
            event_store=InMemoryReflectionEventStore(),
            skill_manager=skill_manager,
        )
        return service

    def test_skill_manager_process_called_with_agent_id(self):
        skill_manager = MagicMock()
        service = self._make_micro_reflection(skill_manager=skill_manager)

        agent_id = uuid4()
        session_id = uuid4()
        service.reflect(session_id, agent_id=agent_id)

        skill_manager.process_session_skills.assert_called_once_with(agent_id, session_id)

    def test_no_skill_manager_no_call(self):
        service = self._make_micro_reflection(skill_manager=None)
        # Should not raise even when no agent_id and no skill_manager
        session_id = uuid4()
        event = service.reflect(session_id)
        assert event is not None

    def test_skill_manager_none_agent_id_skipped(self):
        skill_manager = MagicMock()
        service = self._make_micro_reflection(skill_manager=skill_manager)
        # Pass session_id but no agent_id → process_session_skills must NOT be called
        service.reflect(uuid4(), agent_id=None)
        skill_manager.process_session_skills.assert_not_called()

    def test_skill_manager_error_does_not_propagate(self):
        """Errors in skill processing must not surface to caller."""
        skill_manager = MagicMock()
        skill_manager.process_session_skills.side_effect = RuntimeError("boom")
        service = self._make_micro_reflection(skill_manager=skill_manager)

        agent_id = uuid4()
        # Should not raise
        event = service.reflect(uuid4(), agent_id=agent_id)
        assert event is not None

    def test_noop_skill_manager_works(self):
        noop = NoopSkillManager()
        service = self._make_micro_reflection(skill_manager=noop)
        # NoopSkillManager.process_session_skills is a silent no-op
        event = service.reflect(uuid4(), agent_id=uuid4())
        assert event is not None
