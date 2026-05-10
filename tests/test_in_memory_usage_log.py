"""Tests for InMemoryUsageLog (E24.10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from atman.adapters.memory.in_memory_usage_log import InMemoryUsageLog
from atman.core.ports.memory_usage_log import MemoryUsageRecord, UsageType


def _record(
    *,
    session_id=None,
    memory_id=None,
    memory_type: str = "fact",
    usage_type: UsageType = UsageType.SURFACED,
) -> MemoryUsageRecord:
    return MemoryUsageRecord(
        timestamp=datetime.now(UTC),
        session_id=session_id or uuid4(),
        memory_type=memory_type,
        memory_id=memory_id or uuid4(),
        usage_type=usage_type,
        context="test usage",
    )


def test_log_and_count():
    log = InMemoryUsageLog()
    assert log.count() == 0
    log.log_usage(_record())
    log.log_usage(_record())
    assert log.count() == 2


def test_get_usage_for_session_filters_by_session_and_memory_type():
    log = InMemoryUsageLog()
    session_a = uuid4()
    session_b = uuid4()
    log.log_usage(_record(session_id=session_a, memory_type="fact"))
    log.log_usage(_record(session_id=session_a, memory_type="experience"))
    log.log_usage(_record(session_id=session_b, memory_type="fact"))

    all_a = log.get_usage_for_session(session_a)
    assert len(all_a) == 2

    facts_only = log.get_usage_for_session(session_a, memory_type="fact")
    assert len(facts_only) == 1
    assert facts_only[0].memory_type == "fact"


def test_get_usage_for_memory_returns_recent_first_with_limit():
    log = InMemoryUsageLog()
    memory_id = uuid4()
    other_id = uuid4()
    for _ in range(3):
        log.log_usage(_record(memory_id=memory_id))
    log.log_usage(_record(memory_id=other_id))

    recent = log.get_usage_for_memory(memory_id, limit=2)
    assert len(recent) == 2
    assert all(r.memory_id == memory_id for r in recent)


def test_get_usage_summary_counts_by_usage_type():
    log = InMemoryUsageLog()
    session_id = uuid4()
    log.log_usage(_record(session_id=session_id, usage_type=UsageType.SURFACED))
    log.log_usage(_record(session_id=session_id, usage_type=UsageType.SURFACED))
    log.log_usage(_record(session_id=session_id, usage_type=UsageType.CITED))
    log.log_usage(_record(session_id=uuid4(), usage_type=UsageType.SURFACED))

    summary = log.get_usage_summary(session_id)
    assert summary == {"surfaced": 2, "cited": 1}


def test_clear_resets_log():
    log = InMemoryUsageLog()
    log.log_usage(_record())
    assert log.count() == 1
    log.clear()
    assert log.count() == 0


def test_usage_type_enum_values():
    assert UsageType.SURFACED == "surfaced"
    assert UsageType.ACCESSED == "accessed"
    assert UsageType.CITED == "cited"
    assert UsageType.INFLUENCED == "influenced"
