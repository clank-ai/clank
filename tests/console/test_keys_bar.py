"""Design 0011 §4, §7 and §11 (R2): each page declares its keys once, as named actions with their words (`Page.KEYS`),
and the keys bar, Help and `?` read that one declaration. The keys bar, one row on `bars`, shows the page's own keys
first, then `? explain` and `f1 help`, then the other keys that act anywhere (`f5 machine column`, `q quit`) and
`^p palette` at the right, each key in `key` and its words in `quiet`; when it is too narrow, the other keys that act
anywhere go first, then the page's own from the right, and `?` and `f1` always stay. It shows the keys of the page on
screen wherever the focus is. Help lists every key the pages declare, in board E13's four panels, and holds no table
of keys of its own; no panel's key letter is one of its page's keys (on a page with views, of the keys of the view the
panel is in: the Monitor's Session view's `n` is its Now panel's, its Flow view's builds a new flow, design 0013 §15).
No page's key acts anywhere, but a page's own menu key, pressed again while the page is on screen (the Monitor's F10,
its next view: design 0012 §2), and Esc, which a page with a step back inside it declares as its own, `esc back`
(revised 2026-10-29, decision 0151)."""

import itertools
from typing import Any

import pytest
from textual.widgets import Label, ListView

from clank.client import Client
from clank.console import keys as keys_module
from clank.console.app import PAGES, ClankConsole
from clank.console.details import DetailsScreen
from clank.console.keys import ALWAYS, ANYWHERE, PALETTE, PageKey, fit_keys, shown
from clank.console.keysbar import KeysBar
from clank.console.pages import Page
from clank.console.pages import help as help_module
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.home import Home
from tests.console.frames import FOLDER, focus_on, frame_when, settle

pytestmark = pytest.mark.anyio
STYLE = StyleSettings()
FOLDER_KEYS = "g get everything ready  a OpenCode here  c in VS Code"


def make(client: Client, home: Home, page: str = "folder") -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def keys_line(app: ClankConsole) -> str:
    return render_text(app).splitlines()[-1]


def rgb(color: Any) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


def words(page_key: PageKey) -> str:
    return f"{shown(page_key.key)} {page_key.words}"


@pytest.mark.parametrize("width", [120, 80])
async def test_the_keys_bar_shows_this_folders_keys_first_then_explain_and_help(
    client: Client, home: Home, width: int
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 40)) as pilot:
        await frame_when(pilot, app, "Get ready to work here")
        line = keys_line(app)
        assert line.startswith(f" {FOLDER_KEYS}"), line
        assert line.index("? explain  f1 help") > line.index("c in VS Code"), line


async def test_the_keys_bar_is_one_row_on_bars_each_key_in_key_and_its_words_in_quiet(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(170, 40)) as pilot:
        await frame_when(pilot, app, "Get ready to work here")
        bar = app.query_one(KeysBar)
        assert bar.region.height == 1
        assert bar.region.y == app.size.height - 1
        line = keys_line(app)
        row = app.size.height - 1
        for text, color in [("g", STYLE.colors.key), ("get everything ready", STYLE.colors.quiet)]:
            style = app.screen.get_style_at(line.index(f" {text}") + 1, row)
            assert rgb(style.color) == color, text
            assert rgb(style.bgcolor) == STYLE.colors.bars, text
        app.show_page("docker")
        await settle(pilot, lambda: keys_line(app).startswith(" s start or stop Docker"))
        line = keys_line(app)
        assert "f1 help  esc menu  f5 machine column  q quit  " in line
        assert line.endswith("^p palette "), "the palette's key at the right, while there is room"


def test_a_narrow_keys_bar_drops_the_other_keys_that_act_anywhere_first_then_the_pages_from_the_right() -> None:
    page = (PageKey("s", "docker", "start or stop Docker"), PageKey("d", "doctor", "run the doctor"))
    every, palette = fit_keys(page, 200)
    assert [key.action for key in every] == ["docker", "doctor", *(key.action for key in ANYWHERE)]
    assert palette
    narrower = []
    for width in range(130, 0, -1):
        kept, palette = fit_keys(page, width)
        narrower.append(([key.action for key in kept], palette))
    seen = [narrower[0]] + [each for before, each in itertools.pairwise(narrower) if each != before]
    anywhere = [key.action for key in ANYWHERE]
    assert (
        [actions for actions, _ in seen[1:]]
        == [
            ["docker", "doctor", *anywhere],  # the palette went
            ["docker", "doctor", *anywhere[:-1]],  # then ^b (decision 0125)
            ["docker", "doctor", *anywhere[:-2]],  # then q
            ["docker", "doctor", *anywhere[:-3]],  # then f5
            ["docker", "doctor", *anywhere[:-4]],  # then esc (decision 0129)
            ["docker", *anywhere[:-4]],  # then the page's own, from the right
            anywhere[:-4],
        ]
    )
    assert [key.action for key in ALWAYS] == anywhere[:-4] == ["explain", "page('help')"], "? and f1 always stay"
    assert fit_keys(page, 5)[0] == list(ALWAYS)


