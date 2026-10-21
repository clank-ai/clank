"""Design 0013 §3, §12 and §14 step 6: the Flow view's flow laid out (`boxchart.render`, a pure function). Its stages
(one box, or a DECOMPOSE's tasks fanned out and joined) read left to right in rows that wrap, a line from each row's
last stage down and back to the next row's first; each box shows its type in its color, its title, its model and its
last result, its border its state; a VERIFY's fail line runs under its row back to the box it checks, labeled, or is a
label alone when that box is not in its row; lines are green for pass, red for fail, the "now" color on the path being
run and dashed for what has not run; below 70 columns the flow is the list of board D2's left. The layout's edge cases
(the owner's comment on the prototype, 2026-10-18): over generated flows of 1 to 12 tasks, with and without proposals
waiting, a fail loop, an added box and the next flow, with titles longer than a box, at the Flow panel's widths at 128
and 88 columns and below 70, no box, line label or legend touches another and every line stays inside its panel; a
flow taller than its panel keeps its boxes whole and apart. Snapshots: board D1's flow at those widths."""

from datetime import UTC

import pytest

from clank.components.agents.console.boxchart import BOX_ROWS, LIST_BELOW, render, stages
from clank.console.style import current
from tests.console.frames import assert_frame
from tests.support.flowshapes import d1_view, generated, shapes, touching

WIDE, NARROW, LISTED = 79, 81, 60  # the Flow panel's drawing area at 128 columns, at 88 (stacked), and below 70


def text(chart: object) -> str:
    return "\n".join(line.plain for line in chart.lines)  # type: ignore[attr-defined]


def test_board_d1s_stages_are_its_boxes_in_the_order_they_run_its_tasks_one_fan() -> None:
    assert stages(d1_view()) == [
        ["brief"], ["plan"], ["check"], ["approve"], ["split"], ["T1", "T2", "T3", "T4"], ["join"], ["review"],
    ]  # fmt: skip


@pytest.mark.parametrize(("width", "name"), [(WIDE, "boxchart-d1-79"), (NARROW, "boxchart-d1-81")])
def test_board_d1_is_laid_out_in_rows_of_stages_its_tasks_a_fan_at_the_widths_of_the_flow_panel(
    width: int, name: str
) -> None:
    chart = render(d1_view(), width, selected="T2", zone=UTC)
    assert touching(chart) == []
    assert not chart.listed
    boxes = chart.boxes
    assert boxes["brief"].y == boxes["plan"].y == boxes["check"].y, "the first row: brief, plan, check"
    assert boxes["approve"].y > boxes["check"].y, "the next row"
    assert [boxes[id].x for id in ("T1", "T2", "T3", "T4")] == [boxes["T1"].x] * 4, "the tasks stacked, one fan"
    assert boxes["T1"].y < boxes["T2"].y < boxes["T3"].y < boxes["T4"].y
    assert chart.order[:3] == ["brief", "plan", "check"]
    shown = text(chart)
    assert "Estimate run times" in shown
    assert "step" not in shown, "no Live given: the running box says no step"
    assert_frame(shown + "\n", name)


def test_the_running_box_shows_its_step_and_speed_and_the_selected_box_is_lit() -> None:
    chart = render(d1_view(), WIDE, selected="T2", live={"step": 14, "speed": 48.0}, zone=UTC)
    rect = chart.boxes["T2"]
    inside = [chart.lines[row].plain[rect.x : rect.x + rect.w] for row in range(rect.y, rect.y + rect.h)]
    assert "step 14" in inside[1]
    assert "48 tok/s" in inside[3]
    title_cell = chart.style_at(rect.x + 2, rect.y + 2)
    assert "$clank-selection" in title_cell, "the box selected, on the selection color"
    assert "$clank-now" in chart.style_at(rect.x, rect.y), "a running box's border in the now color"
    assert chart.lines[rect.y].plain[rect.x] == "┏", "a heavier border while it runs"


