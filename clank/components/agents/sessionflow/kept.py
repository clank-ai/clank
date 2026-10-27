"""The flows the service keeps (design 0012 §6.1, decision 0049): one for every session the watchers see, subagents'
included, in memory, with no database table.

`SessionFlows` listens to the watchers' lines (`Sessions.listen`): each line about a session goes to its flow, made the
first time the session is heard. A flow just made is read from OpenCode's history (`Sessions.page`, a page at a time
from the newest, up to `PAGES` pages), the steps finished by then marked done before Clank watched; it is read again, to
fill in what no line said, after its server's instance ended (`disposed`) or its watcher started again (`started`),
once that watcher synced (`synced`, which lists the servers that still run).
After a session's steps changed, the gateway is asked for its requests (its activity, with the requests that ended),
which the flow pairs with its steps, and again each round while one of them is held (design 0012 §9.4: no line comes
while the gateway holds a step's request); and the plan a session carries out is read from the workspace's folder when
it is named, and again when the agent edits it (`edited`). A subagent's flow tells its parent's what it says, briefly. A
session deleted in OpenCode leaves the flows kept.

None of this waits in the watcher's thread: a line only changes a flow and marks what is due, and the keeper's own round
(`work`, once a second while the service runs: `run`) reads the history (each page a `docker exec`), asks the gateway
and reads the plans. A round reads at most `READS` flows, the others waiting for the next, and it stops between two
of them when the service stops (`stop`), which does not wait for a `docker exec` under way. A reading that failed (the
bridge's refusal, a container gone) is tried again, after `RETRY_SECONDS`, then twice as long each time up to
`RETRY_MOST`, and said in the log once until it succeeds; a flow's first reading stays its first (its finished steps
then done before Clank watched) until it succeeds, whatever else made the flow due meanwhile. A flow whose server ended
(the watcher's `gone`, a `synced` that no longer lists its port, a reading the bridge answered `ServerGone`) is set
aside, neither read nor tried again, until a server answers on its port again (any line naming the port, the watch's
`server` first) or its session is heard again, and the log says once for that port that the window closed (on the
owner's machine, 2026-10-26, such histories were asked for over a thousand times in a day). The newest `KEPT` flows
of each workspace are kept, those working before those idle; a flow dropped is made again, and read again, if its
session is heard again. The flows whose version moved are given to the Watch for rules (`changed`, design 0012 §8).
"""

import logging
import posixpath
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol

import anyio
import anyio.to_thread

from clank.components.agents.plans import is_plan, plan_path
from clank.components.agents.sessionflow.branches import same_file
from clank.components.agents.sessionflow.flow import Flow
from clank.components.agents.sessions import ServerGone

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
KEPT = 64  # flows kept of each workspace
PAGE = 50  # messages read a page at a time
PAGES = 40  # pages read at most when a flow is read from the history
ROUND_SECONDS = 1.0  # how often the keeper does what is due
READS = 8  # flows read from the history in one round at most
RETRY_SECONDS = 2.0  # the wait before a reading that failed is tried again, doubled each time it fails again
RETRY_MOST = 60.0  # the longest such wait
LARGEST = 1_000_000  # bytes of a plan's file read
WORKING = ("busy", "retry")
Ask = Callable[[str], dict[str, Any]]  # a session's activity at the gateway, with its requests that ended
Read = Callable[[str, str], "str | None"]  # a file of a workspace's folder, by its path there; None when it cannot be
Key = tuple[str, str]  # a flow's workspace and session


class Reader(Protocol):
    """What the keeper needs of `Sessions`."""

    def listen(self, heard: Callable[[str, dict[str, Any]], None]) -> None:
        """Hear every watcher line."""

    def runs(self, workspace: str, session: str) -> int | None:
        """The port of the server that runs the session."""

    def page(self, workspace: str, port: int, session: str, *, limit: int = ..., before: str = ...) -> dict[str, Any]:
        """A page of the session's history."""


