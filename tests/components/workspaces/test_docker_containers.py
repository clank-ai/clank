"""Design 0004 §3 and design 0002 §2.9: the Docker Desktop adapter's container commands, on a scripted `docker` (each
command's exact arguments; its answer). It reads the platform's CPUs and memory; tells whether an image is built and
builds one, each line as it comes; makes a network only when it is not there; runs a container from its spec, joining
its other networks after it starts; reads, starts, stops and removes a container, and removes a volume, a missing one
being no error; and says how a terminal enters a container. A command Docker refuses raises its own words.

Design 0004 §5 (revised 2026-10-26): the files written when an agent starts go in one `docker exec` (a few lines of
Python reading them from its input), one by one only in a container without Python."""

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from clank.components.workspaces.adapters.docker_desktop import PUT_FILES, DockerDesktop
from clank.components.workspaces.adapters.platform import PlatformError
from clank.components.workspaces.sandbox import ContainerSpec, edge_spec, run_arguments
from clank.kernel.processes import TIMEOUT_SECONDS, Answer

OK = Answer(0, "", "")


class Docker:
    """`docker` as a test sets it: an answer for each command by its first arguments; every call kept."""

    def __init__(self, answers: dict[tuple[str, ...], Answer | str | None]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []

    def find(self, arguments: Sequence[str]) -> Answer | str | None:
        self.calls.append(list(arguments[1:]))
        for size in range(len(arguments) - 1, 0, -1):
            key = tuple(arguments[1 : 1 + size])
            if key in self.answers:
                return self.answers[key]
        return None

    def run(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        found = self.find(arguments)
        return found if isinstance(found, str) or found is None else (found.output if found.ok else None)

    def answer(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        self.input = input
        found = self.find(arguments)
        if isinstance(found, Answer):
            return found
        return Answer(0, found, "") if found is not None else Answer(1, "", "Error: not scripted")


def adapter(docker: Docker, follow: Callable[..., int | None] | None = None) -> DockerDesktop:
    return DockerDesktop(
        docker.run, "docker", platform="win32", answer=docker.answer, follow=follow or (lambda *args, **kwargs: 0)
    )


def test_the_platforms_cpus_and_memory_are_read_from_its_engine() -> None:
    docker = Docker({("info", "--format"): "16 34359738368\n"})
    assert adapter(docker).limits() == (16, 32768)
    assert adapter(Docker({})).limits() is None


def test_an_image_is_built_only_when_asked_and_its_lines_come_as_written() -> None:
    lines: list[str] = []
    seen: list[list[str]] = []

    def follow(arguments: Sequence[str], line: Callable[[str], None], canceled: Callable[[], bool]) -> int:
        seen.append(list(arguments))
        line("#1 building")
        return 0

    docker = Docker({("image", "inspect"): Answer(1, "", "Error: No such image: clank-sandbox:abc")})
    platform = adapter(docker, follow)
    assert not platform.image_exists("clank-sandbox:abc")
    status = platform.build_image(
        "clank-sandbox:abc", "/image", {"clank.image": "sandbox"}, lines.append, lambda: False
    )
    assert (status, lines) == (0, ["#1 building"])
    assert seen == [
        ["docker", "build", "--progress", "plain", "--tag", "clank-sandbox:abc", "--label", "clank.image=sandbox",
         "/image"]
    ]  # fmt: skip


def test_a_network_is_made_only_when_it_is_not_there() -> None:
    docker = Docker({("network", "inspect"): Answer(1, "", "Error: network x not found"), ("network", "create"): OK})
    adapter(docker).ensure_network("clank-abc-inner", internal=True, labels={"clank.home": "abc"})
    assert docker.calls[-1] == ["network", "create", "--internal", "--label", "clank.home=abc", "clank-abc-inner"]
    there = Docker({("network", "inspect"): "clank-abc-inner\n"})
    adapter(there).ensure_network("clank-abc-inner", internal=True, labels={})
    assert [call[:2] for call in there.calls] == [["network", "inspect"]]


def test_a_container_runs_from_its_spec_and_joins_its_other_networks_after_it_starts() -> None:
    spec = ContainerSpec(
        name="clank-abc-two", image="clank-sandbox:abc", labels=(), command=("sleep", "infinity"),
        networks=(("clank-abc-first", ""), ("clank-abc-second", "two")),
    )  # fmt: skip
    docker = Docker({("run",): "4f2a\n", ("network", "connect"): OK})
    adapter(docker).run_container(spec)
    assert docker.calls == [
        run_arguments(spec),
        ["network", "connect", "--alias", "two", "clank-abc-second", spec.name],
    ]


def test_a_container_joins_and_leaves_a_network_and_a_network_is_removed_each_twice_without_error() -> None:
    said = "Error response from daemon:"
    docker = Docker({
        ("network", "connect"): Answer(1, "", f"{said} endpoint with name x already exists in network y"),
        ("network", "disconnect"): Answer(1, "", f"{said} container x is not connected to network y"),
        ("network", "rm"): Answer(1, "", f"{said} network clank-abc-x-net not found"),
    })  # fmt: skip
    platform = adapter(docker)
    platform.join_network("clank-abc-x-net", "clank-abc-edge", "edge")
    platform.leave_network("clank-abc-x-net", "clank-abc-edge")
    platform.remove_network("clank-abc-x-net")
    assert docker.calls == [
        ["network", "connect", "--alias", "edge", "clank-abc-x-net", "clank-abc-edge"],
        ["network", "disconnect", "--force", "clank-abc-x-net", "clank-abc-edge"],
        ["network", "rm", "clank-abc-x-net"],
    ]
    refused = Docker({("network", "connect"): Answer(1, "", "Error response from daemon: container is not running")})
    with pytest.raises(PlatformError, match=r"could not join clank-abc-x-net: .*not running"):
        adapter(refused).join_network("clank-abc-x-net", "clank-abc-edge", "edge")


def test_a_command_docker_refuses_raises_its_own_words() -> None:
    spec = edge_spec("abc", "clank-sandbox:abc", gateway_port=18210, proxy_port=18211)
    refused = Docker({("run",): Answer(125, "", "docker: Error response from daemon: Conflict. The name is in use.\n")})
    with pytest.raises(PlatformError, match=r"clank-abc-edge could not start: .*Conflict\. The name is in use\."):
        adapter(refused).run_container(spec)


def test_a_container_is_read_started_stopped_and_removed_and_a_missing_one_is_no_error() -> None:
    inspected = (
        '{"id":"4f2a","name":"/clank-abc-x","image":"clank-sandbox:abc","state":"exited",'
        '"labels":{"clank.home":"abc","clank.component":"workspaces","clank.record":"x"}}\n'
    )
    docker = Docker({
        ("container", "inspect"): inspected, ("start",): OK, ("stop",): OK,
        ("rm",): Answer(1, "", "Error response from daemon: No such container: clank-abc-x"),
        ("volume", "rm"): Answer(1, "", "Error response from daemon: get clank-abc-x-home: no such volume"),
    })  # fmt: skip
    platform = adapter(docker)
    found = platform.container("clank-abc-x")
    assert found is not None
    assert (found.name, found.state, found.clank["clank.record"]) == ("clank-abc-x", "exited", "x")
    platform.start_container("clank-abc-x")
    platform.stop_container("clank-abc-x", 10)
    platform.remove_container("clank-abc-x")
    platform.remove_volume("clank-abc-x-home")
    assert docker.calls[1:] == [
        ["start", "clank-abc-x"],
        ["stop", "--time", "10", "clank-abc-x"],
        ["rm", "--force", "clank-abc-x"],
        ["volume", "rm", "clank-abc-x-home"],
    ]
    assert adapter(Docker({})).container("clank-abc-y") is None


def test_a_terminal_enters_a_container_as_its_user_in_its_folder_with_its_environment() -> None:
    argv = adapter(Docker({})).exec_argv("clank-abc-x", ["opencode"], workdir="/workspace", env={"A": "1"})
    assert argv == [
        "docker", "exec", "--interactive", "--tty", "--env", "A=1", "--workdir", "/workspace", "clank-abc-x", "opencode"
    ]  # fmt: skip


def test_a_file_is_written_in_a_container_as_its_user() -> None:
    docker = Docker({("exec",): OK})
    adapter(docker).put_file("clank-abc-x", "/home/agent/.config/x.json", "{}\n")
    assert docker.calls == [
        ["exec", "--interactive", "clank-abc-x", "sh", "-c", 'mkdir -p "$(dirname "$1")" && cat > "$1"', "sh",
         "/home/agent/.config/x.json"]
    ]  # fmt: skip
    assert docker.input == b"{}\n"
    refused = Docker({("exec",): Answer(1, "", "Error response from daemon: container is not running")})
    with pytest.raises(PlatformError, match=r"could not be written in clank-abc-x: .*not running"):
        adapter(refused).put_file("clank-abc-x", "/home/agent/x", "")


def test_several_files_are_written_in_a_container_in_one_command(tmp_path: Path) -> None:
    docker = Docker({("exec",): OK})
    files = [("/home/agent/.clank/mcp/a.py", "print('a')\n"), ("/home/agent/.config/x.json", "{}\n")]
    adapter(docker).put_files("clank-abc-x", files)
    assert docker.calls == [["exec", "--interactive", "clank-abc-x", "python3", "-c", PUT_FILES]], (
        "one docker exec for them all: each one is a fifth of a second on Windows (2026-10-26)"
    )
    assert json.loads(docker.input or b"") == [list(each) for each in files]
    written = [(str(tmp_path / "deep" / "a.py"), "print('a')\n"), (str(tmp_path / "b.json"), "{ \"é\": 1 }\r\n")]
    ran = subprocess.run(
        [sys.executable, "-c", PUT_FILES], input=json.dumps(written).encode(), capture_output=True, check=False
    )
    assert ran.returncode == 0, ran.stderr
    assert (tmp_path / "deep" / "a.py").read_bytes() == b"print('a')\n", "its folder made, its text as given"
    assert (tmp_path / "b.json").read_bytes() == "{ \"é\": 1 }\r\n".encode(), "UTF-8, and its line ends untouched"
    refused = Docker({("exec",): Answer(1, "", "Error response from daemon: container is not running")})
    with pytest.raises(PlatformError, match=r"could not be written in clank-abc-x: .*not running"):
        adapter(refused).put_files("clank-abc-x", files)


def test_a_container_without_python_gets_its_files_one_by_one() -> None:
    missing = Answer(127, "", 'OCI runtime exec failed: exec: "python3": executable file not found in $PATH')
    docker = Docker({("exec", "--interactive", "clank-abc-x", "python3"): missing, ("exec",): OK})
    adapter(docker).put_files("clank-abc-x", [("/home/agent/a", "1"), ("/home/agent/b", "2")])
    assert [call[3] for call in docker.calls] == ["python3", "sh", "sh"]
    assert docker.calls[-1][-1] == "/home/agent/b"
