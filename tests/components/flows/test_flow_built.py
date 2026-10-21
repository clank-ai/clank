"""Design 0013 §10, §11 and §15 (decisions 0097 and 0098): a flow built with the model carries its `built` mark (the
planning session it was drafted in, when, its brief's file), which reads and is written back unchanged. Clank writes a
draft with its own settings over the draft's (the workspace, auto-accept on, no wait after any box, the next flow asked,
the mark) and the template's model when the draft names none; a built flow keeps its own rules, each refused with its
field: its first box a YOU whose first file is the brief, BRIEF.md, in the folder already and changed since the planning
began (an old one is not the brief), each other file it writes there too; one GATE, its last box; no other YOU;
no box that waits when done; and a box that changes files runs in auto mode (Clank writes it on a task that names no
mode; review is refused), so nothing waits for the owner on the way. A planning's name, when none is given, is the
first free of `flow`, `flow-2`, ..."""

import json
from pathlib import Path
from typing import Any

from clank.components.flows.building import built_problems, built_values, free_name
from clank.components.flows.deliverables import fingerprint
from clank.components.flows.kinds import Flow
from clank.kernel.settings import read_record, render


def built_flow(**changes: Any) -> dict[str, Any]:
    """A flow as Clank writes one built with the model: its brief, a plan, its check, the tasks, the whole put
    together, and the owner's final review."""
    flow: dict[str, Any] = {
        "schema": "flow/1",
        "title": "A new simulation study",
        "workspace": "myproject",
        "defaults": {"model": "frontier 262K"},
        "auto_accept": True,
        "built": {"session": "ses_plan", "at": "2026-10-20T12:00:00Z", "brief": "BRIEF.md"},
        "boxes": [
            {"id": "brief", "type": "you", "title": "Your brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the plan", "sees": ["BRIEF.md"], "writes": ["PLAN.md"],
             "prompt": "Write the study plan."},
            {"id": "check", "type": "verify", "title": "Check the plan", "checks": "plan",
             "sees": ["BRIEF.md", "PLAN.md"]},
            {"id": "split", "type": "decompose", "title": "Break it into tasks", "sees": ["PLAN.md"]},
            {"id": "join", "type": "integrate", "title": "Put it together", "writes": ["SUMMARY.md", "NEXT.md"]},
            {"id": "review", "type": "gate", "title": "You review the whole", "shows": ["SUMMARY.md"]},
        ],
        "lines": [
            {"from": "brief", "to": "plan"}, {"from": "plan", "to": "check"},
            {"from": "check", "to": "split", "when": "pass"}, {"from": "check", "to": "plan", "when": "fail"},
            {"from": "split", "to": "join"}, {"from": "join", "to": "review"},
        ],
    }  # fmt: skip
    flow.update(changes)
    return flow


def test_a_flow_file_with_its_built_mark_reads_and_is_written_back_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "flows" / "myproject" / "study.json"
    path.parent.mkdir(parents=True)
    values = built_flow()
    values.pop("schema")  # the file's, not a value
    path.write_bytes(render(Flow.model_validate(values)).encode("utf-8"))
    found = read_record(Flow, path)
    assert not isinstance(found, list), [str(problem) for problem in found]
    flow, _, raw = found
    assert isinstance(flow, Flow)
    assert flow.built is not None
    assert (flow.built.session, flow.built.brief) == ("ses_plan", "BRIEF.md")
    assert render(flow) == raw.decode("utf-8")
    assert json.loads(raw)["built"] == {"session": "ses_plan", "at": "2026-10-20T12:00:00Z", "brief": "BRIEF.md"}


def drafted(**changes: Any) -> dict[str, Any]:
    """The flow as the model drafts it with `flow_draft`: no settings of Clank's own, no model named."""
    flow = built_flow()
    for key in ("schema", "workspace", "auto_accept", "built"):
        flow.pop(key, None)
    flow["defaults"] = {}
    flow.update(changes)
    return flow


