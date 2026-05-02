"""Clock port for reproducible time in services and tests."""

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    """Domain clock — inject :class:`SystemClock` or :class:`FrozenClock`."""

    def now(self) -> datetime:
        """Current instant in the domain timeline."""
        ...
