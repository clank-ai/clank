"""One session's flow (design 0012 §6.1-§6.4): its steps, their calls, and the session's facts, from the bridge's lines
and pages of the session's history.

OpenCode's events are the spine. One step is one assistant message: its thinking, its text, its tool calls (made at
once, in one answer), its finish. `Flow` takes the bridge watch's lines about its session (`heard`) and pages of the
session's history (`history`, in the same shapes: `Sessions.page`), and keeps what they say as they said it: each
message and part by its id, the last said winning, except that a page read while lines kept coming never overwrites
what a line said after the reading began (`mark`). Parts are kept in the order of their ids, which OpenCode makes
ascending. The view (`view`) is built from that when it is read after a change, so a burst of a hundred lines costs one
build: the head (the session's facts) and the nodes in time order (the owner's messages and the steps, each step
followed by its calls), each node with `at`, its place in time.

A subagent (design 0012 §3, §6.2) is a branch of its own from the `task` call that started it (its metadata names the
subagent's session; a later call that continues the session is a branch of its own too), ending with what it gave
back; the keeper tells the flow what the subagent's own flow says (`child`), and a subagent whose call is not known yet
hangs from the newest step. A permission asked for a call waits on that call (its `tool.callID`) until it is replied.

A compaction (OpenCode's message with a `compaction` part, then its summary step) is a band across the flow, done once
its summary finished or OpenCode said the session compacted; a compaction said with no message of its own is a band
where it was heard. A band the Guide asked for is the owner's (`asked`, `compaction_asked`, design 0012 §9.6), though
asked with `auto` on as OpenCode's own are. The owner's message sent while the session was busy (heard while busy, or
read from the history: sent while a step was under way) is a note: waiting, read by the next step (whatever message that
step answers), or not read when the run ended without it (design 0012 §9.3). From a revert's message on (after it, when
the revert names a part of it), the nodes are undone until the revert is undone (design 0012 §9.5); the head names the
revert pending (`reverted`), which OpenCode's answer to the Guide's revert or unrevert sets at once (`reverted`, before
the watch's line about the session says it). The messages it undid stay in the flow when OpenCode removes them at the
owner's next message, `final`, since the flow is the log of the owner's guidance; a message removed that no revert undid
leaves it.

What the Guide's Undo and Drop read (design 0012 §9.5, §9.7): each step names the part a revert at its end cuts at
(`cut`), its last part when a text or a tool part comes before it, else "": OpenCode 1.19.0's `session/revert.ts`
turns a revert at a part with neither before it, in its message, into a revert of the whole turn from the owner's
message; and the files its patch parts list (`files`), the patches a revert before them restores. A call whose result
the Guide cleared says so once OpenCode says it is cleared (`cleared_by`, "you", and the tokens it freed, `freed`); one
OpenCode cleared itself says no one.

Each step is joined to the gateway's request that answered it (`requests`, the session's requests as the gateway's
activity gives them; `pairing.py`), with its numbers: when it began, how long it took, its speed, its prompt, its tokens
by kind, how it ended (an error, the loop guard's stop, its engine broken off), and the gateway's hold of it while its
session was paused (`held`, design 0012 §9.4). A step read from the history when Clank
first saw the session (`history(..., joined=True)`) and finished then was done before Clank watched (`before`): it is
never paired, since the gateway's timings of it are not Clank's to claim (design 0012 §3). The owner's message read then
is from before Clank watched too while the step that decides its state (the one that read it, else for a note the one
under way when it was sent) was done before Clank watched, or there is none: a note left unread by a run that ended
after Clank joined is not.

Versions (design 0012 §6.1: the console asks for what changed since its version, as `/gateway/live` serves text after
an offset): each build that changed something takes a new version, and each node, the head and the branches keep the
version at which they last changed; `changes(since)` gives the nodes changed after `since` and those removed, or the
whole flow when `since` is older than the flow (`base`: it was made again, after the service started again or the flow
was dropped) or newer than it.

The main branches and the branch each step joins are `branches.py`'s: a Clank plan's steps when the session carries one
out (the keeper reads the plan's file, `plan`, and gives its text, `planned`); else the todo list's items (`todos.py`),
each revision placed after the step that wrote it (a `todo` line after the newest step when it was heard, which wrote
it; a `todowrite` call of the history after its own step); else the owner's messages.

What it infers it says (design 0012 §6.4): a call failed when it ended in an error or a `bash` call's exit status is not
0, and it is a dead end once a later step began; a step left the context when it ended in an error, unless the owner
stopped it (`MessageAbortedError`) and it has content beyond its start and its thinking, as OpenCode's own
`message-v2.ts` leaves such steps out of every later request (read 2026-10-18).
"""

