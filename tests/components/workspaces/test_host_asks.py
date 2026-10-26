"""Design 0024 §3 (decision 0141): a host the agent reaches without an allowance is asked for. The service allows at
once when the record does, refuses at once within the quiet period, else asks the owner one question per workspace
and host (the same question while it waits): answered always, the host joins the record and the request goes out;
once, it goes out this time; no, or unanswered within `ASK_SECONDS`, it is refused and the host is not asked again for
`QUIET_MINUTES`. The routes the gateway's proxy uses: `POST /workspaces/{name}/hosts/wanted` and
`GET /workspaces/hosts/wanted/{question}`."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import network
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.service import Workspaces
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

OWNER = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "gateway"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def paper(kernel: Kernel, folder: Path) -> Workspaces:
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    found: Workspaces = kernel.parts["workspaces"]
    return found


def test_a_host_not_allowed_is_asked_for_once_per_host_and_always_writes_the_allowance(
    kernel: Kernel, tmp_path: Path
) -> None:
    workspaces = paper(kernel, tmp_path)
    first = workspaces.network.wanted("paper", "api.semanticscholar.org")
    assert first["allowed"] is False
    assert first["quiet"] is False
    question = kernel.questions.get(first["question"])
    assert question.title == "Let paper's agent reach api.semanticscholar.org?"
    assert [option.id for option in question.options] == ["always", "once", "no"]
    assert [option.key for option in question.options] == ["y", "o", "n"]
    assert question.default == "no"
    assert question.about is not None
    assert (question.about.kind, question.about.id) == ("workspace", "paper")
    assert question.expires is not None
    assert question.expires is not None
    assert (question.expires - kernel.clock.now()).total_seconds() == network.ASK_SECONDS
    again = workspaces.network.wanted("paper", "api.semanticscholar.org")
    assert again["question"] == first["question"], "the same question while it waits"
    other = workspaces.network.wanted("paper", "pypi.org")
    assert other["question"] != first["question"], "another host: its own question"
    assert workspaces.network.decision(first["question"]) == {"status": "waiting", "decision": None}
    kernel.questions.answer(first["question"], by=OWNER, option="always")
    assert workspaces.network.decision(first["question"]) == {"status": "answered", "decision": "always"}
    hosts = kernel.settings.get("workspace", "paper").record.model_dump()["hosts"]
    assert list(hosts) == ["api.semanticscholar.org"], "the allowance is written"
    assert "console" in hosts["api.semanticscholar.org"], "by whoever answered"
    assert workspaces.network.wanted("paper", "api.semanticscholar.org") == {
        "allowed": True, "quiet": False, "question": None,
    }  # fmt: skip
    kernel.questions.answer(other["question"], by=OWNER, option="once")
    assert workspaces.network.decision(other["question"]) == {"status": "answered", "decision": "once"}
    assert "pypi.org" not in kernel.settings.get("workspace", "paper").record.model_dump()["hosts"]
    assert workspaces.network.wanted("paper", "pypi.org")["question"] not in (None, other["question"]), (
        "once was this time: the next request asks again"
    )


def test_no_or_no_answer_refuses_and_keeps_the_host_quiet_for_a_while(
    kernel: Kernel, clock: FakeClock, tmp_path: Path
) -> None:
    workspaces = paper(kernel, tmp_path)
    asked = workspaces.network.wanted("paper", "tracker.test")
    kernel.questions.answer(asked["question"], by=OWNER, option="no")
    assert workspaces.network.decision(asked["question"]) == {"status": "answered", "decision": "no"}
    quiet = workspaces.network.wanted("paper", "tracker.test")
    assert quiet == {"allowed": False, "quiet": True, "question": None}
    assert len(kernel.questions.waiting()) == 0, "no new question in the quiet period"
    clock.advance(network.QUIET_MINUTES * 60 + 1)
    asked_again = workspaces.network.wanted("paper", "tracker.test")
    assert asked_again["question"] is not None, "after the quiet period, asked again"
    clock.advance(network.ASK_SECONDS + 1)
    kernel.questions.expire_due()
    assert workspaces.network.decision(asked_again["question"]) == {"status": "expired", "decision": "no"}
    assert workspaces.network.wanted("paper", "tracker.test")["quiet"] is True, "unanswered: quiet too"
    assert workspaces.network.decision("q-nobody") == {"status": "unknown", "decision": "no"}


def test_the_routes_the_proxy_uses_ask_and_read_the_decision(kernel: Kernel, tmp_path: Path) -> None:
    workspaces = paper(kernel, tmp_path)
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        asked = http.post("/api/v1/workspaces/paper/hosts/wanted", json={"host": "export.arxiv.org"}, headers=AUTH)
        assert asked.status_code == 200, asked.text
        found = asked.json()
        assert (found["allowed"], found["quiet"]) == (False, False)
        waiting = http.get(f"/api/v1/workspaces/hosts/wanted/{found['question']}", headers=AUTH).json()
        assert waiting == {"status": "waiting", "decision": None}
        kernel.questions.answer(found["question"], by=OWNER, option="once")
        decided = http.get(f"/api/v1/workspaces/hosts/wanted/{found['question']}", headers=AUTH).json()
        assert decided == {"status": "answered", "decision": "once"}
        missing = http.post("/api/v1/workspaces/nobody/hosts/wanted", json={"host": "x.test"}, headers=AUTH)
        assert missing.status_code == 404
    assert workspaces.network.decision(found["question"])["decision"] == "once"
