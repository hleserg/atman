"""init_observability() — single Sentry initialization entry point for Atman.

Call once at process startup (FastAPI lifespan, CLI main, daemon __main__).
Level is read from ATMAN_OBS_LEVEL env var when not passed explicitly.

Levels
------
off       — no-op; sentry_sdk is never imported; zero overhead
minimal   — errors + AI-route traces at 100 %, 10 % elsewhere, no profiling  (prod default)
debug     — 100 % tracing + profiling + Spotlight  (dev default)
verbose   — debug + SDK self-logging + attach_stacktrace + locals
full      — debug mode for experiments: send_default_pii=True, all prompts captured,
            all NLP/RAG/DB data in spans, no filtering. NOT for production use.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

ObsLevel = Literal["off", "minimal", "debug", "verbose", "full"]
_VALID_LEVELS: frozenset[str] = frozenset({"off", "minimal", "debug", "verbose", "full"})

_LOG = logging.getLogger(__name__)

_initialized: bool = False
_current_level: str = "off"


def is_enabled() -> bool:
    """Return True when Sentry was successfully initialised (level != off, DSN set)."""
    return _initialized


def is_full_mode() -> bool:
    """Return True when running at ATMAN_OBS_LEVEL=full (debug-only: all data captured)."""
    return _current_level == "full"


def _normalize_level(level: str | None) -> str:
    """Return a lowercase, stripped observability level name."""
    if level is None:
        return os.getenv("ATMAN_OBS_LEVEL", "minimal").strip().lower()
    return level.strip().lower()


def init_observability(level: str | None = None) -> None:
    """Initialise Sentry observability at the requested level.

    Args:
        level: One of "off" | "minimal" | "debug" | "verbose" | "full".
               Defaults to the ATMAN_OBS_LEVEL env var, or "minimal" when unset.
    """
    global _initialized, _current_level

    level = _normalize_level(level)

    # True no-op — must not import sentry_sdk at all
    if level == "off":
        return

    if level not in _VALID_LEVELS:
        _LOG.warning(
            "ATMAN_OBS_LEVEL=%r is not a recognised level; falling back to 'minimal'",
            level,
        )
        level = "minimal"

    if _initialized:
        return

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    # ---- everything below this line may import sentry_sdk ----
    import sentry_sdk
    from sentry_sdk.integrations import Integration
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.httpx import HttpxIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    from atman.observability.sampling import _traces_sampler
    from atman.observability.scrubbing import (
        _make_before_send,
        _make_before_send_transaction,
        make_event_scrubber,
    )

    # full mode captures everything including prompts/completions/PII
    _include_prompts = level == "full"
    _log_level = logging.DEBUG if level == "full" else logging.WARNING

    integrations: list[Integration] = [
        AsyncioIntegration(),
        HttpxIntegration(),
        LoggingIntegration(level=_log_level, event_level=logging.ERROR),
    ]

    # PydanticAIIntegration: auto-instruments Agent.run(), model calls, tool executions.
    # include_prompts=True only in full mode (captures all prompt/completion text).
    try:
        from sentry_sdk.integrations.pydantic_ai import PydanticAIIntegration

        try:
            integrations.append(
                PydanticAIIntegration(
                    include_prompts=_include_prompts,
                    handled_tool_call_exceptions=True,
                )
            )
        except TypeError:
            # Older sentry-sdk without handled_tool_call_exceptions support — fall back.
            _LOG.debug(
                "PydanticAIIntegration: handled_tool_call_exceptions not supported, using defaults"
            )
            integrations.append(PydanticAIIntegration(include_prompts=_include_prompts))
    except ImportError:
        pass

    # AnthropicIntegration: include_prompts=True in full mode.
    try:
        from sentry_sdk.integrations.anthropic import AnthropicIntegration

        integrations.append(AnthropicIntegration(include_prompts=_include_prompts))
    except ImportError:
        pass

    # In full mode we skip event filtering so nothing is dropped.
    _before_send = None if level == "full" else _make_before_send(level)
    _before_send_tx = None if level == "full" else _make_before_send_transaction(level)

    common: dict[str, object] = {
        "dsn": dsn,
        "environment": os.getenv("SENTRY_ENVIRONMENT", "production"),
        "release": os.getenv("SENTRY_RELEASE") or None,
        "integrations": integrations,
        "event_scrubber": make_event_scrubber(level),
        "before_send": _before_send,
        "before_send_transaction": _before_send_tx,
        "send_default_pii": level == "full",
        "enable_logs": True,
    }

    if level == "minimal":
        common.update(
            {
                # traces_sampler overrides sample_rate — AI ops always at 1.0,
                # everything else falls back to 0.1 (see sampling._traces_sampler)
                "traces_sampler": _traces_sampler,
                "profiles_sample_rate": 0.0,
                "max_breadcrumbs": 20,
                "debug": False,
            }
        )
    elif level == "debug":
        common.update(
            {
                "traces_sample_rate": 1.0,  # 100 % in dev — full waterfall visible in Spotlight
                "profiles_sample_rate": 0.1,
                "max_breadcrumbs": 50,
                "debug": False,
                "spotlight": True,
            }
        )
    elif level == "verbose":
        common.update(
            {
                "traces_sample_rate": 1.0,  # 100 % in verbose — capture everything
                "profiles_sample_rate": 1.0,
                "max_breadcrumbs": 100,
                "debug": True,
                "spotlight": True,
                "attach_stacktrace": True,
                "include_local_variables": True,
            }
        )
    else:  # full — debug-only mode, no filtering, all prompts/data captured
        common.update(
            {
                "traces_sample_rate": 1.0,
                "stream_gen_ai_spans": True,  # AI spans streamed separately (avoids payload limits)
                "profiles_sample_rate": 1.0,
                "max_breadcrumbs": 500,
                "debug": True,
                "spotlight": True,
                "attach_stacktrace": True,
                "include_local_variables": True,
                "max_value_length": 100_000,  # don't truncate long strings in spans
            }
        )

    sentry_sdk.init(**common)  # type: ignore[arg-type]
    _initialized = True
    _current_level = level
    _LOG.info("Sentry initialised (level=%s, env=%s)", level, common["environment"])
