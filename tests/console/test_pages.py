"""Design 0001 §4.8, §5.6, design 0002 §2.1, §2.4 and §3.2: the console's pages beyond home. History shows every event
the console holds, newest last, and filters by what is typed after `/`. Docker's page (the workspaces component's)
shows Docker's state and versions and each container with whose it is; `s` asks Docker to stop. The machine's page
(the machine component's) shows the profile and the doctor's checks with what to do; `d` runs the doctor. The
operations page lists the newest operations; the highlighted one shows its steps and its log, and `c` cancels it.
Components declare their pages, which join the menu with their keys, whatever status tag a page draws beside its name
and whenever it comes. Design 0016 §15: a cloud preset says its provider and its prices on the Presets page and in the
picker, and its model on the Models page (no GPU memory of this computer's); a switch to it from the picker is the
switch route, as for any preset."""

from datetime import UTC, datetime

import pytest
from textual.content import Content
from textual.widgets import Input, Label, ListView

from clank.client import Client
from clank.console.app import MENU_NAME, ClankConsole
from clank.console.pages import Page
from clank.console.pages.operations import OperationsPage
from clank.console.pick import preset_choices
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import FOLDER, assert_frame, focus_on, frame_when, settle
from tests.fakes.platform import FakePlatform
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)


def ask(title: str) -> QuestionDraft:
    return QuestionDraft(
        type="approval",
        title=title,
        options=[Option(id="yes", label="Yes", key="y"), Option(id="no", label="No", key="n")],
        default="no",
    )


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page)
    app.folder = FOLDER
    return app


def cloud_row(app: ClankConsole) -> int:
    """The row of the cloud preset on the Presets page."""
    return [preset["id"] for preset in app.data.presets].index("cloud-example-coder")


def page_text(app: ClankConsole, page: str) -> str:
    return "\n".join(str(label.content) for label in app.query(f"#page-{page} Label").results(Label))


@pytest.mark.parametrize("tagged", ["", "●", "⠋"], ids=["untagged", "every-tag", "own-spinner"])
async def test_components_pages_join_the_menu_with_their_keys(
    client: Client, home: Home, monkeypatch: pytest.MonkeyPatch, tagged: str
) -> None:
    if tagged == "●":  # a page's status tag drawn before the menu is read, as the phone's was on a slower machine
        monkeypatch.setattr(Page, "badge", lambda self, frame: Content.styled("●", "$clank-good"))
    if tagged == "⠋":  # a page's own tag: the Operations page's spinner while the service's first operations run
        monkeypatch.setattr(OperationsPage, "badge", lambda self, frame: Content.styled("⠋", "$clank-now"))
    app = make(client, home, "home")
    async with app.run_test(size=(120, 34)) as pilot:
        if tagged:
            await settle(
                pilot, lambda: any(tagged in str(item.query_one(Label).content) for item in app.query("#menu .page"))
            )
        shown = [str(item.query_one(Label).content) for item in app.query("#menu .page")]
    pages = [entry[:MENU_NAME].rstrip() for entry in shown]  # each entry's name, without the tag beside it
    assert all(len(entry[MENU_NAME:].strip()) <= 3 for entry in shown), "only a short tag beside a name, whichever"
    assert pages == [
        "F4 This folder",
        "1 Home",
        "2 Questions",
        "3 History",
        "4 Docker",
        "5 Machine",
        "6 Operations",
        "7 Records",
        "8 Models",
        "9 Presets",
        "0 Providers and models",
        "F1 Help",
        "F2 Launch options",
        "F3 MCP servers",
        "F6 Workspaces",
        "F7 Requests",
        "F8 CPU models",
        "F9 Phone",
        "F10 Monitor",
        "F12 Add a model",
    ]


async def test_history_shows_every_event_newest_last_and_filters_by_what_is_typed(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(ask("Stop Docker Desktop?"), asked_by=CLANK)
    kernel.questions.ask(ask("Switch to fast 128K?"), asked_by=CLANK)
    app = make(client, home, "history")
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Switch to fast 128K?" in page_text(app, "history"))
        shown = page_text(app, "history")
        assert shown.index("Stop Docker Desktop?") < shown.index("Switch to fast 128K?")
        assert_frame(await frame_when(pilot, app, "Switch to fast 128K?"), "history")
        await pilot.press("slash", *"fast")
        await settle(pilot, lambda: "Stop Docker Desktop?" not in page_text(app, "history"))
        assert "Switch to fast 128K?" in page_text(app, "history")
        kernel.questions.ask(ask("Load fast 128K now?"), asked_by=CLANK)
        await settle(pilot, lambda: "Load fast 128K now?" in page_text(app, "history"))


async def test_the_history_filter_shows_on_slash_stays_while_it_filters_and_hides_when_left_empty(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(ask("Stop Docker Desktop?"), asked_by=CLANK)
    app = make(client, home, "history")
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Stop Docker Desktop?" in page_text(app, "history"))
        box = app.query_one("#history-filter", Input)
        assert not box.display
        await pilot.press("slash")
        await settle(pilot, lambda: box.has_focus)
        assert box.display
        await pilot.press(*"stop", "escape")
        await settle(pilot, lambda: not box.has_focus)
        assert box.display, "a filter in effect stays in sight"
        await pilot.press("slash")
        await settle(pilot, lambda: box.has_focus)
        await pilot.press(*["backspace"] * 4, "escape")
        await settle(pilot, lambda: not box.display)


async def test_dockers_page_shows_each_container_with_whose_it_is_and_s_asks_to_stop(
    client: Client, kernel: Kernel, home: Home
) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "toolbox-sandbox-017" in page_text(app, "docker"))
        shown = page_text(app, "docker")
        assert "Fake Docker 4.85.0 · running · engine 29.6.2" in shown
        assert "other" in shown
        assert "old-build" in shown
        assert_frame(await frame_when(pilot, app, "old-build"), "docker")
        await pilot.press("s")
        await settle(pilot, lambda: any(q["title"] == "Stop Fake Docker?" for q in app.data.questions))


async def test_the_machines_page_shows_the_profile_and_the_doctors_checks_once_d_ran_it(
    client: Client, home: Home
) -> None:
    app = make(client, home, "machine")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "Not detected yet" in page_text(app, "machine"))
        await pilot.press("d")
        await settle(pilot, lambda: "Docker running" in page_text(app, "machine"))
        await settle(pilot, lambda: "NVIDIA GeForce RTX 5080" in page_text(app, "machine"))
        shown = page_text(app, "machine")
        assert "NVIDIA GeForce RTX 5080" in shown
        assert "start it with `clank docker start`" in shown
        assert_frame(await frame_when(pilot, app, "The API's port"), "machine")


