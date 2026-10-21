"""Design 0002 §2.15: every action is also a command, a client of the API: `clank events`, `clank questions` (and
answering one), `clank operations`, `clank records`, each as readable text or, with --json, JSON; with no service
running, a command says how to start it."""

import json
import threading
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.machine import service as machine_service
from clank.components.machine.kinds import MachineProfile
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.fakes.platform import FakePlatform
from tests.support.live import live_service

STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    detail="2 containers that Clank did not start are running.",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@pytest.fixture
def kernel(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


def test_events_prints_the_newest_events_oldest_first_and_json_lines_for_scripts(kernel: Kernel) -> None:
    kernel.questions.ask(STOP, asked_by=CLANK)
    kernel.questions.ask(STOP.model_copy(update={"title": "Second question?"}), asked_by=CLANK)
    text = run("events")
    assert text.exit_code == 0, text.output
    assert text.output.index("Stop Docker Desktop?") < text.output.index("Second question?")
    lines = [json.loads(line) for line in run("events", "--json").output.splitlines()]
    assert [line["type"] for line in lines][-2:] == ["question.asked", "question.asked"]


def test_events_follow_ends_saying_so_when_the_service_stops(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    results: list[Result] = []
    try:
        with live_service(kernel, name="cli") as client:
            monkeypatch.setattr(common, "connect", client.clone)
            following = threading.Thread(target=lambda: results.append(run("events", "--follow")), daemon=True)
            following.start()
            deadline = time.monotonic() + 10
            while client.get("service")["clients"] != ["cli"]:
                assert time.monotonic() < deadline, "the command did not follow the event stream"
                time.sleep(0.02)
        following.join(10)
    finally:
        kernel.close()
    assert results, "the command did not end when the service stopped"
    assert results[0].exit_code == 0, results[0].output
    assert results[0].output.splitlines()[-1] == "(the service stopped)"


def test_questions_lists_what_waits_and_an_answer_by_key_records_you_through_the_cli(kernel: Kernel) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    listed = run("questions")
    assert asked.id in listed.output
    assert "y  Stop them and Docker" in listed.output
    answered = run("questions", "answer", asked.id, "y")
    assert answered.exit_code == 0, answered.output
    settled = kernel.questions.get(asked.id)
    assert settled.answer is not None
    assert (settled.answer.option, settled.answer.by.via) == ("stop", "cli")
    assert "No question waits for you" in run("questions").output


def test_operations_lists_the_newest_operations(kernel: Kernel) -> None:
    assert "No operation yet" in run("operations").output
    client = common.connect()
    started = client.post("machine/doctor")
    for _ in range(200):
        if client.get(f"records/operation/{started['id']}")["values"]["status"] == "done":
            break
    listed = run("operations")
    assert started["id"] in listed.output
    assert "Check this machine" in listed.output
    as_json: Sequence[dict[str, Any]] = json.loads(run("operations", "--json").output)
    assert as_json[0]["id"] == started["id"]


def test_records_lists_the_kinds_and_shows_any_record(kernel: Kernel) -> None:
    kinds = run("records", "kinds")
    assert "service" in kinds.output
    assert "machine" in kinds.output
    shown = run("records", "show", "service", "service")
    assert "port" in shown.output
    assert "7720" in shown.output
    as_json = json.loads(run("records", "show", "service", "service", "--json").output)
    assert as_json["values"]["port"] == 7720


def test_a_command_without_the_service_says_how_to_start_it(home: Home) -> None:
    result = CliRunner().invoke(main, ["questions"], env={"CLANK_HOME": str(home.root)})
    assert result.exit_code == 1
    assert "clank serve" in result.output


class Recording:
    """A client that keeps what each command posts, and answers as the service would for a host."""

    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.posted.append(body or {})
        return {"name": "x", "distro": "Ubuntu", "clank_folder": (body or {}).get("clank_folder", "")}


def test_arguments_reach_the_service_as_typed_with_no_home_folder_or_wildcard_expanded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Windows, click would expand `~` and `*` in the command line as a shell does; a path may be one on a WSL host,
    where `~` is not this user's home, so Clank passes them as typed."""
    client = Recording()
    monkeypatch.setattr(common, "connect", lambda: client)
    monkeypatch.setattr("sys.argv", ["clank", "host", "add", "x", "--wsl", "Ubuntu", "--folder", "~/models/*"])
    main(standalone_mode=False)
    assert client.posted == [{"id": "x", "adapter": "wsl", "distro": "Ubuntu", "clank_folder": "~/models/*"}]
