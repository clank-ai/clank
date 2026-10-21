"""What the gateway does now (design 0004 §2): each request in flight and how far it is, and how the last one that
ended went; the gateway answers it at `GET /activity`, the service at `GET /gateway/activity`, and the console's home
page shows it.

A request is in flight from the moment it comes until its record is kept. Its phase is what it waits for: its slot
(while the slot's model loads or switches), the first token (the engine reads the prompt), or the rest of the answer
(answering), or, when its engine broke off before answering, for the engine to start again. A streamed event that
carries text counts as one token of each kind it carries: its thinking, its answer or a tool call (design 0012 §5.2);
the engines Clank runs send one event per token, of one kind, so the counts are about right (with drafting, an event may
carry several tokens), and once a request ended the engine's own count is its total. The speed is the tokens after the
first over the time since the first came, so the time spent reading the prompt is not counted against it; for the last
request the engine's own figures win when it gives them (llama.cpp's `timings`, then the `usage` of the answer). Each
request names the session that sent it and that session's parent, a subagent's (`sessions.py`, design 0012 §3), "" when
it names none. A request the gateway answers itself (OpenCode's titles) is not shown or counted, and one whose answer
never started streaming (its client left first) is dropped without being counted.

What a request in flight writes now (design 0012 §5.1, §5.3): its time to the first token (`first_ms`), the kind of the
text it wrote last (`newest`: its thinking, its answer or a tool call), and while that is a tool call's, the call being
written (`writing`: its name and the newest `WRITING` characters of its arguments): only the gateway sees a call's
arguments as they stream, since OpenCode holds them until they are complete.

Live (the Requests page's live view): the text of each request in flight is kept as it streams, as parts of three kinds,
its thinking, its answer and its tool calls, and the last request's text is kept after it ends; `live` gives the newest
request's (or a named one's) from a character offset on, so a client asking every half second receives only what is
new. What was asked (the last message the user wrote) comes with it. A text is kept up to `LIVE_CHARS` characters.

One session (design 0012 §3, §7): `now` and `live` asked for a session give only its own requests and its own last that
ended, so its panels show its own (the previous step's prompt, its own text); asked for its subagents too, they give
those of the subagents it started as well (their parent is that session: while a subagent works, its parent waits on its
call and asks nothing), and the last of them all that ended. Each request still names its own session and parent, so a
client tells them apart. The last request of each of the `SESSIONS_KEPT` newest sessions, and apart from them of the
`SESSIONS_KEPT` newest subagents, is kept with its text, so a session's last stays after another session's request ends
and its subagents never push it out. Asked for them (`ended`), a session's own requests that ended are given too,
numbers only, up to `ENDED_KEPT` of each session kept, so the service pairs them with the session's steps (design 0012
§6.1): each with when it began and the ids of the calls its answer made (`calls`), which are OpenCode's. A request whose
engine broke off its streamed answer says so once it ended (`broken`, in the gateway's words), as a refusal says its
reason (`error`): the Monitor's Watch for marks it (design 0012 §8). Everything here runs on the gateway's event loop,
so nothing is locked.

The context window (design 0012 §4): a request that ended names the preset that answered it and keeps the engine's own
`usage` and `timings` as it gave them, so the service reads each figure where that engine's facts say it is reported
(decision 0067); one whose engine broke off its answer (`broken`, above) is never taken for a finished step.
It keeps its time to the first token (`first_ms`), the measure of the engine's reading speed the Guide's costs are read
at (design 0012 §9.1).
And `now` gives each slot's newest request (`slots`): the oldest in flight that reached its engine (an engine that runs
one request at a time reads them in turn), else the last that ended there; a session, its parent, when it began, and
whether it is in flight, so the Monitor says whose conversation the engine holds (design 0012 §3). A request the
gateway refused after routing it (its engine did not answer, or broke off a whole answer) never counts. One that ended
is `gone` once the slot's engine stopped, started again or was switched since (the routes' `generation` of the slot
moved), since the engine then holds no conversation.

The context's parts (design 0012 §4.2, §11 step 12): each request's census (`census.py`, made by the server from its
body) is kept with it (`census`) and given only among its session's requests that ended (`ended`), never in `last`, a
request in flight or the records: whole for the newest that ended well (answered, no error, not stopped by the loop
guard, not broken off, its client there) and those after it, and without its items for the older ones, whose parts'
numbers the Monitor reads for each step's parts; None for a request that has none.

A request held while its session is paused (design 0012 §9.4, `holds.py`) is in flight with the phase `HELD` and its
hold (`held`: the session that holds it, who paused that one, since when), its seconds counted from when it came; once
it goes on, it is timed from then (`restart`), and when it ended its hold is kept with it (`held`, with until when, how
and for how many seconds). One a note closed, answered by the gateway itself, is never counted nor its session's last,
but stays among its session's requests that ended, so its step's flow shows the hold."""

