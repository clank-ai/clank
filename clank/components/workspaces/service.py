"""The workspaces component's part in the service. In M0 it holds Docker: the container platform's status, whose each
container is, and starting and stopping it.

A container is Clank's only when it carries this CLANK_HOME's id in its `clank.home` label; anything else is another
program's (design 0002 §2.9, §3.2). Starting and stopping are operations (design 0002 §2.4) that hold the lock `docker`:
a start asks the platform, waits until its engine answers (within `start_timeout_seconds`, and it can be canceled while
it waits), then lets the adapter put right what the start disturbed; a stop asks the user first whenever a container
that is not Clank's runs, naming each, because stopping Docker stops them all. Both are safe to run again, and after a
restart an interrupted one is reconciled by reading Docker's state. A platform Clank does not start (the system's Docker
Engine, design 0014 §2) is refused both at once, in the status's words, a stop before any question; so is one this
account has no access to (the docker group). A background check reads the status every `poll_seconds` and records
`docker.changed` when what runs changes (not when only a container's uptime does), so clients follow Docker without
asking it themselves; the first reading after the service starts is what clients load, not a change. The platform is
made by `make_platform` from the setting `adapter` (`auto` by default: the adapter of this computer's Docker, chosen by
`adapters/choose.py` without waking any engine), again when that setting changes, and keeps why it was chosen; Docker's
view says which, why, and whether Clank starts it; tests replace `make_platform`. From M4 the workspaces themselves are
its too: opening, stopping and removing one are operations of `folders.py`, and the edge they share forwards the
gateway's port and the proxy's (from the gateway's service). The edge is kept on every workspace's network (`edge.py`,
design 0004 §3 revised 2026-10-26): the background check joins it back to the network of a running workspace it is not
on, starts it or makes it, from the reading it takes anyway (the first one when the service starts); `reach` puts it
right before an agent starts in a workspace; and each view of a workspace says, as `edge` and `edge_said`, whether its
container reaches the edge, and what Clank does when it does not. The platform adapter's name decides the edge's way to
the gateway (design 0014 §3): `docker-engine` gets the gateway's socket (`edge_socket`, from the gateway's service),
every other adapter the host's loopback; and on Linux no workspace's folder may hold the gateway's socket folder or be
inside it (`socket_folder`).
"""

import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

import anyio
import anyio.to_thread

from clank.components.workspaces import jobs as jobs  # the job runner, for the flows and the agents (design 0021 §6)
from clank.components.workspaces.adapters import CONTAINER_PLATFORMS
from clank.components.workspaces.adapters.choose import choose_platform
from clank.components.workspaces.adapters.platform import Container, ContainerPlatform, PlatformError
from clank.components.workspaces.adapters.platform import PlatformStatus as PlatformStatus  # for the doctor
from clank.components.workspaces.cloud import EVENT_TYPES as CLOUD_EVENT_TYPES
from clank.components.workspaces.cloud import CloudBounds
from clank.components.workspaces.edge import EVENT_TYPES as EDGE_EVENT_TYPES
from clank.components.workspaces.edge import Edge
from clank.components.workspaces.kinds import DockerSettings, Workspace
from clank.components.workspaces.memory import MEMORY_FIX as MEMORY_FIX  # for the doctor (design 0014 §5)
from clank.components.workspaces.memory import memory_said as memory_said
from clank.components.workspaces.network import SETS_FILE, HostAsks, sets
from clank.components.workspaces.sandbox import BRIDGE_PROGRAM as BRIDGE_PROGRAM  # for the agents (design 0005)
from clank.components.workspaces.sandbox import CURRENT_INSTRUCTIONS as CURRENT_INSTRUCTIONS  # for the agents
from clank.components.workspaces.sandbox import CURRENT_PHONE as CURRENT_PHONE  # (design 0018 §7.5)
from clank.components.workspaces.sandbox import EDGE_ALIAS, LAYERS, image_tag, layered_tag, names, thread_env
from clank.components.workspaces.sandbox import PHONE_PROGRAM as PHONE_PROGRAM
from clank.components.workspaces.sandbox import WORKSPACE as WORKSPACE  # for the agents (design 0007)
from clank.components.workspaces.sandbox import agent_files as agent_files
from clank.components.workspaces.setup import proposed_setup
from clank.kernel.clock import to_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.home import Home
from clank.kernel.operations import Canceled, Operation, OperationContext, OperationType, Reconciliation, StepSpec
from clank.kernel.processes import Answer, run_command
from clank.kernel.questions import EXPIRY, Option, QuestionDraft
from clank.kernel.settings import read_record

log = logging.getLogger(__name__)
Owner = Literal["clank", "other"]
WAIT_SECONDS = 1.0
LIMITS_SECONDS = 300.0  # Docker's CPUs and memory, as an agent's start reads them, are read again after this long
WORKSPACES = Actor(kind="clank", via="workspaces")
DOCKER_ENGINE = "docker-engine"  # the adapter whose edge reaches the gateway through its socket (design 0014 §3)
BOUND = ("models", "cloud_answered", "cloud_question", "cloud_said", "cloud_confirm")  # a workspace's bound, in views

