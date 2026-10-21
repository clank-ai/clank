"""Test support: flows as the Flow view shows them (design 0013 §12, §14 step 6).

Board D1's moment (`install_d1`): the flow "A new simulation study" of the workspace `myproject`, its file
`tests/components/flows/d1-flow.json`, at 12:41 on 2026-10-20: the brief written at 12:02; the plan written twice, its
first try found wrong by the check at 12:11 with three findings and its second passed at 12:22; the owner's approval at
12:30; DECOMPOSE's four tasks proposed at 12:31 and accepted at 12:32, T2's prompt edited; T1 done at 12:33; T2
running since 12:35 in its own session; T3, T4, INTEGRATE and the last gate waiting. Its run's file, its batch and its
events are written as the runner writes them, its files in a synthetic folder. Nothing runs.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.proposals import Batch, Proposal
from clank.components.flows.runs import BoxRun, Kept, Run, Runs, Try
from clank.components.flows.verdicts import AGENT, Criterion, Verdict
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.events import Actor, Subject

WORKSPACE = "myproject"
NAME = "study"
FLOW = f"{WORKSPACE}/{NAME}"
OWNER = Actor(kind="user", via="console")
RUNNER = Actor(kind="clank", via="flow runner")
D1_FILE = Path(__file__).resolve().parents[1] / "components" / "flows" / "d1-flow.json"
T2_SESSION = "ses_t2_estimate"
PORT = 4097
BRIEF = """# A new simulation study

The goal: how far the walkers spread, measured on a grid of sizes and drifts.

The limits:

- about 60 grid points
- at most 48 CPU-hours
"""
FINDINGS = [
    "no CPU-hour budget: the grid's cost is unknown",
    "the seeds are not fixed: the runs would not repeat",
    "the grid has 240 points, the brief allows about 60",
]


def at(hour: int, minute: int, second: int = 0) -> datetime:
    """A moment of board D1's day."""
    return datetime(2026, 10, 20, hour, minute, second, tzinfo=UTC)


NOW = at(12, 41)


def d1_values() -> dict[str, Any]:
    """Board D1's flow, as its file holds it."""
    values: dict[str, Any] = json.loads(D1_FILE.read_text(encoding="utf-8"))
    return values


def d1_flow() -> Flow:
    """Board D1's flow, read as the service reads its file."""
    return Flow.model_validate({key: value for key, value in d1_values().items() if key != "schema"})


def kept(path: str, mark: str, size: int = 400) -> Kept:
    """A file as Clank saw it: its fingerprint (`mark` repeated), its size, a copy kept."""
    return Kept(path=path, sha256=(mark * 64)[:64], size=size, copied=True)


def done_try(number: int, start: datetime, end: datetime, *files: Kept, session: str = "", **more: Any) -> Try:
    """A try that ended done."""
    return Try(number=number, started=start, ended=end, outcome="done", session=session, port=PORT if session else None,
               sent=start if session else None, deliverables=list(files), **more)  # fmt: skip


def verdict(result: str, checked: int, given: datetime, findings: list[str], criteria: list[Criterion]) -> Verdict:
    """A VERIFY's verdict, as `flow_verdict` gives it."""
    return Verdict.model_validate(
        {"result": result, "findings": findings, "criteria": criteria, "checked": checked, "given": given, "by": AGENT}
    )


