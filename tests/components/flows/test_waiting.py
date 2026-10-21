"""Design 0013 §2, §8, §9 and §10 (decision 0061): what a flow waits for, told the same way to every client. Each
question a flow's run waits for (a YOU box, a gate, a failed box, a batch of proposals) names its flow, run and box, the
files it shows (each with its place in the folder, the box that wrote it and the tries of that box that kept a copy of
it, so a client can diff the last two; a batch shows none), and the answers that take words; a VERIFY's loop gate shows
the file of the box it checks (board D3), and one more try's words go to that box; a question answered anywhere is no
longer listed. `GET
/api/v1/flows/waiting` lists them. A try's copy of a deliverable is read through `GET
/api/v1/flows/<workspace>/<name>/copy` as it was kept, from the try's folder only: a copy the try did not keep is
refused, saying why. Run against the fake bridge and a synthetic folder."""

import time
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows.verdicts import AGENT
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.questions import Question
from tests.components.flows.rig import (
    FLOW,
    OWNER,
    WORKSPACE,
    Rig,
    at_work,
    checked_study,
    make_rig,
    question,
    running,
    study,
    until,
)

pytestmark = pytest.mark.anyio
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


async def at_the_gate(rig: Rig, plans: list[str]) -> str:
    """The flow run to its gate, the plan written once for each text of `plans` (sent back between them): the gate's
    question."""
    rig.runner.start(FLOW, actor=OWNER)
    brief = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(brief.id, by=OWNER, option="done")
    gate: Question | None = None
    for number, text in enumerate(plans, start=1):
        if gate is not None:
            rig.kernel.questions.answer(gate.id, by=OWNER, option="back", text="Fewer points.")
        title = f"Study · plan · try {number}"
        plan = await until(partial(rig.bridge.prompted, title))
        rig.bridge.finish(plan.session, {"PLAN.md": text})
        gate = await until(lambda: question(rig, "You approve the plan"))
    assert gate is not None
    return gate.id


