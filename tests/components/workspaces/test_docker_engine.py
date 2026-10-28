"""Design 0014 §2 (decision 0070): the Docker Engine adapter reads Docker Engine's state and never changes it. It asks
systemd first, which starts nothing, so a stopped engine is never woken: activating is starting, deactivating stopping,
inactive stopped, failed failed (its detail naming `systemctl status docker`). No command reaches the engine while
systemd says Docker's service is not active (a reading from the last second is reused): neither those it runs, nor
those it follows (a build, a setup), nor those it hands back for another to run (`docker exec`); each is refused with
the command that starts Docker. An active engine is asked `docker version`, its whole answer kept: "permission denied"
is no access, whose detail says how to join the docker group (equivalent to root on that computer) and to restart
Clank's service, or only to restart it when the account joined after the service started. Every command names the
system engine's socket, whatever DOCKER_HOST and the current context say. Without systemd, the engine is asked
directly. Where systemd knows no docker.service of the system's, Docker from the snap and rootless Docker are
unsupported, saying to install Docker Engine from Docker's packages. The capture tool asks what the adapter asks."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from clank.components.workspaces.adapters.docker_cli import INSPECT, LIMITS, MEMORY, STATS, TEMPLATE
from clank.components.workspaces.adapters.docker_engine import BOOT, SOCKET, SYSTEMD, VERSION, DockerEngine
from clank.components.workspaces.adapters.platform import PlatformError
from clank.components.workspaces.sandbox import ContainerSpec
from clank.kernel.processes import TIMEOUT_SECONDS, Answer
from tests.fakes.recorded import FIXTURES, RecordedProgram
from tools import capture_docker_engine as capture_tool

RECORDING = FIXTURES / "docker-engine" / "28.0.4"
ENGINE = ["-H", "unix:///var/run/docker.sock"]
SYSTEMD_ASKED = " ".join(SYSTEMD)
START = "sudo systemctl start docker"


class Machine:
    """systemd, the docker command and its engine as a test sets them: systemd's word for Docker's service (None: no
    systemd), each docker command's answer by its arguments (the engine named first), every docker command kept apart
    from systemd's."""

    def __init__(
        self,
        active: str | None = "active",
        load: str = "loaded",
        answers: Mapping[str, Answer] | None = None,
        unit_file: str = "enabled",
    ) -> None:
        self.active = active
        self.load = load
        self.answers = dict(answers or {})
        self.unit_file = unit_file  # systemd's word for whether Docker's service starts with the computer
        self.asked: list[list[str]] = []
        self.systemd = 0

    def answer(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        if Path(arguments[0]).name == "systemctl" and " ".join(arguments) == " ".join(BOOT):
            if self.active is None:
                return Answer(1, "", "System has not been booted with systemd as init system (PID 1). Can't operate.\n")
            return Answer(0, f"UnitFileState={self.unit_file}\n", "")
        if Path(arguments[0]).name == "systemctl":
            assert " ".join(arguments) == SYSTEMD_ASKED
            self.systemd += 1
            if self.active is None:
                return Answer(1, "", "System has not been booted with systemd as init system (PID 1). Can't operate.\n")
            return Answer(0, f"LoadState={self.load}\nActiveState={self.active}\n", "")
        self.asked.append(list(arguments))
        key = " ".join(arguments[1:])
        return self.answers.get(key, Answer(0, "", ""))

    def run(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        found = self.answer(arguments, timeout)
        return found.output if found.ok else None

    def follow(self, arguments: Sequence[str], line: Callable[[str], None], canceled: Callable[[], bool]) -> int | None:
        self.asked.append(list(arguments))
        return 0


class Clock:
    """A clock a test moves on."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def engine(
    program: Machine | RecordedProgram,
    *,
    command: str | None = "/usr/bin/docker",
    groups: Callable[[], tuple[bool, bool]] = lambda: (False, False),
    environ: Mapping[str, str] | None = None,
    clock: Callable[[], float] | None = None,
    account: Callable[[], str] = lambda: "ada",
) -> DockerEngine:
    follow = program.follow if isinstance(program, Machine) else (lambda *args, **kwargs: 0)
    return DockerEngine(
        program.run if isinstance(program, Machine) else program,
        command,
        platform="linux",
        answer=program.answer,
        follow=follow,
        groups=groups,
        environ=environ or {},
        clock=clock or Clock(),
        account=account,
    )


def test_a_user_outside_the_docker_group_is_told_how_to_join_it() -> None:
    program = RecordedProgram.load(RECORDING, state="no access")
    status = engine(program, groups=lambda: (False, False)).status()
    assert (status.state, status.running, status.containers) == ("no access", False, [])
    for said in ("`sudo usermod -aG docker $USER`", "log out and in again", "`clank stop`", "`clank work`", "root"):
        assert said in status.detail, said


def test_a_service_started_before_the_user_joined_the_docker_group_says_to_restart_it() -> None:
    program = RecordedProgram.load(RECORDING, state="no access")
    status = engine(program, groups=lambda: (True, False)).status()
    assert status.state == "no access"
    assert "usermod" not in status.detail, "the account is in the group already"
    assert "started before" in status.detail
    assert "`clank stop`" in status.detail
    assert "`clank work`" in status.detail


def test_a_stopped_engine_is_read_from_systemd_and_never_woken() -> None:
    program = RecordedProgram.load(RECORDING, state="stopped")
    status = engine(program).status()
    assert (status.state, status.running, status.engine, status.containers) == ("stopped", False, "", [])
    assert START in status.detail
    assert program.calls == [SYSTEMD_ASKED], "no docker command: socket activation would start the engine again"


@pytest.mark.parametrize(
    ("active", "said"),
    [("inactive", START), ("activating", "starting"), ("deactivating", "stopping"), ("failed", "systemctl status")],
)
def test_no_command_reaches_the_engine_while_systemd_says_it_is_not_active(active: str, said: str) -> None:
    machine = Machine(active)
    platform = engine(machine)
    spec = ContainerSpec(name="x", image="i", labels=(), networks=(("n", ""),), command=("true",), once=True)
    asks: list[Callable[[], object]] = [
        lambda: platform.container("clank-abc-x"),
        lambda: platform.build_image("i", "/image", {}, lambda text: None, lambda: False),
        lambda: platform.run_once(spec, lambda text: None, lambda: False),
        lambda: platform.exec_argv("clank-abc-x", ["opencode"], workdir="/workspace"),
        lambda: platform.start_container("clank-abc-x"),
        platform.limits,
    ]
    for ask in asks:
        with pytest.raises(PlatformError, match=said):
            ask()
    assert machine.asked == [], "nothing was sent to the engine"


def test_a_reading_of_systemd_from_the_last_second_is_reused() -> None:
    machine = Machine("active")
    clock = Clock()
    platform = engine(machine, clock=clock)
    platform.image_exists("i")
    platform.limits()
    assert machine.systemd == 1
    machine.active = "inactive"
    clock.now += 1.5
    with pytest.raises(PlatformError, match=START):
        platform.image_exists("i")
    assert machine.systemd == 2
    assert len(machine.asked) == 2, "the stop was seen before the third command"


def test_every_command_goes_to_the_system_engines_socket() -> None:
    elsewhere = {"DOCKER_HOST": "tcp://elsewhere:2375", "DOCKER_CONTEXT": "desktop-linux"}
    machine = Machine("active", answers={"context show": Answer(0, "desktop-linux\n", "")})
    platform = engine(machine, environ=elsewhere)
    platform.status()
    platform.image_exists("i")
    platform.build_image("i", "/image", {}, lambda text: None, lambda: False)
    handed = platform.exec_argv("clank-abc-x", ["opencode"], workdir="/workspace")
    assert machine.asked
    assert all(command[1:3] == ENGINE for command in machine.asked), machine.asked
    assert handed[:3] == ["/usr/bin/docker", *ENGINE]
    assert SOCKET == "unix:///var/run/docker.sock"


@pytest.mark.parametrize(
    ("active", "state"),
    [("activating", "starting"), ("deactivating", "stopping"), ("inactive", "stopped"), ("failed", "failed")],
)
def test_systemds_word_for_dockers_service_gives_its_state(active: str, state: str) -> None:
    machine = Machine(active)
    status = engine(machine).status()
    assert (status.state, status.running, status.containers) == (state, False, [])
    assert status.detail
    assert machine.asked == []


def test_a_failed_engine_says_where_to_read_why() -> None:
    status = engine(Machine("failed")).status()
    assert status.state == "failed"
    assert "`systemctl status docker`" in status.detail
    assert START in status.detail


def test_without_systemd_the_engine_is_asked_directly() -> None:
    running = Machine(None, answers={f"{' '.join(ENGINE)} version --format {VERSION}": Answer(0, "28.0.4\n", "")})
    status = engine(running).status()
    assert (status.state, status.version, status.engine) == ("running", "28.0.4", "28.0.4")
    down = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n"
    stopped = Machine(None, answers={f"{' '.join(ENGINE)} version --format {VERSION}": Answer(1, "\n", down)})
    found = engine(stopped).status()
    assert (found.state, found.detail) == ("stopped", down.strip()), "in Docker's own words"


@pytest.mark.parametrize(
    ("command", "environ", "context", "said"),
    [
        ("/snap/bin/docker", {}, "default", "snap"),
        ("/usr/bin/docker", {"DOCKER_HOST": "unix:///run/user/1000/docker.sock"}, "default", "rootless"),
        (
            "/usr/bin/docker",
            {"XDG_RUNTIME_DIR": "/run/user/1001", "DOCKER_HOST": "unix:///run/user/1001/docker.sock"},
            "default",
            "rootless",
        ),
        ("/usr/bin/docker", {}, "rootless", "rootless"),
    ],
)
def test_docker_from_the_snap_or_rootless_docker_is_unsupported_saying_how_to_install_docker_engine(
    command: str, environ: dict[str, str], context: str, said: str
) -> None:
    machine = Machine("inactive", load="not-found", answers={"context show": Answer(0, f"{context}\n", "")})
    platform = engine(machine, command=command, environ=environ)
    status = platform.status()
    assert (status.state, status.running) == ("unsupported", False)
    assert said in status.detail.lower()
    assert "docs.docker.com/engine/install" in status.detail
    with pytest.raises(PlatformError, match="engine/install"):
        platform.container("clank-abc-x")
    assert all(command[1:] == ["context", "show"] for command in machine.asked), "no command reaches an engine"


def test_where_systemd_knows_dockers_service_its_engine_is_used_whatever_the_context() -> None:
    answers = {
        "context show": Answer(0, "rootless\n", ""),
        f"{' '.join(ENGINE)} version --format {VERSION}": Answer(0, "28.0.4\n", ""),
    }
    machine = Machine("active", answers=answers)
    status = engine(machine, environ={"DOCKER_HOST": "unix:///run/user/1000/docker.sock"}).status()
    assert status.state == "running"
    assert ["context", "show"] not in [command[1:] for command in machine.asked]


def test_the_capture_tool_asks_what_the_adapter_asks() -> None:
    assert capture_tool.SYSTEMD == SYSTEMD
    assert capture_tool.BOOT == BOOT
    assert capture_tool.SOCKET == SOCKET
    assert (capture_tool.VERSION, capture_tool.TEMPLATE, capture_tool.INSPECT) == (VERSION, TEMPLATE, INSPECT)
    assert (capture_tool.LIMITS, capture_tool.STATS, capture_tool.MEMORY) == (LIMITS, STATS, MEMORY)


def test_memory_limits_are_read_as_recorded_and_an_answer_that_reached_no_engine_says_nothing() -> None:
    assert engine(RecordedProgram.load(RECORDING, state="running")).memory_limits() == (True, [])
    assert engine(RecordedProgram.load(RECORDING, state="running")).limits() == (4, 15983)
    denied = engine(RecordedProgram.load(RECORDING, state="no access"))
    assert denied.memory_limits() == (None, []), "recorded: exit 0, limit false, and permission denied on its errors"
    assert denied.limits() is None, "recorded: exit 0 and 0 0, and permission denied on its errors"


def test_the_running_engines_containers_use_is_read_as_recorded() -> None:
    rows = engine(RecordedProgram.load(RECORDING, state="running")).stats()
    assert [row["Name"] for row in rows] == ["web-dev", "toolbox-sandbox-017", "clank-0123456789ab-demo"]
    assert all({"CPUPerc", "MemUsage"} <= set(row) for row in rows)
