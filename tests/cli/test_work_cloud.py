"""Design 0016 §9, §14 and §16, decision 0112: `clank work` with no usable model says so and how to add one; with a
cloud model in the main slot and the workspace not answered, it asks the workspace's question in the terminal, in the
service's words, before OpenCode starts, answered through the question's own route: `n` keeps the workspace on this
machine and stops before OpenCode, saying how to allow it; `y` allows it and goes on."""

from collections.abc import Sequence
from typing import Any

import pytest
from click.testing import CliRunner, Result

from clank.cli.main import main
from clank.components.agents import cli as agents_cli
from clank.kernel.access import client_actor
from tests.support.cloud import CloudBench


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The folder's workspace ready without Docker (`paper`), and what the terminal was asked to run."""
    ran: list[list[str]] = []

    def run(argv: Sequence[str]) -> int:
        ran.append(list(argv))
        return 0

    monkeypatch.setattr(agents_cli, "_ready", lambda client, path, yes: {"workspace": "paper"})
    monkeypatch.setattr(agents_cli, "terminal", run)
    return ran


def work(given: str = "") -> Result:
    return CliRunner().invoke(main, ["work"], input=given)


def cloud(fake: CloudBench) -> None:
    folder = fake.kernel.home.root.parent / "paper"
    folder.mkdir()
    fake.kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=client_actor("cli"))
    fake.add()
    fake.write_preset()
    fake.run("cloud-example-coder")


def test_with_no_usable_model_it_says_so_and_how_to_add_one(cloud_api: CloudBench, started: list[Any]) -> None:
    done = work()
    assert done.exit_code == 1
    assert "No model is set up yet: run clank, or clank model add" in done.output
    assert started == []


def test_n_keeps_the_workspace_local_and_stops_before_opencode(cloud_api: CloudBench, started: list[Any]) -> None:
    cloud(cloud_api)
    done = work("n\n")
    assert done.exit_code == 1
    assert "Let paper's agent use the cloud model cloud: Example Coder?" in done.output
    assert "What never goes: Notion pages" in done.output
    assert "paper is kept on this machine" in done.output
    assert "clank workspace allow" in done.output
    assert started == []
    assert cloud_api.bound("paper")["cloud_answered"]
    asked_again = work()
    assert "Let paper's agent" not in asked_again.output, "asked once"
    assert asked_again.exit_code == 1


def test_y_allows_the_workspace_and_goes_on(cloud_api: CloudBench, started: list[Any]) -> None:
    cloud(cloud_api)
    done = work("y\n")
    assert cloud_api.bound("paper")["models"] == "cloud"
    assert "kept on this machine" not in done.output
