"""Centralized Sentry SDK initialization and observability helpers for Atman.

Usage:
    Call ``init_sentry_from_env()`` once at process startup (factory.py, cli entry points).
    All other helpers gracefully no-op when SENTRY_DSN is not set or sentry-sdk is missing.

Environment variables:
    SENTRY_DSN              ? Sentry project DSN; if unset, all helpers are disabled
    SENTRY_ENVIRONMENT      ? "development" | "staging" | "production" (default: production)
    SENTRY_TRACES_SAMPLE_RATE ? float 0..1, default 0.2
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any, cast

_LOG = logging.getLogger(__name__)

_initialized = False


def is_enabled() -> bool:
    """Return True when SENTRY_DSN is set and SDK is initialized."""
    return _initialized


def init_sentry_from_env() -> bool:
    """Read SENTRY_DSN from env and initialize the SDK.  Returns True on success.

    Delegates to ``atman.observability.init_observability`` so only one init
    system is active.  Legacy callers can keep using this function.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    with suppress(Exception):
        from atman.observability import init_observability
        from atman.observability import is_enabled as obs_enabled

        level = os.getenv("ATMAN_OBS_LEVEL", "minimal").strip().lower()
        init_observability(level)
        global _initialized
        _initialized = obs_enabled()
        return _initialized
    # Honour explicit opt-out even when the new module failed to import.
    if os.getenv("ATMAN_OBS_LEVEL", "").strip().lower() == "off":
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
        _LOG.warning("sentry-sdk not installed ? install sentry-sdk[httpx,asyncio] to enable")
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
        max_breadcrumbs=200,
        enable_logs=True,
    )
    _initialized = True
    _LOG.info("Sentry initialized (env=%s, sample_rate=%.2f)", environment, sample_rate)
    return True


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def set_agent_scope(agent_id: str, session_id: str | None = None) -> None:
    """Tag all subsequent events in this scope with agent_id / session_id."""
    if not _sentry_sdk_active():
        return
    try:
        import sentry_sdk

        sentry_sdk.set_tag("agent_id", agent_id)
        sentry_sdk.set_user({"id": agent_id})
        if session_id:
            sentry_sdk.set_tag("session_id", session_id)
    except Exception:  # nosec B110 ? observability helpers must never raise
        pass


def set_session_tag(session_id: str) -> None:
    """Update session_id tag mid-session (call after start_session returns)."""
    if not _sentry_sdk_active():
        return
    try:
        import sentry_sdk

        sentry_sdk.set_tag("session_id", session_id)
    except Exception:  # nosec B110 ? observability helpers must never raise
        pass


_slog_hook_installed = False


def install_slog_breadcrumb_hook() -> None:
    """Chain a Sentry breadcrumb emitter onto the slog display hook.

    Every ``slog()`` event becomes a Sentry breadcrumb automatically.
    Preserves any already-registered hook (e.g., the Rich-console hook in
    live_chat.py) ? both hooks receive the event in order.

    Safe to call when Sentry is not initialized: the inner hook checks
    ``_initialized`` at call time and skips breadcrumb emission.
    Idempotent ? calling multiple times installs the hook only once.
    """
    global _slog_hook_installed
    if _slog_hook_installed:
        return
    from atman.core.session_log import get_display_hook, set_display_hook

    _previous = get_display_hook()

    def _breadcrumb_hook(event: str, data: dict[str, Any]) -> None:
        if _sentry_sdk_active():
            attrs = {k: str(v) for k, v in data.items() if k != "ts"}
            attrs["event"] = event
            try:
                import sentry_sdk.logger as _sl

                if event == "job_failed":
                    _sl.error(f"atman.{event}", attributes=attrs)
                elif event in ("session_error", "reflect_error"):
                    _sl.warning(f"atman.{event}", attributes=attrs)
                else:
                    _sl.info(f"atman.{event}", attributes=attrs)
            except Exception:  # nosec B110 ? observability helpers must never raise
                pass
            try:
                import sentry_sdk

                sentry_sdk.add_breadcrumb(
                    category=f"atman.{event}",
                    message=event,
                    level="error" if event == "job_failed" else "info",
                    data=attrs,
                )
            except Exception:  # nosec B110 ? observability helpers must never raise
                pass
        if _previous is not None:
            _previous(event, data)

    set_display_hook(_breadcrumb_hook)
    _slog_hook_installed = True


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


