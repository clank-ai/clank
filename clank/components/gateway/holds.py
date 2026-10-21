"""The gateway's holds (design 0012 §9.4, decision 0055): a paused session's next model requests wait in the gateway
until the owner resumes it.

A session is paused by the service (the Guide's `p`, or a Watch for rule set to pause), never by the agent (decision
0084: the gateway's routes for it take the service's local token). From then on each request the session sends, and
each of its subagents' at any depth, is **held**: `take` registers it at the gateway's door, before its slot is woken or
waited for, so the request in flight when the pause came finishes and OpenCode runs that step's calls first. A request
names only its direct parent (`x-parent-session-id`), so the gateway keeps the parent of every session whose requests it
saw (`seen`, the newest `PARENTS_KEPT`), and a pause on the root holds a subagent's subagent too; the nearest pause up
the parents holds it.

A held request is answered at once by the server (200, an event stream), and `keep` gives what it says while it waits:
a comment line at once, saying why, then one each time `keep_seconds` (15) passes, well within the 300 s OpenCode waits
without bytes before it gives up and asks again (OpenCode's `provider/provider.ts`). Comment lines (`: ...`) are part of
the event stream's format, and every client reading it passes over them. The wait is given (`wait`), so the tests run it
on a fake clock. `resume` ends the pause, and each request it held goes on to the engine on its own stream (one that
another pause up its parents also holds stays held by that one). `release` is a note's (§9.4): it closes the requests
held of the session itself, never a subagent's (an empty step ends a subagent's run, and its parent would read an empty
answer), and only those held before the note was sent (`before`): a request held since may already carry the note,
and an empty step in its place would end the run with the note unanswered. `keep` then raises `Released`: the server
ends that stream as an empty step. The pause stays, so the request that carries the note is held until the owner
resumes.

The pauses outlive a restart of the gateway (`file`, the home's `state/holds.json`), since a pause ends only when the
owner resumes (decision 0055); the requests held do not, as a restart cuts every request in flight, and OpenCode's next
asking is held again. Everything here runs on the gateway's event loop, so nothing is locked. At most `PAUSES_KEPT`
pauses are kept; past that the oldest that holds nothing is let go.
"""

import json
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio

from clank.kernel.clock import Clock, SystemClock, from_text, to_text

KEEP_SECONDS = 15.0  # a comment line at least this often while held: OpenCode gives up after 300 s without bytes
PARENTS_KEPT = 4096  # sessions whose parent is kept, the newest heard
PAUSES_KEPT = 256
DEPTH = 32  # parents walked up at most (a loop in what was heard ends there)
Wait = Callable[[anyio.Event, float], Awaitable[bool]]  # wait for the event, at most so long: whether it was set


class Released(Exception):
    """A note closed the held request: the server ends it as an empty step (§9.4)."""


@dataclass
class Pause:
    """A paused session: since when, and who paused it ("you (console)", "Clank (watch for)")."""

    session: str
    since: str
    by: str


@dataclass
class Held:
    """A request held: its id, the session that sent it and that session's parent, the paused session that holds it and
    who paused that one, since when, and once it went on, until when and how (resumed or released)."""

    id: str
    session: str
    parent: str
    holder: str
    by: str
    since: str
    event: anyio.Event = field(default_factory=anyio.Event)
    until: str = ""
    how: str = ""

    @property
    def seconds(self) -> float:
        """How long it was held, once it no longer is (0 before)."""
        if not self.until:
            return 0.0
        return round((from_text(self.until) - from_text(self.since)).total_seconds(), 1)

    def facts(self) -> dict[str, Any]:
        """As the activity and the records show it: the session that holds it, who paused that one, since when; once
        it went on, until when, how (resumed, released, or left: its client left) and for how many seconds."""
        found: dict[str, Any] = {"session": self.holder, "by": self.by, "since": self.since}
        if self.until:
            found.update(until=self.until, how=self.how or "left", seconds=self.seconds)
        return found


async def _wait(event: anyio.Event, seconds: float) -> bool:
    with anyio.move_on_after(seconds):
        await event.wait()
    return event.is_set()


