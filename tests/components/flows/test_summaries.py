"""Design 0025 §6 (design 0013 §12): one line per flow for a list, made by the service so every client says a flow's
state the same way and knows no rule of the runner: not run yet; queued behind another flow; running at a box, so many
of its boxes done; paused; waiting for you (a gate, your part, a failed box, a box done, proposals) at a box, with the
question's id; being built with the model, at its planning's state; done, approved by you when a gate passed;
stopped, with why. Each with the preset its running box uses (else the flow's default), and the run's time. The route
lists every flow, what waits for you first, then what runs, then what ended, newest first, and what never ran last."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows.building import Planning
from clank.components.flows.kinds import Flow
from clank.components.flows.runs import BoxRun, Run, Try, Waiting
from clank.components.flows.summaries import sort_key, summarize
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, WORKSPACE, Rig, make_rig, question, study

OWNER = Actor(kind="user", via="console")
NOW = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 26, 10, 30, tzinfo=UTC)
TITLES = {"fast": "Fast 32K", "frontier": "Frontier 262K"}
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


def flow(**changes: Any) -> Flow:
    values = {**study(defaults={"model": "fast"}), **changes}
    values.pop("schema")  # the file's, not a field
    return Flow.model_validate(values)


def run(status: str = "running", at: str = "plan", **more: Any) -> Run:
    boxes = more.pop(
        "boxes", {"brief": BoxRun(state="done"), "plan": BoxRun(state="running", tries=[Try(number=1, started=NOW)])}
    )
    return Run(
        flow=FLOW, number=1, workspace=WORKSPACE, version="1", status=status, at=at, started_by=OWNER, created=NOW,
        boxes=boxes, **more,
    )  # fmt: skip


def planning(status: str) -> Planning:
    return Planning(flow=FLOW, workspace=WORKSPACE, name="study", where="vscode", status=status, started=NOW, by=OWNER)


def test_a_flow_that_never_ran_says_so_with_its_default_model() -> None:
    line = summarize(FLOW, flow(), None, None, TITLES)
    assert (line["id"], line["workspace"], line["name"], line["title"]) == (FLOW, WORKSPACE, "study", "Study")
    assert (line["state"], line["words"]) == ("never", "not run yet")
    assert (line["model"], line["time"], line["question"], line["box"]) == ("Fast 32K", None, "", "")
    assert line["position"] == {"done": 0, "of": 4}


def test_a_running_flow_names_its_box_and_counts_the_boxes_done() -> None:
    line = summarize(FLOW, flow(), run(), None, TITLES)
    assert (line["state"], line["words"]) == ("running", "Write the plan · 1 of 4")
    assert (line["box"], line["box_title"], line["position"]) == ("plan", "Write the plan", {"done": 1, "of": 4})
    assert line["time"] == "2026-10-26T10:00:00.000Z"


def test_the_running_boxs_own_preset_is_the_models_title() -> None:
    boxes = study()["boxes"]
    boxes[1] = {**boxes[1], "model": "frontier"}
    line = summarize(FLOW, flow(boxes=boxes), run(), None, TITLES)
    assert line["model"] == "Frontier 262K"


def test_a_flow_waiting_for_you_says_what_at_which_box_with_its_question() -> None:
    gate = run(at="approve", waiting=Waiting(question="q-gate", kind="gate", box="approve"),
               boxes={"brief": BoxRun(state="done"), "plan": BoxRun(state="done")})  # fmt: skip
    line = summarize(FLOW, flow(), gate, None, TITLES)
    assert (line["state"], line["words"]) == ("waits", "waits for you: gate · You approve the plan")
    assert (line["question"], line["box"], line["position"]) == ("q-gate", "approve", {"done": 2, "of": 4})
    you = run(at="brief", waiting=Waiting(question="q-you", kind="you", box="brief"), boxes={})
    assert summarize(FLOW, flow(), you, None, TITLES)["words"] == "waits for you: your part · Brief"
    failed = run(at="plan", waiting=Waiting(question="q-f", kind="failed", box="plan"))
    assert summarize(FLOW, flow(), failed, None, TITLES)["words"] == "waits for you: a box failed · Write the plan"
    proposals = run(at="plan", waiting=Waiting(question="q-p", kind="proposals", box="plan"))
    assert summarize(FLOW, flow(), proposals, None, TITLES)["words"] == "waits for you: proposals · Write the plan"
    done = run(at="plan", waiting=Waiting(question="q-d", kind="done", box="plan"))
    assert summarize(FLOW, flow(), done, None, TITLES)["words"] == "waits for you: a box is done · Write the plan"


def test_a_paused_run_says_which_box_runs_on_and_a_queued_one_whom_it_waits_behind() -> None:
    paused = summarize(FLOW, flow(), run(paused=True), None, TITLES)
    assert (paused["state"], paused["words"]) == ("paused", "paused · Write the plan runs on")
    idle = run(paused=True, boxes={"brief": BoxRun(state="done")})
    assert summarize(FLOW, flow(), idle, None, TITLES)["words"] == "paused"
    queued = summarize(FLOW, flow(), run(status="queued", behind=f"{WORKSPACE}/survey", at=""), None, TITLES)
    assert (queued["state"], queued["words"]) == ("queued", "queued behind survey")


def test_a_done_run_says_when_a_gate_approved_it_and_a_stopped_one_why() -> None:
    approved = run(status="done", at="T1", ended=LATER, boxes={
        "brief": BoxRun(state="done"), "plan": BoxRun(state="done"), "approve": BoxRun(state="done"),
        "T1": BoxRun(state="done"),
    })  # fmt: skip
    line = summarize(FLOW, flow(), approved, None, TITLES)
    assert (line["state"], line["words"], line["time"]) == (
        "done",
        "done · approved by you",
        "2026-10-26T10:30:00.000Z",
    )
    plain = run(
        status="done", at="plan", ended=LATER, boxes={"brief": BoxRun(state="done"), "plan": BoxRun(state="done")}
    )
    assert summarize(FLOW, flow(), plain, None, TITLES)["words"] == "done"
    stopped = run(status="stopped", at="plan", ended=LATER, boxes={
        "brief": BoxRun(state="done"),
        "plan": BoxRun(
            state="failed", tries=[Try(number=1, started=NOW, ended=LATER, outcome="stopped", reason="by you")]
        ),
    })  # fmt: skip
    assert summarize(FLOW, flow(), stopped, None, TITLES)["words"] == "stopped: by you"
    quiet = run(status="stopped", at="plan", ended=LATER, boxes={})
    assert summarize(FLOW, flow(), quiet, None, TITLES)["words"] == "stopped"


def test_a_flow_being_built_says_its_plannings_state_until_it_runs() -> None:
    assert summarize(FLOW, flow(), None, planning("talking"), TITLES)["words"] == "building: talking it through"
    assert (
        summarize(FLOW, flow(), None, planning("waiting"), TITLES)["words"] == "building: waits for its OpenCode window"
    )
    assert summarize(FLOW, flow(), None, planning("opening"), TITLES)["words"] == "building: its session starts"
    built = summarize(FLOW, flow(), None, planning("built"), TITLES)
    assert (built["state"], built["words"]) == ("building", "building: written, look, then run")
    assert summarize(FLOW, flow(), None, planning("failed"), TITLES)["state"] == "never", (
        "a failed planning builds nothing"
    )
    assert summarize(FLOW, flow(), run(), planning("ran"), TITLES)["state"] == "running", "once it runs, the run says"


def test_the_list_puts_what_waits_for_you_first_then_what_runs_then_what_ended_newest_first() -> None:
    lines: list[dict[str, Any]] = [
        {"state": "never", "time": None},
        {"state": "done", "time": "2026-10-25T10:00:00.000Z"},
        {"state": "running", "time": "2026-10-26T09:00:00.000Z"},
        {"state": "stopped", "time": "2026-10-26T08:00:00.000Z"},
        {"state": "waits", "time": "2026-10-24T10:00:00.000Z"},
        {"state": "building", "time": None},
    ]
    assert [line["state"] for line in sorted(lines, key=sort_key)] == [
        "waits", "running", "building", "stopped", "done", "never",
    ]  # fmt: skip


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as client:
        yield client


def test_the_route_lists_every_flow_with_its_words_and_the_question_it_waits_for(rig: Rig, http: TestClient) -> None:
    listed = http.get("/api/v1/flows/summaries", headers=AUTH).json()["flows"]
    assert [(line["id"], line["state"], line["words"], line["problems"]) for line in listed] == [
        (FLOW, "never", "not run yet", 0)
    ]
    started = http.post(f"/api/v1/flows/{WORKSPACE}/study/run", headers=AUTH, json={})
    assert started.status_code == 200, started.text
    deadline = time.monotonic() + 10
    while not question(rig, "Brief"):
        assert time.monotonic() < deadline, "the YOU box never asked"
        time.sleep(0.02)
    asked = question(rig, "Brief")
    assert asked is not None
    [line] = http.get("/api/v1/flows/summaries", headers=AUTH).json()["flows"]
    assert (line["state"], line["words"], line["question"]) == ("waits", "waits for you: your part · Brief", asked.id)
    assert line["position"] == {"done": 0, "of": 4}
    assert http.get("/api/v1/flows/summaries", params={"workspace": "other"}, headers=AUTH).json()["flows"] == []
