"""The workspace's mode as the owner sees it, and handing a plan to the agent (design 0009 §7-§8).

The mode shown is **plan** when OpenCode's window works with the planner, else the change rule (**review** or **auto**,
`review.py`). OpenCode's terminal interface keeps its agent to itself (measured on 1.19, design 0009 §7): Clank knows
it from the agent of the last message sent in the window (the watcher's `agent` lines, from the server that runs a
terminal interface) and from its own switches; Tab pressed with nothing sent since is not seen, and the next message
corrects it. Switching does what Tab does, as many times as the window's agents need (`agent_cycle`): to the planner
for plan, to `build` for review and auto, which also set the change rule. A switch with no window running sets the rule
and says so.

Implementing a plan (§8): the plan must be a plan (`plans.py`: a Markdown file of the folder whose header says
`kind: plan`) and a window must run; the change rule is set, and the bridge starts a session in that window whose first
message, sent by `build`, is `/implement`'s instructions with the plan's path, then shows it, so the window takes
`build`. `plans` lists the folder's plans with their steps done, for the console's folder page.
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.agents.adapters.opencode import prompt
from clank.components.agents.plans import SETTINGS, is_plan, plan_path
from clank.kernel.events import CLANK, Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.review import Review
    from clank.components.agents.sessions import Sessions
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

PLANNER, BUILD = "planner", "build"
SHOWN = ("plan", "review", "auto")
LARGEST_PLAN = 1_000_000  # bytes of a Markdown file read to see whether it is a plan
SKIPPED = {*SETTINGS, "node_modules", "runs", "__pycache__", ".venv", "venv"}  # folders not searched for plans
EVENT_TYPES = [
    EventType(
        "agents.mode_switched",
        "You chose a workspace's mode: plan (the planner writes plans), review or auto (build changes files after "
        "your review, or without asking).",
        {"workspace": "The workspace.", "shown": "plan, review or auto.", "agent": "The window's agent now.",
         "mode": "The change rule: review or auto."},
    ),
    EventType(
        "agents.agent_seen",
        "A message was sent in a workspace's OpenCode window with another agent than before (Tab, or a switch).",
        {"workspace": "The workspace.", "agent": "The agent.", "session": "The session."},
    ),
    EventType(
        "agents.plan_handed",
        "A plan was handed to the agent: a new session in OpenCode's window carries it out.",
        {"workspace": "The workspace.", "plan": "The plan, in its folder.", "mode": "review or auto.",
         "session": "The session."},
    ),
]  # fmt: skip


class ModeError(Exception):
    """A mode that cannot be set, or a plan that cannot be handed over, and why."""


@dataclass
class Window:
    """OpenCode's window in a workspace, as last seen: the server that runs it, its session, its agent."""

    port: int
    session: str = ""
    agent: str = ""


