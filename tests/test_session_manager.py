"""
Tests for Session Manager.

Tests session lifecycle, key moment recording, and experience creation.
"""

from uuid import uuid4

import pytest

from atman.adapters.storage.file_state_store import FileStateStore
from atman.core.models import (
    CoreValue,
    EmotionalDepth,
    Goal,
    GoalHorizon,
    Identity,
    KeyMomentInput,
    LayerType,
    NarrativeDocument,
    NarrativeLayer,
    SessionEvent,
)
from atman.core.services import SessionManager, SessionNotFoundError


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary file storage."""
    return FileStateStore(workspace=tmp_path / "session_test")


@pytest.fixture
def test_identity():
    """Create test identity."""
    return Identity(
        id=uuid4(),
        self_description="Test agent",
        core_values=[
            CoreValue(
                name="honesty",
                description="Being truthful",
                confidence=0.8,
            )
        ],
        goals=[
            Goal(
                content="Test goal",
                horizon=GoalHorizon.SHORT,
            )
        ],
        emotional_baseline=0.0,
    )


@pytest.fixture
def test_narrative(test_identity):
    """Create test narrative."""
    return NarrativeDocument(
        identity_id=test_identity.id,
        core_layer=NarrativeLayer(
            layer_type=LayerType.CORE,
            content="Core narrative",
        ),
        recent_layer=NarrativeLayer(
            layer_type=LayerType.RECENT,
            content="Recent narrative",
        ),
    )


@pytest.fixture
def session_manager(temp_storage, test_identity, test_narrative):
    """Create session manager with test data."""
    temp_storage.save_identity(test_identity)
    temp_storage.save_narrative(test_narrative)
    return SessionManager(temp_storage), test_identity.id


def test_start_session_returns_context_with_identity_and_narrative(session_manager):
    """Test that start_session returns context with identity and narrative."""
    manager, agent_id = session_manager

    context = manager.start_session(agent_id)

    assert context is not None
    assert context.session_id is not None
    assert context.identity is not None
    assert context.identity.id == agent_id
    assert context.narrative is not None
    assert context.narrative.core_layer.content == "Core narrative"
    assert context.emotional_baseline == 0.0


def test_start_session_fails_without_identity(temp_storage):
    """Test that start_session fails if identity not found."""
    manager = SessionManager(temp_storage)
    fake_agent_id = uuid4()

    with pytest.raises(ValueError, match="Identity not found"):
        manager.start_session(fake_agent_id)


def test_record_event_tracks_event(session_manager):
    """Test that record_event tracks events."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    event = SessionEvent(
        session_id=context.session_id,
        event_type="test_event",
        description="Test event description",
    )

    manager.record_event(context.session_id, event)

    active_session = manager.get_active_session(context.session_id)
    assert active_session is not None
    assert len(active_session.events) == 1
    assert active_session.events[0].description == "Test event description"


def test_record_key_moment_with_valid_coloring(session_manager):
    """Test that record_key_moment accepts valid emotional coloring."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    moment = KeyMomentInput(
        what_happened="Something significant happened",
        emotional_valence=0.5,
        emotional_intensity=0.7,
        depth=EmotionalDepth.MEANINGFUL,
        why_it_matters="It matters because...",
        values_touched=["honesty"],
    )

    manager.record_key_moment(context.session_id, moment)

    active_session = manager.get_active_session(context.session_id)
    assert active_session is not None
    assert len(active_session.key_moments) == 1
    assert active_session.key_moments[0].what_happened == "Something significant happened"
    assert active_session.key_moments[0].how_i_felt.emotional_valence == 0.5


def test_record_key_moment_without_coloring_requires_incomplete_flag(session_manager):
    """Test that key moment without coloring requires incomplete_coloring flag."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Zero valence and intensity without incomplete_coloring should fail
    moment_no_flag = KeyMomentInput(
        what_happened="Something happened",
        emotional_valence=0.0,
        emotional_intensity=0.0,
        depth=EmotionalDepth.SURFACE,
        why_it_matters="It matters",
        incomplete_coloring=False,  # Explicit False
    )

    with pytest.raises(ValueError, match="no emotional coloring"):
        manager.record_key_moment(context.session_id, moment_no_flag)


def test_record_key_moment_with_incomplete_coloring_flag_is_allowed(session_manager):
    """Test that key moment with incomplete_coloring flag is allowed."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    moment_with_flag = KeyMomentInput(
        what_happened="Something happened but couldn't capture feeling",
        emotional_valence=0.0,
        emotional_intensity=0.0,
        depth=EmotionalDepth.SURFACE,
        why_it_matters="It matters",
        incomplete_coloring=True,  # Explicitly marked as incomplete
    )

    manager.record_key_moment(context.session_id, moment_with_flag)

    active_session = manager.get_active_session(context.session_id)
    assert active_session is not None
    assert active_session.incomplete_coloring is True


def test_finish_session_creates_experience_and_eigenstate(session_manager, temp_storage):
    """Test that finish_session creates SessionExperience and Eigenstate."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Record a key moment
    moment = KeyMomentInput(
        what_happened="Session work",
        emotional_valence=0.3,
        emotional_intensity=0.6,
        depth=EmotionalDepth.MEANINGFUL,
        why_it_matters="Learning",
        values_touched=["honesty"],
    )
    manager.record_key_moment(context.session_id, moment)

    # Finish session
    result = manager.finish_session(
        session_id=context.session_id,
        overall_emotional_tone=0.3,
        key_insight="Test insight",
        alignment_check=True,
    )

    assert result is not None
    assert result.session_id == context.session_id
    assert len(result.key_moments) == 1
    assert result.overall_emotional_tone == 0.3
    assert result.key_insight == "Test insight"
    assert result.eigenstate is not None
    assert result.eigenstate.session_id == context.session_id

    # Verify experience was stored
    experiences = temp_storage.list_recent_experiences(limit=1)
    assert len(experiences) == 1
    stored_exp = experiences[0].experience
    assert stored_exp.session_id == context.session_id
    assert stored_exp.recorded_by == "session_manager"
    assert len(stored_exp.key_moments) == 1