EVENT_TYPES = [
    EventType(
        "docker.changed",
        "What runs in Docker changed: it started or stopped, or a container started, stopped, appeared or went away.",
        {
            "state": "The platform's state, such as running.",
            "summary": "One line on it, such as Docker Desktop · running · 2 containers running, none of them Clank's.",
            "containers": "Each container: its name, its state and whose it is (clank or other).",
        },
    ),
    *CLOUD_EVENT_TYPES,
    *EDGE_EVENT_TYPES,
    EventType(
        "workspaces.host_allowed",
        "A host was allowed to a workspace's agent through Clank's proxy, or taken back (design 0024 §1).",
        {
            "workspace": "The workspace.",
            "host": "The host: a name, or a suffix starting with a dot.",
            "allowed": "True when allowed, false when taken back.",
            "who": "Who did it.",
        },
    ),
]


class WorkspaceUnavailable(Exception):
    """A workspace whose container cannot be used now, and why."""


class DockerError(Exception):
    """Docker cannot do what an operation asked; the message says what to do."""


def make_platform(name: str) -> ContainerPlatform:
    """The container platform the setting names (`auto`: the one this computer's Docker is, `choose_platform`, design
    0014 §2), with its command found on this machine; it keeps why it was chosen (`chosen`)."""
    chosen, why = choose_platform(name)
    adapter = CONTAINER_PLATFORMS.get(chosen)
    platform = adapter(run_command, adapter.find())
    platform.chosen = why
    return platform


def starts(platform: ContainerPlatform) -> bool:
    """Whether Clank starts and stops this platform: an application its user runs does, the system's service does not
    (design 0014 §2)."""
    return any(capability.name == "start" and capability.supported for capability in platform.capabilities())


def status_said(status: PlatformStatus) -> str:
    """The platform's state in a sentence, with what to do when it says: "Docker Engine is stopped: start it with
    `sudo systemctl start docker`; ..."."""
    states = {"no access": "gives this account no access", "failed": "has failed"}
    said = f"{status.label} {states.get(status.state, f'is {status.state}')}"
    return f"{said}: {status.detail}" if status.detail else said


@dataclass(frozen=True)
class DockerReading:
    """Docker as the doctor reads it, without the service (design 0014 §2, §4, §5): the platform's status, whether
    Clank starts it, and while it runs, whether it can limit a container's memory, in its words; and whether the owner
    allows a workspace without that (`allow_unlimited_memory`)."""

    status: PlatformStatus
    starts: bool
    memory: tuple[bool | None, list[str]] = (None, [])
    allow_unlimited_memory: bool = False


def docker_settings(home: Home) -> DockerSettings:
    """`config/docker.json` as the service would read it; its defaults when it is not there or does not read."""
    path = home.config / "docker.json"
    found = read_record(DockerSettings, path) if path.is_file() else []
    return DockerSettings.model_validate(found[0].model_dump()) if isinstance(found, tuple) else DockerSettings()


def read_platform(home: Home) -> DockerReading:
    """Docker as the platform the settings choose reports it now, read without the service (`clank doctor`, and the
    doctor's operation, which does not need this component's part)."""
    settings = docker_settings(home)
    platform = make_platform(settings.adapter)
    status = platform.status()
    return DockerReading(
        status=status,
        starts=starts(platform),
        memory=platform.memory_limits() if status.running else (None, []),
        allow_unlimited_memory=settings.allow_unlimited_memory,
    )


def owner(container: Container, home_id: str) -> Owner:
    """Whose a container is: Clank's (this CLANK_HOME's), or another program's."""
    if container.clank.get("clank.home") == home_id:
        return "clank"
    return "other"


def image_name(name: str) -> str:
    """An image as people read it: an untagged one by the start of its id, as Docker shows ids."""
    return name[: len("sha256:") + 12] if name.startswith("sha256:") else name


def summary(status: PlatformStatus, owners: list[Owner], unlimited: bool = False) -> str:
    """One line on the platform: "Docker Desktop · running · 3 containers running, none of them Clank's", and
    " · memory not limited" while Docker's last reading says it cannot limit a container's memory (design 0014 §4)."""
    text = f"{status.label} · {status.state}"
    if not status.running:
        return text
    return f"{text} · {_running(status, owners)}" + (" · memory not limited" if unlimited else "")


def _running(status: PlatformStatus, owners: list[Owner]) -> str:
    running = [mine for container, mine in zip(status.containers, owners, strict=True) if container.state == "running"]
    if not running:
        return "no container running"
    clanks = running.count("clank")
    if len(running) == 1:
        return f"1 container running, {'Clank' if clanks else 'not Clank'}'s"
    whose = "none" if clanks == 0 else "all" if clanks == len(running) else str(clanks)
    return f"{len(running)} containers running, {whose} of them Clank's"


