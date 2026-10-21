"""The marks the Watch for rules leave, kept in the service, and what each rule then does (design 0012 §8, decision
0053), as `config/monitor.json` says.

`Marks.check` runs the rules (`rules.py`) over one session's flow and takes each mark once, by its key: a mark already
kept only takes the newer words of what it rests on (OpenCode's next attempt). A new mark then does what its rule is set
to do, besides the mark itself: **tell the phone** (the mark is listed for the phone, with what waits, until it is
seen); **pause** the session (`Acting.pause`); **tell the model** and go on (`Acting.note`, the rule's words with
`{why}` replaced by what the mark rests on). Telling the model is capped: one rule sends at most `notes_in_a_row` notes
in a row in a session; after that, the rule marks, pauses and tells the phone. "In a row" counts again from the owner's
own next message (one that is not a note Clank sent), and from a step that finished cleanly after the rule's last note
(the note worked for a step, decision 0083), so a run left alone goes on past loops hours apart. A rule set to do
nothing (`do` empty) is off and marks nothing.

A subagent's mark never notes the subagent: the Guide acts on the root session (design 0012 §3), so its note tells the
phone instead. The note goes through the Guide (design 0012's step 9) and the pause through the gateway's hold (its step
11): the service gives the marks `guide.Ruled`, which sends the note and pauses the session's root, each as the rule;
`NotYet` says why neither can run for marks given nothing to act through. An action that cannot run, for that reason or
any other (the bridge refused, the gateway does not run), tells the phone instead, the mark saying which action waited
and why (decision 0082). A mark on a step, or on a message of the owner's, from before Clank watched (decision 0049's
`before`, the flow's) is kept, counted as seen, and does nothing more: the rules never act on what happened before the
service saw it. A mark of an ask (`WAITS`) is over once its rule no longer finds the ask waiting (answered): it stays in
the Watch for panel until seen, and leaves the phone's list. The actions run outside the lock, so a slow one never holds
the routes that read the marks.

Each new mark that acts is an event, `agents.marked` (the rule, the session, why, and what it did), and marks seen are
one, `agents.marks_seen` (who saw them, through which client). The marks are kept in memory, as the flows are (decision
0049), up to `KEPT` per session, of the newest `SESSIONS` sessions, and made again from the flows after a restart; the
ids of the marks dropped are kept, so a mark dropped to keep the newest is never made, and acted on, again. A session
whose flow the service no longer keeps is forgotten, everything Clank held of it with it (`forget`).

In the service, `run` runs the rules once a second over the flows whose version moved (`watch`), with the facts of the
agent role's slot (`slot_facts`), read once for a round that has a flow to check.
"""

import hashlib
import itertools
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import anyio
import anyio.to_thread

from clank.components.agents.sessionflow.text import brief
from clank.components.agents.watchfor.rules import RULES, Facts, Found, find
from clank.kernel.clock import Clock, to_text
from clank.kernel.events import Actor, EventLog, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.kinds import MonitorSettings
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
ROUND_SECONDS = 1.0  # how often the rules run over the flows that changed

KEPT = 200  # marks kept of one session, the newest
SESSIONS = 128  # sessions whose marks are kept, the newest marked
WATCH = Actor(kind="clank", via="watch for")
NOTE = "tell the model"
PAUSE = "pause"
PHONE = "tell the phone"
Key = tuple[str, str]  # a session's workspace and id
ROLE = "agent"  # the role whose slot's facts the rules read (the agents' model, decision 0008)
_ORDER = itertools.count(1)  # the order marks were made in, which a time alone may not tell
WAITS = ("waiting_for_you", "asks_about_a_repeat", "stopped_with_an_ask_waiting")  # the rules that mark an ask waiting
Place = list[Any] | None  # where in a session's flow a note was counted from: its step's place (`at`)

