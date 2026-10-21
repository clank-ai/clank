"""Design 0002 §2.10 and PROTOTYPE.md: the Docker Desktop adapter finds the docker command on the PATH, else in
Docker Desktop's own folder; without `docker desktop` (Docker Desktop older than 4.37) it says to update and refuses to
start or stop; a start that Docker Desktop's command says it need not make (it believes Docker Desktop runs) starts
Docker Desktop's own program when Docker Desktop is stopped, leaves a Docker Desktop that is starting alone, and says
what to do when the program cannot start; and on Windows, after a start, it puts back WSL's handler for Windows
programs when Docker Desktop removed it, leaves a present one alone, and asks nothing of WSL elsewhere."""

import json
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath

import pytest

from clank.components.workspaces.adapters.docker_desktop import INSPECT, TEMPLATE, VERSIONS, DockerDesktop, find_docker
from clank.components.workspaces.adapters.platform import PlatformError

RUNNING = "wsl.exe --list --running --quiet"
CHECK = "wsl.exe -d Ubuntu-22.04 -e sh -c test -e /proc/sys/fs/binfmt_misc/WSLInterop"
REGISTER = (
    "wsl.exe -d Ubuntu-22.04 -u root -e sh -c echo ':WSLInterop:M::MZ::/init:PF' > /proc/sys/fs/binfmt_misc/register"
)
COMMAND = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
PROGRAM = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
ALREADY = "Docker Desktop is already running\n"


class Answers:
    """Commands answered from a table (their output, or None when they fail), each call kept; `after` says what a
    command changes in the table. A command given by its path is matched by its name."""

    def __init__(self, table: dict[str, str | None], after: dict[str, dict[str, str | None]] | None = None) -> None:
        self.table = dict(table)
        self.after = after or {}
        self.calls: list[str] = []

    def __call__(self, arguments: Sequence[str], timeout: float = 15) -> str | None:
        first = arguments[0]
        name = PureWindowsPath(first).stem if "\\" in first or "/" in first else first
        command = " ".join([name, *arguments[1:]])
        self.calls.append(command)
        answer = self.table.get(command)
        self.table.update(self.after.get(command, {}))
        return answer


class Launches:
    """Applications started, each kept; whether they start."""

    def __init__(self, starts: bool = True) -> None:
        self.starts = starts
        self.launched: list[list[str]] = []

    def __call__(self, arguments: Sequence[str]) -> bool:
        self.launched.append(list(arguments))
        return self.starts


def test_the_command_is_found_on_the_path_first_then_in_docker_desktops_folder(tmp_path: Path) -> None:
    on_path = find_docker(which=lambda name: "/usr/bin/docker", environ={}, platform="linux")
    assert on_path == "/usr/bin/docker"
    program = tmp_path / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
    program.parent.mkdir(parents=True)
    program.write_text("", encoding="utf-8")
    found = find_docker(which=lambda name: None, environ={"LOCALAPPDATA": str(tmp_path)}, platform="win32")
    assert found == str(program)
    assert find_docker(which=lambda name: None, environ={}, platform="win32") is None


def test_without_the_docker_desktop_command_it_says_to_update_and_refuses_to_start_or_stop() -> None:
    platform = DockerDesktop(Answers({}), "docker")
    status = platform.status()
    assert (status.state, status.running) == ("unsupported", False)
    assert "4.37" in status.detail
    supported = {capability.name: capability.supported for capability in platform.capabilities()}
    assert (supported["start"], supported["stop"]) == (False, False)
    with pytest.raises(PlatformError, match=r"4\.37"):
        platform.request_start()
    with pytest.raises(PlatformError, match=r"4\.37"):
        platform.request_stop()


def desktop(status: str | None) -> Answers:
    """Docker Desktop's command answering that it already runs, while its engine does not answer, and its own status
    (None: no answer, as when it is stopped)."""
    return Answers(
        {
            "docker desktop version --format json": '{"version":"v0.4.3"}\n',
            "docker desktop start --detach": ALREADY,
            f"docker version --format {VERSIONS}": None,
            "docker desktop status --format json": status,
        }
    )


