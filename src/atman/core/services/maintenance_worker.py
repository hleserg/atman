"""MaintenanceWorker — dispatch and execute maintenance jobs from the queue."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from atman.core.models.entity import EntityRelation, EntityType, FactEntityLink, KeyMomentEntityLink
from atman.core.models.maintenance import JobName, MaintenanceJob
from atman.core.ports.entity_registry import EntityRegistry
from atman.core.ports.entity_relation_store import EntityRelationStore
from atman.core.ports.entity_relations import EntityRelationExtractor
from atman.core.ports.linguistic import DetectedEntity, LinguisticAnalyzer
from atman.core.ports.maintenance_queue import MaintenanceQueue
from atman.core.ports.memory_backend import FactualMemory
from atman.core.ports.memory_guardian import MemoryGuardian
from atman.core.ports.salience_decay import SalienceDecayService
from atman.core.ports.state_store import StateStore
from atman.core.services.reflection_overload_monitor import ReflectionOverloadMonitor

_LOG = logging.getLogger(__name__)

from atman.core.session_log import slog as _slog  # noqa: E402
from atman.observability.spans import job_scope as _job_scope  # noqa: E402

try:
    from atman.adapters.observability.sentry import (
        metric_distribution as _md,  # type: ignore[assignment]
    )
    from atman.adapters.observability.sentry import (
        metric_increment as _mi,  # type: ignore[assignment]
    )
except Exception:  # pragma: no cover

    def _mi(*_a: object, **_kw: object) -> None: ...  # type: ignore[misc]
    def _md(*_a: object, **_kw: object) -> None: ...  # type: ignore[misc]


class _DispatchOutcome(Enum):
    """Result of `_handle` — distinguishes done vs already-skipped vs no-op."""

    DONE = "done"
    SKIPPED = "skipped"


class MaintenanceWorker:
    """Dispatch and execute maintenance jobs claimed from the queue."""

    def __init__(
        self,
        queue: MaintenanceQueue,
        salience_decay: SalienceDecayService | None = None,
        memory_guardian: MemoryGuardian | None = None,
        *,
        state_store: StateStore | None = None,
        entity_relation_extractor: EntityRelationExtractor | None = None,
        entity_relation_store: EntityRelationStore | None = None,
        entity_registry: EntityRegistry | None = None,
        linguistic_analyzer: LinguisticAnalyzer | None = None,
        factual_memory: FactualMemory | None = None,
        reflection_overload_monitor: ReflectionOverloadMonitor | None = None,
    ) -> None:
        self._queue = queue
        self._decay = salience_decay
        self._guardian = memory_guardian
        # Enrichment dependencies (HLE-28). All optional — a worker without
        # them will mark mrebel_extract / lingvo_enrich jobs as skipped with
        # an explanatory reason rather than crashing, which is the right
        # behaviour for in-memory dev runs that lack ML models.
        self._state_store = state_store
        self._relation_extractor = entity_relation_extractor
        self._relation_store = entity_relation_store
        self._entity_registry = entity_registry
        self._analyzer = linguistic_analyzer
        self._factual_memory = factual_memory
        # HLE-30: reflection cadence anomaly check. None ⇒ job skipped with
        # reason (lean dev mode without reflection_event_store wiring).
        self._overload_monitor = reflection_overload_monitor

    def run_once(self, batch_size: int = 20) -> int:
        """Claim and execute one batch of pending jobs. Returns number processed."""
        jobs = self._queue.claim_batch(batch_size=batch_size)
        for job in jobs:
            self._dispatch(job)
        return len(jobs)

    def _dispatch(self, job: MaintenanceJob) -> None:
        import time as _time

        _t0 = _time.monotonic()
        payload = job.payload or {}
        _slog(
            "job_start",
            job_id=str(job.id),
            job_name=job.job_name.value,
            agent_id=str(payload.get("agent_id", "")),
            payload_keys=list(payload.keys()),
        )
        _tags: dict[str, str] = {
            "job.name": job.job_name.value,
            "job.id": str(job.id),
        }
        if job.agent_id is not None:
            _tags["agent_id"] = str(job.agent_id)
        with _job_scope(_tags):
            try:
                outcome, result = self._handle(job)
                elapsed_ms = round((_time.monotonic() - _t0) * 1000)
                # _handle returns SKIPPED when it has already called mark_skipped
                # (e.g. unknown job type). Only call mark_done for DONE outcomes.
                # This avoids relying on object-identity mutations of `job.status`,
                # which would break under DB-backed queues that don't share state.
                if outcome is _DispatchOutcome.DONE:
                    self._queue.mark_done(job.id, result=result)
                _slog(
                    "job_done",
                    job_id=str(job.id),
                    job_name=job.job_name.value,
                    outcome=outcome.value,
                    result=result,
                    elapsed_ms=elapsed_ms,
                )
                _mi(
                    "atman.maintenance.job_done",
                    tags={"job": job.job_name.value, "outcome": outcome.value},
                )
                _md(
                    "atman.maintenance.job_latency_ms",
                    float(elapsed_ms),
                    unit="millisecond",
                    tags={"job": job.job_name.value},
                )
            except Exception as exc:
                elapsed_ms = round((_time.monotonic() - _t0) * 1000)
                _LOG.exception("maintenance job %s failed", job.id)
                self._queue.mark_failed(job.id, error=str(exc))
                _slog(
                    "job_failed",
                    job_id=str(job.id),
                    job_name=job.job_name.value,
                    error=str(exc),
                    elapsed_ms=elapsed_ms,
                )
                _mi(
                    "atman.maintenance.job_done",
                    tags={"job": job.job_name.value, "outcome": "failed"},
                )

    def _handle(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        if job.job_name == JobName.salience_decay:
            return self._run_decay(job)
        if job.job_name == JobName.memory_guardian_scan:
            return self._run_guardian(job)
        if job.job_name == JobName.mrebel_extract:
            return self._run_mrebel(job)
        if job.job_name == JobName.lingvo_enrich:
            return self._run_lingvo(job)
        if job.job_name == JobName.reflection_overload_check:
            return self._run_overload_check(job)
        if job.job_name == JobName.fact_entity_link:
            return self._run_fact_entity_link_job(job)
        _LOG.warning("unknown job %s, skipping", job.job_name)
        self._queue.mark_skipped(job.id, reason="unknown job type")
        return _DispatchOutcome.SKIPPED, None

    def _run_decay(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        if self._decay is None:
            self._queue.mark_skipped(job.id, reason="salience decay not configured")
            return _DispatchOutcome.SKIPPED, None
        # agent_id is a top-level field on MaintenanceJob — not in payload.
        if job.agent_id is None:
            raise ValueError(f"salience_decay job {job.id} requires agent_id")
        agent_id = job.agent_id
        cutoff_str = (job.payload or {}).get("cutoff")
        cutoff = datetime.fromisoformat(cutoff_str) if cutoff_str else datetime.now(UTC)
        count = self._decay.decay_pass(agent_id, cutoff=cutoff)
        return _DispatchOutcome.DONE, {"updated": count}

    def _run_guardian(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        if self._guardian is None:
            self._queue.mark_skipped(job.id, reason="memory guardian not configured")
            return _DispatchOutcome.SKIPPED, None
        if job.agent_id is None:
            raise ValueError(f"memory_guardian_scan job {job.id} requires agent_id")
        agent_id = job.agent_id
        findings = (
            self._guardian.scan_orphan_entities(agent_id)
            + self._guardian.scan_merge_candidates(agent_id)
            + self._guardian.scan_embedding_gaps(agent_id)
            + self._guardian.scan_stale_moments(agent_id)
            # HLE-31: Level-C psychological metrics
            + self._guardian.scan_quality_metrics(agent_id)
        )
        for f in findings:
            self._guardian.write_finding(f)
        return _DispatchOutcome.DONE, {"findings": len(findings)}

    def _run_mrebel(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        """Async relation-extraction for a single KeyMoment (HLE-28).

        Reads the moment from state_store, runs the configured extractor
        on its narrative, and persists each ExtractedRelation in
        ``agent_N.entity_relations`` with ``learned_by='mrebel'``.
        Skipped (not failed) when the worker has no extractor / store /
        registry — that is a valid lean-deploy configuration, not an error.
        """
        if (
            self._relation_extractor is None
            or self._relation_store is None
            or self._state_store is None
            or self._entity_registry is None
        ):
            self._queue.mark_skipped(job.id, reason="relation enrichment not configured")
            return _DispatchOutcome.SKIPPED, None
        if not (job.payload or {}).get("key_moment_id"):
            self._queue.mark_skipped(job.id, reason="missing key_moment_id payload")
            return _DispatchOutcome.SKIPPED, None
        agent_id, moment_id = _require_moment_payload(job)
        moment = self._state_store.get_key_moment(moment_id)
        if moment is None:
            self._queue.mark_skipped(job.id, reason=f"key moment {moment_id} not found")
            return _DispatchOutcome.SKIPPED, None
        text = _moment_narrative(moment)
        if not text.strip():
            self._queue.mark_skipped(job.id, reason="empty moment narrative")
            return _DispatchOutcome.SKIPPED, None
        relations = self._relation_extractor.extract_relations(text, entities=[])
        written = 0
        for rel in relations:
            subj = self._resolve_entity(agent_id, rel.subject)
            obj = self._resolve_entity(agent_id, rel.object)
            if subj is None or obj is None or subj == obj:
                continue
            self._relation_store.add_relation(
                EntityRelation(
                    agent_id=agent_id,
                    from_entity_id=subj,
                    to_entity_id=obj,
                    relation_type=rel.relation_type,
                    confidence=rel.confidence,
                    learned_by="mrebel",
                )
            )
            written += 1
        return _DispatchOutcome.DONE, {"relations_written": written}

    def _run_lingvo(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        """Async deeper linguistic analysis for a single KeyMoment (HLE-28).

        Calls ``LinguisticAnalyzer.analyze_key_moment`` on the moment's
        narrative fields and stores the structured markers via
        ``state_store.update_moment_structured_markers``. Idempotent —
        skipped when ``structured_markers`` already populated.
        Also resolves entities from the analysis and writes key_moment_entities
        rows when entity_registry is available.
        """
        if self._analyzer is None or self._state_store is None:
            self._queue.mark_skipped(job.id, reason="linguistic enrichment not configured")
            return _DispatchOutcome.SKIPPED, None
        if not (job.payload or {}).get("key_moment_id"):
            self._queue.mark_skipped(job.id, reason="missing key_moment_id payload")
            return _DispatchOutcome.SKIPPED, None
        agent_id, moment_id = _require_moment_payload(job)
        moment = self._state_store.get_key_moment(moment_id)
        if moment is None:
            self._queue.mark_skipped(job.id, reason=f"key moment {moment_id} not found")
            return _DispatchOutcome.SKIPPED, None
        if _moment_has_markers(moment):
            self._queue.mark_skipped(job.id, reason="structured markers already present")
            return _DispatchOutcome.SKIPPED, None
        analysis = self._analyzer.analyze_key_moment(
            moment.what_happened or "", moment.why_it_matters or ""
        )
        k_markers = analysis.model_dump(mode="json") if hasattr(analysis, "model_dump") else {}
        # Namespace under "k" so point-A markers written earlier are preserved via JSONB merge.
        self._state_store.update_moment_structured_markers(
            moment_id,
            {"k": k_markers},
            "2.0",
        )
        entities_linked = _write_km_entity_links(
            moment_id, agent_id, analysis, self._entity_registry, self._state_store
        )
        return _DispatchOutcome.DONE, {
            "moment_id": str(moment_id),
            "entities_linked": entities_linked,
        }

    def _run_overload_check(self, job: MaintenanceJob) -> tuple[_DispatchOutcome, dict | None]:
        """Periodic reflection-cadence anomaly check (HLE-30).

        Delegates to :class:`ReflectionOverloadMonitor.check()`, which
        inspects recent reflection events and emits alerts through the
        wired sink when the windows exceed thresholds. The monitor swallows
        sink failures internally, so this handler is a thin wrapper.
        """
        if self._overload_monitor is None:
            self._queue.mark_skipped(job.id, reason="reflection overload monitor not configured")
            return _DispatchOutcome.SKIPPED, None
        self._overload_monitor.check()
        return _DispatchOutcome.DONE, {"scanned": True}

    def _run_fact_entity_link_job(
        self, job: MaintenanceJob
    ) -> tuple[_DispatchOutcome, dict | None]:
        """Async entity-link enrichment for a single Fact (biographical NER).

        Loads the fact from factual_memory, runs LinguisticAnalyzer.analyze_user_message
        on its content, resolves entities via entity_registry.resolve_or_create, and
        writes the links into agent_N.fact_entities via save_fact_entity_links.
        Skipped (not failed) when any required dependency is absent.
        """
        if self._factual_memory is None or self._analyzer is None or self._entity_registry is None:
            self._queue.mark_skipped(job.id, reason="fact entity link enrichment not configured")
            return _DispatchOutcome.SKIPPED, None

        if job.agent_id is None:
            raise ValueError(f"fact_entity_link job {job.id} requires agent_id")
        agent_id = job.agent_id
        raw_fact_id = (job.payload or {}).get("fact_id")
        if not raw_fact_id:
            raise ValueError(f"fact_entity_link job {job.id} missing fact_id payload")
        fact_id = UUID(str(raw_fact_id))

        fact = self._factual_memory.get_fact(fact_id)
        if fact is None:
            self._queue.mark_skipped(job.id, reason=f"fact {fact_id} not found")
            return _DispatchOutcome.SKIPPED, None

        analysis = self._analyzer.analyze_user_message(fact.content or "")

        entity_links: list[FactEntityLink] = []
        for ent in analysis.entities:
            try:
                resolved, _ = self._entity_registry.resolve_or_create(
                    agent_id, ent.text, ent.entity_type
                )
                entity_links.append(
                    FactEntityLink(
                        fact_id=fact_id,
                        entity_id=resolved.id,
                        agent_id=agent_id,
                        role="mentioned",
                        confidence=ent.confidence,
                    )
                )
            except Exception:
                _LOG.warning(
                    "fact entity resolve failed for %r (fact %s)", ent.text, fact_id, exc_info=True
                )

        unique_links = _dedupe_fact_entity_links(entity_links)

        save_fn = getattr(self._factual_memory, "save_fact_entity_links", None)
        if save_fn is None:
            self._queue.mark_skipped(
                job.id, reason="factual_memory does not support save_fact_entity_links"
            )
            return _DispatchOutcome.SKIPPED, None

        if unique_links:
            save_fn(fact_id, agent_id, unique_links)

        return _DispatchOutcome.DONE, {
            "fact_id": str(fact_id),
            "entities_linked": len(unique_links),
        }

    def _resolve_entity(self, agent_id: UUID, entity: DetectedEntity) -> UUID | None:
        """Look up entity by surface form; skip when nothing matches.

        We deliberately avoid creating new entities here — entity registration
        is the responsibility of the user-message ingestion path, not the
        async enrichment worker.
        """
        if self._entity_registry is None:
            return None
        try:
            matches = self._entity_registry.find_by_name(
                agent_id,
                entity.text,
                entity.entity_type,
            )
        except Exception:
            _LOG.warning("entity lookup failed for %r", entity.text, exc_info=True)
            return None
        return matches[0].id if matches else None


def _dedupe_fact_entity_links(links: list[FactEntityLink]) -> list[FactEntityLink]:
    """Keep one link per (entity_id, role) with the highest confidence."""
    best_by_key: dict[tuple[UUID, str], FactEntityLink] = {}
    for link in links:
        key = (link.entity_id, link.role)
        prev = best_by_key.get(key)
        if prev is None or link.confidence > prev.confidence:
            best_by_key[key] = link
    return list(best_by_key.values())


def _require_moment_payload(job: MaintenanceJob) -> tuple[UUID, UUID]:
    """Extract (agent_id, moment_id) from a moment-scoped enrichment job."""
    if job.agent_id is None:
        raise ValueError(f"{job.job_name.value} job {job.id} requires agent_id")
    raw = (job.payload or {}).get("key_moment_id")
    if not raw:
        raise ValueError(f"{job.job_name.value} job {job.id} missing key_moment_id payload")
    return job.agent_id, UUID(str(raw))


def _moment_narrative(moment: object) -> str:
    """Join the narrative-bearing fields of a KeyMoment for extraction."""
    what = getattr(moment, "what_happened", "") or ""
    why = getattr(moment, "why_it_matters", "") or ""
    if what and why:
        return f"{what}\n\n{why}"
    return what or why


_MARKER_SPAN_INVOLVEMENT: dict[str, str] = {
    "recurring_theme": "mentioned",
    "closure_marker": "evoked",
    "opening_marker": "evoked",
    "contradiction_marker": "evoked",
}


def _write_km_entity_links(
    moment_id: UUID,
    agent_id: UUID,
    analysis: object,
    entity_registry: EntityRegistry | None,
    state_store: StateStore,
) -> int:
    """Resolve entities from a KeyMomentAnalysis and persist key_moment_entities rows.

    Uses resolve_or_create so new biographical entities discovered in a key moment
    are registered immediately. Safe to call multiple times — the INSERT uses
    ON CONFLICT DO NOTHING.

    Returns the number of links written (0 when registry or store don't support it).
    """
    if entity_registry is None:
        return 0
    save_fn = getattr(state_store, "save_key_moment_entity_links", None)
    if save_fn is None:
        return 0

    entity_pairs: list[tuple[UUID, str]] = []

    # Legacy NER entities (biographic: person, place, org, …) → "mentioned"
    for ent in getattr(analysis, "entities", []):
        try:
            resolved, _ = entity_registry.resolve_or_create(agent_id, ent.text, ent.entity_type)
            entity_pairs.append((resolved.id, "mentioned"))
        except Exception:
            _LOG.warning(
                "km entity resolve failed for %r (moment %s)", ent.text, moment_id, exc_info=True
            )

    # 4-label narrative marker spans — resolve as topic entities
    for span in getattr(analysis, "marker_spans", []):
        involvement = _MARKER_SPAN_INVOLVEMENT.get(span.label)
        if involvement is None:
            continue
        try:
            resolved, _ = entity_registry.resolve_or_create(agent_id, span.text, EntityType.topic)
            entity_pairs.append((resolved.id, involvement))
        except Exception:
            _LOG.warning(
                "km span resolve failed for %r (moment %s)", span.text, moment_id, exc_info=True
            )

    if not entity_pairs:
        return 0

    # Deduplicate (entity_id, involvement) — keep first occurrence
    seen: set[tuple[UUID, str]] = set()
    unique: list[tuple[UUID, str]] = []
    for pair in entity_pairs:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)

    links = [
        KeyMomentEntityLink(
            key_moment_id=moment_id,
            entity_id=entity_id,
            agent_id=agent_id,
            involvement=involvement,
        )
        for entity_id, involvement in unique
    ]
    save_fn(moment_id, agent_id, links)
    return len(links)


def _moment_has_markers(moment: object) -> bool:
    """True when the moment already has point-K markers (namespace 'k' or legacy flat markers).

    With JSONB-merge semantics, point-A markers under 'a' are written first at recording time.
    We skip point-K enrichment only when 'k' is already present, not when 'a' exists.
    """
    markers = getattr(moment, "structured_markers", None)
    if not markers:
        return False
    # New namespaced format: check for "k" key specifically
    if isinstance(markers, dict):
        return "k" in markers or (
            # Legacy flat format: detect by presence of point-K keys
            "cognitive_load" in markers and "k" not in markers and "a" not in markers
        )
    return False
