"""Design 0012 §9.1, §9.4, §3 and §11 step 11 (decision 0055): the Guide's pause in the service. It pauses the root of
the session it is given (the Guide acts on the root session), through the gateway, each pause and resume an
`agents.acted` event with who did it; its state is pausing after this step, then held with its timer, then resumed; its
action says its key, what it does, its exact call, its cost and why it cannot run, and the Guide offers it after Compact
now, before Undo; a message sent to a paused session closes the request it holds, after the message was sent, and only
one held before it was sent, never the request that carries it; a Watch for rule set to pause pauses the session, as the
rule, through the Guide; and the routes pause, resume and refuse with the reason. The gateway is a fake here; the
sessions are synthetic."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.pausing import PauseError, Pausing
from clank.components.gateway.service import HoldError
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock, to_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents.test_monitor_sessions import kernel  # noqa: F401  (a fixture, found by its name)

WORKSPACE = "paper"
ROOT = "ses_root"
CHILD = "ses_child"
PORT = 4096
OWNER = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
SINCE = "2026-10-20T12:22:00.000Z"


class FakeHolds:
    """The gateway's holds as the service's gateway part gives them, and what it was asked."""

    def __init__(self) -> None:
        self.pauses: dict[str, dict[str, Any]] = {}
        self.held: dict[str, list[dict[str, Any]]] = {}
        self.asked: list[tuple[str, ...]] = []
        self.problem = ""

    def pause(self, session: str, by: str) -> dict[str, Any]:
        if self.problem:
            raise HoldError(self.problem)
        self.asked.append(("pause", session, by))
        already = session in self.pauses
        self.pauses.setdefault(session, {"session": session, "since": SINCE, "by": by})
        return {**self.pauses[session], "held": self.held.get(session, []), "already": already}

    def resume(self, session: str) -> dict[str, Any] | None:
        if self.problem:
            raise HoldError(self.problem)
        self.asked.append(("resume", session))
        found = self.pauses.pop(session, None)
        return None if found is None else {**found, "held": len(self.held.pop(session, []))}

    def release(self, session: str, before: str = "") -> int:
        self.asked.append(("release", session, before))
        return len(self.held.pop(session, []))

    def holds(self) -> dict[str, Any]:
        pauses = [{**pause, "held": self.held.get(session, [])} for session, pause in self.pauses.items()]
        return {"pauses": [] if self.problem else pauses, "problem": self.problem}


@pytest.fixture
def holds(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> FakeHolds:  # noqa: F811
    """The gateway part answering from a fake, and a session with a subagent, seen by the workspace's watcher."""
    fake = FakeHolds()
    gateway = kernel.parts["gateway"]
    for name in ("pause", "resume", "release", "holds"):
        monkeypatch.setattr(gateway, name, getattr(fake, name))
    sessions = kernel.parts["agents"].sessions
    sessions.heard(WORKSPACE, {"type": "session", "port": PORT, "session": {"id": ROOT, "title": "the work"}})
    sessions.heard(WORKSPACE, {"type": "session", "port": PORT,
                               "session": {"id": CHILD, "parent": ROOT, "title": "a subagent"}})  # fmt: skip
    sessions.heard(WORKSPACE, {"type": "status", "port": PORT, "session": ROOT, "status": "busy"})
    return fake


def pausing(kernel: Kernel) -> Pausing:  # noqa: F811
    found: Pausing = kernel.parts["agents"].pausing
    return found


