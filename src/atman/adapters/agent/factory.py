"""
Factory for assembling AtmanDeps from a workspace path.

Wires together PostgresStateStore (or FileStateStore fallback),
SessionManager+AffectDetector, IdentityService, MicroReflectionService.

Postgres mode is activated when DATABASE_URL (or ATMAN_DB_URL) is set and
the agent_id is registered in public.agents. Falls back to FileStateStore
so lean dev/test runs without a DB still work.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from atman.adapters.agent.config import AgentConfig
from atman.adapters.agent.deps import AtmanDeps
from atman.adapters.reflection.state_store_session_repository import (
    StateStoreSessionRepository,
)
from atman.adapters.state.postgres_state_store import PostgresStateStore
from atman.adapters.storage.file_state_store import FileStateStore
from atman.adapters.storage.in_memory_pending_human_review import InMemoryPendingHumanReviewInbox
from atman.adapters.storage.in_memory_reflection_request_queue import InMemoryReflectionRequestQueue
from atman.adapters.storage.in_memory_reflection_store import InMemoryReflectionEventStore

try:
    from atman.affect.detector import AffectDetector as _AffectDetector
    from atman.affect.detector import AffectDetectorConfig as _AffectDetectorConfig

    _AFFECT_AVAILABLE = True
except ImportError:
    _AffectDetector = None  # type: ignore[assignment,misc]
    _AffectDetectorConfig = None  # type: ignore[assignment,misc]
    _AFFECT_AVAILABLE = False
from atman.core.models import NarrativeDocument
from atman.core.models.identity import Identity, IdentitySnapshot
from atman.core.models.reflection import (
    HealthCriterionOutput,
    NarrativeUpdateOutput,
    PatternDetectionOutput,
    ReframingNoteOutput,
)
from atman.core.narrative_write_audit import NoOpNarrativeWriteAudit
from atman.core.ports.reflection import NarrativeRepository, ReflectionModel
from atman.core.ports.state_store import StateStore
from atman.core.services.identity_service import IdentityService
from atman.core.services.narrative_revision import NarrativeRevisionService
from atman.core.services.narrative_service import NarrativeService
from atman.core.services.reflection_service import (
    DailyReflectionService,
    DeepReflectionService,
    MicroReflectionService,
)
from atman.core.services.session_manager import SessionManager


class _MockReflectionModel(ReflectionModel):
    def detect_pattern(self, experiences, context, *, key_moments_by_session=None):
        return PatternDetectionOutput()

    def generate_reframing_note(self, experience, context, *, key_moments_by_session=None):
        return ReframingNoteOutput(reflection="", reflection_type="insight")

    def propose_narrative_update(
        self,
        current_narrative,
        recent_experiences,
        reflection_level,
        *,
        key_moments_by_session=None,
    ):
        return NarrativeUpdateOutput(body="")

    def assess_health_criterion(
        self, identity, experiences, criterion, *, key_moments_by_session=None
    ):
        return HealthCriterionOutput(score=0.5, evidence=[], concerns=[])


class _NarrativeAdapter(NarrativeRepository):
    def __init__(self, store: StateStore, agent_id: UUID):
        self._s = store
        self._agent_id = agent_id

    def get_current(self) -> NarrativeDocument | None:
        return self._s.load_narrative(self._agent_id)

    def get_history(self) -> list[NarrativeDocument]:
        return []

    def update(self, narrative: NarrativeDocument, *, expected_updated_at=None) -> None:
        self._s.save_narrative(narrative, expected_updated_at=expected_updated_at)

    def save(self, narrative: NarrativeDocument) -> NarrativeDocument:
        return self._s.save_narrative(narrative)


def _build_state_store(
    workspace: Path,
    agent_id: UUID,
) -> FileStateStore | PostgresStateStore:
    """Return PostgresStateStore when DATABASE_URL is set and agent is registered.

    Falls back to FileStateStore so zero-config / CI runs still work.
    """
    db_url = os.environ.get("ATMAN_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        return FileStateStore(workspace=workspace)
    try:
        import psycopg as _pg

        with _pg.connect(db_url) as _conn:
            row = _conn.execute(
                "SELECT serial_id FROM public.agents WHERE id = %s", [agent_id]
            ).fetchone()
        if row is None:
            import logging as _log

            _log.getLogger(__name__).warning(
                "agent %s not in public.agents — falling back to FileStateStore", agent_id
            )
            return FileStateStore(workspace=workspace)
        serial_id = int(row[0])
        return PostgresStateStore(db_url=db_url, serial_id=serial_id)
    except Exception:
        import logging as _log

        _log.getLogger(__name__).warning(
            "PostgresStateStore unavailable — falling back to FileStateStore", exc_info=True
        )
        return FileStateStore(workspace=workspace)


def build_deps(
    workspace: Path,
    agent_id: UUID,
    config: AgentConfig | None = None,
) -> tuple[AtmanDeps, SessionManager, FileStateStore | PostgresStateStore]:
    """Assemble all services and return AtmanDeps ready for a session."""
    if config is None:
        config = AgentConfig()

    # Initialize Sentry once at the composition root if SENTRY_DSN is configured.
    # No-op when the env var is absent — all observability calls degrade gracefully.
    from atman.adapters.observability.sentry import init_sentry_from_env, set_agent_scope

    if init_sentry_from_env():
        set_agent_scope(str(agent_id))

    workspace.mkdir(parents=True, exist_ok=True)
    state_store = _build_state_store(workspace, agent_id)
    identity_service = IdentityService(state_store)
    narrative_service = NarrativeService(state_store)

    identity = state_store.load_identity(agent_id)
    if identity is None:
        identity = identity_service.bootstrap_identity(agent_id)
    if state_store.load_narrative(identity.id) is None:
        narrative_service.create_narrative(identity)

    # Maintenance queue + post-write scheduler (HLE-27): enqueue mREBEL +
    # lingvo enrichment jobs after every KeyMoment write.
    #
    # Use PostgresMaintenanceQueue when DATABASE_URL is set and the state
    # store is Postgres — jobs survive process restarts. Falls back to the
    # in-memory variant for zero-config / CI runs.
    from atman.core.services.post_write_scheduler import PostWriteScheduler

    _mq_pg_url = os.environ.get("ATMAN_DB_URL") or os.environ.get("DATABASE_URL")
    if _mq_pg_url and isinstance(state_store, PostgresStateStore):
        try:
            from atman.adapters.maintenance.postgres_queue import PostgresMaintenanceQueue

            maintenance_queue = PostgresMaintenanceQueue(db_url=_mq_pg_url)
        except Exception:
            import logging as _mq_log

            _mq_log.getLogger(__name__).warning(
                "PostgresMaintenanceQueue unavailable — falling back to in-memory", exc_info=True
            )
            from atman.adapters.maintenance.in_memory_queue import InMemoryMaintenanceQueue

            maintenance_queue = InMemoryMaintenanceQueue()
    else:
        from atman.adapters.maintenance.in_memory_queue import InMemoryMaintenanceQueue

        maintenance_queue = InMemoryMaintenanceQueue()
    post_write_scheduler = PostWriteScheduler(maintenance_queue)

    # HLE-29: divergence pipeline. The detector turns LinguisticAnalysis into
    # DivergenceEvent rows; the store persists them so R6 DivergenceAggregator
    # (Daily reflection) can read populated history later.
    #
    # Analyzer selection (Devin Review ANALYSIS_0002, PR #592):
    # * When the `linguistic` extra is installed AND ATMAN_LINGUISTIC_ENABLED=true,
    #   instantiate the real GLiNER+MiniLM analyzer. It lazy-loads models on
    #   first call so import is cheap.
    # * Otherwise the NoOp analyzer keeps the pipeline alive but emits no
    #   divergence signals — that is the correct dev-mode behaviour.
    from atman.adapters.linguistic.noop_adapter import NoOpLinguisticAnalyzer
    from atman.adapters.memory.in_memory_divergence_events import (
        InMemoryDivergenceEventStore,
    )
    from atman.core.ports.linguistic import LinguisticAnalyzer as _LinguisticAnalyzer
    from atman.core.services.divergence_detector import DivergenceDetector

    _linguistic_enabled = os.getenv("ATMAN_LINGUISTIC_ENABLED", "false").lower() == "true"
    _affect_linguistic: _LinguisticAnalyzer = NoOpLinguisticAnalyzer()
    if _linguistic_enabled:
        try:
            from atman.adapters.linguistic.gliner_minilm_adapter import (  # type: ignore[import-not-found]
                _GLINER_AVAILABLE,
                _TRANSFORMERS_AVAILABLE,
                GLiNERPlusMiniLMAdapter,
            )

            if _GLINER_AVAILABLE and _TRANSFORMERS_AVAILABLE:
                _affect_linguistic = GLiNERPlusMiniLMAdapter()
        except Exception:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Falling back to NoOpLinguisticAnalyzer — GLiNER+MiniLM adapter unavailable",
                exc_info=True,
            )
    _divergence_detector = DivergenceDetector(agent_id)
    _divergence_event_store = InMemoryDivergenceEventStore()

    # HLE-31 / HLE-32: shared MemoryGuardian + InlineValidator so writes
    # surface lightweight findings within milliseconds. Both Level-C scans
    # (HLE-31, scheduled) and the inline checks (HLE-32, post-write) feed
    # the same finding store so consumers see a unified validation_findings
    # stream.
    #
    # IMPORTANT (Devin Review #599): this default wire-up only feeds the
    # guardian a ``state_store`` and ``divergence_event_store``. The Level-B
    # batch scans (``scan_orphan_entities``, ``scan_merge_candidates``,
    # ``scan_embedding_gaps``) need an ``entity_registry`` / ``factual_memory``
    # and silently return ``[]`` here. cli_maintenance / cron workers that
    # want those signals should construct their own guardian with the full
    # dep set; the inline + Level-C paths are intentionally lighter.
    from atman.adapters.memory.in_memory_memory_guardian import InMemoryMemoryGuardian
    from atman.core.services.inline_validator import InlineValidator

    _memory_guardian = InMemoryMemoryGuardian(
        state_store=state_store,
        divergence_event_store=_divergence_event_store,
    )
    _inline_validator = InlineValidator(_memory_guardian)

    # HLE-33: AmbientMemoryService — entity-anchor parallel RAG. The
    # ``EntityRegistry`` is constructed once at the composition root and
    # exposed on ``AtmanDeps.entity_registry`` so write paths (live
    # session, mREBEL post-write enrichment, future fact-ingest hooks)
    # share the same instance with ``AmbientMemoryService.compose_injection``.
    # Without that sharing the ambient pipeline reads from a brand-new
    # empty registry and silently returns nothing — see Devin Review #600
    # ANALYSIS for the trace.
    #
    # In the in-memory default build the registry starts empty. Real
    # entity population requires either the Postgres adapters (which
    # back it via ``agent_N.entities``) or an explicit ``resolve_or_create``
    # call from the live user-message path. The service itself is
    # already wired through ``AtmanDeps.ambient_memory`` and will pick
    # up entities the moment they land in the shared registry.
    from atman.adapters.memory.in_memory_entity_registry import (
        InMemoryEntityRegistry as _AmbientRegistry,
    )
    from atman.core.services.ambient_memory_service import AmbientMemoryService as _Ambient

    _entity_registry: object = _AmbientRegistry()
    _entity_stance_store = None
    _pg_url = os.environ.get("ATMAN_DB_URL") or os.environ.get("DATABASE_URL")
    if _pg_url and isinstance(state_store, PostgresStateStore):
        try:
            from atman.adapters.memory.postgres_entity_registry import PostgresEntityRegistry
            from atman.adapters.memory.postgres_entity_stance import PostgresEntityStanceStore

            _entity_registry = PostgresEntityRegistry(db_url=_pg_url)
            _entity_stance_store = PostgresEntityStanceStore(db_url=_pg_url)
        except Exception:
            import logging as _log

            _log.getLogger(__name__).warning(
                "PostgresEntityRegistry/Stance unavailable — using in-memory", exc_info=True
            )

    # SalienceDecay — single-pass SQL batch UPDATE when Postgres is available,
    # else Python-loop InMemory fallback.
    _salience_decay = None
    if isinstance(state_store, PostgresStateStore):
        try:
            from atman.adapters.state.postgres_salience_decay import PostgresSalienceDecayService

            _salience_decay = PostgresSalienceDecayService(state_store)
        except Exception:
            import logging as _log

            _log.getLogger(__name__).warning(
                "PostgresSalienceDecayService unavailable — using in-memory", exc_info=True
            )
    if _salience_decay is None:
        from atman.core.services.salience_decay_service import InMemorySalienceDecayService

        _salience_decay = InMemorySalienceDecayService(state_store)

    # factual_memory and ambient_memory are built after the linguistic block
    # so that _factual_memory is available when constructing AmbientMemoryService.
    _factual_memory = None

    # HLE-52: build the affect adapter here (composition root) and inject via
    # AffectPort so SessionManager never imports the concrete implementation.
    session_manager = SessionManager(
        state_store,
        workspace=workspace,
        post_write_scheduler=post_write_scheduler,
        inline_validator=_inline_validator,
    )
    if _AFFECT_AVAILABLE:
        assert _AffectDetector is not None and _AffectDetectorConfig is not None
        session_manager.attach_affect(
            _AffectDetector(
                _AffectDetectorConfig(),
                workspace=workspace,
                append_moment=session_manager.append_key_moment,
                linguistic_analyzer=_affect_linguistic,
                divergence_detector=_divergence_detector,
                divergence_event_store=_divergence_event_store,
            )
        )

    # Use a real LLM for narrative revision when ATMAN_LLM_BASE_URL is set.
    # Falls back to _MockReflectionModel so lean dev/test runs without a
    # running LLM still work (narrative won't be updated but nothing crashes).
    _narrative_reflection_model: ReflectionModel
    _atman_llm_url = os.getenv("ATMAN_LLM_BASE_URL", "")
    if _atman_llm_url:
        try:
            from atman.adapters.reflection.openai_reflection_model import OpenAIReflectionModel
            from atman.config import OpenAILLMConfig

            _llm_model_name = (
                os.getenv("ATMAN_LLM_MODEL")
                or os.getenv("LLM_MODEL")
                or os.getenv("AGENT_LLM_MODEL")
                or "gemma4"
            )
            _narrative_reflection_model = OpenAIReflectionModel(
                OpenAILLMConfig(
                    base_url=_atman_llm_url,
                    api_key=os.getenv("ATMAN_LLM_API_KEY", "dummy"),
                    model=_llm_model_name,
                )
            )
        except Exception:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "OpenAIReflectionModel unavailable — using mock (no narrative updates)",
                exc_info=True,
            )
            _narrative_reflection_model = _MockReflectionModel()
    else:
        _narrative_reflection_model = _MockReflectionModel()

    narrative_revision = NarrativeRevisionService(
        narrative_repo=_NarrativeAdapter(state_store, agent_id),
        reflection_model=_narrative_reflection_model,
        narrative_audit=NoOpNarrativeWriteAudit(),
    )
    # Build optional RAG pipeline when ATMAN_LINGUISTIC_ENABLED=true.
    # Uses the configured embedding backend (ollama/flag) and the same
    # state_store that the session will write to.
    # Note: _factual_memory is set inside the try block below; AmbientMemoryService
    # is constructed after this block so it receives the populated reference.
    passive_memory_injector = None
    _embedding_adapter = None
    if os.getenv("ATMAN_LINGUISTIC_ENABLED", "false").lower() == "true":
        from atman.config import build_embedding_adapter
        from atman.config import build_memory_backend as _build_mem
        from atman.core.services.passive_memory_injector import PassiveMemoryInjector

        try:
            from atman.adapters.linguistic.noop_adapter import NoOpLinguisticAnalyzer
            from atman.adapters.memory.bm25_embedding import BM25EmbeddingAdapter
            from atman.adapters.memory.noop_reranker import NoOpReranker

            _embedding_adapter = build_embedding_adapter()
            _factual_memory = _build_mem()
            # Wire the post_write_scheduler so add_fact triggers async entity-link enrichment.
            if hasattr(_factual_memory, "_post_write_scheduler"):
                _factual_memory._post_write_scheduler = post_write_scheduler  # pyright: ignore[reportAttributeAccessIssue]
            # BM25 is zero-dependency and provides a second retrieval signal
            # fused with the dense embedding via Reciprocal Rank Fusion. It
            # rescues exact lexical matches that dense encoders can rank low.
            _bm25 = BM25EmbeddingAdapter()

            # Ambient mode requires both a LinguisticAnalyzer and a
            # MemoryReranker on the PMI. Try the BGE cross-encoder first
            # (linguistic extra); fall back to NoOp when FlagEmbedding /
            # model assets are unavailable so the ambient path stays
            # reachable in lean deployments.
            _linguistic: object = NoOpLinguisticAnalyzer()
            try:
                from atman.adapters.memory.bge_reranker import BgeReranker

                _reranker: object = BgeReranker()
            except Exception:
                _reranker = NoOpReranker()

            passive_memory_injector = PassiveMemoryInjector(
                embedding=_embedding_adapter,
                factual_memory=_factual_memory,
                state_store=state_store,
                bm25=_bm25,
                linguistic_analyzer=_linguistic,
                memory_reranker=_reranker,
            )
        except Exception:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Failed to build PassiveMemoryInjector — RAG disabled", exc_info=True
            )

    # AmbientMemoryService — built here so _factual_memory (set above) is available.
    _ambient_memory = _Ambient(
        linguistic_analyzer=_affect_linguistic,
        entity_registry=_entity_registry,  # type: ignore[arg-type]
        state_store=state_store,
        entity_stance_store=_entity_stance_store,
        salience_decay=_salience_decay,
        factual_memory=_factual_memory,
    )

    # Build optional skill-loop when skills.enabled=true (default).
    #
    # IMPORTANT: skill_manager must be built BEFORE MicroReflectionService so
    # the reflection hook (process_session_skills) actually fires. If you move
    # this block after the MicroReflectionService construction, the hook
    # becomes dead code — see PR #572 Devin review.
    skill_manager = _build_skill_manager(
        agent_id=agent_id,
        embedding_adapter=_embedding_adapter,
    )

    # HLE-30: in-memory ReflectionEventStore shared with the overload monitor
    # below. The factory only constructs MicroReflectionService — Daily and
    # Deep services live in cli_reflection / cron and would need to point at
    # the same event store for the monitor to actually see DAILY / DEEP rows
    # (its only triggers). Production deploys use a single PostgreSQL-backed
    # store shared by every reflection level; the in-memory store in
    # build_deps is correct for unit tests and the Micro-only dev loop but
    # will not fire DAILY / DEEP overload alerts on its own.
    #
    # The monitor is still exposed on AtmanDeps so cli_maintenance / cron
    # entry points can swap the event store and reuse the same monitor /
    # sinks / dispatch.
    _reflection_event_store = InMemoryReflectionEventStore()
    micro_reflection = MicroReflectionService(
        session_repo=StateStoreSessionRepository(state_store, agent_id=agent_id),
        narrative_revision=narrative_revision,
        event_store=_reflection_event_store,
        skill_manager=skill_manager,
    )

    from atman.adapters.observability.composite_overload_alert_sink import (
        CompositeOverloadAlertSink,
    )
    from atman.adapters.observability.in_memory_overload_alert_sink import (
        InMemoryOverloadAlertSink,
    )
    from atman.adapters.observability.logging_overload_alert_sink import (
        LoggingOverloadAlertSink,
    )
    from atman.core.services.reflection_overload_monitor import ReflectionOverloadMonitor

    _overload_sink_inmem = InMemoryOverloadAlertSink()
    _overload_sink = CompositeOverloadAlertSink([_overload_sink_inmem, LoggingOverloadAlertSink()])
    _overload_monitor = ReflectionOverloadMonitor(
        event_store=_reflection_event_store,
        alert_sink=_overload_sink,
    )

    # Build MaintenanceWorker so mREBEL + lingvo_enrich jobs actually run
    # in-process (dev REPL, live_chat.py). Must come after _overload_monitor.
    _maintenance_worker = None
    try:
        from atman.adapters.memory.in_memory_entity_relation_store import (
            InMemoryEntityRelationStore,
        )
        from atman.core.services.maintenance_worker import MaintenanceWorker

        _relation_store = InMemoryEntityRelationStore()
        _mrebel_extractor = None
        if _linguistic_enabled:
            try:
                from atman.adapters.linguistic.mrebel_adapter import MRebelRelationAdapter

                _mrebel_extractor = MRebelRelationAdapter(device="cpu")
            except Exception:
                import logging as _log

                _log.getLogger(__name__).debug(
                    "mrebel unavailable — worker still handles lingvo/decay jobs",
                    exc_info=True,
                )

        _maintenance_worker = MaintenanceWorker(
            queue=maintenance_queue,
            salience_decay=_salience_decay,
            memory_guardian=_memory_guardian,
            state_store=state_store,
            entity_relation_extractor=_mrebel_extractor,
            entity_relation_store=_relation_store,
            entity_registry=_entity_registry,
            linguistic_analyzer=_affect_linguistic if _linguistic_enabled else None,
            factual_memory=_factual_memory,
            reflection_overload_monitor=_overload_monitor,
        )
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "Failed to build MaintenanceWorker — post-write jobs will not drain in-process",
            exc_info=True,
        )

    deps = AtmanDeps.from_config(
        config=config,
        session_manager=session_manager,
        identity_service=identity_service,
        micro_reflection=micro_reflection,
        state_store=state_store,
        agent_id=agent_id,
        session_id=None,
        pending_review_inbox=InMemoryPendingHumanReviewInbox(),
        reflection_request_queue=InMemoryReflectionRequestQueue(),
        passive_memory_injector=passive_memory_injector,
        skill_manager=skill_manager,
        divergence_event_store=_divergence_event_store,
        reflection_overload_monitor=_overload_monitor,
        overload_alert_inspect=_overload_sink_inmem,
        memory_guardian=_memory_guardian,
        ambient_memory=_ambient_memory,
        entity_registry=_entity_registry,
        maintenance_worker=_maintenance_worker,
        maintenance_queue=maintenance_queue,
    )

    return deps, session_manager, state_store


def _skills_enabled() -> bool:
    """Resolve the effective skill-loop enabled flag.

    ``ATMAN_SKILLS_ENABLED`` takes precedence over ``settings.skills.enabled``
    so operators can flip the loop off without editing config or pickling a
    new Settings instance. Anything falsy (``false``/``0``/``no``/``off``,
    case-insensitive) disables; anything else enables.
    """
    import os as _os

    from atman.config import settings as _settings

    raw = _os.getenv("ATMAN_SKILLS_ENABLED")
    if raw is not None:
        return raw.strip().lower() not in ("false", "0", "no", "off", "")
    return _settings.skills.enabled


def _build_skill_manager(agent_id: UUID, embedding_adapter):
    """Assemble SkillManager with graceful fallback.

    Behaviour, in order of preference, when the skill loop is enabled:

    1. ``PostgresSkillStore`` if PostgreSQL is configured and reachable.
    2. ``InMemorySkillStore`` fallback so local/file-based development still
       starts a real (in-process) skill-loop. Per AGENTS.md, the project must
       run without external services; failing to connect to PostgreSQL should
       degrade, not crash.
    3. ``None`` (skill-loop disabled) if both stores fail to construct.

    All branches return at most one log line on the warning level; no
    exception is allowed to escape.
    """
    from atman.config import settings as _settings

    if not _skills_enabled():
        return None

    import logging as _logging
    from pathlib import Path as _Path

    from atman.skills.manager import SkillManager
    from atman.skills.projection import PydanticAgentProjector
    from atman.skills.retriever import SkillRetriever

    log = _logging.getLogger(__name__)

    skill_store: object | None = None
    try:
        from atman.skills.postgres_store import PostgresSkillStore

        skill_store = PostgresSkillStore(db_url=_settings.database_url, agent_id=agent_id)
    except Exception:
        log.info(
            "PostgresSkillStore unavailable — falling back to in-memory skill store. "
            "Set ATMAN_SKILLS_ENABLED=false to silence this notice.",
            exc_info=True,
        )

    if skill_store is None:
        try:
            from atman.skills.in_memory_store import InMemorySkillStore

            skill_store = InMemorySkillStore()
        except Exception:
            log.warning("Failed to build any SkillStore — skill-loop disabled", exc_info=True)
            return None

    try:
        retriever = SkillRetriever(store=skill_store, embedding=embedding_adapter)
        return SkillManager(
            store=skill_store,
            retriever=retriever,
            projector=PydanticAgentProjector(),
            config=_settings.skills,
            agents_root=_Path(_settings.skills.skills_root).expanduser(),
        )
    except Exception:
        log.warning("Failed to build SkillManager — skill-loop disabled", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# IdentityRepository / NarrativeRepository adapters over any StateStore
# ---------------------------------------------------------------------------


class _StateStoreIdentityRepo:
    """IdentityRepository protocol adapter over FileStateStore or PostgresStateStore."""

    def __init__(self, store: FileStateStore | PostgresStateStore, agent_id: UUID) -> None:
        self._store = store
        self._agent_id = agent_id

    def get_current(self) -> Identity | None:
        return self._store.load_identity(self._agent_id)

    def get_snapshot(self, snapshot_id: UUID) -> IdentitySnapshot | None:
        for snap in self._store.list_identity_snapshots(self._agent_id, limit=500):
            if snap.id == snapshot_id:
                return snap
        return None

    def get_history(self) -> list[IdentitySnapshot]:
        return self._store.list_identity_snapshots(self._agent_id)

    def update(self, identity: Identity) -> None:
        self._store.save_identity(identity)

    def create_snapshot(
        self,
        identity: Identity,
        description: str,
        change_summary: str,
        *,
        snapshot_id: UUID | None = None,
    ) -> IdentitySnapshot:
        from uuid import uuid4 as _uuid4

        snap = IdentitySnapshot(
            id=snapshot_id or _uuid4(),
            identity_id=identity.id,
            identity_snapshot=identity.model_copy(deep=True),
            description=description,
            change_summary=change_summary,
        )
        return self._store.create_identity_snapshot(snap)


class _StateStoreNarrativeRepo:
    """NarrativeRepository protocol adapter over FileStateStore or PostgresStateStore."""

    def __init__(self, store: FileStateStore | PostgresStateStore, identity_id: UUID) -> None:
        self._store = store
        self._identity_id = identity_id

    def get_current(self) -> NarrativeDocument | None:
        return self._store.load_narrative(self._identity_id)

    def update(
        self,
        narrative: NarrativeDocument,
        *,
        expected_updated_at=None,
    ) -> None:
        self._store.save_narrative(narrative, expected_updated_at=expected_updated_at)

    def get_history(self) -> list[NarrativeDocument]:
        return []


# ---------------------------------------------------------------------------
# Production builders for Daily and Deep reflection services
# ---------------------------------------------------------------------------


def _build_reflection_model(override: ReflectionModel | None = None) -> ReflectionModel:
    """Return a ReflectionModel: OpenAIReflectionModel when ATMAN_LLM_BASE_URL set, else mock."""
    if override is not None:
        return override
    _url = os.getenv("ATMAN_LLM_BASE_URL", "")
    if _url:
        try:
            from atman.adapters.reflection.openai_reflection_model import OpenAIReflectionModel
            from atman.config import OpenAILLMConfig

            _model = (
                os.getenv("ATMAN_LLM_MODEL")
                or os.getenv("LLM_MODEL")
                or os.getenv("AGENT_LLM_MODEL")
                or "gemma4"
            )
            return OpenAIReflectionModel(
                OpenAILLMConfig(
                    base_url=_url,
                    api_key=os.getenv("ATMAN_LLM_API_KEY", "dummy"),
                    model=_model,
                )
            )
        except Exception:
            import logging as _log

            _log.getLogger(__name__).warning(
                "OpenAIReflectionModel unavailable — using mock", exc_info=True
            )
    return _MockReflectionModel()


def _build_entity_adapters(state_store: FileStateStore | PostgresStateStore):
    """Return (entity_registry, stance_store): Postgres when available, else in-memory."""
    from atman.adapters.memory.in_memory_entity_registry import InMemoryEntityRegistry
    from atman.adapters.memory.in_memory_entity_stance import InMemoryEntityStanceStore

    registry = InMemoryEntityRegistry()
    stance_store = InMemoryEntityStanceStore()
    _pg_url = os.environ.get("ATMAN_DB_URL") or os.environ.get("DATABASE_URL")
    if _pg_url and isinstance(state_store, PostgresStateStore):
        try:
            from atman.adapters.memory.postgres_entity_registry import PostgresEntityRegistry
            from atman.adapters.memory.postgres_entity_stance import PostgresEntityStanceStore

            registry = PostgresEntityRegistry(db_url=_pg_url)
            stance_store = PostgresEntityStanceStore(db_url=_pg_url)
        except Exception:
            import logging as _log

            _log.getLogger(__name__).warning(
                "Postgres entity adapters unavailable — using in-memory", exc_info=True
            )
    return registry, stance_store


def build_daily_reflection_service(
    agent_id: UUID,
    state_store: FileStateStore | PostgresStateStore,
    *,
    reflection_model: ReflectionModel | None = None,
) -> DailyReflectionService:
    """
    Assemble a fully-wired DailyReflectionService with R5-R10 optional hooks.

    Uses OpenAIReflectionModel when ATMAN_LLM_BASE_URL is set, otherwise MockReflectionModel.
    Uses Postgres adapters for entity registry/stance when DATABASE_URL is configured and
    state_store is PostgresStateStore; falls back to in-memory otherwise.
    """
    from atman.adapters.memory.in_memory_divergence_events import InMemoryDivergenceEventStore
    from atman.adapters.memory.in_memory_memory_guardian import InMemoryMemoryGuardian
    from atman.adapters.storage.in_memory_reflection_store import (
        InMemoryPatternStore,
        InMemoryReflectionEventStore,
    )
    from atman.core.services.divergence_aggregator import DivergenceAggregator
    from atman.core.services.entity_stance_formulator import EntityStanceFormulator
    from atman.core.services.findings_triage import FindingsTriage

    model = _build_reflection_model(reflection_model)
    session_repo = StateStoreSessionRepository(state_store, agent_id=agent_id)
    identity_repo = _StateStoreIdentityRepo(state_store, agent_id)
    pattern_store = InMemoryPatternStore()
    event_store = InMemoryReflectionEventStore()

    entity_registry, stance_store = _build_entity_adapters(state_store)
    divergence_event_store = InMemoryDivergenceEventStore()
    guardian = InMemoryMemoryGuardian(
        state_store=state_store, divergence_event_store=divergence_event_store
    )

    return DailyReflectionService(
        session_repo=session_repo,
        identity_repo=identity_repo,
        pattern_store=pattern_store,
        reflection_model=model,
        event_store=event_store,
        divergence_aggregator=DivergenceAggregator(
            event_store=divergence_event_store, pattern_store=pattern_store
        ),
        entity_stance_formulator=EntityStanceFormulator(
            state_store=state_store,
            entity_registry=entity_registry,
            stance_store=stance_store,
            reflection_model=model,
        ),
        findings_triage=FindingsTriage(guardian=guardian),
        reflection_request_queue=InMemoryReflectionRequestQueue(),
        agent_id=agent_id,
    )


def build_deep_reflection_service(
    agent_id: UUID,
    state_store: FileStateStore | PostgresStateStore,
    *,
    reflection_model: ReflectionModel | None = None,
) -> DeepReflectionService:
    """
    Assemble a fully-wired DeepReflectionService with R5-R10 optional hooks.

    Uses OpenAIReflectionModel when ATMAN_LLM_BASE_URL is set, otherwise MockReflectionModel.
    Uses Postgres adapters for entity registry/stance when DATABASE_URL is configured and
    state_store is PostgresStateStore; falls back to in-memory otherwise.
    """
    from atman.adapters.memory.in_memory_divergence_events import InMemoryDivergenceEventStore
    from atman.adapters.memory.in_memory_entity_relation_store import InMemoryEntityRelationStore
    from atman.adapters.memory.in_memory_memory_guardian import InMemoryMemoryGuardian
    from atman.adapters.storage.in_memory_reflection_store import (
        InMemoryHealthAssessmentStore,
        InMemoryPatternStore,
        InMemoryReflectionEventStore,
    )
    from atman.core.services.entity_relations_formulator import EntityRelationsFormulator
    from atman.core.services.entity_stance_formulator import EntityStanceFormulator
    from atman.core.services.merge_candidates_handler import MergeCandidatesHandler

    model = _build_reflection_model(reflection_model)
    session_repo = StateStoreSessionRepository(state_store, agent_id=agent_id)
    identity_repo = _StateStoreIdentityRepo(state_store, agent_id)

    identity = state_store.load_identity(agent_id)
    identity_id = identity.id if identity else agent_id
    narrative_repo = _StateStoreNarrativeRepo(state_store, identity_id)

    pattern_store = InMemoryPatternStore()
    health_store = InMemoryHealthAssessmentStore()
    event_store = InMemoryReflectionEventStore()

    entity_registry, stance_store = _build_entity_adapters(state_store)
    divergence_event_store = InMemoryDivergenceEventStore()
    guardian = InMemoryMemoryGuardian(
        state_store=state_store, divergence_event_store=divergence_event_store
    )

    return DeepReflectionService(
        session_repo=session_repo,
        identity_repo=identity_repo,
        narrative_repo=narrative_repo,
        pattern_store=pattern_store,
        health_store=health_store,
        reflection_model=model,
        event_store=event_store,
        entity_stance_formulator=EntityStanceFormulator(
            state_store=state_store,
            entity_registry=entity_registry,
            stance_store=stance_store,
            reflection_model=model,
        ),
        entity_relations_formulator=EntityRelationsFormulator(
            state_store=state_store,
            entity_registry=entity_registry,
            relation_store=InMemoryEntityRelationStore(),
            reflection_model=model,
        ),
        merge_candidates_handler=MergeCandidatesHandler(
            state_store=state_store,
            entity_registry=entity_registry,
            guardian=guardian,
            reflection_model=model,
        ),
        reflection_request_queue=InMemoryReflectionRequestQueue(),
        agent_id=agent_id,
    )