class SessionFlows:
    """A flow for every session the watchers see."""

    def __init__(self, sessions: Reader, ask: Ask, read: Read) -> None:
        self.sessions, self._ask, self._read = sessions, ask, read
        self._lock = threading.Lock()
        self._flows: dict[str, dict[str, Flow]] = {}  # by workspace, then session, the newest heard last
        self._reading: dict[Key, None] = {}  # flows due to be read from the history, in the order they became due
        self._first: set[Key] = set()  # flows not read from the history yet since they were made
        self._failed: dict[Key, tuple[int, float]] = {}  # flows whose reading failed: how often, and when to try again
        self._under_way: set[Key] = set()  # flows being read
        self._asking: set[Key] = set()  # sessions whose requests are due to be asked of the gateway
        self._planning: set[Key] = set()  # flows whose plan is due to be read
        self._told: dict[Key, dict[str, Any]] = {}  # what each subagent's flow last told its parent's
        self._syncing: set[Key] = set()  # flows to read again once their watcher, started again, synced
        self._gone: dict[str, set[int]] = {}  # each workspace's ports whose server ended, none heard there since
        self._aside: dict[Key, int] = {}  # flows due to be read whose server ended: the port they wait for
        self._said: set[tuple[str, int]] = set()  # the ports said closed in the log, until a server answers there
        self._stopped = threading.Event()
        sessions.listen(self.heard)

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A watcher's line: to the flow of the session it is about (made the first time), and what it makes due."""
        kind = str(line.get("type") or "")
        with self._lock:
            kept = self._flows.setdefault(workspace, {})
            port = line.get("port")
            if kind != "gone" and isinstance(port, int):
                self._back(workspace, port)  # a server speaks on that port: it runs
            if kind == "started":  # read again once the watcher synced: it says then which servers still run
                self._syncing.update((workspace, session) for session in kept)
                for session in kept:
                    self._reading.pop((workspace, session), None)
            elif kind == "synced":
                self._synced(workspace, {int(each) for each in line.get("ports") or []})
            elif kind == "disposed":
                self._due((workspace, session) for session, flow in kept.items() if flow.port == line.get("port"))
            elif kind == "gone" and isinstance(port, int):
                self._ended(workspace, port)
            elif kind == "edited":
                self._planning.update((workspace, session) for session, flow in kept.items()
                                      if flow.plan and same_file(str(line.get("file") or ""), flow.plan))  # fmt: skip
            elif kind == "session" and line.get("deleted"):
                session = _session_of(kind, line)
                kept.pop(session, None)
                self._forget((workspace, session))
            elif session := _session_of(kind, line):
                self._heard(workspace, session, kind, line)

    def flows(self, workspace: str) -> list[dict[str, Any]]:
        """The flows kept of a workspace's sessions, newest heard first, each briefly: its head and its version."""
        with self._lock:
            kept = list(self._flows.get(workspace, {}).values())
            return [{**flow.view()["head"], "version": flow.version} for flow in reversed(kept)]

    def flow(self, workspace: str, session: str, since: int = 0) -> dict[str, Any] | None:
        """A session's flow, whole or what changed after the version `since` (`Flow.changes`); None when not kept."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            return flow.changes(since) if flow is not None else None

    def view(self, workspace: str, session: str) -> dict[str, Any] | None:
        """A session's flow whole, as built now (`Flow.view`: the Guide reads it, design 0012 §9); None when not
        kept."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            return flow.view() if flow is not None else None

    def compaction_asked(self, workspace: str, session: str, index: int | None = None) -> None:
        """The Guide asked OpenCode to compact the session: its band at `index` (the next, by default) is the
        owner's (`Flow.compaction_asked`)."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            if flow is not None:
                flow.compaction_asked(index)

    def reverted(self, workspace: str, session: str, revert: dict[str, Any] | None) -> None:
        """OpenCode answered a revert of the session (an unrevert: None) with its revert as it now stands
        (`Flow.reverted`)."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            if flow is not None:
                flow.reverted(revert)

    def cleared(self, workspace: str, session: str, part: str, freed: int | None) -> None:
        """The Guide cleared a call's result in the session, freeing about `freed` tokens (`Flow.cleared`)."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            if flow is not None:
                flow.cleared(part, freed)

    def keys(self) -> set[Key]:
        """The sessions whose flows are kept, each by its workspace and id (the Watch for rules forget the others)."""
        with self._lock:
            return {(workspace, session) for workspace, kept in self._flows.items() for session in kept}

    def changed(self, versions: dict[Key, int]) -> list[tuple[str, str, int, dict[str, Any]]]:
        """The flows whose version is not the one in `versions` (each read after a change: the Watch for rules, design
        0012 §8): each one's workspace, session, version and view."""
        with self._lock:
            found = []
            for workspace, kept in self._flows.items():
                for session, flow in kept.items():
                    view = flow.view()
                    if versions.get((workspace, session)) != flow.version:
                        found.append((workspace, session, flow.version, view))
            return found

    async def run(self) -> None:
        """Do what is due, once a second, while the service runs; a round under way when it stops is left to end by
        itself, between two of its readings."""
        self._stopped.clear()
        try:
            while True:
                try:
                    await anyio.to_thread.run_sync(self.work, abandon_on_cancel=True)
                except Exception:
                    log.exception("keeping the sessions' flows failed")
                await anyio.sleep(ROUND_SECONDS)
        finally:
            self.stop()

    def stop(self) -> None:
        """The service stops: a round under way ends after what it is doing now."""
        self._stopped.set()

    def work(self) -> None:
        """One round: read the flows due from the history (`READS` at most, each when its wait after a failure is
        over), ask the gateway for the requests due, read the plans due, and tell each parent what its subagents' flows
        say; what the round did not reach before the service stopped stays due."""
        with self._lock:
            now = monotonic()
            reading = [key for key in self._reading if self._failed.get(key, (0, 0.0))[1] <= now][:READS]
            for key in reading:
                del self._reading[key]
            asking, self._asking = list(self._asking), set()
            planning, self._planning = list(self._planning), set()
        for index, key in enumerate(reading):
            if self._stopped.is_set():
                with self._lock:
                    self._due(reading[index:], again=False)
                    self._asking.update(asking)
                    self._planning.update(planning)
                return
            self._read_history(*key)
        for index, key in enumerate(asking):
            if self._stopped.is_set():
                with self._lock:
                    self._asking.update(asking[index:])
                    self._planning.update(planning)
                return
            self._requests(*key)
        for index, key in enumerate(planning):
            if self._stopped.is_set():
                with self._lock:
                    self._planning.update(planning[index:])
                return
            self._plan(*key)
        self._tell_parents()

    def _due(self, keys: Iterable[Key], *, again: bool = True) -> None:
        """Flows due to be read from the history; told `again` (a watcher synced, an instance ended), at once."""
        for key in keys:
            self._reading[key] = None
            if again:
                self._failed.pop(key, None)

    def _forget(self, key: Key) -> None:
        """A flow no longer kept: nothing of it stays due."""
        self._reading.pop(key, None)
        self._failed.pop(key, None)
        self._told.pop(key, None)
        self._aside.pop(key, None)
        for each in (self._first, self._asking, self._planning, self._syncing):
            each.discard(key)

    def _port(self, workspace: str, session: str, flow: Flow) -> int | None:
        """The server a flow is read from: the one the watchers saw run its session, else the one it was last heard
        on."""
        return self.sessions.runs(workspace, session) or flow.port

    def _synced(self, workspace: str, listed: set[int]) -> None:
        """A watcher started again read every server that runs: the flows it held back are read again, those whose
        server is not among them set aside, and that server's port is known to be gone."""
        for each in listed:
            self._back(workspace, each)
        kept = self._flows.get(workspace, {})
        ports = {session: self._port(workspace, session, flow) for session, flow in kept.items()}
        self._gone.setdefault(workspace, set()).update(
            port for port in ports.values() if port is not None and port not in listed
        )
        held = [key for key in self._syncing if key[0] == workspace]
        self._syncing.difference_update(held)
        for key in held:
            if key[1] not in kept:
                continue
            port = ports[key[1]]
            if port is not None and port not in listed:
                self._set_aside(key, port)
            else:
                self._due([key])

    def _ended(self, workspace: str, port: int) -> None:
        """A server stopped (`gone`): its sessions are idle, and a flow due to be read from it is set aside."""
        self._gone.setdefault(workspace, set()).add(port)
        for session, flow in self._flows.get(workspace, {}).items():
            if flow.port != port:
                continue
            flow.heard({"type": "status", "session": session, "status": "idle"})
            key = (workspace, session)
            if key in self._reading or key in self._syncing:  # nothing to read it from now
                self._syncing.discard(key)
                self._set_aside(key, port)

    def _set_aside(self, key: Key, port: int) -> None:
        """A flow due to be read whose server ended: it waits for that port to answer again (`_back`), or for its
        session to be heard again; the log says once for the port that the window closed."""
        self._aside[key] = port
        self._reading.pop(key, None)
        self._failed.pop(key, None)
        self._gone.setdefault(key[0], set()).add(port)
        if (key[0], port) not in self._said:
            self._said.add((key[0], port))
            log.warning("the OpenCode window of %s on port %d closed: its sessions are kept as they were", key[0], port)

    def _back(self, workspace: str, port: int) -> None:
        """A server answers on the port (a line names it): the flows set aside for it are due to be read again."""
        self._gone.get(workspace, set()).discard(port)
        self._said.discard((workspace, port))
        waiting = [key for key, waited in self._aside.items() if key[0] == workspace and waited == port]
        for key in waiting:
            del self._aside[key]
        self._due(waiting)

    def _heard(self, workspace: str, session: str, kind: str, line: dict[str, Any]) -> None:
        kept = self._flows[workspace]
        key = (workspace, session)
        flow = kept.pop(session, None)
        if flow is None:
            flow = Flow(session, workspace)
            self._first.add(key)
            self._reading[key] = None
        elif key in self._aside:  # its session speaks again: read from where it runs now
            del self._aside[key]
            self._due([key])
        elif key in self._first and key not in self._reading and key not in self._under_way:
            self._reading[key] = None  # its first reading waited for its server, which speaks again
        kept[session] = flow  # the newest heard last
        flow.heard(line)
        if kind in ("message", "part", "status", "removed"):
            self._asking.add((workspace, session))
        if kind == "part" and (line.get("part") or {}).get("type") == "text":
            self._planning.add((workspace, session))  # a message of the owner's may name a plan
        if len(kept) > KEPT:
            idle = [id for id, each in kept.items() if each.view()["head"]["status"] not in WORKING and id != session]
            for id in (idle or list(kept))[: len(kept) - KEPT]:
                del kept[id]
                self._forget((workspace, id))

    def _read_history(self, workspace: str, session: str) -> None:
        """Read a flow from the session's history, a page at a time from the newest, on the server that runs it; its
        first reading marks the steps finished by then done before Clank watched. One that failed is tried again, said
        once; one whose server ended is set aside instead."""
        key = (workspace, session)
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            if flow is None:
                return
            port = self._port(workspace, session, flow)
            if port is not None and port in self._gone.get(workspace, set()):
                self._set_aside(key, port)
                return
            since, joined = flow.mark(), key in self._first
            self._under_way.add(key)
        pages: list[dict[str, Any]] = []
        try:
            if port is None:
                raise RuntimeError("no server is known to run it")
            before = ""
            for _ in range(PAGES):
                if self._stopped.is_set():
                    raise RuntimeError("the service stops")
                found = self.sessions.page(workspace, port, session, limit=PAGE, before=before)
                pages.append(found)
                before = str(found.get("next") or "")
                if not before:
                    break
        except Exception as error:  # the bridge's refusal, a container gone: tried again after a wait
            tries = 0
            with self._lock:
                self._under_way.discard(key)
                if self._flows.get(workspace, {}).get(session) is flow:
                    if isinstance(error, ServerGone) and port is not None:
                        self._set_aside(key, port)
                    else:
                        tries = self._failed.get(key, (0, 0.0))[0] + 1
                        self._failed[key] = (tries, monotonic() + min(RETRY_SECONDS * 2 ** (tries - 1), RETRY_MOST))
                        self._reading[key] = None
            if tries == 1:
                log.warning("the history of %s in %s could not be read: %s (tried again, a little later each time)",
                            session, workspace, error)  # fmt: skip
            return
        with self._lock:
            self._under_way.discard(key)
            if self._flows.get(workspace, {}).get(session) is not flow:
                return  # dropped meanwhile
            for found in reversed(pages):  # oldest first
                flow.history(found, since=since, joined=joined)
            self._first.discard(key)
            self._failed.pop(key, None)
            if any(found.get("messages") for found in pages):  # what it read may pair, or name a plan
                self._asking.add(key)
                self._planning.add(key)

    def _requests(self, workspace: str, session: str) -> None:
        """The gateway's requests of the session, in flight and ended, to its flow."""
        try:
            found = self._ask(session)
        except Exception as error:
            log.warning("the gateway's requests of %s could not be read: %s", session, error)
            return
        requests = [*(found.get("ended") or []), *(found.get("requests") or [])]
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            if flow is not None:
                flow.requests([each for each in requests if each.get("session") == session])
            if any(isinstance(each.get("held"), dict) and not each["held"].get("until")
                   for each in requests if each.get("session") == session):  # fmt: skip
                self._asking.add((workspace, session))  # held: no line comes until it goes on, so asked each round

    def _plan(self, workspace: str, session: str) -> None:
        """The plan the session carries out, as its file reads now."""
        with self._lock:
            flow = self._flows.get(workspace, {}).get(session)
            plan = flow.plan if flow is not None else ""
        if flow is None or not plan:
            return
        text = self._read(workspace, plan)
        with self._lock:
            flow.planned(text)

    def _tell_parents(self) -> None:
        """Each subagent's flow tells its parent's what it says: its title, its status, its steps and its calls."""
        with self._lock:
            for workspace, kept in self._flows.items():
                for session, flow in kept.items():
                    head = flow.view()["head"]
                    parent = kept.get(str(head.get("parent") or ""))
                    if parent is None:
                        continue
                    told = {key: head.get(key) for key in ("title", "status", "steps", "calls", "parent")}
                    if self._told.get((workspace, session)) != told:
                        parent.child(session, told)
                        self._told[(workspace, session)] = told


