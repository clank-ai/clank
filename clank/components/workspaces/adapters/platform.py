"""The container platform kind of adapter: the interface every container platform meets (design 0002 §2.9, §2.10).

A container platform (Docker Desktop first; Docker Engine on Linux later) is asked for its status (its state, its
versions and its containers) and to start or stop. Each call is blocking and quick: asking to start returns once the
platform has the request, and the operation that asked waits for the engine by reading the status again, so it can be
canceled and shows its progress. An adapter is built from the function that runs commands and where its command is
(`find()` says where on this machine; None when the platform is not installed), the platform it runs on, and the
function that starts an application (a platform whose own command cannot start it starts its program), so a contract
test can play back what the real program answered. Clank tells its own containers by their labels: every container
Clank starts carries `clank.home` (the CLANK_HOME's id), `clank.component` and `clank.record`, and a container without
this home's `clank.home` is not Clank's to touch.

From M4 a platform also runs the workspaces' containers (design 0004 §3): it says its CPUs and memory, builds an image
(each line of the build as it comes, cancelable), makes a network, runs a container from its spec (`sandbox.py`), or
once in the foreground, followed line by line (a workspace's setup),
reads, starts, stops and removes one, removes a volume, and says how a terminal enters a container. These ask for the
command's whole answer (`answer`), so a refusal is raised in the platform's own words; reading or removing what is not
there is no error. Each container it lists or reads says the networks it is on (a stopped one's too), so the edge's
place on every workspace's network is checked from the reading the service takes anyway (design 0004 §3, revised
2026-10-26); joining a network says whether it joined now or was on it already, and a container that cannot start
because a network it was on is gone (removed, or made again since) is a `NetworkGone`, so Clank makes it again.
These container commands are Docker's own CLI whatever program runs the engine: one base, `DockerCli`
(`docker_cli.py`, design 0014 §2), holds them for every adapter.
"""

import sys
from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field

from clank.components.workspaces.sandbox import ContainerSpec
from clank.kernel.adapters import Adapter
from clank.kernel.processes import Answer, Launch, TimedAnswer, TimedRun, launch_program, run_answer, stream_command

LABELS = ("clank.home", "clank.component", "clank.record", "clank.ports", "clank.proxy")  # the edge's ports, a
# container's proxy port (design 0024 §2): read back, so one made for others is made again


class Follow(Protocol):
    """A long command followed line by line to its exit status, as `stream_command` does."""

    def __call__(
        self, arguments: Sequence[str], line: Callable[[str], None], canceled: Callable[[], bool]
    ) -> int | None:
        """Its exit status, or None when it could not start or was canceled."""


