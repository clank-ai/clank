"""The session bridge (design 0005 §2): the service's way to the OpenCode servers running in a workspace's container.

Every OpenCode Clank starts serves its API on a port of its own on the container's loopback (`--port`, the first free
one from 4096), and `/opt/clank/bridge.py`, in the sandbox image, talks to them: the service runs it with `docker exec`,
one run an action, and reads the JSON it prints. So a running session (the one in VS Code's terminal, or the console's)
can be followed and driven from another client, the phone first: its sessions with their status, the permissions and
questions waiting, a session's last messages; sending a message (without waiting for the answer), starting a session
(OpenCode without a terminal is started first when none runs), stopping it, replying to a permission or a question;
and the MCP servers of the agents running there: their state, and starting or stopping one while they run (OpenCode
connects or disconnects it, or adds one it was not started with). Each action is recorded (`agents.acted`) with who did
it.

The Monitor's actions (design 0012 §9) are here too: rejecting what waits in a session, compacting it, clearing a tool
call's result, reverting and unreverting, and reading its history a page at a time. A message sent to a session the
gateway holds (design 0012 §9.4) closes the request it held before the message was sent once the message is sent, so
OpenCode reads it next, while the pause stays (the request that carries it is held until the owner resumes); the pause
and the resume themselves are the gateway's, recorded here too (`acted`).

A container may run several OpenCode servers (a window's, the phone's, a flow's) that list the same sessions, since
their storage is shared, while only one runs each (design 0012 §3). So the service keeps, from its watchers' lines
(`heard`), the server whose stream carried each session's run, and every action on a session goes there (decision 0079);
only a session no watcher saw, or one whose server the watcher no longer follows (a watcher started again, after its
container was reopened), goes to the port a client names. Listeners (`listen`) hear every line once the review has
handled it: the Monitor's flows (step 5) and the flows' runner (design 0013).

For a flow's runner (design 0013 §4, §5, §7): the sessions at work that are no box's, the owner's own, which a switch
of the main slot waits for (`working`); the flow's own server, without a terminal, ended to be started again with a
box's limits (`end_server`: `pkill` of its `opencode serve --port N`, never a window); and the MCP servers of that one
server read, connected and disconnected (`mcp_on`, `mcp_switch_on`), the other agents' left as they are.
"""

import json
import logging
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
Heard = Callable[[str, dict[str, Any]], None]
RUNNING = ("status", "message", "part", "delta", "removed", "todo", "compacted", "error")  # lines of a session's run
READ_SECONDS = 30.0
SERVE_SECONDS = 60.0
# An OpenCode window: OpenCode with a terminal, as its command line starts (`pgrep -f`'s extended regular expression);
# OpenCode without one runs as `opencode serve`, which this leaves alone.
WINDOW = "(^|/)opencode --port "
SERVED = "(^|/)opencode serve --port {port}( |$)"  # OpenCode without a terminal on one port, as the bridge starts it
AT_WORK = ("busy", "retry")  # a session's status while it works
FAMILY = 50  # the most parents walked up from a subagent
CLOSE_SECONDS = 10.0  # how long a window asked to end may take before it is ended
MCP_SECONDS = 120.0  # an MCP server's start, which OpenCode waits for
REPLIES = ("once", "always", "reject")
EVENT_TYPES = [
    EventType(
        "agents.acted",
        "Someone acted on an agent's session in a workspace: sent a message, started a session, stopped one, or "
        "replied to what the agent asked (design 0005 §2).",
        {
            "workspace": "The workspace.",
            "port": "The OpenCode server's port in the container.",
            "session": "The session.",
            "action": "message, start, show (a session running already shown on a window), stop, permission, "
            "question, mcp (an MCP server started or stopped), cycle (the window's agent switched), reject (what "
            "waited was rejected), compact, clear (a tool call's result cleared), undo (steps taken back), redo "
            "(brought back), pause (its next model requests held in the gateway) or resume.",
            "detail": "The reply, or the message's first words; for a reject, how many waited; for a clear, the part "
            "and its message; for an undo, where it starts.",
        },
    )
]


class SessionError(Exception):
    """An action on a session that could not be done, and why (in the bridge's or OpenCode's words)."""


@dataclass
class Seen:
    """A session as the watchers last saw it: the server whose stream carried its run (None once that server is
    gone), its status there, its parent when it is a subagent's, and its title."""

    port: int | None
    status: str = "idle"
    parent: str | None = None
    title: str = ""


