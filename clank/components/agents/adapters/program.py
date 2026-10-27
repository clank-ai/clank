"""The agent program kind of adapter: the interface every program that works in a workspace meets (decision 0011,
design 0004 §4).

An agent program runs in a workspace's container, from Clank's sandbox image, as the container's user, in the
workspace's folder. Its adapter says the command that starts it in a terminal (`argv`), the environment it runs with
(`env`), and its configuration for a model (`configuration`): the file's path in the container's home (never in the
user's folder) and its text, for a model reached at a URL (the gateway, through the edge), named as the gateway routes
it (a role, decision 0008), with that model's limits, so the program knows when to compact a conversation, and the MCP
servers it gets (design 0004 §10), each a command it starts in the container. The program
runs in the container, not on this machine, so there is nothing of it to record here (`RECORDED = False`); the image
pins its version. It says when it compacts a conversation for a model's limits, and what a compaction keeps
(`compaction`), so the Monitor shows how much is left before it does (design 0012 §4.1).

The program is told a window smaller than the engine's by a margin (`AgentModel.margin`, the owner's `context_margin`,
at most a quarter of the window: `kept_margin`), kept free for one step's tool results: a program compacts once a
step's total nears the window it is told, and that step's results, sent with its next request, must still fit the
engine's (decision 0089).
"""

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from clank.components.tools.service import Server
from clank.kernel.adapters import Adapter


@dataclass(frozen=True)
class AgentModel:
    """The model an agent program talks to: where, its name there, what people call it, its limits in tokens (its
    engine's window and longest answer), whether it reads images, and the margin of the window kept free for one step's
    tool results, which the program is not told of (decision 0089)."""

    url: str
    name: str
    title: str
    context: int
    output: int
    images: bool = True
    margin: int = 0
    key: str = "local"  # the workspace's own key at the gateway (design 0016 §9), its name there


def kept_margin(margin: int, window: int) -> int:
    """The margin kept free in a window: the owner's, at most a quarter of the window, so a small window still leaves a
    step room to work (decision 0089)."""
    return max(0, min(margin, window // 4))


@dataclass(frozen=True)
class Compaction:
    """When an agent program compacts a conversation, for a model's limits (design 0012 §4.1): once a step's total
    reaches `line` tokens; what a compaction keeps, a summary and the newest turns up to `keeps` tokens; and the rule
    in words, with where it was read."""

    line: int
    keeps: int
    rule: str


class AgentProgram(Adapter):
    """A program that works in a workspace: how it starts, and how it is told its model."""

    HOME: ClassVar[str] = "/home/agent"
    RECORDED = False

    @abstractmethod
    def argv(self, port: int | None = None) -> list[str]:
        """The command that starts it in a terminal, in the workspace's folder; with `port`, serving its API there on
        the container's loopback, so its session can be reached (design 0005 §2)."""

    @abstractmethod
    def env(self) -> dict[str, str]:
        """The environment it runs with."""

    @abstractmethod
    def server_entry(self, server: Server) -> dict[str, object]:
        """An MCP server as its configuration names one (started by a command in the container)."""

    @abstractmethod
    def configuration(
        self,
        model: AgentModel,
        servers: Mapping[str, Server] | None = None,
        read_only: Mapping[str, Sequence[str]] | None = None,
    ) -> tuple[str, str]:
        """Its configuration for a model and the MCP servers it gets (each started by a command in the container), with
        the tools of each server its last check marks read-only (all a planner may use, design 0009 §3): the file's
        path in the container (under `HOME`) and its text."""

    def compaction(self, window: int, output: int, margin: int = 0) -> Compaction | None:
        """When it compacts a conversation for a model's window and output limit, told the window less `margin`, and
        what it keeps; None for a program that does not, or says nothing of when."""
        return None

    def files(self) -> list[tuple[str, str]]:
        """Other files it needs in the agent's home beside its configuration, each its path (under `HOME`) and its
        text, written with it; none by default."""
        return []
