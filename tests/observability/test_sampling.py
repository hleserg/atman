"""Tests for _traces_sampler — HLE-240 P1.2 AC-6."""

from __future__ import annotations

import pytest

from atman.observability.sampling import _AI_ROUTES, _traces_sampler


@pytest.mark.parametrize(
    "ctx,expected",
    [
        # gen_ai.operation.name present → always 1.0
        ({"custom_sampling_context": {"gen_ai.operation.name": "chat"}}, 1.0),
        ({"custom_sampling_context": {"gen_ai.operation.name": "embeddings"}}, 1.0),
        # AI route in transaction name → 1.0
        ({"transaction_context": {"name": "/api/agent/start"}}, 1.0),
        ({"transaction_context": {"name": "/api/chat"}}, 1.0),
        ({"transaction_context": {"name": "/api/memory/recall"}}, 1.0),
        # Inherit parent
        ({"parent_sampled": True}, 1.0),
        ({"parent_sampled": False}, 0.0),
        # Default
        ({}, 0.1),
        ({"transaction_context": {"name": "/some/other"}}, 0.1),
        ({"custom_sampling_context": {}}, 0.1),
    ],
)
def test_traces_sampler(ctx: dict, expected: float) -> None:
    assert _traces_sampler(ctx) == expected


def test_ai_routes_set_non_empty():
    assert len(_AI_ROUTES) > 0
    assert "/api/agent" in _AI_ROUTES


def test_gen_ai_beats_other_signals():
    """gen_ai.operation.name takes priority over parent_sampled=False."""
    ctx = {
        "custom_sampling_context": {"gen_ai.operation.name": "rerank"},
        "parent_sampled": False,
    }
    assert _traces_sampler(ctx) == 1.0
