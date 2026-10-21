"""Time: the kernel's one clock, and the one way times are written (design 0002 §2.3).

Times are aware and in UTC. As text they are ISO 8601 with milliseconds and a `Z`, so they sort in time order as text,
in SQLite and in files alike. Tests use `FakeClock`, which moves only when a test moves it.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Anything that tells the time."""

    def now(self) -> datetime:
        """The current time, in UTC."""
        ...


class SystemClock:
    """The computer's own clock."""

    def now(self) -> datetime:
        """The current time, in UTC."""
        return datetime.now(UTC)


class FakeClock:
    """A clock for tests: it stands still until moved."""

    def __init__(self, start: datetime) -> None:
        self._now = _aware(start)

    def now(self) -> datetime:
        """The time the test set."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self._now += timedelta(seconds=seconds)

    def set(self, moment: datetime) -> None:
        """Move the clock to a given time."""
        self._now = _aware(moment)


def to_text(moment: datetime) -> str:
    """A time as Clank writes it: `2026-10-11T12:00:00.123Z`."""
    return _aware(moment).astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_text(text: str) -> datetime:
    """A time written by `to_text`, back as an aware time in UTC."""
    return _aware(datetime.fromisoformat(text)).astimezone(UTC)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a time needs a time zone (Clank keeps every time in UTC)")
    return moment
