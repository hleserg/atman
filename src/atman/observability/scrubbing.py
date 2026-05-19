"""PII scrubbing helpers for Sentry events.

Extends sentry-sdk's DEFAULT_DENYLIST with Atman-specific keys that must
never reach Sentry SaaS: memory contents, reflections, embeddings, prompts.
"""

from __future__ import annotations

from typing import Any

ATMAN_EXTRA_KEYS: list[str] = [
    # fact / memory content — may contain personal statements
    "memory_content",
    "memory_text",
    "fact_payload",
    "fact_content",
    "content_excerpt",  # truncated fact content sent via slog breadcrumbs
    # reflection / identity payloads — psychological data
    "reflection_text",
    "identity_payload",
    "key_insight",
    "user_journal",
    # LLM I/O — may contain personal conversations
    "embedding_input",
    "rerank_documents",
    "prompt",
    "prompt_text",
    "completion",
    "response_text",
    # raw numeric payloads that should stay local
    "embedding",
    "vector",
    # credentials
    "api_key",
    "authorization",
]


def make_event_scrubber(level: str) -> Any:
    """Return an EventScrubber configured with ATMAN_DENYLIST.

    In verbose mode we still scrub — developer must opt-in to raw payloads
    via ATMAN_SEND_PROMPTS=1 at the SDK level if needed.
    """
    from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber  # lazy import

    denylist: list[str] = list(DEFAULT_DENYLIST) + ATMAN_EXTRA_KEYS
    return EventScrubber(denylist=denylist, recursive=True)


def _make_before_send(level: str) -> Any:
    """Factory for before_send callback (no-op filter for now; extensible)."""

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        return event

    return before_send


_HEALTH_ROUTES: frozenset[str] = frozenset({"/health", "/healthz", "/metrics", "/livez", "/readyz"})


def _make_before_send_transaction(level: str) -> Any:
    """Factory for before_send_transaction callback.

    Drops health-check and metrics endpoints to avoid quota waste.
    """

    def before_send_transaction(
        event: dict[str, Any], hint: dict[str, Any]
    ) -> dict[str, Any] | None:
        transaction = event.get("transaction", "")
        if transaction in _HEALTH_ROUTES:
            return None
        return event

    return before_send_transaction
