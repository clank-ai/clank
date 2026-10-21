"""Events: everything that happens is an event, kept in the state database as the history (design 0002 §2.3).

An event has an id that only grows, its time, its type, the record it concerns, who caused it, a one-line summary in
plain English, and small data (large content is referenced, never copied). Every type is declared, with its fields and
what it means, by the part that records it: `docs/EVENTS.md` is generated from those declarations, and an undeclared
type is refused. Live-only types (the text a model is writing, progress ticks) are never kept; only listeners hear
them. Listeners hear a kept event once its transaction has committed, so what they hear is there to be read. A type may
declare that its events need the owner's attention (decision 0113), and each event carries it (`attention`). Old events
are pruned after the days the service's settings keep them; a client that resumes from before the pruned point is told
that it missed some, and reloads what it shows.
"""

import json
import logging
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_core import to_jsonable_python

from clank.kernel.clock import Clock, from_text, to_text
from clank.kernel.records import StateKind
from clank.kernel.store import Store

log = logging.getLogger(__name__)
PRUNED_THROUGH = "events.pruned_through"


class Actor(BaseModel):
    """Who caused something: the user through a client, a paired device, an agent's session, a process, or Clank."""

    kind: Literal["user", "device", "session", "process", "clank"] = Field(
        title="Who", description="The user, a paired device, an agent's session, a process, or Clank itself."
    )
    via: str = Field(
        "", title="Through", description="The client, device, session or process it came through, such as console."
    )

    def describe(self) -> str:
        """How the history names the actor: "you (console)", "Clank", "device phone"."""
        if self.kind == "user":
            return f"you ({self.via})" if self.via else "you"
        if self.kind == "clank":
            return f"Clank ({self.via})" if self.via else "Clank"
        return f"{self.kind} {self.via}".strip()


CLANK = Actor(kind="clank")


class Subject(BaseModel):
    """The record an event or a question concerns."""

    kind: str = Field(title="Kind", description="The kind of that record, such as operation.")
    id: str = Field(title="Id", description="That record's id.")


class Event(StateKind):
    """Something that happened."""

    KIND = "event"
    LABEL = "Event"
    HELP = "Something that happened: kept as the history, and sent to every client as it happens."

    id: int | None = Field(None, title="Id", description="A number that only grows; none for a live-only event.")
    time: datetime = Field(title="Time", description="When it happened, in UTC.")
    type: str = Field(title="Type", description="What happened, such as question.asked (docs/EVENTS.md lists them).")
    subject: Subject | None = Field(None, title="Subject", description="The record it concerns, if any.")
    actor: Actor = Field(title="Actor", description="Who caused it.")
    summary: str = Field(title="Summary", description="What happened, in one line of plain English.")
    data: dict[str, Any] = Field(
        default_factory=dict, title="Data", description="The fields its type declares; large content is referenced."
    )
    attention: bool = Field(
        False,
        title="Needs you",
        description="Whether it needs the owner's attention, as its type declares (decision 0113): a client may "
        "notify, with the summary as its title.",
    )


@dataclass(frozen=True)
class EventType:
    """A declared type of event: its name, what it means, its data's fields, whether it is kept, who declares it, and
    whether its events need the owner's attention (decision 0113)."""

    name: str
    help: str
    fields: Mapping[str, str] = field(default_factory=dict)
    live: bool = False
    owner: str = "kernel"
    attention: bool = False


class EventError(Exception):
    """An event that cannot be recorded or published as asked."""


class EventTypes:
    """The declared event types, by name."""

    def __init__(self, types: Iterable[EventType] = ()) -> None:
        self._types: dict[str, EventType] = {}
        for event_type in types:
            self.add(event_type)

    def add(self, event_type: EventType) -> None:
        """Declare a type; a name declared twice is refused."""
        if event_type.name in self._types:
            raise EventError(f"the event type {event_type.name!r} is declared twice")
        self._types[event_type.name] = event_type

    def get(self, name: str) -> EventType:
        """The type of that name; an undeclared name is refused."""
        if name not in self._types:
            raise EventError(f"{name!r} is not a declared event type")
        return self._types[name]

    def all(self) -> list[EventType]:
        """Every type, the kernel's first, then by owner and name."""
        return sorted(self._types.values(), key=lambda t: (t.owner != "kernel", t.owner, t.name))


Listener = Callable[[Event], None]