class Sessions:
    """The sessions of the OpenCode servers in the workspaces' containers, through the bridge."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        self._seen: dict[str, dict[str, Seen]] = {}  # by workspace, then session
        self._listeners: list[Heard] = []
        self._lock = threading.Lock()

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A line of a workspace's watcher: where each session runs, its status, its parent; then every listener."""
        kind = line.get("type")
        with self._lock:
            seen = self._seen.setdefault(workspace, {})
            if kind == "started":  # a watcher started again: what runs is said again
                for each in seen.values():
                    each.status = "idle"
            elif kind == "synced":  # a server no longer followed ended while no watcher heard it
                followed = {int(port) for port in line.get("ports") or []}
                for each in seen.values():
                    if each.port is not None and each.port not in followed:
                        each.port, each.status = None, "idle"
            elif kind == "gone":
                for each in seen.values():
                    if each.port == line.get("port"):
                        each.port, each.status = None, "idle"
            elif kind == "session" and isinstance(line.get("session"), dict):
                info = line["session"]
                id = str(info.get("id") or "")
                if id and line.get("deleted"):
                    seen.pop(id, None)
                elif id:
                    each = seen.setdefault(id, Seen(port=int(line["port"])))
                    each.parent = info.get("parent") or each.parent
                    each.title = str(info.get("title") or each.title)
            elif kind in RUNNING and line.get("session") and line.get("port"):
                each = seen.setdefault(str(line["session"]), Seen(port=int(line["port"])))
                each.port = int(line["port"])
                if kind == "status":
                    each.status = str(line.get("status") or "idle")
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(workspace, line)
            except Exception:
                log.exception("a listener failed on a line from %s's watcher", workspace)

    def listen(self, heard: Heard) -> None:
        """Hear every line of every workspace's watcher, once the service has read it (the review has handled it)."""
        with self._lock:
            self._listeners.append(heard)

    def runs(self, workspace: str, session: str) -> int | None:
        """The port of the server that runs the session (or ran it last), as the watchers saw; None when none did."""
        with self._lock:
            each = self._seen.get(workspace, {}).get(session)
            return each.port if each is not None else None

    def reach(self, workspace: str, session: str) -> int | None:
        """The port of a server that reaches the session: the one the watchers saw it on, else one of the workspace's
        servers that lists it, else the first that runs, since every OpenCode server of a folder reads the sessions it
        keeps on disk (after the service restarts it has seen none); None when none runs or the container does not
        answer."""
        known = self.runs(workspace, session)
        if known is not None:
            return known
        try:
            running = self.servers(workspace)
        except Exception:  # the workspace's container does not answer: as if none ran
            return None
        listing = [each for each in running if any(one.get("id") == session for one in each.get("sessions") or [])]
        found = (listing or running)[:1]
        return int(found[0]["port"]) if found else None

    def seen(self, workspace: str) -> list[dict[str, Any]]:
        """Each session the workspace's watcher saw: its server, its status, its parent and its title."""
        with self._lock:
            return [
                {"session": id, "port": each.port, "status": each.status, "parent": each.parent, "title": each.title}
                for id, each in self._seen.get(workspace, {}).items()
            ]

    def working(self, workspace: str, besides: Collection[str] = ()) -> list[dict[str, Any]]:
        """The sessions at work in the workspace (busy or retrying, as its watcher last said, on a server that still
        runs) that are not one of `besides` (a flow's boxes' sessions) nor a subagent of one, however deep: the owner's
        own, which a flow's switch of the main slot waits for (design 0013 §7, decision 0062)."""
        apart = set(besides)
        with self._lock:
            seen = dict(self._seen.get(workspace, {}))

        def set_apart(id: str) -> bool:
            for _ in range(FAMILY):
                if id in apart:
                    return True
                each = seen.get(id)
                if each is None or not each.parent:
                    return False
                id = each.parent
            return False

        return [
            {"session": id, "port": each.port, "status": each.status, "parent": each.parent, "title": each.title}
            for id, each in seen.items()
            if each.port is not None and each.status in AT_WORK and not set_apart(id)
        ]

    def _server(self, workspace: str, session: str, port: int) -> int:
        """Where an action on the session goes: the server that runs it, else the port named."""
        known = self.runs(workspace, session)
        return known if known is not None else int(port)

    def servers(self, workspace: str) -> list[dict[str, Any]]:
        """Each OpenCode server in the workspace's container: its port, its sessions (with their status), and the
        permissions and questions waiting."""
        found: list[dict[str, Any]] = self._bridge(workspace, ["servers"])["servers"]
        return found

    def messages(self, workspace: str, port: int, session: str, limit: int = 40) -> dict[str, Any]:
        """A session's last messages, briefly: their text, their tools with titles and states, their files."""
        return self._bridge(workspace, ["messages", str(port), session, str(limit)])

    def free_port(self, workspace: str) -> int:
        """The first port no OpenCode in the container listens on: the next one Clank starts gets it."""
        return int(self._bridge(workspace, ["free-port"])["port"])

    def close_windows(self, workspace: str) -> int:
        """Close every OpenCode window in the workspace's container (design 0004 §5: one at a time), each asked to end
        and ended after `CLOSE_SECONDS` if it has not; OpenCode without a terminal is left. How many there were."""
        found = self._windows(workspace)
        if not found:
            return 0
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        workspaces.run_in(workspace, ["pkill", "-TERM", "-f", WINDOW])
        deadline = time.monotonic() + CLOSE_SECONDS
        while self._windows(workspace):
            if time.monotonic() >= deadline:
                workspaces.run_in(workspace, ["pkill", "-KILL", "-f", WINDOW])
                break
            time.sleep(0.2)
        return len(found)

    def end_server(self, workspace: str, port: int) -> str:
        """End the OpenCode without a terminal on `port` in the workspace's container (a flow's server, started again
        with a box's limits: design 0013 §5), asked to end and ended after `CLOSE_SECONDS` if it has not: ended,
        killed, or gone when nothing runs there. A window is never ended this way (`SessionError`)."""
        found = next((each for each in self.servers(workspace) if int(each["port"]) == port), None)
        if found is None:
            return "gone"
        if found.get("terminal"):
            raise SessionError(f"port {port} runs an OpenCode window in {workspace}: Clank ends no window for a flow")
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        served = SERVED.format(port=port)
        workspaces.run_in(workspace, ["pkill", "-TERM", "-f", served])
        deadline = time.monotonic() + CLOSE_SECONDS
        while workspaces.run_in(workspace, ["pgrep", "-f", served]).status == 0:
            if time.monotonic() >= deadline:
                workspaces.run_in(workspace, ["pkill", "-KILL", "-f", served])
                return "killed"
            time.sleep(0.2)
        return "ended"

    def _windows(self, workspace: str) -> list[str]:
        """The process ids of the OpenCode windows in the workspace's container (none when it cannot say)."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        answer = workspaces.run_in(workspace, ["pgrep", "-f", WINDOW])
        return [pid for pid in answer.output.split() if pid.isdigit()] if answer.status == 0 else []

    def send(
        self,
        workspace: str,
        port: int,
        session: str,
        text: str,
        *,
        actor: Actor,
        files: list[dict[str, str]] | None = None,
        agent: str = "",
        model: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a message to a session, with files (an image, as {url, mime, filename}); the agent answers in its own
        time (the session's messages show it). It goes with the agent and the model given, else with those of the
        session's last message of the owner (design 0012 §9.3), to the server that runs the session; what the bridge
        says it sent (`agent`, `model`)."""
        port = self._server(workspace, session, port)
        given: dict[str, Any] = {"text": text, "files": files or []}
        if agent:
            given["agent"] = agent
        if model:
            given["model"] = model
        before = to_text(self.kernel.clock.now())  # what the gateway held before now never carries this message
        found = self._bridge(workspace, ["prompt", str(port), session], given)
        self._acted(workspace, port, session, "message", " ".join(text.split())[:80], actor)
        self._release(session, before)
        return {"agent": str(found.get("agent") or ""), "model": dict(found.get("model") or {})}

    def serve(self, workspace: str, env: dict[str, str]) -> int:
        """Start OpenCode without a terminal in the workspace's container, with `env` (a flow's server, design 0013
        §5); its port."""
        return int(self._bridge(workspace, ["serve"], {"env": env}, timeout=SERVE_SECONDS)["port"])

    def new(self, workspace: str, port: int, title: str, *, actor: Actor) -> str:
        """A new session on the server on `port`, with its title (a flow's box, design 0013 §5); its id."""
        session = str(self._bridge(workspace, ["new", str(port)], {"title": title})["session"])
        self._acted(workspace, port, session, "start", title, actor)
        return session

    def start(self, workspace: str, text: str, *, env: dict[str, str], actor: Actor, title: str = "") -> dict[str, Any]:
        """A new session in the workspace, on its first OpenCode server (one without a terminal is started when none
        runs), with a first message; its port and id."""
        running = self.servers(workspace)
        port = int(running[0]["port"]) if running else self.serve(workspace, env)
        session = str(self._bridge(workspace, ["new", str(port)], {"title": title})["session"])
        self._acted(workspace, port, session, "start", title or " ".join(text.split())[:80], actor)
        if text.strip():
            self.send(workspace, port, session, text, actor=actor)
        return {"port": port, "session": session}

    def stop(self, workspace: str, port: int, session: str, *, actor: Actor) -> None:
        """Stop what the session does now, on the server that runs it."""
        port = self._server(workspace, session, port)
        self._bridge(workspace, ["abort", str(port), session])
        self._acted(workspace, port, session, "stop", "", actor)

    def reject(self, workspace: str, port: int, session: str, *, actor: Actor) -> dict[str, list[str]]:
        """Reject what waits in the session and its subagents (design 0012 §9.2): the asks and the questions
        rejected."""
        port = self._server(workspace, session, port)
        found = self._bridge(workspace, ["reject", str(port), session])
        rejected = {"rejected": list(found["rejected"]), "questions": list(found["questions"])}
        count = len(rejected["rejected"]) + len(rejected["questions"])
        self._acted(workspace, port, session, "reject", f"{count} waiting", actor)
        return rejected

    def compact(
        self, workspace: str, port: int, session: str, *, actor: Actor, model: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Ask OpenCode to compact the session at its next step (design 0012 §9.6), without waiting for it."""
        port = self._server(workspace, session, port)
        found = self._bridge(workspace, ["summarize", str(port), session], model or {})
        self._acted(workspace, port, session, "compact", "", actor)
        return {"asked": bool(found.get("asked")), "answered": bool(found.get("answered"))}

    def clear(
        self, workspace: str, port: int, session: str, message: str, part: str, *, actor: Actor
    ) -> dict[str, Any]:
        """Clear a finished tool call's result, as OpenCode's own compaction does (design 0012 §9.7)."""
        port = self._server(workspace, session, port)
        found = self._bridge(workspace, ["clear", str(port), session, message, part])
        self._acted(workspace, port, session, "clear", f"{part} of {message}", actor)
        return {"cleared": True, "compacted": found["compacted"], "length": found["length"]}

    def revert(
        self, workspace: str, port: int, session: str, message: str, part: str = "", *, actor: Actor
    ) -> dict[str, Any]:
        """Take back the session from a message (a part of it) on (design 0012 §9.5); what OpenCode keeps of it."""
        port = self._server(workspace, session, port)
        found = self._bridge(workspace, ["revert", str(port), session, message, *([part] if part else [])])
        self._acted(workspace, port, session, "undo", f"from {part or message}", actor)
        return dict(found.get("revert") or {})

    def unrevert(self, workspace: str, port: int, session: str, *, actor: Actor) -> dict[str, Any]:
        """Bring back what the last revert took back; what OpenCode keeps of a revert then (none, once done)."""
        port = self._server(workspace, session, port)
        found = self._bridge(workspace, ["unrevert", str(port), session])
        self._acted(workspace, port, session, "redo", "", actor)
        return dict(found.get("revert") or {})

    def page(self, workspace: str, port: int, session: str, *, limit: int = 50, before: str = "") -> dict[str, Any]:
        """A page of the session's messages, oldest first, in the Monitor's shape, and the cursor of the page before
        it ("" at its first message)."""
        port = self._server(workspace, session, port)
        return self._bridge(workspace, ["page", str(port), session, str(limit), *([before] if before else [])])

    def part(self, workspace: str, port: int, session: str, message: str, part: str) -> dict[str, Any]:
        """One tool call of the session whole (design 0012 §7: the watch cuts a call's input and output), from the
        server that runs it: its input and its output, each cut only past the bridge's cap."""
        port = self._server(workspace, session, port)
        found: dict[str, Any] = self._bridge(workspace, ["part", str(port), session, message, part])["part"]
        return found

    def permission(
        self, workspace: str, port: int, request: str, reply: str, *, actor: Actor, message: str = ""
    ) -> None:
        """Reply to a permission the agent asked for: once, always or reject; a reject may tell the model why."""
        if reply not in REPLIES:
            raise SessionError(f"a permission's reply is once, always or reject, not {reply!r}")
        self._bridge(workspace, ["permission", str(port), request, reply], {"message": message} if message else None)
        self._acted(workspace, port, request, "permission", f"{reply}: {message}" if message else reply, actor)

    def question(self, workspace: str, port: int, request: str, answers: list[list[str]], *, actor: Actor) -> None:
        """Answer a question the agent asked: for each of its questions, the options chosen (or a text of one's own)."""
        self._bridge(workspace, ["question", str(port), request], {"answers": answers})
        self._acted(workspace, port, request, "question", "; ".join(", ".join(each) for each in answers)[:80], actor)

    def mcp(self, workspace: str) -> dict[str, dict[str, str]] | None:
        """The MCP servers of the agents running in the workspace's container, by name, each with its status
        (connected when any agent has it connected, else what one says, with why it failed); None when no agent runs."""
        running = self._bridge(workspace, ["mcp"])["servers"]
        if not running:
            return None
        found: dict[str, dict[str, str]] = {}
        for server in running:
            for name, status in server["mcp"].items():
                if found.get(name, {}).get("status") != "connected":
                    found[name] = status
        return found

    def mcp_switch(self, workspace: str, name: str, on: bool, config: dict[str, Any], *, actor: Actor) -> int:
        """Start an MCP server (connected, or added with its entry) or stop it, in every agent running in the
        workspace's container; how many agents there are."""
        ports = [int(server["port"]) for server in self._bridge(workspace, ["mcp"])["servers"]]
        for port in ports:
            if on:
                self._bridge(workspace, ["mcp-start", str(port), name], {"config": config}, timeout=MCP_SECONDS)
            else:
                self._bridge(workspace, ["mcp-stop", str(port), name])
        if ports:
            self._acted(workspace, ports[0], "", "mcp", f"{name} {'started' if on else 'stopped'}", actor)
        return len(ports)

    def mcp_on(self, workspace: str, port: int) -> dict[str, dict[str, str]]:
        """The MCP servers of the OpenCode on `port` alone, by name, each with its status and why it failed; none when
        nothing answers there."""
        for server in self._bridge(workspace, ["mcp"])["servers"]:
            if int(server["port"]) == port:
                return {str(name): dict(status) for name, status in server["mcp"].items()}
        return {}

    def mcp_switch_on(self, workspace: str, port: int, name: str, on: bool, config: dict[str, Any]) -> None:
        """Connect an MCP server (or add it with its entry, `config`) or disconnect it, in the OpenCode on `port` alone
        (a flow's box's tools, design 0013 §4); the other agents in the container keep theirs."""
        if on:
            self._bridge(workspace, ["mcp-start", str(port), name], {"config": config}, timeout=MCP_SECONDS)
        else:
            self._bridge(workspace, ["mcp-stop", str(port), name])

    def agents(self, workspace: str, port: int) -> list[str]:
        """The agents Tab cycles through in the terminal interface on `port`, in its order."""
        return [str(name) for name in self._bridge(workspace, ["agents", str(port)])["agents"]]

    def cycle(self, workspace: str, port: int, count: int, *, actor: Actor) -> None:
        """Do what Tab does in the terminal interface on `port`, `count` times (design 0009 §7)."""
        self._bridge(workspace, ["cycle", str(port), str(count)])
        self._acted(workspace, port, "", "cycle", f"Tab {count}x", actor)

    def implement(
        self, workspace: str, port: int, text: str, *, title: str, actor: Actor, agent: str = "", wait: float = 0.0
    ) -> str:
        """A new session in the window on `port` whose first message `build` is sent (or `agent`), then shown there
        (design 0009 §8); with `wait`, a window still starting is waited for that many seconds (a planning session,
        design 0013 §15); its id."""
        return self.start_in_window(workspace, port, text, title=title, actor=actor, agent=agent, wait=wait)[0]

    def show_in_window(self, workspace: str, port: int, session: str, *, actor: Actor, wait: float = 0.0) -> bool:
        """Show a session that runs already in the window on `port` (`clank flow attach`, design 0013 §15), a window
        still starting waited for up to `wait` seconds; whether the window showed it."""
        found = self._bridge(workspace, ["show", str(port), session], {"wait": wait}, timeout=SERVE_SECONDS + wait)
        self._acted(workspace, port, session, "show", "on the window at this port", actor)
        return bool(found.get("shown", True))

    def start_in_window(
        self, workspace: str, port: int, text: str, *, title: str, actor: Actor, agent: str = "", wait: float = 0.0
    ) -> tuple[str, bool]:
        """`implement`'s session and whether the window showed it (it stands either way)."""
        asked: dict[str, Any] = {"text": text, "title": title, **({"agent": agent} if agent else {})}
        if wait:
            asked["wait"] = wait
        found = self._bridge(workspace, ["implement", str(port)], asked, timeout=SERVE_SECONDS + wait)
        session = str(found["session"])
        self._acted(workspace, port, session, "start", title, actor)
        return session, bool(found.get("shown", True))

    def _bridge(
        self, workspace: str, argv: list[str], given: dict[str, Any] | None = None, timeout: float = READ_SECONDS
    ) -> dict[str, Any]:
        from clank.components.workspaces.service import BRIDGE_PROGRAM, WorkspaceUnavailable

        workspaces: Workspaces = self.kernel.parts["workspaces"]
        data = json.dumps(given).encode() if given is not None else None
        try:
            answer = workspaces.run_in(workspace, ["python3", BRIDGE_PROGRAM, *argv], input=data, timeout=timeout)
        except WorkspaceUnavailable as error:
            raise SessionError(str(error)) from error
        try:
            found = json.loads(answer.output.strip().splitlines()[-1]) if answer.output.strip() else None
        except ValueError:
            found = None
        if not isinstance(found, dict):
            said = (answer.errors or answer.output).strip()[-300:]
            if "bridge.py" in said and ("No such file" in said or "can't open file" in said):
                raise SessionError(
                    f"{workspace}'s container runs an older sandbox image, without the bridge: stop the workspace and "
                    "open it again (Workspaces, F6: x, then o) so its agents can be reached"
                )
            raise SessionError(f"the bridge in {workspace}'s container did not answer: {said or 'nothing said'}")
        if not found.get("ok"):
            said = str(found.get("error") or "the bridge refused")
            if said.startswith("no action"):
                raise SessionError(
                    f"{workspace}'s container runs an older sandbox image: stop the workspace and open it again "
                    "(Workspaces, F6: x, then o) for this"
                )
            raise SessionError(said)
        return found

    def _release(self, session: str, before: str) -> None:
        """A message was sent: the request the gateway held of the session before it was sent (`before`), if any, ends
        as an empty step, so OpenCode reads the message at its next step, which is held again (design 0012 §9.4). One
        held since may already carry the message (the session was idle, or its step ended meanwhile): it stays held,
        since an empty step in its place would end the run with the message unanswered. A gateway that does not answer
        holds nothing to close: said in the log."""
        gateway = self.kernel.parts.get("gateway")
        if gateway is None:
            return
        try:
            gateway.release(session, before)
        except Exception as error:
            log.warning("the gateway's hold of %s could not be closed: %s", session, error)

    def acted(self, workspace: str, port: int | None, session: str, action: str, detail: str, actor: Actor) -> None:
        """Record an action on a session taken elsewhere (the gateway's pause and resume, design 0012 §9.4)."""
        self._acted(workspace, port, session, action, detail, actor)

    def _acted(self, workspace: str, port: int | None, session: str, action: str, detail: str, actor: Actor) -> None:
        told = {"message": "sent a message to", "start": "started", "show": "showed a session of", "stop": "stopped",
                "permission": "replied to", "question": "answered", "mcp": "changed the MCP servers of",
                "cycle": "switched the agent of",
                "reject": "rejected what waited in", "compact": "asked to compact the session of",
                "clear": "cleared a tool call's result in", "undo": "took back steps of",
                "redo": "brought back steps of", "pause": "paused", "resume": "resumed"}[action]  # fmt: skip
        self.kernel.events.record(
            "agents.acted",
            summary=f"{actor.describe()} {told} {workspace}'s agent ({action}: {detail})"
            if detail
            else f"{actor.describe()} {told} {workspace}'s agent",
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "port": port, "session": session, "action": action, "detail": detail},
        )
