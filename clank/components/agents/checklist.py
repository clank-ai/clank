"""`clank setup`'s checklist (design 0028 §4, §5): what Clank needs on this computer, in order, each item with its
state, what it is now in plain words, and, while it is not done, what to do about it (its `Fix`).

`items` is a pure function of `Facts`. The service gathers them (`GET /setup`, served by the agents' part, which reads
Docker through the workspaces, the main slot through the runtime, this computer through the machine, and Clank's VS
Code window itself); `clank setup` gathers Docker itself when the service does not run, as the doctor does, and then
the model and the folder are not known (`unknown`), which the items say rather than guess.

The items, in order: Docker installed, Docker running, Docker starts with the computer (only where systemd says,
Docker Engine), Docker usable by this account, Docker limits memory (only where it cannot), Clank's service, the
sandbox image (built in the background by the service's `workspaces.image` while it is not built for this Clank), a
model, a folder, and Clank's VS Code window. The service comes before the image, which it builds; both
come after Docker, so a service the setup starts never starts before this account may use Docker (a process keeps the
groups it started with). Starting with the computer and the VS Code window are offered, not required.

Each Docker state of §5 has its words, its fix and whether Clank does it (`Fix.does`): not installed, the installer's
Docker step in the terminal (`winget` on Windows, Homebrew on macOS, Clank's installer on Linux), on a yes; the snap's
or rootless Docker, not supported, the commands shown and never run; Docker Engine stopped, `sudo systemctl start
docker` in the terminal; Docker Desktop stopped, started through its own command by Clank; not started at boot, `sudo
systemctl enable docker` in the terminal; no access outside the docker group, `sudo usermod -aG docker <account>` in
the terminal, then a log out and in, which is the person's; no access inside it, the log out and in alone; no memory
limits, the kernel setting, which Clank never makes. A command that needs administrator rights (`Fix.admin`) runs only
attached to the person's terminal, where sudo or Windows asks for the password itself; Clank never reads, asks for or
keeps a password. An item waits while one it needs is not done (the image while Docker cannot be used).

`view` is the checklist as the API gives it and every client shows it: the items, whether everything required is done
(`ready`), one line on it, and, once ready, what was set up and what each thing is for.
"""

import shlex
import shutil
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from clank.components.workspaces.service import MEMORY_FIX, SetupReading, memory_said

State = Literal["done", "to do", "doing", "waits", "unknown"]
Does = Literal["", "terminal", "docker", "service", "image", "model", "folder"]
INSTALLER = "curl -fsSL https://clank-ai.github.io/install.sh | sh"
DOCKER_PAGE = "docker.com/products/docker-desktop"
ENGINE_PAGES = "docs.docker.com/engine/install"
GROUP_NOTE = "docs.docker.com/engine/install/linux-postinstall"
UNDO = "getting started's Uninstalling section (clank-ai.github.io/get-started) says how to remove each"
TOOLS = ("winget", "brew", "curl")  # what a fix of Docker runs, found on the PATH
LISTED = 3  # the workspaces the folder's item names


@dataclass(frozen=True)
class Fix:
    """What to do about an item, in words (`said`), and what Clank does on a yes (`does`): run `command` in the
    terminal, start Docker through its own command, start its service, build the sandbox image, Add a model, or open the
    folder; nothing ("") when it is the person's to do. `admin`: the command needs administrator rights (sudo, or
    Windows' own prompt). `after`: what the person does once it ran (log out and in). `shown`: the command as the
    person reads it."""

    said: str
    does: Does = ""
    command: tuple[str, ...] = ()
    admin: bool = False
    after: str = ""
    shown: str = ""


@dataclass(frozen=True)
class Item:
    """One thing Clank needs: its state, what it is now, whether it is required for Ready, and its fix."""

    id: str
    title: str
    state: State
    said: str
    required: bool = True
    fix: Fix | None = None