def written(**changes: Any) -> tuple[dict[str, Any], list[str]]:
    return built_values(drafted(**changes), workspace="myproject", model="frontier 262K", built=MARK)


MARK = {"session": "ses_plan", "at": "2026-10-20T12:00:00Z", "brief": "BRIEF.md"}


def problems_of(tmp_path: Path, flow: dict[str, Any], brief: bool = True) -> dict[str, str]:
    """A built flow's own problems, by field, with the brief in the folder or not (written during the planning)."""
    if brief:
        (tmp_path / "BRIEF.md").write_bytes(b"# The study\n\n- at most 48 CPU-hours\n")
    values, _ = built_values(flow, workspace="myproject", model="frontier 262K", built=MARK)
    return {".".join(map(str, place)): said for place, said in built_problems(Flow.model_validate(values), tmp_path)}


def test_clanks_own_settings_win_over_the_drafts_and_the_templates_model_fills_in_for_none() -> None:
    values, said = built_values(
        {**drafted(), "auto_accept": False, "wait_after_every_box": True, "workspace": "other", "next_flow": "run",
         "follows": {"flow": "x/y", "run": 1, "by": "join", "brief": "NEXT.md"}, "schema": "flow/1"},
        workspace="myproject", model="frontier 262K", built=MARK,
    )  # fmt: skip
    flow = Flow.model_validate(values)
    assert (flow.workspace, flow.auto_accept, flow.wait_after_every_box, flow.next_flow) == (
        "myproject", True, False, "ask"
    )  # fmt: skip
    assert flow.follows is None
    assert flow.built is not None
    assert flow.built.session == "ses_plan"
    assert flow.defaults.model == "frontier 262K", "no model named: the template's"
    assert any("auto_accept" in line for line in said), "what Clank set over the draft is said"
    capped, said = written(auto_accept_cap=3)
    assert "auto_accept_cap" not in capped, "a built flow accepts every task its DECOMPOSE proposes"
    assert any("auto_accept_cap" in line and "every task" in line for line in said)
    named, _ = written(defaults={"model": "daily 262K"})
    assert Flow.model_validate(named).defaults.model == "daily 262K", "a model the draft names is kept"


def test_a_built_flow_that_keeps_its_own_rules_has_no_problem(tmp_path: Path) -> None:
    assert problems_of(tmp_path, drafted()) == {}


def test_a_built_flows_brief_comes_first_and_is_in_the_folder(tmp_path: Path) -> None:
    missing = problems_of(tmp_path, drafted(), brief=False)
    assert list(missing) == ["boxes.0.writes.0"]
    assert "BRIEF.md is not in the folder yet" in missing["boxes.0.writes.0"]
    flow = drafted()
    flow["boxes"][0]["writes"] = []
    assert "the brief" in problems_of(tmp_path, flow)["boxes.0.writes"]


def test_a_brief_left_from_before_the_planning_and_every_file_of_the_you_box_are_checked(tmp_path: Path) -> None:
    (tmp_path / "BRIEF.md").write_bytes(b"# An old brief\n")
    values, _ = built_values(drafted(), workspace="myproject", model="frontier 262K", built=MARK)
    old = {"BRIEF.md": fingerprint(tmp_path, "BRIEF.md").sha256}
    found = built_problems(Flow.model_validate(values), tmp_path, before=old)
    assert [place for place, _ in found] == [("boxes", 0, "writes", 0)]
    assert "as it was when the planning began" in found[0][1]
    (tmp_path / "BRIEF.md").write_bytes(b"# The study, as we said\n")
    assert built_problems(Flow.model_validate(values), tmp_path, before=old) == [], "written during the planning"

    more = drafted()
    more["boxes"][0]["writes"] = ["BRIEF.md", "LIMITS.md"]
    named = {".".join(map(str, place)): said for place, said in built_problems(
        Flow.model_validate(built_values(more, workspace="myproject", model="", built=MARK)[0]), tmp_path, before=old
    )}  # fmt: skip
    assert list(named) == ["boxes.0.writes.1"]
    assert "LIMITS.md is not in the folder yet" in named["boxes.0.writes.1"]

    other = drafted()
    other["boxes"][0]["writes"] = ["GOALS.md"]
    (tmp_path / "GOALS.md").write_bytes(b"# Goals\n")
    named = {".".join(map(str, place)): said for place, said in built_problems(
        Flow.model_validate(built_values(other, workspace="myproject", model="", built=MARK)[0]), tmp_path, before=old
    )}  # fmt: skip
    assert "the brief is BRIEF.md" in named["boxes.0.writes.0"]


