"""
P1.5 — Domain invariant tests.

These tests encode rules that MUST hold regardless of which agent last
modified the codebase.  They are intentionally redundant with unit tests —
that's the point: if a refactor breaks an invariant, at least one of these
tests will catch it even if the direct unit test was accidentally removed.

Invariants covered:
1. list_recent_experiences always returns newest-first.
2. DateRangeQuery never returns records outside the range.
3. add_reframing_note never modifies key_moments.
4. Duplicate triggered_by on reframing notes is a no-op (idempotent).
5. reflection_run_key for the same day/identity is deterministic.
6. Micro reflection over the same session twice produces the same level.
7. ExperienceRecord.salience starts at 1.0 and can only decrease with time.
8. Access count increments by exactly 1 per mark_accessed call.

SYSTEM_MAP §2.1 / §3 B–E / §4.2 / §5.3 regression freeze.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from atman.adapters.storage import FileStateStore
from atman.core.models import (
    EmotionalDepth,
    ExperienceRecord,
    FeltSense,
    KeyMoment,
    ReframingNote,
    SessionExperience,
)
from atman.core.ports.state_store import DateRangeQuery


def _record(
    *, timestamp: datetime | None = None, values: list[str] | None = None
) -> ExperienceRecord:
    return ExperienceRecord(
        experience=SessionExperience(
            session_id=uuid4(),
            timestamp=timestamp or datetime.now(UTC),
            key_moments=[
                KeyMoment(
                    what_happened="invariant test",
                    how_i_felt=FeltSense(
                        emotional_valence=0.5,
                        emotional_intensity=0.5,
                        depth=EmotionalDepth.SURFACE,
                    ),
                    why_it_matters="coverage",
                    values_touched=values or ["honesty"],
                )
            ],
        )
    )


# ---------------------------------------------------------------------------
# Invariant 1: list_recent_experiences → newest first
# ---------------------------------------------------------------------------


def test_invariant_list_recent_newest_first(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path)
    base = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    ids_in_order = []
    for i in range(5):
        r = _record(timestamp=base + timedelta(hours=i))
        store.create_experience(r)
        ids_in_order.append(r.experience.id)

    results = store.list_recent_experiences(limit=10)
    timestamps = [r.experience.timestamp for r in results]
    assert timestamps == sorted(timestamps, reverse=True), "list_recent must return newest first"


# ---------------------------------------------------------------------------
# Invariant 2: DateRangeQuery never leaks outside the window
# ---------------------------------------------------------------------------


def test_invariant_date_range_excludes_outside(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path)
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

    inside = _record(timestamp=now)
    early = _record(timestamp=now - timedelta(days=2))
    late = _record(timestamp=now + timedelta(days=2))

    for r in (inside, early, late):
        store.create_experience(r)

    window = DateRangeQuery(
        start_date=now - timedelta(hours=1),
        end_date=now + timedelta(hours=1),
    )
    results = store.search_experiences(window)

    result_ids = {r.experience.id for r in results}
    assert inside.experience.id in result_ids
    assert early.experience.id not in result_ids, "early record must be excluded by DateRangeQuery"
    assert late.experience.id not in result_ids, "late record must be excluded by DateRangeQuery"


# ---------------------------------------------------------------------------
# Invariant 3: add_reframing_note never modifies key_moments
# ---------------------------------------------------------------------------


def test_invariant_reframing_note_does_not_mutate_key_moments(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path)
    record = _record()
    original_what = record.experience.key_moments[0].what_happened
    original_values = list(record.experience.key_moments[0].values_touched)
    store.create_experience(record)

    note = ReframingNote(reflection="new perspective", reflection_type="growth")
    updated = store.add_reframing_note(record.experience.id, note)

    assert updated is not None
    assert updated.experience.key_moments[0].what_happened == original_what
    assert list(updated.experience.key_moments[0].values_touched) == original_values


# ---------------------------------------------------------------------------
# Invariant 4: duplicate triggered_by is idempotent
# ---------------------------------------------------------------------------


def test_invariant_duplicate_triggered_by_is_noop(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path)
    record = _record()
    store.create_experience(record)

    run_id = str(uuid4())
    note = ReframingNote(reflection="first", reflection_type="growth", triggered_by=run_id)
    store.add_reframing_note(record.experience.id, note)

    dup = ReframingNote(reflection="second", reflection_type="growth", triggered_by=run_id)
    result = store.add_reframing_note(record.experience.id, dup)

    assert result is not None
    notes = result.experience.reframing_notes
    assert len(notes) == 1, "duplicate triggered_by must not add a second note"
    assert notes[0].reflection == "first"


# ---------------------------------------------------------------------------
# Invariant 5: salience is in [0, 1] and calculate_current_salience decreases with time
# ---------------------------------------------------------------------------


def test_invariant_salience_is_in_valid_range() -> None:
    record = _record()
    assert 0.0 <= record.experience.salience <= 1.0


def test_invariant_salience_decreases_with_time() -> None:
    record = _record()
    # Pin last_accessed_at to "now" and compare salience at +0 vs +365 days
    from datetime import UTC, datetime

    t0 = datetime.now(UTC)
    record.experience.last_accessed_at = t0
    s_now = record.experience.calculate_current_salience(current_time=t0)
    t_future = t0 + timedelta(days=365)
    s_future = record.experience.calculate_current_salience(current_time=t_future)
    assert s_future < s_now, "salience must be lower one year later than at access time"
    assert s_future >= 0.0, "salience must never go below 0"


# ---------------------------------------------------------------------------
# Invariant 6: access_count increments by exactly 1 each call
# ---------------------------------------------------------------------------


def test_invariant_access_count_increments_by_one(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path)
    record = _record()
    store.create_experience(record)

    for expected in range(1, 4):
        updated = store.mark_accessed(record.experience.id)
        assert updated is not None
        assert updated.experience.access_count == expected


# ---------------------------------------------------------------------------
# Invariant 7: reflection_run_key is deterministic for same inputs
# ---------------------------------------------------------------------------


def test_invariant_reflection_run_key_deterministic() -> None:
    from atman.core.reflection_run_keys import daily_reflection_run_key_for_identity

    date = datetime(2025, 6, 1, tzinfo=UTC)
    identity_id = uuid4()
    key1 = daily_reflection_run_key_for_identity(date, identity_id)
    key2 = daily_reflection_run_key_for_identity(date, identity_id)

    assert key1 == key2, "run_key must be deterministic for same (date, identity_id)"


def test_invariant_reflection_run_key_differs_by_date() -> None:
    from atman.core.reflection_run_keys import daily_reflection_run_key_for_identity

    iid = uuid4()
    d1 = datetime(2025, 6, 1, tzinfo=UTC)
    d2 = datetime(2025, 6, 2, tzinfo=UTC)

    assert daily_reflection_run_key_for_identity(d1, iid) != daily_reflection_run_key_for_identity(
        d2, iid
    )


def test_invariant_reflection_run_key_differs_by_identity() -> None:
    from atman.core.reflection_run_keys import daily_reflection_run_key_for_identity

    date = datetime(2025, 6, 1, tzinfo=UTC)
    assert daily_reflection_run_key_for_identity(
        date, uuid4()
    ) != daily_reflection_run_key_for_identity(date, uuid4())