@dataclass(frozen=True)
class Model:
    """The preset that last answered a test request in the main slot (its `last_good`)."""

    preset: str
    title: str
    cloud: bool  # it runs at a provider (OpenRouter), not on this computer


@dataclass(frozen=True)
class Building:
    """The operation building the sandbox image, while it runs."""

    operation: str
    line: str = ""  # the last line of its log


@dataclass(frozen=True)
class VsCode:
    """Clank's VS Code window: whether VS Code is found, and the version of Clank's extension in it ("": none)."""

    found: bool = False
    extension: str = ""


@dataclass(frozen=True)
class Facts:
    """What the checklist reads. `service`: the facts come from Clank's service, which runs; without it, the model,
    the workspaces, the image's build and this computer's GPUs are not known."""

    system: str
    docker: SetupReading
    service: bool = False
    model: Model | None = None
    workspaces: tuple[tuple[str, str], ...] = ()  # each workspace's name and folder
    building: Building | None = None
    gpus: tuple[str, ...] = ()  # each NVIDIA GPU, "NVIDIA GeForce RTX 5080, 16 GB"
    vscode: VsCode = field(default_factory=VsCode)
    tools: frozenset[str] = frozenset()  # of `TOOLS`, those found


def found_tools(which: Callable[[str], str | None] = shutil.which) -> frozenset[str]:
    """The programs a fix of Docker runs that are on the PATH."""
    return frozenset(tool for tool in TOOLS if which(tool))


def shown(command: Sequence[str]) -> str:
    """A command as the person would type it."""
    return shlex.join(command)


def _admin(command: Sequence[str], said: str, after: str = "") -> Fix:
    """A fix that runs a command with administrator rights in the person's terminal, where sudo asks for the password
    itself."""
    words = f"{said}: `{shown(command)}`, with administrator rights, so it runs in your terminal, where sudo asks for "
    return Fix(
        words + "your password itself (Clank never sees it)",
        "terminal",
        tuple(command),
        admin=True,
        after=after,
        shown=shown(command),
    )


def _installed(facts: Facts) -> Item:
    status = facts.docker.status
    title = "Docker installed"
    if status.state == "not installed":
        said = "not installed. Clank runs the agent in a Docker container of its own for each folder, so the agent "
        return Item("docker_installed", title, "to do", said + "sees only that folder", fix=_install(facts))
    if status.state == "unsupported":
        return Item("docker_installed", title, "to do", status.detail, fix=_unsupported(facts))
    said = f"{status.label} {status.version}" if status.version else f"{status.label} is installed"
    return Item("docker_installed", title, "done", said)


def _install(facts: Facts) -> Fix:
    """The installer's Docker step, run in the terminal on a yes, or where to get Docker when no command can."""
    if facts.system == "win32":
        if "winget" not in facts.tools:
            return Fix(
                f"install Docker Desktop ({DOCKER_PAGE}), open it once and accept its terms, then run `clank setup` "
                "again"
            )
        command: tuple[str, ...] = ("winget", "install", "--id", "Docker.DockerDesktop", "-e")
        return Fix(
            f"install Docker Desktop with Windows' own package manager: `{shown(command)}`. Windows asks for "
            "administrator rights itself, and Docker Desktop's installer may turn WSL 2 on and ask to restart",
            "terminal",
            command,
            admin=True,
            after="restart if Docker Desktop's installer asks, open Docker Desktop once and accept its terms, then run "
            "`clank setup` again",
            shown=shown(command),
        )
    if facts.system == "darwin":
        if "brew" not in facts.tools:
            return Fix(
                f"install Docker Desktop ({DOCKER_PAGE}), open it once and accept its terms, then run `clank setup` "
                "again"
            )
        command = ("brew", "install", "--cask", "docker")
        return Fix(
            f"install Docker Desktop with Homebrew: `{shown(command)}` (it may ask for your password itself)",
            "terminal",
            command,
            admin=True,
            after="open Docker Desktop once (in Applications) and accept its terms, then run `clank setup` again",
            shown=shown(command),
        )
    if "curl" not in facts.tools:
        return Fix(
            f"install Docker Engine as {ENGINE_PAGES} says for your distribution (not the snap), then run `clank "
            "setup` again"
        )
    return Fix(
        f"Clank's installer installs Docker Engine from Docker's own packages for this Linux: `{INSTALLER}`. It shows "
        "each command and asks before it runs them with sudo, which asks for your password itself; it also installs "
        "Clank's latest release again",
        "terminal",
        ("sh", "-c", INSTALLER),
        admin=True,
        after="log out and in once if it added you to the docker group, then run `clank setup` again",
        shown=INSTALLER,
    )


