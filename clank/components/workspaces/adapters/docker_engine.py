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
- *Workspaces' networks.* Docker Engine gives this computer an address on each bridge network, which a container
  on it could reach, a server of this computer's listening there or on every address answering; a workspace's own
  network is made with the bridge's `com.docker.network.bridge.inhibit_ipv4`, so it has none (`inner_network_options`,
  design 0014 §4). The edge's network to the host keeps it: it is the edge's way out.
- *The agent's folder.* A folder Docker Engine mounts shows the host's own owners, and the agent works as user 1000 in
  its container, so a folder user 1000 may not read, write and enter (by its mode's owner, group and others' bits, or
  its POSIX access control list, as Linux decides) is refused, saying whose it is and how to let user 1000 write it
  (`agent_access`, design 0014 §4).
- *How it is set up, for `clank setup`* (`setup_state`, design 0028 §5): whether systemd starts Docker's service with
  the computer (its unit file's state, `systemctl show docker.service --property=UnitFileState`, which starts nothing),
  whether this account is in the docker group as the system lists it now, and the commands its owner runs with
  administrator rights: `sudo systemctl start docker` and `sudo systemctl enable docker` where systemd knows Docker's
  service, and `sudo usermod -aG docker` with this account's name (none when the system gives no name). Clank shows
  them, and runs them only in the owner's terminal, where sudo asks for the password itself; a client runs no other
  (`owner_commands`, which `clank setup` checks a command against before it runs it).
"""

import os
import re
import shlex
import struct
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from clank.components.workspaces.adapters.docker_cli import DockerCli, find_docker, words
from clank.components.workspaces.adapters.platform import (
    Follow,
    PlatformError,
    PlatformSetup,
    PlatformStatus,
    follow_command,
)
from clank.components.workspaces.sandbox import USER
from clank.kernel.adapters import Capability
from clank.kernel.processes import Launch, TimedAnswer, TimedRun, launch_program, run_answer

SOCKET = "unix:///var/run/docker.sock"  # the system engine's, which every command names
SYSTEMD = ("systemctl", "show", "docker.service", "--property=LoadState", "--property=ActiveState")
BOOT = ("systemctl", "show", "docker.service", "--property=UnitFileState")  # whether it starts with the computer
AT_BOOT = ("enabled", "enabled-runtime", "static", "generated", "alias")  # systemd's words: it starts with the computer
NOT_AT_BOOT = ("disabled", "masked", "masked-runtime", "indirect", "linked", "linked-runtime")
START_COMMAND = ("sudo", "systemctl", "start", "docker")  # what its owner runs (design 0028 §5)
BOOT_COMMAND = ("sudo", "systemctl", "enable", "docker")
JOIN_COMMAND = ("sudo", "usermod", "-aG", "docker")  # and this account's name
VERSION = "{{.Server.Version}}"
SYSTEMD_SECONDS = 5.0
FRESH_SECONDS = 1.0  # a reading of systemd this recent is reused before a command
CONTEXT_SECONDS = 5.0
RUNNING = ("active", "reloading")  # systemd's words for a service that runs
DENIED = re.compile(r"permission denied", re.IGNORECASE)
START = "sudo systemctl start docker"
HOST_OFF = {"com.docker.network.bridge.inhibit_ipv4": "true"}  # a bridge with no address of this computer's on it
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


def account_name() -> str:
    """This account's name, as the system lists it (`id -un`); empty off Linux and macOS."""
    if sys.platform == "win32":
        return ""
    import pwd

    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "")


def owner_commands(account: str) -> tuple[tuple[str, ...], ...]:
    """Every command Docker Engine's owner may be offered to run with administrator rights (design 0028 §5): its start,
    its start with the computer, and the docker group's for `account` alone (none without a name)."""
    return (START_COMMAND, BOOT_COMMAND, *(((*JOIN_COMMAND, account),) if account else ()))


AGENT_UID, AGENT_GID = (int(part) for part in USER.split(":"))  # the agent's user and group in its container
ACL = "system.posix_acl_access"  # where Linux keeps a file's POSIX access control list
READ, WRITE, ENTER = 4, 2, 1
OWNER_ENTRY, USER_ENTRY, GROUP_ENTRY, NAMED_GROUP_ENTRY, MASK_ENTRY, OTHER_ENTRY = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20


