"""Design 0014 §2: Docker Engine's recording is made by a small tool that runs the commands the adapter sends, as the
tool lists them, and keeps each one's exit status, output, errors and time. It replaces the containers' ids, and the
names of the computer and its user, by made-up ones alike everywhere they appear. It runs nothing else: its example
containers only when asked, and never sudo; of `docker info` it asks only the fields Clank reads. Three captures
(running, stopped, no access) merge into the recording, whose `how` says where it was made, which version, and what was
replaced; a capture whose engine was not in the state it names is refused, saying so."""

import json
import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

import pytest

from tools import capture_docker_engine as capture_tool
from tools.capture_docker_engine import Personal

ACTIVE = "LoadState=loaded\nActiveState=active\n"
INACTIVE = "LoadState=loaded\nActiveState=inactive\n"
SOCKET = ["-H", "unix:///var/run/docker.sock"]
DENIED = (
    "permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "
    '"http://%2Fvar%2Frun%2Fdocker.sock/v1.48/version": dial unix /var/run/docker.sock: connect: permission denied\n'
)
DOWN = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n"
FIRST = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
SECOND = "60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752"
PERSONAL = Personal(host="fv-az123-456", user="runner", home="/home/runner")
Reply = tuple[int | None, str, str]


def row(id: str, name: str, state: str, networks: str, home: str = "") -> str:
    """One line of `docker ps` as the template writes it: Clank's labels empty but `clank.home`."""
    found = {"id": id, "name": name, "image": "busybox:1.37.0", "state": state, "status": "Up 3 seconds"}
    found |= {"clank.home": home, "clank.component": "", "clank.record": "", "clank.ports": "", "clank.proxy": ""}
    return json.dumps({**found, "networks": networks}) + "\n"


def key(*arguments: str) -> str:
    """A command as the recording keys it."""
    return " ".join(["docker", *SOCKET, *arguments])


def running() -> dict[str, Reply]:
    listed = row(FIRST, "clank-0123456789ab-demo", "running", "clank-0123456789ab-demo-net", home="0123456789ab")
    listed += row(SECOND, "toolbox-docs-build", "exited", "bridge")
    inspected = "".join(
        json.dumps({"id": id, "labels": labels}) + "\n"
        for id, labels in ((FIRST, {"clank.home": "0123456789ab"}), (SECOND, {"toolbox.role": "run"}))
    )
    stats = json.dumps({"ID": FIRST[:12], "Container": FIRST[:12], "Name": "clank-0123456789ab-demo"}) + "\n"
    warnings = '{"limit":true,"warnings":["WARNING: bridge-nf-call-iptables is disabled on fv-az123-456"]}\n'
    return {
        " ".join(capture_tool.SYSTEMD): (0, ACTIVE, ""),
        key("version", "--format", capture_tool.VERSION): (0, "28.0.4\n", ""),
        key("ps", "--all", "--no-trunc", "--format", capture_tool.TEMPLATE): (0, listed, ""),
        key("container", "inspect", "--format", capture_tool.INSPECT, FIRST, SECOND): (0, inspected, ""),
        key("info", "--format", capture_tool.LIMITS): (0, "4 16766234624\n", ""),
        key("info", "--format", capture_tool.MEMORY): (0, warnings, ""),
        key("stats", "--no-stream", "--format", capture_tool.STATS): (0, stats, ""),
    }


def refusing(systemd: str, said: str) -> dict[str, Reply]:
    """Every docker command refused in Docker's words, systemd saying what it says."""
    asked = [
        ("version", "--format", capture_tool.VERSION),
        ("ps", "--all", "--no-trunc", "--format", capture_tool.TEMPLATE),
        ("info", "--format", capture_tool.LIMITS),
        ("info", "--format", capture_tool.MEMORY),
        ("stats", "--no-stream", "--format", capture_tool.STATS),
    ]
    return {" ".join(capture_tool.SYSTEMD): (0, systemd, ""), **{key(*each): (1, "\n", said) for each in asked}}


class Engine:
    """systemd and Docker Engine as a test sets them: each command's answer by its arguments (the program by its name),
    every command kept, and a clock that each answer moves on by `seconds`."""

    def __init__(self, answers: dict[str, Reply], seconds: float = 0.25) -> None:
        self.answers = answers
        self.seconds = seconds
        self.now = 100.0
        self.ran: list[list[str]] = []

    def clock(self) -> float:
        return self.now

    def __call__(self, argv: Sequence[str]) -> Reply:
        self.ran.append(list(argv))
        self.now += self.seconds
        return self.answers.get(" ".join([PurePosixPath(argv[0]).name, *argv[1:]]), (0, "", ""))


def captured(state: str, engine: Engine, examples: bool = False) -> dict[str, Any]:
    return capture_tool.capture(
        state, engine, docker="/usr/bin/docker", clock=engine.clock, personal=PERSONAL, examples=examples
    )


