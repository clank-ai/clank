"""Design 0011 §7, §12.1, §12.3 and §12.4 (the keys bar; what becomes a button; pressing it; how the focus moves): every
key on the keys bar is a button, standing at the column its key stood at before buttons, as §7 fits them; Tab reaches
the bar, last in the screen's order, and goes on to the menu; → and ← move along it and stop at its ends; Enter, Space
and a click press a key through the console's one door; ↑ and Esc go back into the page; the focused key is drawn on
`button-focused`, its blank cells too."""

from typing import Any

import pytest
from rich.cells import cell_len

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.keys import PALETTE, PageKey, fit_keys, said
from clank.console.keysbar import KeysBar
from clank.console.pages import Page
from clank.console.snapshot import render_text
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle

pytestmark = pytest.mark.anyio
STYLE = StyleSettings()
DOCKER = (PageKey("s", "docker", "start or stop Docker"), PageKey("r", "read", "read it again"))


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def before_buttons(keys: tuple[PageKey, ...], width: int) -> str:
    """The keys bar's row as it was drawn before its keys were buttons: a space, the keys two spaces apart, and the
    palette's at the right, a space after it."""
    fitted, palette = fit_keys(keys, width)
    row = " " + "  ".join(said(key) for key in fitted)
    if palette:
        row += " " * max(width - len(row) - cell_len(said(PALETTE)) - 1, 2) + said(PALETTE) + " "
    return row


def bar_row(app: ClankConsole) -> str:
    return render_text(app).splitlines()[-1]


def recorded(page: Page) -> list[str]:
    pressed: list[str] = []

    def press(key: str) -> bool:
        pressed.append(key)
        return True

    page.press = press  # type: ignore[method-assign]
    return pressed


def rgb(color: Any) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


@pytest.mark.parametrize("width", [60, 80, 88, 100, 120, 128, 170])
async def test_each_key_stands_at_the_column_it_stood_at_before_buttons(client: Client, home: Home, width: int) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(width, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        assert bar_row(app).rstrip() == before_buttons(DOCKER, width).rstrip()


async def test_tab_reaches_the_keys_bar_last_and_goes_on_to_the_menu(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        bar = app.query_one(KeysBar)
        for _ in range(12):
            if app.focused is bar:
                break
            await pilot.press("tab")
        assert app.focused is bar
        await pilot.press("tab")
        assert app.focused is not None
        assert app.focused.id == "menu"
        await pilot.press("shift+tab")
        assert app.focused is bar


async def test_the_arrows_move_along_the_keys_bar_and_stop_at_its_ends(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        bar = app.query_one(KeysBar)
        bar.focus()
        await pilot.press("left")
        assert bar.cursor == 0
        for _ in range(20):
            await pilot.press("right")
        assert bar.current is not None
        assert bar.current.key == PALETTE
        assert app.focused is bar


async def test_enter_space_and_a_click_press_a_key_of_the_bar_through_the_one_door(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        pressed = recorded(app.query_one("#page-docker", Page))
        bar = app.query_one(KeysBar)
        bar.focus()
        await pilot.press("right", "enter", "space")
        await pilot.click(KeysBar, offset=(2, 0))
        await pilot.pause()
        assert pressed == ["r", "r", "s"]
        assert bar.cursor == 0, "a click moves the cursor to the key clicked"


async def test_up_and_esc_on_the_keys_bar_go_back_into_the_page(client: Client, home: Home) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Kinds")
        bar = app.query_one(KeysBar)
        for key in ("up", "escape"):
            bar.focus()
            await pilot.pause()
            await pilot.press(key)
            await settle(pilot, lambda: app.focused is not bar)
            assert app.focused is not None
            assert app.focused.id == "records-kinds", key


async def test_the_focused_key_is_drawn_on_button_focused_its_blank_cells_too(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        bar = app.query_one(KeysBar)
        row = app.size.height - 1
        assert rgb(app.screen.get_style_at(1, row).bgcolor) == STYLE.colors.bars
        bar.focus()
        await pilot.pause()
        for column in (0, 1, len(" s start or stop Docker")):
            assert rgb(app.screen.get_style_at(column, row).bgcolor) == STYLE.colors.button_focused, column
        assert rgb(app.screen.get_style_at(len(" s start or stop Docker  r"), row).bgcolor) == STYLE.colors.bars
