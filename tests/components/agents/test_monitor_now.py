"""Design 0012 §5 and §11 step 7: what a session does now, as the service says it for the Monitor's Now panel. Every
row of §5.1's phase table is said from its source (the gateway for its requests, OpenCode for the session), and a
request the engine has not answered yet is "reading the prompt (or queued)", never claimed queued alone (§5.1). The
thinking and the answer are shown against their budgets, from the slot's facts (§5.2, decision 0067): live counts say
"about", and once the answer ended its count is the engine's own and the thinking's is scaled to it, still "about". The
prompt is this step's time to its first token and the previous step's size and cache share (§5.3); the speed keeps each
step's; the call being written is the gateway's (§5.3); and the loop guard says whether it is on as the running gateway
applies it (a change to its settings file waits for its restart, which is said), each part's newest share against its
ratio, or what it stopped (§5.4). The sessions here are synthetic."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.now import PHASES, now
from clank.components.gateway.kinds import GatewaySettings
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import SESSION, doing, ended, facts_of, route
from tests.fakes.platform import FakePlatform

MOMENT = 1_800_000_000.0  # now, in seconds since the epoch
ON = {"on": True, "ratio": 0.06}


def flying(phase: str = "answering", **fields: Any) -> dict[str, Any]:
    """The session's request in flight, as the gateway's activity gives it."""
    counts = fields.pop("counts", {"thinking": 0, "answer": 0, "tool": 0})
    return {"id": "r-9", "time": "2026-10-19T12:31:00.000000Z", "role": "agent", "slot": "main", "session": SESSION,
            "parent": "", "phase": phase, "seconds": 36.1, "tokens": sum(counts.values()), "counts": counts,
            "per_second": 48.0, "loop_guard": {"ratio": 0.06, "parts": []}, "calls": [], "held": None,
            "first_ms": 1000.0, "newest": "", "writing": None, **fields}  # fmt: skip


def view(status: str = "busy", *nodes: dict[str, Any], **head: Any) -> dict[str, Any]:
    """The session's flow, as the service keeps it: its head and its nodes in time order."""
    return {"head": {"session": SESSION, "status": status, **head}, "nodes": list(nodes), "items": [], "version": 1}


def a_step(n: int, ended: str = "working") -> dict[str, Any]:
    return {"id": f"msg_{n}", "kind": "step", "n": n, "ended": ended, "undone": False}


def a_call(tool: str = "bash", status: str = "running", **fields: Any) -> dict[str, Any]:
    return {"id": "prt_1", "kind": "call", "tool": tool, "status": status, "title": "", "input": "", "asking": "",
            "permission": "", "started": (MOMENT - 4) * 1000, "undone": False, **fields}  # fmt: skip


def said(
    gateway: dict[str, Any], flow: dict[str, Any] | None, guard: dict[str, Any] = ON, preset: str = "daily-262k"
) -> dict[str, Any]:
    return now(SESSION, gateway, flow, route(preset), facts_of, guard, MOMENT)


