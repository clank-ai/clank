"""Design 0011 §4, §7, §11 and §12.1 (R2; every key a button): the windows over the console, the details window (`?`,
`v`), the picker, the form, an MCP server's tools and a device's traffic, are each one panel (the traffic window two:
its list and the highlighted exchange), their title in the top border, no longer a bold first line; a window's border is
`border-focused`, since it has the focus (in the traffic window, the border of the panel that holds it), on the page's
`background`; its keys ("Esc closes this") stay its last line, in `quiet`, the details window's a button, `esc close`,
which has the focus when it opens. A window is never wider than the screen allows: a title too long for it is cut in
the border with "…" and shown whole as the window's first line (design 0011 §4 and §5, revised after approval with
decision 0081: nothing cut is lost)."""

from collections.abc import Callable
from typing import Any

import pytest
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Label, ListView

from clank.client import Client
from clank.components.remote.console.traffic import TrafficScreen
from clank.components.tools.console.servers import ToolsScreen
from clank.console.app import ClankConsole
from clank.console.buttons import Buttons
from clank.console.details import DetailsScreen
from clank.console.form import Field, FormScreen
from clank.console.panel import Panel
from clank.console.pick import Choice, PickScreen
from clank.console.snapshot import render_text
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle, steady_frame

pytestmark = pytest.mark.anyio
STYLE = StyleSettings()
WINDOWS: dict[str, tuple[str, Callable[[], ModalScreen[Any]]]] = {
    "details": ("Stop Docker Desktop?", lambda: DetailsScreen("Stop Docker Desktop?", ["Two containers run."])),
    "picker": ("Run in the main slot", lambda: PickScreen("Run in the main slot", [Choice("a", "daily 262K")])),
    "form": ("Add an MCP server", lambda: FormScreen("Add an MCP server", [Field("name", "Name", "myproject")])),
    "tools": ("fake: 2 tools", lambda: ToolsScreen("fake: 2 tools", [Content("fake-mcp 1.2.3")], [Content("add")])),
}


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, home=home)
    app.folder = FOLDER
    return app


async def opened(pilot: Any, app: ClankConsole, window: ModalScreen[Any]) -> list[str]:
    """The window pushed over the console, and the frame once it has stopped changing."""
    await settle(pilot, lambda: "f1 help" in render_text(app))
    app.push_screen(window)
    await settle(pilot, lambda: app.screen is window and bool(window.query(Panel)))
    return (await steady_frame(pilot, app)).splitlines()


def hex_of(color: Any) -> str:
    return str(color.hex).lower()


def inside(app: ClankConsole, panel: Panel) -> str:
    """What the frame shows inside a panel, its rows joined, so that words a row wraps read whole."""
    area = panel.content_region
    return "".join(row[area.x : area.right].rstrip() for row in render_text(app).splitlines()[area.y : area.bottom])


def top_border(rows: list[str], panel: Panel) -> str:
    return rows[panel.region.y][panel.region.x : panel.region.right]


@pytest.mark.parametrize("name", list(WINDOWS))
async def test_a_window_is_one_panel_its_title_in_its_border_its_border_focused_its_keys_its_last_line(
    client: Client, home: Home, name: str
) -> None:
    title, build = WINDOWS[name]
    app = make(client, home)
    async with app.run_test(size=(140, 40)) as pilot:
        window = build()
        rows = await opened(pilot, app, window)
        panels = list(window.query(Panel))
        assert len(panels) == 1, f"{name}: one panel"
        [panel] = panels
        assert panel.title == title
        assert top_border(rows, panel).startswith(f"┌─ {title} ─"), f"{name}: its title in its top border"
        shown = [str(label.content) for label in window.query(Label) if label.display]
        assert title not in shown, f"{name}: no longer a bold first line"
        assert hex_of(panel.styles.border_top[1]) == STYLE.colors.border_focused
        assert hex_of(panel.styles.background) == STYLE.colors.background
        last = list(panel.children)[-1]
        if name == "details":  # its key a button (design 0011 §12.1)
            assert isinstance(last, Buttons), f"{name}: its keys, its last line"
            assert [(each.label, each.said) for each in last.buttons] == [("esc", "close")]
            assert app.focused is last, "the window opens with the focus on its button"
            return
        assert isinstance(last, Label)
        assert str(last.content).endswith("Esc closes this."), f"{name}: its keys, its last line"
        assert hex_of(last.styles.color) == STYLE.colors.quiet


async def test_the_traffic_window_is_two_panels_its_list_and_the_highlighted_exchange(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(140, 40)) as pilot:
        window = TrafficScreen(app, {"id": "d-0", "name": "my phone"})
        await settle(pilot, lambda: "f1 help" in render_text(app))
        app.push_screen(window)
        await settle(pilot, lambda: "Nothing exchanged yet." in render_text(app))
        rows = (await steady_frame(pilot, app)).splitlines()
        exchanges, exchange = list(window.query(Panel))
        assert exchanges.title == "my phone · everything it and this computer exchanged"
        assert exchange.title == "The highlighted exchange"
        assert exchange.region.y == exchanges.region.bottom + STYLE.spacing.rows_between, "a row between, as on a page"
        for panel in (exchanges, exchange):
            assert top_border(rows, panel).startswith(f"┌─ {panel.title} ─")
        assert window.query_one(ListView).has_focus
        assert hex_of(exchanges.styles.border_top[1]) == STYLE.colors.border_focused, "the panel with the focus"
        assert hex_of(exchange.styles.border_top[1]) == STYLE.colors.border
        last = list(exchange.children)[-1]
        assert isinstance(last, Label)
        assert str(last.content) == "Up and Down choose an exchange · Esc closes this."
        assert exchanges.note == "", "no count while nothing was exchanged: the list says so"


async def test_a_window_title_too_long_for_the_screen_is_cut_in_its_border_and_shown_whole_inside(
    client: Client, home: Home
) -> None:
    title = "daily 262K: " + "/".join(["a-folder-of-the-owners"] * 6) + "/presets/[draft] daily-262k.json"
    app = make(client, home)
    async with app.run_test(size=(100, 40)) as pilot:
        window = DetailsScreen(title, ["engine: KVMem"])
        rows = await opened(pilot, app, window)
        panel = window.query_one(Panel)
        assert panel.outer_size.width <= 90, "never wider than the screen allows (90%)"
        border = top_border(rows, panel)
        assert border.startswith("┌─ daily 262K: a-folder")
        assert "…" in border, "cut with …"
        first = next(label for label in window.query(Label) if label.display)
        assert str(first.content) == title, "shown whole, first"
        assert "[draft] daily-262k.json" in inside(app, panel), "as written, not read as markup"
    app = make(client, home)
    async with app.run_test(size=(140, 40)) as pilot:
        window = DetailsScreen("Stop Docker Desktop?", ["Two containers run."])
        await opened(pilot, app, window)
        first = next(label for label in window.query(Label) if label.display)
        assert str(first.content) == "Two containers run.", "a title that fits is not shown twice"
