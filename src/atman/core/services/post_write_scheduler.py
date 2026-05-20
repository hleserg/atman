"""PostWriteScheduler — fire-and-forget enqueue of enrichment jobs after a write.

After a KeyMoment is persisted, the agent's main control loop should not block
on heavy enrichment (mREBEL relation extraction, deeper linguistic analysis,
embedding computation for offline reranker). This service enqueues those
tasks onto the :class:`MaintenanceQueue` so they run asynchronously, either
via `asyncio.create_task` for in-process execution or via the
`atman-maintenance` worker for out-of-process execution.

Idempotency: a deterministic ``run_key`` is derived from
``(job_name, key_moment_id)`` so multiple post-write hooks for the same
moment don't create duplicate jobs.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from atman.core.models.experience import KeyMoment
from atman.core.models.fact import FactRecord
from atman.core.models.maintenance import JobName
from atman.core.ports.maintenance_queue import MaintenanceQueue

_LOG = logging.getLogger(__name__)


# PLAYBOOK-START
# id: deterministic-run-keys-for-async-enqueue
# category: design-patterns
# title: Deterministic Run Keys for De-Duplicated Async Job Enqueue
# status: refined
# since: 2026-05-16
#
# Pattern: derive a deterministic `run_key` from `(job_name, resource_id)` (and
# anything else that semantically identifies "the same logical job for this
# resource"). Pass the key to the queue at enqueue time; the queue treats
# repeat enqueues with a matching key as no-ops (return the existing pending
# / running row instead of inserting a duplicate).
#
# Why generalizable: any post-write hook fired from a request-handler hot
# path will be triggered N times for the same resource under retries,
# replays, or competing observers. Without a run_key the queue accumulates
# duplicate work; with one, idempotency falls out for free without
# distributed locks. Composes with the cron-table-as-queue pattern (see
# 0011_maintenance_jobs.sql) and with the Skip-Locked claim pattern.
def _moment_run_key(job_name: JobName, moment_id: UUID) -> str:
    """Deterministic idempotency key for moment-scoped enrichment jobs."""
    return f"{job_name.value}:moment:{moment_id}"


def _fact_run_key(fact_id: UUID) -> str:
    """Deterministic idempotency key for fact entity-link enrichment jobs."""
    return f"{JobName.fact_entity_link.value}:fact:{fact_id}"


# PLAYBOOK-END


class PostWriteScheduler:
    """Enqueue enrichment jobs onto a MaintenanceQueue after a write event."""

    def __init__(
        self,
        queue: MaintenanceQueue,
        *,
        jobs: tuple[JobName, ...] = (
            JobName.mrebel_extract,
            JobName.lingvo_enrich,
        ),
    ) -> None:
        self._queue = queue
        self._jobs = jobs
        # Strong references for fire-and-forget tasks. asyncio.create_task keeps
        # only a weak ref to the task; without this set, a task spawned from
        # schedule_for_key_moment_async could be garbage-collected mid-flight
        # (see https://docs.python.org/3/library/asyncio-task.html#creating-tasks).
        # Tasks remove themselves via the discard done-callback below.
        self._background_tasks: set[asyncio.Task[None]] = set()

    def schedule_for_key_moment(
        self,
        moment: KeyMoment,
        agent_id: UUID,
        *,
        scheduled_at: datetime | None = None,
    ) -> None:
        """Synchronously enqueue all configured jobs for ``moment``.

        Safe to call from request-handler hot path — enqueuing is cheap
        (one INSERT per job in the Postgres impl, dict mutation in the
        in-memory impl). Use :meth:`schedule_for_key_moment_async` when
        you specifically want to detach from the current event loop turn.
        """
        when = scheduled_at or datetime.now(UTC)
        for job_name in self._jobs:
            try:
                self._queue.enqueue(
                    job_name,
                    agent_id=agent_id,
                    payload={"key_moment_id": str(moment.id)},
                    run_key=_moment_run_key(job_name, moment.id),
                    scheduled_at=when,
                )
            except Exception:
                _LOG.exception(
                    "Failed to enqueue %s for moment %s — continuing", job_name.value, moment.id
                )

    def schedule_for_fact(
        self,
        fact: FactRecord,
        agent_id: UUID,
        *,
        scheduled_at: datetime | None = None,
    ) -> None:
        """Enqueue a fact_entity_link job for async entity resolution after a fact write."""
        when = scheduled_at or datetime.now(UTC)
        try:
            self._queue.enqueue(
                JobName.fact_entity_link,
                agent_id=agent_id,
                payload={"fact_id": str(fact.id)},
                run_key=_fact_run_key(fact.id),
                scheduled_at=when,
            )
        except Exception:
            _LOG.exception("Failed to enqueue fact_entity_link for fact %s — continuing", fact.id)

    # PLAYBOOK-START
    # id: fire-and-forget-asyncio-task-strong-refs
    # category: design-patterns
    # title: Fire-and-Forget Asyncio Tasks with Strong-Reference Lifetime
    # status: refined
    # since: 2026-05-16
    #
    # Pattern: when scheduling a background task with `loop.create_task(...)`
    # from inside a service, asyncio holds only a WEAK reference to the task.
    # A naive `_ = loop.create_task(coro)` lets the task be garbage-collected
    # mid-flight (see CPython issue tracker), so the coroutine may never run
    # to completion. Solution: keep a strong reference in an instance-level
    # `set[asyncio.Task]`, add the task on creation, and register a
    # `set.discard` done-callback so it self-removes when finished. Combine
    # with a separate exception-logger done-callback so silent crashes
    # surface in logs.
    #
    # Why generalizable: every async service that wants fire-and-forget
    # behaviour (post-write hooks, audit observers, telemetry emitters)
    # hits this exact pitfall. The set-of-tasks pattern is the cure
    # recommended in the asyncio docs but is rarely written down.
    async def schedule_for_key_moment_async(
        self,
        moment: KeyMoment,
        agent_id: UUID,
        *,
        scheduled_at: datetime | None = None,
    ) -> None:
        """Fire-and-forget variant — schedules via ``asyncio.create_task``.

        Returns immediately. If no running event loop is available, falls
        back to synchronous enqueue so callers can use this method
        unconditionally.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop — degrade to sync.
            self.schedule_for_key_moment(moment, agent_id, scheduled_at=scheduled_at)
            return

        async def _run() -> None:
            await asyncio.to_thread(
                self.schedule_for_key_moment,
                moment,
                agent_id,
                scheduled_at=scheduled_at,
            )

        # Keep a strong reference in the instance-level set until the task
        # completes — a local variable goes out of scope on return, and
        # asyncio holds only a weak ref to the task.
        task = loop.create_task(_run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(_log_task_exception)
        # Yield once so this coroutine uses ``await`` (fire-and-forget still applies).
        await asyncio.sleep(0)

    # PLAYBOOK-END


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Surface unhandled exceptions from fire-and-forget tasks via logger."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _LOG.exception(
            "post-write enrichment task failed: %s",
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
