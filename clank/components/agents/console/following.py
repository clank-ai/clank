"""Which session the Monitor follows, and its flow as the service keeps it (design 0012 §3, §6.1; decision 0048).

The page follows design 0012 §3's choice (a): the newest active root session of the console's folder (its workspace's
sessions the service keeps a flow of, newest heard first; active: busy or retrying), else the newest root session
heard (`pick`). Picking another (`s`, which pins it) comes with a later step; so does a session idle since the service
started, of which the service keeps no flow until something happens in it (plan s15, "For step 6"). Enter on a flow's
running box pins the page to that box's session (`pin`, design 0013 §12) until Esc goes back to the box (`unpin`).

`Following.read` runs off the screen's thread, once a second while the page is on screen: it reads the folder's
workspace now and then (`WORKSPACE_EVERY` readings: the route asks Docker), the flows kept of it (their heads and
versions, which cost the service nothing to give), and, for the followed session and the subagents its flow names
(and theirs, `SUBAGENTS` at most), only what changed since the version it holds (`GET
/agents/flow/{workspace}/{session}?since=`, `merged`), and only when that flow's version moved. It returns what the
page shows (`Seen`), or None when nothing changed, so the page draws nothing then (design 0001 §5.7). With the flow it
reads the followed session's context totals (`GET /agents/context/{workspace}/{session}`, design 0012 §4.1), which
change when one of its steps ends, when another request reaches the engine, or when the slot switches, and what the
Guide offers for it (`GET /agents/guide/{workspace}/{session}`, design 0012 §9); when the service refuses either, the
session and why (`unavailable`). One reading runs
at a time: one asked for while another is under way (the folder's workspace route can take over a second) returns None
at once and asks nothing, so two never change what is held together, nor deliver an older flow after a newer one.

`Watching.read` reads what the followed session does now (`GET /agents/now/{workspace}/{session}`, design 0012 §5,
`doing`) off the screen's thread too, as often as the page asks (four times a second while the session works, once a
second while it does not), one reading at a time; it returns None when nothing changed since its last reading of that
session, so the page draws nothing then. The page clears what it shows when it follows another session, so it makes
`Watching` forget its last reading then (`forget`): the session followed again is drawn though nothing changed.
`Watching.text` reads the session's request as it is written, from an offset (`GET /gateway/live?session=`, design
0012 §7), one reading at a time too.

`FlowReading.read` reads the flow the Flow view shows (`GET /flows/view`, design 0013 §12) the same way: one reading
at a time, None when the view's version did not move, so the view draws nothing then.

What changed is the whole flow only when the service says so (`whole`): it does when the version asked from is not one
of its flow's (older than its `base`, or a flow made again, whose base is always newer). The base also moves forward
when the service forgets its oldest removals, while a client past it still gets only what changed, to be merged.
"""

import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from clank.client import Client, ClientError

WORKING = ("busy", "retry")
WORKSPACE_EVERY = 10  # readings between two readings of the folder's workspace
SUBAGENTS = 16  # subagents' flows read at most, the newest first


@dataclass(frozen=True)
class Seen:
    """What the page shows: the folder's workspace ("" for none, None when not read yet), the session followed (its
    flow's head), its flow, its subagents' flows, its context totals and what the Guide offers for it (None when not
    read)."""

    workspace: str | None
    head: dict[str, Any] | None = None
    view: dict[str, Any] | None = None
    subagents: dict[str, dict[str, Any]] = field(default_factory=dict)
    context: dict[str, Any] | None = None
    guide: dict[str, Any] | None = None
    box: str = ""  # the flow's box whose session the page is pinned to ("" while it follows the newest)


