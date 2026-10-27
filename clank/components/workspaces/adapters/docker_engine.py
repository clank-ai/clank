"""The Docker Engine adapter, for Linux (design 0014 §2, decision 0070): Docker Engine, the system's service, whose
state Clank reads and never changes.

- *systemd first.* When systemd knows Docker's service, its state is read there (`systemctl show docker.service`, its
  load and active states), which any user may ask and which starts nothing: activating is starting, deactivating
  stopping, inactive stopped, failed failed (its detail names `systemctl status docker`, which says why). Docker's
  packages start the engine through systemd's socket activation, so a docker command sent to a stopped engine could
  start it again, and Clank reads Docker's state every 5 seconds.
- *No command reaches a stopped engine.* Every command to the engine first asks systemd whether Docker's service is
  active (`_ready`; a reading from the last second is reused): the commands the adapter runs, those it follows (a
  build, a setup) and those it hands back for another to run (`docker exec`). When it is not active, nothing is sent,
  and the adapter refuses with the command that starts Docker.
- *Then the engine.* An active engine is asked `docker version`, its whole answer kept. Running gives its version and
  its containers, through the base. "permission denied" on Docker's socket gives the state *no access*, whose detail
  says what to do (`docker_group` tells the two cases apart): join the docker group, which is equivalent to root on
  that computer, log out and in again, and restart Clank's service; or, when the account is in the group but this
  process is not (a process keeps the groups it started with, and `clank work` reuses the service), restart the service
  once logged in again. Any other refusal gives *stopped*, in Docker's words. Without systemd, the engine is asked
  directly.
- *One engine, named.* Every command names the system engine's socket (`-H unix:///var/run/docker.sock`), which wins
  over `DOCKER_HOST` and the current context: Docker Desktop started later, a remote context or a `DOCKER_HOST` never
  gets Clank's commands.
- *Never a start or a stop.* Its start and stop capabilities are false, each naming the command the owner runs (`sudo
  systemctl start docker`; `sudo systemctl stop docker.socket docker.service`, since the service stopped alone is
  started again by its socket); asked anyway, it refuses in those words. Clank never runs sudo.
- *Docker from the snap, and rootless Docker, are unsupported* where systemd knows no `docker.service` of the
  system's: the snap's engine cannot mount the hidden folders of the home folder, and rootless Docker maps user ids.
  The snap's is told by its command's place (under `/snap/`); rootless Docker by `DOCKER_HOST` naming a socket in the
  user's runtime folder, or by a current context named `rootless` (`docker context show`, which reaches no engine).
  Where the system's own service exists too, its engine is used whatever the context, since every command names its
  socket.
"""

import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from clank.components.workspaces.adapters.docker_cli import DockerCli, find_docker, words
from clank.components.workspaces.adapters.platform import Follow, PlatformError, PlatformStatus, follow_command
from clank.kernel.adapters import Capability
from clank.kernel.processes import Launch, TimedAnswer, TimedRun, launch_program, run_answer

SOCKET = "unix:///var/run/docker.sock"  # the system engine's, which every command names
SYSTEMD = ("systemctl", "show", "docker.service", "--property=LoadState", "--property=ActiveState")
VERSION = "{{.Server.Version}}"
SYSTEMD_SECONDS = 5.0
FRESH_SECONDS = 1.0  # a reading of systemd this recent is reused before a command
CONTEXT_SECONDS = 5.0
RUNNING = ("active", "reloading")  # systemd's words for a service that runs
DENIED = re.compile(r"permission denied", re.IGNORECASE)
START = "sudo systemctl start docker"
STOP = "sudo systemctl stop docker.socket docker.service"
INSTALL = (
    "install Docker Engine from Docker's own packages (docs.docker.com/engine/install); Docker Desktop for Linux is "
    "made for x86-64 only"
)
SNAP = (
    "Docker from the snap is not supported: its engine cannot mount the hidden folders of your home folder. Install "
    "Docker Engine from Docker's own packages (docs.docker.com/engine/install)"
)
ROOTLESS = (
    "rootless Docker is not supported: it maps the user ids in containers. Install Docker Engine from Docker's own "
    "packages (docs.docker.com/engine/install), the system's service"
)
JOIN = (
    "this account may not use Docker: join the docker group (`sudo usermod -aG docker $USER`), log out and in again, "
    "then restart Clank's service (`clank stop`, then `clank work`). Anyone in the docker group can act as root on "
    "this computer (docs.docker.com/engine/install/linux-postinstall)"
)
RESTART = (
    "this account is in the docker group, but Clank's service started before it joined and keeps the groups it "
    "started with: log out and in again if you have not yet, then restart Clank's service (`clank stop`, then "
    "`clank work`)"
)


