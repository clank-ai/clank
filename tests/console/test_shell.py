"""Design 0001 §5.1, §5.5, §5.7, design 0002 §2.15, §3.2 and design 0011 §7: the console's shell. Its menu lists every
page it has, each with its key (the F-keys by their number, F10 after F9: design 0012 §2), then every page a later
milestone brings, in red, each with its milestone; a planned
entry opens a red page that says which milestone builds it and what it will do (the owner's request, 2026-10-11); a
highlight overtaken by a newer one before it was heard never takes the menu back. The
header shows the service's uptime, Docker's state and the questions waiting, or that the service is not running. The
style sheet in CLANK_HOME is loaded after Clank's; animations are off; a burst of events is drawn in a few redraws, at
most four a second, and nothing is lost. In the style's look (design 0011 §7): the header is one row on `bars`, the
folder's name in `name` at normal weight on every page ("◆ CLANK" alone bold), each pill whole in its state's color and
the clock in `quiet`; the menu's keys are in `key`, its highlighted entry on `selection` in `selected-text`, bold,
whether the menu has the focus or not, and "coming" in `quiet`; the message line stands above the keys bar, in `quiet`,
an error in `attention`, bold. Design 0028 §4 and decision 0148: while anything the setup needs is missing, a bare
`clank` and `clank console` open on Setup in place of This folder or Home, the header saying "no model: Add a model"
when no model is usable; design 0016 §14 and decision 0105: with the setup done and no model usable, they open on Add a
model; a page named on the command line opens as asked, the header still saying so; with a model ready and the setup
done, the console opens as it always did. A page without a key of its own (Setup) is listed after those with one."""

import time
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner
from textual.color import Color
from textual.widgets import ContentSwitcher, Label, ListItem, ListView

from clank.cli import console as console_command
from clank.cli.main import main
from clank.client import Client
from clank.components.runtime.state import LastGood
from clank.components.workspaces.sandbox import image_tag
from clank.console import app as console_app
from clank.console.app import ClankConsole
from clank.console.menu import PLANNED, MenuEntry, place
from clank.console.snapshot import render_text
from clank.kernel.access import client_actor
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.fakes.platform import FakePlatform
from tests.support.cloud import CloudBench
from tests.support.served import free_port

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)
PLANNED_COLOR = Color.parse(StyleSettings().colors.planned).rgb  # Clank's style's color for a later milestone's page
STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def color_of(label: Label) -> tuple[int, int, int]:
    color = label.rich_style.color
    assert color is not None
    return tuple(color.get_truecolor())  # type: ignore[return-value]


def loaded(app: ClankConsole) -> bool:
    frame = render_text(app)
    return "Fake Docker" in frame and "connected (console)" in frame


