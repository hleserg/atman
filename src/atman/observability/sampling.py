"""Trace sampling strategy for Atman.

AI-related operations (gen_ai.*, /api/agent, /api/chat, /api/memory) are
always sampled at 1.0 to ensure full trace coverage of the critical path.
Everything else defaults to 10% in non-debug levels.
"""

from __future__ import annotations

from typing import Any

_AI_ROUTES: frozenset[str] = frozenset({"/api/agent", "/api/chat", "/api/memory"})


def _traces_sampler(sampling_context: dict[str, Any]) -> float:
    """Return a sample rate based on transaction type.

    Boosted to 1.0 for AI operations; inherits parent decision when available;
    falls back to 0.1 for everything else.
    """
    custom: dict[str, Any] = sampling_context.get("custom_sampling_context", {})
    transaction_context: dict[str, Any] = sampling_context.get("transaction_context", {})

    if "gen_ai.operation.name" in custom:
        return 1.0

    name: str = transaction_context.get("name", "")
    if any(route in name for route in _AI_ROUTES):
        return 1.0

    parent_sampled: bool | None = sampling_context.get("parent_sampled")
    if parent_sampled is not None:
        return 1.0 if parent_sampled else 0.0

    return 0.1
