"""Design 0011 §3 and §12.8 (the style in the console; a button's colors): the console starts in the style its settings
pick (`clank` until changed), registered as a theme whose variables are the style's elements, before its first frame,
a button's five colors among them; an owner's style that changes an element shows; a style that is not found, or a file that does not read, leaves the console in Clank's own style and
the message line says why (its file, line and field); the console always starts. The marks that say a state, the
spinner's frames, a bar's cells, a sparkline's steps and the mark of cut text are the style's: a style with plain marks
draws only those, and a state's mark takes its state's color in any style. Ctrl+P's "Change style" lists the styles
the service has and writes the one picked to the console's settings through the service; the console draws in a style
as soon as the service reports a change of its settings or of its style's file, the keys bar's keys and Help's
included when only `key` changes, and a file that no longer reads leaves
the last good style in force and says why. Textual's own theme command leaves the palette, and the theme an earlier
console remembered is forgotten once: tokyo-night silently, one the owner had picked named on the message line."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.content import Content
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console.folder import checklist_rows
from clank.console.app import ClankConsole
from clank.console.commands import ClankCommands
from clank.console.gauges import bar, fit, spark, spinner
from clank.console.pick import PickScreen
from clank.console.snapshot import render_text
from clank.console.style import LoadedStyle, use
from clank.console.text import tone
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 18, 13, 0, tzinfo=UTC)
PLAIN = {"schema": "style/1", "title": "Plain", "border": "round", "marks": {"on": "*", "done": "+", "failed": "x"}}


def make(client: Client, home: Home) -> ClankConsole:
    return ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


async def test_the_console_starts_in_the_clank_style_with_its_elements_as_variables(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        assert app.theme == "clank"
        variables = app.get_css_variables()
        assert variables["clank-quiet"].lower() == "#828bb8"
        assert variables["clank-border-focused"].lower() == "#7aa2f7"
        assert variables["clank-box-verify"].lower() == "#bb9af7"
        assert variables["clank-data-1"].lower() == "#7aa2f7"


BUTTONS = {
    "button-hover": "#292e42",
    "button-focused": "#7aa2f7",
    "button-focused-text": "#1a1b26",
    "button-pressed": "#bb9af7",
    "button-unable-focused": "#3b4261",
}


async def test_the_style_names_a_buttons_five_colors_and_a_style_file_may_set_them(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        variables = app.get_css_variables()
        assert {name: variables[f"clank-{name}"].lower() for name in BUTTONS} == BUTTONS
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    owners = {"schema": "style/1", "title": "Mine", "colors": {"button_focused": "#00aa00"}}
    (home.config / "styles" / "clank.json").write_text(json.dumps(owners), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        variables = app.get_css_variables()
        assert variables["clank-button-focused"].lower() == "#00aa00"
        assert variables["clank-button-pressed"].lower() == "#bb9af7", "every other element stays Clank's"


async def test_an_owners_style_that_changes_an_element_shows(client: Client, home: Home) -> None:
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    owners = {"schema": "style/1", "title": "Mine", "colors": {"quiet": "#999999"}}
    (home.config / "styles" / "clank.json").write_text(json.dumps(owners), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        variables = app.get_css_variables()
        assert variables["clank-quiet"].lower() == "#999999"
        assert variables["clank-border"].lower() == "#3b4261", "every other element stays Clank's"


async def test_a_style_that_is_not_found_leaves_clanks_and_says_so(client: Client, home: Home) -> None:
    (home.config / "console.json").write_text(json.dumps({"schema": "console/1", "style": "nowhere"}), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.theme == "clank"
        await settle(pilot, lambda: "nowhere" in message(app))
        assert "not found" in message(app)
        assert render_text(app)


async def test_a_style_file_that_does_not_read_leaves_clanks_and_names_its_file_line_and_field(
    client: Client, home: Home
) -> None:
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    broken = '{\n  "schema": "style/1",\n  "colors": {\n    "good": "#12345"\n  }\n}\n'
    (home.config / "styles" / "clank.json").write_text(broken, encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.get_css_variables()["clank-good"].lower() == "#9ece6a"
        await settle(pilot, lambda: "clank.json" in message(app))
        assert "line 4" in message(app)
        assert "colors.good" in message(app)


def plain(home: Home) -> None:
    """An owner's style `plain`, its marks ones every terminal draws, picked in the console's settings."""
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    (home.config / "styles" / "plain.json").write_text(json.dumps(PLAIN), encoding="utf-8")
    (home.config / "console.json").write_text(json.dumps({"schema": "console/1", "style": "plain"}), encoding="utf-8")


async def test_a_style_with_plain_marks_draws_them_on_home_and_no_others(client: Client, home: Home) -> None:
    plain(home)
    app = make(client, home)
    app.folder = FOLDER
    async with app.run_test(size=(120, 40)) as pilot:
        frame = await frame_when(pilot, app, "service up", "x 4")
    assert "* service up" in frame
    assert "* docker running" in frame
    assert "F4 This folder         x 4" in frame, "This folder's badge in the menu"
    assert not {"●", "✓", "✗"} & set(frame)


def colored(content: Content) -> list[tuple[str, str]]:
    """Each colored part of a line: its text and its color."""
    return [(content.plain[span.start : span.end], str(span.style)) for span in content.spans]


def test_this_folders_steps_draw_the_styles_marks_each_in_its_states_color() -> None:
    elements = {key: value for key, value in PLAIN.items() if key != "schema"}
    use(LoadedStyle("plain", StyleSettings.model_validate(elements)))
    assert (tone("+"), tone("x"), tone("*")) == ("$clank-good", "$clank-failed", "")
    rows = checklist_rows([("Docker", "running", True, ""), ("Its workspace", "not opened yet", False, "o")])
    done, left = rows[0][1], rows[1][1]
    assert done.plain == "+ running"
    assert left.plain.startswith("x not opened yet")
    assert colored(done)[0] == ("+", "$clank-good")
    assert colored(left)[0] == ("x", "$clank-failed")


def test_the_drawing_helpers_draw_the_styles_glyphs() -> None:
    glyphs = {"spinner": "-+", "bar": {"full": "#", "empty": ".", "eighths": " 1234567"}, "sparks": "_-^",
              "marks": {"cut": "~"}}  # fmt: skip
    use(LoadedStyle("plain", StyleSettings.model_validate(glyphs)))
    assert [spinner(frame) for frame in range(3)] == ["-", "+", "-"]
    assert bar(0.5, 4).plain == "##.."
    assert bar(0.53, 10).plain == "#####2...."
    assert spark([0, 50, 100], 3).plain == "_-^"
    assert fit("abcdef", 4) == "abc~"


def color_of(label: Label) -> tuple[int, int, int]:
    color = label.rich_style.color
    assert color is not None
    red, green, blue = color.get_truecolor()
    return red, green, blue


def mine(home: Home, planned: str) -> Path:
    """An owner's style `mine`, whose planned pages are drawn in `planned`."""
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    path = home.config / "styles" / "mine.json"
    path.write_text(
        json.dumps({"schema": "style/1", "title": "Mine", "colors": {"planned": planned}}), encoding="utf-8"
    )
    return path


