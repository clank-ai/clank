"""Design 0016 §9 (decisions 0103 and 0112): every workspace, new or existing, stays on this machine until the owner
says otherwise; with a cloud model in the main slot, a workspace not yet answered is asked once whether its agent may
use it (the open question given again while it waits), with words that say what goes, what never does and, for a
workspace that existed before the provider was agreed, that its earlier sessions and folder may hold research; *allow*
makes its bound `cloud` and gives it to the gateway, *keep local* is kept and not asked again; a question that expires
leaves it unanswered, asked again next time; each answer is an event that says who gave it; and the bounds reach the
gateway at every change and at each start of the service. Every answer of the question's route says whether the agent
may start now (`start`), and a folder's view carries its workspace's bound beside its other facts."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.gateway.service import Gateway
from clank.components.workspaces.service import Workspaces
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")
PHONE = Actor(kind="device", via="phone")
CLOUD_MAIN = {"status": "ready", "provider": "endpoint", "endpoint": "openrouter", "title": "cloud: Example Coder",
              "preset": "cloud-example-coder"}  # fmt: skip
LOCAL_MAIN = {"status": "ready", "provider": "engine", "engine": "kvmem-llamacpp", "title": "daily 262K"}


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def main_runs(monkeypatch: pytest.MonkeyPatch, rig: Rig, main: dict[str, Any]) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    real = gateway.routes

    def routes() -> dict[str, Any]:
        return {**real(), "slots": {"main": main}}

    monkeypatch.setattr(gateway, "routes", routes)


def workspace(rig: Rig, tmp_path: Path, name: str = "notes") -> None:
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    rig.kernel.settings.write("workspace", name, {"path": str(folder)}, base=None, actor=YOU)


def asked(http: TestClient, name: str = "notes") -> dict[str, Any]:
    answer = http.post(f"/api/v1/workspaces/{name}/cloud/ask", headers=AUTH)
    assert answer.status_code == 200, answer.text
    found: dict[str, Any] = answer.json()
    return found


def views(http: TestClient) -> dict[str, dict[str, Any]]:
    rows = http.get("/api/v1/workspaces", headers=AUTH).json()
    return {row["name"]: row for row in rows}


def test_every_workspace_starts_on_this_machine_and_its_bound_reaches_the_gateway(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clank.components.workspaces import service as workspaces_service
    from tests.fakes.platform import FakePlatform

    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    workspace(rig, tmp_path)
    shown = views(http)["notes"]
    assert (shown["models"], shown["cloud_answered"], shown["cloud_question"]) == ("this-machine", "", None)
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert gateway.bound("notes") == {"workspace": "notes", "models": "this-machine", "answered": False,
                                      "question": None}  # fmt: skip
    workspaces: Workspaces = rig.kernel.parts["workspaces"]
    workspace(rig, tmp_path, "lab")
    workspaces.cloud.give()
    assert gateway.bound("lab") is not None
    folder = http.get("/api/v1/workspaces/folder", params={"folder": str(tmp_path / "notes")}, headers=AUTH).json()
    assert (folder["workspace"], folder["models"], folder["cloud_answered"], folder["cloud_question"]) == (
        "notes", "this-machine", "", None)  # fmt: skip
    assert folder["cloud_said"] == "not asked yet: notes is asked once before its agent uses the cloud model"
    assert folder["cloud_confirm"]["allow"].startswith("From its next request, notes's agent may send OpenRouter")
    assert shown["cloud_said"] == folder["cloud_said"], "the workspaces' list says it too"
    (tmp_path / "plain").mkdir()
    bare = http.get("/api/v1/workspaces/folder", params={"folder": str(tmp_path / "plain")}, headers=AUTH).json()
    assert (bare["workspace"], bare["models"], bare["cloud_answered"], bare["cloud_question"]) == (None,) * 4
    assert (bare["cloud_said"], bare["cloud_confirm"]) == (None, None)


def test_no_question_is_needed_while_the_main_slot_runs_a_local_model(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(rig, tmp_path)
    main_runs(monkeypatch, rig, LOCAL_MAIN)
    found = asked(http)
    assert (found["needed"], found["allowed"], found["question"], found["start"]) == (False, False, None, True)
    assert rig.kernel.questions.waiting() == []


def test_with_a_cloud_model_the_workspace_is_asked_once_and_allowing_gives_the_gateway_its_bound(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(rig, tmp_path)
    main_runs(monkeypatch, rig, CLOUD_MAIN)
    first = asked(http)
    assert (first["needed"], first["allowed"], first["start"]) == (True, False, False)
    [question] = rig.kernel.questions.waiting()
    assert question.id == first["question"]
    assert question.title == "Let notes's agent use the cloud model cloud: Example Coder?"
    assert [(option.id, option.key) for option in question.options] == [("allow", "y"), ("local", "n")]
    assert (question.default, question.urgency, question.asked_by.describe()) == ("local", "high", "Clank (workspaces)")
    assert question.expires == rig.clock.now() + timedelta(minutes=30)
    assert "never" in question.detail
    assert asked(http)["question"] == first["question"], "the open question, given again"
    assert len(rig.kernel.questions.waiting()) == 1
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert (gateway.bound("notes") or {})["question"] == first["question"]
    rig.kernel.questions.answer(first["question"], by=PHONE, option="allow")
    shown = views(http)["notes"]
    assert (shown["models"], shown["cloud_question"]) == ("cloud", None)
    assert gateway.bound("notes") == {"workspace": "notes", "models": "cloud", "answered": True, "question": None}
    [answered] = rig.kernel.events.latest(types=["workspaces.cloud_answered"])
    assert answered.data == {"workspace": "notes", "models": "cloud", "who": "device phone"}
    assert answered.summary == "notes may use the cloud model (device phone)"
    after = asked(http)
    assert (after["needed"], after["allowed"], after["start"]) == (False, True, True)


def test_keep_local_is_kept_and_never_asked_again_until_the_owner_says(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(rig, tmp_path)
    main_runs(monkeypatch, rig, CLOUD_MAIN)
    rig.kernel.questions.answer(asked(http)["question"], by=YOU, option="local")
    shown = views(http)["notes"]
    assert (shown["models"], shown["cloud_answered"] != "") == ("this-machine", True)
    again = asked(http)
    assert (again["needed"], again["allowed"], again["question"], again["start"]) == (False, False, None, False)
    assert "clank workspace allow" in again["why"]
    allowed = http.post("/api/v1/workspaces/notes/cloud", json={"allow": True}, headers=AUTH)
    assert allowed.json()["models"] == "cloud"
    narrowed = http.post("/api/v1/workspaces/notes/cloud", json={"allow": False}, headers=AUTH)
    assert narrowed.json()["models"] == "this-machine"
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert (gateway.bound("notes") or {})["models"] == "this-machine"


def test_a_question_that_expires_leaves_the_workspace_unanswered_and_asked_again(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(rig, tmp_path)
    main_runs(monkeypatch, rig, CLOUD_MAIN)
    first = asked(http)["question"]
    rig.clock.advance(31 * 60)
    rig.kernel.questions.expire_due()
    shown = views(http)["notes"]
    assert (shown["models"], shown["cloud_answered"], shown["cloud_question"]) == ("this-machine", "", None)
    second = asked(http)
    assert second["needed"] is True
    assert second["question"] != first


def test_a_workspace_older_than_the_agreement_is_told_its_history_may_hold_research(
    rig: Rig,
    http: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(rig, tmp_path, "older")
    rig.clock.advance(60)
    rig.kernel.events.record("runtime.endpoint_added", summary="you added OpenRouter", actor=YOU,
                             data={"id": "openrouter", "adapter": "openrouter", "local_mcp": []})  # fmt: skip
    rig.clock.advance(60)
    workspace(rig, tmp_path, "newer")
    main_runs(monkeypatch, rig, CLOUD_MAIN)
    older = rig.kernel.questions.get(asked(http, "older")["question"])
    newer = rig.kernel.questions.get(asked(http, "newer")["question"])
    assert "earlier sessions and its folder may hold research" in older.detail
    assert "earlier sessions" not in newer.detail
