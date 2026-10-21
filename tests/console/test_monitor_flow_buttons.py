"""Design 0011 §12.4 and §12.9 (how the focus moves; narrow windows), on the Monitor's Flow view (board K3): its keys
bar holds the view's keys at the columns they stood at before they were buttons, at 160, 128, 88 and 60 columns; Tab
from the flow's boxes reaches the keys bar, and Shift+Tab goes back into the page; the boxes keep their arrows while
they have the focus, and the keys bar its own while it does; Enter on the bar's `enter open` presses the view's Enter
once, opening the running box's session."""

from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from rich.cells import cell_len

from clank.client import Client
from clank.components.agents.console.boxpanel import BoxChart
from clank.components.agents.console.monitor import MonitorPage
from clank.console.app import ClankConsole
from clank.console.keys import PALETTE, PageKey, fit_keys, said
from clank.console.keysbar import KeysBar
from clank.console.snapshot import render_text
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import frame_when, settle
from tests.support.flowshapes import NOW, OWNER, install_d1

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "paper"


async def flow_view(app: ClankConsole, pilot: Any) -> MonitorPage:
    """Board D1's moment on the Monitor's Flow view, the running box chosen."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    await settle(pilot, lambda: app.query_one("#monitor-flow-chart-boxes", BoxChart).selected == "T2")
    return page


def make(kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path) -> ClankConsole:
    install_d1(kernel, clock, folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=OWNER, preset="daily-262k")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = str(folder)
    return app


def before_buttons(keys: tuple[PageKey, ...], width: int) -> str:
    """The keys bar's row as it was drawn before its keys were buttons."""
    fitted, palette = fit_keys(keys, width)
    row = " " + "  ".join(said(key) for key in fitted)
    if palette:
        row += " " * max(width - len(row) - cell_len(said(PALETTE)) - 1, 2) + said(PALETTE) + " "
    return row


@pytest.mark.parametrize("width", [160, 128, 88, 60])
async def test_the_flow_views_keys_bar_holds_its_keys_where_they_stood(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, width: int
) -> None:
    app = make(kernel, client, home, clock, folder)
    async with app.run_test(size=(width, 50)) as pilot:
        page = await flow_view(app, pilot)
        keys = page.shown_keys()
        await settle(pilot, lambda: render_text(app).splitlines()[-1].rstrip() == before_buttons(keys, width).rstrip())


async def test_tab_from_the_boxes_reaches_the_keys_bar_and_shift_tab_goes_back_into_the_page(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    app = make(kernel, client, home, clock, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(app, pilot)
        boxes, bar = app.query_one("#monitor-flow-chart-boxes", BoxChart), app.query_one(KeysBar)
        boxes.focus()
        for _ in range(20):
            if app.focused is bar:
                break
            await pilot.press("tab")
        assert app.focused is bar
        await pilot.press("shift+tab")
        assert app.focused is not None
        assert page in app.focused.ancestors


async def test_the_boxes_keep_their_arrows_and_the_keys_bar_its_own(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    app = make(kernel, client, home, clock, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(app, pilot)
        boxes, bar = app.query_one("#monitor-flow-chart-boxes", BoxChart), app.query_one(KeysBar)
        boxes.focus()
        await pilot.press("up")
        await settle(pilot, lambda: boxes.selected == "T1")
        assert bar.cursor == 0
        bar.focus()
        await pilot.press("right", "right")
        assert bar.cursor == 2
        assert boxes.selected == "T1", "the boxes keep the one chosen"


async def test_enter_on_the_bars_enter_open_presses_the_views_enter_once(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    app = make(kernel, client, home, clock, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(app, pilot)
        pressed: list[str] = []
        original = page.press

        def counted(key: str) -> bool:
            pressed.append(key)
            return original(key)

        page.press = counted  # type: ignore[method-assign]
        bar = app.query_one(KeysBar)
        bar.focus()
        await pilot.pause()
        bar.move(next(index for index, each in enumerate(bar.buttons) if each.key.key == "enter"))
        await pilot.press("enter")
        await settle(pilot, lambda: page.view == "session")
        assert pressed == ["enter"]
