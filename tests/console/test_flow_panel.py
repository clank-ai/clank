"""Design 0012 §6.5, §2 (keys, redraws) and §11 step 6: the Flow panel's drawing, a widget of lines. ↑ and ↓ move from
node to node in reading order; ← folds a branch, and on a node that does not fold goes to its parent; → opens a folded
branch, and on an open one goes to its first child; End goes back to now, and the cursor follows now until the owner
moves it; a key that has nothing to do is left to the console (← on the root goes back to the menu). Enter shows the
node whole, with what an inference about it rests on (§6.4). Only the rows that changed are laid out again (design
0001 §5.7), and the same flow again lays out nothing; a flow that changed is laid out once, the cursor on now while
it follows now. With no flow it says "no session yet". A node's details show its text as it was written: a call's
input in square brackets is not read as the console's markup (decision 0045: whole, one key away)."""

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label

from clank.components.agents.console.flowchart import render
from clank.components.agents.console.flowpanel import FlowChart
from clank.components.agents.console.flowtree import tree
from clank.console.details import DetailsScreen
from clank.console.style import LoadedStyle, theme_of, use
from clank.kernel.console_kinds import StyleSettings
from tests.console.frames import settle
from tests.support.boards import board_a

pytestmark = pytest.mark.anyio


class Chart(App[None]):
    """The widget alone, in Clank's style, 100 columns wide."""

    def __init__(self) -> None:
        super().__init__()
        loaded = LoadedStyle("test", StyleSettings())
        use(loaded)
        self.register_theme(theme_of(loaded))
        self.theme = "test"
        self.left_to_the_app = 0

    def compose(self) -> ComposeResult:
        yield FlowChart(id="chart")

    def action_outward(self) -> None:
        self.left_to_the_app += 1

    BINDINGS = [("left", "outward", "back")]  # noqa: RUF012 (Textual's own form)


def chart(app: App[Any]) -> FlowChart:
    return app.query_one("#chart", FlowChart)


async def shown(pilot: Any, app: Chart, view: dict[str, Any] | None = None, subagents: Any = None) -> FlowChart:
    """The widget with the focus, showing board A's flow (or the one given)."""
    widget = chart(app)
    widget.focus()
    if view is None:
        view, subagents = board_a()
    widget.show(view, subagents, key="board-a")
    await settle(pilot, lambda: bool(widget.drawn.lines))
    return widget


async def test_up_and_down_move_from_node_to_node_in_reading_order() -> None:
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = await shown(pilot, app)
        order = widget.drawn.order
        assert widget.cursor == "msg_21", "it starts on now"
        await pilot.press("up")
        assert widget.cursor == order[order.index("msg_21") - 1] == "msg_20", "the note"
        await pilot.press("up", "up", "up")
        assert widget.cursor == "c19"
        await pilot.press("down")
        assert widget.cursor == "msg_18:end"
        assert widget.following is False, "moved: no longer following now"


async def test_left_folds_and_right_opens_a_branch_and_left_on_a_leaf_goes_to_its_parent() -> None:
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = await shown(pilot, app)
        widget.cursor = "todo:1"
        widget.following = False
        await pilot.press("right")
        assert widget.drawn.nodes["todo:1"].folded is False, "opened"
        assert "c02" in widget.drawn.row
        await pilot.press("right")
        assert widget.cursor == "c02", "on an open branch: its first child"
        await pilot.press("left")
        assert widget.cursor == "todo:1", "on a leaf: its parent"
        await pilot.press("left")
        assert widget.drawn.nodes["todo:1"].folded is True, "folded again"
        assert "c02" not in widget.drawn.row
        await pilot.press("left")
        assert widget.cursor == "root"
        await pilot.press("left")
        assert app.left_to_the_app == 1, "nothing to fold and no parent: the console's own Left acts"


async def test_end_goes_back_to_now_and_the_cursor_follows_it_until_moved() -> None:
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = await shown(pilot, app)
        await pilot.press("up", "up")
        assert (widget.cursor, widget.following) == ("c20", False)
        view, subagents = board_a()
        later = next(node for node in view["nodes"] if node["id"] == "msg_21")
        later["ended"], later["text"] = "finished", "The grid: 16, 32 and 64."
        widget.show(view, subagents, key="board-a")
        await pilot.pause()
        assert widget.cursor == "c20", "moved by the owner: it stays"
        await pilot.press("end")
        assert (widget.cursor, widget.following) == (widget.drawn.now, True)
        assert widget.cursor == "msg_21"


