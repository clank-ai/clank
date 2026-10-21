"""Design 0011 §4 (the panel): every section is a panel, a box with its title set in its top border at the left, bold,
and its note at the right of that border, drawn again when a page changes it, and dropped whole, never cut, before the
title goes when the panel is narrow; a panel is never narrower than its title; the panel that holds the focus, and only
it, draws its border in `border-focused`, and Tab goes from panel to panel in reading order; panels in a row share the
row's height and stack when the row is narrow, or at once when what they hold asks for more room than the row has
(design 0011 §9), standing side by side again when it asks for less; panels in a grid stand in columns of set widths,
one beside the several it spans (design 0012 §2: the Monitor's Flow beside Now, Watch for and the Guide), their borders
lined up with the row below, and stack in the order given when the grid is narrow; a style's `round` border draws round
corners; moving the focus costs the console no redraw of its own (design 0001 §5.7).
"""

import re
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label, ListItem, ListView

from clank.console.panel import Panel, PanelGrid, PanelRow
from clank.console.snapshot import render_text
from clank.console.style import LoadedStyle, theme_of, use
from clank.kernel.console_kinds import StyleSettings
from tests.console.frames import settle, steady_frame

pytestmark = pytest.mark.anyio


def listed(*rows: str) -> ListView:
    return ListView(*(ListItem(Label(row)) for row in rows))


class Panels(App[None]):
    """Panels in a style, as a page lays them out: a row of two, then one below."""

    CSS = "ListView { height: auto; }"
    AUTO_FOCUS = None  # nothing has the focus until a test gives it

    def __init__(self, style: StyleSettings | None = None) -> None:
        super().__init__()
        loaded = LoadedStyle("test", style or StyleSettings())
        use(loaded)
        self.register_theme(theme_of(loaded))
        self.theme = "test"

    def compose(self) -> ComposeResult:
        yield PanelRow(
            Panel(Label("Nothing runs right now."), title="Happening now", id="now", note="2 running"),
            Panel(
                listed("Stop Docker Desktop?", "Load daily 262K?", "Open paper?"), title="Waiting for you", id="waits"
            ),
            stack_below=100,
        )
        yield Panel(listed("13:54 docker started"), title="History", id="history", note="newest first")


def lines(app: App[Any]) -> list[str]:
    return render_text(app).splitlines()


def border_of(panel: Panel) -> str:
    return panel.styles.border_top[1].hex.lower()


async def test_a_panel_has_four_borders_its_title_in_the_top_one_and_its_note_at_its_right() -> None:
    app = Panels()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        frame = lines(app)
    history = next(line for line in frame if "History" in line)
    assert history.startswith("┌─ History ─")
    assert history.rstrip().endswith("─ newest first ─┐")
    below = frame[frame.index(history) + 1 :]
    assert below[0].startswith("│ 13:54 docker started")
    assert below[1].startswith("└──")
    assert below[1].rstrip().endswith("┘")


async def test_a_narrow_panel_drops_its_note_and_keeps_its_title_whole() -> None:
    app = Panels()
    async with app.run_test(size=(28, 30)) as pilot:  # stacked, each panel 28 wide: too narrow for "2 running"
        await settle(pilot, lambda: app.query_one(PanelRow).has_class("-stacked"))
        frame = await steady_frame(pilot, app)
    top = next(line for line in frame.splitlines() if "Happening now" in line)
    assert re.fullmatch(r"┌─ Happening now ─+┐", top.rstrip()), "the note dropped whole, not cut"
    assert "Waiting for you" in frame, "the title is never cut"


async def test_a_note_set_or_changed_after_the_panel_is_drawn_shows_in_its_border() -> None:
    app = Panels()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        history = app.query_one("#history", Panel)
        tops = []
        for note in ("3 events", "4 events", ""):
            history.note = note
            await pilot.pause()
            tops.append(next(line for line in lines(app) if "History" in line).rstrip())
    assert tops[0].endswith("─ 3 events ─┐")
    assert tops[1].endswith("─ 4 events ─┐")
    assert re.fullmatch(r"┌─ History ─+┐", tops[2]), "no note"


async def test_a_panel_is_never_narrower_than_its_title() -> None:
    app = Panels()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        waits = app.query_one("#waits", Panel)
    assert waits.styles.min_width is not None
    assert waits.styles.min_width.value == len("Waiting for you") + 6


async def test_only_the_panel_that_holds_the_focus_draws_its_border_in_border_focused() -> None:
    style = StyleSettings()
    app = Panels(style)
    async with app.run_test(size=(120, 20)) as pilot:
        app.query_one("#waits ListView", ListView).focus()
        await pilot.pause()
        borders = {panel.id: border_of(panel) for panel in app.query(Panel)}
    assert borders == {"now": style.colors.border, "waits": style.colors.border_focused, "history": style.colors.border}