import time
from collections.abc import Callable
from typing import Any

from clank.components.gateway.holds import Held
from clank.components.gateway.loops import LoopGuard
from clank.components.gateway.sessions import session_of

WAITING = "waiting for its slot"
READING = "reading the prompt"
ANSWERING = "answering"
AGAIN = "waiting for its engine to start again"
HELD = "held: its session is paused"
LIVE_CHARS = 400_000
ASKED_CHARS = 2000
SESSIONS_KEPT = 8  # sessions whose last request is kept with its text, and subagents apart from them
ENDED_KEPT = 64  # requests that ended kept of each session kept, numbers only
WRITING = 200  # the newest characters of the arguments of the call being written, in a request in flight
KINDS = ("thinking", "answer", "tool")  # of a streamed answer's text, and of its tokens
Part = list[str]  # [kind, text]: kind is one of KINDS
Ended = tuple[dict[str, Any], list[Part], str]  # a request that ended: its numbers, its text, what was asked


class Activity:
    """The requests in flight, how many have been served, and the last that ended."""

    def __init__(
        self, clock: Callable[[], float] = time.perf_counter, generation: Callable[[str], int] = lambda slot: 0
    ) -> None:
        self._clock = clock
        self._generation = generation  # each slot's engine as the routes count them (`Routes.generation`)
        self._flying: dict[str, tuple[dict[str, Any], float, dict[str, int]]] = {}  # record, began, counts by kind
        self._guards: dict[str, LoopGuard] = {}  # the loop guard reading each streamed answer
        self._holds: dict[str, Held] = {}  # each request held while its session is paused, or that was
        self._served = 0
        self._last: dict[str, Any] | None = None
        self._texts: dict[str, list[Part]] = {}
        self._last_text: Ended | None = None  # the last that ended
        self._sessions: dict[str, Ended] = {}  # the last that ended of each of the newest sessions, oldest first
        self._ended: dict[str, list[dict[str, Any]]] = {}  # each of them: its requests that ended, oldest first
        self._slots: dict[str, tuple[dict[str, Any], int]] = {}  # each slot's last that ended, under which engine
        self._censuses: dict[str, dict[str, Any] | None] = {}  # each request in flight's census (`census.py`)

    def begin(self, record: dict[str, Any], began: float) -> None:
        """A request came: its record (filled in as it goes) and when it began, on the clock."""
        self._flying[record["id"]] = (record, began, dict.fromkeys(KINDS, 0))
        self._texts[record["id"]] = []

    def heard(self, record: dict[str, Any], kind: str, text: str) -> None:
        """Text of its answer, as it streamed: its thinking, its answer or a tool call's."""
        parts = self._texts.get(record["id"])
        if parts is None or not text or sum(len(part[1]) for part in parts) > LIVE_CHARS:
            return
        if parts and parts[-1][0] == kind:
            parts[-1][1] += text
        else:
            parts.append([kind, text])

    def hold(self, record: dict[str, Any], held: Held) -> None:
        """A request held at the gateway's door while its session is paused (design 0012 §9.4): it shows held, with
        its timer, until it goes on."""
        if record["id"] in self._flying:
            self._holds[record["id"]] = held

    def restart(self, record: dict[str, Any], began: float) -> None:
        """A held request went on: from now on it is timed as one that came now, the hold apart (`held`)."""
        found = self._flying.get(record["id"])
        if found is not None:
            self._flying[record["id"]] = (found[0], began, found[2])

    def guard(self, record: dict[str, Any], guard: LoopGuard) -> None:
        """The loop guard that reads a request's streamed answer, so its newest shares show (design 0012 §5.4)."""
        if record["id"] in self._flying:
            self._guards[record["id"]] = guard

    def census(self, record: dict[str, Any], found: dict[str, Any] | None) -> None:
        """A request's census, made from its body (`census.py`): kept with it once it ended, among its session's."""
        if record["id"] in self._flying:
            self._censuses[record["id"]] = found

    def token(self, record: dict[str, Any], kind: str) -> None:
        """One more token of its answer streamed, of a kind: thinking, answer or tool."""
        found = self._flying.get(record["id"])
        if found is not None:
            found[2][kind] = found[2].get(kind, 0) + 1

    def end(self, record: dict[str, Any]) -> None:
        """The request ended and its record is kept: it is the last, unless the gateway answered it itself."""
        found = self._flying.pop(record["id"], None)
        text = self._texts.pop(record["id"], [])
        census = self._censuses.pop(record["id"], None)
        self._guards.pop(record["id"], None)
        self._holds.pop(record["id"], None)
        if found is not None and record.get("local") == "released":
            self._released(record, found[2])
        if found is None or record.get("local"):
            return
        self._served += 1
        self._last = _ended(record, found[2])
        if record.get("slot") and not isinstance(record.get("error"), dict):  # a dict: the gateway refused it
            slot = str(record["slot"])
            self._slots[slot] = (_held(record, flying=False), self._generation(slot))
        if not text and record.get("answer"):
            text = [["answer", str(record["answer"])]]
        self._last_text = (self._last, text, _asked(record))
        session = self._last["session"]
        if session:
            self._sessions.pop(session, None)
            self._sessions[session] = self._last_text
            own = self._ended.pop(session, [])
            self._ended[session] = _slimmed([*own, {**self._last, "census": census}][-ENDED_KEPT:])
            child = bool(self._last["parent"])  # a subagent's: kept apart, so they never push their parent's out
            alike = [key for key, found in self._sessions.items() if bool(found[0]["parent"]) == child]
            for key in alike[: max(0, len(alike) - SESSIONS_KEPT)]:
                del self._sessions[key]
                self._ended.pop(key, None)

    def _released(self, record: dict[str, Any], counts: dict[str, int]) -> None:
        """A held request a note closed (design 0012 §9.4): never counted nor its session's last, but kept among its
        session's requests that ended, so its step's flow shows the hold; sessions that have only such requests are
        kept up to `SESSIONS_KEPT`."""
        session = session_of(record.get("headers"))[0]
        if not session:
            return
        own = self._ended.pop(session, [])
        self._ended[session] = [*own, {**_ended(record, counts), "census": None}][-ENDED_KEPT:]
        strays = [key for key in self._ended if key not in self._sessions]
        for key in strays[: max(0, len(strays) - SESSIONS_KEPT)]:
            del self._ended[key]

    def drop(self, record: dict[str, Any]) -> None:
        """Forget a request whose answer never started streaming; one that ended is already gone."""
        self._flying.pop(record["id"], None)
        self._texts.pop(record["id"], None)
        self._censuses.pop(record["id"], None)
        self._guards.pop(record["id"], None)
        self._holds.pop(record["id"], None)

    def now(self, session: str = "", subagents: bool = False, ended: bool = False) -> dict[str, Any]:
        """The requests in flight, oldest first, how many have been served, and the last that ended; for a session,
        only its own requests and its own last, or with `subagents` its subagents' too and the last of them all; with
        `ended`, the session's own requests that ended, oldest first."""
        moment = self._clock()
        guards, holds, texts = self._guards, self._holds, self._texts
        requests = [
            _flying(
                record,
                moment - began,
                counts,
                guards.get(record["id"]),
                holds.get(record["id"]),
                texts.get(record["id"]),
            )
            for record, began, counts in self._flying.values()
            if not record.get("local") and (not session or _of(record, session, subagents))
        ]
        found = self._session_last(session, subagents) if session else self._last_text
        shown = {"requests": requests, "served": self._served, "last": found[0] if found is not None else None,
                 "slots": self._held()}  # fmt: skip
        if ended and session:
            shown["ended"] = list(self._ended.get(session, []))
        return shown

    def live(self, after: int = 0, id: str = "", session: str = "", subagents: bool = False) -> dict[str, Any]:
        """The newest request in flight (or the named one, or else the last that ended): whether it is in flight, its
        numbers, what was asked, and its text from the character `after` on (`length`: all of it so far); `newest`
        names the newest request in flight (or the last), so a client following one that ended sees the next begin.
        For a session, only its own requests are followed, or with `subagents` its subagents' too; a named request of
        another session is never given."""
        moment = self._clock()
        flying = [
            found
            for found in self._flying.values()
            if not found[0].get("local") and (not session or _of(found[0], session, subagents))
        ]
        last = self._session_last(session, subagents) if session else self._last_text
        newest = max(flying, key=lambda found: found[1])[0]["id"] if flying else ""
        newest = newest or (last[0]["id"] if last is not None else "")
        chosen = next((found for found in flying if found[0]["id"] == id), None) if id else None
        if chosen is None and flying and (not id or last is None or last[0]["id"] != id):
            chosen = max(flying, key=lambda found: found[1])
        if chosen is not None:
            record, began, counts = chosen
            key = record["id"]
            meta = _flying(record, moment - began, counts, self._guards.get(key), self._holds.get(key),
                           self._texts.get(key))  # fmt: skip
            text, asked, now = self._texts.get(record["id"], []), _asked(record), True
        elif last is not None:
            meta, text, asked = last
            now = False
        else:
            return {"id": "", "flying": False, "meta": None, "asked": "", "length": 0, "parts": [], "newest": ""}
        length = sum(len(part[1]) for part in text)
        return {
            "newest": newest,
            "id": meta["id"],
            "flying": now,
            "meta": meta,
            "asked": asked,
            "length": length,
            "parts": _from(text, after),
        }

    def _held(self) -> dict[str, dict[str, Any]]:
        """Each slot's newest request: the oldest in flight that reached its engine, else the last that ended there,
        `gone` when the slot's engine changed since."""
        held = {
            slot: {**found, "gone": engine != self._generation(slot)} for slot, (found, engine) in self._slots.items()
        }
        flying = sorted(((began, record) for record, began, _ in self._flying.values()
                         if record.get("slot") and not record.get("local")), key=lambda pair: pair[0])  # fmt: skip
        for _, record in reversed(flying):
            held[str(record["slot"])] = _held(record, flying=True)
        return held

    def _session_last(self, session: str, subagents: bool) -> Ended | None:
        """The last request of a session that ended, or with `subagents` of it or a subagent it started (of the
        sessions kept)."""
        if not subagents:
            return self._sessions.get(session)
        for found in reversed(self._sessions.values()):
            if session in (found[0]["session"], found[0]["parent"]):
                return found
        return None