def test_pausing_a_subagent_pauses_its_root_and_leaves_an_agents_acted_event(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
) -> None:
    paused = pausing(kernel).pause(WORKSPACE, CHILD, actor=OWNER)
    assert holds.asked == [("pause", ROOT, "you (console)")]
    assert (paused["session"], paused["state"]["state"]) == (ROOT, "pausing after this step")
    pausing(kernel).resume(WORKSPACE, CHILD, actor=OWNER)
    acted = kernel.events.after(0, types=["agents.acted"])
    assert [(event.data["action"], event.data["session"], event.data["port"]) for event in acted] == [
        ("pause", ROOT, PORT), ("resume", ROOT, PORT)
    ]  # fmt: skip
    assert {(event.actor.kind, event.actor.via) for event in acted} == {("user", "console")}
    assert acted[0].summary == "you (console) paused paper's agent (pause: its next requests held after this step)"


def test_the_pauses_state_is_pausing_after_this_step_then_held_with_its_timer_then_resumed(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
) -> None:
    assert pausing(kernel).state(WORKSPACE, ROOT)["state"] is None, "never paused"
    pausing(kernel).pause(WORKSPACE, ROOT, actor=OWNER)
    state = pausing(kernel).state(WORKSPACE, ROOT)["state"]
    assert (state["state"], state["time"], state["by"], state["seconds"]) == (
        "pausing after this step", SINCE, "you (console)", None
    )  # fmt: skip
    holds.held[ROOT] = [{"id": "r-1", "session": CHILD, "parent": ROOT, "since": SINCE, "seconds": 42.5}]
    state = pausing(kernel).state(WORKSPACE, CHILD)["state"]
    assert (state["state"], state["seconds"]) == ("held", 42.5)
    resumed = pausing(kernel).resume(WORKSPACE, ROOT, actor=OWNER)
    assert (resumed["state"]["state"], resumed["went"]) == ("resumed", 1)
    state = pausing(kernel).state(WORKSPACE, ROOT)["state"]
    assert (state["state"], state["by"]) == ("resumed", "you (console)")
    with pytest.raises(PauseError, match=f"{ROOT} is not paused"):
        pausing(kernel).resume(WORKSPACE, ROOT, actor=OWNER)


def test_the_pause_action_says_its_key_what_it_does_its_exact_call_and_its_cost(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
) -> None:
    action = pausing(kernel).action(WORKSPACE, CHILD)
    assert {key: action[key] for key in ("action", "key", "title", "can", "why", "confirm", "paused")} == {
        "action": "pause", "key": "p", "title": "Pause", "can": True, "why": "", "confirm": True, "paused": False,
    }  # fmt: skip
    assert action["brief"] == "after this step: its next request waits in the gateway"
    assert "the next model request" in action["does"]
    assert action["calls"] == [f'PUT /holds/{ROOT} {{"by": "<you>"}} (the gateway\'s)']
    assert action["cost"] == {"tokens": 0, "seconds": 0.0, "words": "nothing while held: nothing is read again"}
    pausing(kernel).pause(WORKSPACE, ROOT, actor=OWNER)
    action = pausing(kernel).action(WORKSPACE, ROOT)
    assert (action["title"], action["calls"], action["paused"]) == (
        "Resume", [f"DELETE /holds/{ROOT} (the gateway's)"], True
    )  # fmt: skip
    assert "goes to the model" in action["does"]
    holds.problem = "the gateway does not run"
    action = pausing(kernel).action(WORKSPACE, ROOT)
    assert (action["can"], action["why"]) == (False, "the gateway does not run")
    with pytest.raises(PauseError, match="Pause cannot run now: the gateway does not run"):
        pausing(kernel).pause(WORKSPACE, ROOT, actor=OWNER)


def test_the_guide_offers_the_pause_after_compact_now(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
) -> None:
    offered = kernel.parts["agents"].guide.offer(WORKSPACE, ROOT)
    assert [(each["action"], each["key"]) for each in offered["actions"]] == [
        ("stop", "."), ("note", "m"), ("compact", "k"), ("pause", "p"), ("undo", "u"), ("drop", "x")
    ], "the pause before Undo and Drop (step 10)"  # fmt: skip
    assert offered["actions"][3]["can"] is True


