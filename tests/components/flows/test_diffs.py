"""Design 0013 §8 and §10: each try's deliverables are copied into its folder, and two tries' copies of a file are
compared: a unified diff, and the lines changed counted as board D3 says them ("changed since try 1: 7 lines", a
replaced block counted by its longer side). The runner compares a box's last two tries that kept the file, or the two
asked for; a try that kept the file by its fingerprint only, or wrote no such file, says so; and a gate shows, beside
each file it shows, how many of its lines changed since the try before, counted outside the service's event loop and
within seconds even for a large file of repeated lines (design 0004's no stutter). Run against the fake bridge and a
synthetic folder."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from clank.components.flows import runner as runner_module
from clank.components.flows.diffs import Compared, compare
from clank.components.flows.runner import RunError
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
FIRST = "# The plan\n\nA grid.\nSeeds: any.\nNo budget.\n240 points.\nThen a sweep.\n"
SECOND = "# The plan\n\nA grid.\nSeeds: 1-8.\nBudget: 41.5 CPU-hours.\n64 points.\nThen a sweep.\nA\nB\nC\nD\n"


def grid(seed: int, points: int) -> str:
    """A pretty-printed JSON grid, four lines a point, every eighth point's seed `seed`: lines repeated through it."""
    rows = []
    for point in range(points):
        rows += ["  {", f'    "point": {point},', f'    "seed": {seed if point % 8 == 3 else point % 8},', "  },"]
    return "[\n" + "\n".join(rows) + "\n]\n"


def test_two_copies_are_compared_the_lines_changed_counted_as_board_d3_says_them() -> None:
    found = compare("PLAN.md", FIRST, SECOND, 1, 2)
    assert (found.changed, found.added, found.removed) == (7, 7, 3)
    assert found.said == "changed since try 1: 7 lines"
    assert found.diff.startswith("--- PLAN.md (try 1)\n+++ PLAN.md (try 2)\n@@ ")
    assert "-Seeds: any.\n" in found.diff
    assert "+Budget: 41.5 CPU-hours.\n" in found.diff
    same = compare("PLAN.md", FIRST, FIRST, 1, 2)
    assert (same.changed, same.said, same.diff) == (0, "unchanged since try 1", "")
    assert compare("PLAN.md", FIRST, FIRST.replace("No budget.", "A budget."), 1, 3).said == (
        "changed since try 1: 1 line"
    )


def test_a_large_file_of_repeated_lines_is_compared_within_seconds() -> None:
    before, after = grid(3, 4_800), grid(30, 4_800)
    assert len(after) > 200_000, "as large as a gate compares in passing"
    began = time.monotonic()
    found = compare("grid.json", before, after, 1, 2)
    assert time.monotonic() - began < 10, "matching every line exactly took minutes"
    assert found.changed == 600, "the seed of every eighth point"
    notes = "# Notes\n" + "".join(f"note {number}\n" for number in range(40))
    small = compare("NOTES.md", notes + "x\n" * 50 + "end\n", notes + "x\n" * 49 + "y\nend\n", 1, 2)
    assert small.changed == 1, "a small file's repeated lines still matched exactly"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


async def two_plans(rig: Rig) -> None:
    """The plan written, sent back at the gate, and written again; the gate waits once more."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": FIRST})
    gate = await until(lambda: question(rig, "You approve the plan"))
    rig.kernel.questions.answer(gate.id, by=OWNER, option="back", text="Fix the budget.")
    again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
    rig.bridge.finish(again.session, {"PLAN.md": SECOND})


async def test_the_runner_compares_a_boxs_last_two_tries_and_a_gate_shows_what_changed_since_the_try_before(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        await two_plans(rig)
        gate = await until(lambda: next((each for each in rig.waiting() if "approve" in each.title), None))
    assert "- PLAN.md (changed since try 1: 7 lines)" in gate.detail
    found = rig.runner.diff(FLOW, "plan")
    assert (found["path"], found["a"], found["b"], found["changed"]) == ("PLAN.md", 1, 2, 7)
    assert found["said"] == "PLAN.md of plan: changed since try 1: 7 lines"
    assert found["diff"].startswith("--- PLAN.md (try 1)\n+++ PLAN.md (try 2)\n")
    assert rig.runner.diff(FLOW, "plan", a=2, b=1)["diff"].startswith("--- PLAN.md (try 2)\n")
    with pytest.raises(RunError, match="plan has no try 3"):
        rig.runner.diff(FLOW, "plan", a=1, b=3)
    with pytest.raises(RunError, match="brief kept no copies of a file twice: nothing to compare"):
        rig.runner.diff(FLOW, "brief")


async def test_a_gate_counts_what_changed_outside_the_services_event_loop(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    counted: list[int] = []

    def counting(path: str, before: str, after: str, a: int, b: int) -> Compared:
        counted.append(threading.get_ident())
        return compare(path, before, after, a, b)

    monkeypatch.setattr(runner_module, "compare", counting)
    loop = threading.get_ident()
    async with running(rig.kernel):
        await two_plans(rig)
        gate = await until(lambda: next((each for each in rig.waiting() if "approve" in each.title), None))
    assert "- PLAN.md (changed since try 1: 7 lines)" in gate.detail
    assert counted, "the gate counted the lines changed"
    assert loop not in counted, "counted in a thread, never on the event loop"


async def test_a_try_that_kept_the_file_by_its_fingerprint_only_says_so(rig: Rig) -> None:
    flow = study()
    flow["defaults"] = {"copied_up_to": 20}
    rig.write_flow(flow)
    async with running(rig.kernel):
        await two_plans(rig)
        await until(lambda: next((each for each in rig.waiting() if "approve" in each.title), None))
    with pytest.raises(RunError, match=r"try 1 of plan kept PLAN\.md by its fingerprint only \(69 bytes, more than"):
        rig.runner.diff(FLOW, "plan", a=1, b=2)
    with pytest.raises(RunError, match=r"try 1 of plan wrote no NOTES\.md"):
        rig.runner.diff(FLOW, "plan", path="NOTES.md", a=1, b=2)