def d1_run() -> Run:
    """Board D1's run at 12:41."""
    plan_1, plan_2 = kept("PLAN.md", "a"), kept("PLAN.md", "b")
    grid = kept("grid.json", "c", 1200)
    met = [
        Criterion(line="about 60 grid points", met=True, evidence="60 points in PLAN.md's grid"),
        Criterion(line="at most 48 CPU-hours", met=True, evidence="about 41, by PLAN.md's estimate"),
        Criterion(line="the seeds are fixed", met=True, evidence="seeds 1 to 60, in PLAN.md"),
    ]
    failed = [
        Criterion(line="at most 48 CPU-hours", met=False, evidence="PLAN.md gives no CPU-hours"),
        Criterion(line="about 60 grid points", met=False, evidence="240 points in PLAN.md's grid"),
    ]
    boxes = {
        "brief": BoxRun(state="done", kept=[kept("BRIEF.md", "9")]),
        "plan": BoxRun(
            state="done",
            kept=[plan_2],
            tries=[
                done_try(1, at(12, 2), at(12, 9), plan_1, session="ses_plan_1", agent="planner", mode="plan"),
                done_try(
                    2,
                    at(12, 11),
                    at(12, 18),
                    plan_2,
                    session="ses_plan_2",
                    agent="planner",
                    mode="plan",
                    told="the check's 3 findings",
                ),
            ],
        ),
        "check": BoxRun(
            state="done",
            tries=[
                done_try(
                    1,
                    at(12, 9),
                    at(12, 11),
                    session="ses_check_1",
                    agent="planner",
                    mode="plan",
                    verdict=verdict("fail", 1, at(12, 11), FINDINGS, failed),
                ),
                done_try(
                    2,
                    at(12, 18),
                    at(12, 22),
                    session="ses_check_2",
                    agent="planner",
                    mode="plan",
                    verdict=verdict("pass", 2, at(12, 22), [], met),
                ),
            ],
        ),
        "approve": BoxRun(state="done"),
        "split": BoxRun(
            state="done",
            tries=[done_try(1, at(12, 30), at(12, 31), session="ses_split", agent="planner", mode="plan")],
        ),
        "T1": BoxRun(
            state="done",
            kept=[grid],
            tries=[done_try(1, at(12, 32), at(12, 33), grid, session="ses_t1", agent="build")],
        ),
        "T2": BoxRun(
            state="running",
            tries=[
                Try(
                    number=1,
                    started=at(12, 35),
                    session=T2_SESSION,
                    port=PORT,
                    agent="build",
                    mode="auto",
                    sent=at(12, 35),
                    tokens=8_400,
                )
            ],
        ),
    }
    return Run(
        flow=FLOW, number=1, title="A new simulation study", workspace=WORKSPACE, version="r1", status="running",
        at="T2", operation="op-0000t2", server=PORT, started_by=OWNER, created=at(12, 2), boxes=boxes,
    )  # fmt: skip


def d1_batch() -> Batch:
    """DECOMPOSE's four proposals, accepted at 12:32, T2's prompt edited by the owner."""
    flow = d1_flow()
    proposals = []
    for number, id in enumerate(["T1", "T2", "T3", "T4"], start=1):
        box = next(each for each in flow.boxes if each.id == id).model_copy(update={"proposed": None})
        original = box.model_copy(update={"prompt": "Estimate each point's run time."}) if id == "T2" else None
        proposals.append(
            Proposal(
                id=id,
                number=number,
                after="split",
                box=box,
                original=original,
                why=f"PLAN.md's step {number}",
                state="accepted",
                given=at(12, 31),
                by=AGENT,
                decided=at(12, 32),
                decided_by=OWNER,
            )
        )
    return Batch(flow=FLOW, run=1, box="split", attempt=1, summary="Four tasks, from PLAN.md's steps",
                 submitted=at(12, 31), question="q-d4d4d4", asked=["T1", "T2", "T3", "T4"], replaced=[],
                 proposals=proposals)  # fmt: skip


def proposed_batch(count: int = 4, *, after: str = "split", flow: str = FLOW, run: int = 1) -> Batch:
    """A DECOMPOSE's tasks proposed and waiting for the owner, as `flow_propose_box` stages them."""
    proposals = [
        Proposal(
            id=f"T{number}", number=number, after=after,
            box=Box(id=f"T{number}", type="task", title=f"Task {number} of the plan", sees=["PLAN.md"],
                    prompt=f"Do step {number} of PLAN.md, and write out/t{number}.md.", writes=[f"out/t{number}.md"],
                    accept_when=[f"out/t{number}.md answers step {number}"]),
            why=f"PLAN.md's step {number}", given=at(12, 31), by=AGENT,
        )
        for number in range(1, count + 1)
    ]  # fmt: skip
    return Batch(flow=flow, run=run, box=after, attempt=1, summary=f"{count} tasks from PLAN.md", submitted=at(12, 31),
                 question="q-d4d4d4", asked=[each.id for each in proposals], proposals=proposals)  # fmt: skip