async def test_tab_goes_from_panel_to_panel_in_reading_order() -> None:
    app = Panels()
    async with app.run_test(size=(120, 20)) as pilot:
        visited = []
        for _ in range(2):
            await pilot.press("tab")
            focused = app.focused
            assert focused is not None
            visited.append(next(panel.id for panel in focused.ancestors if isinstance(panel, Panel)))
    assert visited == ["waits", "history"]


async def test_panels_in_a_row_share_its_height_and_stack_when_it_is_narrow() -> None:
    app = Panels()
    async with app.run_test(size=(170, 30)) as pilot:
        await pilot.pause()
        now, waits = app.query_one("#now", Panel), app.query_one("#waits", Panel)
        assert now.outer_size.height == waits.outer_size.height == 5
        assert now.region.y == waits.region.y
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert waits.region.y > now.region.y, "stacked, in reading order"
        assert now.region.x == waits.region.x


async def test_a_row_whose_content_asks_for_more_room_stacks_at_once_and_stands_side_by_side_again_after() -> None:
    app = Panels()
    async with app.run_test(size=(170, 30)) as pilot:
        await pilot.pause()
        row = app.query_one(PanelRow)
        now, waits = app.query_one("#now", Panel), app.query_one("#waits", Panel)
        assert now.region.y == waits.region.y
        row.stack_below = 200  # a question waits in one of its panels: more room than the row has
        await settle(pilot, lambda: waits.region.y > now.region.y)
        assert now.region.x == waits.region.x, "stacked, in reading order"
        row.stack_below = 100
        await settle(pilot, lambda: waits.region.y == now.region.y)
        assert waits.region.x > now.region.right


async def test_a_style_with_round_borders_draws_round_corners() -> None:
    app = Panels(StyleSettings(border="round"))
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        frame = render_text(app)
    assert "╭─ History ─" in frame
    assert {"╮", "╰", "╯"} <= set(frame)
    assert "┌" not in frame


async def test_the_title_takes_the_styles_title_color_and_the_border_its_own() -> None:
    style = StyleSettings()
    app = Panels(style)
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        history = app.query_one("#history", Panel)
        title = history.border_title
    assert border_of(history) == style.colors.border
    assert history.styles.border_title_color.hex.lower() == style.colors.border, "the run of ─ before the note"
    assert title is not None
    markup = title if isinstance(title, str) else title.markup
    assert "bold $clank-title" in markup


class Grids(App[None]):
    """The Monitor's Session view in small: a tall Flow beside Now, Watch for and the Guide, then two panels below in
    the same columns."""

    def __init__(self) -> None:
        super().__init__()
        loaded = LoadedStyle("test", StyleSettings())
        use(loaded)
        self.register_theme(theme_of(loaded))
        self.theme = "test"

    def compose(self) -> ComposeResult:
        yield PanelGrid(
            Panel(Label("idle"), title="Now", id="now"),
            Panel(Label("\n".join(f"step {n}" for n in range(1, 10))), title="Flow", id="flow"),
            Panel(Label("nothing marked"), title="Watch for", id="watch"),
            Panel(Label("nothing to guide"), title="Guide", id="guide"),
            columns="2fr 3fr",
            spans={"flow": 3},
            stack_below=80,
        )
        yield PanelGrid(
            Panel(Label("none yet"), title="Tool calls", id="calls"),
            Panel(Label("none yet"), title="Biggest", id="biggest"),
            columns="2fr 3fr",
            stack_below=80,
        )


async def test_a_tall_panel_of_a_grid_stands_beside_the_panels_it_spans_its_borders_lined_up_with_the_row_below() -> (
    None
):
    app = Grids()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        now, flow, watch, guide, calls, biggest = (
            app.query_one(f"#{id}", Panel) for id in ("now", "flow", "watch", "guide", "calls", "biggest")
        )
        assert now.region.x == watch.region.x == guide.region.x == calls.region.x
        assert flow.region.x == biggest.region.x > now.region.right, "the Flow beside them, Biggest under it"
        assert now.region.right == calls.region.right, "lined up"
        assert flow.region.right == biggest.region.right, "lined up"
        assert now.region.y < watch.region.y < guide.region.y, "Now, Watch for and the Guide one under the other"
        assert flow.region.y == now.region.y, "the Flow spans all three"
        assert flow.region.bottom == guide.region.bottom, "the Flow spans all three"
        assert flow.outer_size.width > now.outer_size.width, "2fr beside 3fr"


async def test_a_narrow_grid_stacks_its_panels_in_the_order_given() -> None:
    app = Grids()
    async with app.run_test(size=(70, 60)) as pilot:
        await settle(pilot, lambda: all(grid.has_class("-stacked") for grid in app.query(PanelGrid)))
        await steady_frame(pilot, app)
        panels = [app.query_one(f"#{id}", Panel) for id in ("now", "flow", "watch", "guide", "calls", "biggest")]
        tops = [panel.region.y for panel in panels]
        assert tops == sorted(set(tops)), "one under the other, in the order given"
        assert {panel.region.x for panel in panels} == {0}
        assert panels[1].outer_size.height == 11, "the Flow as tall as its own nine steps, no longer spanning"