@contextmanager
def session_transaction(session_id: str, agent_id: str) -> Generator[None, None, None]:
    """Root Sentry transaction spanning the entire session lifecycle.

    Wraps ``start_session`` ? all turns ? ``finish_session`` so every LLM
    call and NLP job appears as a child span in the same trace.
    """
    if not _sentry_sdk_active():
        yield
        return
    import sentry_sdk

    with sentry_sdk.start_transaction(
        op="session",
        name="session_lifecycle",
    ) as tx:
        tx.set_tag("agent_id", agent_id)
        tx.set_tag("session_id", session_id)
        yield


@contextmanager
def pipeline_span(op: str, description: str = "") -> Generator[None, None, None]:
    """Child span for a pipeline stage (NER, RAG, affect, ?). No-op when Sentry is off."""
    if not _sentry_sdk_active():
        yield
        return
    import sentry_sdk

    with sentry_sdk.start_span(op=op, description=description or op):
        yield


@contextmanager
def maintenance_job_span(job_name: str, agent_id: str = "") -> Generator[None, None, None]:
    """Child span for a single maintenance job execution."""
    if not _sentry_sdk_active():
        yield
        return
    import sentry_sdk

    with sentry_sdk.start_span(op="maintenance.job", description=job_name) as span:
        span.set_data("agent_id", agent_id)
        span.set_data("job_name", job_name)
        yield


@contextmanager
def reflection_span(reflection_type: str) -> Generator[None, None, None]:
    """Span for a single reflection run (micro / daily / deep)."""
    if not _sentry_sdk_active():
        yield
        return
    import sentry_sdk

    with sentry_sdk.start_span(op="reflection", description=reflection_type) as span:
        span.set_data("reflection_type", reflection_type)
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
    if not _sentry_sdk_active():
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if context:
                scope.set_tag("silent_context", context)
            for k, v in extra.items():
                scope.set_extra(k, str(v))
            sentry_sdk.capture_exception(exc)
    except Exception:  # nosec B110 ? observability helpers must never raise
        pass


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _metric_tags(tags: dict[str, str] | None) -> dict[str, str]:
    return tags or {}


def _emit_metric_distribution(name: str, value: float, unit: str, tags: dict[str, str]) -> None:
    import sentry_sdk

    try:
        sentry_sdk.metrics.distribution(name, value, unit=unit, attributes=tags)
    except (AttributeError, TypeError):
        cast(Any, sentry_sdk.metrics.distribution)(name, value, unit=unit, tags=tags)


def _emit_metric_gauge(name: str, value: float, tags: dict[str, str]) -> None:
    import sentry_sdk

    try:
        sentry_sdk.metrics.gauge(name, value, attributes=tags)
    except (AttributeError, TypeError):
        cast(Any, sentry_sdk.metrics.gauge)(name, value, tags=tags)


def _emit_metric_count(name: str, value: float, tags: dict[str, str]) -> None:
    import sentry_sdk

    try:
        sentry_sdk.metrics.count(name, value, attributes=tags)
    except (AttributeError, TypeError):
        incr = getattr(sentry_sdk.metrics, "incr", None)
        if incr is not None:
            cast(Any, incr)(name, value, tags=tags)


def metric_distribution(
    name: str, value: float, unit: str = "none", tags: dict[str, str] | None = None
) -> None:
    """Emit a distribution metric (histograms, latencies, sizes)."""
    if not _sentry_sdk_active():
        return
    with suppress(Exception):
        _emit_metric_distribution(name, value, unit, _metric_tags(tags))


