"""Tests for :mod:`atman.core.services.structured_markers_aggregator`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from atman.adapters.storage.in_memory_reflection_store import InMemoryPatternStore
from atman.core.models.experience import EmotionalDepth, FeltSense, KeyMoment
from atman.core.models.reflection import PatternType, ReflectionLevel
from atman.core.reflection_run_keys import daily_marker_pattern_detection_key
from atman.core.services.structured_markers_aggregator import (
    StructuredMarkersAggregator,
    aggregate_structured_markers,
)


def _moment(
    *,
    markers: dict[str, Any] | None,
    when_offset_sec: int = 0,
) -> KeyMoment:
    return KeyMoment(
        what_happened="x",
        when=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=when_offset_sec),
        how_i_felt=FeltSense(
            emotional_valence=0.0,
            emotional_intensity=0.5,
            depth=EmotionalDepth.MEANINGFUL,
        ),
        why_it_matters="t",
        structured_markers=markers,
    )


# ---------------------------------------------------------------------------
# aggregate_structured_markers (pure)
# ---------------------------------------------------------------------------


def test_aggregate_below_threshold_yields_nothing():
    moments = [_moment(markers={"cognitive_load": "high"}) for _ in range(4)]
    assert aggregate_structured_markers(moments, min_count=5) == []


def test_aggregate_at_threshold_returns_group():
    moments = [_moment(markers={"cognitive_load": "high"}) for _ in range(5)]
    groups = aggregate_structured_markers(moments, min_count=5)
    assert len(groups) == 1
    sig_type, sig_value, bucket = groups[0]
    assert sig_type == "cognitive_load"
    assert sig_value == "high"
    assert len(bucket) == 5


def test_aggregate_mixed_values_each_meeting_threshold():
    moments = [_moment(markers={"cognitive_load": "high"}, when_offset_sec=i) for i in range(5)] + [
        _moment(markers={"cognitive_load": "low"}, when_offset_sec=100 + i) for i in range(5)
    ]
    groups = aggregate_structured_markers(moments, min_count=5)
    types_values = [(t, v) for (t, v, _) in groups]
    assert ("cognitive_load", "high") in types_values
    assert ("cognitive_load", "low") in types_values
    assert len(groups) == 2


def test_aggregate_one_below_one_above():
    moments = [_moment(markers={"cognitive_load": "high"}, when_offset_sec=i) for i in range(5)] + [
        _moment(markers={"cognitive_load": "low"}, when_offset_sec=100)
    ]
    groups = aggregate_structured_markers(moments, min_count=5)
    assert len(groups) == 1
    assert groups[0][1] == "high"


def test_aggregate_ignores_nested_marker_values():
    # dict / list values are noisy fingerprints — skip.
    moments = [_moment(markers={"context_halo": {"foo": "bar"}}) for _ in range(10)]
    assert aggregate_structured_markers(moments, min_count=5) == []


def test_aggregate_handles_missing_or_empty_markers():
    moments = [_moment(markers=None) for _ in range(3)] + [_moment(markers={}) for _ in range(3)]
    assert aggregate_structured_markers(moments, min_count=1) == []


def test_aggregate_boolean_value_normalization():
    moments = [_moment(markers={"agency_level": True}) for _ in range(5)]
    groups = aggregate_structured_markers(moments, min_count=5)
    assert len(groups) == 1
    assert groups[0] == (groups[0][0], "true", groups[0][2])


# ---------------------------------------------------------------------------
# StructuredMarkersAggregator
# ---------------------------------------------------------------------------


def test_analyze_writes_one_pattern_per_qualifying_group():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store, min_count=5)
    moments = [_moment(markers={"cognitive_load": "high"}) for _ in range(5)]

    stored = agg.analyze(moments, run_key="rk-1")

    assert len(stored) == 1
    p = stored[0]
    assert p.detected_by == ReflectionLevel.DAILY
    assert p.pattern_type == PatternType.COGNITIVE  # cognitive_load → COGNITIVE
    assert len(p.based_on_moment_ids) == 5
    assert all(m.id in p.based_on_moment_ids for m in moments)


def test_analyze_idempotent_via_detection_key():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store, min_count=5)
    moments = [_moment(markers={"trust_signal": "broken"}) for _ in range(5)]

    first = agg.analyze(moments, run_key="rk-7")
    second = agg.analyze(moments, run_key="rk-7")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id  # stable id from detection key
    assert len(store.get_all()) == 1


def test_analyze_uses_signal_specific_pattern_type():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store, min_count=5)

    cases = [
        ("cognitive_load", PatternType.COGNITIVE),
        ("agency_level", PatternType.COGNITIVE),
        ("growth_indicator", PatternType.VALUE_BASED),
        ("boundary_event", PatternType.RELATIONAL),
        ("trust_signal", PatternType.RELATIONAL),
        ("unknown_signal", PatternType.BEHAVIOR),  # fallback
    ]
    for sig_type, expected in cases:
        moments = [_moment(markers={sig_type: "v"}) for _ in range(5)]
        stored = agg.analyze(moments, run_key=f"rk-{sig_type}")
        assert len(stored) == 1
        assert stored[0].pattern_type == expected


def test_analyze_no_moments_returns_empty():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store)
    assert agg.analyze([], run_key="rk-x") == []


def test_analyze_no_run_key_returns_empty():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store, min_count=1)
    moments = [_moment(markers={"cognitive_load": "high"})]
    assert agg.analyze(moments, run_key="") == []


def test_detection_key_matches_expected_format():
    store = InMemoryPatternStore()
    agg = StructuredMarkersAggregator(store, min_count=5)
    moments = [_moment(markers={"boundary_event": "set"}) for _ in range(5)]

    stored = agg.analyze(moments, run_key="rk-9")
    expected_key = daily_marker_pattern_detection_key("rk-9", "boundary_event", "set")
    # Re-saving with the same key returns the same row.
    again = store.save_with_detection_key(expected_key, stored[0])
    assert again.id == stored[0].id
