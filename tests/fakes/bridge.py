"""A fake of the bridge in a workspace's container (design 0005 §2), answered in this process, with a scripted agent.

The fake platform's `inside` hands it each command the service runs in the container (`python3 /opt/clank/bridge.py
<action> ...`); it answers the actions the flows' runner and the review use as the bridge does (one line of JSON):
`servers`, `free-port`, `serve` (an OpenCode without a terminal on the next port), `new` (a session with its title),
`prompt` (the message, its agent and its model kept), `implement` (a session in a window, its first message sent to
the agent asked and the session shown there, a window still starting waited for: design 0013 §15), `abort`,
`permission`, and each server's MCP servers (`mcp`, `mcp-start`, `mcp-stop` on one port: a server served starts with
those its configuration names connected, read through `configuration` when the test gives it, and kept as it was
then). `pkill -f` and `pgrep -f` match each server's command line, `opencode serve --port N` or a window's `opencode
--port N`, and an OpenCode ended is gone (its watcher says so).
What OpenCode would then do is the test's
to say, through the watcher's lines (`say`, handed to the service as its watcher would): a session's status, a step's
tokens, a server gone. `finish` is the scripted agent at work: it writes files in the folder, then the session goes idle
(`finish_unheard`: the same, its watcher saying nothing). A command the runner runs in the container (a box's accept
command, run under `timeout` by `accepting.RUN`) is answered from `commands`, after what `effects` says it does in the
folder, and kept in `ran`; held by `hold` (by its words) until the test lets it go on, or until the runner ends it
(`accepting.END`, kept in `ended`: it then answers 143, as a command sent `TERM`). A job (`jobs.START`, design 0013
§17) writes its files in the folder as the container's would: its command and process id at once; its log (the
answer `commands` gives) and exit once `effects` ran, and once `hold` lets it go on; `jobs.END` ends it with 143 (kept
in `jobs_ended`), and `jobs.ALIVE` says whether it still runs; a job in `vanish` ends without an exit, as a process
killed with its container would. Nothing runs in a container, and no OpenCode runs.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clank.components.flows import accepting, jobs
from clank.kernel.processes import Answer

Heard = Callable[[str, dict[str, Any]], None]
FIRST_PORT = 4096


@dataclass
class Server:
    """An OpenCode server in the container: whether it runs a terminal interface, its sessions and their status."""

    port: int
    terminal: bool = False
    env: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    config: str | None = None  # its configuration, as the container's file said when it was served
    mcp: dict[str, str] = field(default_factory=dict)  # each MCP server's status: connected, disabled, failed

    def command_line(self) -> str:
        """Its command line in the container: a window's, or OpenCode without a terminal."""
        if self.terminal:
            return f"opencode --port {self.port} --hostname 127.0.0.1"
        return f"opencode serve --port {self.port} --hostname 127.0.0.1"


@dataclass
class Prompt:
    """A message sent to a session."""

    port: int
    session: str
    title: str
    text: str
    agent: str
    model: dict[str, str]