async def test_only_the_rows_that_changed_are_laid_out_again() -> None:
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = await shown(pilot, app)
        await pilot.pause()
        first = widget.laid_out
        assert first == len(widget.drawn.lines), "each line laid out once"
        view, subagents = board_a()
        widget.show(view, subagents, key="board-a")
        await pilot.pause()
        assert widget.laid_out == first, "the same flow again: nothing laid out"
        for node in view["nodes"]:
            if node["id"] == "msg_21":
                node["request"] = {**node["request"], "tokens": 1500}
        widget.show(view, subagents, key="board-a")
        await pilot.pause()
        assert widget.laid_out == first + 1, "the one line that changed"
        assert "about 1,500 tokens" in widget.drawn.lines[widget.drawn.row["msg_21"]].plain


async def test_with_no_flow_it_says_no_session_yet() -> None:
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = chart(app)
        await pilot.pause()
        assert [line.plain for line in widget.drawn.lines] == ["no session yet"]
        widget.show(None, None, key="", empty="no flow of this session yet")
        await pilot.pause()
        assert [line.plain for line in widget.drawn.lines] == ["no flow of this session yet"]


async def test_enter_on_a_node_shows_it_whole_and_what_an_inference_rests_on() -> None:
    app = Chart()
    async with app.run_test(size=(60, 40)) as pilot:
        widget = await shown(pilot, app)
        widget.cursor, widget.following = "c19", False
        widget.show(*board_a(), key="board-a")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        said = "\n".join(app.screen.lines)
        assert app.screen.heading == "A call: a dead end"
        assert "bash python -m myproject sweep --sizes 8 16 32 64 128 256" in said, "whole, though the panel cut it"
        assert "it ended in an error and the agent moved on: a later step began" in said, "what the inference rests on"
        assert "Tool execution aborted" in said
        await pilot.press("escape")
        widget.cursor = "msg_21"
        widget.show(*board_a(), key="board-a")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        said = "\n".join(app.screen.lines)
        assert "Its request at the gateway: answering, about 1,415 tokens" in said
        assert "paired in order by time: no call ids confirm it" in said, "how it was paired, and why"


async def test_details_show_a_nodes_text_as_written_brackets_and_all() -> None:
    view, subagents = board_a()
    call = next(node for node in view["nodes"] if node["id"] == "c19")
    call["input"] = 'sed -e "s/[/]/_/g" notes.md'
    call["error"] = "def f(x: list[str]) -> dict[str, int]: [b]not bold[/b]"
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = await shown(pilot, app, view, subagents)
        widget.cursor, widget.following = "c19", False
        widget.show(view, subagents, key="board-a")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        said = [str(label.render()) for label in app.screen.query(Label)]
    assert 'Its input: sed -e "s/[/]/_/g" notes.md' in said, "a closing tag in a command neither crashes nor goes"
    assert "Its error: def f(x: list[str]) -> dict[str, int]: [b]not bold[/b]" in said, "type hints kept whole"


async def test_a_flow_that_changed_is_laid_out_once_with_the_cursor_on_now(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[str] = []
    trees: list[str] = []

    def counted(*args: Any, **kwargs: Any) -> Any:
        rendered.append("render")
        return render(*args, **kwargs)

    def grown(*args: Any, **kwargs: Any) -> Any:
        trees.append("tree")
        return tree(*args, **kwargs)

    monkeypatch.setattr("clank.components.agents.console.flowpanel.render", counted)
    monkeypatch.setattr("clank.components.agents.console.flowchart.tree", grown)
    app = Chart()
    async with app.run_test(size=(100, 40)) as pilot:
        widget = chart(app)
        widget.focus()
        await pilot.pause()
        rendered.clear()
        trees.clear()
        widget.show(*board_a(), key="board-a")
        assert widget.cursor == "msg_21" == widget.drawn.now, "following now"
        assert (rendered, trees) == (["render"], ["tree"]), "the first flow: laid out once, though the cursor moved"
        assert any("selection" in str(span.style) for span in widget.drawn.lines[widget.drawn.row["msg_21"]].spans)
        view, subagents = board_a()
        later = next(node for node in view["nodes"] if node["id"] == "msg_21")
        later["ended"], later["text"] = "failed", ""
        rendered.clear()
        trees.clear()
        widget.show(view, subagents, key="board-a")
        assert widget.cursor == widget.drawn.now
        assert (rendered, trees) == (["render"], ["tree"]), "a flow that changed: laid out once"
