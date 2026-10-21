"""Design 0013 §9, §10 and §14 step 7 (design 0005 §4, design 0002 §2.5): gates and proposals on the phone. The phone
lists a question a flow waits for under its flow, with its box and the files it shows; reads a file it shows as it
stands in the folder (what an approval takes), and only those, never through a link that leads out of the folder; and
answers it, with a note for the answers that take
words (send back's), the note reaching the box's next first message and the answer recorded as the device's. A batch
of proposals asked about a flow, as step 4 asks it, is listed under its flow and answered there. A question is answered
once, from any client: one answered in VS Code leaves the phone's list and the phone's answer is refused, naming who
answered; one answered on the phone leaves the service's waiting questions and what the flows wait for. The page's
script draws a flow's question with its files and its note. While no question is about a flow, the phone's overview
reads no run's file. Run against the fake bridge and a synthetic folder."""

import shutil
import subprocess
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import anyio.to_thread
import httpx2
import pytest
from fastapi.testclient import TestClient

from clank.components.remote import tailnet
from clank.components.remote.app import create_phone_app
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, Subject
from clank.kernel.home import Home
from clank.kernel.processes import background_flags
from clank.kernel.questions import Option, QuestionDraft
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
LOGIN = "owner@example.com"
THROUGH_TAILSCALE = {"Tailscale-User-Login": LOGIN}
ACT = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}
VSCODE = Actor(kind="user", via="vscode")
PAGE = Path(create_phone_app.__code__.co_filename).parent / "page" / "app.js"
BASE = "https://desk.tail0.ts.net:8445"
LOOPBACK = ("127.0.0.1", 50000)


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    monkeypatch.setattr(made.kernel.parts["remote"], "owner_login", lambda: LOGIN)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", LOGIN))
    yield made
    made.kernel.close()


@pytest.fixture
def phone(rig: Rig) -> Iterator[TestClient]:
    app = create_phone_app(rig.kernel.parts["remote"])
    with TestClient(app, base_url=BASE, client=LOOPBACK) as client:
        code = rig.kernel.parts["remote"].pair("my phone", actor=OWNER)["code"]
        assert client.post("/api/pair", json={"code": code}, headers=ACT).status_code == 200
        yield client


async def at_the_gate(rig: Rig, plans: list[str]) -> str:
    """The flow run to its gate, the plan written once for each text (sent back between them): the gate's question."""
    rig.runner.start(FLOW, actor=OWNER)
    brief = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(brief.id, by=OWNER, option="done")
    gate = ""
    for number, text in enumerate(plans, start=1):
        if gate:
            rig.kernel.questions.answer(gate, by=OWNER, option="back", text="Fewer points.")
        plan = await until(partial(rig.bridge.prompted, f"Study · plan · try {number}"))
        rig.bridge.finish(plan.session, {"PLAN.md": text})
        asked = await until(lambda: question(rig, "You approve the plan"))
        gate = asked.id
    return gate


async def call(phone: TestClient, method: str, path: str, **asked: Any) -> httpx2.Response:
    """The phone's request, made off the test's event loop: the flows' runner runs on it, and an answer nudges it."""
    headers = ACT if method == "POST" else THROUGH_TAILSCALE
    answer: httpx2.Response = await anyio.to_thread.run_sync(
        lambda: phone.request(method, path, headers=headers, **asked)
    )
    return answer


async def listed(phone: TestClient) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = (await call(phone, "GET", "/api/overview")).json()["questions"]
    return found


