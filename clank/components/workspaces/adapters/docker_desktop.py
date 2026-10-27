"""The Docker Desktop adapter: Docker Desktop through its own commands (design 0002 §2.9, §2.10).

Docker Desktop 4.37 and newer has the `docker desktop` command (start, stop, status), which this adapter needs; with
an older one, or with Docker Engine alone (a later adapter), it says so. The status asks the engine first: `docker
version` (Docker Desktop's version and its engine's), then `docker ps --all` with a template that gives Clank's labels
exactly; the list of every label is read only for the labels' names, because a value may hold the comma that separates
them. Only when the engine does not answer is `docker desktop status` asked, with a short time limit, to tell a Docker
Desktop that is starting or stopping from a stopped one: stopped, Docker Desktop 4.85 never answers it (recorded on
2026-10-13). A start or a stop is asked with `--detach`, and the operation that asked waits for the engine; the stop
answers only once Docker Desktop has stopped (13 seconds on 4.85), so both are given a minute. After `docker desktop
stop`, Docker Desktop 4.85's `docker desktop start` answers that Docker Desktop already runs and starts nothing; when
that happens to a stopped Docker Desktop, its own program is started instead, as the Start menu starts it (on Windows,
`Docker Desktop.exe`, two folders above its command). On Windows, Docker Desktop started after WSL removes WSL's
handler for Windows programs (PROTOTYPE.md), so after a start, if WSL runs and the handler is gone, the adapter
registers it again and says so. Its container commands (design 0004 §3) are Docker's own: `docker info` for the
CPUs and memory its engine has, `docker build`, `docker network`, `docker run` (then `docker network connect` for a
container's other networks), `docker run --rm` followed line by line for a workspace's setup, `docker container
inspect`, `start`, `stop`, `rm`, `volume rm`, and `docker exec` for a terminal. The files an agent's start writes go in
one `docker exec` of a few lines of Python reading them from its input (`PUT_FILES`; each exec is a fifth of a second
on Windows, and nine of them made most of the agent's wait in VS Code, 2026-10-26), one by one in a container without
Python.
"""

import json
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from clank.components.workspaces.adapters.platform import (
    LABELS,
    Container,
    ContainerPlatform,
    Follow,
    PlatformError,
    PlatformStatus,
    follow_command,
)
from clank.components.workspaces.sandbox import ContainerSpec, joined, run_arguments
from clank.kernel.adapters import Capability
from clank.kernel.processes import TIMEOUT_SECONDS, Answer, Launch, TimedAnswer, TimedRun, launch_program, run_answer

TEMPLATE = (
    '{"id":{{json .ID}},"name":{{json .Names}},"image":{{json .Image}},"state":{{json .State}},'
    '"status":{{json .Status}},"clank.home":{{json (.Label "clank.home")}},'
    '"clank.component":{{json (.Label "clank.component")}},"clank.record":{{json (.Label "clank.record")}},'
    '"clank.ports":{{json (.Label "clank.ports")}},"clank.proxy":{{json (.Label "clank.proxy")}}}'
)
# Each container's labels as Docker's own map: `docker ps` joins them with commas, which a value may also hold.
INSPECT = '{"id":{{json .Id}},"labels":{{json .Config.Labels}}}'
VERSIONS = "{{.Server.Platform.Name}}|{{.Server.Version}}"
LIMITS = "{{.NCPU}} {{.MemTotal}}"
ONE = (
    '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},"state":{{json .State.Status}},'
    '"labels":{{json .Config.Labels}}}'
)
RUN_SECONDS = 120.0
# Several files written in one `docker exec` (`put_files`): each [path, text] of the JSON list on its input, its folder
# made, its text as UTF-8 with its line ends as given.
PUT_FILES = (
    "import json, os, sys\n"
    "for path, text in json.loads(sys.stdin.buffer.read().decode('utf-8')):\n"
    "    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)\n"
    "    with open(path, 'w', encoding='utf-8', newline='') as file:\n"
    "        file.write(text)\n"
)
NOT_FOUND = (126, 127)  # `docker exec`'s status when the container cannot run the program (python3 is not there)
MISSING = re.compile(r"no such (container|volume|network)|not found|is not connected", re.IGNORECASE)
JOINED = re.compile(r"already exists in network", re.IGNORECASE)
STATUS_SECONDS = 2.0  # running, `docker desktop status` answers at once; stopped, never
REQUEST_SECONDS = 60.0  # `docker desktop stop` answers once Docker Desktop has stopped
PROGRAM = "Docker Desktop.exe"
WSL_HANDLER = "/proc/sys/fs/binfmt_misc/WSLInterop"
REGISTER_WSL_HANDLER = "echo ':WSLInterop:M::MZ::/init:PF' > /proc/sys/fs/binfmt_misc/register"
INSTALL = "install Docker Desktop (docker.com/products/docker-desktop)"
UPDATE = (
    "Clank needs the `docker desktop` command, which Docker Desktop has from 4.37: update Docker Desktop (Docker "
    "Engine alone is supported by a later adapter)"
)


