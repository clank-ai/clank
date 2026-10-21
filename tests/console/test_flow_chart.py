"""Design 0012 §6.3 and §11 step 6, board A: the session's flow laid out in lines. Time runs down and the branches open
to the right of their node, joined by box-drawing lines whose junctions stand in one column; under 70 columns, or where
the room to the right is short, a node's children stand under it. Snapshots of board A's flow and of a session with
every kind of node (calls made at once, subagents within a subagent, a dead end, a compaction band, a note), at 128, 88
and 60 columns: the Session view's page without the machine column, beside it, and stacked. Every junction lines up
with the branches it joins; nothing spills out of a node or the panel at any width (a node's words cut with "…"); the
current node alone is highlighted; a folded node says what it holds."""

import pytest
from rich.cells import cell_len

from clank.components.agents.console.flowchart import STACK_BELOW, cut, plain, render
from clank.console.style import current
from tests.console.frames import assert_frame
from tests.support.boards import board_a, every_kind, opened
from tests.support.flowgen import junctions_line_up

WIDTHS = (128, 88, 60)
AS_DRAWN = {"todo:1": False, "todo:2": False, "together:msg_04": False}  # board A's folds, as it draws them


@pytest.mark.parametrize("width", WIDTHS)
def test_board_as_flow_at_128_88_and_60_columns(width: int) -> None:
    view, subagents = board_a()
    drawn = render(view, width, subagents=subagents)
    assert_frame(plain(drawn), f"flow-board-a-{width}")
    assert junctions_line_up(drawn) == []
    if width == 128:
        as_drawn = render(view, width, folds=AS_DRAWN, subagents=subagents)
        assert_frame(plain(as_drawn), "flow-board-a-as-drawn-128")
        assert junctions_line_up(as_drawn) == []


@pytest.mark.parametrize("width", WIDTHS)
def test_calls_made_at_once_subagents_a_dead_end_a_band_and_a_note_at_128_88_and_60_columns(width: int) -> None:
    view, subagents = every_kind()
    drawn = render(view, width, folds=opened(view, subagents), subagents=subagents)
    assert_frame(plain(drawn), f"flow-every-kind-{width}")
    assert junctions_line_up(drawn) == []
    folded = render(view, width, subagents=subagents)
    bands = [row for row in plain(folded).splitlines() if "compacted by OpenCode" in row]
    assert len(bands) == 1, "one band"
    assert "data/tau.csv" not in plain(folded), "the band folds what is above it"
    assert junctions_line_up(folded) == []


def test_every_junction_lines_up_with_the_branches_it_joins() -> None:
    view, subagents = every_kind()
    folds = opened(view, subagents)
    for width in range(30, 141, 7):
        drawn = render(view, width, folds=folds, subagents=subagents)
        assert junctions_line_up(drawn) == [], width
    beside = render(*board_a()[:1], 128, folds=AS_DRAWN)
    rows = plain(beside).splitlines()
    column = rows[0].index(current().tree.split)
    assert {row[column] for row in rows[1:]} <= {"│", "├", "└", " "}, "the root's children: one column of junctions"
    assert rows[-1][column] == "└"


def test_nothing_spills_out_of_a_node_or_the_panel() -> None:
    view, subagents = every_kind()
    folds = opened(view, subagents)
    for width in range(1, 161):
        for drawn in (render(view, width, folds=folds, subagents=subagents), render(view, width)):
            assert all(line.cell_length <= width for line in drawn.lines), width
            assert all(span.end <= width for spans in drawn.spans for span in spans), width
    narrow = plain(render(view, 60, folds=folds, subagents=subagents))
    assert "✗ bash python plot.py --n 8 16 --verbose" in narrow
    assert "--verbose --verbose --verbose --verbose --verbose" not in narrow, "a long command is cut"
    assert "… ⊘" in narrow, "cut with the style's mark, its end kept"
    assert cut("數據分析", 5) == "數據…", "a wide character is never split"
    assert cell_len(cut("數據分析", 5)) <= 5


def test_the_current_node_alone_is_highlighted() -> None:
    view, subagents = board_a()
    drawn = render(view, 128, cursor="c20", subagents=subagents)
    lit = [
        (row, span.start, span.end)
        for row, line in enumerate(drawn.lines)
        for span in line.spans
        if "selection" in str(span.style)
    ]
    rows = {row for row, _, _ in lit}
    assert rows == {drawn.row["c20"]}, "one line"
    node = next(span for span in drawn.spans[drawn.row["c20"]] if span.id == "c20")
    assert all(node.start <= start and end <= node.end for _, start, end in lit), "only the node's own cells"
    assert drawn.now == "msg_21", "the newest node: the step answering now"


def test_a_folded_node_says_what_it_holds() -> None:
    view, subagents = board_a()
    rows = plain(render(view, 128, subagents=subagents)).splitlines()
    done = next(row for row in rows if "Read the simulator and last study" in row)
    assert done.endswith("Read the simulator and last study ▸  6 calls")
    shown = render(view, 128, subagents=subagents)
    assert "c03" not in shown.row, "what it folds is not drawn"
    assert shown.shown("c03") == "todo:1", "the fold that hides it is drawn for it"
    assert render(view, STACK_BELOW - 1, subagents=subagents).lines[0].plain == "You", "stacked: the root alone"