def write_run(runs: Runs, run: Run, *batches: Batch) -> None:
    """A run's file and its batches, as the runner writes them."""
    runs.save(run)
    for batch in batches:
        path = runs.try_folder(run, batch.box, batch.attempt) / "proposals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(batch.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


def write_files(folder: Path) -> None:
    """The files board D1's flow wrote by 12:41, in its folder."""
    for path, text in (("BRIEF.md", BRIEF), ("PLAN.md", "# The study plan\n\n- [x] The grid\n"), ("grid.json", "[]\n")):
        place = folder / path
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(text, encoding="utf-8")


def record_events(kernel: Kernel, clock: FakeClock) -> None:
    """What the runner said as board D1's run went, each at its time."""
    said = [
        (at(12, 2), "flows.run_started", "you started A new simulation study", OWNER, {}),
        (at(12, 2), "flows.box_ended", "you did Brief", OWNER, {"box": "brief", "outcome": "done", "reason": ""}),
        (at(12, 9), "flows.box_ended", "Write the study plan is done", RUNNER, {"box": "plan", "outcome": "done"}),
        (at(12, 11), "flows.box_ended", "Check the plan found plan's try 1 wrong, with 3 findings: back to plan",
         RUNNER, {"box": "check", "outcome": "done", "reason": "it found plan's try 1 wrong"}),
        (at(12, 18), "flows.box_ended", "Write the study plan is done", RUNNER, {"box": "plan", "outcome": "done"}),
        (at(12, 22), "flows.box_ended", "Check the plan is done", RUNNER, {"box": "check", "outcome": "done"}),
        (at(12, 30), "flows.box_ended", "you approved You approve the plan", OWNER,
         {"box": "approve", "outcome": "done", "reason": "approved"}),
        (at(12, 31), "flows.box_ended", "Break it into tasks is done", RUNNER, {"box": "split", "outcome": "done"}),
        (at(12, 32), "flows.proposal_decided", "you accepted T1 to T4", OWNER,
         {"box": "split", "decision": "accepted"}),
        (at(12, 33), "flows.box_ended", "The parameter grid is done", RUNNER, {"box": "T1", "outcome": "done"}),
        (at(12, 35), "flows.box_started", "Estimate run times started", RUNNER, {"box": "T2", "try": 1}),
    ]  # fmt: skip
    for moment, kind, summary, actor, data in said:
        assert isinstance(data, dict)
        clock.set(moment)
        kernel.events.record(kind, summary=summary, actor=actor, subject=Subject(kind="flow", id=FLOW),
                             data={"flow": FLOW, "run": 1, **data})  # fmt: skip
    clock.set(NOW)


def write_flow(kernel: Kernel, values: dict[str, Any], name: str = NAME) -> None:
    """A flow's file in Clank's home, read by the service as if written by hand."""
    path = kernel.home.config / "flows" / WORKSPACE / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(values, indent=2) + "\n").encode("utf-8"))
    kernel.settings.reload_changed()


def install_d1(kernel: Kernel, clock: FakeClock, folder: Path) -> None:
    """Board D1's moment in a kernel: the workspace on `folder`, the flow, its run, its batch, its events, its files."""
    folder.mkdir(parents=True, exist_ok=True)
    kernel.settings.write("workspace", WORKSPACE, {"path": str(folder)}, base=None, actor=OWNER)
    write_flow(kernel, d1_values())
    write_files(folder)
    write_run(kernel.parts["flows"].runner.runs, d1_run(), d1_batch())
    record_events(kernel, clock)


LONG = "a title much longer than any box can hold, with 數據 and café in it"


