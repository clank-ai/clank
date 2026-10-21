"""Design 0012 §9.1, §9.2, §9.3 and §9.6 (§11 step 9), decisions 0054 and 0079: the Guide's actions, run against two
fake OpenCode servers in one workspace's container (`tests/fakes/opencode.py`) with the bridge on this machine.

The exact calls are sent, to the server that runs the session and no other: Stop aborts the session and rejects the
ask waiting in it; a note carries the session's agent, its model and what it is about, and, while a call waits for
approval, rejects that call with the note as its reason instead, adding no message; Compact now asks `summarize` with
the agent role and `auto` on, and returns at once while OpenCode holds the request. Each action leaves an
`agents.acted` event with who did it (the owner from the console or the phone, or a Watch for rule, whose note now goes
through the Guide); an action that cannot run sends nothing and says why. The routes offer the actions, act, and refuse
with the Guide's reason.
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.guide import Guide, GuideError
from clank.components.agents.watchfor.marks import WATCH
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents import test_monitor_sessions as shared
from tests.fakes.opencode import FakeOpenCode

kernel = shared.kernel  # the fixtures, found by their names
servers = shared.servers
until, watched = shared.until, shared.watched

OWNER = Actor(kind="user", via="console")
PHONE = Actor(kind="device", via="phone")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
STEP = {"id": "msg_new", "sessionID": "ses_plan", "role": "assistant", "parentID": "msg_01", "agent": "planner",
        "modelID": "agent", "providerID": "clank", "time": {"created": 1_760_900_100_000}}  # fmt: skip
CALL = {"id": "prt_new", "sessionID": "ses_plan", "messageID": "msg_new", "type": "tool", "callID": "call_rm",
        "tool": "bash", "state": {"status": "running", "input": {"command": "rm -r runs"},
                                  "time": {"start": 1}}}  # fmt: skip
ASK = {"id": "per_1", "sessionID": "ses_plan", "permission": "bash", "patterns": ["rm -r runs"],
       "tool": {"messageID": "msg_new", "callID": "call_rm"}}  # fmt: skip


def busy(server: FakeOpenCode) -> None:
    server.feed({"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "busy"}}})


def idle(server: FakeOpenCode) -> None:
    server.feed({"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "idle"}}})


def asking(server: FakeOpenCode) -> None:
    """The session works on a step whose `bash` call waits for the owner's approval."""
    server.asks = [dict(ASK)]
    busy(server)
    server.feed({"type": "message.updated", "properties": {"sessionID": "ses_plan", "info": STEP}},
                {"type": "message.part.updated", "properties": {"sessionID": "ses_plan", "part": CALL}},
                {"type": "permission.asked", "properties": ASK})  # fmt: skip


def offered(guide: Guide, action: str) -> dict[str, Any]:
    return next(each for each in guide.offer("paper", "ses_plan")["actions"] if each["action"] == action)


def seen(guide: Guide, test: Callable[[], bool]) -> None:
    """Wait until the flow the Guide reads shows it."""
    until(lambda: guide.flows.view("paper", "ses_plan") is not None and test())


