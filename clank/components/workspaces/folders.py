"""Workspaces: folders agents work in, each in a container of its own (design 0004 §1, §3 and §6; design 0002 §2.9).

- `workspaces.open` {folder, yes, layers}, under the lock `workspaces`:
  - record: the folder must be one whose container would see nothing more than it (not a drive's root, not the user's
    home folder, not one that holds CLANK_HOME or is inside it, whose secrets a container must never see); its record
    is found by its folder, else made, named after it (`workspace_name`), and given the image layers named in `layers`
    that it does not have. Docker must run: else the refusal says how to start it (`clank docker start`, or for the
    system's Docker Engine, which Clank never starts, the command its owner runs: design 0014 §2).
  - image: Clank's sandbox image, built when no image of its tag is there, asked first unless `yes` (it downloads
    about a gigabyte), each line of the build in the operation's log; canceling the build ends it. Then the image
    layers its record names (design 0020 §3), each built on the image below it when missing, asked first unless
    `yes`, saying what they add.
  - networks: the workspace's own internal one (no route out, so nothing but the edge answers from inside: not the
    machine, not the internet, not another workspace) and the one that reaches the host, which only the edge joins.
  - edge: the edge's container, forwarding the gateway's port and the proxy's, joined to the workspace's network as
    `edge`, and to the network of every other workspace whose container there is (`edge.py`: an edge made again is on
    its first network only, and the workspaces that ran would lose their way to the model).
  - container: the folder's container, from its image (with its layers), its limits its record's, else half the CPUs
    and a quarter of the memory the platform has.
  The edge and the container are each made when they are not there and started when they are stopped; a stopped one
  made from an older image is made again (a workspace's home is a volume, so nothing of it is lost), as is one that
  cannot start because a network it was on is gone (made again since), and a running one is left as it is (the edge is
  made again when it forwards other ports). So opening again does only what is missing. A folder is never given the
  name `edge` (`RESERVED`): its container would be the edge's.
- `workspaces.setup` {folder, command, yes}, under its own lock (design 0004 §10): the folder's workspace must be open
  once (its record made, the image built). A command given is kept in its record; the command is the record's, else
  the one proposed from the folder's files (`setup.proposed_setup`), else there is nothing to install. Asked first
  unless `yes` (it names the command and says it reaches the internet), it runs in a container of its own made for it
  (`sandbox.setup_spec`), each line in the operation's log, cancelable; the record keeps the command once it ran to its
  end, and a setup that fails leaves that as it was.
- `workspaces.stop` {name}: its container stops; the edge, which others share, stays.
- `workspaces.remove` {name, yes}: asked first unless `yes`; its container, its home (its agent's settings and
  sessions) and its network are removed, then its record. Its folder is never touched.
"""

import os
import re
from collections.abc import Collection, Mapping
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.workspaces.adapters.platform import ContainerPlatform, NetworkGone
from clank.components.workspaces.kinds import Workspace
from clank.components.workspaces.sandbox import (
    PROXY_LABEL,
    ContainerSpec,
    image_folder,
    image_tag,
    layer_chain,
    layer_folder,
    layered_tag,
    names,
    setup_spec,
    workspace_spec,
)
from clank.components.workspaces.setup import proposed_setup
from clank.kernel.operations import Canceled, OperationContext, OperationType, StepSpec
from clank.kernel.questions import Option, QuestionDraft
from clank.kernel.settings import Loaded

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces

LOCK = "workspaces"
SETUP_LOCK = "workspaces.setup"  # one setup at a time, without holding up opening or stopping a workspace
QUESTION_MINUTES = 30
STOP_SECONDS = 10
NAME_LENGTH = 40
RESERVED = frozenset({"edge"})  # names whose container is another of Clank's: `clank-<home>-edge` is the edge's
FALLBACK_LIMITS = (4, 8192)  # CPUs and MiB, when the platform does not say what it has
LAYER_WORDS = {  # each image layer: its name, and what it adds (design 0020 §3)
    "tex": (
        "the TeX layer",
        "TeX Live (LaTeX, latexmk, BibTeX and biber, latexdiff, SyncTeX) and Poppler, so Clank can check and build "
        "the LaTeX the agent writes (design 0020). It downloads about 2 GB, once; every workspace with it shares it.",
    ),
}


class WorkspaceError(Exception):
    """A workspace that cannot be opened, stopped or removed, and why."""


