"""Design 0028 §4 and decision 0148: the console's Setup page shows `clank setup`'s checklist, the service's: each item
with its mark and what it is now, and under an item not done what to do, with the key that does it here (`m` Add a
model, `f` This folder). Under the items, "Next:" and the key of the first required item a key can do; once everything
required is done, "Ready:", what was set up and what each thing is for, and `f`. `r` reads the checklist again. With no
page named, the console opens on Setup while anything required is missing, and as it did before once everything is
done. The page has no key of its own: it is the menu's last page. It fits at 80 columns."""

from datetime import UTC, datetime

import pytest
from textual.widgets import ContentSwitcher, Label

from clank.client import Client
from clank.components.agents import checklist, vscode
from clank.components.agents.console.setup import SetupPage
from clank.components.runtime.state import LastGood
from clank.components.workspaces.sandbox import image_tag
from clank.console.app import ClankConsole
from clank.console.snapshot import render_text
from clank.kernel.access import client_actor
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
YOU = client_actor("console")
RUNTIME = Actor(kind="clank", via="runtime")
TITLE = "Clank's setup"


@pytest.fixture(autouse=True)
def this_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """No VS Code and no installer's tool found, whatever this machine has."""
    monkeypatch.setattr(vscode, "which", lambda name: None)
    monkeypatch.setattr(checklist, "found_tools", lambda: frozenset())


def make(client: Client, home: Home, page: str = "setup", guide: bool = False) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page, guide=guide)
    app.folder = FOLDER
    return app


def said(app: ClankConsole) -> str:
    """What the page's labels say, its lines joined: words a narrow panel wraps are found whole."""
    labels = app.query_one("#page-setup", SetupPage).query(Label).results(Label)
    return " ".join(" ".join(str(label.content).split()) for label in labels if label.display)


def everything_done(kernel: Kernel, platform: FakePlatform) -> None:
    """The sandbox image built, a preset that answered a test request and runs in the main slot, and a workspace."""
    platform.images.add(image_tag())
    state = kernel.parts["runtime"].state
    state.set_slot("main", "ready", "daily 262K answered in 1 s", actor=RUNTIME, preset="daily-262k")
    state.remember_good("main", LastGood(preset="daily-262k", time=NOW))
    kernel.settings.write("workspace", "paper", {"path": FOLDER}, base=None, actor=YOU)


def current_page(app: ClankConsole) -> str:
    return str(app.query_one("#pages", ContentSwitcher).current)


async def test_each_item_shows_what_it_is_now_and_what_to_do_with_the_key_that_does_it(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        frame = await frame_when(pilot, app, TITLE, "Next:", "Clank's VS Code window")
        text = said(app)
        for words in ("Docker installed", "Fake Docker 4.85.0", "no model has answered a test request yet",
                      "press m", "press f", "This computer has NVIDIA GeForce RTX 5080, 16 GB: local models can run",
                      "optional: VS Code is not installed"):  # fmt: skip
            assert words in text, words
        assert "Next:  f open This folder" in frame
        assert_frame(frame, "setup")


async def test_the_setup_page_fits_at_80_columns(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(80, 40)) as pilot:
        frame = await frame_when(pilot, app, TITLE, "Docker installed")
        assert all(len(line) <= 80 for line in frame.splitlines())
        assert_frame(frame, "setup-80")


async def test_with_no_page_named_the_console_opens_on_setup_while_something_required_is_missing(
    client: Client, home: Home
) -> None:
    app = make(client, home, page="folder", guide=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: current_page(app) == "page-setup")
        await settle(pilot, lambda: TITLE in render_text(app))


async def test_once_everything_required_is_done_it_opens_on_this_folder_and_setup_says_ready(
    client: Client, home: Home, kernel: Kernel, platform: FakePlatform
) -> None:
    everything_done(kernel, platform)
    app = make(client, home, page="folder", guide=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: app.data.setup is not None)
        await pilot.pause(0.3)
        assert current_page(app) == "page-folder"
        app.show_page("setup")
        frame = await frame_when(pilot, app, "Ready:", "Your workspaces: paper.")
        assert "open This folder" in frame
        assert_frame(frame, "setup-ready")
        await pilot.press("f")
        await settle(pilot, lambda: current_page(app) == "page-folder")


async def test_m_opens_add_a_model_and_f_opens_this_folder(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, TITLE, "Next:")
        await pilot.press("m")
        await settle(pilot, lambda: current_page(app) == "page-addmodel")
        app.show_page("setup")
        await frame_when(pilot, app, TITLE)
        await pilot.press("f")
        await settle(pilot, lambda: current_page(app) == "page-folder")


async def test_r_reads_the_checklist_again(client: Client, home: Home, platform: FakePlatform) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, TITLE, "not built yet")
        platform.images.add(image_tag())  # built by another program: no event says so
        await pilot.press("r")
        await settle(pilot, lambda: "built for this Clank" in said(app))
        await settle(pilot, lambda: "read the checklist again" in render_text(app))


async def test_the_page_has_no_key_of_its_own_and_is_the_menus_last_page(client: Client, home: Home) -> None:
    app = make(client, home, page="home")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: app.data.setup is not None)
        pages = [item.id for item in app.query("#menu .page")]
        assert pages[-1] == "menu-setup"
        assert SetupPage.ENTRY.key == ""
