"""Design 0011 §12.4 and §12.6 (`?` on a focused button; the message line): while a group has the focus, the message
line says what its focused button does and how it is pressed, in `quiet`, or why it cannot act now, in `attention`, cut
to its one row; a message of an action replaces it; when the focus leaves the groups, it goes, unless a message came
since. `?` with a button focused opens the details window about it: what it does and the keys that press it, or why it
cannot act now; on the keys bar's own `?`, about what had the focus before the keys bar."""

import pytest
from textual.widgets import Label, ListView

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.keysbar import KeysBar
from clank.console.pages import Page
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle

pytestmark = pytest.mark.anyio


def make(client: Client, home: Home, page: str = "docker") -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


def explained(app: ClankConsole) -> tuple[str, str]:
    """The details window's title and its words."""
    assert isinstance(app.screen, DetailsScreen)
    words = " ".join(str(label.content) for label in app.screen.query(Label).results(Label))
    return app.screen.heading, words


async def test_the_message_line_says_what_the_focused_button_does_and_how_it_is_pressed(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        app.query_one("#page-docker", Page).unable = (  # type: ignore[method-assign]
            lambda key: "Docker is not read yet" if key == "r" else ""
        )
        app.query_one(KeysBar).focus()
        await settle(pilot, lambda: "s start or stop Docker" in message(app))
        assert "Enter, Space, s or a click" in message(app)
        assert not app.query_one("#message", Label).has_class("error")
        await pilot.press("right")
        await settle(pilot, lambda: "Docker is not read yet" in message(app))
        assert app.query_one("#message", Label).has_class("error"), "why it cannot act, in attention"


async def test_the_message_line_is_cut_to_its_one_row(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(60, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        app.query_one(KeysBar).focus()
        await settle(pilot, lambda: "s start or stop Docker" in message(app))
        assert len(message(app)) <= 58
        assert message(app).endswith("…")


async def test_a_message_replaces_it_and_leaving_the_groups_clears_it_unless_a_message_came_since(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        bar, menu = app.query_one(KeysBar), app.query_one("#menu", ListView)
        bar.focus()
        await settle(pilot, lambda: "s start or stop Docker" in message(app))
        menu.focus()
        await settle(pilot, lambda: message(app) == "")
        bar.focus()
        await settle(pilot, lambda: "s start or stop Docker" in message(app))
        app.say("asked Docker to start")
        menu.focus()
        await pilot.pause()
        assert "asked Docker to start" in message(app)


async def test_question_mark_on_a_focused_button_explains_it(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        bar = app.query_one(KeysBar)
        bar.focus()
        await pilot.press("right", "question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        title, words = explained(app)
        assert title == "r read it again"
        assert "Enter or Space while it has the focus, by r from anywhere on this page, or by a click" in words
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        assert app.focused is bar


async def test_the_keys_bars_own_question_mark_explains_what_had_the_focus_before(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 30)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        assert app.focused is app.query_one("#menu", ListView)
        bar = app.query_one(KeysBar)
        bar.focus()
        await pilot.pause()
        bar.move(next(index for index, each in enumerate(bar.buttons) if each.key.key == "question_mark"))
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        title, _ = explained(app)
        assert title == "Docker", "the menu's entry, which had the focus"