EVENT_TYPES = [
    EventType(
        "agents.marked",
        "A Watch for rule marked something in an agent's session, and did what its setting says (design 0012 §8).",
        {
            "workspace": "The workspace.",
            "session": "The session.",
            "rule": "The rule, as config/monitor.json names it.",
            "node": "The node of the session's flow the mark shows on.",
            "why": "What the mark rests on.",
            "did": "What the rule did: mark, pause, tell the phone, tell the model (each that ran).",
            "mark": "The mark's id.",
        },
    ),
    EventType(
        "agents.marks_seen",
        "Marks of the Monitor's Watch for were seen, from a client or the phone (design 0012 §8).",
        {"marks": "The marks' ids."},
    ),
]


class Unavailable(Exception):
    """An action a rule cannot take, and why."""


class Acting(Protocol):
    """What a rule asks of the Guide (design 0012 §9): a note to the session, and a pause after its step."""

    def note(self, workspace: str, port: int | None, session: str, text: str) -> None:
        """Send the model a note, as a message of the owner's, on the server that runs the session."""

    def pause(self, workspace: str, session: str) -> None:
        """Hold the session's next model request."""


class Flows(Protocol):
    """What the rules need of the flows the service keeps (`SessionFlows`)."""

    def changed(self, versions: dict[Key, int]) -> list[tuple[str, str, int, dict[str, Any]]]:
        """The flows whose version is not the one given: workspace, session, version and view."""

    def keys(self) -> set[Key]:
        """The sessions whose flows are kept."""


class NotYet:
    """No Guide given to the marks: each action says what it needs."""

    def note(self, workspace: str, port: int | None, session: str, text: str) -> None:
        """No Guide to send it: the service gives one (`guide.Ruled`)."""
        raise Unavailable("telling the model goes through the Guide's note (design 0012 §11 step 9), not given here")

    def pause(self, workspace: str, session: str) -> None:
        """Not built yet: step 11 builds it."""
        raise Unavailable("pausing comes with the gateway's hold (design 0012 §11 step 11)")