def generated(
    tasks: int,
    *,
    proposals: bool = False,
    loop: bool = False,
    added: bool = False,
    next_flow: bool = False,
    long: bool = False,
    running: int = 0,
) -> dict[str, Any]:
    """The Flow view of a flow made for the layout's edge cases (design 0013 §14 step 6): a brief, a plan, a check of
    the plan when `loop` (its first try failed, its fail line taken back to the plan), an added TASK after the plan
    when `added`, the owner's approval, a DECOMPOSE whose `tasks` tasks are in the flow, or waiting as proposals when
    `proposals`, an INTEGRATE, the last gate, and the next flow when `next_flow`; every title `LONG` when `long`; the
    task `running` (from 1) at work, the boxes before it done."""
    from clank.components.flows.view import view

    def title(words: str) -> str:
        return f"{words}: {LONG}" if long else words

    boxes: list[dict[str, Any]] = [
        {"id": "brief", "type": "you", "title": title("Brief"), "writes": ["BRIEF.md"]},
        {"id": "plan", "type": "plan", "title": title("Write the plan"), "writes": ["PLAN.md"], "prompt": "Plan."},
    ]
    chain = ["brief", "plan"]
    lines: list[dict[str, Any]] = [{"from": "brief", "to": "plan"}]
    if added:
        boxes.append({"id": "X1", "type": "task", "title": title("An added box"), "writes": ["added.md"],
                      "prompt": "Add.", "proposed": {"run": 1, "by": "plan"}})  # fmt: skip
        lines.append({"from": "plan", "to": "X1"})
        chain.append("X1")
    if loop:
        boxes.append({"id": "check", "type": "verify", "title": title("Check the plan"), "checks": "plan"})
        lines += [{"from": chain[-1], "to": "check"}, {"from": "check", "to": "plan", "when": "fail"}]
        chain.append("check")
    boxes += [
        {"id": "approve", "type": "gate", "title": title("You approve the plan")},
        {"id": "split", "type": "decompose", "title": title("Break it into tasks")},
    ]
    lines.append({"from": chain[-1], "to": "approve", **({"when": "pass"} if loop else {})})
    lines.append({"from": "approve", "to": "split"})
    named = [f"T{number}" for number in range(1, tasks + 1)]
    if not proposals:
        boxes += [
            {"id": id, "type": "task", "title": title(f"Task {id}"), "writes": [f"out/{id}.md"], "prompt": "Do it.",
             "proposed": {"run": 1, "by": "split"}}
            for id in named
        ]  # fmt: skip
        lines += [{"from": "split", "to": id} for id in named] + [{"from": id, "to": "join"} for id in named]
    else:
        lines.append({"from": "split", "to": "join"})
    boxes += [
        {"id": "join", "type": "integrate", "title": title("Put it together"), "writes": ["STUDY.md", "NEXT.md"]},
        {"id": "review", "type": "gate", "title": title("You review the whole")},
    ]
    lines.append({"from": "join", "to": "review"})
    made = Flow.model_validate({"title": title("A generated flow"), "defaults": {"model": "daily 262K"},
                                "boxes": boxes, "lines": lines})  # fmt: skip
    states: dict[str, BoxRun] = {}
    order_run = [box["id"] for box in boxes]
    at_work = f"T{running}" if running and not proposals else ""
    for id in order_run:
        if at_work and id == at_work:
            states[id] = BoxRun(state="running", tries=[Try(number=1, started=at(12, 35), session="ses_x", port=PORT)])
            break
        if not at_work and id == "join":
            break
        if id == "check":
            states[id] = BoxRun(state="done", tries=[
                done_try(1, at(12, 9), at(12, 11), verdict=verdict("fail", 1, at(12, 11), FINDINGS, [])),
                done_try(2, at(12, 18), at(12, 22), verdict=verdict("pass", 2, at(12, 22), [], [])),
            ])  # fmt: skip
            continue
        tries = [] if id in ("brief", "approve") else [done_try(1, at(12, 2), at(12, 9), kept(f"{id}.md", "e"))]
        states[id] = BoxRun(state="done", tries=tries)
    if loop:
        states["plan"] = BoxRun(state="done", tries=[done_try(1, at(12, 2), at(12, 9)),
                                                      done_try(2, at(12, 11), at(12, 18))])  # fmt: skip
    run = Run(flow=FLOW, number=1, title=made.title, workspace=WORKSPACE, version="r1", status="running",
              at=at_work or "split", started_by=OWNER, created=at(12, 2), boxes=states)  # fmt: skip
    batches = [proposed_batch(tasks)] if proposals else []
    if long and proposals:
        for each in batches[0].proposals:
            each.box.title = title(each.box.title)
    following = {"id": f"{WORKSPACE}/next", "title": title("Run the study")} if next_flow else None
    return view(FLOW, made, run, batches, running="daily-262k", titles={"daily-262k": "daily 262K"}, brief=BRIEF,
                present=lambda path: True, ended={}, next_flow=following)  # fmt: skip