@dataclass(frozen=True)
class Service:
    """What systemd says of Docker's service: its load state (loaded, not-found, masked) and its active state."""

    load: str
    active: str

    @property
    def known(self) -> bool:
        """Whether systemd knows a `docker.service` of the system's."""
        return self.load not in ("", "not-found")


def docker_service(answer: TimedAnswer = run_answer) -> Service | None:
    """What systemd says of Docker's service, which starts nothing; None without systemd (not installed, or not the
    system's manager)."""
    found = answer(list(SYSTEMD), timeout=SYSTEMD_SECONDS)
    if not found.ok:
        return None
    values = dict(line.split("=", 1) for line in found.output.splitlines() if "=" in line)
    return Service(values.get("LoadState", "").strip(), values.get("ActiveState", "").strip())


def from_systemd(service: Service) -> tuple[str, str]:
    """The state of a Docker service that does not run, and what to do, in systemd's words."""
    if service.active == "activating":
        return "starting", "systemd is starting Docker's service: wait a moment (`systemctl status docker` says more)"
    if service.active == "deactivating":
        return "stopping", "systemd is stopping Docker's service"
    if service.active == "failed":
        return "failed", f"Docker's service failed: `systemctl status docker` says why; `{START}` starts it again"
    if service.active == "inactive":
        masked = " (it is masked: `sudo systemctl unmask docker.service docker.socket` first)"
        return "stopped", (
            f"start it with `{START}`{masked if service.load == 'masked' else ''}; Clank never starts or stops "
            "Docker Engine"
        )
    said = service.active or "in no state systemd names"
    return service.active or "unknown", f"systemd says Docker's service is {said}: `systemctl status docker` says more"


def rootless_host(environ: Mapping[str, str]) -> bool:
    """Whether `DOCKER_HOST` names a socket in the user's runtime folder, as rootless Docker sets it."""
    host = environ.get("DOCKER_HOST", "")
    if not host.startswith("unix://"):
        return False
    path = host.removeprefix("unix://")
    folders = [environ.get("XDG_RUNTIME_DIR", ""), "/run/user"]
    return any(folder and path.startswith(folder.rstrip("/") + "/") for folder in folders)


def docker_group() -> tuple[bool, bool]:
    """Whether this account is in the docker group as the system lists it now, and whether this process is: a process
    keeps the groups it started with."""
    if sys.platform == "win32":
        return False, False
    import grp
    import pwd

    try:
        group = grp.getgrnam("docker").gr_gid
    except KeyError:
        return False, False
    account = pwd.getpwuid(os.getuid())
    listed = group in os.getgrouplist(account.pw_name, account.pw_gid)
    return listed, group == os.getegid() or group in os.getgroups()