def metric_gauge(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Emit a gauge metric (queue depths, counts at a point in time)."""
    if not _sentry_sdk_active():
        return
    with suppress(Exception):
        _emit_metric_gauge(name, value, _metric_tags(tags))


def metric_increment(name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
    """Increment a counter metric."""
    if not _sentry_sdk_active():
        return
    with suppress(Exception):
        _emit_metric_count(name, value, _metric_tags(tags))


# ---------------------------------------------------------------------------
# Cron monitoring
# ---------------------------------------------------------------------------


def _sentry_sdk_active() -> bool:
    """True when Sentry was initialized via this adapter or init_observability()."""
    if _initialized:
        return True
    try:
        from atman.observability import is_enabled as obs_enabled

        return obs_enabled()
    except ImportError:
        return False


@contextmanager
def cron_checkin(monitor_slug: str) -> Generator[None, None, None]:
    """Context manager that emits in_progress / ok / error check-ins for a cron job.

    Usage::

        with cron_checkin("atman-maintenance"):
            run_maintenance_batch()
    """
    if not _sentry_sdk_active():
        yield
        return
    import sentry_sdk

    with sentry_sdk.monitor(monitor_slug=monitor_slug):
        yield


# ---------------------------------------------------------------------------
# Full-mode debug helpers (ATMAN_OBS_LEVEL=full only)
# ---------------------------------------------------------------------------


def _is_full_mode() -> bool:
    """True when ATMAN_OBS_LEVEL=full — debug-only mode with no PII filtering."""
    with suppress(Exception):
        from atman.observability.sentry_init import is_full_mode

        return is_full_mode()
    return False


def capture_db_state(table: str, rows: list[Any], *, context: str = "read") -> None:
    """Capture database rows as a Sentry context snapshot + JSON attachment.

    Only active in ATMAN_OBS_LEVEL=full. Attaches all rows to the current
    transaction so the full DB state before/after each operation is visible
    in Sentry Issues and Traces.

    Args:
        table:   Table name (used in context key and filename).
        rows:    List of row dicts / dataclass-like objects with __dict__.
        context: "read" | "before_write" | "after_write" — shown in context key.
    """
    if not _sentry_sdk_active() or not _is_full_mode():
        return
    with suppress(Exception):
        import json

        import sentry_sdk

        # Inline context: row count + first 5 rows for quick inspection
        sample = rows[:5] if rows else []
        sentry_sdk.set_context(
            f"db.{context}.{table}",
            {"row_count": len(rows), "sample": sample},
        )
        if not rows:
            return
        scope = sentry_sdk.get_current_scope()
        scope.add_attachment(
            bytes=json.dumps(rows, default=str, ensure_ascii=False).encode("utf-8"),
            filename=f"db_{context}_{table}.json",
            content_type="application/json",
            add_to_transactions=True,
        )


def capture_system_prompt(prompt_text: str, bundle_meta: dict[str, Any]) -> None:
    """Capture the full system prompt as a Sentry attachment + context.

    Only active in ATMAN_OBS_LEVEL=full. Stores the rendered identity/narrative
    bundle so every session's starting context is visible in Sentry.

    Args:
        prompt_text: Full rendered memory bundle string.
        bundle_meta: Metadata dict (has_identity, has_narrative, etc.).
    """
    if not _sentry_sdk_active() or not _is_full_mode():
        return
    with suppress(Exception):
        import sentry_sdk

        sentry_sdk.set_context(
            "atman.system_prompt",
            {"chars": len(prompt_text), **bundle_meta},
        )
        scope = sentry_sdk.get_current_scope()
        scope.add_attachment(
            bytes=prompt_text.encode("utf-8", "replace"),
            filename="system_prompt.txt",
            content_type="text/plain",
            add_to_transactions=True,
        )
