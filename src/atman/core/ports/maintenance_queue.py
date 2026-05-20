"""Port: MaintenanceQueue — enqueue and claim background maintenance jobs."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from atman.core.models.maintenance import JobName, JobStatus, MaintenanceJob

# Job types that require a ``key_moment_id`` key in their payload.
_MOMENT_SCOPED_JOBS: frozenset[JobName] = frozenset({JobName.mrebel_extract, JobName.lingvo_enrich})


def validate_enqueue_payload(job_name: JobName, payload: dict) -> None:
    """Raise ValueError if a moment-scoped job is missing ``key_moment_id`` in its payload.

    Call this at the start of every ``MaintenanceQueue.enqueue()`` implementation
    so that structurally invalid jobs are rejected before they enter the queue.
    """
    if job_name in _MOMENT_SCOPED_JOBS and not payload.get("key_moment_id"):
        raise ValueError(
            f"{job_name.value} job requires 'key_moment_id' in payload, got: {list(payload.keys())}"
        )


class MaintenanceQueue(ABC):
    """Abstract port for a durable maintenance job queue."""

    @abstractmethod
    def enqueue(
        self,
        job_name: JobName,
        *,
        agent_id: UUID | None = None,
        payload: dict | None = None,
        run_key: str | None = None,
        scheduled_at: datetime | None = None,
    ) -> MaintenanceJob:
        """Enqueue job. If run_key matches existing pending/running job, return that (idempotent)."""

    @abstractmethod
    def claim_batch(
        self,
        job_name: JobName | None = None,
        *,
        batch_size: int = 10,
    ) -> list[MaintenanceJob]:
        """Atomically claim pending jobs (SKIP LOCKED semantics). Returns claimed jobs with status=running."""

    @abstractmethod
    def mark_done(self, job_id: UUID, *, result: dict | None = None) -> None:
        """Mark job as succeeded."""

    @abstractmethod
    def mark_failed(self, job_id: UUID, *, error: str) -> None:
        """Mark job as failed."""

    @abstractmethod
    def mark_skipped(self, job_id: UUID, *, reason: str = "") -> None:
        """Mark job as skipped (duplicate or not applicable)."""

    @abstractmethod
    def list_jobs(
        self,
        status: JobStatus | None = None,
        agent_id: UUID | None = None,
        *,
        limit: int = 100,
    ) -> list[MaintenanceJob]:
        """List jobs filtered by status and/or agent."""
