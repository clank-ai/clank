"""Design 0011 §12.2, §12.3 and §12.4 (a group, pressing a button, how the focus moves), in a small app of three
groups: a row, a column under it and a row under that. Along a group the arrows move its cursor and stop at its ends
(← → in a row, ↑ ↓ in a column), Home and End go to its first and last; ↑ ↓ across a row reach the nearest group above
or below, and stay when there is none; Enter and Space press the button under the cursor; a click presses the button
under it and moves the focus there; the mouse over a button gives it the hover's ground without moving the focus; the
focused button is drawn focused only while its group has the focus; a group in a list's row takes no focus but is
clicked; a group's cursor stays where it was when its buttons change."""

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.pilot import Pilot

from clank.console.buttons import Button, Buttons
from clank.console.keys import PageKey
from clank.console.style import CLANK, LoadedStyle, theme_of
from clank.kernel.console_kinds import StyleSettings

pytestmark = pytest.mark.anyio
STYLE = StyleSettings()


def keys(*letters: str) -> list[Button]:
    return [Button(PageKey(letter, f"do_{letter}", f"do {letter}")) for letter in letters]


class Groups(App[None]):
    """Three groups: a row, a column under it, a row under that, and a clicked-only row."""

    def __init__(self) -> None:
        super().__init__()
        self.pressed: list[str] = []

    def on_mount(self) -> None:
        self.register_theme(theme_of(LoadedStyle(CLANK, StyleSettings())))
        self.theme = CLANK

    def compose(self) -> ComposeResult:
        yield Buttons(keys("a", "b", "c"), press=self.record, id="top")
        yield Buttons(keys("d", "e"), column=True, press=self.record, id="column")
        yield Buttons(keys("f", "g"), press=self.record, id="bottom")
        yield Buttons(keys("h"), press=self.record, focusable=False, id="clicked")

    def record(self, pressed: Button) -> None:
        self.pressed.append(pressed.key.key)


def group(app: Groups, name: str) -> Buttons:
    return app.query_one(f"#{name}", Buttons)


def rgb(color: Any) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


def ground(app: Groups, name: str, column: int) -> str:
    """The background of a cell of a group's first row."""
    area = group(app, name).region
    return rgb(app.screen.get_style_at(area.x + column, area.y).bgcolor)


async def focus(pilot: Pilot[None], widget: Buttons) -> None:
    widget.focus()
    await pilot.pause()


async def test_the_arrows_along_a_row_move_its_cursor_and_stop_at_its_ends_home_and_end_too() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top = group(app, "top")
        await focus(pilot, top)
        await pilot.press("right", "right", "right", "right")
        assert top.cursor == 2, "it stops at the row's end"
        assert app.focused is top
        await pilot.press("left", "left", "left")
        assert top.cursor == 0, "and at its start"
        assert app.focused is top
        await pilot.press("end")
        assert top.cursor == 2
        await pilot.press("home")
        assert top.cursor == 0


async def test_the_arrows_along_a_column_move_its_cursor_and_stop_at_its_ends() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        column = group(app, "column")
        await focus(pilot, column)
        await pilot.press("down", "down", "down")
        assert column.cursor == 1
        assert app.focused is column, "it stops at the column's end"
        await pilot.press("up", "up")
        assert column.cursor == 0
        assert app.focused is column


async def test_up_and_down_across_a_row_reach_the_nearest_group_above_or_below_and_stay_when_there_is_none() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top, column, bottom = group(app, "top"), group(app, "column"), group(app, "bottom")
        await focus(pilot, top)
        await pilot.press("up")
        assert app.focused is top, "nothing above it"
        await pilot.press("down")
        assert app.focused is column
        await focus(pilot, bottom)
        await pilot.press("up")
        assert app.focused is column
        await focus(pilot, bottom)
        await pilot.press("down")
        assert app.focused is bottom, "the clicked-only row takes no focus"


async def test_enter_and_space_press_the_button_under_the_cursor() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        await focus(pilot, group(app, "top"))
        await pilot.press("enter", "right", "space")
        assert app.pressed == ["a", "b"]


async def test_a_click_presses_the_button_under_it_and_moves_the_focus_there() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top, bottom = group(app, "top"), group(app, "bottom")
        await focus(pilot, top)
        await pilot.click("#bottom", offset=(len(" f do f  g"), 0))
        await pilot.pause()
        assert app.pressed == ["g"]
        assert app.focused is bottom
        assert bottom.cursor == 1
        await pilot.click("#bottom", offset=(len(" f do f  g do g  "), 0))  # beyond its buttons
        assert app.pressed == ["g"]


async def test_a_group_in_a_lists_row_takes_no_focus_and_a_click_presses_it() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        clicked = group(app, "clicked")
        assert not clicked.focusable
        await focus(pilot, group(app, "top"))
        await pilot.click("#clicked", offset=(2, 0))
        await pilot.pause()
        assert app.pressed == ["h"]
        assert app.focused is group(app, "top")


async def test_the_focused_button_is_drawn_focused_only_while_its_group_has_the_focus() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top = group(app, "top")
        await focus(pilot, top)
        await pilot.press("right")
        await pilot.pause()
        second = len(" a do a ")
        assert ground(app, "top", second) == STYLE.colors.button_focused
        assert ground(app, "top", second + len(" b do b ") - 1) == STYLE.colors.button_focused, "its blank cell too"
        assert ground(app, "top", 0) != STYLE.colors.button_focused
        await focus(pilot, group(app, "bottom"))
        assert ground(app, "top", second) != STYLE.colors.button_focused
        assert top.cursor == 1, "its cursor stays"


async def test_the_mouse_over_a_button_gives_it_the_hovers_ground_and_leaves_the_focus_where_it_is() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top = group(app, "top")
        await focus(pilot, top)
        await pilot.hover("#bottom", offset=(2, 0))
        await pilot.pause()
        assert ground(app, "bottom", 2) == STYLE.colors.button_hover
        assert app.focused is top
        await pilot.hover("#top", offset=(len(" a do a  b do b  c"), 0))
        await pilot.pause()
        assert ground(app, "bottom", 2) != STYLE.colors.button_hover, "the mouse left it"


async def test_a_groups_cursor_stays_where_it_was_when_its_buttons_change() -> None:
    app = Groups()
    async with app.run_test(size=(60, 12)) as pilot:
        top = group(app, "top")
        await focus(pilot, top)
        await pilot.press("right")
        top.show(keys("a", "b", "c", "x"))
        assert top.cursor == 1
        top.show(keys("a"))
        assert top.cursor == 0, "kept within its buttons"