def test_below_70_columns_the_flow_is_the_list_of_board_d2s_left() -> None:
    chart = render(d1_view(), LISTED, selected="T2", zone=UTC)
    assert chart.listed
    assert touching(chart) == []
    shown = text(chart)
    assert_frame(shown + "\n", "boxchart-d1-60")
    lines = shown.splitlines()
    t1 = next(line for line in lines if "The parameter grid" in line)
    split = next(line for line in lines if "Break it into tasks" in line)
    assert len(t1) - len(t1.lstrip()) > len(split) - len(split.lstrip()), "the tasks indented under DECOMPOSE"
    assert LIST_BELOW == 70


def test_a_fail_line_runs_under_its_row_back_to_the_box_it_checks_labeled_or_is_a_label_alone() -> None:
    chart = render(d1_view(), WIDE, zone=UTC)
    plan, check = chart.boxes["plan"], chart.boxes["check"]
    band = plan.y + plan.h
    assert "fail" in chart.lines[band].plain, "the fail line's label, under the row"
    assert chart.lines[plan.y + plan.h - 1].plain[plan.x : plan.x + plan.w].count("▴") == 1, "back into the plan"
    assert "$clank-failed" in chart.style_at(check.x + check.w // 3, band), "red: the fail line was taken"
    alone = render(generated(1, loop=True, added=True, long=True, running=1), 70, zone=UTC)
    assert touching(alone) == []


def test_lines_are_green_for_pass_red_for_fail_the_now_color_on_the_path_run_and_dashed_for_what_has_not_run() -> None:
    chart = render(d1_view(), WIDE, zone=UTC)
    check, t2, t3 = chart.boxes["check"], chart.boxes["T2"], chart.boxes["T3"]
    glyphs = current().tree
    exit = (check.x + check.w - 2, check.y + check.h - 1)  # the pass line leaves the row's last box below it
    assert chart.lines[exit[1]].plain[exit[0]] == "┬"
    assert "$clank-good" in chart.style_at(*exit), "the pass line, green"
    assert "$clank-now" in chart.style_at(t2.x - 1, t2.y + 1), "into the box running: the now color"
    assert chart.lines[t3.y + 1].plain[t3.x - 1] == glyphs.arrow
    assert "$clank-dim" in chart.style_at(t3.x - 1, t3.y + 1), "into a box not run yet: dim"
    assert glyphs.not_yet in chart.lines[t3.y + 1].plain[t3.x + t3.w : t3.x + t3.w + 3], "and dashed"


@pytest.mark.parametrize("width", [WIDE, NARROW, LISTED, 70, 74, 96, 110, 126])
def test_over_generated_flows_no_box_label_or_legend_touches_another_and_every_line_fits_its_panel(width: int) -> None:
    for name, shown in shapes():
        chart = render(shown, width, selected="T1", live={"step": 3, "speed": 51.5}, zone=UTC)
        assert touching(chart) == [], f"{name} at {width} columns"
        drawn = set(chart.boxes)
        wanted = {each["id"] for each in shown["boxes"]} | ({"next-flow"} if shown["next_flow"] else set())
        assert drawn == wanted, f"{name} at {width} columns: each box drawn once"


def test_a_flow_taller_than_its_panel_keeps_its_boxes_whole_and_apart() -> None:
    chart = render(generated(12, running=3), WIDE, zone=UTC)
    assert len(chart.lines) > 60, "twelve tasks stacked: far taller than a panel, which scrolls"
    assert all(rect.h == BOX_ROWS for rect in chart.boxes.values())
    assert touching(chart) == []


@pytest.mark.parametrize("width", [WIDE, NARROW, 100, 110, 126])
def test_a_boxs_type_and_tries_are_kept_whole_its_step_shortened_or_left_out_first(width: int) -> None:
    shown = d1_view()
    for box in shown["boxes"]:
        if box["id"] == "T2":
            box["tries"] = [box["tries"][0], {**box["tries"][0], "number": 2}]
        if box["id"] == "split":
            box["state"] = "running"
    chart = render(shown, width, live={"step": 14, "speed": 48.0}, zone=UTC)
    for name, words in (("T2", "TASK T2 ⟲2"), ("split", "DECOMPOSE")):
        rect = chart.boxes[name]
        line = chart.lines[rect.y + 1].plain[rect.x : rect.x + rect.w]
        assert words in line, f"{name} at {width}: {line!r}"
        assert current().marks.cut not in line, f"{name} at {width}: nothing of its type or tries cut: {line!r}"