def planned(app: ClankConsole) -> tuple[int, int, int]:
    return color_of(app.query_one("#menu-sampling Label", Label))


async def test_a_remembered_tokyo_night_is_forgotten_and_never_written_again(client: Client, home: Home) -> None:
    remembered = home.state / "console.json"
    remembered.write_text(json.dumps({"theme": "tokyo-night"}), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "connected (console)" in render_text(app))
        assert "tokyo-night" not in message(app)
    assert not remembered.exists()


async def test_a_theme_the_owner_had_picked_is_forgotten_and_named_once_on_the_message_line(
    client: Client, home: Home
) -> None:
    remembered = home.state / "console.json"
    remembered.write_text(json.dumps({"theme": "nord", "kept": 1}), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "nord" in message(app))
        assert "Change style" in message(app)
    assert json.loads(remembered.read_text(encoding="utf-8")) == {"kept": 1}, "what else it remembered stays"
    again = make(client, home)
    async with again.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "connected (console)" in render_text(again))
        assert "nord" not in message(again)


async def test_the_palette_offers_change_style_and_not_textuals_theme(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)):
        assert "Change style" in [name for name, _, _ in ClankCommands(app.screen).commands()]
        assert "Theme" not in [command.title for command in app.get_system_commands(app.screen)]


async def test_picking_a_style_writes_the_consoles_settings_and_the_console_draws_in_it(
    client: Client, kernel: Kernel, home: Home
) -> None:
    mine(home, "#00ff00")
    kernel.settings.reload_changed()  # the service reads the new file, as it does when a file is saved
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "connected (console)" in render_text(app))
        app.pick_style()
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        picker = app.screen
        assert isinstance(picker, PickScreen)
        assert [choice.value for choice in picker.choices] == ["clank", "mine"]
        picker.dismiss("mine")
        await settle(pilot, lambda: app.theme == "mine" and planned(app) == (0, 255, 0))
    written = json.loads((home.config / "console.json").read_text(encoding="utf-8"))
    assert written["style"] == "mine"