def granted(mode: int, owner: int, group: int, acl: bytes | None, uid: int = AGENT_UID, gid: int = AGENT_GID) -> int:
    """What a user (`uid`, in its group `gid`) may do with a file of this mode and owners, as Linux decides it: read
    (4), write (2) and enter (1), from its POSIX access control list when it has one, else its mode's owner, group and
    others' bits."""
    if uid == owner:
        return (mode >> 6) & 7
    entries = _acl_entries(acl)
    if not entries:
        return (mode >> 3) & 7 if gid == group else mode & 7
    mask = next((perms for tag, perms, _ in entries if tag == MASK_ENTRY), 7)
    named = [perms for tag, perms, id in entries if tag == USER_ENTRY and id == uid]
    if named:
        return named[0] & mask
    matching = [
        perms
        for tag, perms, id in entries
        if (tag == GROUP_ENTRY and group == gid) or (tag == NAMED_GROUP_ENTRY and id == gid)
    ]
    if matching:
        found = 0
        for perms in matching:
            found |= perms
        return found & mask
    return next((perms for tag, perms, _ in entries if tag == OTHER_ENTRY), mode & 7)


def _acl_entries(acl: bytes | None) -> list[tuple[int, int, int]]:
    """A POSIX access control list's entries (tag, permissions, id), as Linux stores them: version 2, then eight bytes
    each; none when there is no list."""
    if not acl or len(acl) < 4 or struct.unpack_from("<I", acl)[0] != 2:
        return []
    return [struct.unpack_from("<HHI", acl, offset) for offset in range(4, len(acl) - 7, 8)]


def refusal(folder: str, mode: int, owner: int, group: int, acl: bytes | None, owner_name: str) -> str:
    """Why the agent (user 1000 in its container) could not read, write and enter a folder of these owners and mode as
    Docker Engine mounts it, whose it is, and how to let it; empty when it can (design 0014 §4)."""
    have = granted(mode, owner, group, acl)
    missing = [word for bit, word in ((READ, "read"), (WRITE, "write"), (ENTER, "enter")) if not have & bit]
    if not missing:
        return ""
    lacking = missing[0] if len(missing) == 1 else f"{', '.join(missing[:-1])} or {missing[-1]}"
    whose = f"{owner_name}'s (user {owner}" if owner_name else f"user {owner}'s ("
    quoted = shlex.quote(folder)
    return (
        f"the agent works as user {AGENT_UID} in its container, and {folder} is {whose}, mode {mode & 0o777:o}): user "
        f"{AGENT_UID} may not {lacking} it. Let it, and what you make in it later: `setfacl -R -m "
        f"u:{AGENT_UID}:rwX,d:u:{AGENT_UID}:rwX {quoted}`, or `chmod -R a+rwX {quoted}` (every user of this computer "
        "may then change it)"
    )


def folder_access(folder: str) -> str:
    """`refusal` for a folder of this computer, from its owners, its mode and its access control list; empty off
    Linux."""
    if sys.platform != "linux":
        return ""
    import pwd

    try:
        found = os.stat(folder)
    except OSError as error:
        return f"{folder} cannot be read: {error}"
    try:
        acl: bytes | None = os.getxattr(folder, ACL)
    except OSError:
        acl = None
    try:
        name = pwd.getpwuid(found.st_uid).pw_name
    except KeyError:
        name = ""
    return refusal(folder, found.st_mode, found.st_uid, found.st_gid, acl, name)


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
        account: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(run, command, platform=platform, launch=launch, answer=answer, follow=follow)
        self.groups = groups
        self.environ = environ
        self.clock = clock
        self.account = account  # this account's name; None: as the system lists it when asked (`account_name`)
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

    def agent_access(self, folder: str) -> str:
        """Why the agent could not use this folder as Docker Engine mounts it, with the host's own owners (design 0014
        §4); empty when it can."""
        return folder_access(folder)

    def setup_state(self) -> PlatformSetup:
        """Whether systemd starts Docker's service with the computer, whether this account is in the docker group as
        the system lists it now, and the commands its owner runs to start it, to start it with the computer and to
        join the group (design 0028 §5); none when it is not installed, no systemctl command where systemd knows no
        Docker service of the system's, and no join where the system gives no name for this account."""
        if self.command is None:
            return PlatformSetup()
        found = self.answer(list(BOOT), timeout=SYSTEMD_SECONDS)
        values = dict(line.split("=", 1) for line in found.output.splitlines() if "=" in line) if found.ok else {}
        word = values.get("UnitFileState", "").strip()
        at_boot = True if word in AT_BOOT else False if word in NOT_AT_BOOT else None
        listed, _ = self.groups()
        service, _ = self._reading()
        systemd = service is not None and service.known
        account = self.account() if self.account is not None else account_name()
        return PlatformSetup(
            at_boot=at_boot,
            in_group=listed,
            start=START_COMMAND if systemd else (),
            boot=BOOT_COMMAND if systemd else (),
            join=(*JOIN_COMMAND, account) if account else (),
        )

    def inner_network_options(self) -> dict[str, str]:
        """A workspace's own network gives this computer no address on it (the bridge's `inhibit_ipv4`), so nothing
        listening on this computer answers from inside it (design 0014 §4)."""
        return dict(HOST_OFF)

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
