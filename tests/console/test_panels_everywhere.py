"""Design 0011 §2, §4, §7, §8, §9 and §11 (R2): every section of every page is a panel, and nothing of a page sits
outside one (the hint lines that ended some pages are the keys bar's now, design 0011 §7); every page of the console,
the shell's, each component's and the planned ones, draws the panels it declares (`PANELS`), in that order, each a box
with four borders and its title whole in its own top border, at 80, 120 and 170 columns, Requests' live view too
(shown by `v`), each view of a page with views (the Monitor, design 0012 §2), which keeps its row of tabs and one
heading line outside its panels (decision 0043), and each screen of a page shown one screen at a time (Add a model,
design 0016 §14); with the machine column in a narrow window (F5 at 80 and 100
columns), a page narrower than one of its panels scrolls sideways to all of it rather than cut its title, in each of
its views; a list in a panel is drawn on the panel's background,
not on `surface` (a button's or a choice's), whether it has the focus or not; the phrases the console's tests look for
are still found at 80 columns."""

import re
from functools import partial
from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Label, ListView

from clank.client import Client
from clank.console.app import PAGES, ClankConsole
from clank.console.menu import PLANNED
from clank.console.pages import Page
from clank.console.panel import Panel, PanelRow
from clank.console.snapshot import render_text
from clank.console.style import CLANK, LoadedStyle, theme_of, use
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.home import Home
from tests.console.frames import FOLDER, focus_on, frame_when, settle

pytestmark = pytest.mark.anyio

EVERY_PAGE = [page.ENTRY.id for page in PAGES] + [entry.id for entry in PLANNED]  # as the menu lists them
SHOWN_BY = {"requests-live": "v", "monitor-session-live": "l"}  # a panel a page shows only after one of its keys


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, home=home)
    app.folder = FOLDER
    return app


async def shown(pilot: Pilot[Any], app: ClankConsole, page_id: str) -> Page:
    """The page, brought on screen."""
    app.show_page(page_id)
    await pilot.pause()
    return app.query_one(f"#page-{page_id}", Page)


async def toggle(pilot: Pilot[Any], page: Page, panel: Panel) -> None:
    """Press the page's key that shows the panel (or hides it again), and wait until it did."""
    showing = not panel.display
    assert page.press(SHOWN_BY[panel.id or ""])
    await settle(pilot, lambda: panel.display == showing)


def views_of(page: Page) -> tuple[str, ...]:
    """A page's views, when it has them (the Monitor's), else one view, "" (the page)."""
    return tuple(getattr(page, "VIEWS", ())) or ("",)


async def view_shown(pilot: Pilot[Any], page: Page, view: str) -> list[Panel]:
    """One of a page's views on screen (nothing to do for a page without views), and its panels: a view's are marked
    with its class (`view-session`)."""
    if not view:
        return list(page.query(Panel))
    page.show_view(view)  # type: ignore[attr-defined]
    await pilot.pause()
    return list(page.query(f"Panel.view-{view}").results(Panel))


def shows(panel: Panel, shown: bool) -> bool:
    """Whether a panel is shown, or hidden, as wanted."""
    return bool(panel.display) == shown


def board_of(page: Page, panel: Panel) -> str:
    """The board of its view a panel is shown on, when the page has boards (the Monitor's Flow view: D4); "" else."""
    return next((name for name in getattr(page, "BOARDS", ()) if panel.has_class(f"board-{name}")), "")


def outside_panels(page: Page) -> list[str]:
    """What the page holds outside any panel: but a page with views keeps its row of tabs and one heading line, first
    (decision 0043)."""
    children = list(page.children)
    if views_of(page) != ("",):
        assert all(isinstance(child, Label) for child in children[:2]), f"{page.id}: its tabs and heading line first"
        children = children[2:]
    return [str(child) for child in children if not isinstance(child, Panel | PanelRow)]


async def borders(pilot: Pilot[Any], app: ClankConsole, page: Page, panel: Panel) -> tuple[str, str]:
    """A panel's top and bottom borders as the frame draws them: the page scrolled to the panel's top, then, when the
    panel is taller than the page shows, down to its bottom."""
    page.scroll_to_widget(panel, animate=False, top=True)
    await pilot.pause()
    top = render_text(app).splitlines()[panel.region.y][panel.region.x : panel.region.right]
    below = panel.region.bottom - page.scrollable_content_region.bottom
    if below > 0:
        page.scroll_to(y=page.scroll_y + below, animate=False)
        await pilot.pause()
    bottom = render_text(app).splitlines()[panel.region.bottom - 1][panel.region.x : panel.region.right]
    return top.rstrip(), bottom.rstrip()


def unreachable(page: Page) -> list[str]:
    """The panels of a page that stand beyond its right edge further than its sideways scroll goes: every panel wider
    than the page when the page cannot scroll sideways."""
    view = page.scrollable_content_region
    room = view.width + (page.max_scroll_x if page.allow_horizontal_scroll else 0)
    rights = {panel: panel.region.right - view.x + int(page.scroll_x) for panel in page.query(Panel)}
    return [f"{panel.id} ({right} columns, {room} reached)" for panel, right in rights.items() if right > room]