class Workspaces:
    """The workspaces component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self._adapter = ""  # the setting the platform was made from (auto, or an adapter's name)
        self._platform: ContainerPlatform | None = None
        self._last: dict[str, Any] | None = None
        self._status: PlatformStatus | None = None  # the last reading, as the platform gave it
        self._fingerprint: tuple[Any, ...] | None = None
        self._lock = threading.Lock()
        self._limits: tuple[str, float, tuple[int, int] | None] | None = None  # adapter, when read, what it said
        self._memory: bool | None = None  # whether Docker limits a container's memory, as last read (an opening's)
        self.cloud = CloudBounds(kernel)  # where each workspace's requests may go (design 0016 §9)
        self.network = HostAsks(kernel, self.allow_host)  # the hosts its agent asks for (design 0024 §3)
        self.edge = Edge(self)  # the edge on every workspace's network (design 0004 §3)

    def settings(self) -> DockerSettings:
        """How Clank uses Docker, as the settings say now."""
        return DockerSettings.model_validate(self.kernel.settings.get("docker", "docker").record.model_dump())

    @property
    def platform(self) -> ContainerPlatform:
        """The container platform the settings name, chosen when it is first asked for and again when the setting
        changes (`auto`: this computer's, design 0014 §2)."""
        name = self.settings().adapter
        if self._platform is None or name != self._adapter:
            self._platform, self._adapter = make_platform(name), name
        return self._platform

    def platform_adapter(self) -> str:
        """The adapter in use, by name (docker-desktop, docker-engine): the edge's way to the gateway depends on it
        (design 0014 §3)."""
        return self.platform.NAME

    def platform_starts(self, status: PlatformStatus | None = None) -> bool:
        """Whether Clank starts and stops the platform in use, read from it each time (Docker Desktop's own command
        may answer later than its first asking; Docker Desktop keeps its answer once it has one); never where its
        `status` says it is not installed or unsupported, which no start mends, so nothing more is asked of it."""
        if status is not None and status.state in ("not installed", "unsupported"):
            return False
        return starts(self.platform)

    def note_memory(self, limited: bool | None) -> None:
        """Keep the last reading of whether Docker can limit a container's memory (an opening reads it, design 0014
        §4), which Docker's view says."""
        self._memory = limited

    def not_running(self, status: PlatformStatus) -> str:
        """Why Docker cannot be used now and what to do, for one that does not run: the status's own words, or, for a
        platform Clank starts that says nothing more, how to start it through Clank."""
        if self.platform_starts(status) and not status.detail:
            return f"Docker is {status.state}: start it with `clank docker start`, or from the console's Docker page"
        return status_said(status)

    def docker(self, refresh: bool = False) -> dict[str, Any]:
        """Docker as last read, or read now (when asked, or never read yet): its state, versions, a one-line summary,
        and each container with its owner."""
        if refresh or self._last is None:
            return self._observe(self.platform.status())
        return self._last

    async def check(self) -> dict[str, Any]:
        """Read Docker's state once, recording `docker.changed` if what runs changed since the last reading; then, from
        that reading, put the edge back on the network of each running workspace it is not on (`Edge.check`: Docker is
        asked nothing more while none is cut off)."""
        platform = self.platform
        status = await anyio.to_thread.run_sync(platform.status)
        view = self._observe(status)
        if status.running:
            try:
                await anyio.to_thread.run_sync(self.edge.check, status.containers)
            except Exception:
                log.exception("putting the edge right failed")
        return view

    async def run(self) -> None:
        """Give the gateway each workspace's bound (design 0016 §9), then check Docker every `poll_seconds` while the
        service runs."""
        try:
            await anyio.to_thread.run_sync(self.cloud.give)
        except Exception:
            log.exception("giving the gateway the workspaces' bounds failed")
        while True:
            try:
                await self.check()
            except Exception:
                log.exception("reading Docker's state failed")
            await anyio.sleep(self.settings().poll_seconds)

    def workspaces(self) -> list[dict[str, Any]]:
        """Each workspace: its name, folder and limits, its container, the container's state as Docker says now, and
        whether it reaches the edge (`edge`, `edge_said`: `Edge.view`)."""
        reading = self.platform.status()
        status = self._observe(reading)
        running = status["state"] == "running"
        containers = {container.name: container for container in reading.containers}
        found = names(self.kernel.home.id)
        rows = []
        for loaded in self.kernel.settings.records("workspace"):
            workspace = Workspace.model_validate(loaded.record.model_dump())
            container = containers.get(found.container(loaded.id))
            state = container.state if container else ("not made" if running else f"Docker is {status['state']}")
            rows.append(
                {
                    "name": loaded.id,
                    "path": workspace.path,
                    "cpus": workspace.cpus,
                    "memory_mib": workspace.memory_mib,
                    "container": found.container(loaded.id),
                    "state": state,
                    "setup": _setup_view(workspace.path, workspace),
                    **self.edge.view(loaded.id, containers),
                    **self.cloud.view(loaded.id),
                }
            )
        return rows

    def ask_cloud(self, name: str, cloud: str = "") -> dict[str, Any]:
        """Whether a workspace must be asked before its agent uses the main slot's cloud model, and the question when it
        must (design 0016 §9, decision 0112): any client calls this before it starts the workspace's agent; a flow's
        box names the cloud preset it is about to load (`cloud`, its title)."""
        self._named(name)
        return self.cloud.ask(name, cloud)

    def cloud_view(self, name: str) -> dict[str, Any]:
        """A workspace's bound: `models`, `cloud_answered`, `cloud_question`."""
        self._named(name)
        return self.cloud.view(name)

    def allow_cloud(self, name: str, allow: bool, *, actor: Actor) -> dict[str, Any]:
        """Allow a workspace the cloud model, or keep it on this machine; its view after."""
        self._named(name)
        self.cloud.allow(name, allow, actor=actor)
        return next(row for row in self.records() if row["name"] == name)

    def allow_host(self, name: str, host: str, allow: bool, *, actor: Actor, set_name: str = "") -> dict[str, Any]:
        """Allow a workspace's agent a host through Clank's proxy (design 0024 §1: an exact name, or a suffix starting
        with a dot), or take it back; its record keeps when and how (and the set it came with, `set_name`); the
        gateway's next routes carry it; its view after."""
        from clank.kernel.api import ApiError

        self._named(name)
        wanted = host.strip().lower().rstrip(".")
        if not wanted or any(c in wanted for c in "/: @\\") or wanted in (".",):
            raise ApiError(
                400, "refused", f"{host!r} is not a host name: a name such as pypi.org, or a suffix such as .arxiv.org"
            )
        loaded = self.kernel.settings.get("workspace", name)
        values = loaded.record.model_dump()
        hosts = dict(values.get("hosts") or {})
        if allow:
            marked = f" (set {set_name})" if set_name else ""
            hosts[wanted] = f"allowed {to_text(self.kernel.clock.now())} by {actor.describe()}{marked}"
        else:
            hosts.pop(wanted, None)
        self.kernel.settings.write("workspace", name, {**values, "hosts": hosts}, base=loaded.revision, actor=actor)
        said = f"{name}'s agent may reach {wanted}" if allow else f"{name}'s agent may not reach {wanted} any more"
        self.kernel.events.record(
            "workspaces.host_allowed",
            summary=f"{said} ({actor.describe()})",
            actor=actor,
            subject=Subject(kind="workspace", id=name),
            data={"workspace": name, "host": wanted, "allowed": allow, "who": actor.describe()},
        )
        return next(row for row in self.records() if row["name"] == name)

    def network_sets(self) -> dict[str, dict[str, Any]]:
        """The named sets of hosts (design 0024 §5), as the owner's file has them."""
        return sets(self.kernel.home)

    def allow_set(self, name: str, set_name: str, allow: bool, *, actor: Actor) -> dict[str, Any]:
        """Allow a workspace's agent a named set of hosts (design 0024 §5), each written into its record marked with
        the set; or take the set back: the hosts still marked with it go, one the owner also allowed by name stays.
        Its view after."""
        from clank.components.workspaces.folders import WorkspaceError

        self._named(name)
        known = sets(self.kernel.home)
        if set_name not in known:
            raise WorkspaceError(
                f"there is no set {set_name!r}: the sets are {', '.join(known)} (config/{SETS_FILE} holds them)"
            )
        if allow:
            for host in known[set_name]["hosts"]:
                self.allow_host(name, host, True, actor=actor, set_name=set_name)
        else:
            current = self.kernel.settings.get("workspace", name).record.model_dump().get("hosts") or {}
            for host, how in current.items():
                if f"(set {set_name})" in how:
                    self.allow_host(name, host, False, actor=actor)
        return next(row for row in self.records() if row["name"] == name)

    def host_wanted(self, name: str, host: str) -> dict[str, Any]:
        """A workspace's agent reaches a host (design 0024 §3): allowed, quiet, or the question asked (`network`)."""
        self._named(name)
        return self.network.wanted(name, host)

    def _named(self, name: str) -> None:
        if not any(loaded.id == name for loaded in self.kernel.settings.records("workspace")):
            from clank.kernel.api import ApiError

            raise ApiError(404, "not_found", f"there is no workspace {name}")

    def records(self) -> list[dict[str, Any]]:
        """Each workspace's name and folder, and its bound (design 0016 §9), from its record alone (Docker is not
        asked)."""
        return [
            {
                "name": loaded.id,
                "path": Workspace.model_validate(loaded.record.model_dump()).path,
                "hosts": dict(loaded.record.model_dump().get("hosts") or {}),
                **self.cloud.view(loaded.id),
            }
            for loaded in self.kernel.settings.records("workspace")
        ]

    def running(self) -> dict[str, str]:
        """The workspaces whose container runs, each with its container's id, from Docker's last reading (Docker is not
        asked: the background check keeps the reading current)."""
        reading = self.docker()
        if reading["state"] != "running":
            return {}
        containers = {each["name"]: each["id"] for each in reading["containers"] if each["state"] == "running"}
        found = names(self.kernel.home.id)
        return {
            loaded.id: containers[found.container(loaded.id)]
            for loaded in self.kernel.settings.records("workspace")
            if found.container(loaded.id) in containers
        }

    def folder_view(self, folder: str) -> dict[str, Any]:
        """What working in a folder needs of the workspaces, read now: whether it may be a workspace (else why not),
        its workspace and its container's state, whether the sandbox image is built, and whether the container runs
        it (`current`: false for one made from an older image, which moves to it when it is next opened; None without
        a container), whether its running container reaches the edge (`edge`, `edge_said`: `Edge.view`), and its
        workspace's bound (`models`, `cloud_answered`, `cloud_question`; None without one). Docker's state is its last
        reading (the background check keeps it current); the container, the edge (while the container runs) and the
        image are asked of Docker."""
        from clank.components.workspaces.folders import WorkspaceError, checked_folder

        problem = ""
        try:
            path = checked_folder(folder, self.kernel.home.root, self.socket_folder())
        except WorkspaceError as error:
            path, problem = folder, str(error)
        workspace = next(
            (
                found
                for found in (
                    (loaded.id, Workspace.model_validate(loaded.record.model_dump()))
                    for loaded in self.kernel.settings.records("workspace")
                )
                if os.path.normcase(found[1].path) == os.path.normcase(path)
            ),
            None,
        )
        name = workspace[0] if workspace else None
        docker = self.docker()
        running = docker["state"] == "running"
        container = names(self.kernel.home.id).container(name) if name else None
        found = self.platform.container(container) if running and container else None
        known = found.state if found is not None else "not made"
        state = known if running else f"Docker is {docker['state']}"
        tag = layered_tag(workspace[1].layers) if workspace else image_tag()
        built = self.platform.image_exists(tag) if running else None
        reach: dict[str, Any] = {"edge": None, "edge_said": ""}
        if name and found is not None and found.state == "running":
            edge = self.platform.container(names(self.kernel.home.id).edge)
            reach = self.edge.view(name, {each.name: each for each in (found, edge) if each is not None})
        return {
            "folder": path,
            "problem": problem,
            "workspace": name,
            "container": container,
            "state": state,
            "image": {"tag": tag, "built": built, "current": found.image == tag if found is not None else None},
            "setup": None if problem else _setup_view(path, workspace[1] if workspace else None),
            "hosts": dict(workspace[1].hosts) if workspace else None,
            **reach,
            **(self.cloud.view(name) if name else dict.fromkeys(BOUND)),
        }

    def runs_current_image(self, workspace: str) -> bool | None:
        """Whether the workspace's container runs Clank's sandbox image as this Clank builds it: False for one made
        from an older image (its bridge and Clank's MCP server are baked into it), which moves to the new one when the
        workspace is stopped and opened again; None when it has no container, or Docker refuses to be asked (a stopped
        Docker Engine, design 0014 §2)."""
        try:
            found = self.platform.container(names(self.kernel.home.id).container(workspace))
        except PlatformError:
            return None
        layers = Workspace.model_validate(self.kernel.settings.get("workspace", workspace).record.model_dump()).layers
        return found.image == layered_tag(layers) if found is not None else None

    def set_layer(self, name: str, layer: str, added: bool, *, actor: Actor) -> dict[str, Any]:
        """Add an image layer to a workspace's record, or take it away (design 0020 §3); its layers, and what then."""
        from clank.components.workspaces.folders import WorkspaceError

        if layer not in LAYERS:
            raise WorkspaceError(f"there is no image layer {layer!r}: the layers are {', '.join(LAYERS)}")
        known = {loaded.id: loaded for loaded in self.kernel.settings.records("workspace")}
        if name not in known:
            raise WorkspaceError(f"there is no workspace {name!r}")
        loaded = known[name]
        record = loaded.record.model_dump()
        layers = [each for each in LAYERS if (each in record.get("layers", []) or each == layer) and
                  not (each == layer and not added)]  # fmt: skip
        if layers != record.get("layers", []):
            self.kernel.settings.write(
                "workspace", name, {**record, "layers": layers}, base=loaded.revision, actor=actor
            )
        verb = "added to" if added else "taken from"
        said = (
            f"{layer} is {verb} {name}: open the workspace again to build its image (asked first); its container moves "
            "to it once it is stopped and opened again"
        )
        return {"workspace": name, "layers": layers, "said": said}

    def container_of(self, workspace: str) -> str:
        """The name of a workspace's container, once it runs; `WorkspaceUnavailable` saying why not (a refusal of
        Docker's in its words: a stopped Docker Engine names the command that starts it, design 0014 §2)."""
        if workspace not in {loaded.id for loaded in self.kernel.settings.records("workspace")}:
            raise WorkspaceUnavailable(f"there is no workspace {workspace!r}: `clank workspace open` makes one")
        name = names(self.kernel.home.id).container(workspace)
        try:
            found = self.platform.container(name)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error
        if found is None or found.state != "running":
            raise WorkspaceUnavailable(f"{workspace}'s container does not run: `clank workspace open` starts it")
        return name

    def reach(self, workspace: str) -> list[str]:
        """Before an agent starts in a workspace (design 0004 §3): the edge put right for it, as an opening does (made,
        started or made again when it must be, on its network, and on every workspace's once it was made or started);
        what was put right, each in words, for the agent's notes (empty when nothing was). `WorkspaceUnavailable` when
        Docker refused, saying why."""
        if self._status is None:
            self.docker()
        containers = self._status.containers if self._status is not None else []
        try:
            repair = self.edge.ready(workspace, containers, remake=True, found_by=f"starting the agent in {workspace}")
        except PlatformError as error:
            said = f"{workspace}'s way to the model, the edge, could not be put right: {error}"
            raise WorkspaceUnavailable(said) from error
        return [*repair.did, *([repair.problem] if repair.problem else [])]

    def put_file(self, workspace: str, path: str, text: str) -> None:
        """Write a file in a workspace's running container, as its user."""
        try:
            self.platform.put_file(self.container_of(workspace), path, text)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error

    def put_files(self, workspace: str, files: Sequence[tuple[str, str]], *, container: str = "") -> None:
        """Write several files in a workspace's running container, as its user, in one go (an agent's start, design
        0004 §5); `container`, when the caller has just found it running, is not asked of Docker again."""
        try:
            self.platform.put_files(container or self.container_of(workspace), files)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error

    def exec_argv(
        self, workspace: str, argv: list[str], env: dict[str, str], *, terminal: bool = True, container: str = ""
    ) -> list[str]:
        """The command that runs `argv` in a workspace's container, in its folder, with `env`: in a terminal, else
        talked to over its input and output (an MCP server); `container`, when the caller has just found it running,
        is not asked of Docker again."""
        found = container or self.container_of(workspace)
        try:
            return self.platform.exec_argv(found, argv, workdir=WORKSPACE, env=env, terminal=terminal)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error

    def run_in(self, workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30.0) -> Answer:
        """Run `argv` in a workspace's running container, in its folder, as its user; its whole answer (design 0005
        §2: the session bridge). `WorkspaceUnavailable` when its container does not run, or Docker refuses."""
        found = self.container_of(workspace)
        try:
            return self.platform.run_in(found, argv, workdir=WORKSPACE, input=input, timeout=timeout)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error

    def folder_of(self, workspace: str) -> str:
        """A workspace's folder on this machine."""
        if workspace not in {loaded.id for loaded in self.kernel.settings.records("workspace")}:
            raise WorkspaceUnavailable(f"there is no workspace {workspace!r}: `clank workspace open` makes one")
        return Workspace.model_validate(self.kernel.settings.get("workspace", workspace).record.model_dump()).path

    def agent_env(self, workspace: str) -> dict[str, str]:
        """What a workspace's agent runs with besides its program's own: numerical libraries start as many threads as
        its container has CPUs (Docker's limit does not change how many a program sees; design 0004 §10). The container
        says the same to every program in it, but one made before it did still needs it said here."""
        from clank.components.workspaces.folders import chosen_limits

        loaded = Workspace.model_validate(self.kernel.settings.get("workspace", workspace).record.model_dump())
        cpus, _ = chosen_limits(loaded, self.platform_limits() if loaded.cpus is None else None)
        return dict(thread_env(cpus))

    def platform_limits(self) -> tuple[int, int] | None:
        """The CPUs and memory Docker's engine has, read at most once in `LIMITS_SECONDS` (they change only when Docker
        restarts with other settings, and `docker info` took 0.7 s of every agent's start, 2026-10-26)."""
        platform = self.platform  # the settings' adapter, made again when they name another
        adapter, now, kept = self._adapter, time.monotonic(), self._limits
        if kept is not None and kept[0] == adapter and now - kept[1] < LIMITS_SECONDS:
            return kept[2]
        found = platform.limits()
        self._limits = (adapter, now, found)
        return found

    def container_stats(self) -> list[dict[str, Any]]:
        """Each running container's use of the CPU and memory, as `docker stats` gives it (the machine's meters): none
        unless Docker's last reading is running, so an engine the owner stopped is never woken (design 0014 §2)."""
        if self._status is None or not self._status.running:
            return []
        try:
            return self.platform.stats()
        except PlatformError:
            return []

    def gateway_port(self) -> int:
        """The port the gateway listens on, which the edge forwards."""
        from clank.components.gateway.service import Gateway

        gateway: Gateway = self.kernel.parts["gateway"]
        return gateway.settings().port

    def proxy_port(self) -> int:
        """The port the agent's proxy listens on (design 0024 §2), which the edge forwards too."""
        from clank.components.gateway.service import Gateway

        gateway: Gateway = self.kernel.parts["gateway"]
        return gateway.settings().proxy_port

    def edge_socket(self) -> Path | None:
        """Where the edge forwards on Docker Engine (design 0014 §3): the gateway's socket, its folder made ready, once
        no workspace's folder holds that folder or is inside it; None on any other platform, whose edge reaches the
        host's loopback. `SocketFolderError` (the gateway's), saying why, when the folder may not be used."""
        if self.platform.NAME != DOCKER_ENGINE:
            return None
        from clank.components.gateway.service import Gateway, SocketFolderError

        gateway: Gateway = self.kernel.parts["gateway"]
        path = gateway.edge_socket()
        if path is None:
            raise SocketFolderError("on Docker Engine the edge needs the gateway's socket, made on Linux only")
        folder = path.parent
        for loaded in self.kernel.settings.records("workspace"):
            name, place = loaded.id, Path(Workspace.model_validate(loaded.record.model_dump()).path)
            if folder == place or folder.is_relative_to(place):
                where = f"the gateway's socket folder {folder} is inside the folder of the workspace {name} ({place})"
            elif place.is_relative_to(folder):
                where = f"the folder of the workspace {name} ({place}) is inside the gateway's socket folder ({folder})"
            else:
                continue
            raise SocketFolderError(
                f"{where}: its container would see the gateway's socket, so no workspace opens on Docker Engine until "
                "it moves: set socket_folder in config/gateway.json to a folder outside every workspace's, then clank "
                f"gateway restart (or remove the workspace {name})"
            )
        return path

    def socket_folder(self) -> Path | None:
        """The gateway's socket folder on Linux, which no workspace's folder may hold or be inside (design 0014 §3);
        None on any other system, and while the gateway may not use the folder its settings name (nothing listens there
        then)."""
        from clank.components.gateway.service import Gateway, SocketFolderError

        gateway: Gateway = self.kernel.parts["gateway"]
        try:
            path = gateway.socket_path()
        except SocketFolderError:
            return None
        return path.parent if path is not None else None

    def gateway_runs(self) -> bool:
        """Whether the gateway's process runs, as its status says."""
        from clank.components.gateway.service import Gateway

        gateway: Gateway = self.kernel.parts["gateway"]
        return bool(gateway.status()["state"] == "running")

    def proxy_url(self, name: str) -> str:
        """The proxy as a workspace's container is told it: its URL through the edge, with the workspace's own token
        (design 0024 §2), so the proxy knows whose request each is."""
        from clank.components.gateway.service import network_token
        from clank.kernel.access import local_token

        return f"http://{name}:{network_token(local_token(self.kernel.home), name)}@{EDGE_ALIAS}:{self.proxy_port()}"

    def operation_types(self) -> list[OperationType]:
        """Starting and stopping Docker, under one lock; opening, stopping and removing a workspace."""
        from clank.components.workspaces import folders

        return [*self._docker_operations(), *folders.operation_types(self)]

    def _docker_operations(self) -> list[OperationType]:
        return [
            OperationType(
                "docker.start",
                "Start Docker",
                (StepSpec("start"), StepSpec("wait")),
                self._start,
                reconcile=self._reconcile,
                locks=_docker_lock,
                owner="workspaces",
            ),
            OperationType(
                "docker.stop",
                "Stop Docker",
                (StepSpec("check"), StepSpec("stop"), StepSpec("wait")),
                self._stop,
                reconcile=self._reconcile,
                locks=_docker_lock,
                owner="workspaces",
            ),
        ]

    def router(self) -> Any:
        """Docker's routes."""
        from clank.components.workspaces.api import router

        return router(self)

    async def _start(self, context: OperationContext) -> dict[str, Any]:
        settings = self.settings()
        platform = self.platform
        async with context.step("start"):
            status = await self._read(context, platform)
            if status.running:
                context.log(f"{status.label} is already running")
                return {"already": True, "docker": self._last}
            _require_usable(status)
            if not self.platform_starts():
                raise DockerError(status_said(status))  # the system's: what its owner runs, in the status's words
            await context.run_blocking(platform.request_start)
            context.log(f"asked {status.label} to start")
        async with context.step("wait"):
            status = await self._wait(
                context, platform, lambda found: found.running, settings.start_timeout_seconds, "start"
            )
            context.log(f"{status.label} is running (engine {status.engine})")
            await context.run_blocking(platform.after_start, context.log)
        return {"already": False, "docker": self._last}

    async def _stop(self, context: OperationContext) -> dict[str, Any]:
        settings = self.settings()
        platform = self.platform
        async with context.step("check"):
            status = await self._read(context, platform)
            _require_usable(status)
            if status.state == "stopped":
                context.log(f"{status.label} is not running")
                return {"already": True, "docker": self._last}
            if not self.platform_starts():  # refused in the platform's words, before any question, having run nothing
                await context.run_blocking(platform.request_stop)
                raise DockerError(f"Clank does not stop {status.label}")
            home = self.kernel.home.id
            others = [c for c in status.containers if c.state == "running" and owner(c, home) != "clank"]
            if others:
                draft = self._stop_question(status, others, settings)
                answer = await context.ask(draft)
                if answer.option != "stop":
                    chosen = next((o.label for o in draft.options if o.id == answer.option), answer.text)
                    if answer.by == EXPIRY:
                        raise Canceled(f"canceled: nobody answered within {settings.question_minutes} minutes")
                    raise Canceled(f"canceled: {answer.by.describe()} answered {chosen}")
        async with context.step("stop"):
            await context.run_blocking(platform.request_stop)
            context.log(f"asked {status.label} to stop")
        async with context.step("wait"):
            await self._wait(
                context, platform, lambda found: found.state == "stopped", settings.stop_timeout_seconds, "stop"
            )
            context.log(f"{status.label} stopped")
        return {"already": False, "docker": self._last}

    def _stop_question(
        self, status: PlatformStatus, others: list[Container], settings: DockerSettings
    ) -> QuestionDraft:
        names = ", ".join(container.name for container in others)
        one = len(others) == 1
        running = (
            "1 container that Clank did not start is"
            if one
            else f"{len(others)} containers that Clank did not start are"
        )
        return QuestionDraft(
            type="approval",
            title=f"Stop {status.label}?",
            detail=f"{running} running: {names}. Stopping {status.label} stops {'it' if one else 'them'} too.",
            options=[
                Option(
                    id="stop",
                    label=f"Stop {'it' if one else 'them'} and Docker",
                    key="y",
                    effect=f"stops {status.label} and every container in it",
                ),
                Option(id="cancel", label="Cancel", key="n", effect=f"leaves {status.label} running"),
            ],
            default="cancel",
            expires=self.kernel.clock.now() + timedelta(minutes=settings.question_minutes),
        )

    async def _read(self, context: OperationContext, platform: ContainerPlatform) -> PlatformStatus:
        status = await context.run_blocking(platform.status)
        self._observe(status)
        return status

    async def _wait(
        self,
        context: OperationContext,
        platform: ContainerPlatform,
        done: Callable[[PlatformStatus], bool],
        seconds: int,
        verb: str,
    ) -> PlatformStatus:
        deadline = self.kernel.clock.now() + timedelta(seconds=seconds)
        while True:
            context.check_canceled()
            status = await self._read(context, platform)
            if done(status):
                return status
            if self.kernel.clock.now() >= deadline:
                raise DockerError(
                    f"{status.label} did not {verb} within {seconds} seconds (it is {status.state}); "
                    f"open {status.label} to see why"
                )
            await anyio.sleep(WAIT_SECONDS)

    async def _reconcile(self, operation: Operation) -> Reconciliation:
        platform = self.platform
        status = self._status_of(self._observe(await anyio.to_thread.run_sync(platform.status)))
        return Reconciliation(f"after the restart, {status}")

    def _observe(self, status: PlatformStatus) -> dict[str, Any]:
        view = self._view(status)
        fingerprint = (
            view["state"],
            view["version"],
            view["engine"],
            tuple(sorted((c["id"], c["state"], c["owner"]) for c in view["containers"])),
        )
        with self._lock:
            first = self._fingerprint is None
            changed = fingerprint != self._fingerprint
            self._last, self._status, self._fingerprint = view, status, fingerprint
        if changed and not first:
            self.kernel.events.record(
                "docker.changed",
                summary=view["summary"],
                actor=WORKSPACES,
                data={
                    "state": view["state"],
                    "summary": view["summary"],
                    "containers": [
                        {"name": c["name"], "state": c["state"], "owner": c["owner"]} for c in view["containers"]
                    ],
                },
            )
        return view

    def _view(self, status: PlatformStatus) -> dict[str, Any]:
        """Docker as clients show it: the platform's status, when it was read, a one-line summary, the state in a
        sentence with what to do (`said`), why this adapter is the one in use (`chosen`), whether Clank starts it
        (`starts`: the system's Docker Engine it never does, design 0014 §2), and each container with its owner."""
        owners = [owner(container, self.kernel.home.id) for container in status.containers]
        return {
            **status.model_dump(mode="json", exclude={"containers"}),
            "checked": to_text(self.kernel.clock.now()),
            "summary": summary(status, owners, unlimited=self._memory is False),
            "said": status_said(status),
            "memory_limits": self._memory,
            "chosen": self.platform.chosen,
            "starts": self.platform_starts(status),
            "containers": [
                {**container.model_dump(mode="json", exclude={"label_keys"}), "owner": mine}
                for container, mine in zip(status.containers, owners, strict=True)
            ],
        }

    @staticmethod
    def _status_of(view: dict[str, Any]) -> str:
        return f"{view['label']} is {view['state']}"


def _setup_view(folder: str, workspace: Workspace | None) -> dict[str, Any]:
    """The folder's software: the command that installs it (its record's, else proposed from its files; None: nothing
    to install), and whether it is installed, with what (design 0004 §10)."""
    own = workspace.setup if workspace else None
    command = own or proposed_setup(folder)
    installed_with = workspace.set_up if workspace else ""
    return {
        "command": command,
        "proposed": own is None,
        "installed": command is not None and installed_with == command,
        "installed_with": installed_with,
    }


def _docker_lock(params: Any) -> list[str]:
    return ["docker"]


def _require_usable(status: PlatformStatus) -> None:
    """Refuse, in the status's words, a platform that is not installed, not supported, or not this account's to use
    (the docker group, design 0014 §2)."""
    if status.state == "not installed":
        raise DockerError(f"{status.label} is not installed: {status.detail}")
    if status.state in ("unsupported", "no access"):
        raise DockerError(status.detail)