def test_a_message_sent_to_a_paused_session_closes_its_held_request(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = kernel.parts["agents"].sessions
    order: list[str] = []

    def bridge(workspace: str, argv: list[str], given: Any = None, timeout: float = 0) -> dict[str, Any]:
        order.append(argv[0])
        return {"ok": True}

    monkeypatch.setattr(sessions, "_bridge", bridge)
    holds.pauses[ROOT] = {"session": ROOT, "since": SINCE, "by": "you (console)"}
    holds.held[ROOT] = [{"id": "r-1", "session": ROOT, "parent": "", "since": SINCE, "seconds": 3.0}]
    real = holds.release

    def release(session: str, before: str = "") -> int:
        order.append("release")
        return real(session, before)

    monkeypatch.setattr(kernel.parts["gateway"], "release", release)
    sessions.send(WORKSPACE, PORT, ROOT, "About step 3: skip it.", actor=OWNER)
    assert order == ["prompt", "release"], "the note is sent first, then its hold closed"
    assert [asked[:2] for asked in holds.asked] == [("release", ROOT)]
    assert ROOT in holds.pauses, "the pause stays"


def test_a_messages_release_closes_only_what_was_held_before_the_message_was_sent(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = kernel.parts["agents"].sessions
    before = to_text(clock.now())

    def bridge(workspace: str, argv: list[str], given: Any = None, timeout: float = 0) -> dict[str, Any]:
        clock.advance(2)  # the bridge's round trip: OpenCode stored the message, and may already ask again
        return {"ok": True}

    monkeypatch.setattr(sessions, "_bridge", bridge)
    sessions.send(WORKSPACE, PORT, ROOT, "About step 3: skip it.", actor=OWNER)
    assert holds.asked == [("release", ROOT, before)], "a request held since then may carry the message: it stays held"


def test_a_rule_set_to_pause_pauses_the_session_through_the_gateway(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acting = kernel.parts["agents"].marks.acting
    acting.pause(WORKSPACE, CHILD)
    assert holds.asked == [("pause", ROOT, "Clank (watch for)")]
    [event] = kernel.events.after(0, types=["agents.acted"])
    assert (event.actor.kind, event.actor.via) == ("clank", "watch for")
    noted: list[tuple[str, str, str]] = []
    monkeypatch.setattr(kernel.parts["agents"].guide, "note",
                        lambda workspace, session, text, **given: noted.append((workspace, session, text)))  # fmt: skip
    acting.note(WORKSPACE, PORT, ROOT, "Stop repeating it.")
    assert noted == [(WORKSPACE, ROOT, "Stop repeating it.")], "its note still goes through the Guide (step 9)"


def test_the_routes_pause_and_resume_and_refuse_with_the_reason(
    kernel: Kernel,  # noqa: F811
    holds: FakeHolds,
) -> None:
    app = create_app(kernel, token="t", port=7720)
    route = f"/api/v1/agents/guide/{WORKSPACE}/{ROOT}"
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        shown = http.get(f"{route}/pause", headers=AUTH)
        assert shown.status_code == 200, shown.text
        assert (shown.json()["key"], shown.json()["can"]) == ("p", True)
        paused = http.post(f"{route}/pause", headers=AUTH)
        assert paused.status_code == 200, paused.text
        assert paused.json()["state"]["state"] == "pausing after this step"
        resumed = http.post(f"{route}/resume", headers=AUTH)
        assert resumed.status_code == 200, resumed.text
        refused = http.post(f"{route}/resume", headers=AUTH)
        assert refused.status_code == 409
        assert f"{ROOT} is not paused" in refused.json()["error"]["message"]
        holds.problem = "the gateway does not run"
        refused = http.post(f"{route}/pause", headers=AUTH)
        assert refused.status_code == 409
        assert "the gateway does not run" in refused.json()["error"]["message"]
    assert holds.asked[:2] == [("pause", ROOT, "you (console)"), ("resume", ROOT)]
