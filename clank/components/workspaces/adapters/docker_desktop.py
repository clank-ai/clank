"""The Docker Desktop adapter: Docker Desktop through its own commands (design 0002 §2.9, §2.10).

Docker Desktop 4.37 and newer has the `docker desktop` command (start, stop, status), which this adapter needs; with an
older one it says so (Docker Engine alone has an adapter of its own, `docker_engine.py`). The status asks the engine
first: `docker version` (Docker Desktop's version and its engine's), then its containers, as the base lists them. Only
when the engine does not answer is `docker desktop status` asked, with a short time limit, to tell a Docker Desktop that
is starting or stopping from a stopped one: stopped, Docker Desktop 4.85 never answers it (recorded on 2026-10-13). A
start or a stop is asked with `--detach`, and the operation that asked waits for the engine; the stop answers only once
Docker Desktop has stopped (13 seconds on 4.85), so both are given a minute. After `docker desktop stop`, Docker Desktop
4.85's `docker desktop start` answers that Docker Desktop already runs and starts nothing; when that happens to a
stopped Docker Desktop, its own program is started instead, as the Start menu starts it (on Windows, `Docker
Desktop.exe`, two folders above its command). On Windows, Docker Desktop started after WSL removes WSL's handler for
Windows programs (PROTOTYPE.md), so after a start, if WSL runs and the handler is gone, the adapter registers it again
and says so. Its container commands (design 0004 §3) are Docker's own, the base's (`docker_cli.py`, design 0014 §2),
whose names stay importable from here. On Linux every command names Docker Desktop's own context (`--context
desktop-linux`), so Docker Engine's containers are never read as its own once it has stopped and set the `default`
context back; on Windows and macOS its commands do not change.
"""

import json
import re
import sys
from collections.abc import Callable
from pathlib import PureWindowsPath

from clank.components.workspaces.adapters.docker_cli import INSPECT as INSPECT
from clank.components.workspaces.adapters.docker_cli import PUT_FILES as PUT_FILES
from clank.components.workspaces.adapters.docker_cli import TEMPLATE as TEMPLATE
from clank.components.workspaces.adapters.docker_cli import DockerCli
from clank.components.workspaces.adapters.docker_cli import find_docker as find_docker
from clank.components.workspaces.adapters.platform import Follow, PlatformError, PlatformStatus, follow_command
from clank.kernel.adapters import Capability
from clank.kernel.processes import Launch, TimedAnswer, TimedRun, launch_program, run_answer

VERSIONS = "{{.Server.Platform.Name}}|{{.Server.Version}}"
CONTEXT = "desktop-linux"  # Docker Desktop's own context on Linux, current while it runs
STATUS_SECONDS = 2.0  # running, `docker desktop status` answers at once; stopped, never
REQUEST_SECONDS = 60.0  # `docker desktop stop` answers once Docker Desktop has stopped
PROGRAM = "Docker Desktop.exe"
WSL_HANDLER = "/proc/sys/fs/binfmt_misc/WSLInterop"
REGISTER_WSL_HANDLER = "echo ':WSLInterop:M::MZ::/init:PF' > /proc/sys/fs/binfmt_misc/register"
INSTALL = "install Docker Desktop (docker.com/products/docker-desktop)"
UPDATE = (
    "Clank needs the `docker desktop` command, which Docker Desktop has from 4.37: update Docker Desktop (Docker "
    "Engine alone has an adapter of its own: docker-engine)"
)


