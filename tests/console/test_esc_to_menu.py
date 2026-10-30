"""Design 0011 §12.5 (revised 2026-10-22, decision 0129): Esc goes back to the menu, from anywhere in a page (the owner:
"Unless otherwise stated (like when I am confirming something), the esc key should always bring me back to the Clank
menu"). A window open closes first, as Esc always did; a row of buttons, a page's list or the page itself all go back
to the menu, the page staying as it was. Beside a page that hides the menu (the Monitor), Esc shows it while it has the
focus, the arrows pass the Monitor without hiding it, and going back into the page hides it again. Where a page has a
step back inside it (the Monitor's view before, the Flow view's board D1, Add a model's step before), Esc takes that
step first (revised 2026-10-29, decision 0151; tests/console/test_backspace_erases.py), and Backspace only erases."""

from typing import Any

import pytest
from textual.widgets import ListView

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.keys import ANYWHERE, shown
from clank.console.keysbar import KeysBar
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle

pytestmark = pytest.mark.anyio


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def focused(app: ClankConsole) -> str | None:
    return app.focused.id if app.focused is not None else None


def current(app: ClankConsole) -> str:
    return str(app.query_one("#pages").current)  # type: ignore[attr-defined]


async def press(pilot: Any, app: ClankConsole, key: str, wanted: str) -> None:
    """Press a key, and wait until the focus is where it should be."""
    await pilot.press(key)
    await settle(pilot, lambda: focused(app) == wanted)


def test_esc_is_a_key_that_acts_anywhere_and_says_menu() -> None:
    [esc] = [key for key in ANYWHERE if key.key == "escape"]
    assert (shown(esc.key), esc.words) == ("esc", "menu")
    assert shown("backspace") == "bksp"


async def test_esc_from_a_pages_list_goes_back_to_the_menu_the_page_staying(client: Client, home: Home) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "records-kinds")
        await press(pilot, app, "right", "records-list")
        await press(pilot, app, "escape", "menu")
        assert current(app) == "page-records"
        await press(pilot, app, "right", "records-list")  # back where it was


async def test_esc_from_a_row_of_buttons_goes_back_to_the_menu(client: Client, home: Home) -> None:
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        app.query_one("#keys", KeysBar).focus()
        await settle(pilot, lambda: focused(app) == "keys")
        await press(pilot, app, "escape", "menu")


async def test_esc_closes_a_window_first_then_goes_to_the_menu(client: Client, home: Home) -> None:
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: focused(app) == "menu")
        await press(pilot, app, "right", "operations-list")
        await pilot.press("question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        assert focused(app) == "operations-list", "the window closed; the page keeps the focus"
        await press(pilot, app, "escape", "menu")


async def test_beside_the_monitor_esc_shows_the_menu_and_going_back_in_hides_it(client: Client, home: Home) -> None:
    app = make(client, home, "monitor")
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: app.focused is not None and focused(app) != "menu")
        menu = app.query_one("#menu", ListView)
        assert app.menu_hidden(), (focused(app), app.screen.classes)
        assert not menu.display
        await press(pilot, app, "escape", "menu")
        await settle(pilot, lambda: menu.display and menu.region.width > 0)
        assert not app.menu_hidden()
        await pilot.press("right")
        await settle(pilot, lambda: focused(app) != "menu" and not menu.display)


async def test_the_menus_arrows_pass_the_monitor_without_hiding_the_menu(client: Client, home: Home) -> None:
    app = make(client, home, "monitor")
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: app.focused is not None and focused(app) != "menu")
        await press(pilot, app, "escape", "menu")
        await pilot.press("down")
        await settle(pilot, lambda: current(app) != "page-monitor")
        await pilot.press("up")
        await settle(pilot, lambda: current(app) == "page-monitor")
        await pilot.pause(0.2)
        assert focused(app) == "menu", "the menu keeps the focus on the Monitor's entry"
        assert app.query_one("#menu", ListView).display
