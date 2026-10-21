"""Design 0012 §2 and §11 step 1, decision 0047: the Monitor, a page of the console's menu on F10, listed after F9, with
three views in a row of tabs, Flow, Session and Context (design 0013 §12 lists the Flow view's panels). F10 again, on
the Monitor, moves to the next view, the one shown in the tabs, and a click on a tab shows its view; the page opens on
the view last shown, Session the first time. Each view draws its panels, titled and empty, each saying "no session
yet" (the Flow view's "no flow yet"), under one heading line that claims no more than is known. Enter on the Context
window panel opens the Context view, and Esc goes back to it, though Esc on a window over the view only closes the
window; in the Session view a panel's letter moves the focus into it, and Tab goes from panel to panel. `?` says the
heading line whole, what the page shows and what is built so far. The machine column is hidden on the page, whose
panels take its room, until F5 shows it, and comes back, drawn afresh, on the other pages; and while the Monitor is on
screen and nothing it shows changes, nothing is drawn again, though the machine's meters arrive (design 0001 §5.7,
design 0012 §2: no stutter).
Its frames: the Session view at 128, 88 and 60 columns (the page beside nothing, beside the machine column, and
stacked), the Flow and Context views at 128."""

from datetime import UTC, datetime
from functools import partial
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Label

from clank.client import Client
from clank.components.agents.console.boxpanel import BoxChart
from clank.components.agents.console.contextpanel import ContextWindow
from clank.components.agents.console.contextview import Drawn
from clank.components.agents.console.flowpanel import FlowChart
from clank.components.agents.console.flowpanels import LinesView
from clank.components.agents.console.guidepanel import GuideList
from clank.components.agents.console.monitor import LETTERS, TITLES, VIEWS, Empty, MonitorPage
from clank.components.agents.console.nowpanel import NowSpin
from clank.components.machine.service import METERS
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle, steady_frame

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def monitor(app: ClankConsole) -> MonitorPage:
    return app.query_one("#page-monitor", MonitorPage)


def focused_panel(app: ClankConsole) -> str:
    """The id of the panel that holds the focus, or "" when none does."""
    focused = app.focused
    if focused is None:
        return ""
    return next((node.id or "" for node in focused.ancestors_with_self if isinstance(node, Panel)), "")


def on_screen(app: ClankConsole) -> str:
    """The page on screen, by its id."""
    return str(app.query_one("#pages", ContentSwitcher).current).removeprefix("page-")


def shows(page: MonitorPage, view: str) -> bool:
    """Whether the page shows this view."""
    return page.view == view


def holds_focus(app: ClankConsole, panel: str) -> bool:
    """Whether this panel holds the focus."""
    return focused_panel(app) == panel