class DockerEngine(DockerCli):
    """Docker Engine on Linux, the system's service: its state read from systemd and the engine, never changed."""

    NAME = "docker-engine"
    LABEL = "Docker Engine"
    PLATFORMS = ("linux",)

    def __init__(
        self,
        run: TimedRun,
        command: str | None,
        *,
        platform: str = sys.platform,
        launch: Launch = launch_program,
        answer: TimedAnswer = run_answer,
        follow: Follow = follow_command,
        groups: Callable[[], tuple[bool, bool]] = docker_group,
        environ: Mapping[str, str] = os.environ,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(run, command, platform=platform, launch=launch, answer=answer, follow=follow)
        self.groups = groups
        self.environ = environ
        self.clock = clock
        self._read: tuple[float, Service | None, str] | None = None  # when, what systemd said, why unsupported

    @classmethod
    def find(cls) -> str | None:
        """The docker command on this machine."""
        return find_docker()

    def capabilities(self) -> list[Capability]:
        """Its status, read from systemd and the engine; never a start or a stop, each naming the owner's command."""
        if self.command is None:
            return [Capability(name, False, INSTALL) for name in ("status", "start", "stop")]
        return [
            Capability("status", True, "`systemctl show docker.service`, then `docker version` on the system engine"),
            Capability("start", False, f"`{START}`: Docker Engine is the system's service, which Clank never starts"),
            Capability(
                "stop",
                False,
                f"`{STOP}`: Docker Engine is the system's service, which Clank never stops (stopped alone, the "
                "service is started again by its socket)",
            ),
        ]

    def status(self) -> PlatformStatus:
        """Docker Engine's state, from systemd first; while it runs, its version and its containers."""
        if self.command is None:
            return self._status("not installed", detail=INSTALL)
        service, unsupported = self._reading()
        if service is not None and service.known and service.active not in RUNNING:
            state, detail = from_systemd(service)
            return self._status(state, detail=detail)
        if unsupported:
            return self._status("unsupported", detail=unsupported)
        asked = self._answer("version", "--format", VERSION)
        if asked.ok:
            version = asked.output.strip()
            return self._status("running", version=version, engine=version, containers=self.containers())
        if DENIED.search(asked.errors):
            listed, process = self.groups()
            return self._status("no access", detail=RESTART if listed and not process else JOIN)
        return self._status("stopped", detail=words(asked))

    def request_start(self) -> None:
        """Refused: Clank never starts the system's service; the owner runs the command."""
        if self.command is None:
            raise PlatformError(f"Docker Engine is not installed: {INSTALL}")
        raise PlatformError(f"Clank never starts Docker Engine, the system's service: start it with `{START}`")

    def request_stop(self) -> None:
        """Refused: Clank never stops the system's service; the owner runs the command."""
        if self.command is None:
            raise PlatformError(f"Docker Engine is not installed: {INSTALL}")
        raise PlatformError(
            f"Clank never stops Docker Engine, the system's service: stop it with `{STOP}` (stopped alone, the "
            "service is started again by its socket)"
        )

    def _target(self) -> list[str]:
        """The system engine's socket, named on every command."""
        return ["-H", SOCKET]

    def _ready(self) -> None:
        """Refuse, sending nothing, while systemd says Docker's service is not active, or for a Docker Clank does not
        support; without systemd, the engine is asked."""
        service, unsupported = self._reading()
        if service is not None and service.known:
            if service.active not in RUNNING:
                state, detail = from_systemd(service)
                raise PlatformError(f"Docker Engine is {state}: {detail}")
            return
        if unsupported:
            raise PlatformError(unsupported)

    def _reading(self) -> tuple[Service | None, str]:
        """What systemd says of Docker's service, and why this Docker is unsupported (empty: it is not, or systemd
        knows the system's service), read again once the last reading is a second old."""
        now = self.clock()
        if self._read is None or now - self._read[0] >= FRESH_SECONDS:
            service = docker_service(self.answer)
            unsupported = "" if service is not None and service.known else self._unsupported()
            self._read = (now, service, unsupported)
        return self._read[1], self._read[2]

    def _unsupported(self) -> str:
        """Why this Docker is one Clank does not support: the snap's (its command under /snap/), or rootless Docker (its
        socket in the user's runtime folder, or the current context's name); empty otherwise."""
        if (self.command or "").startswith("/snap/"):
            return SNAP
        if rootless_host(self.environ):
            return ROOTLESS
        current = self.run([self.command or "docker", "context", "show"], timeout=CONTEXT_SECONDS)
        return ROOTLESS if (current or "").strip() == "rootless" else ""