def workspace_name(folder: str, taken: Collection[str]) -> str:
    """A workspace's name from its folder's: lowercase letters, digits and dashes, unique with `-2`, `-3`, and never one
    of `RESERVED`."""
    base = re.sub(r"[^a-z0-9]+", "-", Path(folder).name.lower()).strip("-")[:NAME_LENGTH].strip("-") or "workspace"
    name, number = base, 1
    while name in taken or name in RESERVED:
        number += 1
        name = f"{base}-{number}"
    return name


def checked_folder(given: str, clank_home: Path) -> str:
    """The folder, absolute, when its container would see nothing more than it; `WorkspaceError` saying why not."""
    path = Path(given).expanduser()
    if not path.is_absolute():
        raise WorkspaceError(f"{given} is not a full path")
    if not path.is_dir():
        raise WorkspaceError(f"{given} is not a folder")
    path = path.resolve()
    if path == Path(path.anchor):
        raise WorkspaceError(f"{path} is a drive's root: its container would see the whole drive; open a folder in it")
    if path == Path.home().resolve():
        raise WorkspaceError(
            f"{path} is your home folder: its container would see everything in it; open a folder in it"
        )
    home = clank_home.resolve()
    if home == path or home.is_relative_to(path):
        raise WorkspaceError(f"{path} holds Clank's own folder ({home}), with its secrets: open another folder")
    if path.is_relative_to(home):
        raise WorkspaceError(f"{path} is inside Clank's own folder ({home}): open another folder")
    return str(path)


