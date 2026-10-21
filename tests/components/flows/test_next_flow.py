"""Design 0013 §2, §3, §6, §10 and §11 (decisions 0058 and 0091): once a flow's last gate is approved, the next flow is
made from Clank's template with its last INTEGRATE's brief (its `NEXT.md`, else the last of two or more files), named
`<name>-<n>` and titled by the brief's first heading, linked both ways (`follows`, `next`), and the owner is asked
whether to run it now; nothing starts without their answer unless the flow's `next_flow` says so. Run against the fake
bridge and a synthetic folder."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows import following
from clank.components.flows.kinds import Flow
from clank.components.flows.service import TEMPLATE
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.settings import render
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, make_rig, question, running, until

pytestmark = pytest.mark.anyio


def ending(**changes: Any) -> dict[str, Any]:
    """A flow of YOU, PLAN, INTEGRATE and a last GATE: the INTEGRATE writes a summary and the next brief."""
    flow: dict[str, Any] = {
        "schema": "flow/1",
        "title": "Study",
        "defaults": {"model": "daily 262K"},
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the plan", "sees": ["BRIEF.md"], "writes": ["PLAN.md"],
             "prompt": "Write the study plan for the brief."},
            {"id": "join", "type": "integrate", "title": "Put it together", "writes": ["SUMMARY.md", "NEXT.md"]},
            {"id": "review", "type": "gate", "title": "You review the whole", "shows": ["SUMMARY.md"]},
        ],
        "lines": [{"from": "brief", "to": "plan"}, {"from": "plan", "to": "join"}, {"from": "join", "to": "review"}],
    }  # fmt: skip
    flow.update(changes)
    return flow


def record(values: dict[str, Any]) -> Flow:
    """A flow from its file's values (its schema the file's, not a value)."""
    return Flow.model_validate({key: value for key, value in values.items() if key != "schema"})


def template() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return found


def test_integrates_brief_is_its_next_md_else_the_last_of_two_or_more_files_else_none() -> None:
    made = record(ending())
    assert following.last_gate(made) == "review"
    assert following.brief_of(made, "review") == ("join", "NEXT.md")
    other = ending()
    other["boxes"][2]["writes"] = ["notes/next-brief.md", "SUMMARY.md"]
    assert following.brief_of(record(other), "review") == ("join", "SUMMARY.md"), "the last of two"
    other["boxes"][2]["writes"] = ["reports/NEXT.md", "SUMMARY.md"]
    assert following.brief_of(record(other), "review") == ("join", "reports/NEXT.md"), "by its name"
    other["boxes"][2]["writes"] = ["SUMMARY.md"]
    assert following.brief_of(record(other), "review") is None, "a summary alone is no brief"
    ungated = ending(boxes=ending()["boxes"][:3], lines=ending()["lines"][:2])
    assert following.last_gate(record(ungated)) is None, "its last box is no gate"


def test_the_next_flows_name_counts_on_from_this_ones() -> None:
    assert following.next_name("myproject/study", set()) == "myproject/study-2"
    assert following.next_name("myproject/study", {"myproject/study-2"}) == "myproject/study-3"
    assert following.next_name("myproject/study-2", set()) == "myproject/study-3"
    assert following.next_name("myproject/study-9", {"myproject/study-10"}) == "myproject/study-11"


def test_its_title_is_the_briefs_first_heading_else_this_flows_title_next() -> None:
    assert following.title_of("Some words first.\n\n## Run the study\n\n# Later\n", "Study") == "Run the study"
    assert following.title_of("No heading at all.\n", "Study") == "Study, next"


def test_the_next_flow_is_clanks_template_with_its_workspace_model_words_and_where_it_came_from() -> None:
    made = record(ending())
    values = following.next_values(
        template(), "myproject/study", made, run=1, by="join", brief="NEXT.md", replaces="abc", title="Run the study"
    )
    made_next = Flow.model_validate(values)
    assert [box.id for box in made_next.boxes] == [box["id"] for box in template()["boxes"]]
    assert (made_next.title, made_next.workspace, made_next.defaults.model) == (
        "Run the study", "myproject", "daily 262K",
    )  # fmt: skip
    assert made_next.follows is not None
    assert made_next.follows.model_dump() == {
        "flow": "myproject/study", "run": 1, "by": "join", "brief": "NEXT.md", "replaces": "abc",
    }  # fmt: skip
    assert made_next.boxes[0].holds.startswith(
        "Your brief starts as NEXT.md, which join wrote at the end of Study (run 1): Clank copies it into BRIEF.md "
        "when this flow first runs, unless you changed BRIEF.md since."
    )
    assert (made_next.next, made_next.next_flow) == ("", "ask")
    again = record(json.loads(render(made_next)))
    assert again == made_next, "a flow with its links is written back as it reads"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, ending())
    # the flows' preset runs already, so no box waits for a switch of the main slot (design 0013 §7)
    made.kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=OWNER, preset="daily-262k")
    yield made
    made.kernel.close()


NEXT = "# Run the study\n\nRun the grid's 60 points, at most 48 CPU-hours.\n"
NEXT_ID = f"{WORKSPACE}/study-2"


async def to_the_last_gate(rig: Rig, summary_only: bool = False) -> Any:
    """The run started, its brief, plan and INTEGRATE done; the last gate's question."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    join = await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    files = {"SUMMARY.md": "All done.\n"} if summary_only else {"SUMMARY.md": "All done.\n", "NEXT.md": NEXT}
    rig.bridge.finish(join.session, files)
    return await until(lambda: question(rig, "You review the whole"))


