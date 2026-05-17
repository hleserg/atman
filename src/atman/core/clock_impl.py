"""Core-level clock utilities (timezone normalisation).

Concrete `ClockPort` implementations (`SystemClock`, `FrozenClock`) live in
`atman.adapters.clock`. Core code depends on the `ClockPort` interface
defined in `atman.core.ports.clock`; only this small `ensure_utc` helper
remains here because it is a pure-function utility with no dependency on
any clock source.
"""

from datetime import UTC, datetime

__all__ = ["ensure_utc"]


def ensure_utc(dt: datetime) -> datetime:
    """
    Normalize datetimes to UTC for stable comparisons and range queries.

    Naive values are treated as **already in UTC** (wall time), not local time.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
