"""Tests for SessionWorkingMemory (E24.9)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from atman.core.models import FactRecord, KeyMoment, SessionExperience
from atman.core.models.experience import EmotionalDepth, FeltSense
from atman.core.services.session_working_memory import SessionWorkingMemory


def _fact(content: str = "fact body") -> FactRecord:
    return FactRecord(content=content, source="test")


def _experience() -> SessionExperience:
    moment = KeyMoment(
        what_happened="something significant",
        when=datetime.now(UTC),
        how_i_felt=FeltSense(
            emotional_valence=0.4,
            emotional_intensity=0.6,
            depth=EmotionalDepth.MEANINGFUL,
        ),
        why_it_matters="it shaped my view",
    )
    return SessionExperience(session_id=uuid4(), key_moments=[moment])


def test_add_fact_then_has_and_get():
    wm = SessionWorkingMemory()
    fact = _fact()
    wm.add_fact(fact)
    assert wm.has(fact.id)
    cached = wm.get(fact.id)
    assert cached is not None
    assert cached.item_type == "fact"
    assert cached.access_count >= 2  # add + get


def test_add_fact_is_idempotent():
    wm = SessionWorkingMemory()
    fact = _fact()
    wm.add_fact(fact)
    wm.add_fact(fact)
    assert wm.size() == 1


def test_add_experience_records_summary():
    wm = SessionWorkingMemory()
    exp = _experience()
    wm.add_experience(exp)
    cached = wm.get(exp.id)
    assert cached is not None
    assert cached.item_type == "experience"
    assert "something significant" in cached.content


def test_add_experience_is_idempotent():
    wm = SessionWorkingMemory()
    exp = _experience()
    wm.add_experience(exp)
    wm.add_experience(exp)
    assert wm.size() == 1


def test_add_facts_batch_returns_only_new():
    wm = SessionWorkingMemory()
    fact_a = _fact("A")
    fact_b = _fact("B")
    new = wm.add_facts_batch([fact_a, fact_b, fact_a])
    assert {f.id for f in new} == {fact_a.id, fact_b.id}
    # Re-running should return nothing new
    assert wm.add_facts_batch([fact_a]) == []


def test_list_cached_filters_by_type():
    wm = SessionWorkingMemory()
    fact = _fact()
    exp = _experience()
    wm.add_fact(fact)
    wm.add_experience(exp)
    facts = wm.list_cached("fact")
    experiences = wm.list_cached("experience")
    assert len(facts) == 1
    assert len(experiences) == 1
    assert wm.list_cached() == [*facts, *experiences] or wm.list_cached() == [
        *experiences,
        *facts,
    ]


def test_clear_resets_cache():
    wm = SessionWorkingMemory()
    wm.add_fact(_fact())
    wm.clear()
    assert wm.size() == 0


def test_lru_eviction_when_over_capacity():
    wm = SessionWorkingMemory(max_size=2)
    fact_a = _fact("A")
    fact_b = _fact("B")
    fact_c = _fact("C")
    wm.add_fact(fact_a)
    wm.add_fact(fact_b)
    wm.add_fact(fact_c)
    assert wm.size() == 2
    assert not wm.has(fact_a.id)
    assert wm.has(fact_b.id)
    assert wm.has(fact_c.id)


def test_get_returns_none_for_unknown():
    wm = SessionWorkingMemory()
    assert wm.get(uuid4()) is None