def shapes() -> list[tuple[str, dict[str, Any]]]:
    """Every generated flow of the layout's edge cases, each named: 1 to 12 tasks, with and without proposals waiting,
    a fail loop, an added box and the next flow, with titles longer than a box; a task at work in each."""
    found = []
    for tasks in range(1, 13):
        for proposals in (False, True):
            for extra in ("", "loop", "added", "next", "long", "all"):
                every = extra == "all"
                name = f"{tasks} tasks{' proposed' if proposals else ''}{f' {extra}' if extra else ''}"
                shown = generated(
                    tasks,
                    proposals=proposals,
                    loop=every or extra == "loop",
                    added=every or extra == "added",
                    next_flow=every or extra == "next",
                    long=every or extra == "long",
                    running=0 if proposals else min(2, tasks),
                )
                found.append((name, shown))
    return found


def d1_view() -> dict[str, Any]:
    """Board D1's moment as the service's view gives it: its flow, its run, its batch, its brief, its events."""
    from clank.components.flows.view import view

    ended = {
        "brief": (at(12, 2), "you (console)"),
        "approve": (at(12, 30), "you (console)"),
        "split": (at(12, 31), "Clank (flow runner)"),
        "T1": (at(12, 33), "Clank (flow runner)"),
    }
    return view(
        FLOW, d1_flow(), d1_run(), [d1_batch()], running="daily-262k", titles={"daily-262k": "daily 262K"},
        brief=BRIEF, present=lambda path: True, ended=ended,
    )  # fmt: skip


def touching(chart: Any) -> list[str]:
    """What is wrong with a laid out flow (design 0013 §14 step 6: "no box, line label or legend overlaps another or
    leaves its panel's drawing area"): a line wider than the chart; two boxes closer than one cell; a label or a legend
    item on a box, on another label or on another item; the legend above a box; a box not its full height."""
    wrong = []
    for row, line in enumerate(chart.lines):
        if line.cell_length > chart.width:
            wrong.append(f"line {row} is {line.cell_length} cells, wider than {chart.width}")
    rects = list(chart.boxes.items())
    for index, (one, a) in enumerate(rects):
        if not chart.listed and a.h != chart.box_rows:
            wrong.append(f"{one} is {a.h} rows, not {chart.box_rows}")
        if a.x < 0 or a.x + a.w > chart.width:
            wrong.append(f"{one} leaves the chart: columns {a.x} to {a.x + a.w}")
        for other, b in rects[index + 1 :]:
            apart = a.x + a.w < b.x or b.x + b.w < a.x or a.y + a.h < b.y or b.y + b.h < a.y
            if not apart and not chart.listed:
                wrong.append(f"{one} touches {other}")
    spans = [("label", *each) for each in chart.labels] + [("legend", *each) for each in chart.legend]
    for index, (kind, row, start, end) in enumerate(spans):
        if end > chart.width:
            wrong.append(f"a {kind} on line {row} leaves the chart at {end}")
        for name, rect in rects:
            if rect.y <= row < rect.y + rect.h and start < rect.x + rect.w and rect.x < end:
                wrong.append(f"a {kind} on line {row} ({start} to {end}) is on {name}")
            if kind == "legend" and row <= rect.y + rect.h - 1:
                wrong.append(f"the legend's line {row} is not under {name}")
        for other, row2, start2, end2 in spans[index + 1 :]:
            if row == row2 and start < end2 and start2 < end:
                wrong.append(f"a {kind} and a {other} share line {row}, {max(start, start2)} to {min(end, end2)}")
    return wrong


