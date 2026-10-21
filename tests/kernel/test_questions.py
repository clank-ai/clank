"""Design 0002 §2.5: a question is answered once, from any client, with who answered, through which client and when;
it takes its default when its time is up, can be withdrawn, survives a restart, and each step is an event."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, EventLog, Subject
from clank.kernel.home import Home
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError, Questions
from clank.kernel.store import Store

CONSOLE = Actor(kind="user", via="console")
VSCODE = Actor(kind="user", via="vscode")
DOCKER = Actor(kind="clank", via="docker.stop")
STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    detail="2 containers that Clank did not start are running: another-model-relay, toolbox-sandbox-017.",
    options=[
        Option(id="stop", label="Stop them and Docker", effect="Docker Desktop stops.", key="y"),
        Option(id="cancel", label="Cancel", effect="Nothing changes.", key="n"),
    ],
    default="cancel",
)
NAME = QuestionDraft(
    type="text",
    title="What should the new preset be called?",
    options=[Option(id="daily", label="daily 262K")],
)


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, registry.event_types())


@pytest.fixture
def questions(store: Store, log: EventLog, clock: FakeClock) -> Questions:
    return Questions(store, log, clock)


def test_asking_records_the_question_and_announces_it(questions: Questions, log: EventLog) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    assert asked.id.startswith("q-")
    assert (asked.status, asked.type, asked.answer) == ("waiting", "approval", None)
    assert questions.waiting() == [asked]
    [event] = log.after(0, types=["question.asked"])
    assert event.subject == Subject(kind="question", id=asked.id)
    assert event.summary == "Clank (docker.stop) asks: Stop Docker Desktop?"


def test_an_answer_records_who_gave_it_through_which_client_and_when(
    questions: Questions, log: EventLog, clock: FakeClock
) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    clock.advance(60)
    answered = questions.answer(asked.id, by=VSCODE, option="stop")
    assert answered.status == "answered"
    assert answered.answer is not None
    assert (answered.answer.option, answered.answer.by, answered.answer.time) == ("stop", VSCODE, clock.now())
    assert questions.waiting() == []
    [event] = log.after(0, types=["question.answered"])
    assert event.summary == f"you (vscode) answered {asked.id}: Stop them and Docker"


def test_a_second_answer_is_refused_naming_the_first(questions: Questions) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    questions.answer(asked.id, by=VSCODE, option="stop")
    with pytest.raises(QuestionError, match=r"already answered by you \(vscode\)"):
        questions.answer(asked.id, by=CONSOLE, option="cancel")


def test_an_answer_must_be_one_of_the_options(questions: Questions) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    with pytest.raises(QuestionError, match="stop, cancel"):
        questions.answer(asked.id, by=CONSOLE, option="maybe")


def test_a_text_question_needs_words_or_one_of_its_suggestions(questions: Questions) -> None:
    asked = questions.ask(NAME, asked_by=DOCKER)
    with pytest.raises(QuestionError, match="in words"):
        questions.answer(asked.id, by=CONSOLE, text="  ")
    answered = questions.answer(asked.id, by=CONSOLE, text="fast 128K")
    assert answered.answer is not None
    assert answered.answer.text == "fast 128K"
    suggested = questions.answer(questions.ask(NAME, asked_by=DOCKER).id, by=CONSOLE, option="daily")
    assert suggested.answer is not None
    assert suggested.answer.option == "daily"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"options": [Option(id="ok", label="OK")]}, "at least two options"),
        ({"default": "later"}, "not one of the options"),
        ({"default": None, "expires": datetime(2026, 10, 11, 12, 30, tzinfo=UTC)}, "needs a default"),
        (
            {"options": [Option(id="stop", label="Stop", key="y"), Option(id="cancel", label="Cancel", key="y")]},
            "the key y chooses two options",
        ),
    ],
)
def test_a_draft_without_enough_options_or_with_a_default_that_is_not_an_option_is_refused(
    changes: dict[str, object], expected: str
) -> None:
    with pytest.raises(ValidationError, match=expected):
        QuestionDraft.model_validate({**STOP.model_dump(), **changes})


def test_a_question_whose_time_is_up_takes_its_default_and_says_so(
    questions: Questions, log: EventLog, clock: FakeClock
) -> None:
    asked = questions.ask(STOP.model_copy(update={"expires": clock.now() + timedelta(minutes=30)}), asked_by=DOCKER)
    assert questions.expire_due() == []
    clock.advance(timedelta(minutes=31).total_seconds())
    [expired] = questions.expire_due()
    assert expired.id == asked.id
    assert expired.status == "expired"
    assert expired.answer is not None
    assert expired.answer.option == "cancel"
    [event] = log.after(0, types=["question.expired"])
    assert event.summary == f"{asked.id} was not answered in time; Clank took its default: Cancel"


def test_a_withdrawn_question_cannot_be_answered(questions: Questions) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    questions.withdraw(asked.id, reason="Docker stopped by itself", by=DOCKER)
    with pytest.raises(QuestionError, match="withdrawn: Docker stopped by itself"):
        questions.answer(asked.id, by=CONSOLE, option="stop")


def test_questions_survive_reopening_the_database(questions: Questions, home: Home, clock: FakeClock) -> None:
    asked = questions.ask(STOP, asked_by=DOCKER)
    reopened = Store(home.database)
    try:
        again = Questions(reopened, EventLog(reopened, clock, registry.event_types()), clock)
        assert again.get(asked.id) == asked
    finally:
        reopened.close()


def test_listeners_hear_an_answer_after_it_is_recorded(questions: Questions) -> None:
    heard: list[Question] = []
    questions.on_resolved(heard.append)
    asked = questions.ask(STOP, asked_by=DOCKER)
    questions.answer(asked.id, by=CONSOLE, option="cancel")
    assert [(question.id, question.status) for question in heard] == [(asked.id, "answered")]