async def test_the_phone_lists_a_gate_under_its_flow_with_its_box_and_the_files_it_shows(
    rig: Rig, phone: TestClient
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# 240 points\n", "# 60 points\n"])
        [shown] = await listed(phone)

    assert shown["id"] == gate
    assert shown["flow"] == {
        "flow": FLOW, "title": "Study", "run": 1, "box": "approve", "box_title": "You approve the plan",
        "type": "gate", "kind": "gate",
        "files": [{"path": "PLAN.md", "box": "plan", "tries": [1, 2], "exists": True}],
        "notes": {"back": "Your note for plan's next try: what to change (optional)."},
    }  # fmt: skip
    back = next(option for option in shown["options"] if option["id"] == "back")
    assert "plan runs try 3 of 3, its last," in back["effect"], "what each answer does"


async def test_the_phone_reads_a_file_a_gate_shows_as_it_stands_in_the_folder_and_only_those(
    rig: Rig, phone: TestClient
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        rig.write("PLAN.md", "# The plan, as the owner edited it at the gate\n")
        read = await call(phone, "GET", f"/api/flow-files/{gate}/0")
        assert read.status_code == 200, read.text
        assert read.json() == {
            "path": "PLAN.md", "box": "plan", "size": 47, "text": "# The plan, as the owner edited it at the gate\n",
            "why": "",
        }  # fmt: skip
        assert (await call(phone, "GET", f"/api/flow-files/{gate}/1")).status_code == 404
        assert (await call(phone, "GET", "/api/flow-files/q-nothing/0")).status_code == 404
        with TestClient(create_phone_app(rig.kernel.parts["remote"]), base_url=BASE, client=LOOPBACK) as stranger:
            assert (await call(stranger, "GET", f"/api/flow-files/{gate}/0")).status_code == 401, "a device not paired"

        rig.write("PLAN.md", "x" * 40_001)
        large = (await call(phone, "GET", f"/api/flow-files/{gate}/0")).json()
        assert large["text"] is None
        assert "40,001 bytes, more than the phone is shown (40,000)" in large["why"]
        rig.kernel.questions.answer(gate, by=OWNER, option="stop")
        await until(lambda: rig.run().status == "stopped")
        assert (await call(phone, "GET", f"/api/flow-files/{gate}/0")).status_code == 404, "answered: gone"


async def test_send_back_from_the_phone_carries_its_note_to_the_boxs_next_first_message(
    rig: Rig, phone: TestClient
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# 240 points\n"])
        body = {"option": "back", "text": "  About 60 points, as the brief says.  "}
        answered = await call(phone, "POST", f"/api/clank-questions/{gate}", json=body)
        assert answered.status_code == 200, answered.text
        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))

    assert "About 60 points, as the brief says." in again.text
    [event] = [each for each in rig.events("question.answered") if each.subject and each.subject.id == gate]
    assert (event.actor.kind, event.actor.via) == ("device", "my phone")


async def test_a_batch_of_proposals_asked_about_a_flow_is_listed_under_its_flow_and_answered_there(
    rig: Rig, phone: TestClient
) -> None:
    draft = QuestionDraft(
        type="choice",
        title="Study: Break it into tasks proposes 4 boxes",
        detail="1 · TASK T1 The grid\n2 · TASK T2 The sweep\n3 · TASK T3 Dry runs\n4 · TASK T4 Estimates",
        options=[
            Option(id="accept_all", label="Accept them all", effect="T1-T4 join the flow, in this order.", key="A"),
            Option(id="reject_all", label="Reject them all", effect="None of them runs.", key="x"),
        ],
        about=Subject(kind="flow", id=FLOW),
    )
    batch = rig.kernel.questions.ask(draft, asked_by=Actor(kind="clank", via="flow runner"))
    [shown] = await listed(phone)
    assert (shown["id"], shown["title"]) == (batch.id, "Study: Break it into tasks proposes 4 boxes")
    assert shown["flow"] == {"flow": FLOW, "title": "Study", "kind": "", "files": [], "notes": {}}
    assert "4 · TASK T4 Estimates" in shown["detail"]
    answered = await call(phone, "POST", f"/api/clank-questions/{batch.id}", json={"option": "accept_all"})
    assert answered.status_code == 200, answered.text
    settled = rig.kernel.questions.get(batch.id)
    assert settled.answer is not None
    assert (settled.answer.option, settled.answer.by.kind) == ("accept_all", "device")
    assert await listed(phone) == []


async def test_a_gate_answered_in_vscode_leaves_the_phones_list_and_the_phones_answer_is_refused_naming_who(
    rig: Rig, phone: TestClient
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        assert [each["id"] for each in await listed(phone)] == [gate]
        rig.kernel.questions.answer(gate, by=VSCODE, option="approve")
        assert await listed(phone) == []
        late = await call(phone, "POST", f"/api/clank-questions/{gate}", json={"option": "stop"})
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))

    assert late.status_code == 409
    assert "already answered by you (vscode)" in late.json()["error"]
    assert rig.run().status == "running", "the phone's late stop did nothing"


async def test_a_gate_answered_on_the_phone_leaves_the_services_waiting_questions_and_what_the_flows_wait_for(
    rig: Rig, phone: TestClient
) -> None:
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        answered = await call(phone, "POST", f"/api/clank-questions/{gate}", json={"option": "approve"})
        assert answered.status_code == 200, answered.text
        assert rig.kernel.questions.waiting() == []
        assert rig.kernel.parts["flows"].waiting() == []
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


def test_the_phone_page_draws_a_flows_question_with_its_files_and_its_note() -> None:
    script = PAGE.read_text(encoding="utf-8")
    waiting = script.split("function waitingBoxes", 1)[1].split("\n}\n", 1)[0]
    assert "flowBox(question)" in waiting, "a question about a flow drawn under its flow"
    flow_box = script.split("function flowBox", 1)[1].split("\n}\n", 1)[0]
    assert "api/flow-files/" in flow_box, "a file it shows read on the phone"
    assert "flow.notes" in flow_box, "the answers that take words"
    assert "text:" in flow_box, "an answer's words sent with it"
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not on the PATH: the script's syntax is checked where it is")
    checked = subprocess.run(
        [node, "--check", str(PAGE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        creationflags=background_flags(),  # no console window on Windows
    )
    assert checked.returncode == 0, checked.stderr


async def test_a_file_a_gate_shows_that_leads_out_of_the_folder_is_not_read(
    rig: Rig, phone: TestClient, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("not the folder's\n", encoding="utf-8")
    try:
        (tmp_path / "probe").symlink_to(outside)
    except OSError:
        pytest.skip("this machine may not make a symbolic link (Windows without the privilege)")
    async with running(rig.kernel):
        gate = await at_the_gate(rig, ["# The plan\n"])
        (rig.folder / "PLAN.md").unlink()
        (rig.folder / "PLAN.md").symlink_to(outside)
        read = (await call(phone, "GET", f"/api/flow-files/{gate}/0")).json()
        rig.kernel.questions.answer(gate, by=OWNER, option="stop")

    assert read["text"] is None
    assert "leads out of the folder" in read["why"]


async def test_the_phones_overview_reads_no_runs_file_while_no_question_is_about_a_flow(
    rig: Rig, phone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused() -> None:
        raise AssertionError("the runs' files were read")

    monkeypatch.setattr(rig.kernel.parts["flows"], "waiting", refused)
    plain = QuestionDraft(
        type="approval",
        title="Stop Docker Desktop?",
        options=[Option(id="stop", label="Stop it"), Option(id="cancel", label="Cancel")],
    )
    rig.kernel.questions.ask(plain, asked_by=Actor(kind="clank", via="docker.stop"))
    [shown] = await listed(phone)
    assert "flow" not in shown
