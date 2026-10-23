"""Design 0013 §2, §3, §5 and §9 (decisions 0060 and 0085): a box's first message is, in order, its type's
instructions, the flow's brief, its prompt, the files it sees (a text file whole up to a size, a setting; a larger or
binary one by its path and size), what the boxes before it delivered (an INTEGRATE: every deliverable before it, by the
box that wrote it; a DECOMPOSE's task: those of the tasks before it), its deliverable and *accept when*, and on a later
try what happened to the last one; each file says the box it came from. Design 0013 §17: the corpus's notes, each by
its path and first line, when side tasks wrote any."""

from pathlib import Path
from typing import Any

from clank.components.flows.first import first_message, instructions
from clank.components.flows.kinds import Flow


def flow(**defaults: Any) -> Flow:
    return Flow.model_validate({
        "title": "A new simulation study",
        "defaults": defaults,
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the study plan", "sees": ["BRIEF.md"],
             "prompt": "Write the study plan for the brief.", "writes": ["PLAN.md"],
             "holds": "the grid, the methods and what the runs cost",
             "accept_when": ["the grid has about 60 points", "the seeds are fixed"]},
            {"id": "T1", "type": "task", "title": "The parameter grid", "sees": ["PLAN.md", "data/table.bin"],
             "prompt": "Write the grid of the plan's parameters.", "writes": ["grid.json"]},
            {"id": "T2", "type": "task", "title": "The sweep", "sees": ["grid.json", "BRIEF.md", "notes/missing.md"],
             "prompt": "Write the sweep's script.", "writes": ["scripts/sweep.py"]},
        ],
        "lines": [{"from": "brief", "to": "plan"}, {"from": "plan", "to": "T1"}, {"from": "T1", "to": "T2"}],
    })  # fmt: skip


def folder(tmp_path: Path) -> Path:
    (tmp_path / "BRIEF.md").write_text("About 60 grid points, at most 48 CPU-hours.\n", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("---\nkind: plan\n---\n# The plan\n\n- [ ] the grid\n", encoding="utf-8")
    (tmp_path / "grid.json").write_text('{"points": [' + ", ".join(["1"] * 3000) + "]}\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "table.bin").write_bytes(bytes(range(256)) * 4)
    return tmp_path


def test_its_parts_come_in_order_the_types_instructions_first(tmp_path: Path) -> None:
    made = flow()
    text = first_message(made, made.boxes[1], folder(tmp_path), number=1)
    assert text.startswith(instructions("plan"))
    places = [text.index(each) for each in (
        instructions("plan"), "## The brief", "## Your task: Write the study plan",
        "Write the study plan for the brief.", "## Your deliverable", "- PLAN.md",
        "the grid, the methods and what the runs cost", "It is accepted when:", "- the grid has about 60 points",
        "- the seeds are fixed",
    )]  # fmt: skip
    assert places == sorted(places)
    assert "## Your last try" not in text, "a first try has none"


def test_a_text_file_is_handed_whole_up_to_the_setting_and_a_larger_or_binary_one_by_its_path_and_size(
    tmp_path: Path,
) -> None:
    made = flow(whole_up_to=2000)
    there = folder(tmp_path)
    t1 = first_message(made, made.boxes[2], there, number=1)
    assert "### PLAN.md (from plan)" in t1
    assert "- [ ] the grid" in t1, "PLAN.md whole"
    assert "`data/table.bin` (from the folder): 1,024 bytes, not text: read it with your tools if you need it" in t1
    t2 = first_message(made, made.boxes[3], there, number=1)
    size = (there / "grid.json").stat().st_size
    assert f"`grid.json` (from T1): {size:,} bytes, more than 2,000 handed whole" in t2
    assert '"points"' not in t2
    assert "### BRIEF.md (from brief)" in t2
    assert "`notes/missing.md` (from the folder): not in the folder yet" in t2


def test_a_file_holding_backticks_is_fenced_with_more_of_them(tmp_path: Path) -> None:
    made = flow()
    there = folder(tmp_path)
    (there / "BRIEF.md").write_text("Run it as:\n````\npython sweep.py\n````\n", encoding="utf-8")
    text = first_message(made, made.boxes[1], there, number=1)
    assert "`````\nRun it as:\n````\npython sweep.py\n````\n`````" in text


def test_a_later_try_is_told_what_happened_to_the_last_one(tmp_path: Path) -> None:
    made = flow()
    text = first_message(
        made, made.boxes[1], folder(tmp_path), number=2,
        last="Try 1 failed: it ended without writing PLAN.md.\nThe user's note: fix the seeds.",
    )  # fmt: skip
    assert text.endswith("## Your last try\n\nThis is try 2. Try 1 failed: it ended without writing PLAN.md.\n"
                         "The user's note: fix the seeds.\n")  # fmt: skip


def test_each_type_a_model_runs_has_its_instructions_and_says_how_it_ends() -> None:
    for type in ("plan", "verify", "decompose", "task", "integrate"):
        said = instructions(type)
        assert said.strip(), type
    assert "flow_verdict" in instructions("verify")
    assert "flow_submit" in instructions("decompose")


def fanned() -> Flow:
    """Board D1's shape: a DECOMPOSE's three tasks, one after another, joined at an INTEGRATE."""
    return Flow.model_validate({
        "title": "A new simulation study",
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the study plan", "sees": ["BRIEF.md"],
             "prompt": "Write the study plan for the brief.", "writes": ["PLAN.md"]},
            {"id": "split", "type": "decompose", "title": "Break it into tasks", "sees": ["PLAN.md"]},
            {"id": "T1", "type": "task", "title": "The grid", "prompt": "Write the grid.", "writes": ["grid.json"]},
            {"id": "T2", "type": "task", "title": "Estimates", "prompt": "Estimate the runs.", "sees": ["grid.json"],
             "writes": ["runs/estimates.md"]},
            {"id": "T3", "type": "task", "title": "The sweep", "prompt": "Write the sweep.",
             "writes": ["scripts/sweep.py", "grid.json"]},
            {"id": "join", "type": "integrate", "title": "Put it together", "sees": ["BRIEF.md"],
             "writes": ["STUDY-PLAN.md"]},
            {"id": "review", "type": "gate", "title": "You review the whole", "shows": ["STUDY-PLAN.md"]},
        ],
        "lines": [
            {"from": "brief", "to": "plan"}, {"from": "plan", "to": "split"}, {"from": "split", "to": "T1"},
            {"from": "split", "to": "T2"}, {"from": "split", "to": "T3"}, {"from": "T1", "to": "join"},
            {"from": "T2", "to": "join"}, {"from": "T3", "to": "join"}, {"from": "join", "to": "review"},
        ],
    })  # fmt: skip


