"""PII scrubbing helpers for Sentry events.

Extends sentry-sdk's DEFAULT_DENYLIST with Atman-specific keys that must
never reach Sentry SaaS: memory contents, reflections, embeddings, prompts.
"""

from __future__ import annotations

import traceback
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


def make_event_scrubber(_level: str) -> Any:
    """Return an EventScrubber configured with ATMAN_DENYLIST.

    In verbose mode we still scrub — developer must opt-in to raw payloads
    via ATMAN_SEND_PROMPTS=1 at the SDK level if needed.
    """
    from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber  # lazy import

    denylist: list[str] = list(DEFAULT_DENYLIST) + ATMAN_EXTRA_KEYS
    return EventScrubber(denylist=denylist, recursive=True)


_REFLECTION_OVERLOAD_LOGGER = "atman.reflection.overload"
_TESTS_PATH_MARKERS: tuple[str, ...] = ("/tests/", "\\tests\\")
_OPERATIONAL_ERROR_MESSAGE_MARKERS: tuple[str, ...] = (
    "post-write scheduler raised",
    "Failed to enqueue",
)


def _is_pytest_frame_path(path: str) -> bool:
    if any(marker in path for marker in _TESTS_PATH_MARKERS):
        return True
    normalized = path.replace("\\", "/")
    return "/tests/" in normalized or normalized.startswith("tests/")


def _event_logger_name(event: dict[str, Any]) -> str:
    return str(event.get("logger") or "")


def _event_level(event: dict[str, Any]) -> str:
    return str(event.get("level") or "").lower()


def _event_message(event: dict[str, Any]) -> str:
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        return str(logentry.get("formatted") or logentry.get("message") or "")
    return str(event.get("message") or "")


def _frame_paths_from_event(event: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    exception = event.get("exception")
    if not isinstance(exception, dict):
        return paths
    for exc_value in exception.get("values") or []:
        if not isinstance(exc_value, dict):
            continue
        stacktrace = exc_value.get("stacktrace")
        if not isinstance(stacktrace, dict):
            continue
        for frame in stacktrace.get("frames") or []:
            if not isinstance(frame, dict):
                continue
            for key in ("abs_path", "filename", "module"):
                value = frame.get(key)
                if value:
                    paths.append(str(value))
    return paths


def _frame_paths_from_hint(hint: dict[str, Any]) -> list[str]:
    exc_info = hint.get("exc_info")
    if not isinstance(exc_info, tuple) or len(exc_info) < 3 or exc_info[2] is None:
        return []
    return [summary.filename for summary in traceback.extract_tb(exc_info[2])]


def _iter_stack_frame_paths(event: dict[str, Any], hint: dict[str, Any]) -> list[str]:
    return _frame_paths_from_event(event) + _frame_paths_from_hint(hint)


def _stack_frame_in_tests(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    return any(_is_pytest_frame_path(path) for path in _iter_stack_frame_paths(event, hint))


def _is_operational_error_log(event: dict[str, Any]) -> bool:
    if _event_level(event) not in ("error", "fatal"):
        return False
    message = _event_message(event)
    return any(marker in message for marker in _OPERATIONAL_ERROR_MESSAGE_MARKERS)


def _should_drop_operational_signal(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    if _event_logger_name(event) == _REFLECTION_OVERLOAD_LOGGER:
        return True
    if _stack_frame_in_tests(event, hint):
        return True
    return _is_operational_error_log(event)


def _make_before_send(level: str) -> Any:
    """Factory for before_send callback — drop operational / test noise."""

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        if _should_drop_operational_signal(event, hint):
            return None
        return event

    return before_send


_HEALTH_ROUTES: frozenset[str] = frozenset({"/health", "/healthz", "/metrics", "/livez", "/readyz"})


def _make_before_send_transaction(_level: str) -> Any:
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
