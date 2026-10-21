"""Design 0013 §2, §3, §4 and §11 (decisions 0057 and 0066): a flow is a readable settings file of the kinds `Flow`,
`Box` and `Line`; board D1's flow loads and is written back unchanged; a flow that breaks §3's rules is refused, each
problem naming the file, the line and the field; a VERIFY has its two lines, pass and fail; a file a box writes, sees
or shows lies in the folder; DECOMPOSE's tasks fan out and join, and nothing else does; and Clank's template keeps
every rule."""

import copy
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.rules import effective_mode
from clank.kernel.records import undocumented_fields
from clank.kernel.settings import DEFAULTS, SettingsProblem, read_record, render

D1 = Path(__file__).with_name("d1-flow.json")
TEMPLATE = DEFAULTS / "templates" / "flow.json"


def d1() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(D1.read_text(encoding="utf-8"))
    return loaded


def refused(tmp_path: Path, flow: dict[str, Any]) -> tuple[list[SettingsProblem], list[str]]:
    """The problems found reading `flow` from a file, and the file's lines."""
    text = json.dumps(flow, indent=2, ensure_ascii=False) + "\n"
    path = tmp_path / "flows" / "myproject" / "study.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    found = read_record(Flow, path)
    assert isinstance(found, list), "the flow was read, not refused"
    assert {problem.path for problem in found} == {path}
    return found, text.splitlines()


def named(problems: list[SettingsProblem], lines: list[str]) -> dict[str, tuple[str, str]]:
    """Each problem by its field: the text of the line it names, and its message."""
    return {str(p.field): (lines[p.line - 1].strip() if p.line else "", p.message) for p in problems}


def test_board_d1s_flow_loads_and_is_written_back_unchanged() -> None:
    found = read_record(Flow, D1)
    assert not isinstance(found, list), [str(problem) for problem in found]
    flow, version, raw = found
    assert version == 1
    assert render(flow) == raw.decode("utf-8")
    assert isinstance(flow, Flow)
    assert [box.id for box in flow.boxes] == [
        "brief", "plan", "check", "approve", "split", "T1", "T2", "T3", "T4", "join", "review"
    ]  # fmt: skip
    assert flow.defaults.tries == 3
    assert (flow.defaults.limits.minutes, flow.defaults.limits.tokens) == (30, 200_000)
    assert flow.lines[3].from_ == "check"
    assert (flow.lines[3].to, flow.lines[3].when) == ("plan", "fail")


def test_a_line_back_that_is_not_a_verifys_fail_is_refused_naming_its_line_and_field(tmp_path: Path) -> None:
    flow = d1()
    flow["lines"].append({"from": "approve", "to": "plan"})
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["lines.14.to"]
    line, message = found["lines.14.to"]
    assert line == '"to": "plan"'
    assert "only a VERIFY's fail line may point back" in message


def test_a_fail_line_must_lead_back_to_the_box_its_verify_checks(tmp_path: Path) -> None:
    flow = d1()
    flow["lines"][3]["to"] = "brief"
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["lines.3.to"]
    assert found["lines.3.to"][0] == '"to": "brief",'
    assert "the box it checks (plan)" in found["lines.3.to"][1]


