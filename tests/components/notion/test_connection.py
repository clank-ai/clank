"""Design 0010 §2-§3: Clank connects to Notion with the owner's integration secret, kept as a secret only once Notion
accepts it, and never in a record, an event or an answer; the status names the integration and its workspace; every
request names Notion's API version and carries the secret as a bearer token; a request Notion limits is sent again
after the wait Notion asks for. `clank notion connect` asks for the secret without showing it."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.notion.service import Notion
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, VERSION, FakeNotion

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


@pytest.fixture
def notion() -> FakeNotion:
    return FakeNotion()


@pytest.fixture
def kernel(home: Home, notion: FakeNotion) -> Iterator[Kernel]:
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 17, 18, 0, tzinfo=UTC)), registry.components())
    part: Notion = kernel.parts["notion"]
    part.transport = notion.transport
    part.sleep = notion.wait
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7731), base_url="http://127.0.0.1:7731") as client:
        yield client


def call(http: TestClient, method: str, path: str, status: int = 200, **body: Any) -> Any:
    answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=body or None)
    assert answer.status_code == status, answer.text
    return answer.json()


def written(home: Home) -> str:
    """Everything Clank wrote outside its secrets folder."""
    return "\n".join(
        path.read_bytes().decode("utf-8", errors="replace")
        for path in home.root.rglob("*")
        if path.is_file() and home.secrets not in path.parents
    )


def test_connecting_keeps_the_secret_only_once_notion_accepts_it_and_the_status_names_what_it_reached(
    kernel: Kernel, http: TestClient
) -> None:
    assert call(http, "GET", "notion/status")["connected"] is False
    refused = call(http, "POST", "notion/connect", 409, secret="ntn_not_the_right_one")
    assert "Notion refused the secret" in refused["error"]["message"]
    assert kernel.secrets.shown("notion/notion") == []
    status = call(http, "POST", "notion/connect", secret=SECRET)
    assert (status["connected"], status["integration"], status["workspace"]) == (True, "Clank", "A made-up workspace")
    assert status["secret"] == {"set": "2026-10-17T18:00:00.000Z", "ends": SECRET[-4:]}
    assert call(http, "GET", "notion/status")["connected"] is True
    [connected] = kernel.events.after(0, types=["notion.connected"])
    assert connected.data == {"integration": "Clank", "workspace": "A made-up workspace"}


def test_every_request_names_notions_api_version_and_carries_the_secret_as_a_bearer_token(
    kernel: Kernel, http: TestClient, notion: FakeNotion
) -> None:
    call(http, "POST", "notion/connect", secret=SECRET)
    call(http, "GET", "notion/status")
    assert notion.requests, "the status asked Notion"
    for sent in notion.requests:
        assert sent.headers["authorization"] == f"Bearer {SECRET}"
        assert sent.headers["notion-version"] == VERSION


def test_a_request_notion_limits_is_sent_again_after_the_wait_notion_asks_for(
    kernel: Kernel, http: TestClient, notion: FakeNotion
) -> None:
    call(http, "POST", "notion/connect", secret=SECRET)
    notion.limit(2, 0.5)
    assert call(http, "GET", "notion/status")["connected"] is True
    assert notion.waited == [2.0, 0.5]
    notion.limit(*[1] * 10)
    status = call(http, "GET", "notion/status")
    assert status["problem"].startswith("Notion kept asking Clank to wait")


def test_the_secret_is_in_no_record_event_or_answer(kernel: Kernel, http: TestClient) -> None:
    answers = [call(http, "POST", "notion/connect", secret=SECRET), call(http, "GET", "notion/status")]
    assert SECRET not in json.dumps(answers)
    assert SECRET not in written(kernel.home)
    assert SECRET not in json.dumps([event.data for event in kernel.events.after(0)])


def test_disconnecting_removes_the_secret_and_the_status_says_how_to_connect(kernel: Kernel, http: TestClient) -> None:
    call(http, "POST", "notion/connect", secret=SECRET)
    status = call(http, "DELETE", "notion/connect")
    assert (status["connected"], status["secret"]) == (False, None)
    assert "clank notion connect" in status["problem"]
    assert kernel.secrets.shown("notion/notion") == []


def test_clank_notion_connect_asks_for_the_secret_without_showing_it_and_says_what_it_reached(
    kernel: Kernel, http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7731", "t", name="cli", http=http))
    connected = CliRunner().invoke(main, ["notion", "connect"], input=f"{SECRET}\n")
    assert connected.exit_code == 0, connected.output
    assert SECRET not in connected.output
    assert "Connected to Notion: the integration Clank, in A made-up workspace." in connected.output
    status = CliRunner().invoke(main, ["notion", "status"])
    assert "Notion: connected as Clank, in A made-up workspace (secret ending" in status.output
    gone = CliRunner().invoke(main, ["notion", "disconnect"])
    assert "Disconnected from Notion" in gone.output
    assert "Notion: not connected" in CliRunner().invoke(main, ["notion", "status"]).output
