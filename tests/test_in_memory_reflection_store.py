"""Extra coverage for in-memory reflection stores."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atman.adapters.storage.in_memory_reflection_store import (
    InMemoryHealthAssessmentStore,
    InMemoryPatternStore,
    InMemoryReflectionEventStore,
)
from atman.core.models.reflection import (
    CriterionAssessment,
    HealthAssessment,
    JahodaCriterion,
    PatternCandidate,
    PatternType,
    ReflectionEvent,
    ReflectionLevel,
)


def test_pattern_store_get_by_level_and_update() -> None:
    store = InMemoryPatternStore()
    p = PatternCandidate(
        pattern_type=PatternType.BEHAVIOR,
        description="d1",
        detected_by=ReflectionLevel.DAILY,
    )
    store.save(p)
    assert store.get(p.id) == p
    assert store.get_by_level(ReflectionLevel.DAILY) == [p]
    assert store.get_by_level(ReflectionLevel.MICRO) == []

    p2 = PatternCandidate(
        id=p.id,
        pattern_type=PatternType.BEHAVIOR,
        description="d2",
        detected_by=ReflectionLevel.DAILY,
        confidence=0.9,
    )
    store.update(p2)
    got = store.get(p.id)
    assert got is not None
    assert got.description == "d2"

    with pytest.raises(ValueError, match="not found"):
        store.update(
            PatternCandidate(
                pattern_type=PatternType.BEHAVIOR,
                description="x",
                detected_by=ReflectionLevel.MICRO,
            )
        )


def test_pattern_store_save_with_detection_key_is_idempotent() -> None:
    store = InMemoryPatternStore()
    key = "k1"
    p1 = PatternCandidate(
        pattern_type=PatternType.BEHAVIOR,
        description="first",
        detected_by=ReflectionLevel.DAILY,
    )
    p2 = PatternCandidate(
        pattern_type=PatternType.BEHAVIOR,
        description="second",
        detected_by=ReflectionLevel.DAILY,
    )
    a = store.save_with_detection_key(key, p1)
    b = store.save_with_detection_key(key, p2)
    assert a.id == b.id
    assert a.description == "first"
    assert len(store.get_all()) == 1


def test_reflection_event_store_upserts_by_run_key() -> None:
    store = InMemoryReflectionEventStore()
    run_key = "daily|v1|2099-01-01|identity|00000000-0000-4000-8000-000000000001"
    store.save(
        ReflectionEvent(
            reflection_level=ReflectionLevel.DAILY,
            reflection_run_key=run_key,
            key_insight="first",
            notes="outcome=daily_ok",
        )
    )
    store.save(
        ReflectionEvent(
            reflection_level=ReflectionLevel.DAILY,
            reflection_run_key=run_key,
            key_insight="second",
            notes="outcome=daily_ok",
        )
    )
    assert len(store.get_all()) == 1
    got = store.get_by_reflection_run_key(run_key)
    assert got is not None
    assert got.key_insight == "second"


def test_reflection_event_store_queries() -> None:
    store = InMemoryReflectionEventStore()
    e1 = ReflectionEvent(
        reflection_level=ReflectionLevel.MICRO,
        experiences_analyzed=[],
        key_insight="a",
    )
    e2 = ReflectionEvent(
        reflection_level=ReflectionLevel.DEEP,
        experiences_analyzed=[],
        key_insight="b",
    )
    store.save(e1)
    store.save(e2)

    assert store.get(e1.id) == e1
    assert len(store.get_all()) == 2
    assert len(store.get_by_level(ReflectionLevel.MICRO)) == 1
    recent = store.get_recent(limit=1)
    assert len(recent) == 1


def _criteria_uniform(score: float) -> dict[JahodaCriterion, CriterionAssessment]:
    criteria: dict[JahodaCriterion, CriterionAssessment] = {}
    for criterion in JahodaCriterion:
        criteria[criterion] = CriterionAssessment(
            criterion=criterion,
            score=score,
            evidence=["e"],
            concerns=["c"],
        )
    return criteria


def test_health_assessment_store_get_latest() -> None:
    store = InMemoryHealthAssessmentStore()
    assert store.get_latest() is None

    a1 = HealthAssessment(
        criteria=_criteria_uniform(0.5),
        overall_score=0.5,
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
    )
    a2 = HealthAssessment(
        criteria=_criteria_uniform(0.8),
        overall_score=0.8,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save(a1)
    store.save(a2)

    latest = store.get_latest()
    assert latest is not None
    assert latest.overall_score == pytest.approx(0.8)
    assert store.get(a2.id) == a2


# --- SYSTEM_MAP §1.5 P2 additions ---


def test_reflection_event_store_get_by_unknown_run_key_returns_none() -> None:
    """SYSTEM_MAP §1.5: querying for an unknown ``reflection_run_key`` returns ``None``."""
    store = InMemoryReflectionEventStore()
    assert store.get_by_reflection_run_key("never|saved|key") is None


def test_pattern_store_get_unknown_pattern_id_returns_none() -> None:
    """SYSTEM_MAP §1.5: ``PatternStore.get`` for an unknown id yields ``None``."""
    from uuid import uuid4

    store = InMemoryPatternStore()
    assert store.get(uuid4()) is None
    assert store.get_all() == []
    assert store.get_by_level(ReflectionLevel.DAILY) == []


def test_health_store_get_unknown_assessment_returns_none() -> None:
    """SYSTEM_MAP §1.5: ``HealthAssessmentStore.get`` returns ``None`` for unknown ids."""
    from uuid import uuid4

    store = InMemoryHealthAssessmentStore()
    assert store.get(uuid4()) is None
    assert store.get_latest() is None
