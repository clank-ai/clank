"""Design 0024 §4 (decision 0141): what the owner sees of the agent's internet exchanges. The network log the gateway's
process writes is read by the service from the files' ends, newest first, one line an exchange, for one workspace when
one is named; the day's bytes are summed by host; the hosts allowed are listed per workspace; `clank network log` and
`clank network hosts` say the same from the command line."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.gateway.proxy import NetworkLog
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

OWNER = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7729", "t", name="cli", http=client))
        yield client


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


def written(folder: Path) -> None:
    """Two days of exchanges, as the proxy writes them."""
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        {"time": "2026-10-25T20:00:00.000+00:00", "workspace": "paper", "host": "pypi.org", "port": 443,
         "method": "CONNECT", "status": 200, "sent": 800, "received": 21000, "seconds": 0.4},
        {"time": "2026-10-26T08:00:00.000+00:00", "workspace": "paper", "host": "pypi.org", "port": 443,
         "method": "CONNECT", "status": 200, "sent": 1200, "received": 12000, "seconds": 0.2},
        {"time": "2026-10-26T08:00:05.000+00:00", "workspace": "paper", "host": "export.arxiv.org", "port": 443,
         "method": "CONNECT", "status": 200, "sent": 500, "received": 30000, "seconds": 1.1, "why": "asked: once"},
        {"time": "2026-10-26T08:00:09.000+00:00", "workspace": "other", "host": "nope.test", "port": 80,
         "method": "GET", "path": "/", "status": 403, "seconds": 0.001, "why": "not allowed"},
    ]  # fmt: skip
    (folder / "2026-10-25.jsonl").write_text(json.dumps(lines[0]) + "\n", encoding="utf-8")
    (folder / "2026-10-26.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines[1:]), encoding="utf-8")


def test_the_log_is_read_newest_first_for_one_workspace_or_all_and_the_days_bytes_are_summed_by_host(
    tmp_path: Path,
) -> None:
    written(tmp_path / "network")
    log = NetworkLog(tmp_path / "network", today=lambda: date(2026, 10, 26))
    recent = log.recent(10)
    assert [(line["host"], line["status"]) for line in recent] == [
        ("nope.test", 403), ("export.arxiv.org", 200), ("pypi.org", 200), ("pypi.org", 200),
    ]  # fmt: skip
    assert [line["host"] for line in log.recent(10, workspace="other")] == ["nope.test"]
    assert len(log.recent(2)) == 2
    assert log.by_host() == {
        "export.arxiv.org": {"sent": 500, "received": 30000, "exchanges": 1},
        "pypi.org": {"sent": 1200, "received": 12000, "exchanges": 1},
        "nope.test": {"sent": 0, "received": 0, "exchanges": 1},
    }, "today's, the most received first"
    assert NetworkLog(tmp_path / "nowhere").recent(5) == []


def test_the_routes_and_the_commands_show_the_exchanges_and_the_hosts_allowed(
    kernel: Kernel, http: TestClient, tmp_path: Path
) -> None:
    written(kernel.home.logs / "network")
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path), "hosts": {"pypi.org": "allowed by you"}},
                          base=None, actor=OWNER)  # fmt: skip
    found = http.get("/api/v1/gateway/network/log", params={"limit": 3}, headers=AUTH).json()
    assert [line["host"] for line in found["exchanges"]] == ["nope.test", "export.arxiv.org", "pypi.org"]
    assert found["by_host"]["export.arxiv.org"]["received"] == 30000
    only = http.get("/api/v1/gateway/network/log", params={"workspace": "paper"}, headers=AUTH).json()
    assert {line["workspace"] for line in only["exchanges"]} == {"paper"}
    hosts = http.get("/api/v1/gateway/network/hosts", headers=AUTH).json()
    assert hosts == {"paper": {"pypi.org": "allowed by you"}}
    said = run("network", "log", "--limit", "2")
    assert said.exit_code == 0, said.output
    assert "nope.test" in said.output
    assert "403" in said.output
    assert "not allowed" in said.output
    assert "export.arxiv.org" in said.output
    assert "pypi.org" not in said.output.split("by host")[0], "two lines asked for"
    listed = run("network", "hosts")
    assert listed.exit_code == 0, listed.output
    assert "paper: pypi.org" in listed.output
    assert run("network", "log", "--json").exit_code == 0


def test_an_exchange_is_said_in_local_time_with_words_for_what_it_lacks() -> None:
    """The log keeps UTC times: the line cut its hours from the text, 21:06:30 for 17:06 on the owner's PC, and printed
    a missing status as None (2026-10-26)."""
    from clank.cli.common import local_time
    from clank.components.gateway.networkcli import exchange_line

    when = "2026-10-26T21:06:30.000+00:00"
    line = exchange_line({"time": when, "workspace": "paper", "host": "registry.npmjs.org", "method": "CONNECT",
                          "status": None, "seconds": None})  # fmt: skip
    assert line.startswith(local_time(when))
    assert "no status" in line
    assert "None" not in line