def install_proposals(kernel: Kernel, clock: FakeClock, folder: Path, count: int = 4) -> None:
    """Board D4's moment: board D1's flow before its tasks, its DECOMPOSE's `count` tasks proposed and waiting."""
    install_d1(kernel, clock, folder)
    values = d1_values()
    values["boxes"] = [each for each in values["boxes"] if not each["id"].startswith("T")]
    values["lines"] = [
        each for each in values["lines"] if not (each["from"].startswith("T") or each["to"].startswith("T"))
    ]
    values["lines"].insert(4, {"from": "split", "to": "join"})
    write_flow(kernel, values)
    run = d1_run()
    run.at, run.boxes = "split", {name: state for name, state in run.boxes.items() if not name.startswith("T")}
    write_run(kernel.parts["flows"].runner.runs, run, proposed_batch(count))


PLAN_1 = "# The study plan\n\nThe grid: 240 points.\n\nThe seeds: drawn at random.\n"
PLAN_2 = "# The study plan\n\nThe grid: 60 points.\n\nThe seeds: 1 to 60.\n\nThe cost: about 41 CPU-hours.\n"


def install_gate(kernel: Kernel, clock: FakeClock, folder: Path, kind: str = "gate") -> str:
    """Board D3's moment (12:22): board D1's flow at its first gate, the plan's two tries kept, the check passed on the
    second; the gate's question asked, as the runner asks it. Its id. `kind` "done": the gate approved, the flow
    waiting after it only because the flow waits after every box (the runner's question of go on or stop)."""
    from clank.components.flows.runs import Waiting
    from clank.kernel.questions import Option, QuestionDraft

    install_d1(kernel, clock, folder)
    stop = Option(id="stop", label="Stop the flow", effect="The run ends here; nothing after it runs.", key="s")
    if kind == "done":
        draft = QuestionDraft(
            type="approval",
            title="A new simulation study: You approve the plan is done; go on?",
            detail="approve is done, and its *when done* says to wait for you before the next box.",
            options=[Option(id="go", label="Go on", effect="The next box starts.", key="y"), stop],
            about=Subject(kind="flow", id=FLOW),
        )
    else:
        draft = QuestionDraft(
            type="choice",
            title="A new simulation study: You approve the plan",
            detail="The flow A new simulation study waits at You approve the plan.\n- PLAN.md (changed since try 1)",
            options=[
                Option(id="approve", label="Approve and go on", effect="The next box starts.", key="y"),
                Option(id="back", label="Send back with a note", effect="plan runs its next try with your note.",
                       key="b"),
                stop,
            ],
            about=Subject(kind="flow", id=FLOW),
        )  # fmt: skip
    asked = kernel.questions.ask(draft, asked_by=RUNNER)
    run = d1_run()
    run.at = "approve"
    run.boxes = {name: state for name, state in run.boxes.items() if name in ("brief", "plan", "check")}
    run.boxes["approve"] = BoxRun(state="done" if kind == "done" else "running")
    run.waiting = Waiting(question=asked.id, kind=kind, box="approve")
    runs = kernel.parts["flows"].runner.runs
    write_run(runs, run)
    for number, text in ((1, PLAN_1), (2, PLAN_2)):
        place = runs.try_folder(run, "plan", number) / "deliverables" / "PLAN.md"
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(text, encoding="utf-8")
    (folder / "PLAN.md").write_text(PLAN_2, encoding="utf-8")
    return asked.id
