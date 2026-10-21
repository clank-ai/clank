"""Design 0002 §2.3: times are kept in UTC as text that sorts in time order, and tests move a fake clock by hand."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from clank.kernel.clock import FakeClock, from_text, to_text


def test_the_fake_clock_moves_only_when_told() -> None:
    clock = FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC))
    first = clock.now()
    assert clock.now() == first
    clock.advance(90)
    assert clock.now() == first + timedelta(seconds=90)


def test_times_round_trip_through_text_in_utc() -> None:
    local = datetime(2026, 10, 11, 8, 0, 0, 123000, tzinfo=timezone(timedelta(hours=-4)))
    assert to_text(local) == "2026-10-11T12:00:00.123Z"
    assert from_text("2026-10-11T12:00:00.123Z") == local


def test_times_as_text_sort_in_time_order() -> None:
    times = [
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2025, 12, 31, 23, 59, tzinfo=UTC),
        datetime(2026, 10, 11, tzinfo=UTC),
    ]
    assert sorted(to_text(moment) for moment in times) == [to_text(moment) for moment in sorted(times)]


def test_a_time_without_a_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        to_text(datetime(2026, 10, 11, 12, 0))