def _session_of(kind: str, line: dict[str, Any]) -> str:
    """The session a line is about ("" for a line about none, or one the flows do not use)."""
    if kind == "session":
        return str((line.get("session") or {}).get("id") or "")
    if kind == "asked":
        return str((line.get("request") or {}).get("sessionID") or "")
    if kind in ("message", "part", "removed", "todo", "compacted", "error", "status", "replied"):
        return str(line.get("session") or "")
    return ""


def gateway_asker(kernel: "Kernel") -> Ask:
    """How the keeper asks the gateway for a session's requests: its activity with the requests that ended."""

    def ask(session: str) -> dict[str, Any]:
        found: dict[str, Any] = kernel.parts["gateway"].activity(session, False, True)
        return found

    return ask


def plan_reader(kernel: "Kernel") -> Read:
    """How the keeper reads a plan: from the workspace's folder on this machine, a Markdown file in it whose header says
    it is a plan (design 0009 §4); None otherwise, and for a name that leads outside the folder (a model may write the
    name a subagent's message gives)."""
    from clank.components.workspaces.service import WORKSPACE

    def read(workspace: str, named: str) -> str | None:
        relative = posixpath.relpath(named, WORKSPACE) if named.startswith(WORKSPACE + "/") else named
        relative = posixpath.normpath(relative.replace("\\", "/"))
        if not plan_path(relative):
            return None
        try:
            folder = Path(kernel.parts["workspaces"].folder_of(workspace)).resolve()
            path = folder.joinpath(*relative.split("/")).resolve()
            if not path.is_relative_to(folder) or path.stat().st_size > LARGEST:
                return None
            text = path.read_bytes().decode("utf-8", errors="replace")
        except Exception:
            return None
        return text if is_plan(text) else None

    return read