class EventLog:
    """The history: events kept in the state database, and the listeners that hear them."""

    def __init__(self, store: Store, clock: Clock, types: EventTypes) -> None:
        self._store = store
        self._clock = clock
        self._types = types
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()

    def record(
        self,
        type: str,
        *,
        summary: str,
        actor: Actor,
        subject: Subject | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Event:
        """Keep an event, inside the transaction already open if there is one; listeners hear it after commit."""
        declared = self._types.get(type)
        if declared.live:
            raise EventError(f"{type} is live only: publish it, it is never kept")
        time = self._clock.now()
        values: dict[str, Any] = to_jsonable_python(dict(data or {}))
        with self._store.transaction() as db:
            cursor = db.execute(
                "INSERT INTO events (time, type, subject_kind, subject_id, actor, summary, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    to_text(time),
                    type,
                    subject.kind if subject else None,
                    subject.id if subject else None,
                    actor.model_dump_json(),
                    summary,
                    json.dumps(values, ensure_ascii=False),
                ),
            )
            event = Event(
                id=cursor.lastrowid, time=time, type=type, subject=subject, actor=actor, summary=summary, data=values,
                attention=declared.attention,
            )  # fmt: skip
            self._store.after_commit(lambda: self._tell(event))
        return event

    def publish_live(
        self,
        type: str,
        *,
        summary: str,
        actor: Actor,
        subject: Subject | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Event:
        """Tell the listeners about a live-only event, which is never kept."""
        declared = self._types.get(type)
        if not declared.live:
            raise EventError(f"{type} is kept: record it")
        event = Event(
            time=self._clock.now(),
            type=type,
            subject=subject,
            actor=actor,
            summary=summary,
            data=to_jsonable_python(dict(data or {})),
            attention=declared.attention,
        )
        self._tell(event)
        return event

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Hear every event from now on; returns the function that stops it."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _tell(self, event: Event) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                log.exception("a listener failed on event %s (%s)", event.id, event.type)

    def after(
        self,
        last_id: int,
        *,
        types: Sequence[str] | None = None,
        subject: Subject | None = None,
        limit: int = 1000,
    ) -> list[Event]:
        """The kept events after `last_id`, oldest first, optionally of some types or about one record."""
        where, params = _filters(types, subject)
        rows = self._store.read(
            f"SELECT * FROM events WHERE id > ?{where} ORDER BY id LIMIT ?", (last_id, *params, limit)
        )
        return [self._read(row) for row in rows]

    def latest(
        self,
        limit: int = 100,
        *,
        before: int | None = None,
        types: Sequence[str] | None = None,
        subject: Subject | None = None,
    ) -> list[Event]:
        """The newest kept events, newest first, a page at a time (`before` the oldest id of the previous page)."""
        where, params = _filters(types, subject)
        bound = 2**62 if before is None else before
        rows = self._store.read(
            f"SELECT * FROM events WHERE id < ?{where} ORDER BY id DESC LIMIT ?", (bound, *params, limit)
        )
        return [self._read(row) for row in rows]

    def _read(self, row: Any) -> Event:
        """A kept event, its attention its type's as declared now (a type no longer declared: none)."""
        event = _event(row)
        with suppress(EventError):
            event.attention = self._types.get(event.type).attention
        return event

    def last_id(self) -> int:
        """The id of the newest kept event, or 0."""
        return int(self._store.read("SELECT COALESCE(MAX(id), 0) FROM events")[0][0])

    def missed(self, last_id: int) -> bool:
        """Whether a client that last saw `last_id` missed events that were pruned since."""
        return last_id < self._pruned_through()

    def prune(self, older_than: datetime) -> int:
        """Remove the events older than a time, remembering how far it pruned; returns how many it removed."""
        with self._store.transaction() as db:
            row = db.execute("SELECT COUNT(*), MAX(id) FROM events WHERE time < ?", (to_text(older_than),)).fetchone()
            count, highest = int(row[0]), row[1]
            if count:
                db.execute("DELETE FROM events WHERE id <= ?", (highest,))
                db.execute(
                    "INSERT INTO kernel_meta (key, value) VALUES (?, ?)"
                    " ON CONFLICT (key) DO UPDATE SET value = MAX(CAST(value AS INTEGER), excluded.value)",
                    (PRUNED_THROUGH, str(highest)),
                )
        return count

    def _pruned_through(self) -> int:
        rows = self._store.read("SELECT value FROM kernel_meta WHERE key = ?", (PRUNED_THROUGH,))
        return int(rows[0][0]) if rows else 0


def _filters(types: Sequence[str] | None, subject: Subject | None) -> tuple[str, list[Any]]:
    where = ""
    params: list[Any] = []
    if types:
        where += f" AND type IN ({', '.join('?' for _ in types)})"
        params += list(types)
    if subject is not None:
        where += " AND subject_kind = ? AND subject_id = ?"
        params += [subject.kind, subject.id]
    return where, params


def _event(row: Any) -> Event:
    subject = Subject(kind=row["subject_kind"], id=row["subject_id"]) if row["subject_kind"] else None
    return Event(
        id=row["id"],
        time=from_text(row["time"]),
        type=row["type"],
        subject=subject,
        actor=Actor.model_validate_json(row["actor"]),
        summary=row["summary"],
        data=json.loads(row["data"]),
    )