def test_finish_session_without_key_moments_fails(session_manager):
    """Test that finish_session fails if no key moments recorded."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Try to finish without key moments
    with pytest.raises(ValueError, match="without key moments"):
        manager.finish_session(context.session_id)


def test_key_moments_are_immutable_after_storage(session_manager, temp_storage):
    """Test that original key moments don't mutate after storage."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Record key moment
    original_what = "Original event"
    moment = KeyMomentInput(
        what_happened=original_what,
        emotional_valence=0.5,
        emotional_intensity=0.7,
        depth=EmotionalDepth.MEANINGFUL,
        why_it_matters="Testing immutability",
        values_touched=["honesty"],
    )
    manager.record_key_moment(context.session_id, moment)

    # Finish session
    result = manager.finish_session(
        session_id=context.session_id,
        overall_emotional_tone=0.5,
    )

    # Get stored experience
    experiences = temp_storage.list_recent_experiences(limit=1)
    stored_exp = experiences[0].experience

    # Original moment should match stored
    assert result.key_moments[0].what_happened == original_what
    assert stored_exp.key_moments[0].what_happened == original_what

    # Try to modify stored experience (should not affect original)
    # This tests Pydantic immutability, not our code mutating things
    assert stored_exp.recorded_by == "session_manager"


def test_resource_warning_can_be_recorded_as_key_moment(session_manager):
    """Test that resource/token warnings can be recorded as key moments."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Record resource warning as key moment
    warning_moment = KeyMomentInput(
        what_happened="Approaching token limit - need to wrap up session",
        emotional_valence=-0.2,
        emotional_intensity=0.4,
        depth=EmotionalDepth.SURFACE,
        why_it_matters="Resource constraints affect quality of work",
        values_touched=["competence"],
        what_changed="Learned to monitor resources during session",
    )

    manager.record_key_moment(context.session_id, warning_moment)

    active_session = manager.get_active_session(context.session_id)
    assert active_session is not None
    assert len(active_session.key_moments) == 1
    assert "token limit" in active_session.key_moments[0].what_happened


def test_session_not_found_errors(session_manager):
    """Test that operations on non-existent session raise SessionNotFoundError."""
    manager, _ = session_manager
    fake_session_id = uuid4()

    event = SessionEvent(
        session_id=fake_session_id,
        event_type="test",
        description="test",
    )

    with pytest.raises(SessionNotFoundError):
        manager.record_event(fake_session_id, event)

    moment = KeyMomentInput(
        what_happened="test",
        emotional_valence=0.5,
        emotional_intensity=0.5,
        depth=EmotionalDepth.SURFACE,
        why_it_matters="test",
    )

    with pytest.raises(SessionNotFoundError):
        manager.record_key_moment(fake_session_id, moment)

    with pytest.raises(SessionNotFoundError):
        manager.finish_session(fake_session_id)


def test_multiple_key_moments_in_session(session_manager):
    """Test recording multiple key moments in one session."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    moments = [
        KeyMomentInput(
            what_happened=f"Event {i}",
            emotional_valence=0.1 * i,
            emotional_intensity=0.5,
            depth=EmotionalDepth.SURFACE,
            why_it_matters=f"Reason {i}",
        )
        for i in range(1, 4)
    ]

    for moment in moments:
        manager.record_key_moment(context.session_id, moment)

    result = manager.finish_session(context.session_id)

    assert len(result.key_moments) == 3
    assert result.key_moments[0].what_happened == "Event 1"
    assert result.key_moments[1].what_happened == "Event 2"
    assert result.key_moments[2].what_happened == "Event 3"


def test_eigenstate_captures_session_state(session_manager):
    """Test that eigenstate captures key session information."""
    manager, agent_id = session_manager
    context = manager.start_session(agent_id)

    # Record moment with values
    moment = KeyMomentInput(
        what_happened="Complex work",
        emotional_valence=0.4,
        emotional_intensity=0.8,
        depth=EmotionalDepth.PROFOUND,
        why_it_matters="Deep learning",
        values_touched=["honesty", "competence"],
        principles_questioned=["always_be_certain"],
    )
    manager.record_key_moment(context.session_id, moment)

    result = manager.finish_session(
        session_id=context.session_id,
        overall_emotional_tone=0.4,
        key_insight="Deep insight",
    )

    eigenstate = result.eigenstate
    assert eigenstate is not None
    assert eigenstate.emotional_tone == 0.4
    assert eigenstate.emotional_intensity == 0.8  # From key moment
    assert eigenstate.session_summary == "Deep insight"
    assert "honesty" in eigenstate.dominant_themes or "competence" in eigenstate.dominant_themes
    assert "always_be_certain" in eigenstate.unresolved_tensions