def test_a_box_with_two_lines_on_is_refused(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"].append({"id": "extra", "type": "task", "title": "Something more", "writes": ["extra.md"]})
    flow["lines"].append({"from": "approve", "to": "extra"})
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["lines.14.from"]
    assert found["lines.14.from"][0] == '"from": "approve",'
    assert "goes on to one box" in found["lines.14.from"][1]


def test_a_join_is_refused_outside_decomposes_tasks(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"].append({"id": "extra", "type": "task", "title": "Something more", "writes": ["extra.md"]})
    flow["lines"] += [{"from": "plan", "to": "extra"}, {"from": "extra", "to": "check"}]
    found = named(*refused(tmp_path, flow))
    assert sorted(found) == ["lines.14.from", "lines.15.to"]
    assert found["lines.15.to"][0] == '"to": "check"'
    assert "is reached by one line" in found["lines.15.to"][1]


def test_a_verify_checking_a_box_that_is_not_before_it_is_refused(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"][2]["checks"] = "split"
    flow["lines"][3]["to"] = "split"
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["boxes.2.checks"]
    assert found["boxes.2.checks"][0] == '"checks": "split",'
    assert "does not come before it" in found["boxes.2.checks"][1]


def test_a_verify_without_its_fail_line_or_its_pass_line_is_refused(tmp_path: Path) -> None:
    flow = d1()
    del flow["lines"][3]
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["boxes.2.id"]
    assert found["boxes.2.id"][0] == '"id": "check",'
    assert "no fail line back to plan" in found["boxes.2.id"][1]
    last = {
        "schema": "flow/1",
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief"},
            {"id": "plan", "type": "plan", "title": "Plan"},
            {"id": "check", "type": "verify", "title": "Check", "checks": "plan"},
        ],
        "lines": [
            {"from": "brief", "to": "plan"},
            {"from": "plan", "to": "check"},
            {"from": "check", "to": "plan", "when": "fail"},
        ],
    }
    found = named(*refused(tmp_path, last))
    assert list(found) == ["boxes.2.id"]
    assert "no pass line" in found["boxes.2.id"][1]


def test_a_box_no_line_reaches_is_refused(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"].append({"id": "extra", "type": "task", "title": "Something more", "writes": ["extra.md"]})
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["boxes.11.id"]
    assert found["boxes.11.id"][0] == '"id": "extra",'
    assert "no line reaches it" in found["boxes.11.id"][1]


def test_a_deliverable_that_is_not_markdown_in_a_box_in_plan_mode_is_refused(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"][1]["writes"].append("grid.json")
    flow["boxes"][5]["mode"] = "plan"
    found = named(*refused(tmp_path, flow))
    assert sorted(found) == ["boxes.1.writes.1", "boxes.5.writes.0"]
    assert found["boxes.1.writes.1"][0] == '"grid.json"'
    assert "Plan mode" in found["boxes.1.writes.1"][1]
    assert effective_mode(Box(id="T3", type="task", title="The sweep script")) is None
    assert effective_mode(Box(id="check", type="verify", title="Check", checks="plan")) == "plan"


@pytest.mark.parametrize(
    ("change", "field", "line", "words"),
    [
        (lambda f: f["lines"].append({"from": "review", "to": "nowhere"}), "lines.14.to", '"to": "nowhere"', "no box"),
        (lambda f: f["lines"][0].update(when="pass"), "lines.0.when", '"when": "pass"', "only a VERIFY's lines"),
        (lambda f: f["lines"][2].pop("when"), "lines.2.when", "{", "pass or fail"),
        (
            lambda f: f["boxes"].append({"id": "brief", "type": "gate", "title": "Again"}),
            "boxes.11.id", '"id": "brief",', "an earlier box",
        ),
        (lambda f: f["boxes"][0].update(type="plan"), "boxes.0.type", '"type": "plan",', "first box is a YOU"),
        (lambda f: f["boxes"][3].update(model="daily 262K"), "boxes.3.model", '"model": "daily 262K"', "done by you"),
        (lambda f: f["boxes"][2].pop("checks"), "boxes.2.checks", "{", "names the box"),
        (lambda f: f["boxes"][1].update(checks="brief"), "boxes.1.checks", '"checks": "brief"', "only a VERIFY"),
        (lambda f: f["boxes"][9].update(checks="T4"), "boxes.9.checks", '"checks": "T4"', "join is an INTEGRATE"),
    ],
)  # fmt: skip
def test_each_other_rule_refuses_its_flow_naming_the_line_and_field(
    tmp_path: Path, change: Any, field: str, line: str, words: str
) -> None:
    flow = d1()
    change(flow)
    found = named(*refused(tmp_path, flow))
    assert list(found) == [field]
    assert found[field][0] == line
    assert words in found[field][1]


@pytest.mark.parametrize("path", ["/etc/passwd", "D:/projects/notes.md", "../outside.md", "runs\\estimates.md"])
def test_a_deliverable_outside_the_folder_is_refused(tmp_path: Path, path: str) -> None:
    flow = d1()
    flow["boxes"][6]["writes"] = [path]
    found = named(*refused(tmp_path, flow))
    assert list(found) == ["boxes.6.writes.0"]
    assert "folder" in found["boxes.6.writes.0"][1]


def test_decomposes_tasks_fan_out_and_join_but_another_box_may_not(tmp_path: Path) -> None:
    flow = d1()
    flow["boxes"][4]["type"] = "task"
    found = named(*refused(tmp_path, flow))
    assert {"lines.6.from", "lines.7.from", "lines.8.from", "lines.10.to", "lines.11.to", "lines.12.to"} <= set(found)
    assert "only a DECOMPOSE's tasks fan out" in found["lines.6.from"][1]


@pytest.mark.parametrize("type", ["gate", "you", "plan"])
def test_a_decompose_fans_out_to_its_tasks_only(tmp_path: Path, type: str) -> None:
    flow = d1()
    for box in flow["boxes"][5:9]:
        box["type"] = type
        box.pop("writes", None)
    found = named(*refused(tmp_path, flow))
    assert {"lines.6.from", "lines.7.from", "lines.8.from", "lines.10.to", "lines.11.to", "lines.12.to"} <= set(found)
    assert "only a DECOMPOSE's tasks fan out" in found["lines.6.from"][1]


def test_a_flow_of_thousands_of_boxes_in_a_chain_is_read_without_a_crash() -> None:
    boxes = [{"id": "brief", "type": "you", "title": "Brief"}]
    boxes += [{"id": f"t{n}", "type": "task", "title": f"Task {n}"} for n in range(3000)]
    lines = [{"from": a["id"], "to": b["id"]} for a, b in pairwise(boxes)]
    assert len(Flow.model_validate({"boxes": boxes, "lines": lines}).boxes) == 3001
    lines.append({"from": "t2999", "to": "t5"})
    with pytest.raises(ValueError, match="only a VERIFY's fail line may point back"):
        Flow.model_validate({"boxes": boxes, "lines": lines})


def test_every_field_of_a_flow_has_a_label_and_help() -> None:
    assert undocumented_fields(Flow) == []


def test_a_flow_has_its_place_among_the_settings() -> None:
    assert (Flow.KIND, Flow.folder(), Flow.GROUPED_BY) == ("flow", "flows", "workspace")
    copied = copy.deepcopy(d1())
    copied.pop("schema")
    assert Flow.model_validate(copied).title == "A new simulation study"


def test_clanks_template_reads_as_a_flow_that_keeps_every_rule_for_any_workspace() -> None:
    found = read_record(Flow, TEMPLATE)
    assert not isinstance(found, list), [str(problem) for problem in found]
    flow, _, raw = found
    assert isinstance(flow, Flow)
    assert render(flow) == raw.decode("utf-8"), "the template is in the settings files' one fixed format"
    assert flow.workspace == ""
    assert [box.type for box in flow.boxes] == ["you", "plan", "verify", "gate", "decompose", "integrate", "gate"]
    presets = DEFAULTS / "presets"
    names = {path.stem for path in presets.glob("*.json")}
    names |= {json.loads(path.read_text(encoding="utf-8"))["title"] for path in presets.glob("*.json")}
    assert {model for model in (flow.defaults.model, *(box.model for box in flow.boxes)) if model} <= names


def test_clanks_template_runs_its_boxes_on_what_the_main_slot_runs_so_a_new_flow_switches_nothing() -> None:
    # Decision 0117 (superseding 0095 for the shipped default): a flow made from the template, the next flow too, runs
    # on whatever model the main slot runs, local or cloud, and never switches it.
    found = read_record(Flow, TEMPLATE)
    assert not isinstance(found, list), [str(problem) for problem in found]
    flow = found[0]
    assert isinstance(flow, Flow)
    assert flow.defaults.model == ""
    assert [box.model for box in flow.boxes if box.model] == []