def with_requests(*requests: dict[str, Any], ended_too: tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    return {**doing(*ended_too), "requests": list(requests)}


@pytest.mark.parametrize(
    ("gateway", "flow", "state", "phase", "source"),
    [
        (with_requests(flying("waiting for its slot")), view(), "slot", "waiting for its slot", "gateway"),
        (with_requests(flying("reading the prompt")), view(), "reading", "reading the prompt (or queued)", "gateway"),
        (with_requests(flying(newest="thinking")), view(), "thinking", "thinking", "gateway"),
        (with_requests(flying(newest="answer")), view(), "answering", "answering", "gateway"),
        (with_requests(flying(newest="tool", writing={"tool": "bash", "arguments": '{"command": "ls'})), view(),
         "writing", "writing a call", "gateway"),
        (with_requests(flying("waiting for its engine to start again")), view(), "again",
         "waiting for its engine to start again", "gateway"),
        (with_requests(), view("busy", a_step(3), a_call(title="Run the tests")), "tool", "running a tool", "OpenCode"),
        (with_requests(), view("busy", a_step(3), a_call(asking="per_1", permission="edit")), "you", "waiting for you",
         "OpenCode"),
        (with_requests(), view("busy", a_step(3), a_call("question", "running")), "you", "waiting for you", "OpenCode"),
        (with_requests(), view("retry", attempt=2, retry="Provider is overloaded", next=(MOMENT + 8) * 1000), "retry",
         "retrying", "OpenCode"),
        (with_requests(flying(newest="answer")), view("busy", {"id": "c", "kind": "band", "done": False}),
         "compacting", "compacting", "OpenCode"),
        (with_requests(flying("held: its session is paused", held={"session": SESSION, "by": "you (console)",
                                                                    "since": "2026-10-19T12:22:00Z"})),
         view(), "held", "held", "gateway"),
        (doing(ended("r-1", 9000, 300, looped="its thinking repeated itself")), view("idle", a_step(3, "failed")),
         "looped", "stopped by the loop guard", "gateway"),
        (with_requests(), view("idle", a_step(3, "finished")), "idle", "idle", "OpenCode"),
        (with_requests(), view("busy", a_step(3, "finished")), "between", "working, between its steps", "OpenCode"),
    ],
)  # fmt: skip
def test_each_row_of_the_phase_table_is_said_from_its_source(
    gateway: dict[str, Any], flow: dict[str, Any], state: str, phase: str, source: str
) -> None:
    shown = said(gateway, flow)
    assert (shown["state"], shown["phase"], shown["source"]) == (state, phase, source)
    assert PHASES[state] == phase


def test_each_phase_says_its_detail_and_whether_it_works() -> None:
    tool = said(with_requests(), view("busy", a_step(3), a_call(title="Run the tests", input='{"command": "pytest"}')))
    assert tool["call"] == {"tool": "bash", "title": "Run the tests", "input": '{"command": "pytest"}'}
    assert (tool["seconds"], tool["working"], tool["step"]) == (4.0, True, 3), "since the call started"
    asks = said(with_requests(), view("busy", a_step(3), a_call("edit", asking="per_1", permission="edit")))
    assert (asks["detail"], asks["working"]) == ("edit asks for your approval (edit)", False)
    retry = said(with_requests(), view("retry", attempt=2, retry="Provider is overloaded", next=(MOMENT + 8) * 1000))
    assert retry["detail"] == "attempt 2 of at most 5, the next in 8 s: Provider is overloaded"
    held = said(
        with_requests(
            flying(
                "held: its session is paused",
                seconds=180.0,
                held={"session": SESSION, "by": "you (console)", "since": "12:22"},
            )
        ),
        view(),
    )
    assert (held["detail"], held["seconds"], held["working"]) == ("the Guide paused it (you (console))", 180.0, False)
    looped = said(doing(ended("r-1", 9000, 300, looped="its thinking repeated itself")), view("idle"))
    assert looped["detail"] == "the session is idle; that text is not in the context"
    assert not looped["working"]
    nothing = said(doing(), None)
    assert (nothing["state"], nothing["step"]) == ("idle", None), "no flow kept: OpenCode's status not known"


def test_reading_the_prompt_is_said_or_queued_and_queued_is_never_claimed_alone() -> None:
    reading = said(with_requests(flying("reading the prompt", seconds=3.2, first_ms=None)), view())
    assert reading["phase"] == "reading the prompt (or queued)"
    assert (reading["prompt"]["reading"], reading["seconds"]) == (True, 3.2)
    for phase in PHASES.values():
        assert "queued" not in phase.replace("(or queued)", ""), phase


def test_live_counts_say_about_and_the_answers_end_corrects_them_from_the_engines_count() -> None:
    counts = {"thinking": 1203, "answer": 40, "tool": 172}
    live = said(with_requests(flying(newest="answer", counts=counts)), view())
    assert live["thinking"] == {"tokens": 1203, "about": True, "budget": 4096}
    assert live["output"] == {"tokens": 1415, "about": True, "budget": 16384}, "its thinking, text and calls"
    assert live["of"] == "this step"
    finished = {**ended("r-9", 150000, 1502), "counts": counts}  # the engine counted 1,502; 1,415 were heard
    end = said(doing(finished), view("idle", a_step(30, "finished")))
    assert end["output"] == {"tokens": 1502, "about": False, "budget": 16384}, "the engine's own count"
    assert end["thinking"] == {"tokens": round(1203 * 1502 / 1415), "about": True, "budget": 4096}, (
        "scaled to the engine's count: usage has no count of its own for the thinking"
    )
    assert end["of"] == "the last step"
    unreported = {**finished, "usage": None}
    shown = said(doing(unreported), view("idle"))
    assert shown["output"] == {"tokens": 1502, "about": True, "budget": 16384}, "no count of the engine's: about"
    cpu = said(with_requests(flying(newest="thinking", counts=counts)), view(), preset="cpu-8k")
    assert cpu["thinking"]["budget"] is None, "an engine with no thinking budget: none shown"
    assert cpu["output"]["budget"] == 1024, "the facts of the slot the request went to"


def test_the_prompt_is_this_steps_time_and_the_previous_steps_size_and_the_speed_keeps_each_steps() -> None:
    before = (ended("r-1", 100000, 900, cached=96000, per_second=41.0),
              ended("r-2", 153614, 1415, cached=147815, per_second=47.5))  # fmt: skip
    shown = said(with_requests(flying(newest="answer", first_ms=1000.0, per_second=48.0), ended_too=before), view())
    assert shown["prompt"] == {"first_ms": 1000.0, "reading": False, "tokens": 153614, "cached": 147815,
                               "of": "the previous step"}  # fmt: skip
    assert shown["speed"] == {"now": 48.0, "steps": [41.0, 47.5, 48.0]}
    idle = said(doing(*before), view("idle"))
    assert idle["prompt"]["of"] == "the last step"
    assert idle["speed"] == {"now": 47.5, "steps": [41.0, 47.5]}


def test_the_call_being_written_is_the_gateways() -> None:
    writing = {"tool": "bash", "arguments": '{"command": "python -m myproject'}
    shown = said(with_requests(flying(newest="tool", writing=writing)), view())
    assert shown["writing"] == writing
    assert said(with_requests(flying(newest="answer")), view())["writing"] is None


def test_the_loop_guard_says_off_watching_each_parts_share_or_what_it_stopped() -> None:
    off = said(with_requests(flying(newest="answer", loop_guard=None)), view(), guard={"on": False, "ratio": 0.06})
    assert (off["guard"]["on"], off["guard"]["said"]) == (False, "off")
    parts = [{"part": "thinking", "name": "", "share": 0.31, "stretch": 2000},
             {"part": "tool 0", "name": "bash", "share": 0.12, "stretch": 2000}]  # fmt: skip
    watching = said(with_requests(flying(newest="tool", loop_guard={"ratio": 0.06, "parts": parts})), view())
    assert watching["guard"] == {"on": True, "ratio": 0.06, "parts": parts, "stopped": "",
                                 "said": "watching · nothing repeats", "restart": False}  # fmt: skip
    reading = said(with_requests(flying("reading the prompt", loop_guard=None)), view())
    assert reading["guard"]["said"] == "watching · nothing written yet"
    unread = said(with_requests(flying(newest="answer", loop_guard=None)), view())
    assert unread["guard"]["said"] == "not reading this answer: it is not streamed"
    stopped_gateway = said({**doing(), "state": "stopped"}, view("idle"))
    assert stopped_gateway["guard"]["said"] == "the gateway is stopped"
    stopped = said(doing(ended("r-1", 9000, 300, looped="its thinking repeated itself (its newest 2,000 characters)")),
                   view("idle"))  # fmt: skip
    assert stopped["guard"]["stopped"] == "its thinking repeated itself (its newest 2,000 characters)"
    assert (
        stopped["guard"]["said"]
        == "stopped the last answer: its thinking repeated itself (its newest 2,000 characters)"
    )


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def test_the_route_says_what_the_followed_session_does_now(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = kernel.parts["gateway"]
    asked: list[tuple[Any, ...]] = []

    def activity(session: str = "", subagents: bool = False, ended_too: bool = False) -> dict[str, Any]:
        asked.append((session, subagents, ended_too))
        return with_requests(flying(newest="thinking", counts={"thinking": 900, "answer": 0, "tool": 0}))

    monkeypatch.setattr(gateway, "activity", activity)
    monkeypatch.setattr(gateway, "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(gateway, "facts", facts_of)
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:
        answer = http.get(f"/api/v1/agents/now/myproject/{SESSION}", headers={"Authorization": "Bearer t"})
    assert answer.status_code == 200, answer.text
    shown = answer.json()
    assert (shown["workspace"], shown["session"], shown["state"]) == ("myproject", SESSION, "thinking")
    assert shown["thinking"] == {"tokens": 900, "about": True, "budget": 4096}
    assert (shown["guard"]["on"], shown["guard"]["ratio"]) == (True, 0.06), "the gateway's settings"
    assert asked == [(SESSION, False, True)], "the session's own requests, with those that ended"


def test_the_loop_guard_is_said_as_the_running_gateway_applies_it_and_a_change_waiting_for_its_restart_too(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = kernel.parts["gateway"]
    applied: dict[str, Any] = {"on": False, "ratio": 0.06}
    request = flying(newest="answer", loop_guard=None)
    monkeypatch.setattr(gateway, "activity", lambda session="", subagents=False, ended=False: {
        **with_requests(request), "guard": applied})  # fmt: skip
    monkeypatch.setattr(gateway, "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(gateway, "facts", facts_of)
    monkeypatch.setattr(gateway, "settings", lambda: GatewaySettings(loop_guard=True))
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:

        def guard() -> dict[str, Any]:
            answer = http.get(f"/api/v1/agents/now/myproject/{SESSION}", headers={"Authorization": "Bearer t"})
            assert answer.status_code == 200, answer.text
            found: dict[str, Any] = answer.json()["guard"]
            return found

        off = guard()
        assert (off["on"], off["said"], off["restart"]) == (False, "off", True), "the file's on waits for a restart"
        applied.update(on=True, ratio=0.08)
        monkeypatch.setattr(gateway, "settings", lambda: GatewaySettings(loop_guard=False))
        on = guard()
        assert (on["on"], on["ratio"], on["restart"]) == (True, 0.08, True), "it still guards, at its own ratio"
        monkeypatch.setattr(gateway, "settings", lambda: GatewaySettings(loop_guard=True, loop_ratio=0.08))
        assert guard()["restart"] is False
        monkeypatch.setattr(gateway, "activity", lambda session="", subagents=False, ended=False: {
            **with_requests(request), "state": "stopped"})  # fmt: skip
        stopped = guard()
        assert (stopped["on"], stopped["restart"]) == (True, False), "stopped: the file's, which its start applies"