class DockerDesktop(DockerCli):
    """Docker Desktop, on Windows, macOS and Linux."""

    NAME = "docker-desktop"
    LABEL = "Docker Desktop"
    PLATFORMS = ("win32", "darwin", "linux")

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
        super().__init__(run, command, platform=platform, launch=launch, answer=answer, follow=follow)
        self._desktop: str | None = None

    @classmethod
    def find(cls) -> str | None:
        """The docker command on this machine."""
        return find_docker()

    def capabilities(self) -> list[Capability]:
        """Status, start and stop, through `docker desktop` when this Docker Desktop has it."""
        if self.command is None:
            return [Capability(name, False, INSTALL) for name in ("status", "start", "stop")]
        version = self._desktop_command()
        if version is None:
            return [Capability(name, False, UPDATE) for name in ("status", "start", "stop")]
        return [Capability(name, True, f"`docker desktop {name}` ({version})") for name in ("status", "start", "stop")]

    def status(self) -> PlatformStatus:
        """Docker Desktop's state; while it runs, its versions and its containers."""
        if self.command is None:
            return self._status("not installed", detail=INSTALL)
        if self._desktop_command() is None:
            return self._status("unsupported", detail=UPDATE)
        versions = self._docker("version", "--format", VERSIONS)
        if versions is None:
            state = _state(self._docker("desktop", "status", "--format", "json", timeout=STATUS_SECONDS))
            if state == "running":
                return self._status("starting", detail="Docker Desktop runs, but its engine does not answer yet")
            return self._status(state)
        version, engine = _versions(versions)
        return self._status("running", version=version, engine=engine, containers=self.containers())

    def request_start(self) -> None:
        """`docker desktop start --detach`; when it answers that Docker Desktop already runs while it is stopped,
        Docker Desktop's own program."""
        self._require()
        answer = self._docker("desktop", "start", "--detach", timeout=REQUEST_SECONDS)
        if answer is None:
            raise PlatformError("Docker Desktop did not take the request to start: open Docker Desktop to see why")
        if "already running" in answer.lower() and self.status().state == "stopped":
            program = self._program()
            if program is None or not self.launch([program]):
                raise PlatformError(
                    "Docker Desktop's command says it already runs, but it is stopped, and its own program could not "
                    "be started: open Docker Desktop"
                )

    def request_stop(self) -> None:
        """`docker desktop stop --detach`: every container stops with it."""
        self._require()
        if self._docker("desktop", "stop", "--detach", timeout=REQUEST_SECONDS) is None:
            raise PlatformError("Docker Desktop did not take the request to stop: quit it from its icon in the taskbar")

    def _target(self) -> list[str]:
        """On Linux, Docker Desktop's own context; elsewhere, the docker command's own choice."""
        return ["--context", CONTEXT] if self.platform == "linux" else []

    def _program(self) -> str | None:
        """Docker Desktop's own program: on Windows, two folders above its command (`resources/bin/docker.exe`); None
        elsewhere, for now."""
        if self.platform != "win32" or self.command is None:
            return None
        folders = PureWindowsPath(self.command).parents
        return str(folders[2] / PROGRAM) if len(folders) > 2 else None

    def after_start(self, log: Callable[[str], None]) -> None:
        """On Windows, put back WSL's handler for Windows programs if the start removed it while WSL ran."""
        if self.platform != "win32":
            return
        listed = self.run(["wsl.exe", "--list", "--running", "--quiet"]) or ""
        names = [line.strip() for line in listed.splitlines() if line.strip() and " " not in line.strip()]
        if not names:
            return
        check = ["wsl.exe", "-d", names[0], "-e", "sh", "-c", f"test -e {WSL_HANDLER}"]
        if self.run(check) is not None:
            return
        log(
            "WSL lost its handler for Windows programs (Docker Desktop removes it when it starts after WSL); "
            "putting it back"
        )
        self.run(["wsl.exe", "-d", names[0], "-u", "root", "-e", "sh", "-c", REGISTER_WSL_HANDLER])
        if self.run(check) is not None:
            log("WSL can run Windows programs again")
        else:
            log("it could not be put back: stop WSL (`wsl --shutdown`) and open it after Docker Desktop has started")

    def _require(self) -> None:
        if self.command is None:
            raise PlatformError(f"Docker Desktop is not installed: {INSTALL}")
        if self._desktop_command() is None:
            raise PlatformError(UPDATE)

    def _desktop_command(self) -> str | None:
        if self._desktop is None:
            answer = self._docker("desktop", "version", "--format", "json")
            if answer is not None:
                try:
                    self._desktop = str(json.loads(answer).get("version", "")) or "its version unknown"
                except (ValueError, AttributeError):
                    self._desktop = answer.strip() or "its version unknown"
        return self._desktop


def _state(answer: str | None) -> str:
    if answer is None:
        return "stopped"
    try:
        return str(json.loads(answer).get("Status", "unknown")).lower() or "unknown"
    except (ValueError, AttributeError):
        return "unknown"


def _versions(answer: str) -> tuple[str, str]:
    name, _, engine = answer.strip().partition("|")
    found = re.search(r"Docker Desktop (\S+)", name)
    return (found.group(1) if found else name.strip()), engine.strip()