def _unsupported(facts: Facts) -> Fix:
    """What replaces a Docker Clank does not support: never run by Clank (design 0028 §5)."""
    if facts.docker.status.adapter == "docker-engine":
        return Fix(
            f"install Docker Engine from Docker's own packages beside it, as {ENGINE_PAGES} says for your "
            f"distribution; Clank's installer does it, showing each command and asking first (`{INSTALLER}`), and "
            "Clank then uses that one"
        )
    return Fix(
        "update Docker Desktop (4.37 or newer has the `docker desktop` command Clank needs), then run `clank setup` "
        "again"
    )


def _running(facts: Facts, installed: Item) -> Item:
    status, title = facts.docker.status, "Docker running"
    if installed.state != "done":
        return Item("docker_running", title, "waits", "waits for Docker to be installed")
    if status.running:
        engine = f", engine {status.engine}" if status.engine and status.engine != status.version else ""
        return Item("docker_running", title, "done", f"it runs{engine}")
    if status.state == "no access":
        return Item("docker_running", title, "done", "it runs; this account may not use it yet (below)")
    if status.state in ("starting", "stopping"):
        said = f"{status.label} is {status.state}: wait a moment, then check again"
        return Item("docker_running", title, "to do", said)
    if facts.docker.starts:
        said = f"{status.label} is not running"
        how = (
            f"start {status.label}: Clank asks it with its own command and waits for it (the first time, accept its "
            "terms in its window)"
        )
        return Item("docker_running", title, "to do", said, fix=Fix(how, "docker"))
    said = (
        "Docker's service failed (`systemctl status docker` says why)"
        if status.state == "failed"
        else f"{status.label} is {status.state}"
    )
    start = facts.docker.setup.start
    if not start:
        return Item("docker_running", title, "to do", said, fix=Fix(status.detail or f"start {status.label}"))
    return Item("docker_running", title, "to do", said, fix=_admin(start, f"start {status.label}"))


def _boot(facts: Facts) -> Item | None:
    """Whether Docker starts with the computer, where its platform says (Docker Engine, through systemd)."""
    at_boot, boot = facts.docker.setup.at_boot, facts.docker.setup.boot
    if at_boot is None:
        return None
    title = "Docker starts with the computer"
    if at_boot:
        return Item("docker_boot", title, "done", "systemd starts Docker's service when the computer starts", False)
    said = "no: Docker will be stopped after the computer restarts"
    fix = _admin(boot, "start it with the computer") if boot else None
    return Item("docker_boot", title, "to do", said, False, fix)


def _access(facts: Facts, running: Item) -> Item:
    status, title = facts.docker.status, "Docker usable by this account"
    if running.state != "done":
        return Item("docker_access", title, "waits", "waits for Docker to run")
    if status.state != "no access":
        return Item("docker_access", title, "done", "this account may use Docker")
    again = "`clank stop`, then `clank`" if facts.service else "run `clank setup` again"
    if facts.docker.setup.in_group:
        said = "this account is in the docker group, but the group is not active in this session yet"
        fix = Fix(f"log out and in again (or restart the computer), then {again}")
        return Item("docker_access", title, "to do", said, fix=fix)
    join = facts.docker.setup.join
    if facts.docker.setup.in_group is None or not join:
        return Item("docker_access", title, "to do", "this account may not use Docker", fix=Fix(status.detail))
    said = (
        "this account may not use Docker: it is not in the docker group. Docker says the group gives root's rights on "
        f"this computer ({GROUP_NOTE})"
    )
    after = f"log out and in once (or restart the computer), so every program you start can use Docker; then {again}"
    return Item("docker_access", title, "to do", said, fix=_admin(join, "join the docker group", after))


