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

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, cast
from uuid import UUID, uuid5

from atman.core.clock_impl import SystemClock
from atman.core.exceptions import (
    SessionAlreadyFinishedError,
    SessionNotFoundError,
    TooManyActiveSessionsError,
)
from atman.core.models import (
    ActiveSessionSummary,
    Eigenstate,
    ExperienceRecord,
    KeyMoment,
    KeyMomentInput,
    Session,
    SessionContext,
    SessionEvent,
    SessionExperience,
    SessionResult,
)
from atman.core.ports.affect import AffectPort
from atman.core.ports.clock import ClockPort
from atman.core.ports.state_store import StateStore

if TYPE_CHECKING:
    # Legacy kwargs (affect_workspace + affect_config) still construct an
    # AffectDetector internally for backwards compatibility; the new
    # canonical wiring is to pass an already-built ``AffectPort`` via the
    # ``affect`` kwarg from the composition root.
    from atman.affect.detector import AffectDetectorConfig
    from atman.core.ports.divergence_events import DivergenceEventStore
    from atman.core.ports.linguistic import LinguisticAnalyzer
    from atman.core.services.divergence_detector import DivergenceDetector
    from atman.core.services.inline_validator import InlineValidator
    from atman.core.services.post_write_scheduler import PostWriteScheduler

# Cap for eigenstate list fields; order is insertion-derived until salience ranking exists.
MAX_EIGENSTATE_ITEMS = 5

# Namespace for deterministic session-derived IDs used by external callers.
_SESSION_EXPERIENCE_ID_NS = UUID("018e5a2b-7c3d-7b2a-9f01-2a3b4c5d6e7f")

_NARRATIVE_SAVE_RETRIES = 5

_LOG = logging.getLogger(__name__)

from atman.core.session_log import slog as _slog  # noqa: E402


@dataclass(frozen=True, slots=True)
class _FinishJournalMetadata:
    """Finish-time fields needed to rebuild downstream artifacts after a crash."""

    finished_at: datetime | None = None
    overall_emotional_tone: float = 0.0
    key_insight: str = ""
    alignment_check: bool = True
    alignment_notes: str = ""
    incomplete_coloring: bool | None = None


def _session_finish_marker(session_id: UUID) -> str:
    """Hidden marker so a successful narrative write is not duplicated on finish retry."""
    return f"<!-- atman:session-finish:{session_id} -->"


def deterministic_session_experience_id(session_id: UUID) -> UUID:
    """Return a deterministic UUID derived from session_id (used by external callers)."""
    return uuid5(_SESSION_EXPERIENCE_ID_NS, str(session_id))


def _experience_store_available(state_store: StateStore) -> bool:
    """True when the store implements legacy ExperienceRecord persistence."""
    try:
        state_store.get_experience(deterministic_session_experience_id(UUID(int=0)))
    except NotImplementedError:
        return False
    return True