async def opened(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    """The console loaded, then F10 pressed: the Monitor on screen."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    await settle(pilot, lambda: on_screen(app) == "monitor")
    return monitor(app)


async def test_the_monitor_is_on_f10_listed_after_f9(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        pages = [str(item.query_one(Label).content) for item in app.query("#menu .page")]
    assert pages[-3:-1] == ["F9 Phone", "F10 Monitor"], "F12 Add a model after it"


async def test_f10_opens_the_monitor_and_f10_again_moves_to_its_next_view_flow_session_context_and_round(
    client: Client, home: Home
) -> None:
    style = StyleSettings()
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        assert VIEWS == ("flow", "session", "context"), "the tabs' order: board D1's"
        assert page.view == "session", "Session the first time: board A, the owner's pick"
        seen = []
        for _ in range(3):
            await pilot.press("f10")
            await pilot.pause()
            seen.append(page.view)
            tabs = app.query_one("#monitor-tabs", Label)
            row = render_text(app).splitlines()[tabs.region.y]
            assert all(title in row for title in ("Flow", "Session", "Context"))
            title = {"flow": " Flow ", "session": " Session ", "context": " Context "}[page.view]
            at = app.screen.get_style_at(row.index(title) + 1, tabs.region.y)
            assert at.bgcolor is not None
            assert "#{:02x}{:02x}{:02x}".format(*at.bgcolor.get_truecolor()) == style.colors.selection, page.view
    assert seen == ["context", "flow", "session"]


async def test_each_view_draws_its_panels_titled_and_empty_saying_no_session_yet_or_no_flow_yet(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 60)) as pilot:
        page = await opened(pilot, app)
        for view in VIEWS:
            page.show_view(view)
            await pilot.pause()
            frame = render_text(app)
            boards = [f"board-{name}" for name in page.BOARDS]  # the Flow view's D4, beside its D1
            shown = [panel for panel in page.panels(view) if not any(panel.has_class(each) for each in boards)]
            panels = [panel for panel in shown if panel.id != "monitor-session-live"]
            assert len(panels) == 7, view
            assert all(panel.region.height for panel in panels), f"{view}: its panels on screen"
            others = [panel for panel in page.query(Panel) if panel not in panels]
            assert len(others) == len(page.PANELS) - 7, view  # the live text and the boards among them, hidden
            assert not app.query_one("#monitor-session-live").display, "the live text, hidden until l"
            assert not any(panel.region.height for panel in others), f"{view}: no other view's panel on screen"
            says = "no flow yet" if view == "flow" else "no session yet"
            for panel in panels:
                assert f"┌─ {panel.title}" in frame, (view, panel.title)
                if panel.id == "monitor-flow-boxes":  # a flow's boxes, drawn by their own widget (plan s28)
                    assert [line.plain for line in panel.query_one(BoxChart).chart.lines] == [says]
                elif view == "flow":  # the Flow view's other panels, each its own lines (plan s28)
                    assert str(panel.query_one(LinesView).content) == says, panel.id
                elif panel.id == "monitor-session-flow":  # the session's flow, drawn by its own widget (plan s16)
                    assert [line.plain for line in panel.query_one(FlowChart).drawn.lines] == [says]
                elif panel.id == "monitor-session-context":  # the session's totals, by their own widget (plan s13)
                    assert str(panel.query_one(ContextWindow).content) == says
                elif panel.id == "monitor-session-guide":  # what the Guide offers, by its own widget (plan s19)
                    assert str(panel.query_one(GuideList).content) == says
                elif panel.query(Drawn):  # the Context view's panels, each drawn by its function (plan s22)
                    assert str(panel.query_one(Drawn).content) == says, panel.id
                elif panel.id == "monitor-session-now":  # what the session does now, by its own widget (plan s17)
                    assert str(panel.query_one("#now-head", Label).content) == says
                    assert not panel.query_one(NowSpin).display, "no spinner's cell before a session is followed"
                else:
                    assert [str(empty.content) for empty in panel.query(Empty)] == [says], (view, panel.id)
            region = app.query_one("#monitor-heading").region
            heading = render_text(app).splitlines()[region.y][region.x : region.right]
            assert heading.startswith("No flow yet" if view == "flow" else "No session yet"), heading


async def test_the_monitor_opens_on_the_view_last_shown(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        await pilot.press("f10")
        await settle(pilot, lambda: page.view == "context")
        await pilot.press("1")
        await settle(pilot, lambda: on_screen(app) == "home")
        await pilot.press("f10")
        await settle(pilot, lambda: on_screen(app) == "monitor")
        await pilot.pause()
        assert page.view == "context", "coming back opens the view last shown, not the next"


async def test_enter_on_the_context_window_panel_opens_the_context_view_and_esc_goes_back_to_it(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        await pilot.press("c")
        await settle(pilot, lambda: focused_panel(app) == "monitor-session-context")
        await pilot.press("enter")
        await settle(pilot, lambda: page.view == "context")
        await settle(pilot, lambda: focused_panel(app) == "monitor-context-totals")
        await pilot.press("escape")
        await settle(pilot, lambda: page.view == "session")
        await settle(pilot, lambda: focused_panel(app) == "monitor-session-context")
        await pilot.press("n", "enter")
        await pilot.pause()
        assert page.view == "session", "Enter opens the Context view from the Context window panel only"


async def test_in_the_session_view_a_panels_letter_and_tab_move_the_focus_from_panel_to_panel(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        await opened(pilot, app)
        for letter, panel in LETTERS.items():
            await pilot.press(letter)
            await settle(pilot, partial(holds_focus, app, panel))
            assert app.query_one(f"#{panel}", Panel).key == letter, "its letter beside its title"
        assert set(LETTERS) == set("cnftbwg")
        await pilot.press("c")
        await settle(pilot, lambda: focused_panel(app) == "monitor-session-context")
        visited = []
        for _ in range(6):
            await pilot.press("tab")
            await pilot.pause()
            visited.append(focused_panel(app))
    assert visited == [
        "monitor-session-now",
        "monitor-session-flow",
        "monitor-session-watch",
        "monitor-session-guide",
        "monitor-session-calls",
        "monitor-session-biggest",
    ]


async def test_question_mark_says_what_the_monitor_shows_and_what_is_built_so_far(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        await pilot.press("c", "question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        said = " ".join(str(label.content) for label in app.screen.query(Label))
    assert "Monitor" in said
    assert "Session view" in said
    assert "F10 again moves to the next view" in said
    assert "Built so far" in said
    assert "Its keys: f10 next view" in said


async def test_question_mark_says_the_heading_line_whole_where_the_page_cuts_it(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(82, 50)) as pilot:
        await opened(pilot, app)
        frame = await frame_when(pilot, app, "No session yet")
        await pilot.press("c", "question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        said = " ".join(str(label.content) for label in app.screen.query(Label))
    whole = "No session yet · this folder has no workspace: This folder (F4) opens one"
    assert whole not in frame, "at 60 columns the page cuts the heading line"
    assert "This folder …" in frame
    assert whole in said


def meters_arrive(kernel: Kernel, times: int) -> None:
    """The machine's meters read and told, as the service does every second."""
    machine = kernel.parts["machine"]
    for _ in range(times):
        reading = machine.keep_reading()
        kernel.events.publish_live("machine.meters", summary="the machine's meters", actor=METERS, data=reading)


async def test_the_machine_column_is_hidden_on_the_monitor_at_160_columns_and_back_on_home_drawn_afresh(
    client: Client, kernel: Kernel, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        column = app.query_one("#machine")
        drawn = app.query_one("#machine-meters", Label)
        await settle(pilot, lambda: column.display and "RTX 5080" in render_text(app))
        seconds = len(app.data.meters)
        assert f"{seconds}s " in str(drawn.render()), "the CPU's graph covers one second a reading"
        await opened(pilot, app)
        await settle(pilot, lambda: not column.display)
        assert "RTX 5080" not in render_text(app)
        width = app.query_one("#page-monitor").outer_size.width
        assert width == 160 - 30 - 2, "the page takes the column's room: 128 columns"
        meters_arrive(kernel, 3)
        await settle(pilot, lambda: len(app.data.meters) == seconds + 3)
        await pilot.press("1")
        await settle(pilot, lambda: column.display and f"{seconds + 3}s " in str(drawn.render()))


async def test_f5_shows_the_machine_column_on_the_monitor(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        await opened(pilot, app)
        column = app.query_one("#machine")
        await settle(pilot, lambda: not column.display)
        await pilot.press("f5")
        await settle(pilot, lambda: column.display and "RTX 5080" in render_text(app))
        await pilot.press("f5")
        await settle(pilot, lambda: not column.display)


async def test_the_monitor_on_screen_redraws_nothing_while_nothing_it_shows_changes(
    client: Client, kernel: Kernel, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        await opened(pilot, app)
        await steady_frame(pilot, app)
        refreshed: list[str] = []
        original = Widget.refresh

        def counted(widget: Widget, *args: Any, **kwargs: Any) -> Widget:
            refreshed.append(f"{type(widget).__name__}#{widget.id}")
            return original(widget, *args, **kwargs)

        monkeypatch.setattr(Widget, "refresh", counted)
        readings = len(app.data.meters)
        for _ in range(8):  # the machine's meters, four times a second for two seconds: nothing the Monitor shows
            meters_arrive(kernel, 1)
            await pilot.pause(0.25)
        await settle(pilot, lambda: len(app.data.meters) >= readings + 8)
        await pilot.pause(0.5)
        monkeypatch.setattr(Widget, "refresh", original)
    assert refreshed == [], "nothing on screen was drawn again"


@pytest.mark.parametrize(
    ("width", "height", "machine", "page_width", "name"),
    [
        (160, 40, False, 128, "monitor-session-160"),
        (160, 40, True, 90, "monitor-session-160-f5"),
        (82, 50, False, 60, "monitor-session-82"),
    ],
)
async def test_the_session_view_at_128_88_and_60_columns(
    client: Client, home: Home, width: int, height: int, machine: bool, page_width: int, name: str
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, height)) as pilot:
        page = await opened(pilot, app)
        if machine:
            await pilot.press("f5")
            await settle(pilot, lambda: "RTX 5080" in render_text(app))
        frame = await frame_when(pilot, app, "No session yet")
        assert page.outer_size.width == page_width, "the page's width, as design 0012 §2 counts it (88 is about 90)"
    assert_frame(frame, name)


@pytest.mark.parametrize("view", ["flow", "context"])
async def test_the_flow_and_context_views_at_128_columns(client: Client, home: Home, view: str) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        page.show_view(view)
        frame = await frame_when(pilot, app, "this folder has no workspace" if view == "flow" else "What is in it")
    assert_frame(frame, f"monitor-{view}-160")


async def test_esc_on_a_window_over_the_context_view_closes_the_window_and_leaves_the_view(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        await pilot.press("f10")
        await settle(pilot, lambda: page.view == "context")
        await pilot.press("question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        await pilot.pause(0.2)
        assert page.view == "context", "Esc goes back from a window to its view (design 0012 §2), no further"


async def test_a_click_on_a_tab_shows_its_view(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        tabs = app.query_one("#monitor-tabs", Label)
        row = render_text(app).splitlines()[tabs.region.y][tabs.region.x : tabs.region.right]
        for view in ("context", "flow", "session"):
            await pilot.click("#monitor-tabs", offset=(row.index(TITLES[view]), 0))
            await settle(pilot, partial(shows, page, view))
        await pilot.click("#monitor-tabs", offset=(len(row.rstrip()) + 5, 0))
        await pilot.pause()
        assert page.view == "session", "a click beside the tabs changes nothing"