def follow_command(arguments: Sequence[str], line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
    """`stream_command`, as a `Follow`."""
    return stream_command(arguments, line, canceled=canceled)


class PlatformError(Exception):
    """The platform cannot do what it was asked; the message says what to do."""


class NetworkGone(PlatformError):
    """A container that cannot start because a network it was on is gone: removed, or made again since (Docker keeps
    the network's id, not its name); one made again from its spec starts."""


class Container(BaseModel):
    """One container, as the platform lists it."""

    id: str = Field(title="Id", description="The container's id.")
    name: str = Field(title="Name", description="Its name.")
    image: str = Field(title="Image", description="The image it runs.")
    state: str = Field(title="State", description="running, exited, created, paused, restarting or dead.")
    status: str = Field("", title="Status", description="The platform's own words, such as Up 2 hours.")
    clank: dict[str, str] = Field(
        default_factory=dict, title="Clank's labels", description="The clank.* labels it carries, exactly."
    )
    label_keys: list[str] = Field(
        default_factory=list, title="Labels", description="The name of every label it carries."
    )
    networks: list[str] = Field(
        default_factory=list,
        title="Networks",
        description="The networks it is on, by name: a stopped one's too, which it rejoins when it starts.",
    )


class PlatformStatus(BaseModel):
    """What the platform is doing, and what runs in it."""

    adapter: str = Field(title="Adapter", description="The adapter that reads it, such as docker-desktop.")
    label: str = Field(title="Platform", description="The platform, such as Docker Desktop.")
    state: str = Field(
        title="State",
        description="running, starting, stopping, stopped, not installed, unsupported, or the platform's own word.",
    )
    version: str = Field("", title="Version", description="The platform's version, while it runs.")
    engine: str = Field("", title="Engine", description="Its engine's version, while it runs.")
    containers: list[Container] = Field(
        default_factory=list, title="Containers", description="Every container, running or not, while it runs."
    )
    detail: str = Field("", title="Detail", description="Why it is in this state, and what to do about it.")

    @property
    def running(self) -> bool:
        """Whether its engine runs and answers."""
        return self.state == "running"


class ContainerPlatform(Adapter):
    """A container platform: its status, and starting and stopping it."""

    def __init__(
        self,
        run: TimedRun,
        command: str | None,
        *,
        platform: str = sys.platform,
        launch: Launch = launch_program,
        answer: TimedAnswer = run_answer,
        follow: Follow = follow_command,
    ) -> None:
        self.run = run
        self.command = command
        self.platform = platform
        self.launch = launch
        self.answer = answer
        self.follow = follow
        self.chosen = ""  # why this adapter is the one in use, said by whoever chose it (design 0014 §2)

    @classmethod
    @abstractmethod
    def find(cls) -> str | None:
        """Where the platform's command is on this machine, or None when it is not installed."""

    @abstractmethod
    def status(self) -> PlatformStatus:
        """What the platform is doing now, and its containers while it runs."""

    @abstractmethod
    def request_start(self) -> None:
        """Ask the platform to start; returns once it has the request."""

    @abstractmethod
    def request_stop(self) -> None:
        """Ask the platform to stop, with every container in it; returns once it has the request."""

    @abstractmethod
    def limits(self) -> tuple[int, int] | None:
        """The CPUs and the memory (MiB) the platform gives its containers, or None when it does not say."""

    @abstractmethod
    def stats(self) -> list[dict[str, Any]]:
        """Each running container's use of the CPU and memory, in the platform's own fields (`docker stats`: Name,
        CPUPerc, MemUsage); none when it does not say."""

    @abstractmethod
    def memory_limits(self) -> tuple[bool | None, list[str]]:
        """Whether the platform can limit a container's memory (None: it does not say), and its warnings about it, in
        its words (design 0014 §4: a Raspberry Pi's default kernel cannot)."""

    @abstractmethod
    def image_exists(self, tag: str) -> bool:
        """Whether an image of this tag is built."""

    @abstractmethod
    def build_image(
        self,
        tag: str,
        folder: str,
        labels: Mapping[str, str],
        line: Callable[[str], None],
        canceled: Callable[[], bool],
        args: Mapping[str, str] | None = None,
    ) -> int | None:
        """Build an image from a folder, with build arguments (`args`), giving `line` each line as it comes; its exit
        status, or None when it could not start or was canceled."""

    @abstractmethod
    def ensure_network(self, name: str, *, internal: bool, labels: Mapping[str, str]) -> None:
        """Make a network unless it is there (internal: no route out)."""

    @abstractmethod
    def join_network(self, network: str, container: str, alias: str) -> bool:
        """Join a container to a network, where others call it `alias`: True when it joined now, False when it was on
        it already (no error)."""

    @abstractmethod
    def leave_network(self, network: str, container: str) -> None:
        """Take a container off a network; not on it, or either not there, is no error."""

    @abstractmethod
    def remove_network(self, name: str) -> None:
        """Remove a network; one not there is no error."""

    @abstractmethod
    def container(self, name: str) -> Container | None:
        """The container of this name, or None."""

    @abstractmethod
    def run_container(self, spec: ContainerSpec) -> None:
        """Run a container from its spec, joining its other networks after it starts."""

    @abstractmethod
    def run_once(self, spec: ContainerSpec, line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
        """Run a container from its spec in the foreground, giving `line` each line it writes, removed when it ends;
        its exit status, or None when it could not start or was canceled."""

    @abstractmethod
    def start_container(self, name: str) -> None:
        """Start a stopped container; `NetworkGone` when a network it was on is gone."""

    @abstractmethod
    def stop_container(self, name: str, seconds: int) -> None:
        """Stop a container, ending it after `seconds`; one not there is no error."""

    @abstractmethod
    def remove_container(self, name: str) -> None:
        """Remove a container, running or not; one not there is no error."""

    @abstractmethod
    def remove_volume(self, name: str) -> None:
        """Remove a volume; one not there is no error."""

    @abstractmethod
    def put_file(self, name: str, path: str, text: str) -> None:
        """Write a file in a running container, as the container's user, making its folder when it is not there."""

    def put_files(self, name: str, files: Sequence[tuple[str, str]]) -> None:
        """Write several files in a running container as `put_file` does each (a platform may do it in one go)."""
        for path, text in files:
            self.put_file(name, path, text)

    @abstractmethod
    def run_in(
        self, name: str, argv: Sequence[str], *, workdir: str, input: bytes | None = None, timeout: float = 30.0
    ) -> Answer:
        """Run `argv` in a running container, as its user, in `workdir`, giving it `input`; its whole answer (the
        session bridge, design 0005 §2)."""

    @abstractmethod
    def exec_argv(
        self,
        name: str,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None = None,
        terminal: bool = True,
    ) -> list[str]:
        """The command that runs `argv` in a container, in `workdir`, as its user, with `env`: for a terminal, else
        talked to over its input and output (`terminal=False`: an MCP server)."""

    def after_start(self, log: Callable[[str], None]) -> None:
        """Put right what starting the platform disturbed on this machine, saying what it does; most need nothing."""

    def agent_access(self, folder: str) -> str:
        """Why the agent (user 1000 in its container) could not read and write this folder as the platform mounts it,
        saying how to let it; empty when it can. Docker Desktop's file sharing maps the folder's owner, so it says
        nothing; Docker Engine shows the host's own owners (design 0014 §4)."""
        return ""