def _of(record: dict[str, Any], session: str, subagents: bool) -> bool:
    """Whether a request is a session's own, or with `subagents` a subagent's it started."""
    own, parent = session_of(record.get("headers"))
    return session == own or (subagents and session == parent)


def _slimmed(ended: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A session's requests that ended, each census before the newest that ended well kept without its items."""
    well = [index for index, each in enumerate(ended) if _well(each)]
    if not well:
        return ended
    return [
        {**each, "census": {key: value for key, value in each["census"].items() if key != "items"}}
        if index < well[-1] and isinstance(each.get("census"), dict) and "items" in each["census"]
        else each
        for index, each in enumerate(ended)
    ]


def _well(ended: dict[str, Any]) -> bool:
    """Whether a request ended well: answered, no error, not stopped by the loop guard, not broken off, its client
    there (the Monitor's finished step, design 0012 §4.1)."""
    return ended.get("status") == 200 and not any(ended.get(key) for key in ("error", "looped", "broken", "left"))


def _held(record: dict[str, Any], *, flying: bool) -> dict[str, Any]:
    """A request as the newest of its slot: its id, its session and parent, when it began, whether it is in flight (and
    not `gone`: whether the engine changed since is known when it is given)."""
    session, parent = session_of(record.get("headers"))
    return {"id": record["id"], "session": session, "parent": parent, "time": record.get("time", ""), "flying": flying,
            "gone": False}  # fmt: skip


def _from(parts: list[Part], after: int) -> list[Part]:
    """The parts of a text from a character on."""
    found: list[Part] = []
    start = 0
    for kind, text in parts:
        end = start + len(text)
        if end > after:
            found.append([kind, text[max(0, after - start) :]])
        start = end
    return found


def _asked(record: dict[str, Any]) -> str:
    """The last message the user wrote in a request, briefly."""
    body = record.get("request") or {}
    for message in reversed(body.get("messages") or [] if isinstance(body, dict) else []):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            text = " ".join(str(content or "").split())
            return text[:ASKED_CHARS] + (" …" if len(text) > ASKED_CHARS else "")
    return ""


def _flying(
    record: dict[str, Any],
    seconds: float,
    counts: dict[str, int],
    guard: LoopGuard | None = None,
    held: Held | None = None,
    text: list[Part] | None = None,
) -> dict[str, Any]:
    tokens = sum(counts.values())
    first = record.get("first_token_ms")
    phase = WAITING if "slot" not in record else (READING if first is None else ANSWERING)
    if record.get("waiting_again"):
        phase = AGAIN
    if held is not None and not held.until:
        phase = HELD
    session, parent = session_of(record.get("headers"))
    return {
        "id": record["id"],
        "time": record.get("time", ""),
        "role": record.get("role", ""),
        "slot": record.get("slot", ""),
        "session": session,
        "parent": parent,
        "phase": phase,
        "seconds": round(seconds, 1),
        "tokens": tokens,
        "counts": dict(counts),
        "per_second": _speed(tokens, seconds * 1000, first),
        "loop_guard": None if guard is None else {"ratio": guard.ratio, "parts": guard.newest()},
        "calls": list(record.get("calls") or []),
        "held": held.facts() if held is not None else None,
        "first_ms": first,
        "newest": text[-1][0] if text else "",
        "writing": _writing(text or []),
    }


def _writing(text: list[Part]) -> dict[str, str] | None:
    """The call being written, while a request's newest text is a tool call's: its name and the newest characters of
    its arguments (`_heard` in `server.py` starts each call with "→ name ", its arguments after)."""
    if not text or text[-1][0] != "tool":
        return None
    written = text[-1][1]
    start = written.rfind("\n→ ")
    if start < 0:
        return None
    name, _, arguments = written[start + 3 :].partition(" ")
    return {"tool": name, "arguments": arguments[-WRITING:]}


def _ended(record: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    usage: dict[str, Any] = record.get("usage") or {}  # kept only when the engine gave them as objects
    timings: dict[str, Any] = record.get("timings") or {}
    tokens = int(timings.get("predicted_n") or usage.get("completion_tokens") or sum(counts.values()))
    total = float(record.get("total_ms") or 0)
    speed = timings.get("predicted_per_second")
    error = record.get("error")
    session, parent = session_of(record.get("headers"))
    return {
        "id": record["id"],
        "time": record.get("time", ""),
        "role": record.get("role", ""),
        "slot": record.get("slot", ""),
        "session": session,
        "parent": parent,
        "status": record.get("status"),
        "seconds": round(total / 1000, 1),
        "tokens": tokens,
        "counts": dict(counts),
        "per_second": round(float(speed), 1) if speed else _speed(tokens, total, record.get("first_token_ms")),
        "prompt_tokens": timings.get("prompt_n") or usage.get("prompt_tokens"),
        "first_ms": record.get("first_token_ms") if counts and any(counts.values()) else None,
        "error": str(error.get("message") or error) if isinstance(error, dict) else str(error or ""),
        "looped": str(record.get("looped") or ""),
        "broken": str(record.get("broken") or ""),
        "full": str(record.get("full") or ""),
        "left": bool(record.get("left")),
        "calls": list(record.get("calls") or []),
        "preset": record.get("preset"),
        "usage": record.get("usage") if isinstance(record.get("usage"), dict) else None,
        "timings": record.get("timings") if isinstance(record.get("timings"), dict) else None,
        "held": record.get("held") if isinstance(record.get("held"), dict) else None,
    }


def _speed(tokens: int, elapsed_ms: float, first_ms: float | None) -> float | None:
    """Tokens a second after the first token: None until there are two, or when no time has passed since the first."""
    if first_ms is None or tokens < 2 or elapsed_ms <= first_ms:
        return None
    return round((tokens - 1) / ((elapsed_ms - first_ms) / 1000), 1)
