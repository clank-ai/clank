"""Design 0011 §12.3 and §12.7 (pressing a button; a button that cannot act now): a key typed and its button, pressed
by Enter, Space or a click, reach the same `press` of the page, through the console's one door; a key that acts
anywhere runs its binding's action; a key the page says cannot act now says why on the message line, typed or pressed,
and the page's `press` is not called; a key of several says the keys it stands for; every group that shows a key shows
it pressed when it is pressed, by its key too. A digit opens its page while the focus is not in the page, and is the
page's only once the focus is in it (design 0001 §5.1)."""

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.buttons import Button, Buttons
from clank.console.details import DetailsScreen
from clank.console.keys import ANYWHERE, PageKey
from clank.console.pages import Page
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import FOLDER, frame_when, settle

pytestmark = pytest.mark.anyio
READ = PageKey("r", "read", "read it again")
NUMBERED = QuestionDraft(
    type="choice",
    title="Which preset?",
    options=[Option(id="daily", label="daily 262K", key="1"), Option(id="fast", label="fast 128K", key="2")],
)


def make(client: Client, home: Home, page: str) -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


def recorded(page: Page, unable: dict[str, str] | None = None) -> list[str]:
    """The keys the page's `press` is called with, from now on; `unable` says which cannot act now, and why."""
    pressed: list[str] = []

    def press(key: str) -> bool:
        pressed.append(key)
        return key in ("s", "r")

    page.press = press  # type: ignore[method-assign]
    if unable is not None:
        page.unable = lambda key: unable.get(key, "")  # type: ignore[method-assign]
    return pressed


async def test_a_key_typed_and_its_button_reach_the_same_press_of_the_page(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        pressed = recorded(app.query_one("#page-docker", Page))
        await pilot.press("r")
        app.press_button(Button(READ))
        await pilot.pause()
        assert pressed == ["r", "r"]


async def test_a_key_that_acts_anywhere_runs_its_bindings_action(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        help_key = next(key for key in ANYWHERE if key.key == "f1")
        app.press_button(Button(help_key))
        await settle(pilot, lambda: app.query_one("#pages").current == "page-help")  # type: ignore[attr-defined]
        explain = next(key for key in ANYWHERE if key.key == "question_mark")
        app.press_button(Button(explain))
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))


async def test_a_key_that_cannot_act_now_says_why_typed_or_pressed_and_the_page_is_not_pressed(
    client: Client, home: Home
) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        pressed = recorded(app.query_one("#page-docker", Page), {"r": "nothing to read yet"})
        await pilot.press("r")
        await settle(pilot, lambda: "nothing to read yet" in message(app))
        assert app.query_one("#message", Label).has_class("error")
        app.say("something else")
        app.press_button(Button(READ))
        await settle(pilot, lambda: "nothing to read yet" in message(app))
        assert pressed == []


async def test_a_key_of_several_says_the_keys_it_stands_for(client: Client, home: Home) -> None:
    app = make(client, home, "questions")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "No question waits")
        app.press_button(Button(PageKey("y n …", "answer", "answer it with an option's key")))
        await settle(pilot, lambda: "y n …" in message(app))


async def test_every_group_that_shows_a_key_shows_it_pressed_when_its_key_is_typed(client: Client, home: Home) -> None:
    app = make(client, home, "docker")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        recorded(app.query_one("#page-docker", Page))
        other = Buttons([Button(READ)], id="other")
        await app.query_one("#page-docker", Page).mount(other)
        await pilot.press("r")
        assert other.pressed == 0
        await settle(pilot, lambda: other.pressed is None)


async def test_a_digit_opens_its_page_until_the_focus_is_in_the_page_that_takes_it(
    client: Client, kernel: Kernel, home: Home
) -> None:
    asked = kernel.questions.ask(NUMBERED, asked_by=CLANK)
    app = make(client, home, "home")
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, "Which preset?")
        assert app.focused is not None
        assert app.focused.id == "menu"
        await pilot.press("2")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-questions")  # type: ignore[attr-defined]
        await pilot.pause(0.3)
        assert kernel.questions.get(asked.id).answer is None, "the digit opened its page and answered nothing"