def ready(kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Guide:
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    busy(flow)
    until(lambda: sessions.runs("paper", "ses_plan") == flow.port)
    guide: Guide = kernel.parts["agents"].guide
    return guide


def test_stop_aborts_the_session_and_rejects_a_waiting_ask_on_the_server_that_runs_it(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    asking(flow)
    seen(guide, lambda: offered(guide, "stop")["calls"][1] == 'POST /permission/per_1/reply {"reply": "reject"}')
    answer = guide.stop("paper", "ses_plan", actor=OWNER)
    assert (answer["state"], answer["rejected"], answer["port"]) == ("stopping", ["per_1"], flow.port)
    assert [path for _, path, _ in flow.sent] == ["/session/ses_plan/abort", "/permission/per_1/reply"]
    assert flow.sent_to("/permission/per_1/reply") == [{"reply": "reject"}]
    assert window.sent == [], "nothing reached the server that does not run the session"
    assert offered(guide, "stop")["state"]["state"] == "stopping"
    flow.feed({"type": "permission.replied", "properties": {"sessionID": "ses_plan", "requestID": "per_1",
                                                            "reply": "reject"}})  # fmt: skip
    idle(flow)
    seen(guide, lambda: offered(guide, "stop")["state"]["state"] == "stopped")


def test_a_note_carries_the_agent_the_model_and_what_it_is_about(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    seen(guide, lambda: offered(guide, "stop")["can"])
    answer = guide.note("paper", "ses_plan", "use a log scale.", about="step 3, `bash pytest -q`", actor=OWNER)
    said = "About step 3, `bash pytest -q`: use a log scale."
    assert (answer["text"], answer["agent"], answer["model"]) == (said, "planner", {"providerID": "clank",
                                                                                    "modelID": "agent"})  # fmt: skip
    [sent] = flow.sent_to("/session/ses_plan/prompt_async")
    assert (sent["agent"], sent["model"], sent["parts"]) == (
        "planner", {"providerID": "clank", "modelID": "agent"}, [{"type": "text", "text": said}]
    )  # fmt: skip
    assert offered(guide, "note")["state"]["state"] == "written"


def test_a_note_while_a_call_waits_for_approval_rejects_that_call_with_the_note(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    asking(flow)
    seen(guide, lambda: "reject" in offered(guide, "note")["does"])
    answer = guide.note("paper", "ses_plan", "keep the runs; skip the cleanup.", actor=OWNER)
    assert answer["rejected"] == "per_1"
    assert flow.sent_to("/permission/per_1/reply") == [
        {"reply": "reject", "message": "keep the runs; skip the cleanup."}
    ]
    assert flow.sent_to("/session/ses_plan/prompt_async") == [], "no message added"
    assert offered(guide, "note")["state"]["state"] == "sent"


def test_compact_now_asks_summarize_with_the_agent_role_and_auto_on_and_returns_at_once(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    seen(guide, lambda: offered(guide, "stop")["can"])
    began = time.monotonic()
    answer = guide.compact("paper", "ses_plan", actor=OWNER)
    assert time.monotonic() - began < 10, "OpenCode holds the request until the run ends: the Guide does not wait"
    assert (answer["state"], answer["asked"], answer["answered"]) == ("asked", True, False)
    assert flow.sent_to("/session/ses_plan/summarize") == [{"providerID": "clank", "modelID": "agent", "auto": True}]
    again = offered(guide, "compact")
    assert (again["can"], again["state"]["state"]) == (False, "asked")
    with pytest.raises(GuideError, match="asked already"):
        guide.compact("paper", "ses_plan", actor=OWNER)
    assert len(flow.sent_to("/session/ses_plan/summarize")) == 1
    flow.release.set()


def test_each_action_leaves_an_agents_acted_event_with_who_did_it(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    seen(guide, lambda: offered(guide, "stop")["can"])
    guide.note("paper", "ses_plan", "a note from the phone.", actor=PHONE)
    guide.compact("paper", "ses_plan", actor=OWNER)
    guide.stop("paper", "ses_plan", actor=OWNER)
    acted = kernel.events.after(0, types=["agents.acted"])
    assert [(event.data["action"], event.actor.describe()) for event in acted] == [
        ("message", "device phone"), ("compact", "you (console)"), ("stop", "you (console)"),
        ("reject", "you (console)"),
    ]  # fmt: skip
    assert {event.data["port"] for event in acted} == {flow.port}
    flow.release.set()


def test_a_rules_note_goes_through_the_guide_as_the_rule(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design 0012 §8 (decision 0082): "tell the model" was waiting for this step; it sends the rule's words now."""
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    seen(guide, lambda: offered(guide, "stop")["can"])
    kernel.parts["agents"].marks.acting.note("paper", flow.port, "ses_plan", "You ran the same call three times.")
    [sent] = flow.sent_to("/session/ses_plan/prompt_async")
    assert (sent["parts"][0]["text"], sent["agent"]) == ("You ran the same call three times.", "planner")
    [acted] = kernel.events.after(0, types=["agents.acted"])
    assert acted.actor == WATCH


def test_an_action_that_cannot_run_sends_nothing_and_says_why(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    idle(flow)
    seen(guide, lambda: not offered(guide, "stop")["can"])
    with pytest.raises(GuideError, match="Stop now cannot run now: the session is idle and nothing waits in it"):
        guide.stop("paper", "ses_plan", actor=OWNER)
    with pytest.raises(GuideError, match="an empty note is not sent"):
        guide.note("paper", "ses_plan", "  ", actor=OWNER)
    with pytest.raises(GuideError, match="keeps no flow of ses_gone"):
        guide.note("paper", "ses_gone", "Go on.", actor=OWNER)
    assert flow.sent == []
    assert window.sent == []
    assert kernel.events.after(0, types=["agents.acted"]) == []


def test_the_routes_offer_the_actions_act_and_refuse_with_the_reason(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    seen(guide, lambda: offered(guide, "stop")["can"])
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        found = http.get("/api/v1/agents/guide/paper/ses_plan", headers=AUTH).json()
        keys = [each["key"] for each in found["actions"]]
        assert (found["port"], keys) == (flow.port, [".", "m", "k", "p", "u", "x"])
        noted = http.post("/api/v1/agents/guide/paper/ses_plan/note", json={"text": "Go on.", "about": "step 2"},
                          headers=AUTH)  # fmt: skip
        assert (noted.status_code, noted.json()["text"]) == (200, "About step 2: Go on.")
        assert http.post("/api/v1/agents/guide/paper/ses_plan/compact", headers=AUTH).json()["state"] == "asked"
        refused = http.post("/api/v1/agents/guide/paper/ses_plan/compact", headers=AUTH)
        assert (refused.status_code, "asked already" in refused.json()["error"]["message"]) == (409, True)
        assert http.post("/api/v1/agents/guide/paper/ses_plan/stop", headers=AUTH).json()["state"] == "stopping"
        missing = http.get("/api/v1/agents/guide/paper/ses_gone", headers=AUTH)
        assert missing.status_code == 409
    flow.release.set()