async def test_an_edit_of_the_style_in_force_shows_and_one_that_does_not_read_keeps_the_last_good(
    client: Client, kernel: Kernel, home: Home
) -> None:
    path = mine(home, "#00ff00")
    (home.config / "console.json").write_text(json.dumps({"schema": "console/1", "style": "mine"}), encoding="utf-8")
    kernel.settings.reload_changed()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "connected (console)" in render_text(app) and planned(app) == (0, 255, 0))
        mine(home, "#0000ff")
        kernel.settings.reload_changed()
        await settle(pilot, lambda: planned(app) == (0, 0, 255))
        path.write_text(path.read_text(encoding="utf-8").replace("#0000ff", "#0000f"), encoding="utf-8")
        kernel.settings.reload_changed()
        await settle(pilot, lambda: "mine.json" in message(app))
        assert "colors.planned" in message(app)
        assert planned(app) == (0, 0, 255), "the last good style stays in force"


def drawn_at(app: ClankConsole, x: int, y: int) -> str:
    """The color the screen draws at a column and row, as `#rrggbb`."""
    color = app.screen.get_style_at(x, y).color
    assert color is not None
    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


async def test_an_edit_of_the_style_in_force_that_changes_only_key_recolors_the_keys_bar_and_helps_keys(
    client: Client, kernel: Kernel, home: Home
) -> None:
    path = home.config / "styles" / "mine.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    def write(key: str) -> None:
        path.write_text(json.dumps({"schema": "style/1", "title": "Mine", "colors": {"key": key}}), encoding="utf-8")

    write("#00ff00")
    (home.config / "console.json").write_text(json.dumps({"schema": "console/1", "style": "mine"}), encoding="utf-8")
    kernel.settings.reload_changed()
    app = make(client, home)
    async with app.run_test(size=(170, 120)) as pilot:
        bar = app.size.height - 1
        await settle(pilot, lambda: "connected (console)" in render_text(app))
        app.show_page("help")

        def docker_key() -> tuple[int, int]:
            """Where Help's "Keys on the other pages" draws Docker's first key."""
            lines = render_text(app).splitlines()
            row = next(n for n, line in enumerate(lines) if "s start or stop Docker" in line)
            return lines[row].index("s start or stop Docker"), row

        await settle(pilot, lambda: "Keys on the other pages" in render_text(app))
        assert render_text(app).splitlines()[-1].startswith(" ? explain"), "Help has no keys of its own"
        assert drawn_at(app, 1, bar) == drawn_at(app, *docker_key()) == "#00ff00"
        write("#ff00ff")
        kernel.settings.reload_changed()
        await settle(pilot, lambda: app.get_css_variables()["clank-key"].lower() == "#ff00ff")
        await settle(pilot, lambda: drawn_at(app, 1, bar) == "#ff00ff")
        await settle(pilot, lambda: drawn_at(app, *docker_key()) == "#ff00ff")
        assert "Keys on the other pages" in render_text(app), "still on Help"