def flow_of(rig: Rig, flow: str) -> Flow:
    record = rig.kernel.settings.get(Flow.KIND, flow).record
    assert isinstance(record, Flow)
    return record


def next_question(rig: Rig) -> Any:
    return question(rig, "run the next flow")


async def test_approving_the_last_gate_makes_the_next_flow_linked_both_ways_and_asks_starting_nothing(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        asked = await until(lambda: next_question(rig))
        await anyio.sleep(0.2)
    assert asked.title == "Study is done: run the next flow, Run the study, now?"
    assert [option.id for option in asked.options] == ["run-next", "later"]
    assert asked.about is not None
    assert (asked.about.kind, asked.about.id) == ("flow", NEXT_ID)
    assert "Its brief is NEXT.md, which join wrote" in asked.detail
    made = flow_of(rig, NEXT_ID)
    assert (made.title, made.workspace) == ("Run the study", WORKSPACE)
    assert made.follows is not None
    assert (made.follows.flow, made.follows.run, made.follows.by, made.follows.brief) == (FLOW, 1, "join", "NEXT.md")
    assert flow_of(rig, FLOW).next == NEXT_ID, "linked both ways"
    assert rig.runner.runs.latest(NEXT_ID) is None, "it never starts without your answer"
    assert (rig.folder / "BRIEF.md").read_text(encoding="utf-8") == "About 60 grid points.\n", "no file changed"
    made_events = rig.events("flows.next_made")
    assert [event.data["next"] for event in made_events] == [NEXT_ID]


async def test_a_run_stopped_at_its_last_gate_or_an_integrate_that_wrote_no_brief_makes_none(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="stop")
        await until(lambda: rig.run().status == "stopped")
        await anyio.sleep(0.2)
    assert next_question(rig) is None
    assert flow_of(rig, FLOW).next == ""
    assert rig.events("flows.next_made") == []


async def test_an_integrate_that_wrote_no_brief_makes_none_saying_why(rig: Rig) -> None:
    flow = ending()
    flow["boxes"][2]["writes"] = ["SUMMARY.md"]
    rig.write_flow(flow)
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig, summary_only=True)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        said = await until(lambda: rig.events("flows.next_made"))
    assert said[0].data["next"] == ""
    assert said[0].data["why"] == "no INTEGRATE before review writes a brief (NEXT.md)"
    assert next_question(rig) is None


async def test_run_it_now_starts_the_next_flow_whose_first_run_copies_its_brief_in(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        asked = await until(lambda: next_question(rig))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="run-next")
        brief = await until(lambda: question(rig, "Run the study: Your brief"))
    assert "Your brief starts as NEXT.md, which join wrote at the end of Study (run 1)" in brief.detail
    assert (rig.folder / "BRIEF.md").read_bytes().decode("utf-8") == NEXT, "its brief, copied in as its run began"
    copied = rig.events("flows.next_brief")
    assert [(event.data["into"], event.data["copied"]) for event in copied] == [("BRIEF.md", True)]
    started = rig.runner.runs.latest(NEXT_ID)
    assert started is not None
    assert started.started_by == OWNER


async def test_later_starts_nothing_and_clank_flow_run_starts_it_then(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        asked = await until(lambda: next_question(rig))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="later")
        await anyio.sleep(0.2)
        assert rig.runner.runs.latest(NEXT_ID) is None
        rig.runner.start(NEXT_ID, actor=OWNER)
        await until(lambda: question(rig, "Run the study: Your brief"))


async def test_a_brief_file_the_owner_changed_since_is_kept_as_they_left_it(rig: Rig) -> None:
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        asked = await until(lambda: next_question(rig))
        rig.write("BRIEF.md", "My own next brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="run-next")
        await until(lambda: question(rig, "Run the study: Your brief"))
    assert (rig.folder / "BRIEF.md").read_bytes().decode("utf-8") == "My own next brief.\n"
    kept = rig.events("flows.next_brief")
    assert [event.data["copied"] for event in kept] == [False]
    assert "you changed BRIEF.md since" in kept[0].summary


async def test_a_flow_set_to_run_starts_its_next_flow_unasked_and_one_set_off_makes_none(rig: Rig) -> None:
    rig.write_flow(ending(next_flow="run"))
    async with running(rig.kernel):
        gate = await to_the_last_gate(rig)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        await until(lambda: question(rig, "Run the study: Your brief"))
    assert next_question(rig) is None, "unasked"

    rig.write_flow(ending(next_flow="off"), name="other")
    assert flow_of(rig, f"{WORKSPACE}/other").next_flow == "off"