def _memory(facts: Facts) -> Item | None:
    """Docker's memory limits, said only where Docker cannot set them (design 0014 §4)."""
    limited, words = facts.docker.memory
    if limited is not False:
        return None
    title, said = "Docker limits memory", memory_said(words)
    if facts.docker.allow_unlimited_memory:
        allowed = f"no ({said}): workspaces open without it, as allow_unlimited_memory in config/docker.json allows"
        return Item("docker_memory", title, "done", allowed)
    fix = Fix(f"{MEMORY_FIX[0].upper()}{MEMORY_FIX[1:]}; or set allow_unlimited_memory in config/docker.json")
    return Item("docker_memory", title, "to do", f"no ({said}), so no workspace opens", fix=fix)


def _service(facts: Facts, access: Item) -> Item:
    """Clank's service; while this account may not use Docker yet, it waits: a service started then keeps the groups
    this session has, and could not use Docker either once the account may."""
    title = "Clank's service"
    if facts.service:
        return Item("service", title, "done", "it runs in the background: the gateway, the workspaces and the agents")
    if access.state == "to do":
        said = "waits until this account can use Docker: started before, it could not use Docker either"
        return Item("service", title, "waits", said)
    said = "not running. It runs in the background: the gateway, the workspaces and the agents"
    fix = Fix(
        "start it: `clank serve --background` (`clank` starts it too; `clank stop` ends it)",
        "service",
        shown="clank serve --background",
    )
    return Item("service", title, "to do", said, fix=fix)


def _image(facts: Facts, usable: bool) -> Item:
    docker, title = facts.docker, "The sandbox image"
    if not usable:
        return Item("image", title, "waits", "waits until this account can use Docker")
    if facts.building is not None:
        line = f": {facts.building.line}" if facts.building.line else ""
        return Item("image", title, "doing", f"being built in the background ({facts.building.operation}){line}")
    if docker.image_built is None:
        return Item("image", title, "unknown", "Docker did not say")
    if docker.image_built:
        return Item("image", title, "done", f"built for this Clank ({docker.image})")
    said = (
        "not built yet. Every workspace's container runs it; it is built once, in a few minutes, and downloads about a "
        "gigabyte (Ubuntu 24.04, Node.js 22, OpenCode and the common build tools)"
    )
    fix = Fix(
        "build it now, in the background: the setup goes on meanwhile, and the first folder then opens at once",
        "image",
    )
    return Item("image", title, "to do", said, fix=fix)


def _model(facts: Facts) -> Item:
    title = "A model"
    if not facts.service:
        return Item("model", title, "unknown", "Clank's service tells this once it runs")
    if facts.model is not None:
        where = "in the cloud, at OpenRouter" if facts.model.cloud else "on this computer"
        return Item("model", title, "done", f"{facts.model.title} answered a test request ({where})")
    if facts.system == "darwin":
        gpu = "A Mac has no NVIDIA GPU: the cloud is the way"
    elif facts.gpus:
        gpu = f"This computer has {facts.gpus[0]}: local models can run on it"
    else:
        gpu = "This computer has no NVIDIA GPU Clank can use: the cloud is the way"
    said = f"no model has answered a test request yet. {gpu}"
    fix = Fix(
        "Add a model: in the cloud through OpenRouter (with your OpenRouter key), on this computer's GPU, or both "
        "(the cloud first, then local)",
        "model",
        shown="clank model add",
    )
    return Item("model", title, "to do", said, fix=fix)


