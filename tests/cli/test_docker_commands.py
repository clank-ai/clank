"""Design 0002 §2.15 and §3.2: `clank docker status` prints Docker's state, its versions and each running container
with its owner, as readable text and, with --json, as JSON; `clank docker start` and `clank docker stop` follow their
operation step by step; a stop that needs an answer asks at the terminal (no leaves Docker running), `--yes` answers
it as you (cli), and an answer given elsewhere while the prompt waits is reported with who gave it."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform, container


@pytest.fixture
def platform(home: Home) -> FakePlatform:
    return FakePlatform(
        containers=[
            container("workspace-demo", labels={"clank.home": home.id}),
            container("toolbox-sandbox-017", labels={"toolbox.sandbox": "1"}),
            container("postgres-dev"),
            container("old-build", state="exited"),
            container("built-here").model_copy(update={"image": "sha256:" + "27161702926d" * 5 + "abcd"}),
        ]
    )


@pytest.fixture
def kernel(home: Home, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(workspaces_service, "WAIT_SECONDS", 0.001)
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


def run(*arguments: str, input: str | None = None) -> Result:
    return CliRunner().invoke(main, list(arguments), input=input)


def test_docker_status_prints_the_state_and_each_running_container_with_its_owner(kernel: Kernel) -> None:
    shown = run("docker", "status")
    assert shown.exit_code == 0, shown.output
    assert "Fake Docker 4.85.0 · running · engine 29.6.2" in shown.output
    assert "4 containers running, 1 of them Clank's" in shown.output
    lines = {line.split()[0]: line for line in shown.output.splitlines()[2:]}
    assert "Clank's" in lines["workspace-demo"]
    assert "other" in lines["toolbox-sandbox-017"]
    assert "other" in lines["postgres-dev"]
    assert "old-build" not in shown.output
    assert "sha256:271617029" in lines["built-here"]
    assert "27161702926d27161702926d" not in lines["built-here"]
    as_json = json.loads(run("docker", "status", "--json").output)
    assert as_json["state"] == "running"
    assert len(as_json["containers"]) == 5


def test_docker_status_of_a_stopped_docker_is_its_state_alone_with_no_empty_line(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.state = "stopped"
    shown = run("docker", "status")
    assert shown.exit_code == 0, shown.output
    assert shown.output == "Fake Docker · stopped\n"


def test_docker_start_prints_each_step_and_the_end(kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "stopped"
    started = run("docker", "start")
    assert started.exit_code == 0, started.output
    for line in ("1 of 2: start", "asked Fake Docker to start", "2 of 2: wait", "Fake Docker is running"):
        assert line in started.output
    assert started.output.index("1 of 2: start") < started.output.index("2 of 2: wait")
    assert started.output.strip().splitlines()[-1].startswith("Fake Docker · running")


def test_docker_stop_asks_at_the_terminal_and_no_leaves_docker_running(kernel: Kernel, platform: FakePlatform) -> None:
    stopped = run("docker", "stop", input="n\n")
    assert stopped.exit_code == 1
    assert "Stop Fake Docker?" in stopped.output
    assert "toolbox-sandbox-017, postgres-dev" in stopped.output
    assert "y  Stop them and Docker" in stopped.output
    assert "canceled: you (cli) answered Cancel" in stopped.output
    assert platform.state == "running"


def test_docker_stop_yes_answers_the_question_as_you_through_the_cli(kernel: Kernel, platform: FakePlatform) -> None:
    stopped = run("docker", "stop", "--yes")
    assert stopped.exit_code == 0, stopped.output
    assert platform.state == "stopped"
    [question] = kernel.questions.find()
    assert question.answer is not None
    assert (question.answer.option, question.answer.by.via) == ("stop", "cli")


def test_an_answer_given_elsewhere_while_the_prompt_waits_is_reported_with_who_gave_it(
    kernel: Kernel, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch
) -> None:
    def answered_in_the_console_meanwhile(text: str, default: str) -> str:
        [question] = kernel.questions.waiting()
        kernel.questions.answer(question.id, by=Actor(kind="user", via="console"), option="stop")
        return "n"

    monkeypatch.setattr(follow, "ask", answered_in_the_console_meanwhile)
    stopped = run("docker", "stop")
    assert stopped.exit_code == 0, stopped.output
    assert "already answered by you (console)" in stopped.output
    assert platform.state == "stopped"