import bisect
import itertools
import time
from dataclasses import dataclass
from typing import Any

from clank.components.agents.sessionflow import branches, todos
from clank.components.agents.sessionflow.pairing import pair
from clank.components.agents.sessionflow.text import brief

ABORTED = "MessageAbortedError"  # the error of a step the owner stopped
NOT_CONTENT = ("step-start", "reasoning")  # parts that do not keep a stopped step in the context
REQUESTS_KEPT = 128  # the gateway's requests of the session kept, the newest
KEEP = 1000  # characters of a part's text, input or output kept: briefs, the whole one read of the history away
REMOVED_KEPT = 1000  # nodes removed whose removal is still said to a client that asks since before it
# Versions, shared by every flow of the service and rising across its runs, so a version is never one another flow had
VERSIONS = itertools.count(int(time.time() * 1000))
OF_A_SESSION = ("message", "part", "removed", "todo", "compacted", "error", "status", "replied")


@dataclass
class Kept:
    """A message or a part as last said, when (a counter over everything the flow took), and whether a line said it."""

    value: dict[str, Any]
    said: int
    live: bool


class Flow:
    """One session's flow: what the lines and the history said, and the view built from it."""

    def __init__(self, session: str, workspace: str = "") -> None:
        self.session, self.workspace = session, workspace
        self.port: int | None = None
        self.base = self.version = next(VERSIONS)
        self._count = itertools.count(1)
        self._messages: dict[str, Kept] = {}
        self._parts: dict[str, Kept] = {}
        self._status: dict[str, Any] = {"status": "idle"}
        self._info: dict[str, Any] = {}
        self._error = ""
        self._children: dict[str, dict[str, Any]] = {}  # each subagent's session: what its own flow says, briefly
        self._asks: dict[str, dict[str, str]] = {}  # by the call asked for: the ask's id and its permission
        self._plan_text: str | None = None  # the plan's file as last read, when the session carries one out
        self._todos: dict[str, list[dict[str, Any]]] = {}  # the todo list heard, by the step that wrote it
        self._busy_said: set[str] = set()  # the owner's messages first heard while the session was busy
        self._before: set[str] = set()  # the steps done before Clank watched
        self._said_before: set[str] = set()  # the owner's messages read when Clank first saw the session
        self._requests: dict[str, dict[str, Any]] = {}  # the gateway's requests of the session, by id
        self._compacted: list[list[Any]] = []  # each compaction OpenCode said: where the flow stood when it was heard
        self._asked_bands: set[int] = set()  # the bands, by their place in time order, the Guide asked for
        self._final: set[str] = set()  # the messages a revert undid that OpenCode removed since: kept, final
        self._cleared_by: dict[str, int | None] = {}  # the calls whose result the Guide cleared: the tokens freed
        self._changed = True
        self._view: dict[str, Any] = {}
        self._shown: dict[str, tuple[dict[str, Any], int]] = {}  # each node as last built, and its version
        self._removed: dict[str, int] = {}  # each node removed, and the version that removed it
        self._items_at = 0  # the version at which the branches last changed

    def mark(self) -> int:
        """Where the flow stands now: a page of history read after this never overwrites what a line said since."""
        return next(self._count)

    def heard(self, line: dict[str, Any]) -> None:
        """A line of the bridge's watch; one about another session changes nothing."""
        kind = line.get("type")
        if kind == "session":
            info = line.get("session") or {}
            if info.get("id") != self.session:
                return
            self._info = {**self._info, **info, "deleted": bool(line.get("deleted"))}
        elif kind == "asked":
            request = line.get("request") or {}
            if request.get("sessionID") != self.session or not (request.get("tool") or {}).get("callID"):
                return
            asked = {"id": str(request.get("id") or ""), "permission": str(request.get("permission") or "")}
            self._asks[str(request["tool"]["callID"])] = asked
        elif kind in OF_A_SESSION and str(line.get("session") or "") == self.session:
            self._session_line(str(kind), line)
        else:
            return
        if line.get("port"):
            self.port = int(line["port"])
        self._changed = True

    def compaction_asked(self, index: int | None = None) -> None:
        """The Guide asked OpenCode to compact the session (design 0012 §9.6): the band at `index` in time order (the
        next one, by default) is the owner's, though asked with `auto` on as OpenCode's own are."""
        self._asked_bands.add(index if index is not None else self.view()["head"]["compactions"])
        self._changed = True

    def reverted(self, revert: dict[str, Any] | None) -> None:
        """OpenCode answered the Guide's revert (or its unrevert, None) with the session's revert as it now stands
        (design 0012 §9.5): shown at once, as the watch's line about the session says it after."""
        self._info = {**self._info, "revert": dict(revert or {})}
        self._changed = True

    def cleared(self, part: str, freed: int | None) -> None:
        """The Guide cleared a call's result (design 0012 §9.7), freeing about `freed` tokens: once OpenCode says it is
        cleared, its node says by you."""
        self._cleared_by[part] = freed
        self._changed = True

    @property
    def plan(self) -> str:
        """The Clank plan the session carries out: the file the first message of `/implement` names ("" for none)."""
        return self._planned()[0]

    def planned(self, text: str | None) -> None:
        """The plan's file as read now (None when it cannot be read)."""
        if text != self._plan_text:
            self._plan_text = text
            self._changed = True

    def child(self, session: str, brief: dict[str, Any]) -> None:
        """What a subagent's own flow says, briefly: its title, its status, its steps and its calls."""
        if self._children.get(session) != brief:
            self._children[session] = dict(brief)
            self._changed = True

    def history(self, page: dict[str, Any], since: int | None = None, joined: bool = False) -> None:
        """A page of the session's history, oldest first (`Sessions.page`); what a line said after `since` stays. Read
        when Clank first saw the session (`joined`), its steps finished then were done before Clank watched."""
        for message in page.get("messages") or []:
            info = message.get("info") or {}
            known = self._messages.get(str(info.get("id") or ""))
            finished = info.get("role") == "assistant" and (info.get("completed") or info.get("error"))
            if joined and finished and not (known is not None and known.live):
                self._before.add(str(info["id"]))
            if joined and info.get("role") == "user" and not (known is not None and known.live):
                self._said_before.add(str(info["id"]))
            self._keep(self._messages, info, live=False, since=since)
            for part in message.get("parts") or []:
                self._keep(self._parts, part, live=False, since=since)
        self._changed = True

    def requests(self, found: list[dict[str, Any]]) -> None:
        """The gateway's requests of the session (in flight and ended), as its activity gives them; the newest
        `REQUESTS_KEPT` are kept."""
        changed = False
        for request in found:
            id = str(request.get("id") or "")
            if id and self._requests.get(id) != request:
                self._requests[id] = dict(request)
                changed = True
        if len(self._requests) > REQUESTS_KEPT:
            newest = sorted(self._requests.values(), key=lambda each: str(each.get("time") or ""))[-REQUESTS_KEPT:]
            self._requests = {str(each["id"]): each for each in newest}
        self._changed = self._changed or changed

    def view(self) -> dict[str, Any]:
        """The flow as the Monitor reads it: its head, its nodes in time order (each with `v`, the version at which it
        last changed), its branches, and its version."""
        if self._changed:
            self._changed = False
            self._versioned(self._build())
        return {**self._view, "version": self.version}

    def changes(self, since: int = 0) -> dict[str, Any]:
        """What changed after the version `since`: the head, the nodes changed, the ids of those removed, and the
        branches when they changed; the whole flow (`whole`) when `since` is not one of this flow's versions."""
        view = self.view()
        found: dict[str, Any] = {"version": self.version, "base": self.base, "head": view["head"]}
        if not self.base <= since <= self.version:
            return {**found, "whole": True, "nodes": view["nodes"], "removed": [], "items": view["items"]}
        found.update(whole=False, nodes=[node for node in view["nodes"] if node["v"] > since],
                     removed=[id for id, version in self._removed.items() if version > since])  # fmt: skip
        if self._items_at > since:
            found["items"] = view["items"]
        return found

    def _versioned(self, built: dict[str, Any]) -> None:
        """Take a new build: a new version when anything in it changed, each node keeping the version at which it
        last changed."""
        nodes = {node["id"]: node for node in built["nodes"]}
        changed = [id for id, node in nodes.items() if self._shown.get(id, (None, 0))[0] != node]
        gone = [id for id in self._shown if id not in nodes]
        items = built["items"] != self._view.get("items")
        if changed or gone or items or built["head"] != self._view.get("head"):
            self.version = next(VERSIONS)
        for id in changed:
            self._shown[id] = (nodes[id], self.version)
            self._removed.pop(id, None)
        for id in gone:
            del self._shown[id]
            self._removed[id] = self.version
        if len(self._removed) > REMOVED_KEPT:
            oldest = sorted(self._removed.items(), key=lambda each: each[1])[: len(self._removed) - REMOVED_KEPT]
            for id, version in oldest:
                del self._removed[id]
                self.base = max(self.base, version)  # a client from before it would not hear of that removal
        if items:
            self._items_at = self.version
        shown = [{**node, "v": self._shown[node["id"]][1]} for node in built["nodes"]]
        self._view = {"head": built["head"], "nodes": shown, "items": built["items"]}

    def _session_line(self, kind: str, line: dict[str, Any]) -> None:
        if kind == "message":
            info = line.get("message") or {}
            busy = self._status.get("status") in ("busy", "retry")
            if info.get("role") == "user" and busy and str(info.get("id")) not in self._messages:
                self._busy_said.add(str(info.get("id")))
            self._keep(self._messages, info, live=True)
        elif kind == "part":
            self._keep(self._parts, line.get("part") or {}, live=True)
        elif kind == "removed":
            message = str(line.get("message") or "")
            if message in self._final or message in self._taken_back():  # OpenCode made a revert final: kept
                self._final.add(message)
            elif line.get("part"):
                self._parts.pop(str(line["part"]), None)
            else:
                self._messages.pop(message, None)
                for id in [id for id, kept in self._parts.items() if kept.value.get("message") == message]:
                    del self._parts[id]
        elif kind == "status":
            self._status = {key: line.get(key) for key in ("status", "attempt", "message", "next")}
        elif kind == "error":
            self._error = str(line.get("error") or "")
        elif kind == "compacted":
            newest = max((kept.value for kept in self._messages.values()), default={},
                         key=lambda info: (info.get("created") or 0, str(info.get("id"))))  # fmt: skip
            self._compacted.append([newest.get("created") or 0, str(newest.get("id") or ""), 2_000_000])
        elif kind == "todo":
            steps = [kept.value for kept in self._messages.values() if kept.value.get("role") == "assistant"]
            newest = max(steps, key=lambda info: (info.get("created") or 0, str(info.get("id"))), default={})
            self._todos[str(newest.get("id") or "")] = [dict(each) for each in line.get("todos") or []]
        elif kind == "replied":
            for call in [call for call, asked in self._asks.items() if asked["id"] == line.get("request")]:
                del self._asks[call]

    def _keep(self, kept: dict[str, Kept], value: dict[str, Any], *, live: bool, since: int | None = None) -> None:
        id = str(value.get("id") or "")
        if not id:
            return
        found = kept.get(id)
        if since is not None and found is not None and found.live and found.said > since:
            return  # a line said it after the history was read: the line is newer
        kept[id] = Kept(slim(value), next(self._count), live or (found.live if found is not None else False))

    def _build(self) -> dict[str, Any]:
        messages = sorted(
            (kept.value for kept in self._messages.values()),
            key=lambda info: (info.get("created") or 0, str(info.get("id"))),
        )
        parts: dict[str, list[dict[str, Any]]] = {}
        for id in sorted(self._parts):
            part = self._parts[id].value
            parts.setdefault(str(part.get("message") or ""), []).append(part)
        steps = [info for info in messages if info.get("role") == "assistant"]
        newest = str(steps[-1]["id"]) if steps else ""
        number = {str(info["id"]): index + 1 for index, info in enumerate(steps)}
        starts = [info.get("created") or 0 for info in steps]
        nodes: list[dict[str, Any]] = []
        for info in messages:
            id = str(info["id"])
            own = parts.get(id, [])
            if info.get("role") == "user":
                band = next((part for part in own if part.get("type") == "compaction"), None)
                said = self._band(info, band, steps) if band is not None else self._said(info, own, steps, starts)
                nodes.append(said)
                continue
            nodes.append(self._step(info, own, number[id]))
            for index, part in enumerate(each for each in own if each.get("type") == "tool"):
                call = _call(info, part, index + 1, moved_on=id != newest)
                asked = self._asks.get(str(call["call"]), {})
                call.update(asking=asked.get("id", ""), permission=asked.get("permission", ""))
                by = call["cleared"] and call["id"] in self._cleared_by
                call.update(cleared_by="you" if by else "", freed=self._cleared_by.get(call["id"]) if by else None)
                nodes.append(call)
                if part.get("subagent"):
                    nodes.append(self._subagent(str(part["subagent"]), call, info))
        started = {node["session"] for node in nodes if node["kind"] == "subagent"}
        for session in self._children:
            if session not in started and steps:
                nodes.append(self._subagent(session, None, steps[-1]))
        bands = [node for node in nodes if node["kind"] == "band"]
        for index, band in enumerate(bands):
            band["done"] = band["done"] or index < len(self._compacted)
        for index, at in enumerate(self._compacted[len(bands) :]):
            nodes.append({"id": f"compacted:{len(bands) + index + 1}", "kind": "band", "at": at, "auto": True,
                          "summary": "", "done": True})  # fmt: skip
        nodes.sort(key=lambda node: node["at"])
        for index, band in enumerate(node for node in nodes if node["kind"] == "band"):
            band["asked"] = index in self._asked_bands
        cut = self._undone(messages)
        for node in nodes:
            final = str(node.get("step") or node["id"]) in self._final
            node["undone"] = final or (cut is not None and node["at"] >= cut)
            if final:
                node["final"] = True
        source, items, joined = self._branches(messages, parts)
        watched = [
            {"id": str(info["id"]), "created": info.get("created") or 0,
             "calls": [part.get("call") for part in parts.get(str(info["id"]), []) if part.get("type") == "tool"]}
            for info in steps
            if str(info["id"]) not in self._before
        ]  # fmt: skip
        paired = pair(watched, list(self._requests.values()))
        for node in nodes:
            if node["kind"] == "step":
                node["item"] = joined.get(node["id"], "")
                node["before"] = node["id"] in self._before
                found = paired.get(node["id"])
                node["request"] = self._request(found.request, found.confirmed, found.why) if found else None
                node["tries"] = list(found.tries) if found else []
        head = {**self._head(messages, nodes), "branches": source, "plan": self.plan, "before": len(self._before),
                "compactions": sum(1 for node in nodes if node["kind"] == "band")}  # fmt: skip
        return {"head": head, "nodes": nodes, "items": items}

    def _request(self, id: str, confirmed: bool, why: str) -> dict[str, Any]:
        """A step's request as its node shows it: the gateway's numbers, and how it was paired."""
        request = self._requests.get(id, {})
        shown = {key: request.get(key) for key in ("id", "time", "seconds", "per_second", "prompt_tokens", "tokens",
                                                     "counts", "error", "looped", "broken", "left", "phase",
                                                     "held")}  # fmt: skip
        return {**shown, "flying": "phase" in request, "confirmed": confirmed, "why": why}

    def _taken_back(self) -> set[str]:
        """The messages the revert pending took back (none when nothing is reverted)."""
        messages = sorted((kept.value for kept in self._messages.values()),
                          key=lambda info: (info.get("created") or 0, str(info.get("id"))))  # fmt: skip
        cut = self._undone(messages)
        if cut is None:
            return set()
        return {str(info["id"]) for info in messages if [info.get("created") or 0, str(info["id"]), 0] >= cut}

    def _reverted(self) -> dict[str, str] | None:
        """The revert pending, as OpenCode keeps it: the message it took back from, and the part it names."""
        revert = self._info.get("revert") or {}
        if not revert.get("messageID"):
            return None
        return {"message": str(revert["messageID"]), "part": str(revert.get("partID") or "")}

    def _undone(self, messages: list[dict[str, Any]]) -> list[Any] | None:
        """Where what the session's revert took back begins (None when nothing is reverted)."""
        revert = self._info.get("revert") or {}
        ids = [str(info["id"]) for info in messages]
        if not revert.get("messageID") or revert["messageID"] not in ids:
            return None
        index = ids.index(revert["messageID"]) + (1 if revert.get("partID") else 0)
        if index >= len(messages):
            return None
        return [messages[index].get("created") or 0, ids[index], 0]

    def _band(self, info: dict[str, Any], part: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
        """A compaction: its message, whether OpenCode asked for it itself, its summary step, and whether it is done."""
        summary = next((step for step in steps if step.get("parent") == info["id"] and step.get("summary")), None)
        done = summary is not None and bool(summary.get("completed")) and not summary.get("error")
        return {"id": info["id"], "kind": "band", "at": [info.get("created") or 0, info["id"], 0],
                "auto": bool(part.get("auto")), "summary": summary["id"] if summary else "", "done": done}  # fmt: skip

    def _planned(self) -> tuple[str, str]:
        """The plan the session carries out and the message that named it ("" and "" for none)."""
        users = {id: kept.value for id, kept in self._messages.items() if kept.value.get("role") == "user"}
        named = []
        for kept in self._parts.values():
            info = users.get(str(kept.value.get("message") or ""))
            if info is not None and kept.value.get("type") == "text":
                plan = branches.plan_named(str(kept.value.get("text") or ""))
                if plan:
                    named.append(((info.get("created") or 0, str(info["id"])), plan))
        if not named:
            return "", ""
        (_, message), plan = min(named)
        return plan, message

    def _branches(
        self, messages: list[dict[str, Any]], parts: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, list[dict[str, Any]], dict[str, str]]:
        """Where the branches come from (plan, todo or said), the branches, and the branch each step joins."""
        plan, named = self._planned()
        busy = self._status.get("status") in ("busy", "retry")
        listed = branches.checklist(self._plan_text) if plan and self._plan_text is not None else []
        ordered = [info for info in messages if info.get("role") == "assistant"]
        steps = [branches.Step(str(info["id"]), str(info.get("parent") or "")) for info in ordered]
        if listed:
            begun = next(index for index, info in enumerate(messages) if info.get("id") == named)
            after = {str(info["id"]) for info in messages[begun:]}
            steps = [step for step in steps if step.id in after]
            for step in steps:
                for part in parts.get(step.id, []):
                    made, guessed = branches.ticks(str(part.get("tool") or ""), part.get("input"), plan)
                    step.ticks += made
                    if guessed:
                        step.guessed.append(str(part["id"]))
            items, joined = branches.from_plan(plan, listed, steps, busy=busy)
            return "plan", items, joined
        revisions = self._revisions(ordered, parts)
        if revisions:
            items, progress = todos.follow(revisions)
            keyed = {item["key"]: item for item in items}
            joined = {}
            for index, step in enumerate(steps):
                began = [progress[each] for each, (wrote, _) in enumerate(revisions) if wrote < index]
                joined[step.id] = began[-1] if began else ""
                if joined[step.id]:
                    keyed[joined[step.id]]["steps"].append(step.id)
            return "todo", items, joined
        said = [
            (str(info["id"]), " ".join(str(part.get("text") or "") for part in parts.get(str(info["id"]), [])
                                       if part.get("type") == "text" and not part.get("synthetic")))
            for info in messages
            if info.get("role") == "user"
            and not any(part.get("type") == "compaction" for part in parts.get(str(info["id"]), []))
        ]  # fmt: skip
        items, joined = branches.from_said(said, steps, busy=busy)
        return "said", items, joined

    def _revisions(self, steps: list[dict[str, Any]], parts: dict[str, list[dict[str, Any]]]) -> list[todos.Revision]:
        """The todo list's revisions, each with the index of the step that wrote it (-1 before any step), in order: a
        revision heard for a step stands for that step's `todowrite` calls."""
        found: list[todos.Revision] = [(-1, self._todos[""])] if "" in self._todos else []
        for index, info in enumerate(steps):
            id = str(info["id"])
            if id in self._todos:
                found.append((index, self._todos[id]))
                continue
            for part in parts.get(id, []):
                wrote = todos.written(
                    str(part.get("tool") or ""), part.get("input"), part.get("output"), part.get("todos")
                )
                if wrote is not None:
                    found.append((index, wrote))
        return found

    def _subagent(self, session: str, call: dict[str, Any] | None, step: dict[str, Any]) -> dict[str, Any]:
        """A subagent's branch: from its call (or from the newest step while its call is not known), with what it gave
        back, and what its own flow says when it is kept. Its id is its call's and its session's, since a later `task`
        call may continue the same session, a branch from each call; the session's alone while no call is known."""
        own = self._children.get(session, {})
        at = [*call["at"], 1] if call is not None else [step.get("created") or 0, step["id"], 1_000_000]
        return {
            "id": f"{call['id']}:{session}" if call is not None else session, "kind": "subagent", "session": session,
            "at": at, "step": step["id"], "call": call["id"] if call else "",
            "title": (call or {}).get("title") or brief(own.get("title") or ""),
            "status": (call or {}).get("status") or "", "gave": (call or {}).get("output") or "",
            "steps": own.get("steps"), "calls": own.get("calls"), "state": own.get("status") or "",
        }  # fmt: skip

    def _said(
        self, info: dict[str, Any], parts: list[dict[str, Any]], steps: list[dict[str, Any]], starts: list[Any]
    ) -> dict[str, Any]:
        """The owner's message: a note when it was sent while the session was busy, read by the first step that began
        after it (OpenCode stores it at once and gives every message stored to the next step); else read by the step
        that answers it."""
        said = " ".join(str(part.get("text") or "") for part in parts if part.get("type") == "text"
                        and not part.get("synthetic"))  # fmt: skip
        created = info.get("created") or 0
        begun = bisect.bisect_left(starts, created)
        last = steps[begun - 1] if begun else None  # the step begun last before it: one runs at a time
        under_way = last is not None and (
            (last.get("completed") is None and not last.get("error")) or (last.get("completed") or 0) > created
        )
        note = info["id"] in self._busy_said or under_way
        if note:  # stored at once, read by the next step, whatever message that step answers
            read = str(steps[begun]["id"]) if begun < len(steps) else ""
        else:
            read = next((str(step["id"]) for step in steps[begun:] if step.get("parent") == info["id"]), "")
        state = ""
        if note:
            state = "read" if read else ("waiting" if self._status.get("status") in ("busy", "retry") else "not read")
        decides = read or (str(last["id"]) if note and last is not None else "")
        before = info["id"] in self._said_before and (not decides or decides in self._before)
        return {
            "id": info["id"], "kind": "said", "at": [created, info["id"], 0], "text": brief(said),
            "length": sum(int(part.get("length") or 0) for part in parts if part.get("type") == "text"),
            "agent": info.get("agent") or "", "model": info.get("model") or {}, "created": info.get("created"),
            "note": note, "state": state,
            "read_by": read, "before": before,
        }  # fmt: skip

    def _step(self, info: dict[str, Any], parts: list[dict[str, Any]], n: int) -> dict[str, Any]:
        error, name = str(info.get("error") or ""), str(info.get("error_name") or "")
        content = any(part.get("type") not in NOT_CONTENT for part in parts)
        if error:
            ended = "stopped" if name == ABORTED else "failed"
        else:
            ended = "finished" if info.get("completed") else "working"
        written = [part for part in parts if part.get("type") == "text" and not part.get("synthetic")]
        cut = str(parts[-1]["id"]) if any(part.get("type") in ("text", "tool") for part in parts[:-1]) else ""
        files: list[str] = []
        for part in (each for each in parts if each.get("type") == "patch"):
            files += [str(file) for file in part.get("files") or [] if str(file) not in files]
        return {
            "id": info["id"], "kind": "step", "at": [info.get("created") or 0, info["id"], 0], "n": n,
            "said": info.get("parent") or "", "agent": info.get("agent") or "", "model": info.get("model") or {},
            "created": info.get("created"), "completed": info.get("completed"), "tokens": info.get("tokens") or {},
            "finish": info.get("finish") or "", "error": error, "ended": ended,
            "context": "left" if error and not (name == ABORTED and content) else "in",
            "summary": bool(info.get("summary")), "calls": [part["id"] for part in parts if part.get("type") == "tool"],
            "together": sum(1 for part in parts if part.get("type") == "tool"),
            "thinking": sum(int(part.get("length") or 0) for part in parts if part.get("type") == "reasoning"),
            "text": brief(" ".join(str(part.get("text") or "") for part in written)),
            "length": sum(int(part.get("length") or 0) for part in written), "cut": cut, "files": files,
        }  # fmt: skip

    def _head(self, messages: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict[str, Any]:
        status = self._status
        return {
            "workspace": self.workspace, "session": self.session, "port": self.port,
            "title": str(self._info.get("title") or ""), "parent": self._info.get("parent") or "",
            "status": status.get("status") or "idle", "attempt": status.get("attempt"),
            "retry": status.get("message") or "", "next": status.get("next"),
            "agent": next((str(info.get("agent")) for info in reversed(messages) if info.get("agent")), ""),
            "since": messages[0].get("created") if messages else None,
            "steps": sum(1 for node in nodes if node["kind"] == "step"),
            "calls": sum(1 for node in nodes if node["kind"] == "call"), "error": self._error,
            "reverted": self._reverted(),
        }  # fmt: skip


def slim(value: dict[str, Any]) -> dict[str, Any]:
    """A message or a part as a flow keeps it: its texts, input and output cut at `KEEP` characters (a text's whole
    length is kept beside it), but a `todowrite` call's output, from which an older bridge's todo list is read (whole up
    to the bridge's own cut; the bridge now keeps the list whole in `todos`, which is kept as it is)."""
    kept = dict(value)
    for key in ("text", "input", "output", "error"):
        if isinstance(kept.get(key), str) and len(kept[key]) > KEEP:
            if key == "output" and kept.get("tool") == "todowrite":
                continue
            kept[key] = kept[key][:KEEP]
    return kept


def _call(step: dict[str, Any], part: dict[str, Any], index: int, *, moved_on: bool) -> dict[str, Any]:
    """A tool call's node: what it did and how it ended; failed when it ended in an error or a `bash` call's exit status
    is not 0, a dead end once a later step began."""
    exit = part.get("exit")
    failed = part.get("status") == "error" or (part.get("tool") == "bash" and isinstance(exit, int) and exit != 0)
    time = part.get("time") or {}
    return {
        "id": part["id"], "kind": "call", "at": [step.get("created") or 0, step["id"], index], "step": step["id"],
        "tool": part.get("tool") or "", "call": part.get("call") or "", "status": part.get("status") or "",
        "title": brief(part.get("title") or ""), "input": brief(part.get("input") or ""),
        "output": brief(part.get("output") or ""), "length": part.get("length"),
        "error": brief(part.get("error") or ""), "exit": exit, "failed": failed, "dead_end": failed and moved_on,
        "cleared": bool(time.get("compacted")), "started": time.get("start"), "ended": time.get("end"),
        "subagent": part.get("subagent") or "",
    }  # fmt: skip