def test_each_page_declares_its_keys_as_named_actions_none_of_them_a_key_that_acts_anywhere() -> None:
    declared = 0
    for page in PAGES:
        others = {other.ENTRY.key.lower() for other in PAGES if other is not page}  # its own: pressed again on it
        anywhere = ({key.key for key in (*ANYWHERE, PALETTE)} | others) - {"escape"}  # a step back: decision 0151
        assert isinstance(page.KEYS, tuple), page.ENTRY.id
        assert all(isinstance(key, PageKey) for key in page.KEYS), page.ENTRY.id
        actions = [key.action for key in page.KEYS]
        assert all(action.isidentifier() for action in actions), (page.ENTRY.id, actions)
        assert len(set(actions)) == len(actions), f"{page.ENTRY.id}: an action named twice"
        pressed = [key.key for key in page.KEYS]
        assert len(set(pressed)) == len(pressed), f"{page.ENTRY.id}: a key declared twice"
        assert not set(pressed) & anywhere, f"{page.ENTRY.id}: {set(pressed) & anywhere} act anywhere"
        assert all(key.words for key in page.KEYS), page.ENTRY.id
        declared += len(page.KEYS)
    assert declared >= 50, "the pages' keys are declared"


async def test_no_panel_letter_is_one_of_its_pages_keys(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for page in app.query(Page):
            views = getattr(page, "VIEW_KEYS", None)
            if views is None:
                letters = {panel.key for panel in page.query(Panel) if panel.key}
                assert not letters & {key.key for key in page.KEYS}, page.id
                continue
            for view, keys in views.items():  # a page with views: a letter of a view's panels, against its keys
                letters = {panel.key for panel in page.query(f"Panel.view-{view}").results(Panel) if panel.key}
                assert not letters & set(keys), (page.id, view)


async def test_the_keys_bar_shows_the_keys_of_the_page_on_screen_wherever_the_focus_is(
    client: Client, home: Home
) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        menu = app.query_one("#menu", ListView)
        assert app.focused is menu
        assert keys_line(app).startswith(" s start or stop Docker  r read it again  ? explain  f1 help")
        await focus_on(pilot, app, menu, next(n for n, item in enumerate(menu.children) if item.id == "menu-machine"))
        await settle(pilot, lambda: keys_line(app).startswith(" d run the doctor  ? explain"))
        await pilot.press("right")
        await settle(pilot, lambda: app.focused is not menu)
        assert keys_line(app).startswith(" d run the doctor  ? explain")


async def test_help_lists_every_key_the_pages_declare_in_four_panels_and_holds_no_table_of_its_own(
    client: Client, home: Home
) -> None:
    assert not hasattr(help_module, "KEYS"), "Help reads the pages' declarations"
    app = make(client, home, "help")
    async with app.run_test(size=(170, 60)) as pilot:
        await pilot.pause()
        help_page = app.query_one("#page-help", Page)
        assert [panel.title for panel in help_page.query(Panel)] == [
            "Keys anywhere",
            "Keys on This folder",
            "Keys on the other pages",
            "What each page shows",
        ]

        def text(panel: str) -> str:
            labels = help_page.query_one(f"#{panel}", Panel).query(Label).results(Label)
            return " ".join(str(label.content) for label in labels)

        anywhere = text("help-anywhere")
        for key in (*ANYWHERE, PALETTE):
            assert shown(key.key) in anywhere, key
            assert (key.help or key.words) in anywhere, key
        first = next(page for page in PAGES if page.ENTRY.first)
        for key in first.KEYS:
            assert (key.help or key.words) in text("help-first"), key
        others = text("help-others")
        for page in PAGES:
            if page is first or not page.KEYS:
                continue
            assert page.ENTRY.label in others, page.ENTRY.id
            for key in page.KEYS:
                assert words(key) in others, (page.ENTRY.id, key)


async def test_question_mark_says_the_keys_the_page_declares_on_its_menu_entry_and_in_the_page(
    client: Client, home: Home
) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        menu = app.query_one("#menu", ListView)
        assert app.focused is menu, "the focus starts on the menu's entry"

        async def explained() -> str:
            await pilot.press("question_mark")
            await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
            said = " ".join(str(label.content) for label in app.screen.query(Label).results(Label))
            await pilot.press("escape")
            await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
            return said

        assert "Its keys: s start or stop Docker · r read it again." in await explained()
        await pilot.press("right")
        await settle(pilot, lambda: app.focused is not menu and app.focused is not None)
        assert "Its keys: s start or stop Docker · r read it again." in await explained(), "the page's own"


def test_the_keys_module_names_how_a_key_is_shown() -> None:
    assert [shown(key) for key in ("question_mark", "slash", "escape", "enter", "ctrl+p", "f1", "s")] == [
        "?",
        "/",
        "esc",
        "enter",
        "^p",
        "f1",
        "s",
    ]
    assert keys_module.PALETTE.words == "palette"


async def test_a_click_on_a_key_of_the_keys_bar_presses_it(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        await pilot.click(KeysBar, offset=(keys_line(app).index("? explain") + 2, 0))
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
