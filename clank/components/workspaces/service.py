"""The workspaces component's part in the service. In M0 it holds Docker: the container platform's status, whose each
container is, and starting and stopping it.

A container is Clank's only when it carries this CLANK_HOME's id in its `clank.home` label; anything else is another
program's (design 0002 §2.9, §3.2). Starting and stopping are operations (design 0002 §2.4) that hold the lock `docker`:
a start asks the platform, waits until its engine answers (within `start_timeout_seconds`, and it can be canceled while
it waits), then lets the adapter put right what the start disturbed; a stop asks the user first whenever a container
that is not Clank's runs, naming each, because stopping Docker stops them all. Both are safe to run again, and after a
restart an interrupted one is reconciled by reading Docker's state. A background check reads the status every
`poll_seconds` and records `docker.changed` when what runs changes (not when only a container's uptime does), so clients
follow Docker without asking it themselves; the first reading after the service starts is what clients load, not a
change. The platform is made by `make_platform` from the adapter the settings name, again when that setting changes;
tests replace `make_platform`. From M4 the workspaces themselves are its too: opening, stopping and removing one are
operations of `folders.py`, and the edge they share forwards the gateway's port (from the gateway's service).
"""

import logging
import os
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

import anyio
import anyio.to_thread

from clank.components.workspaces import jobs as jobs  # the job runner, for the flows and the agents (design 0021 §6)
from clank.components.workspaces.adapters import CONTAINER_PLATFORMS
from clank.components.workspaces.adapters.platform import Container, ContainerPlatform, PlatformError, PlatformStatus
from clank.components.workspaces.cloud import EVENT_TYPES as CLOUD_EVENT_TYPES
from clank.components.workspaces.cloud import CloudBounds
from clank.components.workspaces.kinds import DockerSettings, Workspace
from clank.components.workspaces.network import HostAsks
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
from clank.kernel.operations import Canceled, Operation, OperationContext, OperationType, Reconciliation, StepSpec
from clank.kernel.processes import Answer, run_command
from clank.kernel.questions import EXPIRY, Option, QuestionDraft

log = logging.getLogger(__name__)
Owner = Literal["clank", "other"]
WAIT_SECONDS = 1.0
WORKSPACES = Actor(kind="clank", via="workspaces")
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
    """The container platform an adapter name gives, with its command found on this machine."""
    adapter = CONTAINER_PLATFORMS.get(name)
    return adapter(run_command, adapter.find())


def owner(container: Container, home_id: str) -> Owner:
    """Whose a container is: Clank's (this CLANK_HOME's), or another program's."""
    if container.clank.get("clank.home") == home_id:
        return "clank"
    return "other"


def image_name(name: str) -> str:
    """An image as people read it: an untagged one by the start of its id, as Docker shows ids."""
    return name[: len("sha256:") + 12] if name.startswith("sha256:") else name


def summary(status: PlatformStatus, owners: list[Owner]) -> str:
    """One line on the platform: "Docker Desktop · running · 3 containers running, none of them Clank's"."""
    text = f"{status.label} · {status.state}"
    if not status.running:
        return text
    running = [mine for container, mine in zip(status.containers, owners, strict=True) if container.state == "running"]
    if not running:
        return f"{text} · no container running"
    clanks = running.count("clank")
    if len(running) == 1:
        return f"{text} · 1 container running, {'Clank' if clanks else 'not Clank'}'s"
    whose = "none" if clanks == 0 else "all" if clanks == len(running) else str(clanks)
    return f"{text} · {len(running)} containers running, {whose} of them Clank's"