class SessionManager:
    """
    Session runtime that experiences sessions in real-time.

    Manages the complete session lifecycle:
    - start_session: loads personality context
    - record_event: tracks raw events and schedules AffectDetector (when configured)
    - append_key_moment / append_key_moment_input: programmatic key moments
    - finish_session: persists KeyMoments + Eigenstate + updates Narrative
    """

    def __init__(
        self,
        state_store: StateStore,
        max_active_sessions: int | None = None,
        clock: ClockPort | None = None,
        affect: AffectPort | None = None,
        affect_workspace: Path | None = None,
        affect_config: AffectDetectorConfig | None = None,
        workspace: Path | None = None,
        post_write_scheduler: PostWriteScheduler | None = None,
        linguistic_analyzer: LinguisticAnalyzer | None = None,
        divergence_detector: DivergenceDetector | None = None,
        divergence_event_store: DivergenceEventStore | None = None,
        inline_validator: InlineValidator | None = None,
    ) -> None:
        """
        Initialize Session Manager.

        Args:
            state_store: Storage for identity, narrative, experience, eigenstate
            max_active_sessions: If set, ``start_session`` raises when this many sessions are active.
            clock: Clock for reproducible timestamps (defaults to SystemClock)
            affect: Optional :class:`AffectPort` implementation. When set, takes
                precedence over the legacy ``affect_workspace`` / ``affect_config``
                kwargs and avoids constructing AffectDetector from Core.
            affect_workspace: Legacy — optional workspace directory for affect
                baseline JSONL. Kept for back-compat; new callers should pass
                a pre-built ``affect`` instead.
            affect_config: Legacy — optional :class:`AffectDetectorConfig`
                (requires ``affect_workspace``). Same back-compat note as above.
            workspace: Optional workspace directory for session journals
            post_write_scheduler: Optional :class:`PostWriteScheduler` — when
                provided, every persisted ``KeyMoment`` enqueues the configured
                async enrichment jobs (mREBEL relation extraction, deeper
                linguistic analysis). Failures inside the scheduler are
                logged but never propagated, so the hot path stays unblocked.
        """
        self._state_store = state_store
        self._max_active_sessions = max_active_sessions
        self._clock = clock or SystemClock()
        self._active_sessions: dict[UUID, SessionResult] = {}
        self._journal_locks: dict[UUID, IO[str]] = {}
        self._lock = threading.Lock()
        self._workspace = workspace
        self._post_write_scheduler = post_write_scheduler
        self._inline_validator = inline_validator
        # HLE-56: pending fire-and-forget AffectDetector tasks per session.
        # ``finish_session`` drains these before flipping ``is_finished`` so
        # that key moments produced by the affect hook are not silently
        # dropped by ``append_key_moment``'s SessionAlreadyFinishedError.
        self._pending_affect_tasks: dict[UUID, list[asyncio.Task[None]]] = {}

        self._affect: AffectPort | None = affect
        if self._affect is None and affect_workspace is not None and affect_config is not None:
            # Legacy path: build the detector here so existing callers keep
            # working. Lazy import keeps Core free of a static dependency on
            # the concrete adapter.
            from atman.affect.detector import AffectDetector

            self._affect = AffectDetector(
                affect_config,
                workspace=affect_workspace,
                append_moment=self.append_key_moment,
                linguistic_analyzer=linguistic_analyzer,
                divergence_detector=divergence_detector,
                divergence_event_store=divergence_event_store,
            )

    @property
    def affect_detector(self) -> AffectPort | None:
        """Optional behavioural detector wired to :meth:`append_key_moment`."""
        return self._affect

    def attach_affect(self, affect: AffectPort) -> None:
        """Wire an :class:`AffectPort` after construction.

        Useful when the affect implementation needs a reference to
        :meth:`append_key_moment` (it does, via its ``append_moment``
        callback) and would otherwise create a circular constructor
        dependency. Idempotent: a second call replaces the previous port.
        """
        self._affect = affect

    def _journal_path(self, agent_id: UUID, session_id: UUID) -> Path | None:
        """Return journal path for a session, or None if workspace not configured."""
        if self._workspace is None:
            return None
        sessions_dir = self._workspace / str(agent_id) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir / f"active_{session_id}.jsonl"

    def _journal_lock_path(self, agent_id: UUID, session_id: UUID) -> Path | None:
        """Return lock path for an active session journal."""
        journal_path = self._journal_path(agent_id, session_id)
        if journal_path is None:
            return None
        return journal_path.with_suffix(f"{journal_path.suffix}.lock")

    def _try_lock_journal(self, agent_id: UUID, session_id: UUID) -> IO[str] | None:
        """Try to take the inter-process lock for a session journal."""
        lock_path = self._journal_lock_path(agent_id, session_id)
        if lock_path is None:
            return None

        lock_file: IO[str] | None = None
        try:
            import fcntl

            lock_file = lock_path.open("a+", encoding="utf-8")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except BlockingIOError:
            if lock_file is not None:
                lock_file.close()
            return None
        except (ImportError, OSError) as exc:
            _LOG.warning("Failed to lock journal for session %s: %s", session_id, exc)
            return None

    def _release_journal_file(self, lock_file: IO[str], *, unlink: bool) -> None:
        """Release a journal lock file."""
        lock_path = Path(lock_file.name)
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError) as exc:
            _LOG.warning("Failed to unlock journal %s: %s", lock_path, exc)
        finally:
            lock_file.close()
            if unlink:
                lock_path.unlink(missing_ok=True)

    def _journal_locked_elsewhere(self, agent_id: UUID, session_id: UUID) -> bool:
        """Return True when another live process owns this session journal."""
        lock_file = self._try_lock_journal(agent_id, session_id)
        if lock_file is None:
            return self._workspace is not None
        self._release_journal_file(lock_file, unlink=False)
        return False

    def _journal_accumulate_entry(
        self,
        entry: dict[str, object],
        *,
        key_moment_ids: list[UUID],
        journaled_moments: dict[UUID, KeyMoment],
        fact_refs_set: set[UUID],
    ) -> _FinishJournalMetadata | None:
        """Apply one decoded journal entry to accumulators; return finish payload when applicable."""
        kind = entry.get("type")
        if kind == "key_moment":
            moment_id = UUID(str(entry["moment_id"]))
            key_moment_ids.append(moment_id)
            moment_data = entry.get("moment")
            if isinstance(moment_data, dict):
                journaled_moments[moment_id] = KeyMoment.model_validate(moment_data)
            fact_refs = entry.get("fact_refs", [])
            if isinstance(fact_refs, list):
                for fact_id_str in fact_refs:
                    fact_refs_set.add(UUID(str(fact_id_str)))
            return None
        if kind == "facts_read":
            fact_ids = entry.get("fact_ids", [])
            if isinstance(fact_ids, list):
                for fact_id_str in fact_ids:
                    fact_refs_set.add(UUID(str(fact_id_str)))
            return None
        if kind == "finish_session":
            return self._finish_metadata_from_journal(entry)
        return None

    def _write_journal_entry(
        self, agent_id: UUID, session_id: UUID, entry: dict[str, object]
    ) -> None:
        """Append journal entry to session journal (if workspace configured)."""
        journal_path = self._journal_path(agent_id, session_id)
        if journal_path is None:
            return
        try:
            with journal_path.open("a", encoding="utf-8") as f:
                json.dump(entry, f, default=str)
                f.write("\n")
        except (OSError, ValueError) as exc:
            _LOG.warning("Failed to write journal entry for session %s: %s", session_id, exc)

    # PLAYBOOK-START
    # id: self-contained-recovery-journals
    # category: design-patterns
    # title: Self-Contained Recovery Journals for In-Flight State
    # status: draft
    # since: 2026-05-12
    #
    # Pattern: when journaling in-flight state for crash recovery, keep an
    # advisory lock while the owner is live and include enough payload to
    # reconstruct the referenced records, not just their IDs. Recovery must
    # refuse to delete the journal if it cannot rebuild every referenced row.
    #
    # Why generalizable: any write-behind or finish-time persistence flow can crash
    # between "record exists in memory" and "record exists in durable storage".
    # ID-only journals create dangling references; lock-free recovery can steal
    # live sessions from another process. Self-contained, locked journal entries
    # preserve the last recovery source and distinguish crashed from active work.
    #
    # Trade-offs: journal entries are larger and may duplicate data already stored
    # on the happy path, but the duplication is bounded and only used for recovery.
    # PLAYBOOK-END
    def _load_journal_payload(
        self, journal_file: Path
    ) -> tuple[list[UUID], dict[UUID, KeyMoment], set[UUID], _FinishJournalMetadata | None]:
        """Load recoverable key moments and fact references from a session journal."""
        key_moment_ids: list[UUID] = []
        journaled_moments: dict[UUID, KeyMoment] = {}
        fact_refs_set: set[UUID] = set()
        finish_metadata: _FinishJournalMetadata | None = None

        with journal_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    fm = self._journal_accumulate_entry(
                        entry,
                        key_moment_ids=key_moment_ids,
                        journaled_moments=journaled_moments,
                        fact_refs_set=fact_refs_set,
                    )
                    if fm is not None:
                        finish_metadata = fm
                except (KeyError, ValueError) as exc:
                    _LOG.warning("Skipping malformed journal line in %s: %s", journal_file, exc)
                    continue

        return key_moment_ids, journaled_moments, fact_refs_set, finish_metadata

    def _finish_metadata_from_journal(self, entry: dict[str, object]) -> _FinishJournalMetadata:
        """Parse finish metadata conservatively; malformed fields fall back to safe defaults."""
        finished_at_raw = entry.get("finished_at")
        finished_at: datetime | None = None
        if isinstance(finished_at_raw, str):
            try:
                finished_at = datetime.fromisoformat(finished_at_raw)
            except ValueError:
                finished_at = None

        tone_raw = entry.get("overall_emotional_tone")
        overall_emotional_tone = float(tone_raw) if isinstance(tone_raw, int | float) else 0.0
        if not -1.0 <= overall_emotional_tone <= 1.0:
            overall_emotional_tone = 0.0

        key_insight_raw = entry.get("key_insight")
        alignment_check_raw = entry.get("alignment_check")
        alignment_notes_raw = entry.get("alignment_notes")
        incomplete_coloring_raw = entry.get("incomplete_coloring")

        return _FinishJournalMetadata(
            finished_at=finished_at,
            overall_emotional_tone=overall_emotional_tone,
            key_insight=key_insight_raw if isinstance(key_insight_raw, str) else "",
            alignment_check=alignment_check_raw if isinstance(alignment_check_raw, bool) else True,
            alignment_notes=alignment_notes_raw if isinstance(alignment_notes_raw, str) else "",
            incomplete_coloring=incomplete_coloring_raw
            if isinstance(incomplete_coloring_raw, bool)
            else None,
        )

    def _load_recovery_key_moments(
        self,
        session_id: UUID,
        key_moment_ids: list[UUID],
        journaled_moments: dict[UUID, KeyMoment],
    ) -> list[KeyMoment] | None:
        """Load or restore all key moments needed for session recovery."""
        loaded_moments: list[KeyMoment] = []
        for moment_id in key_moment_ids:
            loaded_moment = self._state_store.get_key_moment(moment_id)
            if loaded_moment is None and moment_id in journaled_moments:
                loaded_moment = journaled_moments[moment_id]
                try:
                    self._state_store.create_key_moment(loaded_moment)
                except ValueError:
                    # Another recovery/finish path stored it first.
                    loaded_moment = self._state_store.get_key_moment(moment_id)
            if loaded_moment is not None:
                loaded_moments.append(loaded_moment)

        if len(loaded_moments) != len(key_moment_ids):
            _LOG.warning(
                "Cannot recover orphaned session %s: %d/%d key moments available; "
                "leaving journal for manual recovery",
                session_id,
                len(loaded_moments),
                len(key_moment_ids),
            )
            return None

        return loaded_moments

    def _finish_artifacts_complete(self, agent_id: UUID, session_id: UUID) -> bool:
        """Return True when all finish-session artifacts already exist."""
        eigenstate = self._state_store.load_latest_eigenstate(
            session_id=session_id,
            identity_id=agent_id,
        )
        if eigenstate is None:
            return False

        narrative = self._state_store.load_narrative(agent_id)
        if narrative is None:
            return False
        if session_id in narrative.finished_session_ids:
            return True
        # Legacy fallback: narratives written before the dedicated tracking
        # field carried a hidden marker inside recent_layer.content. Reflection
        # passes overwrite recent_layer, so this signal is unreliable — kept
        # only to recognise pre-migration data.
        return _session_finish_marker(session_id) in narrative.recent_layer.content

    def _recover_single_orphan_journal(self, agent_id: UUID, journal_file: Path) -> None:
        """Recover one journal file when not active elsewhere; unlink on success."""
        session_id_str = journal_file.stem.replace("active_", "")
        session_id = UUID(session_id_str)

        with self._lock:
            if session_id in self._active_sessions:
                return
            stale_lock = self._journal_locks.pop(session_id, None)
            if stale_lock is not None:
                self._release_journal_file(stale_lock, unlink=False)
        if self._journal_locked_elsewhere(agent_id, session_id):
            _LOG.debug("Skipping live journal locked by another process: %s", session_id)
            return

        (
            key_moment_ids,
            journaled_moments,
            _fact_refs_set,
            _finish_metadata,
        ) = self._load_journal_payload(journal_file)

        if key_moment_ids:
            loaded_moments = self._load_recovery_key_moments(
                session_id,
                key_moment_ids,
                journaled_moments,
            )
            if loaded_moments is None:
                return

            # HLE-57: persist session→moments mapping for reflection engine
            self._state_store.store_key_moments(session_id, loaded_moments)
            _LOG.info(
                "Recovered orphaned session %s with %d key moments",
                session_id,
                len(loaded_moments),
            )

            # HLE-27: schedule post-write enrichment for recovered moments
            for moment in loaded_moments:
                self._schedule_post_write(moment, agent_id)

        journal_file.unlink()

    def _recover_orphaned_sessions(self, agent_id: UUID) -> None:
        """Scan for orphaned session journals and persist their key moments.

        Orphaned journals arise from interrupted sessions that never completed
        finish_session. Each orphan's key moments are stored and the session→moments
        mapping is written so downstream reflection sees the recovered history.
        """
        if self._workspace is None:
            return
        sessions_dir = self._workspace / str(agent_id) / "sessions"
        if not sessions_dir.exists():
            return

        for journal_file in sessions_dir.glob("active_*.jsonl"):
            try:
                self._recover_single_orphan_journal(agent_id, journal_file)
            except Exception as exc:
                _LOG.error("Failed to recover orphaned journal %s: %s", journal_file, exc)
                continue

    def start_session(self, agent_id: UUID) -> SessionContext:
        """
        Start a new session with personality context.

        Loads and creates:
        1. Current identity
        2. Identity snapshot for provenance tracking
        3. Current narrative
        4. Emotional baseline from identity
        5. Last eigenstate (if exists)
        6. Recent reflections summary (placeholder for now)

        Also scans for orphaned session journals (from interrupted sessions)
        and converts them to SessionExperience with close_reason="interrupted".

        The identity snapshot establishes provenance chain: later Reflection/Identity
        can link session experience to the specific identity state that was active
        during the session.

        Args:
            agent_id: UUID of the agent

        Returns:
            SessionContext: Context for this session with identity_snapshot_id

        Raises:
            ValueError: If identity or narrative not found
            TooManyActiveSessionsError: If active session limit is exceeded
        """
        # Recover orphaned sessions before starting new one
        self._recover_orphaned_sessions(agent_id)

        identity = self._state_store.load_identity(agent_id)
        if identity is None:
            raise ValueError(f"Identity not found for agent {agent_id}")

        narrative = self._state_store.load_narrative(identity.id)
        if narrative is None:
            raise ValueError(f"Narrative not found for identity {identity.id}")

        last_eigenstate = self._state_store.load_latest_eigenstate(identity_id=identity.id)

        from atman.core.models.identity import IdentitySnapshot

        context = SessionContext(
            identity=identity,
            identity_snapshot_id=None,
            narrative=narrative,
            emotional_baseline=identity.emotional_baseline,
            last_eigenstate=last_eigenstate,
            recent_reflections_summary="",  # Placeholder for future
            started_at=self._clock.now(),
        )

        with self._lock:
            if self._max_active_sessions is not None and len(self._active_sessions) >= (
                self._max_active_sessions
            ):
                raise TooManyActiveSessionsError(
                    f"Active session limit ({self._max_active_sessions}) reached; "
                    "finish a session before starting another."
                )
            snapshot = IdentitySnapshot(
                identity_id=identity.id,
                description="Session start snapshot",
                identity_snapshot=identity,
                change_summary="Snapshot for session lifecycle tracking",
            )
            stored_snapshot = self._state_store.create_identity_snapshot(snapshot)
            context = context.model_copy(update={"identity_snapshot_id": stored_snapshot.id})
            self._active_sessions[context.session_id] = SessionResult(
                session_id=context.session_id,
                started_at=context.started_at,
                events=[],
                key_moments=[],
                identity_snapshot_id=stored_snapshot.id,
                identity_id=identity.id,
            )

        # v2: persist Session row so ExperienceViewRepository, decay jobs,
        # and Reflection follow-ups have a canonical session record.
        # The base StateStore port's `create_session` is a no-op default that
        # returns the session unchanged — no exception. Concrete adapters
        # (InMemoryStateStore, FileStateStore, PostgresStateStore) implement
        # real persistence and may raise on genuine failures (DB connection
        # lost, disk full, etc.). If that happens, roll back the in-memory
        # registry entry so the orphan does not count toward
        # max_active_sessions, then re-raise so the caller knows the start
        # failed (the caller never receives the session_id here).
        try:
            self._state_store.create_session(
                Session(
                    id=context.session_id,
                    agent_id=agent_id,
                    started_at=context.started_at,
                    status="active",
                    identity_snapshot_id=stored_snapshot.id,
                )
            )
        except Exception:
            with self._lock:
                self._active_sessions.pop(context.session_id, None)
            raise

        journal_lock = self._try_lock_journal(identity.id, context.session_id)
        if journal_lock is not None:
            with self._lock:
                self._journal_locks[context.session_id] = journal_lock

        _slog(
            "session_started",
            agent_id=str(agent_id),
            session_id=str(context.session_id),
            identity_id=str(identity.id),
            snapshot_id=str(context.identity_snapshot_id),
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
        event_copy = event.model_copy(update={"session_id": session_id})
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None:
                raise SessionNotFoundError(f"Session {session_id} not found")
            if session_result.is_finished:
                raise SessionAlreadyFinishedError(f"Session {session_id} already finished")
            session_result.events.append(event_copy)
        self._schedule_affect_processing(session_id, event_copy)

    def _schedule_affect_processing(self, session_id: UUID, event: SessionEvent) -> None:
        """Schedule :class:`AffectDetector` after ``record_event``.

        With a running asyncio loop the task is created and tracked per session
        so that :meth:`finish_session` can drain it before flipping
        ``is_finished`` (HLE-56) — without the drain, late-firing affect tasks
        race ``finish_session`` and their key moments are dropped by
        ``append_key_moment``'s ``SessionAlreadyFinishedError``.

        Without a loop, ``asyncio.run`` executes the detector synchronously on
        this thread (blocking until scoring finishes) — avoid configuring
        affect for latency-sensitive synchronous ``record_event`` callers
        without an event loop.
        """
        det = self._affect
        if det is None:
            return
        text = event.description
        thinking = event.thinking

        async def _run() -> None:
            try:
                await det.process(text, thinking=thinking, session_id=session_id)
            except Exception:
                _LOG.exception("AffectDetector.process failed for session %s", session_id)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_run())
            with self._lock:
                self._pending_affect_tasks.setdefault(session_id, []).append(task)

            def _discard(t: asyncio.Task[None]) -> None:
                with self._lock:
                    bucket = self._pending_affect_tasks.get(session_id)
                    if bucket is None:
                        return
                    with contextlib.suppress(ValueError):
                        bucket.remove(t)
                    if not bucket:
                        self._pending_affect_tasks.pop(session_id, None)

            task.add_done_callback(_discard)
        except RuntimeError:
            try:
                asyncio.run(_run())
            except RuntimeError:
                _LOG.warning(
                    "AffectDetector could not be scheduled (no usable event loop); session_id=%s",
                    session_id,
                )

    _AFFECT_DRAIN_TIMEOUT_S = 5.0

    async def drain_pending_affect_tasks(self, session_id: UUID) -> None:
        """Async drain — call from :func:`async def` runners BEFORE ``finish_session``.

        HLE-56 (Devin #594): the synchronous drain that runs from inside
        ``finish_session`` cannot ``await`` and therefore busy-polls. When
        ``finish_session`` is invoked on the same event-loop thread that
        owns the affect tasks (the realistic case in
        ``runner.py::async def chat``), the busy-poll deadlocks the loop —
        the very tasks it is waiting on can never run because their loop is
        blocked. The sync path detects this and short-circuits with a
        warning; runners get an effective drain by ``await``-ing this
        coroutine before calling ``finish_session``.

        Times out after ``_AFFECT_DRAIN_TIMEOUT_S`` seconds — affect is a
        best-effort observer, never a blocker for session finalization.
        """
        with self._lock:
            tasks = list(self._pending_affect_tasks.get(session_id, ()))
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self._AFFECT_DRAIN_TIMEOUT_S,
            )
        except TimeoutError:
            pending = sum(1 for t in tasks if not t.done())
            _LOG.warning(
                "AffectDetector async drain timed out for session %s; %d task(s) "
                "still pending — affect-derived key moments from those tasks "
                "may be dropped.",
                session_id,
                pending,
            )

    def _drain_pending_affect_tasks(self, session_id: UUID) -> None:
        """Synchronous drain invoked from :meth:`finish_session`.

        Only effective when ``finish_session`` is called from a thread that
        does **not** own the loop the affect tasks were scheduled on — in
        that case ``task.done()`` flips as the loop on the other thread runs
        the coroutines, and a brief poll suffices.

        When the caller is on the same thread as the running loop (HLE-56
        / Devin #594: the realistic async runner case), busy-polling here
        would deadlock the loop. Detect that situation and short-circuit
        with a debug log — async callers that need an effective drain must
        ``await drain_pending_affect_tasks`` before calling
        ``finish_session``.

        When ``_schedule_affect_processing`` ran via ``asyncio.run`` (no
        loop on the caller's thread, sync execution) there are no tracked
        tasks and this method is a no-op.
        """
        import time as _time

        with self._lock:
            tasks = list(self._pending_affect_tasks.get(session_id, ()))
        if not tasks:
            return

        # If we're on a thread that already owns a running loop, blocking
        # synchronously would deadlock the very loop those tasks need to
        # progress. Skip; async callers can use ``drain_pending_affect_tasks``.
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None:
            _LOG.debug(
                "Skipping synchronous affect drain for session %s — caller is "
                "on the event loop thread (use ``await "
                "drain_pending_affect_tasks(...)`` before finish_session for "
                "an effective drain).",
                session_id,
            )
            return

        deadline = _time.monotonic() + self._AFFECT_DRAIN_TIMEOUT_S
        while not all(t.done() for t in tasks):
            if _time.monotonic() >= deadline:
                pending = sum(1 for t in tasks if not t.done())
                _LOG.warning(
                    "AffectDetector drain timed out for session %s; %d task(s) "
                    "still pending — affect-derived key moments from those "
                    "tasks may be dropped.",
                    session_id,
                    pending,
                )
                return
            _time.sleep(0.01)

    def append_key_moment(self, session_id: UUID, moment: KeyMoment) -> None:
        """
        Append a fully materialised key moment (used by AffectDetector and tests).

        Raises:
            SessionNotFoundError: If session not found
            SessionAlreadyFinishedError: If session already finished
        """
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None:
                raise SessionNotFoundError(f"Session {session_id} not found")
            if session_result.is_finished:
                raise SessionAlreadyFinishedError(f"Session {session_id} already finished")
            session_result.key_moments.append(moment)

            # Get agent_id for journal
            agent_id = session_result.identity_id

        # Write to journal after releasing lock
        if agent_id is not None:
            self._write_journal_entry(
                agent_id,
                session_id,
                {
                    "type": "key_moment",
                    "moment_id": str(moment.id),
                    "timestamp": self._clock.now().isoformat(),
                    "what_happened": moment.what_happened,
                    "moment": moment.model_dump(mode="json"),
                    "fact_refs": [str(fid) for fid in moment.fact_refs],
                },
            )
            # NB: post-write enrichment is intentionally NOT scheduled here.
            # Moments live only in `session_result.key_moments` until
            # `finish_session` persists them to `state_store`. Scheduling now
            # would race with the worker, which calls `state_store.get_key_moment`
            # and would mark the job permanently `skipped` when the lookup
            # returns None. See HLE-27 follow-up — the scheduler now fires
            # from `finish_session` once the moments are durable.

    def append_key_moment_input(self, session_id: UUID, moment: KeyMomentInput) -> None:
        """
        Validate :class:`KeyMomentInput` and append the resulting :class:`KeyMoment`.

        This replaces the removed :meth:`record_key_moment` for programmatic callers.
        """
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None:
                raise SessionNotFoundError(f"Session {session_id} not found")
            if session_result.is_finished:
                raise SessionAlreadyFinishedError(f"Session {session_id} already finished")

            if (
                math.isclose(moment.emotional_valence, 0.0)
                and math.isclose(moment.emotional_intensity, 0.0)
                and not moment.incomplete_coloring
            ):
                raise ValueError(
                    "Key moment has no emotional coloring. "
                    "If coloring couldn't be captured, set incomplete_coloring=True"
                )

            moment_with_time = moment.model_copy(update={"recorded_at": self._clock.now()})
            key_moment = moment_with_time.to_key_moment()
            # Set session_id here so both the journal and any immediate DB write
            # have the correct FK — to_key_moment() leaves it None.
            key_moment.session_id = session_id

            if moment.incomplete_coloring:
                session_result.incomplete_coloring = True

            session_result.key_moments.append(key_moment)

            # Write journal entry (outside lock to avoid blocking)
            agent_id = session_result.identity_id

        # Write to journal after releasing lock
        if agent_id is not None:
            self._write_journal_entry(
                agent_id,
                session_id,
                {
                    "type": "key_moment",
                    "moment_id": str(key_moment.id),
                    "timestamp": self._clock.now().isoformat(),
                    "what_happened": key_moment.what_happened,
                    "moment": key_moment.model_dump(mode="json"),
                    "fact_refs": [str(fid) for fid in key_moment.fact_refs],
                },
            )
            # Write to DB immediately so moments survive a crash before finish_session.
            # store_key_moment is an idempotent upsert — finish_session calling it
            # again is safe. If the DB write fails we log and continue; the journal
            # above is the crash-recovery fallback.
            try:
                self._state_store.store_key_moment(key_moment)
                # Moment is now durable — safe to schedule post-write enrichment.
                self._schedule_post_write(key_moment, agent_id)
            except Exception:
                _LOG.warning(
                    "store_key_moment failed for %s — moment in journal, enrichment deferred",
                    key_moment.id,
                    exc_info=True,
                )
            _slog(
                "key_moment_appended",
                session_id=str(session_id),
                agent_id=str(agent_id),
                moment_id=str(key_moment.id),
                what_happened=key_moment.what_happened[:120],
            )

    def _schedule_post_write(self, moment: KeyMoment, agent_id: UUID) -> None:
        """Fire-and-forget enqueue of post-write enrichment jobs.

        Idempotent via the scheduler's deterministic run_key; safe to call
        repeatedly with the same moment_id. Failures are swallowed and
        logged so an enrichment-pipeline outage cannot break message
        ingestion (HLE-27, plan §17 principle 12).
        """
        if self._post_write_scheduler is None:
            return
        try:
            self._post_write_scheduler.schedule_for_key_moment(moment, agent_id)
        except Exception:
            _LOG.exception("post-write scheduler raised for moment %s — continuing", moment.id)

    def record_key_moment(self, session_id: UUID, moment: KeyMomentInput) -> None:
        """
        Removed — use :class:`~atman.affect.detector.AffectDetector` or
        :meth:`append_key_moment_input`.
        """
        _ = (session_id, moment)
        raise AttributeError(
            "SessionManager.record_key_moment was removed. Use AffectDetector.submit_self_report "
            "for agent-authored key moments, or append_key_moment / append_key_moment_input for "
            "programmatic recording. See atman.affect.AffectDetector."
        )

    def _note_facts_read(self, session_id: UUID, fact_ids: list[UUID]) -> None:
        """
        Note that specific facts were read/accessed during this session.

        This creates back-links from experiences to the facts that shaped them.
        Called automatically when facts are surfaced to the session context.

        Args:
            session_id: UUID of the session
            fact_ids: List of fact IDs that were read

        Raises:
            SessionNotFoundError: If session not found
            SessionAlreadyFinishedError: If session already finished
        """
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None:
                raise SessionNotFoundError(f"Session {session_id} not found")
            if session_result.is_finished:
                raise SessionAlreadyFinishedError(f"Session {session_id} already finished")

            # Store fact IDs in the SessionResult PrivateAttr for aggregation at finish.
            session_result._facts_read.update(fact_ids)

            # Get agent_id for journal
            agent_id = session_result.identity_id

        # Write to journal after releasing lock
        if agent_id is not None and fact_ids:
            self._write_journal_entry(
                agent_id,
                session_id,
                {
                    "type": "facts_read",
                    "timestamp": self._clock.now().isoformat(),
                    "fact_ids": [str(fid) for fid in fact_ids],
                },
            )

    @staticmethod
    def _normalized_close_reason(
        close_reason: str | None,
    ) -> Literal["timeout_sleep", "menu_timeout", "restart", "forced", "interrupted"] | None:
        allowed_close_reasons = (
            "timeout_sleep",
            "menu_timeout",
            "restart",
            "forced",
            "interrupted",
        )
        if close_reason not in allowed_close_reasons:
            return None
        return cast(
            Literal["timeout_sleep", "menu_timeout", "restart", "forced", "interrupted"],
            close_reason,
        )

    def _finish_session_commit_side_effects(
        self,
        session_id: UUID,
        session_result: SessionResult,
        *,
        safe_close_reason: (
            Literal["timeout_sleep", "menu_timeout", "restart", "forced", "interrupted"] | None
        ),
        unexamined_fact_refs: list[UUID],
        key_insight: str,
        restart_reason: str | None,
        user_language: str,
        colored_fact_ids: set[UUID],
    ) -> None:
        """Persist moments, legacy experience row, eigenstate, narrative, and Session row."""
        for moment in session_result.key_moments:
            if moment.session_id is None:
                moment.session_id = session_id
            self._state_store.store_key_moment(moment)

        self._state_store.store_key_moments(session_id, session_result.key_moments)

        if self._post_write_scheduler is not None and session_result.identity_id is not None:
            for moment in session_result.key_moments:
                self._schedule_post_write(moment, session_result.identity_id)

        if self._inline_validator is not None and session_result.identity_id is not None:
            for moment in session_result.key_moments:
                self._inline_validator.check_key_moment(moment, agent_id=session_result.identity_id)

        self._persist_legacy_session_experience(
            session_id,
            session_result,
            safe_close_reason=safe_close_reason,
            unexamined_fact_refs=unexamined_fact_refs,
            key_insight=key_insight,
            restart_reason=restart_reason,
            user_language=user_language,
            colored_fact_ids=colored_fact_ids,
        )

        eigenstate = self._create_eigenstate(session_result)
        session_result.eigenstate = eigenstate
        self._state_store.save_eigenstate(eigenstate)

        self._save_session_narrative_update(session_result)

        existing_session = self._state_store.get_session(session_id)
        if existing_session is None:
            return

        closed_status: Literal["completed", "interrupted"] = (
            "interrupted" if safe_close_reason in {"interrupted", "forced"} else "completed"
        )
        existing_session.status = closed_status
        existing_session.ended_at = session_result.finished_at
        existing_session.close_reason = safe_close_reason  # type: ignore[assignment]
        existing_session.restart_reason = restart_reason or ""
        existing_session.user_language = user_language
        existing_session.unexamined_fact_refs = list(unexamined_fact_refs)
        self._state_store.update_session(existing_session)

    def finish_session(
        self,
        session_id: UUID,
        overall_emotional_tone: float = 0.0,
        key_insight: str = "",
        alignment_check: bool = True,
        alignment_notes: str = "",
        close_reason: str | None = None,
        restart_reason: str | None = None,
        user_language: str = "ru",
    ) -> SessionResult:
        """
        Finish session: persist KeyMoments + Eigenstate + update Narrative.

        This method:
        1. Validates session can be finished (has key moments)
        2. Persists KeyMoments and session→moments mapping
        3. Creates and stores Eigenstate
        4. Updates recent narrative layer with session summary
        5. Removes session from active tracking
        6. Returns SessionResult

        The narrative update ensures the next start_session() loads updated context,
        fulfilling the minimal runtime path requirement: session result → narrative update
        → next session sees updated self-narrative.

        Args:
            session_id: UUID of the session
            overall_emotional_tone: Overall emotional tone (-1.0 to 1.0)
            key_insight: Main insight from session
            alignment_check: Did experience match identity?
            alignment_notes: Notes about alignment or drift
            close_reason: Reason for session closure (timeout_sleep | restart | forced | interrupted)
            restart_reason: Human-readable reason when close_reason=restart
            user_language: Detected language of the user ('ru' or 'en')

        Returns:
            SessionResult: Complete session result with experience and eigenstate

        Raises:
            SessionNotFoundError: If session not found
            SessionAlreadyFinishedError: If session was already finished
            ValueError: If session has no key moments, tone out of range, or alignment contract
        """
        # HLE-56: drain pending AffectDetector tasks BEFORE acquiring the
        # session lock so late-firing affect hooks can still call
        # ``append_key_moment`` (which itself takes the same lock). Without
        # the drain, affect tasks racing ``finish_session`` would see
        # ``is_finished=True`` and raise ``SessionAlreadyFinishedError`` that
        # the fire-and-forget wrapper swallows — silently losing key moments.
        self._drain_pending_affect_tasks(session_id)
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None:
                raise SessionNotFoundError(f"Session {session_id} not found")
            if session_result.is_finished:
                raise SessionAlreadyFinishedError(f"Session {session_id} already finished")
            if not session_result.key_moments:
                raise ValueError("Cannot finish session without key moments")
            if not -1.0 <= overall_emotional_tone <= 1.0:
                raise ValueError("overall_emotional_tone must be between -1.0 and 1.0")
            if not alignment_check and not alignment_notes.strip():
                raise ValueError(
                    "alignment_notes is required when alignment_check=False "
                    "(explain how experience diverged from identity)."
                )
            # Mark as finishing to block concurrent finish_session calls
            # If persistence fails, we rollback this flag in except
            session_result.is_finished = True

        session_result.finished_at = self._clock.now()
        session_result.overall_emotional_tone = overall_emotional_tone
        session_result.key_insight = key_insight
        session_result.alignment_check = alignment_check
        session_result.alignment_notes = alignment_notes
        self._write_finish_journal_entry(session_result)

        # Persist key moments, eigenstate, and update narrative
        # If this fails, rollback is_finished flag to allow retry

        safe_close_reason = self._normalized_close_reason(close_reason)

        # Compute unexamined facts (read but not colored by any key moment).
        _colored_fact_ids: set[UUID] = set()
        for _moment in session_result.key_moments:
            _colored_fact_ids.update(_moment.fact_refs)
        unexamined_fact_refs: list[UUID] = list(session_result._facts_read - _colored_fact_ids)

        try:
            self._finish_session_commit_side_effects(
                session_id,
                session_result,
                safe_close_reason=safe_close_reason,
                unexamined_fact_refs=unexamined_fact_refs,
                key_insight=key_insight,
                restart_reason=restart_reason,
                user_language=user_language,
                colored_fact_ids=_colored_fact_ids,
            )

        except Exception:
            # Rollback is_finished flag to allow retry of finish_session()
            with self._lock:
                session_result.is_finished = False
            raise

        # Remove from active sessions only after successful persistence
        with self._lock:
            self._active_sessions.pop(session_id, None)
            journal_lock = self._journal_locks.pop(session_id, None)
            self._pending_affect_tasks.pop(session_id, None)

        # Delete journal after successful persistence
        if session_result.identity_id is not None:
            journal_path = self._journal_path(session_result.identity_id, session_id)
            if journal_path is not None and journal_path.exists():
                try:
                    journal_path.unlink()
                    _LOG.debug("Deleted journal for completed session %s", session_id)
                except OSError as exc:
                    _LOG.warning("Failed to delete journal for session %s: %s", session_id, exc)

        if journal_lock is not None:
            self._release_journal_file(journal_lock, unlink=True)

        final = session_result.model_copy(deep=True)
        _slog(
            "session_finished",
            session_id=str(session_id),
            agent_id=str(final.identity_id),
            close_reason=safe_close_reason,
            key_moments=len(final.key_moments),
            finished_at=str(final.finished_at),
        )
        return final

    def _persist_legacy_session_experience(
        self,
        session_id: UUID,
        session_result: SessionResult,
        *,
        safe_close_reason: (
            Literal["timeout_sleep", "menu_timeout", "restart", "forced", "interrupted"] | None
        ),
        unexamined_fact_refs: list[UUID],
        key_insight: str,
        restart_reason: str | None,
        user_language: str,
        colored_fact_ids: set[UUID],
    ) -> None:
        """Write SessionExperience for FileStateStore / in-memory adapters.

        PostgresStateStore v2 stores sessions and key moments only; experience
        operations raise NotImplementedError and are skipped here. Reflection on
        Postgres uses Session + KeyMoment via StateStoreSessionRepository, not
        ExperienceRecord rows.
        """
        if not _experience_store_available(self._state_store):
            return

        experience_id = deterministic_session_experience_id(session_id)
        existing_record = self._state_store.get_experience(experience_id)
        if existing_record is not None:
            if existing_record.experience.session_id != session_id:
                raise ValueError(
                    f"Stored experience {experience_id} belongs to another session "
                    f"({existing_record.experience.session_id}); refusing to proceed."
                )
            return

        fact_refs_set: set[UUID] = set(colored_fact_ids)
        fact_refs_set.update(session_result._facts_read)
        key_moment_ids = [m.id for m in session_result.key_moments]

        avg_emotional_intensity = 0.5
        has_profound_moment = False
        if session_result.key_moments:
            from atman.core.models.experience import EmotionalDepth

            avg_emotional_intensity = sum(
                m.how_i_felt.emotional_intensity for m in session_result.key_moments
            ) / len(session_result.key_moments)
            has_profound_moment = any(
                m.how_i_felt.depth == EmotionalDepth.PROFOUND for m in session_result.key_moments
            )

        experience = SessionExperience(
            id=experience_id,
            session_id=session_id,
            timestamp=session_result.finished_at or self._clock.now(),
            key_moment_ids=key_moment_ids,
            unexamined_fact_refs=unexamined_fact_refs,
            recorded_by="session_manager",
            identity_snapshot_id=session_result.identity_snapshot_id,
            importance=0.5,
            salience=0.5,
            avg_emotional_intensity=avg_emotional_intensity,
            has_profound_moment=has_profound_moment,
            incomplete_coloring=session_result.incomplete_coloring,
            fact_refs=list(fact_refs_set),
            close_reason=safe_close_reason,
            agent_recap=key_insight or None,
            restart_reason=restart_reason or "",
            user_language=user_language,
        )
        self._state_store.create_experience(ExperienceRecord(experience=experience))

    def _write_finish_journal_entry(self, session_result: SessionResult) -> None:
        """Persist finish-time metadata before downstream artifacts can partially fail."""
        if session_result.identity_id is None:
            return
        self._write_journal_entry(
            session_result.identity_id,
            session_result.session_id,
            {
                "type": "finish_session",
                "session_id": str(session_result.session_id),
                "finished_at": session_result.finished_at.isoformat(),
                "overall_emotional_tone": session_result.overall_emotional_tone,
                "key_insight": session_result.key_insight,
                "alignment_check": session_result.alignment_check,
                "alignment_notes": session_result.alignment_notes,
                "incomplete_coloring": session_result.incomplete_coloring,
                "identity_snapshot_id": str(session_result.identity_snapshot_id)
                if session_result.identity_snapshot_id is not None
                else None,
            },
        )

    def _save_session_narrative_update(self, session_result: SessionResult) -> None:
        """Append session summary to recent narrative with optimistic concurrency."""
        if session_result.identity_id is None:
            return
        identity_id = session_result.identity_id
        session_id = session_result.session_id
        last_err: BaseException | None = None
        for _ in range(_NARRATIVE_SAVE_RETRIES):
            narrative = self._state_store.load_narrative(identity_id)
            if narrative is None:
                raise RuntimeError(
                    f"Narrative disappeared for identity {identity_id} during finish_session; "
                    "session experience/eigenstate saved but narrative not updated. "
                    "This breaks the session lifecycle contract."
                )
            if session_id in narrative.finished_session_ids:
                return
            # Legacy compatibility: pre-HLE-50 finishes embedded the marker in
            # recent_layer prose. If we see it, treat the session as finished
            # without re-appending the summary.
            if _session_finish_marker(session_id) in narrative.recent_layer.content:
                return
            update_text = self._build_narrative_update(session_result)
            existing_content = narrative.recent_layer.content.strip()
            next_content = (
                f"{existing_content}\n\n{update_text}" if existing_content else update_text
            )
            expected_at = narrative.updated_at
            narrative.update_recent_layer(next_content)
            narrative.mark_session_finished(session_id)
            try:
                self._state_store.save_narrative(
                    narrative,
                    expected_updated_at=expected_at,
                )
                return
            except ValueError as exc:
                msg = str(exc)
                if "updated_at mismatch" in msg:
                    last_err = exc
                    continue
                raise
        raise RuntimeError(
            "Narrative concurrent update: exceeded retries; resolve conflict outside SessionManager."
        ) from last_err

    def _build_narrative_update(self, session_result: SessionResult) -> str:
        """
        Build narrative update from session result.

        Creates a brief summary of the session for the recent narrative layer.
        This ensures the agent's self-narrative reflects recent lived experience.

        Args:
            session_result: Finished session result

        Returns:
            str: Narrative update text
        """
        # Extract key themes from session
        themes = set()
        for moment in session_result.key_moments:
            themes.update(moment.values_touched)

        # Build summary
        parts = []

        if session_result.key_insight:
            parts.append(session_result.key_insight)

        if themes:
            themes_str = ", ".join(sorted(themes)[:5])  # Limit to 5 themes
            parts.append(f"This engaged my values around {themes_str}.")

        if session_result.key_moments:
            num_moments = len(session_result.key_moments)
            tone = session_result.overall_emotional_tone
            tone_desc = "positive" if tone > 0.2 else "negative" if tone < -0.2 else "neutral"
            parts.append(
                f"Experienced {num_moments} significant moment{'s' if num_moments > 1 else ''} "
                f"with an overall {tone_desc} emotional tone."
            )

        if not parts:
            parts.append("Recently completed a session.")

        return " ".join(parts)

    def _create_eigenstate(self, session_result: SessionResult) -> Eigenstate:
        """
        Create eigenstate from session result.

        Open threads, themes, and tensions are truncated to :data:`MAX_EIGENSTATE_ITEMS`
        in encounter order until a salience-based ranking exists.

        Args:
            session_result: Session result to create eigenstate from

        Returns:
            Eigenstate: Created eigenstate
        """
        if session_result.key_moments:
            avg_intensity = sum(
                m.how_i_felt.emotional_intensity for m in session_result.key_moments
            ) / len(session_result.key_moments)
        else:
            avg_intensity = 0.5

        n_events = len(session_result.events)
        cognitive_load = min(1.0, float(n_events) / 10.0)

        open_threads_raw = [
            e.description
            for e in session_result.events
            if e.event_type in ("unfinished", "open_question", "pending")
        ]
        open_threads = list(dict.fromkeys(open_threads_raw))

        dominant_flat = [
            value for moment in session_result.key_moments for value in moment.values_touched
        ]
        dominant_themes = list(dict.fromkeys(dominant_flat))

        tension_flat = [
            principle
            for moment in session_result.key_moments
            for principle in moment.principles_questioned
        ]
        unresolved_tensions = list(dict.fromkeys(tension_flat))

        # Deterministic ID based on session_id for idempotent retry
        eigenstate_id = UUID(int=session_result.session_id.int ^ 0xE16E157A7E)

        return Eigenstate(
            id=eigenstate_id,
            session_id=session_result.session_id,
            identity_id=session_result.identity_id,
            timestamp=session_result.finished_at,
            emotional_tone=session_result.overall_emotional_tone,
            emotional_intensity=avg_intensity,
            cognitive_load=cognitive_load,
            open_threads=open_threads[:MAX_EIGENSTATE_ITEMS],
            dominant_themes=dominant_themes[:MAX_EIGENSTATE_ITEMS],
            unresolved_tensions=unresolved_tensions[:MAX_EIGENSTATE_ITEMS],
            session_summary=session_result.key_insight or "Session completed",
            key_insight=session_result.key_insight,
        )

    def get_active_session(self, session_id: UUID) -> SessionResult | None:
        """
        Get active session by ID.

        Sessions mid-finish (``is_finished``) are not returned as active.

        Args:
            session_id: UUID of the session

        Returns:
            SessionResult | None: Session result if active and not finishing, None otherwise
        """
        with self._lock:
            session_result = self._active_sessions.get(session_id)
            if session_result is None or session_result.is_finished:
                return None
            return session_result.model_copy(deep=True)

    def list_active_sessions(self) -> list[ActiveSessionSummary]:
        """
        List active sessions with counts (avoids N+1 ``get_active_session`` calls).

        Returns:
            Summaries for sessions that are not mid-finish.
        """
        with self._lock:
            return [
                ActiveSessionSummary(
                    session_id=sid,
                    started_at=sr.started_at,
                    events_count=len(sr.events),
                    key_moments_count=len(sr.key_moments),
                )
                for sid, sr in self._active_sessions.items()
                if not sr.is_finished
            ]
