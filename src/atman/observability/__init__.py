"""atman.observability — public API for Sentry-based observability.

Usage at entrypoint:
    from atman.observability import init_observability
    init_observability()          # reads ATMAN_OBS_LEVEL from env

Usage in adapters / engines (after init):
    from atman.observability.spans import ai_chat_span, memory_span
    with ai_chat_span("anthropic", "claude-opus-4-7") as span:
        ...
"""

from atman.observability.sentry_init import ObsLevel, init_observability, is_enabled, is_full_mode

__all__ = ["ObsLevel", "init_observability", "is_enabled", "is_full_mode"]
