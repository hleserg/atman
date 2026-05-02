"""Domain-level exceptions for core services."""


class GovernanceRejectedError(Exception):
    """Raised when a write is blocked by governance policy (e.g. core narrative without approval)."""


class NarrativePersistenceConflictError(Exception):
    """
    Raised when a narrative write loses optimistic concurrency.

    The caller read a document snapshot, but another writer committed first
    (different ``updated_at`` on the persisted narrative).
    """