async def test_the_menu_lists_every_page_with_its_key_then_every_planned_page_in_red_with_its_milestone(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        pages = [str(item.query_one(Label).content) for item in app.query("#menu .page")]
        assert pages[0].startswith("F4 This folder"), "the page a bare clank opens comes first"
        keys = [page.split()[0] for page in pages]
        assert keys == [
            "F4",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "0",
            "F1",
            "F2",
            "F3",
            "F6",
            "F7",
            "F8",
            "F9",
            "F10",
            "F12",
            "Setup",
        ], "the first page, the digits (0 last), then F keys, then a page without a key of its own"
        planned = {item.id: item for item in app.query("#menu .planned")}
        assert set(planned) == {f"menu-{entry.id}" for entry in PLANNED}
        for entry in PLANNED:
            label = planned[f"menu-{entry.id}"].query_one(Label)
            assert entry.label in str(label.content)
            assert entry.milestone in str(label.content)
            assert color_of(label) == PLANNED_COLOR


def test_the_menu_sorts_its_f_keys_by_their_number_so_f10_follows_f9() -> None:
    entries = [MenuEntry(id, id, "", "", key=key) for id, key in [("a", "F10"), ("b", "F2"), ("c", "0"), ("d", "F9")]]
    entries += [MenuEntry("e", "e", "", "", key="1"), MenuEntry("f", "f", "", "", key="F4", first=True)]
    assert [entry.key for entry in sorted(entries, key=place)] == ["F4", "1", "0", "F2", "F9", "F10"]


async def test_a_planned_entry_opens_a_red_page_naming_its_milestone_and_what_it_will_do(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#menu-sampling")
        await settle(pilot, lambda: "coming in M3" in render_text(app))
        page = " ".join(str(label.content) for label in app.query("#page-sampling Label").results(Label))
        assert "a change applies from the next request" in page
        assert "design 0001 §3.3, §5.3" in page
        assert color_of(app.query_one("#page-sampling Label", Label)) == PLANNED_COLOR


async def test_a_menu_highlight_overtaken_by_a_newer_one_never_takes_the_menu_back(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        menu = app.query_one("#menu", ListView)
        items = list(menu.query(ListItem).results(ListItem))
        first = next(item for item in items if item.id == "menu-home")
        agents = next(n for n, item in enumerate(items) if item.id == "menu-agents")
        menu.post_message(ListView.Highlighted(menu, first))  # Home's highlight, not heard yet...
        menu.index = agents  # ...when a newer one moves the menu on (a quick key, or a test's own move)
        pages = app.query_one("#pages", ContentSwitcher)
        await settle(pilot, lambda: pages.current == "page-agents")
        for _ in range(10):
            await pilot.pause()
            assert (menu.index, pages.current) == (agents, "page-agents"), "the older highlight took the menu back"


async def test_the_header_shows_the_services_uptime_dockers_state_and_the_questions_waiting(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(STOP, asked_by=CLANK)
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "1 question waiting" in render_text(app).splitlines()[0])
        header = render_text(app).splitlines()[0]
        assert "service up 2h14m" in header
        assert "docker running" in header
        assert header.rstrip().endswith("13:54")


async def test_the_header_says_when_the_service_is_not_running(home: Home) -> None:
    app = make(Client(f"http://127.0.0.1:{free_port()}", "t", name="console"), home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "service not running" in render_text(app).splitlines()[0])


async def test_a_style_sheet_in_clank_home_is_loaded_after_clanks(client: Client, home: Home) -> None:
    (home.config / "console.tcss").write_text(".planned { color: blue; }\n", encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        assert color_of(app.query_one("#menu-sampling Label", Label)) == (0, 0, 255)


async def test_animations_are_off(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        assert app.animation_level == "none"


@pytest.mark.parametrize("width", [120, 80])
async def test_home_at_120_and_at_80_columns(client: Client, home: Home, width: int) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 30)) as pilot:
        assert_frame(await frame_when(pilot, app, "Fake Docker", "connected (console)"), f"home-{width}")


async def test_a_burst_of_events_is_drawn_in_a_few_redraws_and_nothing_is_lost(
    client: Client, kernel: Kernel, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: loaded(app))
        before = app.redraws
        started = time.monotonic()
        for _ in range(50):
            kernel.questions.ask(STOP, asked_by=CLANK)
        await settle(
            pilot,
            lambda: (
                len(app.data.questions) == 50
                and sum(event["type"] == "question.asked" for event in app.data.history) == 50
            ),
        )
        elapsed = time.monotonic() - started
        assert app.redraws - before <= elapsed * 4 + 2


def rgb(color: Any) -> str:
    """A rendered color (Rich's) as `#rrggbb`."""
    assert color is not None
    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


async def test_the_page_on_screen_is_found_without_searching_the_whole_console(
    client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The keys' buttons ask for the page on screen many times a frame, the menu for every page's badge four times a
    second: a search of the whole console each time (every page's widgets are in it) made a page switch take a fifth of
    a second (measured 2026-10-22). A page found once is found again from the console's index."""
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "f1 help")
        assert app._shown_page() is not None
        searched: list[Any] = []
        original = ClankConsole.query

        def query(self: ClankConsole, selector: Any = None) -> Any:
            searched.append(selector)
            return original(self, selector)

        monkeypatch.setattr(ClankConsole, "query", query)
        for _ in range(50):
            assert app._shown_page() is not None
        assert searched == [], "no search of the console for the page on screen"


async def test_the_header_is_one_row_on_bars_naming_the_folder_in_name_not_bold_on_every_page(
    client: Client, home: Home
) -> None:
    style = StyleSettings()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        for page in [entry.id for entry in app.entries()]:
            app.show_page(page)
            await pilot.pause()
            header = render_text(app).splitlines()[0]
            assert "◆ CLANK  paper" in header, page
            at = app.screen.get_style_at(header.index("paper"), 0)
            assert rgb(at.color) == style.colors.name, page
            assert rgb(at.bgcolor) == style.colors.bars, page
            assert not at.bold, f"{page}: the folder's name at normal weight, as the boards draw it"
            brand = app.screen.get_style_at(header.index("CLANK"), 0)
            assert rgb(brand.color) == style.colors.brand
            assert brand.bold, "◆ CLANK bold"


async def test_each_pill_is_drawn_whole_in_its_states_color_and_the_clock_in_quiet(client: Client, home: Home) -> None:
    style = StyleSettings()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "docker running" in render_text(app).splitlines()[0])
        header = render_text(app).splitlines()[0]
        start = header.index("docker running") - 2  # its dot, then its words
        colors = {rgb(app.screen.get_style_at(x, 0).color) for x in range(start, start + len("● docker running"))}
        assert colors == {style.colors.good}
        assert rgb(app.screen.get_style_at(header.rstrip().index("13:54"), 0).color) == style.colors.quiet


async def test_the_menus_keys_are_in_key_and_its_highlighted_entry_on_selection_in_selected_text_bold(
    client: Client, home: Home
) -> None:
    style = StyleSettings()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        item = app.query_one("#menu-home")
        assert item.has_class("-highlight")
        x, y = item.region.x, item.region.y
        for focused in (True, False):
            if not focused:
                await pilot.press("right")
                await settle(pilot, lambda: app.focused is not app.query_one("#menu"))
            name = app.screen.get_style_at(x + 2, y)  # "1 Home": its name
            assert rgb(name.bgcolor) == style.colors.selection, focused
            assert rgb(name.color) == style.colors.selected_text, focused
            assert name.bold, focused
            assert rgb(app.screen.get_style_at(x, y).color) == style.colors.key, focused
        other = app.query_one("#menu-docker")
        assert rgb(app.screen.get_style_at(other.region.x, other.region.y).color) == style.colors.key
        assert rgb(app.screen.get_style_at(other.region.x + 2, other.region.y).color) == style.colors.text
        coming = app.query_one("#menu-coming")
        assert rgb(app.screen.get_style_at(coming.region.x + 2, coming.region.y + 1).color) == style.colors.quiet


async def test_the_message_line_stands_above_the_keys_bar_in_quiet_and_an_error_in_attention_bold(
    client: Client, home: Home
) -> None:
    style = StyleSettings()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        row = app.size.height - 2
        for error, color in ((False, style.colors.quiet), (True, style.colors.attention)):
            app.say("something happened", error=error)
            await settle(pilot, lambda: "something happened" in render_text(app).splitlines()[row])
            at = app.screen.get_style_at(render_text(app).splitlines()[row].index("something"), row)
            assert rgb(at.color) == color
            assert bool(at.bold) == error


def current_page(app: ClankConsole) -> str:
    return str(app.query_one("#pages", ContentSwitcher).current)


async def test_with_something_the_setup_needs_missing_clank_opens_on_setup_the_header_saying_no_model(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="folder", guide=True)
    app.folder = FOLDER
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: current_page(app) == "page-setup")
        await settle(pilot, lambda: "What Clank needs on this computer" in render_text(app))
        assert "no model: Add a model" in render_text(app).splitlines()[0]


def set_up(kernel: Kernel, platform: FakePlatform, preset: str) -> None:
    """What the setup needs, done: the sandbox image built, a preset that answered a test request, a workspace."""
    platform.images.add(image_tag())
    kernel.parts["runtime"].state.remember_good("main", LastGood(preset=preset, time=NOW))
    kernel.settings.write("workspace", "paper", {"path": FOLDER}, base=None, actor=client_actor("console"))


async def test_with_the_setup_done_and_no_model_usable_clank_opens_on_add_a_model(
    client: Client, home: Home, kernel: Kernel, platform: FakePlatform, cloud_api: CloudBench
) -> None:
    set_up(kernel, platform, "daily-262k")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="folder", guide=True)
    app.folder = FOLDER
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: current_page(app) == "page-addmodel")
        await settle(pilot, lambda: "How should Clank run its model?" in render_text(app))