def pick(heads: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The session to follow: the newest active root session, else the newest root session (heads newest first)."""
    roots = [head for head in heads if not head.get("parent")]
    return next((head for head in roots if head.get("status") in WORKING), roots[0] if roots else None)


def merged(held: dict[str, Any] | None, changes: dict[str, Any]) -> dict[str, Any]:
    """A flow brought up to date by what changed since its version: whole when the service says so (it does when the
    version asked from is not its flow's, as after it made the flow again), else its nodes changed put in, those
    removed taken out, kept in time order."""
    kept = {"version": changes["version"], "base": changes.get("base"), "head": changes["head"]}
    if held is None or changes.get("whole"):
        return {**kept, "nodes": list(changes.get("nodes") or []), "items": list(changes.get("items") or [])}
    nodes = {node["id"]: node for node in held["nodes"]}
    for id in changes.get("removed") or []:
        nodes.pop(id, None)
    for node in changes.get("nodes") or []:
        nodes[node["id"]] = node
    ordered = sorted(nodes.values(), key=lambda node: list(node.get("at") or []))
    return {**kept, "nodes": ordered, "items": list(changes["items"]) if "items" in changes else held["items"]}


def doing(client: Client, workspace: str, session: str) -> dict[str, Any]:
    """What a session does now (`GET /agents/now/{workspace}/{session}`, design 0012 §5), or why it is not known."""
    try:
        found: dict[str, Any] = client.get(f"agents/now/{quote(workspace)}/{quote(session)}")
    except ClientError as error:
        return {"session": session, "unavailable": str(error)}
    return found


class Following:
    """The session the page follows and the flows it holds, read from the service (one reading at a time)."""

    def __init__(self, client: Client, folder: str) -> None:
        self.client, self.folder = client, folder
        self.workspace: str | None = None
        self.flows: dict[str, dict[str, Any]] = {}  # by session: as last brought up to date
        self._readings = 0
        self._shown: tuple[Any, ...] | None = None
        self._reading = threading.Lock()
        self.pinned: tuple[str, str, str] | None = None  # a flow's box's session: its workspace, its id, the box

    def pin(self, workspace: str, session: str, box: str) -> None:
        """Follow a flow's box's session (design 0013 §12: Enter on a running box) until `unpin`."""
        self.pinned, self._shown = (workspace, session, box), None

    def unpin(self) -> None:
        """Follow the newest session of the folder again."""
        self.pinned, self._shown = None, None

    def read(self) -> Seen | None:
        """Read what changed; what the page shows, or None when nothing did or another reading is under way. Raises
        what the client raises."""
        if not self._reading.acquire(blocking=False):
            return None
        try:
            return self._read()
        finally:
            self._reading.release()

    def _read(self) -> Seen | None:
        pinned = self.pinned
        if pinned is None and (self.workspace is None or self._readings % WORKSPACE_EVERY == 0):
            self.workspace = str(self.client.get("workspaces/folder", folder=self.folder).get("workspace") or "")
        elif pinned is not None:
            self.workspace = pinned[0]
        self._readings += 1
        if not self.workspace:
            self.flows = {}
            return self._seen(Seen(""))
        heads = self.client.get(f"agents/flow/{quote(self.workspace)}")["flows"]
        head = pick(heads)
        if pinned is not None:  # the box's session, as the service keeps it, else as the flow names it
            found = next((each for each in heads if each.get("session") == pinned[1]), None)
            head = found or {"session": pinned[1], "title": pinned[2], "status": "", "parent": ""}
        if head is None:
            self.flows = {}
            return self._seen(Seen(self.workspace))
        versions = {str(each["session"]): each.get("version") for each in heads}
        wanted = [str(head["session"])]
        for session in wanted:  # the followed session, then the subagents its flow and theirs name
            if session not in versions:
                continue
            held = self.flows.get(session)
            if held is None or held.get("version") != versions[session]:
                try:
                    changes = self.client.get(f"agents/flow/{quote(self.workspace)}/{quote(session)}",
                                              since=held["version"] if held else 0)  # fmt: skip
                except ClientError:
                    self.flows.pop(session, None)
                    continue
                self.flows[session] = merged(held, changes)
            named = [str(node.get("session")) for node in reversed(self.flows[session]["nodes"])
                     if node.get("kind") == "subagent" and node.get("session")]  # fmt: skip
            for child in named:
                if child not in wanted and len(wanted) <= SUBAGENTS:
                    wanted.append(child)
        self.flows = {session: flow for session, flow in self.flows.items() if session in wanted}
        root = self.flows.get(wanted[0])
        subagents = {session: flow for session, flow in self.flows.items() if session != wanted[0]}
        try:
            context = self.client.get(f"agents/context/{quote(self.workspace)}/{quote(wanted[0])}")
        except ClientError as error:  # the panel says why, for the session followed
            context = {"session": wanted[0], "unavailable": str(error)}
        try:
            guide = self.client.get(f"agents/guide/{quote(self.workspace)}/{quote(wanted[0])}")
        except ClientError as error:
            guide = {"session": wanted[0], "unavailable": str(error)}
        box = pinned[2] if pinned is not None else ""
        return self._seen(Seen(self.workspace, head, root, subagents, context, guide, box))

    def _seen(self, seen: Seen) -> Seen | None:
        """The page's to show, or None when it is what was shown last."""
        shown = (
            seen.workspace,
            seen.box,
            (seen.head or {}).get("session"),
            (seen.view or {}).get("version"),
            tuple(sorted((session, flow.get("version")) for session, flow in seen.subagents.items())),
            seen.context,
            seen.guide,
        )
        if shown == self._shown:
            return None
        self._shown = shown
        return seen


class Watching:
    """What the followed session does now, read from the service (one reading at a time)."""

    def __init__(self, client: Client) -> None:
        self.client = client
        self._last: tuple[str, str, dict[str, Any]] | None = None  # the workspace, the session and what it did
        self._reading = threading.Lock()
        self._writing = threading.Lock()

    def read(self, workspace: str, session: str) -> dict[str, Any] | None:
        """What the session does now; None when it is what the last reading of it said, or a reading is under way.
        Raises what the client raises but a refusal, which is said (`unavailable`)."""
        if not self._reading.acquire(blocking=False):
            return None
        try:
            found = doing(self.client, workspace, session)
            if self._last == (workspace, session, found):
                return None
            self._last = (workspace, session, found)
            return found
        finally:
            self._reading.release()

    def forget(self) -> None:
        """Forget the last reading, so the next one is returned even when it says what that one said: the page
        followed another session meanwhile and cleared what it showed of this one."""
        self._last = None

    def text(self, session: str, after: int, request: str) -> dict[str, Any] | None:
        """The session's request as it is written (`GET /gateway/live?session=`, design 0012 §7), from the character
        `after` of the request `request` on (or of its newest, "" for none held); None while a reading is under way.
        Raises what the client raises."""
        if not self._writing.acquire(blocking=False):
            return None
        try:
            found: dict[str, Any] = self.client.get("gateway/live", session=session, after=after, id=request)
            return found
        finally:
            self._writing.release()


class FlowReading:
    """The flow the Monitor's Flow view shows (`GET /flows/view`, design 0013 §12), read from the service one reading at
    a time: the folder's, or the one named (`flow`)."""

    def __init__(self, client: Client, folder: str) -> None:
        self.client, self.folder = client, folder
        self.flow = ""  # a flow named by the owner, `<workspace>/<name>`; "" for the one the folder follows
        self._last: str | None = None  # the version of the view last returned, or why there was none
        self._reading = threading.Lock()

    def read(self) -> dict[str, Any] | None:
        """The view; None when its version did not move since the last reading, or another reading is under way.
        Raises what the client raises."""
        if not self._reading.acquire(blocking=False):
            return None
        try:
            found: dict[str, Any] = self.client.get("flows/view", folder=self.folder, flow=self.flow)
            said = str(found.get("version") or found.get("why") or "")
            if said == self._last:
                return None
            self._last = said
            return found
        finally:
            self._reading.release()

    def forget(self) -> None:
        """Forget the last reading, so the next one is returned even when it did not change."""
        self._last = None