async def test_a_gate_names_its_flow_run_and_box_and_the_files_it_shows_with_the_tries_that_kept_a_copy(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# 240 points\n", "# 60 points\n"])
        [waits] = rig.kernel.parts["flows"].waiting()

    assert waits["question"] == gate
    assert (waits["flow"], waits["workspace"], waits["name"], waits["title"]) == (FLOW, WORKSPACE, "study", "Study")
    assert (waits["run"], waits["box"], waits["box_title"], waits["type"], waits["kind"]) == (
        1, "approve", "You approve the plan", "gate", "gate"
    )  # fmt: skip
    assert waits["folder"] == str(rig.folder)
    assert waits["files"] == [
        {"path": "PLAN.md", "file": str(rig.folder / "PLAN.md"), "box": "plan", "tries": [1, 2], "exists": True}
    ]
    assert set(waits["notes"]) == {"back"}, "a gate's send back takes a note; approve and stop take none"
    assert "plan" in waits["notes"]["back"], "the note says which box it is for"


async def test_a_you_box_names_the_files_the_owner_writes(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        brief = await until(lambda: question(rig, "Brief"))
        [waits] = rig.kernel.parts["flows"].waiting()

    assert (waits["question"], waits["box"], waits["type"], waits["kind"]) == (brief.id, "brief", "you", "you")
    assert waits["files"] == [
        {"path": "BRIEF.md", "file": str(rig.folder / "BRIEF.md"), "box": "brief", "tries": [], "exists": False}
    ]
    assert waits["notes"] == {}, "done and stop take no words"


async def test_a_failed_box_names_its_own_deliverables_and_try_again_takes_words(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        brief = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "About 60 grid points.\n")
        rig.kernel.questions.answer(brief.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {})
        failed = await until(lambda: question(rig, "failed"))
        [waits] = rig.kernel.parts["flows"].waiting()

    assert (waits["question"], waits["box"], waits["type"], waits["kind"]) == (failed.id, "plan", "plan", "failed")
    assert waits["files"] == [
        {"path": "PLAN.md", "file": str(rig.folder / "PLAN.md"), "box": "plan", "tries": [], "exists": False}
    ]
    assert set(waits["notes"]) == {"retry"}, "try again takes words for the next try"


async def test_a_question_answered_anywhere_is_no_longer_listed(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        assert [each["question"] for each in rig.kernel.parts["flows"].waiting()] == [gate]
        rig.kernel.questions.answer(gate, by=OWNER, option="approve")
        assert rig.kernel.parts["flows"].waiting() == [], "answered: listed nowhere, before the runner even moves on"
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


def test_the_route_lists_what_the_flows_wait_for(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        assert http.get("/api/v1/flows/waiting", headers=AUTH).json() == {"waiting": []}
        http.post("/api/v1/flows/myproject/study/run", headers=AUTH, json={})
        deadline = time.monotonic() + 10
        while not rig.waiting() and time.monotonic() < deadline:  # the service runs in its own thread
            time.sleep(0.02)
        listed = http.get("/api/v1/flows/waiting", headers=AUTH).json()["waiting"]
    assert [(each["box"], each["kind"]) for each in listed] == [("brief", "you")]


def copy(rig: Rig, status: int = 200, **asked: Any) -> Any:
    """A try's copy through the route, as VS Code asks for it (the service's routes only, its runner not started)."""
    app = create_app(rig.kernel, token="t", port=7720)
    answer = TestClient(app, base_url="http://127.0.0.1:7720").get(
        "/api/v1/flows/myproject/study/copy", headers=AUTH, params=asked
    )
    assert answer.status_code == status, answer.text
    return answer.json()


def refused(rig: Rig, status: int, **asked: Any) -> str:
    """Why the route refused a copy."""
    message: str = copy(rig, status, **asked)["error"]["message"]
    return message


async def test_each_trys_copy_is_read_as_it_was_kept_after_the_file_in_the_folder_moved_on(rig: Rig) -> None:
    async with running(rig.kernel):
        await at_the_gate(rig, ["# 240 points\n", "# 60 points\n"])
    rig.write("PLAN.md", "# 60 points, as the owner edited it at the gate\n")

    first = copy(rig, box="plan", file="PLAN.md", run=1, **{"try": 1})
    assert (first["run"], first["box"], first["try"], first["path"]) == (1, "plan", 1, "PLAN.md")
    assert first["text"] == "# 240 points\n"
    assert copy(rig, box="plan", file="PLAN.md", **{"try": 2})["text"] == "# 60 points\n", "the latest run by default"


async def test_a_copy_the_try_did_not_keep_is_refused_saying_why(rig: Rig) -> None:
    rig.write_flow(study(defaults={"copied_up_to": 20}))
    async with running(rig.kernel):
        await at_the_gate(rig, ["# short\n", "# a plan longer than twenty bytes\n"])

    assert "by its fingerprint only (34 bytes" in refused(rig, 409, box="plan", file="PLAN.md", **{"try": 2})
    assert "try 1 of plan did not write grid.json" in refused(rig, 409, box="plan", file="grid.json", **{"try": 1})
    assert "plan has no try 3" in refused(rig, 404, box="plan", file="PLAN.md", **{"try": 3})
    assert "no run 2" in refused(rig, 404, box="plan", file="PLAN.md", run=2, **{"try": 1})
    assert "did not write" in refused(rig, 409, box="plan", file="../../run.json", **{"try": 1}), "only its own files"


async def test_a_verify_loops_gate_shows_the_checked_boxs_file_and_its_tries(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(home, clock, tmp_path, monkeypatch, checked_study(2))
    try:
        async with running(rig.kernel):
            rig.runner.start(FLOW, actor=OWNER)
            brief = await until(lambda: question(rig, "Brief"))
            rig.write("BRIEF.md", "About 60 grid points.\n")
            rig.kernel.questions.answer(brief.id, by=OWNER, option="done")
            for number in (1, 2):
                plan = await until(partial(rig.bridge.prompted, f"Study · plan · try {number}"))
                rig.bridge.finish(plan.session, {"PLAN.md": f"# The plan, try {number}\n"})
                check = await at_work(rig, "check", number)
                rig.runner.verdict(
                    WORKSPACE, "fail", ["240 grid points where the brief allows about 60."], [], actor=AGENT
                )
                rig.bridge.finish(check.session)
            gate = await until(lambda: question(rig, "plan used its 2 tries"))
            [waits] = rig.kernel.parts["flows"].waiting()
    finally:
        rig.kernel.close()

    assert (waits["question"], waits["box"], waits["type"], waits["kind"]) == (gate.id, "check", "verify", "failed")
    assert waits["files"] == [
        {"path": "PLAN.md", "file": str(rig.folder / "PLAN.md"), "box": "plan", "tries": [1, 2], "exists": True}
    ], "the checked box's file, its last two tries to diff (board D3)"
    assert set(waits["notes"]) == {"retry"}
    assert "plan's next try" in waits["notes"]["retry"], "one more try's words go to the box it checks"


async def test_a_batch_of_proposals_the_run_waits_for_names_its_flow_run_and_box_and_shows_no_file(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        rig.kernel.questions.answer(gate, by=OWNER, option="approve")
        work = await at_work(rig, "T1")
        proposal = {"after": "T1", "type": "task", "title": "The estimates", "prompt": "Estimate each point.",
                    "deliverable": "runs/estimates.md"}  # fmt: skip
        rig.runner.proposing.propose(WORKSPACE, proposal, actor=AGENT)
        rig.runner.proposing.submit(WORKSPACE, "One more task.", actor=AGENT)
        rig.bridge.finish(work.session, {"grid.json": "[]\n"})
        asked = await until(lambda: question(rig, "proposed"))
        await until(lambda: rig.run().waiting is not None)
        [waits] = rig.kernel.parts["flows"].waiting()
    assert (waits["question"], waits["box"], waits["kind"]) == (asked.id, "T1", "proposals")
    assert (waits["files"], waits["notes"]) == ([], {}), "its proposals are told in its detail; none is a file yet"
