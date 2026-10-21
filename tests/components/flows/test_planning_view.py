"""Design 0013 §12 and §15 (decision 0101): the Flow view shows a planning while it is open. A folder's view follows
its workspace's open planning (waiting, opening, talking, or failed with no run started since) before a flow that ran;
its steps say it started, what it waits for (`clank flow attach`), the session's tool calls so far, that it waits for
the owner's answer, `BRIEF.md` written with its time, and each draft refused with its problems or accepted; the latest
draft is drawn with the view's own layout and marked as a draft even when refused, as far as it reads; with none yet,
nothing is drawn; once a draft is accepted, the view is the built flow."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.building import BuildError, Building
from clank.components.flows.verdicts import AGENT
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import OWNER, Rig, make_rig, study
from tests.components.flows.test_flow_built import drafted

BRIEF = "# A new simulation study\n\n- at most 48 CPU-hours\n"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, None)
    yield made
    made.kernel.close()


def building(rig: Rig) -> Building:
    found: Building = rig.kernel.parts["flows"].building
    return found


def view(rig: Rig) -> dict[str, Any]:
    shown: dict[str, Any] = rig.kernel.parts["flows"].view(str(rig.folder))
    return shown


def session_flow(monkeypatch: pytest.MonkeyPatch, rig: Rig, head: dict[str, Any], nodes: list[dict[str, Any]]) -> None:
    """The planning session's flow as the agents keep it (made up: nothing runs)."""
    monkeypatch.setattr(rig.kernel.parts["agents"].flows, "view", lambda workspace, session: {"head": head,
                        "nodes": nodes} if session == "ses_plan" else None)  # fmt: skip


def talking(rig: Rig) -> str:
    """A planning opened to attach, its session started: its flow's id."""
    flow = building(rig).open("myproject", "", "attach", actor=OWNER)["flow"]
    building(rig)._change(flow, status="talking", session="ses_plan", port=4096)
    return str(flow)


def test_the_folders_view_follows_an_open_planning_before_a_flow_that_ran_and_says_what_it_waits_for(
    rig: Rig,
) -> None:
    rig.write_flow(study())
    rig.write("BRIEF.md", BRIEF)
    rig.runner.start("myproject/study", actor=OWNER)
    rig.runner.stop("myproject/study", actor=OWNER)
    rig.clock.advance(60)
    building(rig).open("myproject", "", "attach", actor=OWNER)
    shown = view(rig)
    assert shown["flow"] == "myproject/flow"
    assert shown["boxes"] == [], "no draft yet: nothing drawn"
    assert shown["draft"] is None
    planning = shown["planning"]
    assert (planning["status"], planning["attach"]) == ("waiting", f"cd {rig.folder} then clank flow attach")
    assert [step["kind"] for step in planning["steps"]] == ["started", "waits"]
    assert "clank flow attach" in planning["steps"][1]["said"]

    building(rig)._failed("myproject/flow", "no OpenCode window answered on port 4096")
    assert view(rig)["planning"]["steps"][-1]["said"].endswith("no OpenCode window answered on port 4096")
    rig.clock.advance(60)
    rig.runner.start("myproject/study", actor=OWNER)
    assert view(rig).get("planning") is None, "a failed planning, a run started since: the flow is followed again"


def test_its_steps_say_the_calls_so_far_the_answer_it_waits_for_the_brief_and_each_draft(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    talking(rig)
    step = {"kind": "step", "finish": "tool-calls", "ended": "finished", "together": 2}
    session_flow(monkeypatch, rig, {"status": "busy", "calls": 7, "steps": 3}, [step])
    planning = view(rig)["planning"]
    assert planning["session"] == {"workspace": "myproject", "session": "ses_plan", "port": 4096}
    said = [step["said"] for step in planning["steps"]]
    assert "reading the folder: 7 tool calls so far" in said
    assert "waiting for your answer" not in said

    session_flow(monkeypatch, rig, {"status": "idle", "calls": 7, "steps": 4},
                 [step, {**step, "finish": "stop", "together": 0}])  # fmt: skip
    assert view(rig)["planning"]["steps"][-1]["said"] == "waiting for your answer"
    question = {"kind": "call", "tool": "question", "status": "running"}
    session_flow(monkeypatch, rig, {"status": "busy", "calls": 8, "steps": 5}, [step, question])
    assert view(rig)["planning"]["steps"][-1]["said"] == "waiting for your answer", "its question waits"

    rig.write("BRIEF.md", BRIEF)
    brief = next(step for step in view(rig)["planning"]["steps"] if step["kind"] == "brief")
    assert brief["said"] == "BRIEF.md written"
    assert brief["at"]

    broken = drafted(title="The study")
    broken["boxes"][1]["when_done"] = "wait"
    with pytest.raises(BuildError):
        building(rig).draft("myproject", broken, actor=AGENT)
    shown = view(rig)
    drafts = [step for step in shown["planning"]["steps"] if step["kind"] == "draft"]
    assert [(each["number"], each["state"]) for each in drafts] == [(1, "refused")]
    assert any(problem.startswith("boxes.1.when_done:") for problem in drafts[0]["problems"])
    assert shown["draft"]["number"] == 1
    assert shown["draft"]["state"] == "refused"
    assert [box["id"] for box in shown["boxes"]] == ["brief", "plan", "check", "split", "join", "review"], "drawn"
    assert shown["title"] == "The study"


def test_a_draft_that_breaks_a_flows_rules_is_drawn_as_far_as_it_reads(rig: Rig) -> None:
    talking(rig)
    rig.write("BRIEF.md", BRIEF)
    draft = drafted()
    draft["lines"].append({"from": "join", "to": "nowhere"})
    draft["boxes"].append({"id": "extra", "type": "gate"})  # no title: it does not read
    with pytest.raises(BuildError):
        building(rig).draft("myproject", draft, actor=AGENT)
    shown = view(rig)
    assert shown["draft"]["state"] == "refused"
    assert [box["id"] for box in shown["boxes"]] == ["brief", "plan", "check", "split", "join", "review"]
    assert all(line["to"] != "nowhere" for line in shown["lines"])


def test_once_a_draft_is_accepted_the_view_is_the_built_flow(rig: Rig) -> None:
    flow = talking(rig)
    rig.write("BRIEF.md", BRIEF)
    building(rig).draft("myproject", drafted(title="The study"), actor=AGENT)
    shown = view(rig)
    assert shown.get("planning") is None
    assert shown["flow"] == flow
    assert shown["built"]["status"] == "built"
