"""Design 0012 §9.1 (§11 step 12's review): a window that asks before an action (`ConfirmScreen`: "a confirmation,
Enter, or Esc to leave it") takes only an Enter pressed while it is on screen. The Enter that opened it, a page's key
that pushed it, is never taken as "do it", wherever the window is opened from; the next Enter does it, Esc leaves it.
Design 0011 §12.1 and §12.5: its keys are its last line, a group of buttons, the focus on "do it" when it opens; the
right arrow reaches "leave it", which Enter then presses; Space presses too, and a click on either does what its key
does, the same guard kept."""

from typing import Any

import pytest
from textual import events
from textual.app import App

from clank.components.agents.console.itemsscreen import ItemsScreen
from clank.console.buttons import Buttons
from clank.console.confirm import ConfirmScreen
from clank.console.style import CLANK, LoadedStyle, theme_of
from clank.kernel.console_kinds import StyleSettings
from tests.console.frames import settle

pytestmark = pytest.mark.anyio


class Styled(App[None]):
    """An app in the console's own style, whose elements the windows name, keeping what its windows answered."""

    def __init__(self) -> None:
        super().__init__()
        self.answers: list[Any] = []
        loaded = LoadedStyle(CLANK, StyleSettings())
        self.register_theme(theme_of(loaded))
        self.theme = loaded.name


class Opener(Styled):
    """A page whose Enter opens a window that asks first, as the Monitor's Could be freed and its Guide do."""

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter" and not isinstance(self.screen, ConfirmScreen):
            self.push_screen(ConfirmScreen("Compact now", ["It compacts the session."]), self.answers.append)


async def test_the_enter_that_opens_a_window_that_asks_first_never_does_it() -> None:
    app = Opener()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen), "still asking"
        assert app.answers == [], "the Enter that opened it did nothing in it"
        await pilot.press("enter")
        await settle(pilot, lambda: app.answers == [True])
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("escape")
        await settle(pilot, lambda: app.answers == [True, False])


async def test_an_enter_right_after_the_key_that_opened_the_window_does_it() -> None:
    app = Opener()
    async with app.run_test() as pilot:
        await pilot.press("enter", "enter")
        await settle(pilot, lambda: app.answers == [True])


async def test_a_window_is_armed_only_once_the_message_it_was_made_in_is_done() -> None:
    app = Opener()
    async with app.run_test():
        window: Any = ConfirmScreen("Drop", ["It clears a result."])
        assert window.armed is False, "the key that opened it does nothing in it"


class Lister(Styled):
    """A page whose `x` opens the window of items, where `x` drops one, as the Monitor's Context view does."""

    def on_key(self, event: events.Key) -> None:
        if event.key == "x" and not isinstance(self.screen, ItemsScreen):
            rows = [{"part": "results", "of": "results", "call": "call_c03", "node": "c03"}]
            self.push_screen(ItemsScreen("tool results", rows, ["  5,636  step 3   read src/simulator.py"], []),
                             self.answers.append)  # fmt: skip


async def test_the_x_that_opens_the_window_of_items_never_drops_one_in_it() -> None:
    app = Lister()
    async with app.run_test() as pilot:
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
        await pilot.pause(0.3)
        assert isinstance(app.screen, ItemsScreen), "still open"
        assert app.answers == [], "the x that opened it dropped nothing"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert app.answers == [], "Enter does nothing in it"
        await pilot.press("x")
        await settle(pilot, lambda: len(app.answers) == 1)
        assert app.answers[0]["node"] == "c03"


async def test_it_opens_with_the_focus_on_do_it_and_the_right_arrow_reaches_leave_it() -> None:
    app = Opener()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        keys = app.screen.query_one("#confirm-keys", Buttons)
        await settle(pilot, lambda: app.focused is keys)
        assert [each.said for each in keys.buttons] == ["do it", "leave it"]
        assert keys.cursor == 0
        await pilot.press("right", "enter")
        await settle(pilot, lambda: app.answers == [False])
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.1)
        await pilot.press("space")
        await settle(pilot, lambda: app.answers == [False, True])


async def test_a_click_on_a_windows_button_does_what_its_key_does() -> None:
    app = Opener()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.1)
        await pilot.click("#confirm-keys", offset=(len(" enter do it  e"), 0))
        await settle(pilot, lambda: app.answers == [False])