@pytest.mark.parametrize("width", [80, 120, 170])
async def test_each_page_draws_its_declared_panels_in_order_each_a_box_with_its_title_whole_and_nothing_outside_them(
    client: Client, home: Home, width: int
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 80)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        assert len(EVERY_PAGE) == len(app.query_one("#pages").children), "the menu lists every page"
        for page_id in EVERY_PAGE:
            page = await shown(pilot, app, page_id)
            panels = list(page.query(Panel))
            assert panels, f"{page_id} has no panel"
            assert tuple(panel.id for panel in panels) == page.PANELS, page_id
            assert not outside_panels(page), f"{page_id}: {outside_panels(page)} outside any panel"
            seen = []
            for view in views_of(page):
                for panel in await view_shown(pilot, page, view):
                    seen.append(panel)
                    hidden = not panel.display
                    board = board_of(page, panel)
                    screen = getattr(page, "SCREEN_OF", {}).get(panel.id)
                    if hidden and board:  # a board of a view (the Flow view's D4), shown in place of its first
                        page.show_board(board)  # type: ignore[attr-defined]
                        await settle(pilot, partial(shows, panel, True))
                    elif hidden and screen:  # a screen of a page shown one at a time (Add a model's)
                        page.show_screen(screen)  # type: ignore[attr-defined]
                        await settle(pilot, partial(shows, panel, True))
                    elif hidden:
                        assert panel.id in SHOWN_BY, f"{page_id}: {panel.id} is hidden, and no key of the page shows it"
                        await toggle(pilot, page, panel)
                    top, bottom = await borders(pilot, app, page, panel)
                    assert re.fullmatch(rf"┌─ {re.escape(panel.title)} .*┐", top), f"{page_id}: {panel.id} {top!r}"
                    assert re.fullmatch(r"└─+┘", bottom), f"{page_id}: {panel.id} {bottom!r}"
                    if hidden and board:
                        page.show_board("d1")  # type: ignore[attr-defined]
                        await settle(pilot, partial(shows, panel, False))
                    elif hidden and screen:
                        page.show_screen(page.SCREENS[0])  # type: ignore[attr-defined]
                        await settle(pilot, partial(shows, panel, False))
                    elif hidden:
                        await toggle(pilot, page, panel)
            assert seen == panels, f"{page_id}: every panel, in one view or another"


@pytest.mark.parametrize("width", [80, 100])
async def test_with_the_machine_column_in_a_narrow_window_each_page_scrolls_sideways_to_the_whole_of_its_panels(
    client: Client, home: Home, width: int
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 60)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        await pilot.press("f5")
        await settle(pilot, lambda: app.query_one("#machine").display)
        wider = []
        for page_id in EVERY_PAGE:
            page = await shown(pilot, app, page_id)
            for view in views_of(page):
                await view_shown(pilot, page, view)
                keyed = [panel for panel in page.query(Panel)
                         if panel.id in SHOWN_BY and (not view or panel.has_class(f"view-{view}"))]  # fmt: skip
                for panel in [None, *keyed]:  # a panel shown by a key, in its own view
                    if panel is not None:
                        await toggle(pilot, page, panel)
                    assert not unreachable(page), f"{page_id}: {unreachable(page)}, which no sideways scroll reaches"
                    visible = page.scrollable_content_region.width
                    wider += [each.id for each in page.query(Panel) if each.region and each.outer_size.width > visible]
                    if panel is not None:
                        await toggle(pilot, page, panel)
    assert "requests-list-panel" in wider, "a panel wider than its page, so the sideways scroll is what is tested"


class NarrowPage(App[None]):
    """A page 20 columns wide, as F5 leaves one at 80 columns: a panel just as wide, then prose that wraps again once
    the vertical scroll bar takes two of the columns, so Textual decides its scroll bars twice."""

    CSS = "Label { width: 1fr; }"

    def __init__(self) -> None:
        super().__init__()
        loaded = LoadedStyle(CLANK, StyleSettings())
        use(loaded)
        self.register_theme(theme_of(loaded))
        self.theme = CLANK

    def compose(self) -> ComposeResult:
        with Page():
            yield Panel(Label("2 setups"), title="Serving setups", id="setups")  # 20 columns: its title's
            for _ in range(8):
                yield Label("a sentence long enough to wrap at either width, the page's or its view's")


async def test_a_panel_wider_than_its_page_by_no_more_than_the_vertical_scroll_bar_is_reached_sideways_too() -> None:
    app = NarrowPage()
    async with app.run_test(size=(20, 12)) as pilot:
        await pilot.pause()
        page = app.query_one(Page)
        assert page.show_vertical_scrollbar, "a page taller than the window"
        assert page.query_one("#setups", Panel).outer_size.width == 20 > page.scrollable_content_region.width
        assert not unreachable(page)
        assert page.show_horizontal_scrollbar


async def test_a_list_in_a_panel_is_drawn_on_the_panels_background_whether_it_has_the_focus_or_not(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 50)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        lists = []
        for page_id in EVERY_PAGE:
            page = await shown(pilot, app, page_id)
            for panel in (panel for panel in page.query(Panel) if panel.display):
                for listed in (listed for listed in panel.query(ListView) if listed.display):
                    behind = panel.background_colors[1]
                    assert listed.background_colors[1] == behind, f"{page_id}: {listed.id}"
                    await focus_on(pilot, app, listed)
                    assert listed.background_colors[1] == behind, f"{page_id}: {listed.id}, with the focus"
                    lists.append(listed.id)
    assert len(lists) >= 5, lists


async def test_the_phrases_the_tests_look_for_are_found_at_80_columns(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(80, 30)) as pilot:
        frame = await frame_when(pilot, app, "Fake Docker", "connected (console)")
    assert "What runs" in frame
