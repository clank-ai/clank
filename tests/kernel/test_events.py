"""Design 0002 §2.3: every event is kept with an id that only grows, is heard by listeners only once it is committed,
can be followed from any point, and tells a client that is too far behind that it missed some."""

from datetime import timedelta

import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.events import CLANK, Actor, Event, EventError, EventLog, EventType, EventTypes, Subject
from clank.kernel.store import Store

TYPES = EventTypes(
    [
        EventType("thing.happened", "A thing happened.", {"size": "How big it was."}),
        EventType("thing.ticked", "A live tick.", live=True),
    ]
)
YOU = Actor(kind="user", via="console")
T1 = Subject(kind="thing", id="t-1")
T2 = Subject(kind="thing", id="t-2")


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, TYPES)


def happened(log: EventLog, size: int, subject: Subject | None = None) -> Event:
    return log.record(
        "thing.happened", summary=f"a thing of size {size}", actor=YOU, subject=subject, data={"size": size}
    )


def record_then_fail(log: EventLog, store: Store) -> None:
    with store.transaction():
        happened(log, 9)
        raise RuntimeError("rolled back")


def test_ids_only_grow_and_an_event_reads_back_as_written(log: EventLog, clock: FakeClock) -> None:
    first = happened(log, 1)
    clock.advance(5)
    second = happened(log, 2, T1)
    assert first.id is not None
    assert second.id is not None
    assert second.id > first.id
    assert log.after(0) == [first, second]
    assert second.actor.describe() == "you (console)"
    assert CLANK.describe() == "Clank"


def test_an_undeclared_type_is_refused(log: EventLog) -> None:
    with pytest.raises(EventError, match="not a declared event type"):
        log.record("thing.unknown", summary="?", actor=YOU)


def test_a_live_only_event_reaches_listeners_but_is_never_kept(log: EventLog) -> None:
    heard: list[Event] = []
    log.subscribe(heard.append)
    log.publish_live("thing.ticked", summary="tick", actor=CLANK)
    assert [(event.type, event.id) for event in heard] == [("thing.ticked", None)]
    assert log.after(0) == []
    with pytest.raises(EventError, match="live only"):
        log.record("thing.ticked", summary="tick", actor=CLANK)


def test_following_from_an_id_returns_later_events_filtered_by_type_and_subject(log: EventLog) -> None:
    a = happened(log, 1, T1)
    b = happened(log, 2, T2)
    c = happened(log, 3, T1)
    assert a.id is not None
    assert log.after(a.id) == [b, c]
    assert log.after(0, subject=T1) == [a, c]
    assert log.after(0, types=["thing.happened"], limit=2) == [a, b]
    assert log.last_id() == c.id


def test_listeners_hear_an_event_only_after_its_transaction_commits(log: EventLog, store: Store) -> None:
    heard: list[Event] = []
    log.subscribe(heard.append)
    with store.transaction():
        happened(log, 1)
        assert heard == []
    assert len(heard) == 1
    with pytest.raises(RuntimeError, match="rolled back"):
        record_then_fail(log, store)
    assert len(heard) == 1
    assert len(log.after(0)) == 1


def test_a_listener_that_fails_does_not_stop_the_others(log: EventLog) -> None:
    heard: list[Event] = []

    def broken(event: Event) -> None:
        raise RuntimeError("a broken listener")

    log.subscribe(broken)
    log.subscribe(heard.append)
    happened(log, 1)
    assert len(heard) == 1


def test_an_unsubscribed_listener_hears_nothing_more(log: EventLog) -> None:
    heard: list[Event] = []
    stop = log.subscribe(heard.append)
    happened(log, 1)
    stop()
    happened(log, 2)
    assert len(heard) == 1


def test_the_latest_events_come_newest_first_a_page_at_a_time(log: EventLog) -> None:
    events = [happened(log, size) for size in range(5)]
    page = log.latest(2)
    assert page == [events[4], events[3]]
    assert log.latest(2, before=events[3].id) == [events[2], events[1]]


def test_a_client_behind_the_pruned_events_is_told_it_missed_some(log: EventLog, clock: FakeClock) -> None:
    old = happened(log, 1)
    clock.advance(timedelta(days=40).total_seconds())
    new = happened(log, 2)
    assert log.prune(older_than=clock.now() - timedelta(days=30)) == 1
    assert log.after(0) == [new]
    assert old.id is not None
    assert log.missed(0)
    assert not log.missed(old.id)
