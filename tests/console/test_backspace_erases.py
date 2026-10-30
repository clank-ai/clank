"""Design 0011 §12.4 (revised 2026-10-29, decision 0151: the owner's report that Backspace went back a step while they
typed in Add a model): Backspace erases in a field you type in and never moves you; Esc goes back. A field's own keys
(Backspace, Delete, the arrows, Home, End) stay the field's, on a page and in a window, and the page under it never
hears them. No page declares Backspace as a key of its own. On Add a model, Backspace in the models' search, in the
key's hidden field and in a setting erases there, the step staying; Backspace outside a field does nothing; Esc leaves
the search first, then goes back one step, and from the first step to the menu, the page staying as it was. Where Esc
steps back, the keys bar says `esc back`; it never writes `bksp`."""

from datetime import UTC, datetime

import pytest
from textual.widgets import Input, TextArea

from clank.client import Client
from clank.components.agents.console.flowview import BOARD_KEYS
from clank.components.runtime.console.addmodel import SCREEN_KEYS, AddModelPage
from clank.console.app import PAGES, ClankConsole
from clank.console.editor import EditScreen
from clank.console.form import Field, FormScreen, SecretField
from clank.console.pages import Page
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle
from tests.console.test_add_model import CHOICE, KEY_SCREEN, on_screen, to_models
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 29, 9, 14, tzinfo=UTC)
FIELD_KEYS = ("backspace", "left", "delete", "home", "end", "right")


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page)
    app.folder = FOLDER
    return app


def heard_by(page: Page) -> list[str]:
    """The keys the console gives the page from now on, each still acted on as before."""
    heard: list[str] = []
    press = page.press

    def listening(key: str) -> bool:
        heard.append(key)
        return press(key)

    page.press = listening  # type: ignore[method-assign]
    return heard


def adding(app: ClankConsole) -> AddModelPage:
    return app.query_one("#page-addmodel", AddModelPage)


def test_no_page_declares_backspace_as_a_key_of_its_own() -> None:
    declared = [key for page in PAGES for key in page.KEYS]
    declared += [key for keys in SCREEN_KEYS.values() for key in keys]
    declared += [key for keys in BOARD_KEYS.values() for key in keys]
    assert [key for key in declared if key.key == "backspace"] == []


async def test_a_fields_own_keys_stay_the_fields_and_the_page_never_hears_them(client: Client, home: Home) -> None:
    app = make(client, home, "home")
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot, lambda: "f1 help" in render_text(app))
        page = app.query_one("#page-home", Page)
        heard = heard_by(page)
        field = Input(id="typed-here")
        await page.mount(field)
        field.focus()
        await settle(pilot, lambda: app.focused is field)
        await pilot.press(*"hello", "backspace")
        assert field.value == "hell", "Backspace erases the last character"
        await pilot.press("left", "delete", "home", "end", "backspace")
        assert field.value == "he"
        assert [key for key in heard if key in FIELD_KEYS] == [], "the page never hears a field's own keys"
        assert app.screen is page.screen, "nothing moved"


async def test_in_a_window_backspace_erases_its_field_and_the_page_under_it_never_hears_it(
    client: Client, home: Home
) -> None:
    app = make(client, home, "home")
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot, lambda: "f1 help" in render_text(app))
        heard = heard_by(app.query_one("#page-home", Page))
        window = FormScreen("A name", [Field("name", "Name", "")])
        app.push_screen(window)
        await settle(pilot, lambda: app.screen is window and isinstance(app.focused, Input))
        await pilot.press(*"paper", "backspace", "backspace")
        assert window.query_one(Input).value == "pap"
        editor = EditScreen("A note to the model", "Look first.", "Enter sends it.")
        app.push_screen(editor)
        await settle(pilot, lambda: app.screen is editor and isinstance(app.focused, TextArea))
        await pilot.press("end", "backspace", "left", "delete")
        assert editor.query_one(TextArea).text == "Look firs"
        assert [key for key in heard if key in FIELD_KEYS] == []
        assert app.screen is editor, "the windows stay open"


async def test_backspace_in_the_models_search_erases_there_and_esc_leaves_the_search_then_goes_back(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home, "addmodel")
    async with app.run_test(size=(88, 44)) as pilot:
        await to_models(pilot, app)
        await pilot.press("slash", *"smal", "backspace")
        search = app.query_one("#add-search", Input)
        await settle(pilot, lambda: search.value == "sma")
        assert adding(app).screen_name == "model", "Backspace erased; the step stayed"
        assert "esc back" in render_text(app).splitlines()[-1]
        assert "bksp" not in render_text(app)
        await pilot.press("escape")
        await settle(pilot, lambda: not search.display)
        assert adding(app).screen_name == "model", "Esc leaves the search first"
        await pilot.press("escape")
        await on_screen(pilot, app, CHOICE)
        await pilot.press("escape")
        await settle(pilot, lambda: app.focused is not None and app.focused.id == "menu")
        assert adding(app).screen_name == "choice", "from the first step, Esc goes to the menu, the page staying"


async def test_backspace_in_the_keys_hidden_field_erases_and_never_leaves_the_step(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add(key=False)
    app = make(client, home, "addmodel")
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c")
        await on_screen(pilot, app, KEY_SCREEN)
        field = app.query_one(SecretField)
        await settle(pilot, lambda: app.focused is field)
        await pilot.press(*"q1-made-up", "backspace", "backspace")
        assert field.ends == "ade-"
        await pilot.press(*["backspace"] * 12)
        assert not field.filled
        assert adding(app).screen_name == "key", "Backspace on an empty field does nothing"
    assert cloud_api.calls == []


async def test_backspace_in_a_setting_erases_there_and_outside_a_field_does_nothing(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home, "addmodel")
    async with app.run_test(size=(88, 44)) as pilot:
        await to_models(pilot, app)
        await pilot.press("enter")
        await on_screen(pilot, app, "Its settings")
        output = app.query_one("#add-max_output", Input)
        output.focus()
        await settle(pilot, lambda: app.focused is output)
        await pilot.press("end", "backspace")
        assert output.value == "1638"
        assert adding(app).screen_name == "settings"
        app.set_focus(None)  # the focus on no field
        await pilot.press("backspace")
        assert adding(app).screen_name == "settings", "Backspace outside a field does nothing"
        await pilot.press("escape")
        await on_screen(pilot, app, "that take tool calls")
        assert adding(app).screen_name == "model", "Esc goes back one step"


async def test_on_the_first_steps_esc_goes_back_and_the_keys_bar_says_so(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home, "addmodel")
    async with app.run_test(size=(88, 34)) as pilot:
        await on_screen(pilot, app, CHOICE)
        await pilot.press("c")
        await on_screen(pilot, app, "openrouter.ai")
        bar = render_text(app).splitlines()[-1]
        assert "esc back" in bar, bar
        assert "esc menu" not in bar, bar
        await pilot.press("backspace")
        assert adding(app).screen_name == "provider", "Backspace never goes back"
        await pilot.press("escape")
        await on_screen(pilot, app, CHOICE)
        assert "esc menu" in render_text(app).splitlines()[-1]
