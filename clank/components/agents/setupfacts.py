"""What the setup's checklist reads (`checklist.Facts`, design 0028 §4), gathered in the service or without it.

`from_service` is the agents' part's (`GET /setup`): Docker through the workspaces' platform (`setup_reading`, its
memory limits kept a few minutes), the preset that last answered a test request in the main slot (the runtime's
`last_good`), each workspace from its record, the operation building the sandbox image while one does (a
`workspaces.image`, or an opening of a workspace in its image step), this computer's GPUs as the machine reads them,
Clank's VS Code window, and the programs a fix of Docker runs. `offline` is `clank setup`'s when the service does not
run: Docker as the doctor reads it (`read_setup`), Clank's VS Code window and the programs; the rest is the service's
to say. Clank's VS Code window is read from its files alone (`vscode_state`): VS Code's program as Clank finds it, and
the newest version of Clank's extension in the window's own extensions folder (CLANK_HOME/vscode/extensions), so no
program is started to know it.
"""

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from clank.components.agents import checklist, vscode
from clank.components.agents.checklist import Building, Facts, Model, VsCode
from clank.components.agents.kinds import VsCodeSettings
from clank.components.workspaces.service import read_setup
from clank.kernel.home import Home
from clank.kernel.settings import read_record

if TYPE_CHECKING:
    from clank.components.machine.service import Machine
    from clank.components.runtime.service import Runtime
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

EXTENSION = re.compile(r"clank\.clank-(\d+(?:\.\d+)*)")  # Clank's extension's folder in VS Code's extensions folder
BUILDING = ("workspaces.image", "workspaces.open")  # the operations that build the sandbox image
UNFINISHED = ("queued", "running", "waiting")
GIB = 2**30


def vscode_state(home: Home, configured: list[str], find: Callable[..., object] | None = None) -> VsCode:
    """Clank's VS Code window: whether VS Code's program is found (as the window would find it), and the newest version
    of Clank's extension in the window's extensions folder ("" when none)."""
    found = (find or vscode.find_program)(configured) is not None
    folder = home.root / "vscode" / "extensions"
    versions = []
    if folder.is_dir():
        for path in folder.iterdir():
            match = EXTENSION.fullmatch(path.name)
            if match and path.is_dir():
                versions.append(match.group(1))
    newest = max(versions, key=lambda version: tuple(int(part) for part in version.split(".")), default="")
    return VsCode(found=found, extension=newest)


def vscode_settings(home: Home) -> VsCodeSettings:
    """`config/vscode.json` as the service would read it; its defaults when it is not there or does not read."""
    path: Path = home.config / "vscode.json"
    loaded = read_record(VsCodeSettings, path) if path.is_file() else []
    return VsCodeSettings.model_validate(loaded[0].model_dump()) if isinstance(loaded, tuple) else VsCodeSettings()


def offline(home: Home, folder: str = "") -> Facts:
    """What `clank setup` reads without the service: Docker, through the platform the settings choose, Clank's VS Code
    window, and the programs a fix of Docker runs; `folder` checked as a workspace's would be."""
    return Facts(
        system=sys.platform,
        docker=read_setup(home, folder),
        vscode=vscode_state(home, vscode_settings(home).program),
        tools=checklist.found_tools(),
    )


def from_service(kernel: "Kernel", folder: str = "", refresh: bool = False) -> Facts:
    """What the service reads for the checklist (the module's docstring); Docker's status read now with `refresh`."""
    workspaces: Workspaces = kernel.parts["workspaces"]
    runtime: Runtime = kernel.parts["runtime"]
    machine: Machine = kernel.parts["machine"]
    docker = workspaces.setup_reading(folder, refresh)
    settings = VsCodeSettings.model_validate(kernel.settings.get("vscode", "vscode").record.model_dump())
    return Facts(
        system=sys.platform,
        docker=docker,
        service=True,
        model=_model(runtime),
        workspaces=tuple((str(row["name"]), str(row["path"])) for row in workspaces.records()),
        building=_building(kernel) if docker.image_built is False else None,
        gpus=_gpus(machine),
        vscode=vscode_state(kernel.home, settings.program),
        tools=checklist.found_tools(),
    )


def _gpus(machine: "Machine") -> tuple[str, ...]:
    """This computer's NVIDIA GPUs, each with its memory: from the machine's last reading of its meters (NVIDIA's own
    library, every second), else from its profile (the doctor's)."""
    readings = machine.meters()
    found = readings[-1].get("gpus") if readings else None
    if found:
        return tuple(f"{gpu['name']}, {gpu['memory_total'] / GIB:.0f} GB" for gpu in found if gpu.get("memory_total"))
    return tuple(f"{gpu.name}, {gpu.memory_mib / 1024:.0f} GB" for gpu in machine.profile().gpus)


def _model(runtime: "Runtime") -> Model | None:
    """The preset that last answered a test request in the main slot, with its title and whether it is a cloud one."""
    good = runtime.state.slot("main").last_good
    if good is None:
        return None
    view = next((preset for preset in runtime.presets() if preset["id"] == good.preset), None)
    return Model(good.preset, runtime.title(good.preset), cloud=bool(view and view.get("endpoint")))


def _building(kernel: "Kernel") -> Building | None:
    """The operation building the sandbox image, with its log's last line: one that builds it alone, or the opening of
    a workspace in its image step."""
    for status in UNFINISHED:
        for operation in kernel.operations.find(status=status):
            if operation.type not in BUILDING:
                continue
            if operation.type == "workspaces.open" and (not operation.steps or operation.steps[-1].name != "image"):
                continue
            if operation.status == "waiting":
                return Building(operation.id, "it waits for your answer (Waiting for you, or `clank questions`)")
            lines = kernel.operations.log_lines(operation.id)
            return Building(operation.id, lines[-1].text if lines else "")
    return None
