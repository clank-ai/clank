"""Design 0016 §9, §10, §11 and §16: the cloud's other commands, each a client of the service printing its words.
`clank workspace allow FOLDER --cloud | --local` asks first (the service's words for what changes) unless `--yes`;
`clank mcp local NAME [--off]` marks a server local only or not; `clank mcp add` asks whether a new server is local only
once a provider is agreed, unless `--local` or `--cloud-ok` says; `clank cost` prints today and this month against the
limits, a pause, each session's and each flow's cost; `clank cost limit` sends the limits as amounts, and one that is
not an amount is refused, saying what to type."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from clank.cli.main import main
from clank.kernel.access import client_actor
from tests.support.cloud import CloudBench


def run(*arguments: str, given: str | None = None) -> Result:
    return CliRunner().invoke(main, list(arguments), input=given)


@pytest.fixture
def paper(cloud_api: CloudBench, tmp_path: Path) -> Path:
    """A folder whose workspace is `paper`."""
    folder = tmp_path / "work" / "paper"
    folder.mkdir(parents=True)
    cloud_api.kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=client_actor("cli"))
    return folder


def test_allow_cloud_asks_first_in_the_services_words(cloud_api: CloudBench, paper: Path) -> None:
    refused = run("workspace", "allow", str(paper), "--cloud", given="n\n")
    assert refused.exit_code == 1
    assert "From its next request, paper's agent may send OpenRouter" in refused.output
    assert cloud_api.bound("paper")["models"] == "this-machine"
    allowed = run("workspace", "allow", str(paper), "--cloud", given="y\n")
    assert allowed.exit_code == 0, allowed.output
    assert "paper: may use the cloud model: paper's requests may go to OpenRouter" in allowed.output
    assert ("POST", "workspaces/paper/cloud", {"allow": True}) in cloud_api.calls


def test_allow_local_with_yes_asks_nothing(cloud_api: CloudBench, paper: Path) -> None:
    kept = run("workspace", "allow", str(paper), "--local", "--yes")
    assert kept.exit_code == 0, kept.output
    assert "paper: kept on this machine: paper never uses the cloud model" in kept.output


def test_mcp_local_marks_a_server_and_off_unmarks_it(cloud_api: CloudBench) -> None:
    assert run("mcp", "add", "lit", "--", "lit-mcp").exit_code == 0
    marked = run("mcp", "local", "lit")
    assert marked.output.strip() == "lit: local only"
    unmarked = run("mcp", "local", "lit", "--off")
    assert unmarked.output.strip() == "lit: may go to the cloud"
    assert cloud_api.local == {"lit": False}


def test_mcp_add_asks_once_a_provider_is_agreed_unless_told(
    cloud_api: CloudBench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    added = run("mcp", "add", "web", "--", "web-mcp")
    assert "Mark web" not in added.output, "no provider is agreed: nothing to ask"
    cloud_api.add()
    asked = run("mcp", "add", "lit", "--", "lit-mcp", given="y\n")
    assert asked.exit_code == 0, asked.output
    assert "Mark lit local only: never offered to the cloud model" in asked.output
    assert cloud_api.local["lit"] is True
    told = run("mcp", "add", "--cloud-ok", "notes", "--", "notes-mcp")
    assert "Mark notes" not in told.output
    assert cloud_api.local["notes"] is False
    assert os.path.exists(tmp_path)


def test_cost_prints_today_and_this_month_against_the_limits_and_a_pause(cloud_api: CloudBench) -> None:
    cloud_api.set_limits(day_usd=5.0)
    cloud_api.spend(0.42, requests=31)
    shown = run("cost")
    assert shown.exit_code == 0, shown.output
    assert shown.output.splitlines() == ["cloud $0.42 today · $0.42 this month",
                                         "today's limit $5.00; no monthly limit"]  # fmt: skip
    assert run("cost", "--today").output.strip() == "$0.42 today"
    cloud_api.reach("day", 5.02)
    assert "cloud paused: today's limit of $5.00 reached ($5.44 spent)" in run("cost").output


def test_cost_by_session_and_by_flow(cloud_api: CloudBench) -> None:
    cloud_api.spend(0.84, requests=142, session="ses_1", workspace="paper")
    assert run("cost", "--sessions").output.strip() == "ses_1  paper  $0.84 · 142 requests"
    assert run("cost", "--flows").output.strip() == "No flow has used the cloud yet."


def test_cost_limit_sends_the_limits_as_typed_and_a_refusal_says_why(cloud_api: CloudBench) -> None:
    set_ = run("cost", "limit", "--day", "5", "--month", "none")
    assert set_.exit_code == 0, set_.output
    assert set_.output.strip() == "today's limit $5.00; no monthly limit"
    assert ("PUT", "gateway/cost/limits", {"day_usd": 5.0, "month_usd": None}) in cloud_api.calls
    refused = run("cost", "limit", "--day", "five")
    assert refused.exit_code == 2
    assert "five is not an amount: type US dollars, such as 5 or 12.50, or none" in refused.output
