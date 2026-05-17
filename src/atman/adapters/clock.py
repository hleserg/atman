"""Concrete ClockPort implementations.

The default `SystemClock` and the test-only `FrozenClock` live in the
adapters layer because they are concrete implementations of the
`ClockPort` interface defined in `atman.core.ports.clock`. Core code
should depend on the port, not on these implementations.
"""

from datetime import UTC, datetime


class SystemClock:
    """Wall-clock implementation (UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Fixed instant for deterministic tests."""

    def __init__(self, frozen: datetime) -> None:
        self._frozen = frozen if frozen.tzinfo is not None else frozen.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._frozen
