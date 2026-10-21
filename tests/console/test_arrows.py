"""Design 0001 §5.1 and design 0011 §12.5: the console is keyboard-first, so the arrows move the focus between the menu
and the page on screen, without the mouse (the owner's request, 2026-10-15). The console starts on the menu. Right, or
Enter, goes from the menu into the page: where the focus was when the page was left, else to its first list, or to the
page itself when it has none, so that Up and Down scroll it. Right and Left move between a page's lists, and Left from
its first list goes back to the menu, where Up and Down open the other pages again. A window's arrows leave the focus
behind it alone."""

from typing import Any

import pytest
from textual.widgets import ListView

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle

pytestmark = pytest.mark.anyio


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def focused(app: ClankConsole) -> str | None:
    return app.focused.id if app.focused is not None else None


async def press(pilot: Any, app: ClankConsole, key: str, wanted: str) -> None:
    """Press a key, and wait until the focus is where it should be."""
    await pilot.press(key)
    await settle(pilot, lambda: focused(app) == wanted)


async def test_right_goes_from_the_menu_into_the_pages_list_and_left_comes_back(client: Client, home: Home) -> None:
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "operations-list")
        await press(pilot, app, "left", "menu")
        menu = app.query_one("#menu", ListView)
        assert menu.highlighted_child is not None
        assert menu.highlighted_child.id == "menu-operations"
        await press(pilot, app, "down", "menu")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-records")  # type: ignore[attr-defined]


async def test_right_and_left_move_between_a_pages_lists_and_left_from_the_first_goes_to_the_menu(
    client: Client, home: Home
) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        for wanted in ("records-kinds", "records-list", "records-fields"):
            await press(pilot, app, "right", wanted)
        await pilot.press("right")
        await pilot.pause(0.2)
        assert focused(app) == "records-fields"  # the last list keeps the focus
        for wanted in ("records-list", "records-kinds", "menu"):
            await press(pilot, app, "left", wanted)


async def test_on_a_page_without_a_list_right_focuses_the_page_itself_and_left_goes_back(
    client: Client, home: Home
) -> None:
    app = make(client, home, "help")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "page-help")
        await press(pilot, app, "left", "menu")


async def test_enter_on_the_menu_goes_into_the_page_as_right_does(client: Client, home: Home) -> None:
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "enter", "operations-list")
        await press(pilot, app, "left", "menu")
        assert app.query_one("#pages").current == "page-operations"  # type: ignore[attr-defined]


async def test_back_into_a_page_the_focus_goes_where_it_was_left(client: Client, home: Home) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "records-kinds")
        await press(pilot, app, "right", "records-list")
        app.query_one("#menu", ListView).focus()  # as a click on the menu does
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "records-list")


async def test_the_console_starts_on_the_menu_whose_arrows_still_open_the_pages(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await pilot.press("down")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-machine")  # type: ignore[attr-defined]
        assert focused(app) == "menu"


async def test_the_arrows_in_a_window_leave_the_focus_behind_it_alone(client: Client, home: Home) -> None:
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await pilot.press("question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        await pilot.press("right", "left", "right")
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        assert focused(app) == "menu"
