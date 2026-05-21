"""Span helper layer for Atman observability.

Standard context managers wrapping sentry_sdk.start_span so every adapter
and engine uses the same op names and attribute schema.  The CI scanner
(tools/check_instrumentation.py) recognises these names as valid instrumentation.

When ``ATMAN_OBS_LEVEL=off``, helpers yield without importing ``sentry_sdk`` so the
documented zero-overhead contract holds.  When observability is enabled but Sentry
was not initialised (no DSN), the SDK returns a no-op span automatically.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

# Sentry span attribute keys (single definition for helpers + tests; Sonar S1192).
GEN_AI_DATA_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_DATA_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_DATA_REQUEST_MODEL = "gen_ai.request.model"


def _observability_disabled() -> bool:
    """True when ATMAN_OBS_LEVEL opts out of any sentry_sdk import."""
    return os.getenv("ATMAN_OBS_LEVEL", "minimal").strip().lower() == "off"


@contextmanager
def ai_chat_span(provider: str, model: str, *, op_name: str = "chat") -> Generator[Any, None, None]:
    """Span for a single LLM chat completion.

    Sets gen_ai.operation.name, gen_ai.provider.name, gen_ai.request.model.
    """
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op=f"gen_ai.{op_name}", name=f"{provider}/{model}") as span:
        span.set_data(GEN_AI_DATA_OPERATION_NAME, op_name)
        span.set_data(GEN_AI_DATA_PROVIDER_NAME, provider)
        span.set_data(GEN_AI_DATA_REQUEST_MODEL, model)
        yield span


@contextmanager
def ai_embeddings_span(provider: str, model: str) -> Generator[Any, None, None]:
    """Span for an embedding call (single batch)."""
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op="gen_ai.embeddings", name=f"{provider}/{model}") as span:
        span.set_data(GEN_AI_DATA_OPERATION_NAME, "embeddings")
        span.set_data(GEN_AI_DATA_PROVIDER_NAME, provider)
        span.set_data(GEN_AI_DATA_REQUEST_MODEL, model)
        yield span


@contextmanager
def ai_rerank_span(
    provider: str, model: str, docs_in: int, top_n: int
) -> Generator[Any, None, None]:
    """Span for a reranking call."""
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op="gen_ai.rerank", name=f"{provider}/{model}") as span:
        span.set_data(GEN_AI_DATA_OPERATION_NAME, "rerank")
        span.set_data(GEN_AI_DATA_PROVIDER_NAME, provider)
        span.set_data(GEN_AI_DATA_REQUEST_MODEL, model)
        span.set_data("rerank.docs_in", docs_in)
        span.set_data("rerank.top_n", top_n)
        yield span


@contextmanager
def memory_span(action: str, namespace: str, **data: Any) -> Generator[Any, None, None]:
    """Span for a memory operation (recall / store / extract / reflect / clarify)."""
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op=f"memory.{action}", name=f"{action}:{namespace}") as span:
        span.set_data("memory.action", action)
        span.set_data("memory.namespace", namespace)
        for key, value in data.items():
            span.set_data(key, value)
        yield span


@contextmanager
def db_span(
    system: str,
    operation: str,
    *,
    collection: str | None = None,
    **data: Any,
) -> Generator[Any, None, None]:
    """Span for a database operation (postgresql / qdrant)."""
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    name = f"{system}.{operation}"
    if collection:
        name = f"{name}:{collection}"

    with sentry_sdk.start_span(op="db", name=name) as span:
        span.set_data("db.system", system)
        span.set_data("db.operation", operation)
        if collection is not None:
            span.set_data("db.collection", collection)
        for key, value in data.items():
            span.set_data(key, value)
        yield span


@contextmanager
def pipeline_span(op: str, description: str = "") -> Generator[Any, None, None]:
    """Generic span for an internal pipeline stage (NER, RAG, affect, etc.).

    Use the specific helpers (ai_chat_span, memory_span, db_span) where possible.
    pipeline_span is the escape hatch for stages that don't map to a named helper.
    """
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op=op, name=description or op) as span:
        yield span


@contextmanager
def job_scope(tags: dict[str, str]) -> Generator[None, None, None]:
    """Isolation scope for a background job, setting Sentry error-grouping tags.

    Wraps the job body in sentry_sdk.isolation_scope() so each job's errors
    are captured independently. Falls back to a no-op when observability is
    off or sentry_sdk is unavailable.
    """
    if _observability_disabled():
        yield
        return

    scope_cm = None
    with contextlib.suppress(Exception):
        import sentry_sdk

        scope_cm = sentry_sdk.isolation_scope()

    if scope_cm is None:
        yield
        return

    with scope_cm as scope:
        for key, value in tags.items():
            scope.set_tag(key, value)
        yield


@contextmanager
def cron_span(monitor_slug: str) -> Generator[Any, None, None]:
    """Context manager that wraps a cron job body with a Sentry span.

    Unlike cron_checkin in adapters.observability.sentry, this emits a regular
    span suitable for inclusion in a parent transaction.
    """
    if _observability_disabled():
        yield None
        return

    import sentry_sdk

    with sentry_sdk.start_span(op="cron", name=monitor_slug) as span:
        span.set_data("cron.monitor_slug", monitor_slug)
        yield span


def set_conversation_id(session_id: str) -> None:
    """Tag the current span and scope with gen_ai.conversation.id = session_id.

    Enables Sentry's Explore > Conversations view to group all turns from one
    session into a single conversation replay.
    """
    if _observability_disabled():
        return
    import sentry_sdk

    span = sentry_sdk.get_current_span()
    if span is not None:
        span.set_data("gen_ai.conversation.id", session_id)
    sentry_sdk.set_tag("conversation_id", session_id)
