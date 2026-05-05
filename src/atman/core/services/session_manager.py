"""
Session Manager - the session runtime that experiences sessions in real-time.

This is not a data packager - this is an active participant in experience.
Session Manager:
1. Loads personality context at session start
2. Tracks events and key moments during session
3. Colors experience in real-time (not retrospectively)
4. Transfers already-colored experience to Experience Store
5. Creates eigenstate at session end

Critical design principle:
- Experience is colored IN THE MOMENT, not guessed later
- If coloring is incomplete, use incomplete_coloring flag
- Session Manager doesn't fabricate emotions - it records what was actually experienced
"""

from datetime import UTC, datetime
from uuid import UUID

from atman.core.models import (
    Eigenstate,
    ExperienceRecord,
    KeyMomentInput,
    SessionContext,
    SessionEvent,
    SessionExperience,
    SessionResult,
)
from atman.core.ports.state_store import StateStore


class SessionNotFoundError(Exception):
    """Raised when session is not found."""

    pass


class SessionAlreadyFinishedError(Exception):
    """Raised when trying to modify a finished session."""

    pass


class SessionManager:
    """
    Session runtime that experiences sessions in real-time.

    Manages the complete session lifecycle:
    - start_session: loads personality context
    - record_event: tracks raw events
    - record_key_moment: captures significant moments with emotional coloring
    - finish_session: creates SessionExperience and Eigenstate
    """

    def __init__(self, state_store: StateStore):
        """
        Initialize Session Manager.

        Args:
            state_store: Storage for identity, narrative, experience, eigenstate
        """
        self._state_store = state_store
        # Active sessions in memory
        self._active_sessions: dict[UUID, SessionResult] = {}

    def start_session(self, agent_id: UUID) -> SessionContext:
        """
        Start a new session with personality context.

        Loads:
        1. Current identity
        2. Current narrative
        3. Emotional baseline from identity
        4. Last eigenstate (if exists)
        5. Recent reflections summary (placeholder for now)

        Args:
            agent_id: UUID of the agent

        Returns:
            SessionContext: Context for this session

        Raises:
            ValueError: If identity or narrative not found
        """
        # Load identity
        identity = self._state_store.load_identity(agent_id)
        if identity is None:
            raise ValueError(f"Identity not found for agent {agent_id}")

        # Load narrative
        narrative = self._state_store.load_narrative(identity.id)
        if narrative is None:
            raise ValueError(f"Narrative not found for identity {identity.id}")

        # Load last eigenstate (optional)
        last_eigenstate = self._state_store.load_latest_eigenstate()

        # Create session context
        context = SessionContext(
            identity=identity,
            narrative=narrative,
            emotional_baseline=identity.emotional_baseline,
            last_eigenstate=last_eigenstate,
            recent_reflections_summary="",  # Placeholder for future
        )

        # Initialize session result tracking
        self._active_sessions[context.session_id] = SessionResult(
            session_id=context.session_id,
            started_at=context.started_at,
            events=[],
            key_moments=[],
        )

        return context

    def record_event(self, session_id: UUID, event: SessionEvent) -> None:
        """
        Record an event from lower agent during session.

        Not all events become key moments - this is just tracking what happened.

        Args:
            session_id: UUID of the session
            event: Event to record

        Raises:
            SessionNotFoundError: If session not found
            SessionAlreadyFinishedError: If session already finished
        """
        session_result = self._active_sessions.get(session_id)
        if session_result is None:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Ensure event belongs to this session
        event.session_id = session_id

        session_result.events.append(event)

    def record_key_moment(self, session_id: UUID, moment: KeyMomentInput) -> None:
        """
        Record a key moment with emotional coloring.

        This is the CRITICAL method - where first-hand experience is captured.

        IMPORTANT:
        - Emotional coloring MUST be present (valence, intensity, depth)
        - If coloring couldn't be captured fully, set incomplete_coloring=True
        - This method does NOT guess emotions - it records what was experienced

        Args:
            session_id: UUID of the session
            moment: Key moment input with mandatory emotional coloring

        Raises:
            SessionNotFoundError: If session not found
            SessionAlreadyFinishedError: If session already finished
            ValueError: If emotional coloring is missing without incomplete_coloring flag
        """
        session_result = self._active_sessions.get(session_id)
        if session_result is None:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Validate emotional coloring
        # If valence and intensity are both zero, require incomplete_coloring flag
        if (
            moment.emotional_valence == 0.0
            and moment.emotional_intensity == 0.0
            and not moment.incomplete_coloring
        ):
            raise ValueError(
                "Key moment has no emotional coloring. "
                "If coloring couldn't be captured, set incomplete_coloring=True"
            )

        # Convert input to KeyMoment
        key_moment = moment.to_key_moment()

        # Track incomplete coloring at session level
        if moment.incomplete_coloring:
            session_result.incomplete_coloring = True

        session_result.key_moments.append(key_moment)

    def finish_session(
        self,
        session_id: UUID,
        overall_emotional_tone: float = 0.0,
        key_insight: str = "",
        alignment_check: bool = True,
        alignment_notes: str = "",
    ) -> SessionResult:
        """
        Finish session and create SessionExperience + Eigenstate.

        This method:
        1. Validates session can be finished (has key moments)
        2. Creates SessionExperience from key moments
        3. Stores experience in Experience Store
        4. Creates and stores Eigenstate
        5. Removes session from active tracking
        6. Returns SessionResult

        Args:
            session_id: UUID of the session
            overall_emotional_tone: Overall emotional tone (-1.0 to 1.0)
            key_insight: Main insight from session
            alignment_check: Did experience match identity?
            alignment_notes: Notes about alignment or drift

        Returns:
            SessionResult: Complete session result with experience and eigenstate

        Raises:
            SessionNotFoundError: If session not found
            ValueError: If session has no key moments
        """
        session_result = self._active_sessions.get(session_id)
        if session_result is None:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Validate session has key moments
        if not session_result.key_moments:
            raise ValueError("Cannot finish session without key moments")

        # Validate emotional tone range
        if not -1.0 <= overall_emotional_tone <= 1.0:
            raise ValueError("overall_emotional_tone must be between -1.0 and 1.0")

        # Update session result
        session_result.finished_at = datetime.now(UTC)
        session_result.overall_emotional_tone = overall_emotional_tone
        session_result.key_insight = key_insight
        session_result.alignment_check = alignment_check
        session_result.alignment_notes = alignment_notes

        # Create SessionExperience
        experience = SessionExperience(
            session_id=session_id,
            timestamp=session_result.finished_at,
            key_moments=session_result.key_moments,
            recorded_by="session_manager",  # Guarantees first-hand
            importance=0.5,  # Default importance
            salience=0.5,  # Default salience
            incomplete_coloring=session_result.incomplete_coloring,
        )

        # Store experience
        experience_record = ExperienceRecord(experience=experience)
        self._state_store.create_experience(experience_record)

        # Create Eigenstate
        eigenstate = self._create_eigenstate(session_result)
        session_result.eigenstate = eigenstate

        # Store eigenstate
        self._state_store.save_eigenstate(eigenstate)

        # Remove from active sessions
        del self._active_sessions[session_id]

        return session_result

    def _create_eigenstate(self, session_result: SessionResult) -> Eigenstate:
        """
        Create eigenstate from session result.

        Args:
            session_result: Session result to create eigenstate from

        Returns:
            Eigenstate: Created eigenstate
        """
        # Calculate average emotional intensity from key moments
        if session_result.key_moments:
            avg_intensity = sum(
                m.how_i_felt.emotional_intensity for m in session_result.key_moments
            ) / len(session_result.key_moments)
        else:
            avg_intensity = 0.5

        # Extract open threads from events
        open_threads = [
            e.description
            for e in session_result.events
            if e.event_type in ("unfinished", "open_question", "pending")
        ]

        # Extract dominant themes from key moments
        dominant_themes = list(
            set(value for moment in session_result.key_moments for value in moment.values_touched)
        )

        # Extract unresolved tensions
        unresolved_tensions = list(
            set(
                principle
                for moment in session_result.key_moments
                for principle in moment.principles_questioned
            )
        )

        return Eigenstate(
            session_id=session_result.session_id,
            timestamp=session_result.finished_at,
            emotional_tone=session_result.overall_emotional_tone,
            emotional_intensity=avg_intensity,
            cognitive_load=0.5,  # Could be calculated from event complexity
            open_threads=open_threads[:5],  # Limit to top 5
            dominant_themes=dominant_themes[:5],  # Limit to top 5
            unresolved_tensions=unresolved_tensions[:5],  # Limit to top 5
            session_summary=session_result.key_insight or "Session completed",
            key_insight=session_result.key_insight,
        )

    def get_active_session(self, session_id: UUID) -> SessionResult | None:
        """
        Get active session by ID.

        Args:
            session_id: UUID of the session

        Returns:
            SessionResult | None: Session result if active, None otherwise
        """
        return self._active_sessions.get(session_id)

    def list_active_sessions(self) -> list[UUID]:
        """
        List all active session IDs.

        Returns:
            list[UUID]: List of active session IDs
        """
        return list(self._active_sessions.keys())
