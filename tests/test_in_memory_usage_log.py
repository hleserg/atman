"""Unit tests for :class:`InMemoryUsageLog` (memory usage telemetry)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from atman.adapters.memory.in_memory_usage_log import InMemoryUsageLog
from atman.core.ports.memory_usage_log import MemoryUsageRecord, UsageType


def _record(
    session_id, memory_id, *, memory_type: str = "fact", usage_type: UsageType = UsageType.SURFACED
) -> MemoryUsageRecord:
    return MemoryUsageRecord(
        timestamp=datetime.now(UTC),
        session_id=session_id,
        memory_type=memory_type,
        memory_id=memory_id,
        usage_type=usage_type,
        context="test",
    )


def test_log_and_count() -> None:
    log = InMemoryUsageLog()
    sid, mid = uuid4(), uuid4()
    log.log_usage(_record(sid, mid))
    log.log_usage(_record(sid, uuid4()))
    assert log.count() == 2


def test_get_usage_for_session_filters_by_session_and_memory_type() -> None:
    log = InMemoryUsageLog()
    sid, other = uuid4(), uuid4()
    log.log_usage(_record(sid, uuid4(), memory_type="fact"))
    log.log_usage(_record(sid, uuid4(), memory_type="experience"))
    log.log_usage(_record(other, uuid4(), memory_type="fact"))

    all_for_session = log.get_usage_for_session(sid)
    assert len(all_for_session) == 2

    only_facts = log.get_usage_for_session(sid, memory_type="fact")
    assert len(only_facts) == 1
    first = only_facts[0]
    assert first is not None
    assert first.memory_type == "fact"


def test_get_usage_for_memory_returns_most_recent_first_capped_by_limit() -> None:
    log = InMemoryUsageLog()
    mid = uuid4()
    for _ in range(3):
        log.log_usage(_record(uuid4(), mid))
    # Add an unrelated record
    log.log_usage(_record(uuid4(), uuid4()))

    most_recent = log.get_usage_for_memory(mid, limit=2)
    assert len(most_recent) == 2
    assert all(r.memory_id == mid for r in most_recent)


def test_get_usage_summary_counts_per_usage_type() -> None:
    log = InMemoryUsageLog()
    sid = uuid4()
    log.log_usage(_record(sid, uuid4(), usage_type=UsageType.SURFACED))
    log.log_usage(_record(sid, uuid4(), usage_type=UsageType.SURFACED))
    other_type = next((u for u in UsageType if u is not UsageType.SURFACED), UsageType.SURFACED)
    log.log_usage(_record(sid, uuid4(), usage_type=other_type))

    summary = log.get_usage_summary(sid)
    assert summary[UsageType.SURFACED.value] == 2
    if other_type is not UsageType.SURFACED:
        assert summary[other_type.value] == 1


def test_clear_empties_log() -> None:
    log = InMemoryUsageLog()
    log.log_usage(_record(uuid4(), uuid4()))
    log.clear()
    assert log.count() == 0