class Marks:
    """The marks of every session the service watches, and what their rules did."""

    def __init__(
        self,
        settings: Callable[[], "MonitorSettings"],
        clock: Clock,
        events: EventLog,
        acting: Acting | None = None,
    ) -> None:
        self._settings, self._clock, self._events = settings, clock, events
        self.acting: Acting = acting if acting is not None else NotYet()
        self._lock = threading.Lock()
        self._kept: dict[Key, dict[str, dict[str, Any]]] = {}  # by session, then mark id, oldest first
        self._said: dict[Key, set[str]] = {}  # the messages of each session seen, the owner's and Clank's notes
        self._sent: dict[Key, set[str]] = {}  # the notes Clank sent each session, as its flow keeps their text
        self._in_a_row: dict[tuple[str, str, str], list[Place]] = {}  # the notes in a row of each rule in a session
        self._versions: dict[Key, int] = {}  # the version of each flow the rules last ran over
        self._made: dict[Key, set[str]] = {}  # the ids of every mark made in each session, those no longer kept too

    def watch(self, flows: Flows, facts: Callable[[], Facts]) -> int:
        """One round: run the rules over every flow whose version moved since they last ran over it, with the slot's
        facts, read once for the round (none when nothing changed); how many flows were checked."""
        changed = flows.changed(self._versions)
        self._forget_gone(flows.keys())
        if not changed:
            return 0
        try:
            known = facts()
        except Exception as error:  # the gateway or the runtime could not say: the rules that need them stay quiet
            log.warning("the slot's facts could not be read: %s", error)
            known = Facts()
        for workspace, session, version, view in changed:
            self._versions[(workspace, session)] = version
            self.check(workspace, session, view, known)
        return len(changed)

    async def run(self, flows: Flows, facts: Callable[[], Facts]) -> None:
        """Run the rules over the flows that changed, once a second, while the service runs (decision 0053: they act
        while no console is open)."""
        while True:
            try:
                await anyio.to_thread.run_sync(self.watch, flows, facts, abandon_on_cancel=True)
            except Exception:
                log.exception("the Watch for rules failed")
            await anyio.sleep(ROUND_SECONDS)

    def check(self, workspace: str, session: str, view: dict[str, Any], facts: Facts) -> list[dict[str, Any]]:
        """Run the rules over a session's flow; the new marks, each having done what its rule is set to do."""
        settings = self._settings()
        every = find(view, facts)
        found = [each for each in every if settings.rule(each.rule).do]
        waiting = {mark_id(workspace, session, each) for each in every if each.rule in WAITS}
        head = view.get("head") or {}
        nodes = {str(node.get("id")): node for node in view.get("nodes") or []}
        key = (workspace, session)
        made: list[tuple[dict[str, Any], list[str], Place]] = []
        fresh: list[dict[str, Any]] = []
        with self._lock:
            self._owner_spoke(key, nodes)
            kept = self._kept.setdefault(key, {})
            for mark in kept.values():
                if mark["rule"] in WAITS and mark["id"] not in waiting:
                    mark["over"] = True  # the ask no longer waits: answered, or gone with its session's run
            made_here = self._made.setdefault(key, set())
            for each in found:
                id = mark_id(workspace, session, each)
                if id in made_here:
                    if id in kept:
                        kept[id]["why"] = each.why  # newer words of the same (OpenCode's next attempt)
                    continue  # one no longer kept, to keep the newest, is never made again
                mark = self._mark(workspace, session, each, head, nodes)
                kept[id] = mark
                made_here.add(id)
                fresh.append(mark)
                if not mark["before"]:
                    made.append((mark, *self._plan(key, each, nodes, settings)))
            self._bound(key)
        for mark, actions, place in made:
            self._act(mark, actions, settings, head, place)
        for mark, _, _ in made:
            did = [each["action"] for each in mark["did"] if each["done"]]
            self._events.record(
                "agents.marked",
                summary=f"Watch for · {mark['name']} in {mark['title'] or session}: {mark['why']}",
                actor=WATCH,
                subject=Subject(kind="workspace", id=workspace),
                data={
                    "workspace": workspace,
                    "session": session,
                    "rule": mark["rule"],
                    "node": mark["node"],
                    "why": mark["why"],
                    "did": did,
                    "mark": mark["id"],
                },
            )
        with self._lock:
            return [_copy(mark) for mark in fresh]

    def marks(self, workspace: str = "", session: str = "", limit: int = 100) -> list[dict[str, Any]]:
        """The marks kept, newest first; of one workspace, or one session, when named."""
        with self._lock:
            found = [
                _copy(mark)
                for (each_workspace, each_session), kept in self._kept.items()
                if workspace in ("", each_workspace) and session in ("", each_session)
                for mark in kept.values()
            ]
        found.sort(key=lambda mark: (mark["time"], mark["order"]), reverse=True)
        return found[:limit]

    def unseen(self) -> int:
        """How many marks are not seen yet (beside "Monitor" in the menu)."""
        with self._lock:
            return sum(1 for kept in self._kept.values() for mark in kept.values() if not mark["seen"])

    def phone(self, limit: int = 30) -> list[dict[str, Any]]:
        """The marks told to the phone and not seen yet, newest first; a mark of an ask no longer waiting is over."""
        return [mark for mark in self.marks(limit=10_000)
                if mark["phone"] and not mark["seen"] and not mark["over"]][:limit]  # fmt: skip

    def seen(self, ids: list[str] | None = None, *, workspace: str = "", session: str = "", actor: Actor) -> int:
        """Mark seen the marks of these ids, or every mark of a session (or of a workspace); how many were not seen."""
        with self._lock:
            chosen = [
                mark
                for (each_workspace, each_session), kept in self._kept.items()
                for mark in kept.values()
                if not mark["seen"]
                and (mark["id"] in ids if ids is not None else (workspace in ("", each_workspace)
                                                               and session in ("", each_session)))
            ]  # fmt: skip
            for mark in chosen:
                mark["seen"] = True
        if chosen:
            self._events.record(
                "agents.marks_seen",
                summary=f"{actor.describe()} saw {len(chosen)} mark{'s' if len(chosen) != 1 else ''} of Watch for",
                actor=actor,
                data={"marks": [mark["id"] for mark in chosen]},
            )
        return len(chosen)

    def forget(self, workspace: str, session: str) -> None:
        """A session no longer watched: its marks go."""
        with self._lock:
            key = (workspace, session)
            for each in (self._kept, self._said, self._sent, self._made, self._versions):
                each.pop(key, None)
            for counted in [counted for counted in self._in_a_row if counted[:2] == key]:
                del self._in_a_row[counted]

    def _forget_gone(self, kept: set[Key]) -> None:
        """Forget every session whose flow the service no longer keeps (dropped for newer ones, or deleted)."""
        with self._lock:
            known = set(self._versions) | set(self._kept) | set(self._said) | set(self._made)
        for workspace, session in known - kept:
            self.forget(workspace, session)

    def _mark(
        self, workspace: str, session: str, found: Found, head: dict[str, Any], nodes: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        rule = RULES[found.rule]
        before = _before(nodes.get(found.node), nodes)
        why = "found in the session's history, from before Clank watched: nothing more done"
        return {
            "id": mark_id(workspace, session, found), "workspace": workspace, "session": session,
            "port": head.get("port"), "title": str(head.get("title") or ""), "rule": found.rule, "name": rule.title,
            "fires": rule.fires, "source": rule.source, "node": found.node, "key": found.key, "why": found.why,
            "offer": found.offer, "time": to_text(self._clock.now()), "order": next(_ORDER), "before": before,
            "seen": before, "phone": False, "over": False,
            "did": [{"action": "mark", "done": True, "why": why if before else ""}],
        }  # fmt: skip

    def _plan(
        self, key: Key, found: Found, nodes: dict[str, dict[str, Any]], settings: "MonitorSettings"
    ) -> tuple[list[str], Place]:
        """What a new mark's rule does besides marking: its actions, the note capped (counted here, under the lock, so
        two checks of one session never both send the last note allowed), and the place its note is counted from."""
        do = settings.rule(found.rule).do
        actions: list[str] = [action for action in (NOTE, PAUSE, PHONE) if action in do]
        if NOTE not in actions:
            return actions, None
        row = self._in_a_row.setdefault((*key, found.rule), [])
        place = _place(nodes.get(found.node), nodes)
        if row and _went_on(nodes, row[-1], place):
            row.clear()  # a step finished cleanly after the last note: this one is not in a row with it
        if len(row) >= settings.notes_in_a_row:
            return ["capped", PAUSE, PHONE], None
        row.append(place)
        return actions, place

    def _act(
        self, mark: dict[str, Any], actions: list[str], settings: "MonitorSettings", head: dict[str, Any], place: Place
    ) -> None:
        """Take a new mark's actions, each recorded with whether it ran and, when not, why; one that cannot run tells
        the phone instead."""
        workspace, session, rule = mark["workspace"], mark["session"], mark["rule"]
        did: list[dict[str, Any]] = []
        instead: list[str] = []
        for action in actions:
            if action == "capped":
                count = settings.notes_in_a_row
                why = (f"{count} notes in a row already from this rule, the most config/monitor.json allows "
                       f"(notes_in_a_row): the rule marks, pauses and tells the phone, until your own next "
                       f"message")  # fmt: skip
                did.append({"action": NOTE, "done": False, "why": why})
                continue
            try:
                if action == NOTE and head.get("parent"):
                    raise Unavailable(f"{session} is a subagent: the Guide acts on the root session, and a note to a "
                                      "subagent comes later (design 0012 §3)")  # fmt: skip
                if action == NOTE:
                    text = settings.rule(rule).note.replace("{why}", mark["why"])
                    self.acting.note(workspace, head.get("port"), session, text)
                    with self._lock:
                        self._sent.setdefault((workspace, session), set()).add(brief(text))
                elif action == PAUSE:
                    self.acting.pause(workspace, session)
                elif action == PHONE:
                    continue
                did.append({"action": action, "done": True, "why": ""})
            except Exception as error:  # not built yet (`Unavailable`), or refused: the phone is told instead
                if action == NOTE:  # a note that did not go is not counted
                    with self._lock:
                        row = self._in_a_row.get((workspace, session, rule), [])
                        if place in row:
                            row.remove(place)
                did.append({"action": action, "done": False, "why": str(error) or type(error).__name__})
                instead.append(action)
        if PHONE in actions or instead:
            why = f"instead of {' and '.join(instead)}, which could not run" if instead and PHONE not in actions else ""
            did.append({"action": PHONE, "done": True, "why": why})
        with self._lock:
            mark["did"] += did
            mark["phone"] = PHONE in actions or bool(instead)

    def _owner_spoke(self, key: Key, nodes: dict[str, dict[str, Any]]) -> None:
        """The owner's own new message starts every rule's count of notes in a row again; a note Clank sent does not."""
        said = {id: node for id, node in nodes.items() if node.get("kind") == "said"}
        if key not in self._said:
            self._said[key] = set(said)
            return
        new = [node for id, node in said.items() if id not in self._said[key]]
        self._said[key].update(said)
        sent = self._sent.get(key, set())
        if any(str(node.get("text") or "") not in sent for node in new):
            for counted in [counted for counted in self._in_a_row if counted[:2] == key]:
                del self._in_a_row[counted]

    def _bound(self, key: Key) -> None:
        kept = self._kept[key]
        for id in list(kept)[: max(0, len(kept) - KEPT)]:
            del kept[id]
        if len(self._kept) > SESSIONS:
            newest = {each: max((mark["order"] for mark in marks.values()), default=0)
                      for each, marks in self._kept.items()}  # fmt: skip
            for each in sorted(newest, key=lambda each: newest[each])[: len(self._kept) - SESSIONS]:
                if each != key:
                    self._kept.pop(each, None)  # its ids stay made: its flow read again marks nothing twice


def mark_id(workspace: str, session: str, found: Found) -> str:
    """A mark's id: the same for the same rule's same find in the same session."""
    named = "\n".join((workspace, session, found.rule, found.key)).encode("utf-8")
    return "m-" + hashlib.sha256(named).hexdigest()[:12]


def _before(node: dict[str, Any] | None, nodes: dict[str, dict[str, Any]]) -> bool:
    """Whether a node is from before Clank watched: a step, or a message of the owner's, as the flow says; a call or a
    subagent through its step."""
    if node is None:
        return False
    if node.get("kind") in ("step", "said"):
        return bool(node.get("before"))
    step = nodes.get(str(node.get("step") or ""))
    return bool(step and step.get("before"))


def _place(node: dict[str, Any] | None, nodes: dict[str, dict[str, Any]]) -> Place:
    """Where a mark stands in its session's flow, as its step's place (a call's or a subagent's step); None when its
    node is not in the flow."""
    if node is None:
        return None
    step = nodes.get(str(node.get("step") or "")) if node.get("kind") not in ("step", "said") else node
    return list((step or node)["at"])


def _went_on(nodes: dict[str, dict[str, Any]], after: Place, upto: Place) -> bool:
    """Whether a step of the model's finished cleanly after the place `after` and before `upto` (any after it when
    `upto` is not known): the note sent at `after` worked for a step."""
    if after is None:
        return False
    return any(
        node.get("kind") == "step" and node.get("ended") == "finished" and not node.get("summary")
        and not node.get("undone") and node["at"] > after and (upto is None or node["at"] < upto)
        for node in nodes.values()
    )  # fmt: skip


def _copy(mark: dict[str, Any]) -> dict[str, Any]:
    """A mark as a client is given it, apart from the one kept."""
    return {**mark, "did": [dict(each) for each in mark["did"]]}


def slot_facts(kernel: "Kernel") -> Callable[[], Facts]:
    """How the rules read the facts of the slot the agent role's requests reach (design 0012 §4: whatever model is
    loaded): its window, its output limit and its thinking budget, from the gateway's routes; none while no model runs,
    and none when the gateway cannot say. Whose conversation the engine holds is not known before design 0012's step
    3, so the rule that reads it stays quiet."""

    def facts() -> Facts:
        try:
            routes = kernel.parts["gateway"].routes()
            slot = routes["slots"].get(routes["roles"].get(ROLE, routes["default_slot"])) or {}
        except Exception as error:
            log.warning("the agent's slot could not be read: %s", error)
            return Facts()
        return Facts(context=_count(slot.get("context")), output=_count(slot.get("output")),
                     thinking=_count(slot.get("thinking")))  # fmt: skip

    return facts


def _count(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None