class Modes:
    """Each workspace's window, the mode shown, and plans handed over."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions", review: "Review") -> None:
        self.kernel = kernel
        self.sessions = sessions
        self.review = review
        self._windows: dict[str, Window] = {}
        self._lock = threading.Lock()

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A watcher's `agent` line: a message sent with this agent, on a server with or without a window."""
        if not line.get("terminal"):
            return  # a session without a window (the phone's): the window's agent is not its
        agent, session = str(line.get("agent") or ""), str(line.get("session") or "")
        with self._lock:
            window = self._windows.get(workspace)
            changed = window is None or window.agent != agent
            self._windows[workspace] = Window(int(line["port"]), session, agent)
        if changed:
            self.kernel.events.record(
                "agents.agent_seen",
                summary=f"{workspace}'s window works with {agent}",
                actor=CLANK,
                subject=Subject(kind="workspace", id=workspace),
                data={"workspace": workspace, "agent": agent, "session": session},
            )

    def shown(self, workspace: str) -> dict[str, Any]:
        """The window's agent as last seen (None when no message was seen yet), and the mode shown."""
        with self._lock:
            window = self._windows.get(workspace)
        agent = window.agent if window is not None and window.agent else None
        return {"agent": agent, "shown": "plan" if agent == PLANNER else self.review.mode(workspace)}

    def switch(self, workspace: str, shown: str, *, actor: Actor) -> dict[str, Any]:
        """Plan, review or auto: the window's agent switched (the change rule set for review and auto); the view, with
        a note when the window could not be switched."""
        if shown not in SHOWN:
            raise ModeError(f"a workspace's mode is plan, review or auto, not {shown}")
        if shown != "plan":
            self.review.switch(workspace, shown, actor=actor)
        wanted = PLANNER if shown == "plan" else BUILD
        note = self._to(workspace, wanted, actor)
        self.kernel.events.record(
            "agents.mode_switched",
            summary=f"{actor.describe()} set {workspace} to {shown}",
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "shown": shown, "agent": wanted, "mode": self.review.mode(workspace)},
        )
        return {**self.review.view(workspace), "note": note}

    def implement(self, workspace: str, plan: str, mode: str, *, actor: Actor) -> dict[str, Any]:
        """Hand a plan to the agent in review or auto mode: a new session in OpenCode's window carries it out."""
        if mode not in ("review", "auto"):
            raise ModeError(f"a plan is implemented in review or auto mode, not {mode}")
        relative = plan.replace("\\", "/").strip("/")
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        path = Path(workspaces.folder_of(workspace), *relative.split("/"))
        if not plan_path(relative) or not path.is_file() or not is_plan(_read(path)):
            raise ModeError(
                f"{plan} is not a plan of {workspace}: a Markdown file of its folder whose header says kind: plan"
            )
        port = self._window_port(workspace)
        self.review.switch(workspace, mode, actor=actor)
        text = prompt("implement.md").replace("$ARGUMENTS", relative)
        session = self.sessions.implement(workspace, port, text, title=f"Implement {relative}", actor=actor)
        with self._lock:
            self._windows[workspace] = Window(port, session, BUILD)
        self.kernel.events.record(
            "agents.plan_handed",
            summary=f"{actor.describe()} handed {relative} to {workspace}'s agent ({mode})",
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "plan": relative, "mode": mode, "session": session},
        )
        return {"workspace": workspace, "plan": relative, "mode": mode, "port": port, "session": session}

    def plans(self, workspace: str) -> list[dict[str, Any]]:
        """The folder's plans, newest first: each one's path, title, status, and steps done of all."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        folder = Path(workspaces.folder_of(workspace))
        found = []
        for root, folders, files in os.walk(folder):
            folders[:] = sorted(name for name in folders if name not in SKIPPED and not name.startswith("."))
            for name in files:
                path = Path(root, name)
                relative = path.relative_to(folder).as_posix()
                if not plan_path(relative):
                    continue
                text = _read(path)
                if is_plan(text):
                    found.append({"path": relative, **_described(text), "modified": path.stat().st_mtime})
        return sorted(found, key=lambda each: -each["modified"])

    def _to(self, workspace: str, wanted: str, actor: Actor) -> str:
        """Switch the window's agent to `wanted`; what to tell the owner when it could not be done ("" when it was)."""
        try:
            port = self._window_port(workspace)
            order = self.sessions.agents(workspace, port)
        except ModeError as error:
            return str(error)
        if wanted not in order:
            return f"this OpenCode window has no {wanted}: start it again (F4 c or a) so it reads Clank's configuration"
        with self._lock:
            window = self._windows.get(workspace)
            current = window.agent if window is not None and window.port == port and window.agent else BUILD
        if current not in order:
            current = order[0]
        steps = (order.index(wanted) - order.index(current)) % len(order)
        if steps:
            self.sessions.cycle(workspace, port, steps, actor=actor)
        with self._lock:
            session = window.session if window is not None and window.port == port else ""
            self._windows[workspace] = Window(port, session, wanted)
        return ""

    def window_port(self, workspace: str) -> int:
        """The port of OpenCode's window in the workspace (for a message to start a session there, as the Notion review
        sends a batch back)."""
        return self._window_port(workspace)

    def _window_port(self, workspace: str) -> int:
        """The port of OpenCode's window in the workspace: the one a message was last seen in, else the first
        server that runs a terminal interface."""
        from clank.components.agents.sessions import SessionError

        try:
            running = [server for server in self.sessions.servers(workspace) if server.get("terminal")]
        except SessionError as error:
            raise ModeError(str(error)) from error
        if not running:
            raise ModeError(
                f"no OpenCode runs in a window in {workspace}: open it first (F4 c or a, or Clank: Open the agent "
                "in VS Code); the change rule is set"
            )
        ports = [int(server["port"]) for server in running]
        with self._lock:
            window = self._windows.get(workspace)
        return window.port if window is not None and window.port in ports else ports[0]


def _read(path: Path) -> str | None:
    """A file's text when it is small enough to be a plan; None otherwise or when it cannot be read."""
    try:
        if path.stat().st_size > LARGEST_PLAN:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _described(text: str | None) -> dict[str, Any]:
    """A plan's title and status from its header, and its checklist's steps done of all."""
    lines = (text or "").splitlines()
    header: dict[str, str] = {}
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        key, _, value = line.partition(":")
        header[key.strip()] = value.strip()
    done = sum(1 for line in lines if line.lstrip().lower().startswith("- [x]"))
    steps = done + sum(1 for line in lines if line.lstrip().startswith("- [ ]"))
    return {"title": header.get("title", ""), "status": header.get("status", ""), "done": done, "steps": steps}
