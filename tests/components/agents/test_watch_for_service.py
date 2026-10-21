"""Design 0012 §8 and §11 step 8 (decision 0053): the Watch for rules run in the service whenever a session's flow
changes, so they act while no console is open, and only then (an unchanged flow is not read again); the facts they
read are those of the agent role's slot (design 0012 §4: whatever model is loaded); the service answers the marks,
how many are not seen and marking them seen, and each flow's answer carries its own marks."""

from typing import Any

from fastapi.testclient import TestClient

from clank.components.agents.kinds import MonitorSettings
from clank.components.agents.watchfor.marks import Marks, slot_facts
from clank.components.agents.watchfor.rules import Facts
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from tests.components.agents.test_monitor_sessions import kernel  # noqa: F401  (a fixture, found by its name)
from tests.components.agents.test_session_flows_kept import WORKSPACE, FakeSessions, keeper
from tests.components.agents.test_watch_for_rules import LIMITS, bash, steps_with
from tests.support.flowlines import SESSION, lines, updated

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


def said_with(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events OpenCode sends for the owner's message and steps of these calls, one each."""
    return [event for message in steps_with(calls) for event in updated(message)]


def test_the_rules_run_when_a_flow_changes_while_no_console_is_open(kernel: Kernel) -> None:  # noqa: F811
    sessions = FakeSessions()
    flows = keeper(sessions)
    marks = Marks(MonitorSettings, kernel.clock, kernel.events)
    asked: list[int] = []

    def facts() -> Facts:
        asked.append(1)
        return LIMITS

    assert marks.watch(flows, facts) == 0
    assert asked == [], "nothing changed: the slot's facts are not read"
    sessions.say(said_with([bash("c1", "pytest -q"), bash("c2", "pytest -q")]))
    flows.work()
    assert marks.watch(flows, facts) == 1
    assert marks.marks() == []
    assert marks.watch(flows, facts) == 0, "an unchanged flow is not checked again"
    sessions.say(said_with([bash("c1", "pytest -q"), bash("c2", "pytest -q"), bash("c3", "pytest -q")]))
    assert marks.watch(flows, facts) == 1
    [made] = marks.marks()
    assert (made["rule"], made["workspace"], made["session"], made["node"]) == (
        "same_call_again", WORKSPACE, SESSION, "c3"
    )  # fmt: skip
    assert len(asked) == 2, "read once for each round that had a flow to check"


def test_the_routes_list_the_marks_mark_them_seen_and_a_flow_carries_its_own(kernel: Kernel) -> None:  # noqa: F811
    agents = kernel.parts["agents"]
    for line in lines(said_with([bash(f"c{n}", "pytest -q") for n in range(1, 4)])):
        agents.flows.heard(WORKSPACE, line)
    assert agents.marks.watch(agents.flows, lambda: LIMITS) == 1
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        listed = http.get("/api/v1/agents/marks", headers=AUTH).json()
        assert listed["unseen"] == 1
        [mark] = listed["marks"]
        assert (mark["rule"], mark["name"], mark["session"]) == ("same_call_again", "The same call again", SESSION)
        assert "3 times in the last 12" in mark["why"]
        assert [each["action"] for each in mark["did"]] == ["mark"]
        flow = http.get(f"/api/v1/agents/flow/{WORKSPACE}/{SESSION}", headers=AUTH).json()
        assert [each["id"] for each in flow["marks"]] == [mark["id"]]
        assert http.get("/api/v1/agents/marks?session=ses_other", headers=AUTH).json()["marks"] == []
        seen = http.post("/api/v1/agents/marks/seen", headers=AUTH, json={"ids": [mark["id"]]})
        assert seen.status_code == 200, seen.text
        assert seen.json() == {"seen": 1}
        assert http.get("/api/v1/agents/marks", headers=AUTH).json()["unseen"] == 0
    [event] = kernel.events.after(0, types=["agents.marks_seen"])
    assert (event.actor.kind, event.actor.via) == ("user", "cli")


def test_the_facts_come_from_the_agent_roles_slot(kernel: Kernel, monkeypatch: Any) -> None:  # noqa: F811
    main: dict[str, Any] = {"status": "ready", "context": 262_144, "output": 16_384, "thinking": 4096}
    routes: dict[str, Any] = {
        "slots": {
            "main": main,
            "fast": {"status": "ready", "context": 8192, "output": 256, "thinking": None},
        },
        "roles": {"agent": "main", "completion": "fast"},
        "default_slot": "main",
    }
    monkeypatch.setattr(kernel.parts["gateway"], "routes", lambda: routes)
    assert slot_facts(kernel)() == Facts(context=262_144, output=16_384, thinking=4096)
    main.update(status="stopped", context=None, output=None, thinking=None)
    assert slot_facts(kernel)() == Facts(), "no model runs: nothing is known"

    def broken() -> dict[str, Any]:
        raise RuntimeError("the runtime could not say")

    monkeypatch.setattr(kernel.parts["gateway"], "routes", broken)
    assert slot_facts(kernel)() == Facts()