def chosen_limits(workspace: Workspace, platform: tuple[int, int] | None) -> tuple[float, int]:
    """A workspace's container's CPUs and memory (MiB): its record's, else half the CPUs and a quarter of the memory
    the platform has (`platform`, None when it does not say)."""
    cpus, memory_mib = platform or FALLBACK_LIMITS
    chosen_cpus = workspace.cpus if workspace.cpus is not None else max(1.0, float(cpus // 2))
    chosen_memory = workspace.memory_mib if workspace.memory_mib is not None else max(2048, memory_mib // 4)
    return chosen_cpus, chosen_memory


def operation_types(workspaces: "Workspaces") -> list[OperationType]:
    """Opening, stopping and removing a workspace, under one lock."""
    folders = Folders(workspaces)
    steps = ("record", "image", "networks", "edge", "container")
    return [
        OperationType(
            "workspaces.open",
            "Open a workspace",
            tuple(StepSpec(step) for step in steps),
            folders.open,
            locks=_lock,
            owner="workspaces",
        ),
        OperationType(
            "workspaces.setup",
            "Install a workspace's software",
            (StepSpec("plan"), StepSpec("install")),
            folders.setup,
            locks=lambda params: [SETUP_LOCK],
            owner="workspaces",
        ),
        OperationType(
            "workspaces.stop", "Stop a workspace", (StepSpec("stop"),), folders.stop, locks=_lock, owner="workspaces"
        ),
        OperationType(
            "workspaces.remove",
            "Remove a workspace",
            (StepSpec("plan"), StepSpec("remove")),
            folders.remove,
            locks=_lock,
            owner="workspaces",
        ),
    ]


class Folders:
    """What opening, stopping and removing a workspace do."""

    def __init__(self, workspaces: "Workspaces") -> None:
        self.workspaces = workspaces
        self.kernel = workspaces.kernel

    async def open(self, context: OperationContext) -> dict[str, Any]:
        """The record, the image, the networks, the edge, the container: each only when missing."""
        home = self.kernel.home.id
        async with context.step("record"):
            folder = checked_folder(str(context.params["folder"]), self.kernel.home.root)
            platform = self.workspaces.platform
            status = await context.run_blocking(platform.status)
            if not status.running:
                raise WorkspaceError(self.workspaces.not_running(status))
            name, workspace = self._record_for(folder, context)
            workspace = self._with_layers(name, workspace, list(context.params.get("layers") or []), context)
        async with context.step("image"):
            tag = image_tag()
            if await context.run_blocking(platform.image_exists, tag):
                context.log(f"{tag} is built")
            else:
                if not context.params.get("yes"):
                    await self._ask_build(context, tag)
                await self._build(context, platform, tag)
            image = await self._layers(context, platform, name, workspace)
        async with context.step("networks"):
            found = names(home)
            labels = {"clank.home": home, "clank.component": "workspaces"}
            await context.run_blocking(lambda: platform.ensure_network(found.outer, internal=False, labels=labels))
            inner = found.inner(name)
            await context.run_blocking(lambda: platform.ensure_network(inner, internal=True, labels=labels))
        async with context.step("edge"):
            repair = await context.run_blocking(
                lambda: self.workspaces.edge.ready(
                    name, status.containers, everyone=True, remake=True, found_by=f"opening {name}", log=context.log
                )
            )
            if repair.problem:
                raise WorkspaceError(repair.problem)
        async with context.step("container"):
            cpus, memory_mib = await self._limits(context, platform, workspace)
            proxy = self.workspaces.proxy_url(name)
            spec = workspace_spec(home, name, folder, image, cpus=cpus, memory_mib=memory_mib, proxy=proxy)
            await self._ensure(context, platform, spec)
        return {"workspace": name, "folder": folder, "container": spec.name, "image": image}

    async def setup(self, context: OperationContext) -> dict[str, Any]:
        """Install the folder's software into its workspace's home, asked first, in a container that reaches the
        internet; the record keeps a command given, and the command once it ran to its end."""
        async with context.step("plan"):
            folder = checked_folder(str(context.params["folder"]), self.kernel.home.root)
            found = self._found(folder)
            if found is None:
                raise WorkspaceError(f"{folder} is not a workspace yet: open it first (`clank workspace open`, or o)")
            loaded = found
            given = str(context.params.get("command") or "").strip()
            if given and given != loaded.record.model_dump()["setup"]:
                loaded = self._write(loaded, context, setup=given)
                context.log(f"{loaded.id}'s setup is now: {given}")
            workspace = Workspace.model_validate(loaded.record.model_dump())
            command = workspace.setup or proposed_setup(folder)
            if command is None:
                context.log(f"{folder} has nothing to install: no pyproject.toml or requirements.txt, no setup command")
                return {"workspace": loaded.id, "installed": False}
            platform = self.workspaces.platform
            tag = layered_tag(workspace.layers)
            if not await context.run_blocking(platform.image_exists, tag):
                raise WorkspaceError(f"{loaded.id}'s image ({tag}) is not built: open {loaded.id} first (o builds it)")
            if not context.params.get("yes"):
                await self._ask_setup(context, loaded.id, command)
        async with context.step("install"):
            cpus, memory_mib = await self._limits(context, platform, workspace)
            spec = setup_spec(
                self.kernel.home.id, loaded.id, folder, tag, cpus=cpus, memory_mib=memory_mib, command=command
            )
            context.log(f"running in {spec.name}: {command}")
            status = await context.run_blocking(platform.run_once, spec, context.log, lambda: _canceled(context))
            context.check_canceled()
            if status != 0:
                raise WorkspaceError(f"the setup did not finish (exit {status}): the lines above say why")
            self._write(self._loaded(loaded.id), context, set_up=command)
            context.log(f"installed with: {command}")
        return {"workspace": loaded.id, "installed": True, "command": command}

    async def stop(self, context: OperationContext) -> dict[str, Any]:
        """Its container stops."""
        name = str(context.params["name"])
        async with context.step("stop"):
            self._loaded(name)
            container = names(self.kernel.home.id).container(name)
            await context.run_blocking(self.workspaces.platform.stop_container, container, STOP_SECONDS)
            context.log(f"{container} stopped")
        return {"workspace": name, "container": container}

    async def remove(self, context: OperationContext) -> dict[str, Any]:
        """Asked first (saying so when its container runs: what runs in it ends), its container and its home go, then
        its record; its folder stays."""
        name = str(context.params["name"])
        async with context.step("plan"):
            loaded = self._loaded(name)
            folder = Workspace.model_validate(loaded.record.model_dump()).path
            if not context.params.get("yes"):
                container = await context.run_blocking(
                    self.workspaces.platform.container, names(self.kernel.home.id).container(name)
                )
                running = container is not None and container.state == "running"
                await self._ask_remove(context, name, folder, running)
        async with context.step("remove"):
            found = names(self.kernel.home.id)
            platform = self.workspaces.platform
            await context.run_blocking(platform.remove_container, found.container(name))
            await context.run_blocking(platform.remove_volume, found.volume(name))
            await context.run_blocking(platform.leave_network, found.inner(name), found.edge)
            await context.run_blocking(platform.remove_network, found.inner(name))
            self.kernel.settings.delete("workspace", name, base=loaded.revision, actor=context.actor)
            context.log(f"removed {found.container(name)}, {found.volume(name)} and its network; {folder} is as it was")
        return {"workspace": name, "folder": folder}

    def _record_for(self, folder: str, context: OperationContext) -> tuple[str, Workspace]:
        """The workspace of this folder, made when there is none."""
        records = self.kernel.settings.records("workspace")
        for loaded in records:
            workspace = Workspace.model_validate(loaded.record.model_dump())
            if os.path.normcase(workspace.path) == os.path.normcase(folder):
                context.log(f"the workspace {loaded.id} is {folder}")
                return loaded.id, workspace
        name = workspace_name(folder, {loaded.id for loaded in records})
        written = self.kernel.settings.write("workspace", name, {"path": folder}, base=None, actor=context.actor)
        context.log(f"made the workspace {name} for {folder}")
        return name, Workspace.model_validate(written.record.model_dump())

    def _with_layers(self, name: str, workspace: Workspace, layers: list[str], context: OperationContext) -> Workspace:
        """The record with the layers asked for that it does not have yet."""
        missing = [layer for layer in layers if layer not in workspace.layers]
        if not missing:
            return workspace
        try:
            layer_chain([*workspace.layers, *missing])
        except ValueError as error:
            raise WorkspaceError(str(error)) from error
        written = self._write(self._loaded(name), context, layers=[*workspace.layers, *missing])
        context.log(
            f"{name} gets {', '.join(missing)}: its image is built with {'it' if len(missing) == 1 else 'them'}"
        )
        return Workspace.model_validate(written.record.model_dump())

    def _found(self, folder: str) -> Loaded | None:
        """The workspace of this folder, or None."""
        return next(
            (
                loaded
                for loaded in self.kernel.settings.records("workspace")
                if os.path.normcase(Workspace.model_validate(loaded.record.model_dump()).path)
                == os.path.normcase(folder)
            ),
            None,
        )

    def _write(self, loaded: Loaded, context: OperationContext, **changes: Any) -> Loaded:
        """The record with these values changed, written over the revision it was read at."""
        values = {**loaded.record.model_dump(), **changes}
        return self.kernel.settings.write("workspace", loaded.id, values, base=loaded.revision, actor=context.actor)

    def _loaded(self, name: str) -> Loaded:
        known = {loaded.id: loaded for loaded in self.kernel.settings.records("workspace")}
        if name not in known:
            raise WorkspaceError(f"there is no workspace {name!r}; there are: {', '.join(sorted(known)) or 'none'}")
        return known[name]

    async def _layers(
        self, context: OperationContext, platform: ContainerPlatform, name: str, workspace: Workspace
    ) -> str:
        """Build the image layers the workspace names that are missing, asked first unless `yes`; its image's tag."""
        try:
            chain = layer_chain(workspace.layers)
        except ValueError as error:
            raise WorkspaceError(f"{name}'s record names {error}") from error
        missing = [step for step in chain if not await context.run_blocking(platform.image_exists, step.tag)]
        if missing and not context.params.get("yes"):
            await self._ask_layers(context, name, [step.layer for step in missing])
        for step in missing:
            await self._build(context, platform, step.tag, layer_folder(step.layer), {"BASE": step.base}, step.layer)
        for step in chain:
            if step not in missing:
                context.log(f"{step.tag} is built")
        return chain[-1].tag if chain else image_tag()

    async def _build(
        self,
        context: OperationContext,
        platform: ContainerPlatform,
        tag: str,
        folder: Path | None = None,
        args: Mapping[str, str] | None = None,
        layer: str = "",
    ) -> None:
        context.log(f"building {tag}: a few minutes, once")
        labels: Mapping[str, str] = {"clank.image": layer or "sandbox"}
        built_from = str(folder or image_folder())
        status = await context.run_blocking(
            lambda: platform.build_image(tag, built_from, labels, context.log, lambda: _canceled(context), args)
        )
        context.check_canceled()
        if status != 0:
            what = LAYER_WORDS[layer][0] if layer in LAYER_WORDS else "the sandbox image"
            raise WorkspaceError(f"{what} could not be built (exit {status}): the lines above say why")

    async def _ensure(self, context: OperationContext, platform: ContainerPlatform, spec: ContainerSpec) -> None:
        """Make the workspace's container when it is not there; start it when it is stopped; make it again from a newer
        image, when it was not told the proxy this one is (its label `clank.proxy`, design 0024 §2), or when it cannot
        start because a network it was on is gone (made again since: Docker keeps the network's id)."""
        found = await context.run_blocking(platform.container, spec.name)
        wanted_proxy = dict(spec.labels).get(PROXY_LABEL, "")
        told = found.clank.get(PROXY_LABEL, "") if found is not None else ""
        if found is not None and found.state != "running":
            if found.image != spec.image:
                await context.run_blocking(platform.remove_container, spec.name)
                context.log(f"{spec.name} was made from {found.image}; it is made again from {spec.image}")
                found = None
            elif told != wanted_proxy:
                await context.run_blocking(platform.remove_container, spec.name)
                was = f"told the proxy on {told}" if told else "made without the proxy"
                context.log(f"{spec.name} was {was}; it is made again, told the proxy on {wanted_proxy}")
                found = None
        if found is None:
            await context.run_blocking(platform.run_container, spec)
            context.log(f"{spec.name} made and started")
        elif found.state != "running":
            try:
                await context.run_blocking(platform.start_container, spec.name)
            except NetworkGone:
                await context.run_blocking(platform.remove_container, spec.name)
                context.log(f"{spec.name} could not start (a network it was on is gone): it is made again")
                await context.run_blocking(platform.run_container, spec)
                context.log(f"{spec.name} made and started")
                return
            context.log(f"{spec.name} started")
        elif found.image != spec.image:
            context.log(f"{spec.name} runs {found.image}: it is made again from {spec.image} once it is stopped")
        elif told != wanted_proxy:
            was = f"told the proxy on {told}, not {wanted_proxy}" if told else "without the proxy"
            context.log(f"{spec.name} runs {was}: it is made again, told the proxy, once it is stopped")
        else:
            context.log(f"{spec.name} runs")

    async def _limits(
        self, context: OperationContext, platform: ContainerPlatform, workspace: Workspace
    ) -> tuple[float, int]:
        """Its record's CPUs and memory, else half the CPUs and a quarter of the memory the platform has."""
        found = None
        if workspace.cpus is None or workspace.memory_mib is None:
            found = await context.run_blocking(platform.limits)
        chosen_cpus, chosen_memory = chosen_limits(workspace, found)
        context.log(f"its limits: {chosen_cpus:g} CPUs, {chosen_memory:,} MiB")
        return chosen_cpus, chosen_memory

    async def _ask_build(self, context: OperationContext, tag: str) -> None:
        lines = [
            f"Clank's sandbox image ({tag}) is not built yet: it is built once, in a few minutes.",
            "It downloads about a gigabyte: Ubuntu 24.04, Node.js 22, OpenCode and the common build tools.",
            "Every workspace's container and the edge run it.",
        ]
        await self._ask(context, "Build Clank's sandbox image?", lines, "build", "Build it", "nothing is built")

    async def _ask_layers(self, context: OperationContext, name: str, layers: list[str]) -> None:
        said = [LAYER_WORDS.get(layer, (f"the {layer} layer", "")) for layer in layers]
        title = f"Build {' and '.join(words for words, _ in said)} for {name}?"
        lines = [f"{words[0].upper()}{words[1:]} adds {adds}" for words, adds in said]
        lines.append(
            f"{name}'s container moves to it when it is next made: a running one once it is stopped and opened."
        )
        await self._ask(context, title, lines, "build", "Build it", "nothing is built")

    async def _ask_setup(self, context: OperationContext, name: str, command: str) -> None:
        lines = [
            f"Clank installs {name}'s own software into its home (~/.venv), so its agent can run it:",
            f"  {command}",
            "It runs in a container of its own that reaches the internet to download the packages, mounted like the "
            "workspace's; the workspace's container, where the agent runs, never reaches out.",
            "The first time it may take a few minutes.",
        ]
        await self._ask(context, f"Install {name}'s software?", lines, "install", "Install it", "nothing is installed")

    async def _ask_remove(self, context: OperationContext, name: str, folder: str, running: bool) -> None:
        ends = "Its container runs now: what runs in it ends, OpenCode in a VS Code window or a terminal too."
        lines = [
            *([ends] if running else []),
            "Its container and its home (its agent's settings and sessions) are removed.",
            f"{folder} stays as it is.",
        ]
        await self._ask(context, f"Remove the workspace {name}?", lines, "remove", "Remove it", "nothing is removed")

    async def _ask(
        self, context: OperationContext, title: str, lines: list[str], yes: str, label: str, otherwise: str
    ) -> None:
        """Ask; any answer but `yes` cancels the operation with nothing done."""
        draft = QuestionDraft(
            type="approval",
            title=title,
            detail="\n".join(lines),
            options=[
                Option(id=yes, label=label, key="y", effect=title.rstrip("?").lower()),
                Option(id="cancel", label="Not now", key="n", effect=otherwise),
            ],
            default="cancel",
            expires=self.kernel.clock.now() + timedelta(minutes=QUESTION_MINUTES),
        )
        answer = await context.ask(draft)
        if answer.option != yes:
            raise Canceled(f"{otherwise}: {answer.by.describe()} chose not to")


def _lock(params: Mapping[str, Any]) -> list[str]:
    return [LOCK]


def _canceled(context: OperationContext) -> bool:
    try:
        context.check_canceled()
    except Canceled:
        return True
    return False
