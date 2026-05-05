"""Domain-level exceptions for core services."""


class AtmanError(Exception):
    """Base class for recoverable Atman domain errors."""


class GovernanceRejectedError(Exception):
    """Raised when a write is blocked by governance policy (e.g. core narrative without approval)."""


class NarrativePersistenceConflictError(Exception):
    """
    Raised when a narrative write loses optimistic concurrency.

    The caller read a document snapshot, but another writer committed first
    (different ``updated_at`` on the persisted narrative).
    """


class SessionNotFoundError(AtmanError):
    """Raised when a session ID is not present in the active session registry."""


class SessionAlreadyFinishedError(AtmanError):
    """Raised when mutating or finishing a session that has already completed."""


class TooManyActiveSessionsError(AtmanError):
    """Raised when ``start_session`` would exceed ``SessionManager`` active session limit."""
