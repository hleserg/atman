"""Sentry observability for the HF Space demo.

Mirrors the public surface of `src/atman/adapters/observability/sentry.py`
but keeps the demo standalone (no `atman.*` imports). All helpers no-op
silently when `SENTRY_DSN` is not set or `sentry-sdk` is not installed,
so the Space stays runnable without observability credentials.

Setup on HuggingFace Spaces:
    Settings → Variables and secrets → New secret:
        SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>
    Optional:
        SENTRY_ENVIRONMENT=demo          (default)
        SENTRY_TRACES_SAMPLE_RATE=0.2    (default)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

_LOG = logging.getLogger(__name__)
_initialized = False

P = ParamSpec("P")
R = TypeVar("R")


def is_enabled() -> bool:
    return _initialized


def init_sentry_from_env() -> bool:
    """Initialize Sentry SDK from `SENTRY_DSN`. Returns True on success."""
    global _initialized
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        _LOG.info("SENTRY_DSN not set — observability disabled.")
        return False
    environment = os.getenv("SENTRY_ENVIRONMENT", "demo")
    try:
        import sentry_sdk
        from sentry_sdk.integrations.httpx import HttpxIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        _LOG.warning("sentry-sdk not installed — observability disabled.")
        return False

    sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2"))
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=os.getenv("SPACE_ID") or os.getenv("HF_SPACE_ID"),
        traces_sample_rate=sample_rate,
        profiles_sample_rate=0.0,
        integrations=[
            HttpxIntegration(),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        send_default_pii=False,
        max_breadcrumbs=100,
    )
    _initialized = True
    _LOG.info("Sentry initialized (env=%s, sample_rate=%.2f)", environment, sample_rate)
    return True


@contextmanager
def pipeline_span(op: str, description: str = "") -> Generator[None, None, None]:
    """Child span for a pipeline stage. No-op when Sentry is off."""
    if not _initialized:
        yield
        return
    import sentry_sdk

    with sentry_sdk.start_span(op=op, description=description or op):
        yield


def capture_silent_exception(exc: BaseException, context: str = "", **extra: Any) -> None:
    """Capture an exception that was handled (logged, fallback applied) to Sentry."""
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
    except Exception:  # nosec B110 — observability must never raise
        pass


def traced(op: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator: wrap a Gradio handler in a Sentry span + capture unhandled errors.

    On exception: report to Sentry, then re-raise so Gradio surfaces the error
    to the user (UX > silent failure).
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with pipeline_span(op, fn.__name__):
                try:
                    return cast(R, fn(*args, **kwargs))
                except Exception as exc:
                    if _initialized:
                        with suppress(Exception):
                            import sentry_sdk

                            sentry_sdk.capture_exception(exc)
                    raise

        return wrapper

    return decorator