async def test_operations_show_their_steps_and_log_and_c_cancels_the_highlighted_one(
    client: Client, home: Home, platform: FakePlatform
) -> None:
    platform.state = "stopped"
    platform.starts_after = None
    started = client.post("docker/start")
    app = make(client, home, "operations")
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "asked Fake Docker to start" in page_text(app, "operations"))
        shown = page_text(app, "operations")
        assert started["id"] in shown
        assert "2 of 2: wait" in shown
        await focus_on(pilot, app, app.query_one("#operations-list", ListView))
        await pilot.press("c")
        await settle(pilot, lambda: client.get(f"records/operation/{started['id']}")["values"]["status"] == "canceled")
        await settle(pilot, lambda: "canceled by you (console)" in page_text(app, "operations"))
        assert_frame(await frame_when(pilot, app, "canceled by you (console)"), "operations")


def test_the_picker_says_a_cloud_presets_provider_and_prices() -> None:
    cloud = {"id": "cloud-example-coder", "title": "cloud: Example Coder", "engine": "", "engine_version": "",
             "endpoint": "openrouter", "provider": "cloud openrouter", "model": "example-vendor/example-coder",
             "price": {"in": 0.3, "out": 1.2, "cached_in": 0.03}, "problems": []}  # fmt: skip
    [choice] = preset_choices([cloud])
    assert choice.detail == "cloud openrouter · $0.30 in, $1.20 out per million · example-vendor/example-coder"


async def test_a_cloud_preset_says_its_provider_and_prices_on_presets_and_its_model_on_models(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    cloud_api.run("cloud-example-coder")
    app = make(client, home, "presets")
    async with app.run_test(size=(120, 44)) as pilot:
        await frame_when(pilot, app, "cloud openrouter · $0.30 in, $1.20 out per million")
        listed = app.query_one("#presets-list", ListView)
        await focus_on(pilot, app, listed, cloud_row(app))
        frame = await frame_when(pilot, app, "$0.03 cached in, per million tokens")
        await pilot.press("8")
        frame = await frame_when(pilot, app, "window 262,144")
        assert "It runs at OpenRouter's provider: none of this computer's GPU." in frame
        assert "cloud: Example Coder answered in 1 s" in frame


async def test_a_switch_to_a_cloud_preset_from_the_picker_is_the_switch_route(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    app = make(client, home, "models")
    async with app.run_test(size=(120, 44)) as pilot:
        await frame_when(pilot, app, "main")
        await focus_on(pilot, app, app.query_one("#models-slots", ListView), 0)
        await pilot.press("w")
        await settle(pilot, lambda: bool(app.screen.query("#pick-list")))
        picker = app.screen.query_one("#pick-list", ListView)
        assert "cloud openrouter · $0.30 in, $1.20 out per million · example-vendor/example-coder" in render_text(app)
        picker.index = next(index for index, item in enumerate(picker.children)
                            if "cloud: Example Coder" in str(item.query_one(Label).content))  # fmt: skip
        await pilot.press("enter")
        await settle(pilot, lambda: bool(app.data.slots) and app.data.slots[0]["preset"] == "cloud-example-coder")
    main = client.get("runtime/slots")[0]
    assert (main["status"], main["preset"]) == ("ready", "cloud-example-coder")


async def test_a_cloud_presets_explanation_says_its_provider(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    app = make(client, home, "presets")
    async with app.run_test(size=(120, 44)) as pilot:
        await frame_when(pilot, app, "cloud openrouter")
        listed = app.query_one("#presets-list", ListView)
        await focus_on(pilot, app, listed, cloud_row(app))
        page = app.query_one("#page-presets", Page)
        title, lines = page.explain()
    assert title == "cloud: Example Coder"
    assert lines[0].startswith("A cloud preset of cloud openrouter with example-vendor/example-coder, in ")