class Workspaces:
    """The workspaces component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self._adapter = ""
        self._platform: ContainerPlatform | None = None
        self._last: dict[str, Any] | None = None
        self._fingerprint: tuple[Any, ...] | None = None
        self._lock = threading.Lock()
        self.cloud = CloudBounds(kernel)  # where each workspace's requests may go (design 0016 §9)
        self.network = HostAsks(kernel, self.allow_host)  # the hosts its agent asks for (design 0024 §3)

    def settings(self) -> DockerSettings:
        """How Clank uses Docker, as the settings say now."""
        return DockerSettings.model_validate(self.kernel.settings.get("docker", "docker").record.model_dump())

    @property
    def platform(self) -> ContainerPlatform:
        """The container platform the settings name."""
        name = self.settings().adapter
        if self._platform is None or name != self._adapter:
            self._platform, self._adapter = make_platform(name), name
        return self._platform

    def docker(self, refresh: bool = False) -> dict[str, Any]:
        """Docker as last read, or read now (when asked, or never read yet): its state, versions, a one-line summary,
        and each container with its owner."""
        if refresh or self._last is None:
            return self._observe(self.platform.status())
        return self._last

    async def check(self) -> dict[str, Any]:
        """Read Docker's state once, recording `docker.changed` if what runs changed since the last reading."""
        platform = self.platform
        return self._observe(await anyio.to_thread.run_sync(platform.status))

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
        """Each workspace: its name, folder and limits, its container, and the container's state as Docker says now."""
        status = self.docker(refresh=True)
        running = status["state"] == "running"
        containers = {container["name"]: container for container in status["containers"]}
        found = names(self.kernel.home.id)
        rows = []
        for loaded in self.kernel.settings.records("workspace"):
            workspace = Workspace.model_validate(loaded.record.model_dump())
            container = containers.get(found.container(loaded.id))
            state = container["state"] if container else ("not made" if running else f"Docker is {status['state']}")
            rows.append(
                {
                    "name": loaded.id,
                    "path": workspace.path,
                    "cpus": workspace.cpus,
                    "memory_mib": workspace.memory_mib,
                    "container": found.container(loaded.id),
                    "state": state,
                    "setup": _setup_view(workspace.path, workspace),
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

    def allow_host(self, name: str, host: str, allow: bool, *, actor: Actor) -> dict[str, Any]:
        """Allow a workspace's agent a host through Clank's proxy (design 0024 §1: an exact name, or a suffix starting
        with a dot), or take it back; its record keeps when and how; the gateway's next routes carry it; its view
        after."""
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
            hosts[wanted] = f"allowed {to_text(self.kernel.clock.now())} by {actor.describe()}"
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
        a container), and its workspace's bound (`models`, `cloud_answered`, `cloud_question`; None without one).
        Docker's state is its last reading (the background check keeps it current); the container and the image are
        asked of Docker."""
        from clank.components.workspaces.folders import WorkspaceError, checked_folder

        problem = ""
        try:
            path = checked_folder(folder, self.kernel.home.root)
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
        return {
            "folder": path,
            "problem": problem,
            "workspace": name,
            "container": container,
            "state": state,
            "image": {"tag": tag, "built": built, "current": found.image == tag if found is not None else None},
            "setup": None if problem else _setup_view(path, workspace[1] if workspace else None),
            "hosts": dict(workspace[1].hosts) if workspace else None,
            **(self.cloud.view(name) if name else dict.fromkeys(BOUND)),
        }

    def runs_current_image(self, workspace: str) -> bool | None:
        """Whether the workspace's container runs Clank's sandbox image as this Clank builds it: False for one made
        from an older image (its bridge and Clank's MCP server are baked into it), which moves to the new one when the
        workspace is stopped and opened again; None when it has no container."""
        found = self.platform.container(names(self.kernel.home.id).container(workspace))
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
        """The name of a workspace's container, once it runs; `WorkspaceUnavailable` saying why not."""
        if workspace not in {loaded.id for loaded in self.kernel.settings.records("workspace")}:
            raise WorkspaceUnavailable(f"there is no workspace {workspace!r}: `clank workspace open` makes one")
        name = names(self.kernel.home.id).container(workspace)
        found = self.platform.container(name)
        if found is None or found.state != "running":
            raise WorkspaceUnavailable(f"{workspace}'s container does not run: `clank workspace open` starts it")
        return name

    def put_file(self, workspace: str, path: str, text: str) -> None:
        """Write a file in a workspace's running container, as its user."""
        try:
            self.platform.put_file(self.container_of(workspace), path, text)
        except PlatformError as error:
            raise WorkspaceUnavailable(str(error)) from error

    def exec_argv(self, workspace: str, argv: list[str], env: dict[str, str], *, terminal: bool = True) -> list[str]:
        """The command that runs `argv` in a workspace's container, in its folder, with `env`: in a terminal, else
        talked to over its input and output (an MCP server)."""
        return self.platform.exec_argv(
            self.container_of(workspace), argv, workdir=WORKSPACE, env=env, terminal=terminal
        )

    def run_in(self, workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30.0) -> Answer:
        """Run `argv` in a workspace's running container, in its folder, as its user; its whole answer (design 0005
        §2: the session bridge). `WorkspaceUnavailable` when its container does not run."""
        return self.platform.run_in(self.container_of(workspace), argv, workdir=WORKSPACE, input=input, timeout=timeout)

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

        loaded = self.kernel.settings.get("workspace", workspace)
        cpus, _ = chosen_limits(Workspace.model_validate(loaded.record.model_dump()), self.platform.limits())
        return dict(thread_env(cpus))

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

    def proxy_url(self, name: str) -> str:
        """The proxy as a workspace's container is told it: its URL through the edge, with the workspace's own token
        (design 0024 §2), so the proxy knows whose request each is."""
        from clank.components.gateway.proxy import network_token
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
            self._last, self._fingerprint = view, fingerprint
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
        owners = [owner(container, self.kernel.home.id) for container in status.containers]
        return {
            **status.model_dump(mode="json", exclude={"containers"}),
            "checked": to_text(self.kernel.clock.now()),
            "summary": summary(status, owners),
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
    if status.state == "not installed":
        raise DockerError(f"{status.label} is not installed: {status.detail}")
    if status.state == "unsupported":
        raise DockerError(status.detail)