def find_docker(
    which: Callable[[str], str | None] = shutil.which,
    environ: Mapping[str, str] = os.environ,
    platform: str = sys.platform,
) -> str | None:
    """The docker command: on the PATH, else in Docker Desktop's own folder; None when neither has it."""
    found = which("docker")
    if found:
        return found
    for candidate in _desktop_commands(environ, platform):
        if candidate.is_file():
            return str(candidate)
    return None


def _desktop_commands(environ: Mapping[str, str], platform: str) -> list[Path]:
    if platform == "win32":
        bases = [
            (environ.get("LOCALAPPDATA"), ("Programs", "DockerDesktop")),
            (environ.get("ProgramFiles"), ("Docker", "Docker")),
        ]
        return [Path(root, *parts, "resources", "bin", "docker.exe") for root, parts in bases if root]
    if platform == "darwin":
        return [Path("/Applications/Docker.app/Contents/Resources/bin/docker")]
    return []


class DockerDesktop(ContainerPlatform):
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
        listed = self._docker("ps", "--all", "--no-trunc", "--format", TEMPLATE) or ""
        rows = [json.loads(line) for line in listed.splitlines() if line.strip()]
        labels = self._label_names([row["id"] for row in rows])
        return self._status("running", version=version, engine=engine, containers=_containers(rows, labels))

    def _label_names(self, ids: list[str]) -> dict[str, list[str]]:
        """Each container's label names, from Docker's own map of them; a container gone since it was listed (which
        fails the inspection of them all) has none, and the others are asked one at a time."""
        if not ids:
            return {}
        together = self._docker("container", "inspect", "--format", INSPECT, *ids)
        answers = (
            [together]
            if together is not None
            else [self._docker("container", "inspect", "--format", INSPECT, id) for id in ids]
        )
        found: dict[str, list[str]] = {}
        for answer in answers:
            for line in (answer or "").splitlines():
                if line.strip():
                    raw = json.loads(line)
                    found[raw["id"]] = sorted(raw.get("labels") or {})
        return found

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

    def limits(self) -> tuple[int, int] | None:
        """The CPUs and memory Docker's engine has (on Docker Desktop, its virtual machine's)."""
        found = (self._docker("info", "--format", LIMITS) or "").split()
        if len(found) != 2 or not all(part.isdigit() for part in found):
            return None
        return int(found[0]), int(found[1]) // (1024 * 1024)

    def image_exists(self, tag: str) -> bool:
        """Whether `docker image inspect` finds it."""
        return self._answer("image", "inspect", "--format", "{{.Id}}", tag).ok

    def build_image(
        self,
        tag: str,
        folder: str,
        labels: Mapping[str, str],
        line: Callable[[str], None],
        canceled: Callable[[], bool],
        args: Mapping[str, str] | None = None,
    ) -> int | None:
        """`docker build`, with its build arguments, its plain progress followed line by line."""
        marks = [part for key, value in labels.items() for part in ("--label", f"{key}={value}")]
        given = [part for key, value in (args or {}).items() for part in ("--build-arg", f"{key}={value}")]
        argv = [self.command or "docker", "build", "--progress", "plain", "--tag", tag, *marks, *given, folder]
        return self.follow(argv, line, canceled)

    def ensure_network(self, name: str, *, internal: bool, labels: Mapping[str, str]) -> None:
        """`docker network create`, unless `docker network inspect` finds it."""
        if self._answer("network", "inspect", "--format", "{{.Name}}", name).ok:
            return
        marks = [part for key, value in labels.items() for part in ("--label", f"{key}={value}")]
        made = self._answer("network", "create", *(["--internal"] if internal else []), *marks, name)
        if not made.ok:
            raise PlatformError(f"the network {name} could not be made: {_words(made)}")

    def join_network(self, network: str, container: str, alias: str) -> None:
        """`docker network connect --alias`."""
        joined_it = self._answer("network", "connect", "--alias", alias, network, container)
        if not joined_it.ok and not JOINED.search(joined_it.errors):
            raise PlatformError(f"{container} could not join {network}: {_words(joined_it)}")

    def leave_network(self, network: str, container: str) -> None:
        """`docker network disconnect --force`."""
        self._gone_or_done(self._answer("network", "disconnect", "--force", network, container), network)

    def remove_network(self, name: str) -> None:
        """`docker network rm`."""
        self._gone_or_done(self._answer("network", "rm", name), name)

    def container(self, name: str) -> Container | None:
        """`docker container inspect`, or None when it is not there."""
        found = self._answer("container", "inspect", "--format", ONE, name)
        if not found.ok:
            return None
        raw = json.loads(found.output)
        labels = raw.get("labels") or {}
        return Container(
            id=raw["id"],
            name=str(raw["name"]).lstrip("/"),
            image=raw["image"],
            state=raw["state"],
            clank={label: labels[label] for label in LABELS if labels.get(label)},
            label_keys=sorted(labels),
        )

    def run_container(self, spec: ContainerSpec) -> None:
        """`docker run`, then `docker network connect` for each of its other networks."""
        ran = self._answer(*run_arguments(spec), timeout=RUN_SECONDS)
        if not ran.ok:
            raise PlatformError(f"{spec.name} could not start: {_words(ran)}")
        for network, alias in joined(spec):
            joined_it = self._answer("network", "connect", *(["--alias", alias] if alias else []), network, spec.name)
            if not joined_it.ok:
                raise PlatformError(f"{spec.name} could not join {network}: {_words(joined_it)}")

    def run_once(self, spec: ContainerSpec, line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
        """`docker run --rm` in the foreground, its output followed line by line; canceling it removes the container."""
        status = self.follow([self.command or "docker", *run_arguments(spec)], line, canceled)
        if status is None:
            self._answer("rm", "--force", spec.name)  # a canceled run's container goes too
        return status

    def start_container(self, name: str) -> None:
        """`docker start`."""
        started = self._answer("start", name, timeout=RUN_SECONDS)
        if not started.ok:
            raise PlatformError(f"{name} could not start: {_words(started)}")

    def stop_container(self, name: str, seconds: int) -> None:
        """`docker stop`."""
        self._gone_or_done(self._answer("stop", "--time", str(seconds), name, timeout=seconds + RUN_SECONDS), name)

    def remove_container(self, name: str) -> None:
        """`docker rm --force`."""
        self._gone_or_done(self._answer("rm", "--force", name), name)

    def remove_volume(self, name: str) -> None:
        """`docker volume rm`."""
        self._gone_or_done(self._answer("volume", "rm", name), name)

    def put_file(self, name: str, path: str, text: str) -> None:
        """`docker exec --interactive` of a shell that writes what it reads, as the container's own user."""
        script = 'mkdir -p "$(dirname "$1")" && cat > "$1"'
        put = self._answer("exec", "--interactive", name, "sh", "-c", script, "sh", path, input=text.encode("utf-8"))
        if not put.ok:
            raise PlatformError(f"{path} could not be written in {name}: {_words(put)}")

    def put_files(self, name: str, files: Sequence[tuple[str, str]]) -> None:
        """One `docker exec --interactive` of Python that writes the files it reads, as the container's own user; one
        by one (`put_file`) in a container without Python."""
        given = json.dumps([[path, text] for path, text in files]).encode("utf-8")
        put = self._answer("exec", "--interactive", name, "python3", "-c", PUT_FILES, input=given)
        if put.status in NOT_FOUND:
            super().put_files(name, files)
        elif not put.ok:
            paths = ", ".join(path for path, _ in files)
            raise PlatformError(f"{paths} could not be written in {name}: {_words(put)}")

    def run_in(
        self, name: str, argv: Sequence[str], *, workdir: str, input: bytes | None = None, timeout: float = 30.0
    ) -> Answer:
        """`docker exec --interactive` (no terminal), its whole answer."""
        return self._answer("exec", "--interactive", "--workdir", workdir, name, *argv, timeout=timeout, input=input)

    def exec_argv(
        self,
        name: str,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None = None,
        terminal: bool = True,
    ) -> list[str]:
        """`docker exec`, with a terminal unless told not to, as the container's own user."""
        given = [part for key, value in (env or {}).items() for part in ("--env", f"{key}={value}")]
        tty = ["--tty"] if terminal else []
        return [self.command or "docker", "exec", "--interactive", *tty, *given, "--workdir", workdir, name, *argv]

    def _gone_or_done(self, answer: Answer, name: str) -> None:
        if not answer.ok and not MISSING.search(answer.errors):
            raise PlatformError(f"Docker refused for {name}: {_words(answer)}")

    def _answer(self, *arguments: str, timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        return self.answer([self.command or "docker", *arguments], timeout=timeout, input=input)

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

    def _docker(self, *arguments: str, timeout: float = TIMEOUT_SECONDS) -> str | None:
        return self.run([self.command or "docker", *arguments], timeout=timeout)

    def _status(self, state: str, **values: object) -> PlatformStatus:
        return PlatformStatus.model_validate({"adapter": self.NAME, "label": self.LABEL, "state": state, **values})


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


def _containers(rows: list[dict[str, Any]], labels: dict[str, list[str]]) -> list[Container]:
    containers = []
    for raw in rows:
        containers.append(
            Container(
                id=raw["id"],
                name=raw["name"],
                image=raw["image"],
                state=raw["state"],
                status=raw.get("status", ""),
                clank={label: raw[label] for label in LABELS if raw.get(label)},
                label_keys=labels.get(raw["id"], []),
            )
        )
    return containers


def _words(answer: Answer) -> str:
    """What Docker said of a refusal: its errors, else its output, on one line."""
    said = (answer.errors or answer.output).strip() or f"exit {answer.status}"
    return " ".join(said.split())
