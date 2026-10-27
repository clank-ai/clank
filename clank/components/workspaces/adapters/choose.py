"""Which container platform adapter the setting `adapter` means on this computer (design 0014 §2, decision 0070).

A name set in `config/docker.json` is used as named. `auto`, the default, is Docker Desktop on Windows and macOS. On
Linux it is the adapter of the engine the docker command would use, found without asking any engine, so none is woken:

1. Docker Desktop, when the command's current context is Docker Desktop's (`desktop-linux`, read with `docker context
   show`): Docker Desktop sets that context while it runs, and sets `default` back when it stops.
2. Else Docker Engine, when systemd knows Docker's service.
3. Else Docker Desktop, when Docker Desktop's own command answers (`docker desktop version`): a stopped Docker Desktop,
   on a computer without Docker Engine.
4. Else Docker Engine, when a docker command is found: it asks the engine directly, or says that Docker from the snap
   and rootless Docker are unsupported.
5. Else Docker Engine, which says that Docker is not installed, and how to install it.

Each choice says why, in words Docker's view shows. The three commands it may run (`docker context show`, `systemctl
show docker.service`, `docker desktop version`) reach no engine.
"""

import os
import shutil
import sys
from collections.abc import Callable, Mapping

from clank.components.workspaces.adapters.docker_cli import find_docker
from clank.components.workspaces.adapters.docker_desktop import CONTEXT as DESKTOP_CONTEXT
from clank.components.workspaces.adapters.docker_engine import docker_service
from clank.kernel.processes import TimedAnswer, run_answer

AUTO = "auto"
ASK_SECONDS = 5.0


def choose_platform(
    setting: str,
    platform: str = sys.platform,
    answer: TimedAnswer = run_answer,
    which: Callable[[str], str | None] = shutil.which,
    environ: Mapping[str, str] = os.environ,
) -> tuple[str, str]:
    """The adapter's name the setting means here, and why."""
    if setting != AUTO:
        return setting, "named in config/docker.json"
    if platform == "win32":
        return "docker-desktop", "Docker Desktop: this is Windows"
    if platform == "darwin":
        return "docker-desktop", "Docker Desktop: this is macOS"
    docker = find_docker(which, environ, platform)
    if docker is not None:
        context = answer([docker, "context", "show"], timeout=ASK_SECONDS)
        if context.ok and context.output.strip() == DESKTOP_CONTEXT:
            return "docker-desktop", (
                f"Docker Desktop: the docker command's current context is Docker Desktop's ({DESKTOP_CONTEXT})"
            )
    service = docker_service(answer)
    if service is not None and service.known:
        return "docker-engine", "Docker Engine: this is Linux, and systemd knows Docker's service"
    if docker is None:
        return "docker-engine", "Docker Engine: no docker command is installed"
    if answer([docker, "desktop", "version", "--format", "json"], timeout=ASK_SECONDS).ok:
        return "docker-desktop", "Docker Desktop: its own command answers, and systemd knows no Docker Engine"
    return "docker-engine", "Docker Engine: the docker command is here, and no Docker Desktop answers"
