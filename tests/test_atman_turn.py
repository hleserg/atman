"""Unit tests for AtmanTurn per-turn pipeline (Chat UI / host agents)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from atman.adapters.agent.deps import AtmanDeps
from atman.adapters.agent.runner import AtmanTurn
from atman.adapters.reflection.mock_reflection_model import MockReflectionModel
from atman.adapters.storage import InMemoryExperienceStore, InMemoryStateStore
from atman.adapters.storage.in_memory_reflection_store import InMemoryReflectionEventStore
from atman.core.models import LayerType, NarrativeDocument, NarrativeLayer
from atman.core.narrative_write_audit import NoOpNarrativeWriteAudit
from atman.core.services import (
    ExperienceService,
    IdentityService,
    MicroReflectionService,
    NarrativeRevisionService,
    SessionManager,
)


def _minimal_deps(*, injected_context: str | None = None) -> tuple[AtmanDeps, SessionManager]:
    agent_id = uuid4()
    state_store = InMemoryStateStore()
    experience_service = ExperienceService(InMemoryExperienceStore())
    event_store = InMemoryReflectionEventStore()
    narrative_revision = NarrativeRevisionService(
        narrative_repo=state_store,  # type: ignore[arg-type]
        reflection_model=MockReflectionModel(),
        narrative_audit=NoOpNarrativeWriteAudit(),
    )
    identity_service = IdentityService(state_store)
    identity_service.bootstrap_identity(agent_id)
    state_store.save_narrative(
        NarrativeDocument(
            id=uuid4(),
            identity_id=agent_id,
            core_layer=NarrativeLayer(
                layer_type=LayerType.CORE,
                content="Bootstrap core.",
            ),
            recent_layer=NarrativeLayer(
                layer_type=LayerType.RECENT,
                content="Bootstrap recent.",
            ),
            threads=[],
            updated_at=datetime.now(UTC),
        )
    )
    sm = SessionManager(state_store)
    session_id = sm.start_session(agent_id).session_id
    deps = AtmanDeps(
        session_manager=sm,
        identity_service=identity_service,
        micro_reflection=MicroReflectionService(
            session_repo=experience_service,  # type: ignore[arg-type]
            narrative_revision=narrative_revision,
            event_store=event_store,
        ),
        state_store=state_store,
        agent_id=agent_id,
        session_id=session_id,
        injected_context=injected_context,
    )
    return deps, sm


def test_atman_turn_pre_clears_stale_injected_context() -> None:
    """pre() must not accumulate prior-turn RAG in injected_context."""
    deps, sm = _minimal_deps(injected_context="stale turn context")
    turn = AtmanTurn(deps, sm, deps.session_id)
    out = turn.pre("hello")
    assert out.injected_context is None or "stale turn context" not in (out.injected_context or "")


def test_atman_turn_post_schedules_affect_via_record_event() -> None:
    """post() records agent_response so SessionManager can run AffectDetector."""
    deps, sm = _minimal_deps()
    assert deps.session_id is not None
    turn = AtmanTurn(deps, sm, deps.session_id)
    turn.pre("hi")
    turn.post("Agent reply without thinking tags.")
    active = sm.get_active_session(deps.session_id)
    assert active is not None
    agent_events = [e for e in active.events if e.event_type == "agent_response"]
    assert agent_events
    assert "Agent reply" in agent_events[-1].description