def _folder(facts: Facts) -> Item:
    title, docker = "A folder", facts.docker
    if not facts.service:
        return Item("folder", title, "unknown", "Clank's service tells this once it runs")
    if facts.workspaces:
        named = ", ".join(f"{name} ({path})" for name, path in facts.workspaces[:LISTED])
        more = f" and {len(facts.workspaces) - LISTED} more" if len(facts.workspaces) > LISTED else ""
        count = len(facts.workspaces)
        return Item("folder", title, "done", f"{count} workspace{'s' if count > 1 else ''}: {named}{more}")
    said = "no folder is a workspace yet. The agent works in a folder you choose, in a container that sees only it"
    if docker.folder_problem:
        fix = Fix(f"{docker.folder_problem}. Open a terminal in a project's folder and type `clank` there")
    elif docker.folder_access:
        fix = Fix(docker.folder_access)
    elif docker.folder:
        fix = Fix(f"open {docker.folder} as a workspace (This folder's o does it too)", "folder")
    else:
        fix = Fix("This folder opens the folder `clank` was started in as a workspace", "folder")
    return Item("folder", title, "to do", said, fix=fix)


def _vscode(facts: Facts) -> Item:
    title = "Clank's VS Code window"
    if facts.vscode.extension:
        return Item("vscode", title, "done", f"its extension {facts.vscode.extension} is installed", False)
    if not facts.vscode.found:
        said = "VS Code is not installed; the agent works in the terminal without it"
        fix = Fix("install VS Code (code.visualstudio.com), then `clank code` in a folder")
        return Item("vscode", title, "to do", said, False, fix)
    said = "Clank's extension is not in its VS Code window yet"
    fix = Fix("`clank code` in a folder (or c on This folder) installs it the first time it opens the window")
    return Item("vscode", title, "to do", said, False, fix)


def items(facts: Facts) -> list[Item]:
    """Every item, in order."""
    installed = _installed(facts)
    running = _running(facts, installed)
    access = _access(facts, running)
    found = [installed, running, _boot(facts), access, _memory(facts), _service(facts, access)]
    usable = access.state == "done" and facts.docker.status.running
    found += [_image(facts, usable), _model(facts), _folder(facts), _vscode(facts)]
    return [item for item in found if item is not None]


def ready(found: Sequence[Item]) -> bool:
    """Whether everything required is done."""
    return all(item.state == "done" for item in found if item.required)


def ready_said(facts: Facts) -> list[str]:
    """Once ready: what was set up, and what each thing is for."""
    label = facts.docker.status.label
    lines = [
        f"{label} runs the agent in a container of its own for each folder, so the agent sees only that folder.",
        f"The sandbox image ({facts.docker.image}) is what each of those containers runs.",
        "Clank's service runs in the background: the gateway every model request goes through, the workspaces and the "
        "agents.",
    ]
    if facts.model is not None:
        where = (
            "in the cloud, at OpenRouter: each request is paid and shown" if facts.model.cloud else "on this computer"
        )
        lines.append(f"{facts.model.title} answers the agent, {where}.")
    if facts.workspaces:
        lines.append("Your workspaces: " + ", ".join(name for name, _ in facts.workspaces) + ".")
    lines += [
        "Next: open a terminal in a project's folder and type `clank`; This folder starts the agent there (a), or in "
        "VS Code (c).",
        f"To undo any of it, {UNDO}.",
    ]
    return lines


def view(facts: Facts) -> dict[str, Any]:
    """The checklist as the API gives it: every item (its fix with its command as shown), whether everything required
    is done, one line on it, and once ready what was set up."""
    found = items(facts)
    done = ready(found)
    left = [item.title for item in found if item.required and item.state != "done"]
    said = "Ready: everything Clank needs is set up." if done else f"Not ready yet: {', '.join(left)}."
    return {
        "ready": done,
        "said": said,
        "items": [_item_view(item) for item in found],
        "ready_said": ready_said(facts) if done else [],
    }


def _item_view(item: Item) -> dict[str, Any]:
    found = asdict(item)
    if item.fix is not None:
        found["fix"]["command"] = list(item.fix.command)
    return found
