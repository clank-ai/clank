"""The workspace's agent, as the notion component reaches it (design 0010 §7), through the agents component: the
session that submits a batch is the one most recently active among the agents running in the workspace's container
(an MCP server does not know its session), kept with the batch; a batch sent back is one message to that session
while it still runs, else the first message of a new session in the workspace's OpenCode window (as a plan is handed
over, design 0009 §8). OpenCode keeps a message sent to a busy session until it is idle. Nothing is sent while no
OpenCode window runs: the owner is told to open it.
"""

from typing import TYPE_CHECKING, Any

from clank.components.notion.client import NotionRefused
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.kernel.core import Kernel


class AgentLink:
    """The agents of the workspaces, for the notion component."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel

    def session(self, workspace: str) -> dict[str, Any] | None:
        """The session most recently active in the workspace's container, None when none runs (or none can be read)."""
        from clank.components.agents.service import SessionError

        try:
            servers = self.kernel.parts["agents"].sessions.servers(workspace)
        except (KeyError, SessionError):
            return None
        found = [
            (int(each.get("updated") or each.get("created") or 0), int(server["port"]), str(each["id"]))
            for server in servers
            for each in server.get("sessions") or []
        ]
        if not found:
            return None
        _, port, session = max(found)
        return {"port": port, "session": session}

    def send(
        self, workspace: str, text: str, session: dict[str, Any] | None, *, title: str, actor: Actor
    ) -> dict[str, Any]:
        """Send a message to the session, or to a new session in the window when it no longer runs; where it went."""
        from clank.components.agents.service import ModeError, SessionError

        agents = self.kernel.parts["agents"]
        try:
            running = {
                (int(server["port"]), str(each["id"]))
                for server in agents.sessions.servers(workspace)
                for each in server.get("sessions") or []
            }
            if session is not None and (int(session["port"]), str(session["session"])) in running:
                agents.sessions.send(workspace, int(session["port"]), str(session["session"]), text, actor=actor)
                return {"port": int(session["port"]), "session": str(session["session"]), "new": False}
            port = agents.modes.window_port(workspace)
            started = agents.sessions.implement(workspace, port, text, title=title, actor=actor)
        except (ModeError, SessionError) as error:
            raise NotionRefused(f"the agent of {workspace} could not be told: {error}") from error
        return {"port": port, "session": started, "new": True}