class FakeBridge:
    """The bridge in one workspace's container, in this process."""

    def __init__(self, workspace: str, folder: Path, hear: Heard | None = None) -> None:
        self.workspace = workspace
        self.folder = folder
        self.hear = hear
        self.servers: dict[int, Server] = {}
        self.prompts: list[Prompt] = []
        self.actions: list[tuple[str, list[str]]] = []
        self.refuse: dict[str, str] = {}  # an action that fails, with the bridge's words
        self.hold: dict[str, threading.Event] = {}  # an action that waits until the test lets it go on
        self.commands: dict[str, Answer] = {}  # what a command run in the container answers, by its words
        self.effects: dict[str, Callable[[], None]] = {}  # what a command does in the folder, by its words
        self.ran: list[str] = []  # each command run in the container, by its words
        self.commanded: list[list[str]] = []  # and its whole argv
        self.ended: list[str] = []  # each command the runner ended, by its pid file
        self.configuration: Callable[[], str | None] | None = None  # the container's OpenCode configuration, read
        self.failing: dict[str, str] = {}  # an MCP server that fails to connect, with why
        self.shown: list[tuple[int, str]] = []  # each session shown in a window: its port and its id
        self.show = True  # whether a window shows a session it is asked to (False: it would not, as a TUI may)
        self._running: dict[str, str] = {}  # each command running, by its pid file
        self.jobs: list[str] = []  # each job started, by its command's words
        self.jobs_ended: list[str] = []  # each job ended by Clank, by its folder in the workspace
        self.looked: list[str] = []  # each look at whether a job runs (jobs.ALIVE), by its folder in the container
        self.vanish: set[str] = set()  # a job, by its command's words, whose process ends without writing its exit
        self._jobs: dict[str, threading.Thread] = {}  # each job's work, by its folder in the container
        self._made = 0
        self._lock = threading.RLock()

    def inside(self, argv: list[str], given: bytes | None) -> Answer:
        """What the container answers a command: the bridge's line, or nothing for another program."""
        if argv[:3] == ["sh", "-c", accepting.RUN]:
            return self._command(argv)
        if argv[:3] == ["sh", "-c", accepting.END]:
            with self._lock:
                self.ended.append(argv[4])
                command = self._running.get(argv[4], "")
            if command in self.hold:
                self.hold[command].set()
            return Answer(0, "", "")
        if argv[:3] in (["sh", "-c", jobs.START], ["sh", "-c", jobs.END], ["sh", "-c", jobs.ALIVE]):
            return self._job(argv)
        if argv[0] in ("pkill", "pgrep") and "-f" in argv:
            return self._processes(argv)
        if len(argv) < 3 or not argv[1].endswith("bridge.py"):
            return Answer(1, "", "")
        action, rest = argv[2], argv[3:]
        body = json.loads(given) if given else {}
        with self._lock:
            self.actions.append((action, rest))
        if action in self.hold:  # asked, and held until the test lets it go on
            self.hold[action].wait(10)
        if action in ("implement", "show") and not self._waited(int(rest[0]), float(body.get("wait") or 0)):
            said = f"no OpenCode window answered on port {rest[0]} within {float(body.get('wait') or 0):g} seconds"
            return Answer(0, json.dumps({"ok": False, "error": said}) + "\n", "")
        with self._lock:
            try:
                if action in self.refuse:
                    raise RuntimeError(self.refuse[action])
                result = {"ok": True, **self._act(action, rest, body if isinstance(body, dict) else {})}
            except (RuntimeError, KeyError, ValueError) as error:
                result = {"ok": False, "error": str(error)}
        return Answer(0, json.dumps(result) + "\n", "")

    def _command(self, argv: list[str]) -> Answer:
        """A box's accept command, as `accepting.RUN` runs it: `sh -c RUN sh <pid file> <kill after> <seconds>
        <command>`."""
        pid, command = argv[4], argv[7]
        with self._lock:
            self.ran.append(command)
            self.commanded.append(list(argv))
            self._running[pid] = command
        if command in self.effects:
            self.effects[command]()
        if command in self.hold:  # running, until the test lets it go on or the runner ends it
            self.hold[command].wait(10)
        with self._lock:
            self._running.pop(pid, None)
            if pid in self.ended:
                return Answer(143, "", "Terminated\n")
            return self.commands.get(command, Answer(127, "", f"sh: 1: {command}: not found\n"))

    def _job(self, argv: list[str]) -> Answer:
        """A job started (`sh -c START sh <folder> <seconds> <command> <cwd>`), ended or looked at, its folder in the
        container (under `/workspace`) the test's folder."""
        inside = argv[4]
        folder = self.folder.joinpath(*inside.removeprefix("/workspace/").split("/"))
        if argv[2] == jobs.ALIVE:
            self.looked.append(inside)
            thread = self._jobs.get(inside)
            return Answer(0 if thread is not None and thread.is_alive() else 1, "", "")
        if argv[2] == jobs.END:
            with self._lock:
                self.jobs_ended.append(inside.removeprefix("/workspace/"))
            if not (folder / "exit").exists():
                (folder / "exit").write_text(f"{jobs.TERMINATED}\n", encoding="utf-8")
            command = (folder / "command").read_text(encoding="utf-8").strip() if (folder / "command").exists() else ""
            if command in self.hold:
                self.hold[command].set()
            return Answer(0, "", "")
        command = argv[6]
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("exit", "pid"):
            (folder / name).unlink(missing_ok=True)
        (folder / "command").write_text(command + "\n", encoding="utf-8")
        (folder / "pid").write_text(f"{2000 + len(self.jobs)}\n", encoding="utf-8")
        with self._lock:
            self.jobs.append(command)

        def work() -> None:
            if command in self.effects:
                self.effects[command]()
            if command in self.hold:
                self.hold[command].wait(10)
            if (folder / "exit").exists() or command in self.vanish:  # ended meanwhile, or gone without a word
                return
            answer = self.commands.get(command, Answer(127, "", f"sh: 1: {command}: not found\n"))
            (folder / "log").write_text(answer.output + answer.errors, encoding="utf-8")
            (folder / "exit").write_text(f"{answer.status}\n", encoding="utf-8")

        self._jobs[inside] = threading.Thread(target=work, daemon=True)
        self._jobs[inside].start()
        return Answer(0, "", "")

    def _processes(self, argv: list[str]) -> Answer:
        """`pgrep -f PATTERN` (the matching servers' made-up pids) and `pkill -SIGNAL -f PATTERN` (the matching servers
        end at once, their watcher saying each is gone), over each server's command line."""
        pattern = re.compile(argv[-1])
        with self._lock:
            self.commanded.append(list(argv))
            found = [port for port, server in self.servers.items() if pattern.search(server.command_line())]
            if argv[0] == "pkill":
                for port in found:
                    self.servers.pop(port)
        if argv[0] == "pkill" and self.hear is not None:
            for port in found:
                self.say({"type": "gone", "port": port})
        return Answer(0 if found else 1, "".join(f"{1000 + port}\n" for port in found), "")

    def _waited(self, port: int, wait: float) -> bool:
        """Whether a server answers on the port, waited for up to `wait` seconds (a window still starting)."""
        deadline = time.monotonic() + wait
        while True:
            with self._lock:
                if port in self.servers:
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    def window(self) -> int:
        """An OpenCode with a terminal (the owner's window) on the next port; its port."""
        with self._lock:
            port = self._free()
            self.servers[port] = Server(port, terminal=True)
            return port

    def say(self, line: dict[str, Any]) -> None:
        """A line of the workspace's watcher, heard by the service."""
        assert self.hear is not None, "the bridge has no service to tell"
        self.hear(self.workspace, line)

    def status(self, session: str, status: str) -> None:
        """A session's status changed (busy, idle), as the watch says it."""
        port = self.port_of(session)
        with self._lock:
            self.servers[port].sessions[session]["status"] = status
        self.say({"type": "status", "port": port, "session": session, "status": status})

    def finish(self, session: str, files: dict[str, str] | None = None, *, tokens: int = 0) -> None:
        """The scripted agent's work: it writes `files` in the folder, answers (a text part), finishes a step of
        `tokens` output tokens, and the session goes idle."""
        for path, text in (files or {}).items():
            target = self.folder.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        answer = {"id": f"prt_text_{session}", "message": "msg_1", "type": "text", "text": "Done."}
        self.say({"type": "part", "port": self.port_of(session), "session": session, "part": answer})
        if tokens:
            self.step(session, tokens)
        self.status(session, "idle")

    def finish_unheard(self, session: str, files: dict[str, str] | None = None) -> None:
        """The scripted agent's work ended while its watcher heard nothing of it, as when OpenCode's stream went silent
        (2026-10-22): the files written and the session idle on its server, and no line said."""
        for path, text in (files or {}).items():
            target = self.folder.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        port = self.port_of(session)
        with self._lock:
            self.servers[port].sessions[session]["status"] = "idle"

    def step(self, session: str, tokens: int, reasoning: int = 0) -> None:
        """A step of the session finished, with the tokens its model wrote."""
        with self._lock:
            self._made += 1
            part = f"prt_{self._made:03d}"
        self.say({
            "type": "part", "port": self.port_of(session), "session": session,
            "part": {"id": part, "message": "msg_1", "type": "step-finish",
                     "tokens": {"input": 9000, "output": tokens, "reasoning": reasoning}, "reason": "stop"},
        })  # fmt: skip

    def gone(self, port: int) -> None:
        """A server stopped (its container closed, or it ended)."""
        with self._lock:
            self.servers.pop(port, None)
        self.say({"type": "gone", "port": port})

    def port_of(self, session: str) -> int:
        """The server a session runs on."""
        with self._lock:
            return next(port for port, server in self.servers.items() if session in server.sessions)

    def prompted(self, title: str) -> Prompt | None:
        """The last message sent to a session whose title holds `title`, if any."""
        with self._lock:
            found = [each for each in self.prompts if title in each.title]
        return found[-1] if found else None

    def done(self, action: str) -> list[list[str]]:
        """The arguments of each time an action was asked."""
        with self._lock:
            return [rest for name, rest in self.actions if name == action]

    def _free(self) -> int:
        port = FIRST_PORT
        while port in self.servers:
            port += 1
        return port

    def _act(self, action: str, rest: list[str], body: dict[str, Any]) -> dict[str, Any]:
        if action == "servers":
            return {"servers": [self._listed(server) for server in self.servers.values()]}
        if action == "free-port":
            return {"port": self._free()}
        if action == "serve":
            port = self._free()
            config = self.configuration() if self.configuration is not None else None
            named = sorted((json.loads(config).get("mcp") or {}) if config else {})
            self.servers[port] = Server(port, env=dict(body.get("env") or {}), config=config,
                                        mcp=dict.fromkeys(named, "connected"))  # fmt: skip
            return {"port": port}
        if action == "mcp":
            statuses = [
                {"port": port, "mcp": {name: {"status": status, "error": self.failing.get(name, "")}
                                       for name, status in server.mcp.items()}}
                for port, server in self.servers.items()
            ]  # fmt: skip
            return {"servers": statuses}
        server = self.servers.get(int(rest[0])) if rest else None
        if server is None:
            raise RuntimeError(f"nothing answers on port {rest[0] if rest else '?'}")
        if action == "new":
            self._made += 1
            session = f"ses_{self._made:03d}"
            server.sessions[session] = {"title": str(body.get("title") or ""), "status": "idle"}
            return {"session": session}
        if action == "prompt":
            listed = server.sessions[rest[1]]
            agent, model = str(body.get("agent") or ""), dict(body.get("model") or {})
            self.prompts.append(Prompt(server.port, rest[1], listed["title"], str(body["text"]), agent, model))
            listed["status"] = "busy"
            return {"sent": True, "agent": agent, "model": model}
        if action == "implement":  # a session in a window, its first message sent to the agent asked, then shown
            self._made += 1
            session = f"ses_{self._made:03d}"
            title, agent = str(body.get("title") or ""), str(body.get("agent") or "build")
            server.sessions[session] = {"title": title, "status": "busy"}
            self.prompts.append(Prompt(server.port, session, title, str(body["text"]), agent, {}))
            if self.show:
                self.shown.append((server.port, session))
            return {"session": session, "shown": self.show}
        if action == "show":  # a session that runs already, shown in this window
            if self.show:
                self.shown.append((server.port, rest[1]))
            return {"session": rest[1], "shown": self.show}
        if action == "abort":
            server.sessions[rest[1]]["status"] = "idle"
            return {"stopped": True}
        if action == "permission":
            return {"replied": True}
        if action == "mcp-start":
            name = rest[1]
            if name not in server.mcp and not body.get("config"):
                raise ValueError(f"{name} is not one of this agent's MCP servers, and no entry came to add it")
            server.mcp[name] = "failed" if name in self.failing else "connected"
            return {"status": {"status": server.mcp[name], "error": self.failing.get(name, "")}}
        if action == "mcp-stop":
            server.mcp[rest[1]] = "disabled"
            return {"stopped": True}
        raise ValueError(f"no action {action!r}")

    @staticmethod
    def _listed(server: Server) -> dict[str, Any]:
        sessions = [
            {"id": id, "title": each["title"], "parent": None, "status": each["status"]}
            for id, each in server.sessions.items()
        ]
        return {"port": server.port, "terminal": server.terminal, "sessions": sessions, "children": [],
                "permissions": [], "questions": []}  # fmt: skip
