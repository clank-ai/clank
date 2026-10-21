"""Design 0002 §2.5 (decision 0114): a question's option may ask for a number, with its unit, its bounds and its step
(`{"kind": "number", "unit", "min", "max", "step"}`, the shape every client reads), so every client answers it the same
way; an answer of that option takes a number within the bounds, on the step, and one without a number, with a word, out
of bounds or off the step is refused before anyone hears of it, saying the bounds and the unit; the question keeps the
declaration, and the answer the number."""

import pytest
from pydantic import ValidationError

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, EventLog
from clank.kernel.questions import Asked, Option, QuestionDraft, QuestionError, Questions
from clank.kernel.store import Store

PHONE = Actor(kind="device", via="phone")
CLANK = Actor(kind="clank", via="gateway")
LIMIT = QuestionDraft(
    type="choice",
    title="Cloud spending reached today's limit of $5.00 ($5.02 spent): raise it?",
    options=[
        Option(id="double", label="Raise today's limit to $10.00", key="y"),
        Option(
            id="raise",
            label="Raise it to …",
            key="r",
            asks=Asked(kind="number", unit="USD", min=5.02, max=100000, step=0.01),
        ),
        Option(id="keep", label="Keep the cloud paused", key="n"),
    ],
    default="keep",
)


@pytest.fixture
def questions(store: Store, clock: FakeClock) -> Questions:
    return Questions(store, EventLog(store, clock, registry.event_types()), clock)


def test_an_option_that_asks_a_number_takes_one_within_its_bounds(questions: Questions) -> None:
    asked = questions.ask(LIMIT, asked_by=CLANK)
    kept = questions.get(asked.id)
    raising = kept.option("raise")
    assert raising is not None
    assert raising.asks is not None
    assert raising.asks.model_dump() == {"kind": "number", "unit": "USD", "min": 5.02, "max": 100000, "step": 0.01}
    answered = questions.answer(asked.id, by=PHONE, option="raise", text="12.50")
    assert answered.answer is not None
    assert (answered.answer.option, answered.answer.text) == ("raise", "12.50")


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("", "needs a number"),
        ("twelve", "needs a number"),
        ("4.99", "between 5.02 and 100,000 USD"),
        ("100001", "between 5.02 and 100,000 USD"),
        ("12.505", "in steps of 0.01"),
    ],
)
def test_an_answer_without_a_number_in_bounds_is_refused_saying_them(
    questions: Questions, text: str, words: str
) -> None:
    asked = questions.ask(LIMIT, asked_by=CLANK)
    with pytest.raises(QuestionError, match=words):
        questions.answer(asked.id, by=PHONE, option="raise", text=text)
    assert questions.get(asked.id).status == "waiting"
    assert questions.answer(asked.id, by=PHONE, option="keep").status == "answered", "the others need no number"


def test_a_number_asked_needs_bounds_and_a_step_that_make_sense() -> None:
    with pytest.raises(ValidationError, match="min"):
        Asked(kind="number", unit="USD", min=10, max=1)
    with pytest.raises(ValidationError, match="step"):
        Asked(kind="number", unit="USD", min=1, max=10, step=0)
    assert Asked(kind="number", min=1, max=10).problem("3.14159") is None, "without a step, any number in bounds"