def test_a_start_its_command_says_it_need_not_make_starts_docker_desktops_own_program_when_it_is_stopped() -> None:
    launches = Launches()
    DockerDesktop(desktop(None), COMMAND, platform="win32", launch=launches).request_start()
    assert launches.launched == [[PROGRAM]]


def test_a_docker_desktop_that_is_starting_is_left_to_start() -> None:
    launches = Launches()
    DockerDesktop(desktop('{"Status": "starting"}\n'), COMMAND, platform="win32", launch=launches).request_start()
    assert launches.launched == []


def test_a_stopped_docker_desktop_whose_program_cannot_start_says_what_to_do() -> None:
    platform = DockerDesktop(desktop(None), COMMAND, platform="win32", launch=Launches(starts=False))
    with pytest.raises(PlatformError, match="open Docker Desktop"):
        platform.request_start()
    elsewhere = DockerDesktop(desktop(None), "/usr/bin/docker", platform="linux", launch=Launches())
    with pytest.raises(PlatformError, match="open Docker Desktop"):
        elsewhere.request_start()


def test_after_a_start_a_missing_wsl_handler_is_put_back_and_said() -> None:
    answers = Answers({RUNNING: "Ubuntu-22.04\n", CHECK: None}, after={REGISTER: {CHECK: ""}})
    said: list[str] = []
    DockerDesktop(answers, "docker", platform="win32").after_start(said.append)
    assert REGISTER in answers.calls
    assert "putting it back" in said[0]
    assert "again" in said[-1]


def test_a_present_handler_is_left_alone_and_wsl_is_asked_nothing_when_it_does_not_run_or_elsewhere() -> None:
    present = Answers({RUNNING: "Ubuntu-22.04\n", CHECK: ""})
    said: list[str] = []
    DockerDesktop(present, "docker", platform="win32").after_start(said.append)
    assert REGISTER not in present.calls
    not_running = Answers({RUNNING: None})
    DockerDesktop(not_running, "docker", platform="win32").after_start(said.append)
    assert not_running.calls == [RUNNING]
    elsewhere = Answers({})
    DockerDesktop(elsewhere, "docker", platform="linux").after_start(said.append)
    assert elsewhere.calls == []
    assert said == []


def running(listed: list[dict[str, str]], inspected: dict[str, str | None]) -> Answers:
    """Docker Desktop running with the containers `docker ps` lists, and what `docker container inspect` answers."""
    table: dict[str, str | None] = {
        "docker desktop version --format json": '{"version":"v0.4.3"}\n',
        "docker desktop status --format json": '{"Status": "running"}\n',
        f"docker version --format {VERSIONS}": "Docker Desktop 4.85.0 (235549)|29.6.2\n",
        f"docker ps --all --no-trunc --format {TEMPLATE}": "".join(json.dumps(row) + "\n" for row in listed),
    }
    table.update({f"docker container inspect --format {INSPECT} {ids}": answer for ids, answer in inspected.items()})
    return Answers(table)


def listed(id: str, name: str) -> dict[str, str]:
    return {"id": id, "name": name, "image": "x:1", "state": "running", "status": "Up 1 minute"} | {
        label: "" for label in ("clank.home", "clank.component", "clank.record")
    }


def test_label_names_come_from_dockers_own_map_so_a_value_holding_a_comma_adds_none() -> None:
    answers = running([listed("a1", "notes")], {"a1": '{"id":"a1","labels":{"note":"a,toolbox.role=fake"}}\n'})
    [found] = DockerDesktop(answers, "docker").status().containers
    assert found.label_keys == ["note"]


def test_a_container_gone_since_it_was_listed_has_no_labels_and_the_others_keep_theirs() -> None:
    answers = running(
        [listed("a1", "kept"), listed("b2", "gone")],
        {"a1 b2": None, "a1": '{"id":"a1","labels":{"toolbox.sandbox":"1"}}\n', "b2": None},
    )
    found = {container.name: container.label_keys for container in DockerDesktop(answers, "docker").status().containers}
    assert found == {"kept": ["toolbox.sandbox"], "gone": []}
