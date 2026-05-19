"""Span helper layer for Atman observability.

Standard context managers wrapping sentry_sdk.start_span so every adapter
and engine uses the same op names and attribute schema.  The CI scanner
(tools/check_instrumentation.py) recognises these names as valid instrumentation.

All helpers degrade gracefully when Sentry is not initialised — the SDK
returns a no-op span automatically in that case.

Recognised by the instrumentation scanner (P3.1) via INSTRUMENTATION_MARKERS:
    ai_chat_span, ai_embeddings_span, ai_rerank_span, memory_span, db_span,
    cron_span
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def ai_chat_span(
    provider: str, model: str, *, op_name: str = "chat"
) -> Generator[Any, None, None]:
    """Span for a single LLM chat completion.

    Sets gen_ai.operation.name, gen_ai.provider.name, gen_ai.request.model.
    """
    import sentry_sdk

    with sentry_sdk.start_span(
        op=f"gen_ai.{op_name}", name=f"{provider}/{model}"
    ) as span:
        span.set_data("gen_ai.operation.name", op_name)
        span.set_data("gen_ai.provider.name", provider)
        span.set_data("gen_ai.request.model", model)
        yield span


@contextmanager
def ai_embeddings_span(
    provider: str, model: str
) -> Generator[Any, None, None]:
    """Span for an embedding call (single batch)."""
    import sentry_sdk

    with sentry_sdk.start_span(
        op="gen_ai.embeddings", name=f"{provider}/{model}"
    ) as span:
        span.set_data("gen_ai.operation.name", "embeddings")
        span.set_data("gen_ai.provider.name", provider)
        span.set_data("gen_ai.request.model", model)
        yield span


@contextmanager
def ai_rerank_span(
    provider: str, model: str, docs_in: int, top_n: int
) -> Generator[Any, None, None]:
    """Span for a reranking call."""
    import sentry_sdk

    with sentry_sdk.start_span(
        op="gen_ai.rerank", name=f"{provider}/{model}"
    ) as span:
        span.set_data("gen_ai.operation.name", "rerank")
        span.set_data("gen_ai.provider.name", provider)
        span.set_data("gen_ai.request.model", model)
        span.set_data("rerank.docs_in", docs_in)
        span.set_data("rerank.top_n", top_n)
        yield span


@contextmanager
def memory_span(
    action: str, namespace: str, **data: Any
) -> Generator[Any, None, None]:
    """Span for a memory operation (recall / store / extract / reflect / clarify)."""
    import sentry_sdk

    with sentry_sdk.start_span(
        op=f"memory.{action}", name=f"{action}:{namespace}"
    ) as span:
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
def cron_span(monitor_slug: str) -> Generator[Any, None, None]:
    """Context manager that wraps a cron job body with a Sentry span.

    Unlike cron_checkin in adapters.observability.sentry, this emits a regular
    span suitable for inclusion in a parent transaction.
    """
    import sentry_sdk

    with sentry_sdk.start_span(op="cron", name=monitor_slug) as span:
        span.set_data("cron.monitor_slug", monitor_slug)
        yield span