def delivered(tmp_path: Path) -> Path:
    there = folder(tmp_path)
    (there / "scripts").mkdir()
    (there / "scripts" / "sweep.py").write_text("print('sweep')\n", encoding="utf-8")
    return there


def test_integrates_first_message_names_every_deliverable_before_it_with_the_box_that_wrote_it(tmp_path: Path) -> None:
    made = fanned()
    there = delivered(tmp_path)
    text = first_message(made, made.boxes[6], there, number=1)
    section = text[text.index("## Every deliverable before you") : text.index("## Your deliverable")]
    size = (there / "BRIEF.md").stat().st_size
    assert section.splitlines()[2:] == [
        "The files the boxes before you delivered, in the order they ran; read each with your tools:",
        f"- `BRIEF.md` (from brief): {size:,} bytes",
        f"- `PLAN.md` (from plan): {(there / 'PLAN.md').stat().st_size:,} bytes",
        f"- `grid.json` (from T3): {(there / 'grid.json').stat().st_size:,} bytes",
        "- `runs/estimates.md` (from T2): not in the folder",
        f"- `scripts/sweep.py` (from T3): {(there / 'scripts' / 'sweep.py').stat().st_size:,} bytes",
        "",
    ], "each once, by the box that wrote it last, in the order they ran (the tasks accepted included)"
    assert text.index("## The brief") < text.index("## Every deliverable before you")


def test_a_decomposes_task_is_named_what_the_tasks_before_it_delivered(tmp_path: Path) -> None:
    made = fanned()
    there = delivered(tmp_path)
    first, second, third = (first_message(made, box, there, number=1) for box in made.boxes[3:6])
    assert "## What the tasks before you delivered" not in first, "T1 runs first"
    assert "## What the tasks before you delivered" not in second, "T2 is handed grid.json whole already"
    section = third[third.index("## What the tasks before you delivered") : third.index("## Your deliverable")]
    assert "You run after T1 and T2, broken out of the same work by split" in section
    assert "- `grid.json` (from T1)" in section
    assert "- `runs/estimates.md` (from T2): not in the folder" in section
    assert "## Every deliverable before you" not in third


def test_a_decomposes_first_message_says_to_propose_each_task_after_its_own_box(tmp_path: Path) -> None:
    made = fanned()
    text = first_message(made, made.boxes[2], delivered(tmp_path), number=1)
    assert "propose each task with `flow_propose_box`, `after` set to `split`, in the order they should run" in text
    assert "then call `flow_submit`" in text
    assert "flow_read" in instructions("decompose"), "it may read the flow first"


def test_a_deliverable_already_in_the_folder_is_named_and_must_be_written_again(tmp_path: Path) -> None:
    """A PLAN that found its PLAN.md from an earlier run kept it unwritten, and its box failed (2026-10-22): its first
    message says which of its files are there already, and that each must be written again during this session."""
    there = first_message(flow(), flow().boxes[1], folder(tmp_path), number=1)
    assert "PLAN.md is in the folder already, from before" in there
    assert "write it again during this session" in there
    (tmp_path / "PLAN.md").unlink()
    fresh = first_message(flow(), flow().boxes[1], tmp_path, number=1)
    assert "from before" not in fresh


def test_the_corpuss_notes_are_listed_by_path_and_first_line_when_there_are_any(tmp_path: Path) -> None:
    made = flow()
    box = made.boxes[2]
    assert "## The corpus" not in first_message(made, box, folder(tmp_path), number=1)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "1-2-the-next-fit.md").write_text("fit.py fits the grid.\n", encoding="utf-8")
    (tmp_path / "corpus" / "1-1-prior-bounds.md").write_text("# The best bound is 5.\n\nFrom A.\n", encoding="utf-8")
    (tmp_path / "corpus" / "scratch.txt").write_text("not a note\n", encoding="utf-8")
    said = first_message(made, box, tmp_path, number=1)
    section = said[said.index("## The corpus") :]
    assert (
        "- corpus/1-1-prior-bounds.md: The best bound is 5.\n- corpus/1-2-the-next-fit.md: fit.py fits the grid."
        in section
    )
    assert "scratch.txt" not in said
