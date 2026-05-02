"""No-op observer for reflection event persistence (tests may replace)."""

from atman.core.models.reflection import ReflectionLevel


class NoOpReflectionEventPersistenceObserver:
    """Ignores reflection event store failures after narrative commit."""

    def record_reflection_event_save_failed_after_narrative_commit(
        self,
        *,
        reflection_level: ReflectionLevel,
        error_message: str,
    ) -> None:
        return None
