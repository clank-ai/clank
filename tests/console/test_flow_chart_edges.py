"""Design 0012 §6.3 and §11 step 6, revised at the owner's comment on the prototype ("we need to be sure we are testing
out edge cases for dealing with this in practice"): over sessions generated from a seed (many steps, many calls made at
once, subagents within subagents, long names, wide characters, failures, notes, compactions, a revert), at the widths
the Monitor gives its flow and narrower ones, folded as by default and wholly open, no node, junction or label overlaps
another and every line stays within the panel's width; every node not folded away is drawn once, and the nodes in
reading order go down the lines; the cursor following now lights the newest node drawn, laid out as without it, and a
cursor folded away lights the fold that hides it. A session of one message, or of nothing yet, draws its root."""

import pytest

from clank.components.agents.console.flowchart import plain, render
from clank.components.agents.console.flowtree import tree
from clank.components.agents.sessionflow.flow import Flow
from tests.support.boards import opened
from tests.support.flowgen import drawn_once, generated, junctions_line_up
from tests.support.flowlines import SESSION, lines, page, status, user

SEEDS = range(40)
WIDTHS = (128, 88, 60, 41, 23, 9)


@pytest.mark.parametrize("seed", SEEDS)
def test_over_generated_sessions_at_every_width_no_node_junction_or_label_overlaps_and_every_line_fits(
    seed: int,
) -> None:
    view, subagents = generated(seed)
    for folds in ({}, opened(view, subagents)):
        for width in WIDTHS:
            drawn = render(view, width, folds=folds, subagents=subagents)
            assert all(line.cell_length <= width for line in drawn.lines), (seed, width)
            assert junctions_line_up(drawn) == [], (seed, width)


@pytest.mark.parametrize("seed", SEEDS)
def test_over_generated_sessions_every_node_is_drawn_once_and_reached_in_reading_order(seed: int) -> None:
    view, subagents = generated(seed)
    for folds in ({}, opened(view, subagents)):
        root = tree(view, folds, subagents)
        for width in WIDTHS:
            drawn = render(view, width, folds=folds, subagents=subagents)
            assert drawn_once(drawn, root) == [], (seed, width)
            assert drawn.now in drawn.row, "the newest node, or the fold that hides it, is drawn"
            following = render(view, width, folds=folds, subagents=subagents, follow=True)
            assert following.cursor == following.now == drawn.now, (seed, width)
            assert plain(following) == plain(drawn), (seed, width)
            hidden = [id for id in drawn.nodes if id not in drawn.row]
            if hidden:
                moved = render(view, width, hidden[-1], folds, subagents)
                assert moved.cursor == drawn.shown(hidden[-1]) in drawn.row, (seed, width)


def test_a_session_of_one_message_and_nothing_yet_draws_its_root() -> None:
    flow = Flow(SESSION)
    assert plain(render(flow.view(), 88)) == "You", "nothing yet: the root alone"
    flow.history(page([user("msg_01", 1_000, "Plot tau against p.")]))
    for line in lines([status("busy")]):
        flow.heard(line)
    assert plain(render(flow.view(), 88)) == "You ─── ● Plot tau against p."
    assert plain(render(flow.view(), 60)) == "You\n└─ ● Plot tau against p."
    assert render(None, 88).lines == []