def test_a_built_flow_waits_only_at_its_last_box_a_gate(tmp_path: Path) -> None:
    gated = drafted()
    gated["boxes"].insert(3, {"id": "approve", "type": "gate", "title": "You approve the plan", "shows": ["PLAN.md"]})
    gated["lines"][2] = {"from": "check", "to": "approve", "when": "pass"}
    gated["lines"].append({"from": "approve", "to": "split"})
    found = problems_of(tmp_path, gated)
    assert list(found) == ["boxes.3.type"]
    assert "only at its end" in found["boxes.3.type"]

    ungated = drafted()
    ungated["boxes"].pop()
    ungated["lines"].pop()
    found = problems_of(tmp_path, ungated)
    assert list(found) == ["boxes.4.type"]
    assert "ends with a GATE" in found["boxes.4.type"]

    waiting = drafted()
    waiting["boxes"][1]["when_done"] = "wait"
    assert "waits only at its end" in problems_of(tmp_path, waiting)["boxes.1.when_done"]


def test_a_built_flow_has_one_you_its_first_box(tmp_path: Path) -> None:
    flow = drafted()
    flow["boxes"].insert(1, {"id": "data", "type": "you", "title": "You fetch the data", "writes": ["data.csv"]})
    flow["lines"][0] = {"from": "brief", "to": "data"}
    flow["lines"].insert(1, {"from": "data", "to": "plan"})
    assert "one YOU" in problems_of(tmp_path, flow)["boxes.1.type"]


def tasked(mode: str | None = None) -> dict[str, Any]:
    """The built flow with a TASK of its own in place of the DECOMPOSE, its mode `mode` (none: left out)."""
    flow = drafted()
    task: dict[str, Any] = {"id": "T1", "type": "task", "title": "The grid", "prompt": "Write the grid.",
                            "writes": ["grid.json"]}  # fmt: skip
    if mode is not None:
        task["mode"] = mode
    flow["boxes"][3] = task
    flow["lines"][2] = {"from": "check", "to": "T1", "when": "pass"}
    flow["lines"][4] = {"from": "T1", "to": "join"}
    return flow


def test_a_built_flows_tasks_run_in_auto_mode_and_review_is_refused(tmp_path: Path) -> None:
    values, said = built_values(tasked(), workspace="myproject", model="frontier 262K", built=MARK)
    flow = Flow.model_validate(values)
    assert [(box.id, box.mode) for box in flow.boxes] == [
        ("brief", None), ("plan", None), ("check", None), ("T1", "auto"), ("join", None), ("review", None)
    ], "a task runs in auto, the planner's boxes in plan"  # fmt: skip
    assert any('boxes.3.mode to "auto"' in line for line in said)
    found = problems_of(tmp_path, tasked("review"))
    assert list(found) == ["boxes.3.mode"]
    assert "review would make each change T1 asks to make wait for the user" in found["boxes.3.mode"]
    assert problems_of(tmp_path, tasked("auto")) == {}


def test_the_first_free_name_is_flow_then_flow_2() -> None:
    assert free_name("myproject", set()) == "flow"
    assert free_name("myproject", {"myproject/flow", "other/flow-2"}) == "flow-2"
    assert free_name("myproject", {"myproject/flow", "myproject/flow-2"}) == "flow-3"
