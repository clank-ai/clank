"""Design 0013 §2 and §5 (decisions 0085 and 0086): every box a model runs is prepared for its fresh session. Its first
message hands the flow's brief whether or not its `sees` lists it, and once; then, in order: the type's instructions,
where it sits in the flow, the brief, its task, the notes of the boxes before it, the files it sees, what the boxes
before it delivered, its deliverable and its own handoff note, and its last try."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clank.components.flows.first import first_message, instructions
from clank.components.flows.handoff import Note
from clank.components.flows.kinds import Flow
from clank.components.flows.runs import Run, Try
from clank.components.flows.verdicts import Verdict
from clank.kernel.events import Actor

WHEN = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
BRIEF = "About 60 grid points, at most 48 CPU-hours.\n"


def study(**defaults: Any) -> Flow:
    """Board D1's flow: the brief, a plan and its check, the owner's approval, three tasks, put together, reviewed."""
    return Flow.model_validate({
        "title": "A new simulation study",
        "defaults": defaults,
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the study plan", "sees": ["BRIEF.md"],
             "prompt": "Write the study plan for the brief.", "writes": ["PLAN.md"],
             "accept_when": ["the grid has about 60 points"]},
            {"id": "check", "type": "verify", "title": "Check the plan", "checks": "plan",
             "sees": ["BRIEF.md", "PLAN.md"]},
            {"id": "approve", "type": "gate", "title": "You approve the plan", "shows": ["PLAN.md"]},
            {"id": "split", "type": "decompose", "title": "Break it into tasks", "sees": ["PLAN.md"]},
            {"id": "T1", "type": "task", "title": "The grid", "prompt": "Write the grid.", "sees": ["PLAN.md"],
             "writes": ["grid.json"]},
            {"id": "T2", "type": "task", "title": "Estimates", "prompt": "Estimate the runs.", "sees": ["grid.json"],
             "writes": ["runs/estimates.md"]},
            {"id": "T3", "type": "task", "title": "The sweep", "prompt": "Write the sweep.", "sees": ["PLAN.md"],
             "writes": ["scripts/sweep.py"]},
            {"id": "join", "type": "integrate", "title": "Put it together", "writes": ["STUDY-PLAN.md"]},
            {"id": "review", "type": "gate", "title": "You review the whole", "shows": ["STUDY-PLAN.md"]},
        ],
        "lines": [
            {"from": "brief", "to": "plan"}, {"from": "plan", "to": "check"},
            {"from": "check", "to": "approve", "when": "pass"}, {"from": "check", "to": "plan", "when": "fail"},
            {"from": "approve", "to": "split"}, {"from": "split", "to": "T1"}, {"from": "split", "to": "T2"},
            {"from": "split", "to": "T3"}, {"from": "T1", "to": "join"}, {"from": "T2", "to": "join"},
            {"from": "T3", "to": "join"}, {"from": "join", "to": "review"},
        ],
    })  # fmt: skip


def folder(tmp_path: Path) -> Path:
    (tmp_path / "BRIEF.md").write_bytes(BRIEF.encode("utf-8"))
    (tmp_path / "PLAN.md").write_bytes(b"---\nkind: plan\n---\n# The plan\n\n- [ ] the grid\n")
    (tmp_path / "grid.json").write_bytes(b"[1, 2, 3]\n")
    return tmp_path


def box(flow: Flow, id: str) -> Any:
    return next(each for each in flow.boxes if each.id == id)


def test_a_box_whose_sees_omits_the_brief_is_handed_it_before_its_task(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study")
    assert "## The brief" in text
    section = text[text.index("## The brief") : text.index("## Your task")]
    assert "### BRIEF.md (from brief)" in section
    assert BRIEF.strip() in section, "handed whole, the goal and the limits"
    assert text.index("## The brief") < text.index("## Your task") < text.index("## The files you are handed")
    files = text[text.index("## The files you are handed") : text.index("## Your deliverable")]
    assert "### PLAN.md (from plan)" in files
    assert "BRIEF.md" not in files


def test_a_box_whose_sees_lists_the_brief_is_handed_it_once(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "plan"), folder(tmp_path), number=1, name="study")
    assert text.count(BRIEF.strip()) == 1
    assert "## The files you are handed" not in text, "the plan sees only the brief, handed under its own heading"
    check = first_message(made, box(made, "check"), folder(tmp_path), number=1, name="study")
    assert check.count(BRIEF.strip()) == 1
    assert "### PLAN.md (from plan)" in check, "a VERIFY is handed the brief and the deliverable it checks"


def test_a_brief_larger_than_the_setting_is_named_by_its_path_and_size(tmp_path: Path) -> None:
    made = study(whole_up_to=10)
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study")
    size = len(BRIEF.encode("utf-8"))
    section = text[text.index("## The brief") : text.index("## Your task")]
    assert f"`BRIEF.md` (from brief): {size:,} bytes, more than 10 handed whole" in section
    assert BRIEF.strip() not in text


def test_a_brief_not_written_yet_is_said_so(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "T1"), tmp_path, number=1, name="study")
    section = text[text.index("## The brief") : text.index("## Your task")]
    assert "`BRIEF.md` (from brief): not in the folder yet" in section


def test_the_brief_comes_after_the_types_instructions_and_before_the_task_and_the_files(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "T3"), folder(tmp_path), number=1, name="study")
    assert text.startswith(instructions("task"))
    places = [text.index(each) for each in (
        instructions("task"), "## The brief", "## Your task: The sweep", "## The files you are handed",
        "## What the tasks before you delivered", "## Your deliverable",
    )]  # fmt: skip
    assert places == sorted(places)


def run_of(**states: str) -> Run:
    """A run of the study, each box named in the state given (the rest waiting)."""
    made = Run(
        flow="myproject/study", number=1, title="A new simulation study", workspace="myproject", version="1",
        status="running", started_by=Actor(kind="user", via="console"), created=WHEN,
    )  # fmt: skip
    for name, state in states.items():
        made.box(name).state = state  # type: ignore[assignment]
        made.box(name).tries.append(Try(number=1, started=WHEN, outcome="done"))
    return made


def section(text: str, heading: str, until: str) -> list[str]:
    return text[text.index(heading) : text.index(until)].strip().splitlines()


def test_the_map_lists_the_boxes_before_it_with_what_each_delivered_marks_it_and_names_those_after_it(
    tmp_path: Path,
) -> None:
    made = study()
    run = run_of(brief="done", plan="done", check="done", approve="done", split="done")
    run.box("check").tries[-1].verdict = Verdict(result="pass", given=WHEN, by=Actor(kind="session", via="agent"))
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study", run=run)
    assert section(text, "## Where you are in the flow", "## The brief") == [
        "## Where you are in the flow",
        "",
        'You are box 6 of 10 in the flow "A new simulation study", run 1. Its boxes run one after another, each a '
        "session of its own: you have none of their history, only what this message hands you and the folder.",
        "",
        "Before you:",
        '1. brief (YOU) "Brief": the user wrote BRIEF.md.',
        '2. plan (PLAN) "Write the study plan": delivered PLAN.md.',
        '3. check (VERIFY) "Check the plan": its verdict on plan, pass.',
        '4. approve (GATE) "You approve the plan": the user approved.',
        '5. split (DECOMPOSE) "Break it into tasks": broke the work into T1, T2 and T3.',
        "",
        'You: 6. T1 (TASK) "The grid", try 1.',
        "",
        "After you:",
        '7. T2 (TASK) "Estimates": sees your grid.json.',
        '8. T3 (TASK) "The sweep": is told of your grid.json.',
        '9. join (INTEGRATE) "Put it together": is told of every deliverable, yours included.',
        '10. review (GATE) "You review the whole".',
    ]


def test_the_boxes_after_a_plan_say_how_they_use_its_deliverable(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "plan"), folder(tmp_path), number=2, name="study", run=run_of(brief="done"))
    lines = section(text, "After you:", "## The brief")
    assert lines[:4] == [
        "After you:",
        '3. check (VERIFY) "Check the plan": checks your deliverable, and a fail sends you back with its findings.',
        '4. approve (GATE) "You approve the plan": shows your PLAN.md to the user.',
        '5. split (DECOMPOSE) "Break it into tasks": sees your PLAN.md.',
    ]
    assert 'You: 2. plan (PLAN) "Write the study plan", try 2.' in text


def test_a_box_skipped_or_taken_as_it_was_is_said_so_on_the_map(tmp_path: Path) -> None:
    made = study()
    run = run_of(brief="done", plan="done", check="skipped", approve="done", split="done", T1="done")
    run.box("T1").tries[-1].outcome = "failed"
    text = first_message(made, box(made, "T2"), folder(tmp_path), number=1, name="study", run=run)
    assert '3. check (VERIFY) "Check the plan": skipped by the user.' in text
    assert '6. T1 (TASK) "The grid": delivered grid.json, taken as it was after its try 1 failed.' in text


def test_with_no_run_the_map_says_what_each_box_before_it_delivers(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study")
    assert section(text, "## Where you are in the flow", "You: ")[2:9] == [
        'You are box 6 of 10 in the flow "A new simulation study". Its boxes run one after another, each a session '
        "of its own: you have none of their history, only what this message hands you and the folder.",
        "",
        "Before you:",
        '1. brief (YOU) "Brief": the user writes BRIEF.md.',
        '2. plan (PLAN) "Write the study plan": delivers PLAN.md.',
        '3. check (VERIFY) "Check the plan": checks plan\'s deliverable.',
        '4. approve (GATE) "You approve the plan": the user decides.',
    ]
    assert '5. split (DECOMPOSE) "Break it into tasks": breaks the work into T1, T2 and T3.' in text


def test_the_map_comes_after_the_types_instructions_and_holds_no_other_boxs_prompt(tmp_path: Path) -> None:
    made = study()
    for name in ("plan", "check", "split", "T2", "join"):
        text = first_message(made, box(made, name), folder(tmp_path), number=1, name="study")
        assert instructions(box(made, name).type).rstrip() + "\n\n## Where you are in the flow" in text, name
        assert text.index("## Where you are in the flow") < text.index("## The brief"), name
        the_map = text[text.index("## Where you are in the flow") : text.index("## The brief")]
        for other in made.boxes:
            assert not other.prompt or other.prompt not in the_map, (name, other.id)


def test_a_plan_a_task_and_an_integrate_are_asked_for_their_handoff_note_after_what_they_are_accepted_when(
    tmp_path: Path,
) -> None:
    made = study()
    for name in ("plan", "T1", "join"):
        text = first_message(made, box(made, name), folder(tmp_path), number=1, name="study")
        deliverable = text[text.index("## Your deliverable") :]
        note = f"Last, write your handoff note in `.clank/handoff/study/{name}.md`"
        assert note in deliverable, name
        assert "what you did, the decisions you made and why, and what is still open" in deliverable, name
        assert deliverable.index(note) < deliverable.index("You are done when"), name
        if box(made, name).accept_when:
            assert deliverable.index("It is accepted when:") < deliverable.index(note), name


def test_a_verify_and_a_decompose_write_no_note_a_decomposes_summary_is_its_note(tmp_path: Path) -> None:
    made = study()
    check = first_message(made, box(made, "check"), folder(tmp_path), number=1, name="study")
    assert "write your handoff note" not in check
    split = first_message(made, box(made, "split"), folder(tmp_path), number=1, name="study")
    assert "write your handoff note" not in split
    assert ".clank/handoff/study/split.md" not in split
    assert "then call `flow_submit` with a short summary, which the boxes after you are handed as your note" in split


def test_each_types_instructions_say_how_it_hands_on_what_it_knows() -> None:
    for type in ("plan", "task", "integrate"):
        assert "handoff note" in instructions(type), type
    assert "handed as your note" in instructions("decompose")
    assert "You write no handoff note" in instructions("verify")


def notes() -> list[Note]:
    return [
        Note(box="plan", type="plan", attempt=2, where="its note, `.clank/handoff/study/plan.md`",
             text="Chose 60 points on a log grid.\nOpen: the seeds.", whole=".clank/handoff/study/plan.md"),
        Note(box="check", type="verify", attempt=1, where="its verdict", text="Its verdict on plan: pass."),
        Note(box="split", type="decompose", attempt=1, where="its summary when it submitted its tasks",
             text="Three tasks: the grid, the estimates, the sweep."),
    ]  # fmt: skip


def test_a_later_box_is_handed_the_notes_before_it_in_order_quoted_after_its_task(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study", notes=notes())
    assert section(text, "## Notes from the boxes before you", "## The files you are handed") == [
        "## Notes from the boxes before you",
        "",
        "What each box before you handed on, in the order they ran, in its own words:",
        "",
        "### plan (PLAN), try 2: its note, `.clank/handoff/study/plan.md`",
        "",
        "> Chose 60 points on a log grid.",
        "> Open: the seeds.",
        "",
        "### check (VERIFY), try 1: its verdict",
        "",
        "> Its verdict on plan: pass.",
        "",
        "### split (DECOMPOSE), try 1: its summary when it submitted its tasks",
        "",
        "> Three tasks: the grid, the estimates, the sweep.",
    ]
    assert text.index("## Your task") < text.index("## Notes from the boxes before you")


def test_a_note_longer_than_the_setting_is_cut_saying_where_the_whole_is(tmp_path: Path) -> None:
    made = study(note_up_to=19)
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study", notes=notes()[:1])
    assert "> Chose 60 points on\n> … (cut at 19 characters: the whole note is `.clank/handoff/study/plan.md`)" in text
    assert "Open: the seeds." not in text


def test_a_box_that_left_no_note_or_has_not_run_yet_is_said_so(tmp_path: Path) -> None:
    made = study()
    said = [
        Note(box="plan", type="plan", attempt=1, where="no note", said="It left no handoff note."),
        Note(box="check", type="verify", attempt=None, where="not run yet",
             said="It has not run yet in this run: its note comes once it has."),
    ]  # fmt: skip
    text = first_message(made, box(made, "T1"), folder(tmp_path), number=1, name="study", notes=said)
    assert "### plan (PLAN), try 1: no note\n\nIt left no handoff note." in text
    assert "### check (VERIFY): not run yet\n\nIt has not run yet in this run: its note comes once it has." in text


def test_a_verify_is_handed_no_notes(tmp_path: Path) -> None:
    made = study()
    text = first_message(made, box(made, "check"), folder(tmp_path), number=1, name="study", notes=notes()[:1])
    assert "## Notes from the boxes before you" not in text
    assert "Chose 60 points" not in text