async def test_with_a_model_ready_clank_opens_on_this_folder(
    client: Client, home: Home, kernel: Kernel, platform: FakePlatform, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    cloud_api.run("cloud-example-coder")
    set_up(kernel, platform, "cloud-example-coder")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="folder", guide=True)
    app.folder = FOLDER
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "cloud: Example Coder" in render_text(app).splitlines()[0])
        await pilot.pause(0.3)
        assert current_page(app) == "page-folder"


async def test_a_page_named_on_the_command_line_opens_as_asked_the_header_saying_no_model(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="models")
    app.folder = FOLDER
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "no model: Add a model" in render_text(app).splitlines()[0])
        await pilot.pause(0.3)
        assert current_page(app) == "page-models"


def test_a_bare_clank_and_clank_console_open_the_guide_and_a_page_named_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[dict[str, Any]] = []

    class Recorded:
        def __init__(self, client: Any, **kwargs: Any) -> None:
            opened.append(kwargs)

        def run(self, **kwargs: Any) -> None:
            return None

    class Unused:
        def close(self) -> None:
            return None

    monkeypatch.setattr(console_app, "ClankConsole", Recorded)
    monkeypatch.setattr(console_command, "connect", lambda home, start: Unused())
    for arguments in ([], ["console"], ["console", "--page", "models"]):
        assert CliRunner().invoke(main, arguments).exit_code == 0
    assert [(each["page"], each["guide"]) for each in opened] == [("folder", True), ("home", True), ("models", False)]