def test_a_capture_keeps_each_commands_status_output_errors_and_time() -> None:
    engine = Engine(refusing(ACTIVE, DENIED), seconds=0.25)
    found = captured("no access", engine)
    answers = found["answers"]
    assert answers[" ".join(capture_tool.SYSTEMD)] == [0, ACTIVE, 0.25, ""]
    assert answers[key("version", "--format", capture_tool.VERSION)] == [1, "\n", 0.25, DENIED]
    assert all(len(answer) == 4 for answer in answers.values()), "status, output, seconds, errors: every one"
    assert (found["state"], found["command"], found["version"]) == ("no access", "/usr/bin/docker", "")
    late = (None, "", "no answer within 15 s")
    slow = Engine({**refusing(INACTIVE, DOWN), " ".join(capture_tool.SYSTEMD): late})
    assert captured("stopped", slow)["answers"][" ".join(capture_tool.SYSTEMD)] == [None, "", 0.25, late[2]]


def test_a_capture_replaces_ids_names_and_host_values_alike_everywhere() -> None:
    engine = Engine(running())
    engine.answers[key("stats", "--no-stream", "--format", capture_tool.STATS)] = (
        0,
        engine.answers[key("stats", "--no-stream", "--format", capture_tool.STATS)][1],
        "WARNING: Error loading config file: /home/runner/.docker/config.json: permission denied\n",
    )
    found = captured("running", engine)
    text = json.dumps(found)
    for real in (FIRST, FIRST[:12], SECOND, "fv-az123-456", "/home/runner"):
        assert real not in text, real
    made_up = ["a1" * 32, "b2" * 32]
    inspected = key("container", "inspect", "--format", capture_tool.INSPECT, *made_up)
    assert inspected in found["answers"], "the ids are made up in the commands too, so the adapter's ask matches"
    listed = found["answers"][key("ps", "--all", "--no-trunc", "--format", capture_tool.TEMPLATE)][1]
    assert [json.loads(line)["id"] for line in listed.splitlines()] == made_up
    assert [json.loads(line)["id"] for line in found["answers"][inspected][1].splitlines()] == made_up
    stats = found["answers"][key("stats", "--no-stream", "--format", capture_tool.STATS)]
    assert json.loads(stats[1])["ID"] == made_up[0][:12]
    assert "/home/user/.docker/config.json" in stats[3]
    assert "made-up-host" in found["answers"][key("info", "--format", capture_tool.MEMORY)][1]
    assert found["version"] == "28.0.4"
    assert set(found["replaced"]) == {"the containers' ids", "the computer's name", "the user's home folder"}


def test_a_capture_runs_only_its_listed_commands_and_never_sudo() -> None:
    plain = Engine(running())
    captured("running", plain)
    ids = [FIRST, SECOND]
    assert plain.ran == [[*command] for command in capture_tool.commands(ids, docker="/usr/bin/docker")]
    examples = Engine(running())
    captured("running", examples, examples=True)
    made = capture_tool.example_commands(docker="/usr/bin/docker")
    removed = capture_tool.example_cleanup(docker="/usr/bin/docker")
    assert examples.ran == [*made, *capture_tool.commands(ids, docker="/usr/bin/docker"), *removed]
    assert all(command[1:3] == SOCKET for command in made + removed), "the examples go to the system engine too"
    assert any(command[3] == "run" for command in made)
    assert any(command[3:5] == ["rm", "--force"] for command in removed)
    for state, answers in (("stopped", refusing(INACTIVE, DOWN)), ("no access", refusing(ACTIVE, DENIED))):
        engine = Engine(answers)
        captured(state, engine)
        assert engine.ran == [[*command] for command in capture_tool.commands([], docker="/usr/bin/docker")]
    every = plain.ran + examples.ran
    assert not [command for command in every if "sudo" in command], "the tool never runs sudo"
    asked = {field for command in every if command[3:4] == ["info"] for field in re.findall(r"\.(\w+)", command[-1])}
    assert asked == {"NCPU", "MemTotal", "MemoryLimit", "Warnings"}, "never the whole of docker info"


def test_three_captures_merge_into_the_recording_saying_where_which_version_and_what_was_replaced() -> None:
    states = [
        captured("running", Engine(running())),
        captured("stopped", Engine(refusing(INACTIVE, DOWN))),
        captured("no access", Engine(refusing(ACTIVE, DENIED))),
    ]
    recording = capture_tool.merge(states, where="GitHub's ubuntu-24.04 runner", recorded="2026-10-27")
    assert (recording["program"], recording["version"], recording["platform"]) == ("Docker Engine", "28.0.4", "linux")
    assert (recording["initial"], recording["transitions"], recording["command"]) == ("running", {}, "/usr/bin/docker")
    assert list(recording["states"]) == ["running", "stopped", "no access"]
    assert "GitHub's ubuntu-24.04 runner" in recording["how"]
    assert "28.0.4" in recording["how"]
    assert "the containers' ids" in recording["how"]
    assert recording["recorded"] == "2026-10-27"


@pytest.mark.parametrize(
    ("state", "answers", "said"),
    [
        ("running", refusing(ACTIVE, DENIED), "its engine did not answer"),
        ("stopped", refusing(ACTIVE, DENIED), "systemd says Docker's service is active"),
        ("no access", running(), "Docker did not refuse"),
    ],
)
def test_a_capture_whose_engine_was_not_in_the_state_it_names_is_refused_saying_so(
    state: str, answers: dict[str, Reply], said: str
) -> None:
    found = captured(state, Engine(answers))
    assert any(said in problem for problem in capture_tool.problems(found))
    with pytest.raises(ValueError, match=said):
        capture_tool.merge([found], where="here", recorded="2026-10-27")