class Holds:
    """The paused sessions and the requests held."""

    def __init__(
        self,
        keep_seconds: float = KEEP_SECONDS,
        wait: Wait = _wait,
        clock: Clock | None = None,
        file: Path | None = None,
    ) -> None:
        self.keep_seconds = keep_seconds
        self._wait = wait
        self._clock = clock if clock is not None else SystemClock()
        self._file = file
        self._pauses: dict[str, Pause] = self._read()
        self._held: dict[str, Held] = {}
        self._parents: dict[str, str] = {}

    def seen(self, session: str, parent: str) -> None:
        """A request of `session` named `parent` as its parent: kept, so its subagents are held with its root."""
        if not session or not parent or session == parent:
            return
        self._parents.pop(session, None)
        self._parents[session] = parent
        for oldest in list(self._parents)[: max(0, len(self._parents) - PARENTS_KEPT)]:
            del self._parents[oldest]

    def holding(self, session: str, parent: str = "") -> str:
        """The paused session that holds a request of `session` (whose parent is `parent`): its own pause, else the
        nearest up its parents; "" when none does."""
        self.seen(session, parent)
        found = session
        for _ in range(DEPTH):
            if not found:
                return ""
            if found in self._pauses:
                return found
            found = self._parents.get(found, "")
        return ""

    def take(self, id: str, session: str, parent: str = "") -> Held | None:
        """A request comes: held (and registered at once, so a resume before its stream begins is not missed) when a
        pause holds it, else None."""
        holder = self.holding(session, parent)
        if not holder:
            return None
        held = Held(id, session, parent, holder, self.by(holder), self._now())
        self._held[id] = held
        return held

    async def keep(self, held: Held) -> AsyncGenerator[bytes, None]:
        """What a held streamed request says while it waits: a comment line at once, then one each `keep_seconds`,
        until its pause ends; `Released` when a note closed it. It is forgotten when this ends, however it ends."""
        try:
            by = f" by {held.by}" if held.by else ""
            yield (f": held by Clank: session {held.holder} is paused{by} since {held.since}; this request goes to the "
                   "model when it is resumed\n\n").encode()  # fmt: skip
            while not await self._wait(held.event, self.keep_seconds):
                yield b": held\n\n"
            if held.how == "released":
                raise Released(held.id)
        finally:
            self.drop(held)

    async def wait(self, held: Held) -> None:
        """A held request not streamed: it waits without a word until its pause ends; `Released` when a note closed
        it. It is forgotten when this ends."""
        try:
            while not await self._wait(held.event, self.keep_seconds):
                pass
            if held.how == "released":
                raise Released(held.id)
        finally:
            self.drop(held)

    def drop(self, held: Held) -> None:
        """Forget a held request (its client left, or it went on)."""
        if self._held.get(held.id) is held:
            del self._held[held.id]
        if not held.until:
            held.until = self._now()

    def pause(self, session: str, by: str) -> dict[str, Any]:
        """Pause a session: its next requests, and its subagents', are held. A session paused already keeps its first
        pause (`already`)."""
        found = self._pauses.get(session)
        already = found is not None
        if found is None:
            found = self._pauses[session] = Pause(session, self._now(), by)
            self._bound()
            self._write()
        return {**self._shown(found), "already": already}

    def resume(self, session: str) -> dict[str, Any] | None:
        """End a session's pause: each request it held goes on (unless another pause up its parents holds it); the
        pause as it was, with how many it let go (`held`), or None when it was not paused."""
        found = self._pauses.pop(session, None)
        if found is None:
            return None
        self._write()
        went = 0
        for held in [each for each in self._held.values() if each.holder == session]:
            holder = self.holding(held.session, held.parent)
            if holder:
                held.holder, held.by = holder, self.by(holder)
                continue
            self._end(held, "resumed")
            went += 1
        return {"session": found.session, "since": found.since, "by": found.by, "held": went}

    def release(self, session: str, before: str = "") -> int:
        """A note was sent to the session: its own requests held now are closed (as empty steps), and the pause stays;
        how many. With `before` (when the note was about to be sent), only those held before then: one held since may
        carry the note, and stays held until the owner resumes."""
        until = from_text(before) if before else None
        closed = [
            held for held in self._held.values()
            if held.session == session and not held.event.is_set()
            and (until is None or from_text(held.since) < until)
        ]  # fmt: skip
        for held in closed:
            self._end(held, "released")
        return len(closed)

    def view(self) -> list[dict[str, Any]]:
        """Each pause, oldest first: the session, since when, by whom, and the requests it holds now, each with its
        session, its parent, since when and for how many seconds."""
        return [self._shown(pause) for pause in self._pauses.values()]

    def by(self, holder: str) -> str:
        """Who paused a session ("" when it is not paused)."""
        found = self._pauses.get(holder)
        return found.by if found is not None else ""

    def _shown(self, pause: Pause) -> dict[str, Any]:
        now = self._clock.now()
        held = [
            {"id": each.id, "session": each.session, "parent": each.parent, "since": each.since,
             "seconds": round((now - from_text(each.since)).total_seconds(), 1)}
            for each in self._held.values()
            if each.holder == pause.session and not each.event.is_set()
        ]  # fmt: skip
        return {"session": pause.session, "since": pause.since, "by": pause.by, "held": held}

    def _end(self, held: Held, how: str) -> None:
        held.how, held.until = how, self._now()
        held.event.set()

    def _now(self) -> str:
        return to_text(self._clock.now())

    def _bound(self) -> None:
        holding = {held.holder for held in self._held.values()}
        for session in list(self._pauses):
            if len(self._pauses) <= PAUSES_KEPT:
                return
            if session not in holding:
                del self._pauses[session]

    def _read(self) -> dict[str, Pause]:
        if self._file is None:
            return {}
        try:
            found = json.loads(self._file.read_text(encoding="utf-8"))
            return {
                str(each["session"]): Pause(str(each["session"]), str(each["since"]), str(each.get("by") or ""))
                for each in found["pauses"]
            }
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _write(self) -> None:
        if self._file is None:
            return
        pauses = [{"session": each.session, "since": each.since, "by": each.by} for each in self._pauses.values()]
        self._file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._file.with_name(f".{self._file.name}.writing")
        temporary.write_text(json.dumps({"pauses": pauses}, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self._file)
