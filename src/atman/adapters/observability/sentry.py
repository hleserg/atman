"""Centralized Sentry SDK initialization and observability helpers for Atman.

Usage:
    Call ``init_sentry_from_env()`` once at process startup (factory.py, cli entry points).
    All other helpers gracefully no-op when SENTRY_DSN is not set or sentry-sdk is missing.

Environment variables:
    SENTRY_DSN              — Sentry project DSN; if unset, all helpers are disabled
    SENTRY_ENVIRONMENT      — "development" | "staging" | "production" (default: production)
    SENTRY_TRACES_SAMPLE_RATE — float 0..1, default 0.2
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

_LOG = logging.getLogger(__name__)

_initialized = False


def is_enabled() -> bool:
    """Return True when SENTRY_DSN is set and SDK is initialized."""
    return _initialized


def init_sentry_from_env() -> bool:
    """Read SENTRY_DSN from env and initialize the SDK.  Returns True on success."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    env = os.getenv("SENTRY_ENVIRONMENT", "production")
    return _init(dsn=dsn, environment=env)


def _init(dsn: str, environment: str = "production", release: str | None = None) -> bool:
    global _initialized
    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        _LOG.warning("sentry-sdk not installed — install sentry-sdk[httpx,asyncio] to enable")
        return False

    sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2"))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=sample_rate,
        profiles_sample_rate=0.05,
        integrations=[
            AsyncioIntegration(),
            HttpxIntegration(),
            # Captures WARNING+ as breadcrumbs, ERROR+ as Sentry events
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        send_default_pii=False,
    )
    _initialized = True
    _LOG.info("Sentry initialized (env=%s, sample_rate=%.2f)", environment, sample_rate)
    return True


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def set_agent_scope(agent_id: str, session_id: str | None = None) -> None:
    """Tag all subsequent events in this scope with agent_id / session_id."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_tag("agent_id", agent_id)
        sentry_sdk.set_user({"id": agent_id})
        if session_id:
            sentry_sdk.set_tag("session_id", session_id)
    except Exception:
        pass


def set_session_tag(session_id: str) -> None:
    """Update session_id tag mid-session (call after start_session returns)."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_tag("session_id", session_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


@contextmanager
def session_transaction(session_id: str, agent_id: str) -> Generator[None, None, None]:
    """Root Sentry transaction spanning the entire session lifecycle.

    Wraps ``start_session`` → all turns → ``finish_session`` so every LLM
    call and NLP job appears as a child span in the same trace.
    """
    if not _initialized:
        yield
        return
    try:
        import sentry_sdk

        with sentry_sdk.start_transaction(
            op="session",
            name="session_lifecycle",
        ) as tx:
            tx.set_tag("agent_id", agent_id)
            tx.set_tag("session_id", session_id)
            yield
            return
    except Exception:
        pass
    yield


@contextmanager
def maintenance_job_span(job_name: str, agent_id: str = "") -> Generator[None, None, None]:
    """Child span for a single maintenance job execution."""
    if not _initialized:
        yield
        return
    try:
        import sentry_sdk

        with sentry_sdk.start_span(op="maintenance.job", description=job_name) as span:
            span.set_data("agent_id", agent_id)
            span.set_data("job_name", job_name)
            yield
            return
    except Exception:
        pass
    yield


@contextmanager
def reflection_span(reflection_type: str) -> Generator[None, None, None]:
    """Span for a single reflection run (micro / daily / deep)."""
    if not _initialized:
        yield
        return
    try:
        import sentry_sdk

        with sentry_sdk.start_span(op="reflection", description=reflection_type) as span:
            span.set_data("reflection_type", reflection_type)
            yield
            return
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# Exception capture
# ---------------------------------------------------------------------------


def capture_silent_exception(exc: BaseException, context: str = "", **extra: Any) -> None:
    """Capture an exception that was silently swallowed (debug-logged) to Sentry.

    Use this in ``except Exception`` blocks where the app intentionally
    continues but the exception is still worth tracking:

        try:
            risky_call()
        except Exception as e:
            _LOG.debug("risky_call failed", exc_info=True)
            capture_silent_exception(e, context="risky_call", session_id=str(sid))
    """
    if not _initialized:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if context:
                scope.set_tag("silent_context", context)
            for k, v in extra.items():
                scope.set_extra(k, str(v))
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def metric_distribution(
    name: str, value: float, unit: str = "none", tags: dict[str, str] | None = None
) -> None:
    """Emit a distribution metric (histograms, latencies, sizes)."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.metrics.distribution(name, value, unit=unit, tags=tags or {})
    except Exception:
        pass


def metric_gauge(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Emit a gauge metric (queue depths, counts at a point in time)."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.metrics.gauge(name, value, tags=tags or {})
    except Exception:
        pass


def metric_increment(name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
    """Increment a counter metric."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.metrics.incr(name, value, tags=tags or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cron monitoring
# ---------------------------------------------------------------------------


@contextmanager
def cron_checkin(monitor_slug: str) -> Generator[None, None, None]:
    """Context manager that emits in_progress / ok / error check-ins for a cron job.

    Usage::

        with cron_checkin("atman-maintenance"):
            run_maintenance_batch()
    """
    if not _initialized:
        yield
        return
    try:
        import sentry_sdk

        with sentry_sdk.monitor(monitor_slug=monitor_slug):
            yield
        return
    except Exception:
        pass
    yield
