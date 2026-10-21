"""Design 0002 §2.5 and design 0011 §12.1: the questions page lists every question waiting for the user, each with its
detail, its options and who asked it when; the highlighted one is answered with an option's key, as you (console). Each
question's options are buttons, clicked: a click on another question's option highlights it and answers it, the list
keeping the focus."""

from datetime import UTC, datetime

import pytest
from textual.widgets import ListView

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.buttons import Buttons
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import assert_frame, focus_on, frame_when, settle

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)
FIRST = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    detail="2 containers that Clank did not start are running: another-model-relay, toolbox-sandbox-017.",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)
SECOND = QuestionDraft(
    type="choice",
    title="Which preset?",
    options=[Option(id="daily", label="daily 262K", key="1"), Option(id="fast", label="fast 128K", key="2")],
)


async def test_the_questions_page_lists_every_waiting_question_and_answers_the_highlighted_one(
    client: Client, kernel: Kernel, home: Home
) -> None:
    kernel.questions.ask(FIRST, asked_by=CLANK)
    second = kernel.questions.ask(SECOND, asked_by=CLANK)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="questions")
    async with app.run_test(size=(120, 34)) as pilot:
        await settle(pilot, lambda: "Which preset?" in render_text(app))
        assert_frame(await frame_when(pilot, app, "Which preset?"), "questions")
        await focus_on(pilot, app, app.query_one("#questions-list", ListView), 1)
        await pilot.press("2")
        await settle(pilot, lambda: kernel.questions.get(second.id).answer is not None)
    answer = kernel.questions.get(second.id).answer
    assert answer is not None
    assert (answer.option, answer.by.via) == ("fast", "console")


async def test_a_click_on_another_questions_option_highlights_it_and_answers_it_the_list_keeping_the_focus(
    client: Client, kernel: Kernel, home: Home
) -> None:
    first = kernel.questions.ask(FIRST, asked_by=CLANK)
    second = kernel.questions.ask(SECOND, asked_by=CLANK)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="questions")
    async with app.run_test(size=(120, 34)) as pilot:
        await frame_when(pilot, app, "Which preset?")
        listed = app.query_one("#questions-list", ListView)
        await focus_on(pilot, app, listed, 0)
        groups = list(listed.query(Buttons).results(Buttons))
        assert [[each.label for each in group.buttons] for group in groups] == [["y", "n", "v"], ["1", "2", "v"]]
        assert not any(group.focusable for group in groups), "the list keeps the focus; its rows' buttons are clicked"
        await pilot.click(groups[1], offset=(len(" 1 daily 262K  2"), 0))
        await settle(pilot, lambda: kernel.questions.get(second.id).answer is not None)
        assert app.focused is listed
    answer = kernel.questions.get(second.id).answer
    assert answer is not None
    assert answer.option == "fast"
    assert kernel.questions.get(first.id).answer is None
