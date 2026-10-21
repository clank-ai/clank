"""Design 0002 §2.3 (decision 0113): an event type declares whether its events need the owner's attention, and each
event carries it, as recorded, as heard, as published live and as read back; the events page says it; questions asked
and the cloud's spending limits and refusals are the first that need the owner (design 0016 §11, §17)."""

import pytest

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, Event, EventLog, EventType, EventTypes
from clank.kernel.store import Store
from tools.eventsdoc import render

TYPES = EventTypes(
    [
        EventType("thing.happened", "A thing happened."),
        EventType("thing.broke", "A thing broke.", attention=True),
        EventType("thing.ticked", "A live tick.", live=True, attention=True),
    ]
)
YOU = Actor(kind="user", via="console")


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, TYPES)


def test_an_event_carries_its_types_attention_as_recorded_heard_and_read_back(log: EventLog) -> None:
    heard: list[Event] = []
    log.subscribe(heard.append)
    quiet = log.record("thing.happened", summary="a thing happened", actor=YOU)
    loud = log.record("thing.broke", summary="a thing broke", actor=YOU)
    live = log.publish_live("thing.ticked", summary="a tick", actor=YOU)
    assert (quiet.attention, loud.attention, live.attention) == (False, True, True)
    assert [event.attention for event in heard] == [False, True, True]
    assert [event.attention for event in log.after(0)] == [False, True]
    assert [event.attention for event in log.latest()] == [True, False]


def test_the_events_page_says_which_types_need_the_owner() -> None:
    text = render(TYPES)
    assert "| `thing.broke` | kept, needs you | A thing broke. | none |" in text
    assert "| `thing.happened` | kept | A thing happened. | none |" in text


def test_questions_asked_and_the_clouds_limits_and_refusals_need_the_owner() -> None:
    types = {event_type.name: event_type for event_type in registry.event_types().all()}
    assert types["question.asked"].attention
    for name in ("gateway.limit_warned", "gateway.limit_reached", "gateway.cloud_refused"):
        assert types[name].attention, name
    assert not types["gateway.cost"].attention
    assert not types["question.answered"].attention
    assert not types["runtime.slot"].attention
