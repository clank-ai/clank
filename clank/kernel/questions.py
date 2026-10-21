"""Questions: the one way any part of Clank asks the user something and waits for the answer (design 0002 §2.5).

A question is an approval (may this happen?), a choice (one of these) or an answer in words (with suggested answers).
It says what it concerns and who asks, exactly what is at stake (its detail), each possible answer and what it does
(an option may ask for a number, with its bounds and unit, given as the answer's words: decision 0114),
and what happens if nobody answers in time. It is answered once, from any client: the answer records who gave it,
through which client, and when, and a second answer is refused with the first one's name. Asking, answering, expiring
and withdrawing are each an event. Questions live in the state database, so they survive a restart of the service; the
part that asked acts on the answer when it hears of it (`on_resolved`). The approval, choice or text of a question is
its `type`, because `kind` names the kind of record (principle 4).
"""

import json
import logging
import secrets
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clank.kernel.clock import Clock, from_text, to_text
from clank.kernel.events import Actor, EventLog, EventType, Subject
from clank.kernel.records import StateKind
from clank.kernel.store import Store

log = logging.getLogger(__name__)
EXPIRY = Actor(kind="clank", via="expiry")

EVENT_TYPES = [
    EventType(
        "question.asked",
        "Clank asks the user something and waits for the answer.",
        {"type": "approval, choice or text.", "title": "The question in one line.", "urgency": "normal or high."},
        attention=True,
    ),
    EventType(
        "question.answered",
        "The user answered a question, from one of the clients.",
        {"option": "The option chosen, if any.", "text": "The answer in words, if any."},
    ),
    EventType(
        "question.expired",
        "Nobody answered in time; Clank took the question's default.",
        {"option": "The default it took."},
    ),
    EventType(
        "question.withdrawn",
        "The part that asked no longer needs the answer.",
        {"reason": "Why."},
    ),
]


class Asked(BaseModel):
    """What an option needs besides being chosen (decision 0114): a number in a unit, within bounds, on a step; the
    shape every client reads, `{"kind": "number", "unit", "min", "max", "step"}`."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["number"] = Field(title="Kind", description="number: an amount, a count, a size.")
    unit: str = Field("", title="Unit", description="Its unit, such as USD.")
    min: float = Field(title="Least", description="The least it may be.")
    max: float = Field(title="Most", description="The most it may be.")
    step: float | None = Field(
        None, gt=0, title="Step", description="The least change it takes, such as 0.01; none: any."
    )

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if self.min > self.max:
            raise ValueError(f"the min {self.min:g} is above the max {self.max:g}")
        return self

    def problem(self, text: str) -> str | None:
        """What is wrong with an answer's words as this number, or None."""
        bounds = f"between {_number(self.min)} and {_number(self.max)}{' ' + self.unit if self.unit else ''}"
        try:
            value = float(text.strip().lstrip("$").replace(",", ""))
        except ValueError:
            return f"needs a number {bounds}"
        if not self.min <= value <= self.max:
            return f"needs a number {bounds}, not {text.strip()}"
        if self.step and abs(value / self.step - round(value / self.step)) > 1e-6:
            return f"needs a number {bounds} in steps of {self.step:g}, not {text.strip()}"
        return None


class Option(BaseModel):
    """One possible answer to a question, and what it does."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(title="Id", description="How the answer names this option, such as stop.")
    label: str = Field(title="Label", description="The option as clients show it.")
    effect: str = Field("", title="Effect", description="What choosing it does.")
    key: str = Field("", title="Key", description="The key that chooses it in the console, such as y.")
    asks: Asked | None = Field(
        None,
        title="Asks",
        description="What choosing it needs besides (decision 0114): a number, with its bounds and unit, given as the "
        "answer's words.",
    )


class QuestionDraft(BaseModel):
    """A question as the part that asks it writes it."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["approval", "choice", "text"] = Field(
        title="Type",
        description="approval: may this happen?; choice: one of these; text: an answer in words, with suggestions.",
    )
    title: str = Field(title="Title", description="The question in one line.")
    detail: str = Field(
        "", title="Detail", description="Exactly what is at stake: the command, the diff, the host, the reason."
    )
    options: list[Option] = Field(
        default_factory=list,
        title="Options",
        description="Each possible answer and what it does; for a text question, suggested answers.",
    )
    default: str | None = Field(None, title="Default", description="The option taken if nobody answers in time.")
    expires: datetime | None = Field(
        None, title="Expires", description="When the default is taken if nobody has answered."
    )
    urgency: Literal["normal", "high"] = Field(
        "normal", title="Urgency", description="How soon the user should see it; high ones reach the phone at once."
    )
    about: Subject | None = Field(None, title="About", description="The record the question concerns.")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("each option needs its own id")
        keys = [option.key for option in self.options if option.key]
        if repeated := sorted({key for key in keys if keys.count(key) > 1}):
            raise ValueError(f"the key {repeated[0]} chooses two options; each needs its own key")
        if self.type != "text" and len(ids) < 2:
            raise ValueError(f"an {self.type} question needs at least two options")
        if self.default is not None and self.default not in ids:
            raise ValueError(f"the default {self.default!r} is not one of the options")
        if self.expires is not None and self.default is None:
            raise ValueError("a question that expires needs a default")
        return self


class Answer(BaseModel):
    """How a question was answered: the option or the words, who answered, through which client, and when."""

    option: str | None = Field(None, title="Option", description="The option chosen; none for an answer in words.")
    text: str = Field("", title="Text", description="The answer in words, or a reason given with the option.")
    by: Actor = Field(title="By", description="Who answered, and through which client.")
    time: datetime = Field(title="Time", description="When.")


class Question(QuestionDraft, StateKind):
    """A question to the user, and its answer once there is one."""

    KIND = "question"
    LABEL = "Question"
    HELP = "Something Clank asks the user and waits for: an approval, a choice, or an answer in words."

    id: str = Field(title="Id", description="The question's name, such as q-7f3a91.")
    status: Literal["waiting", "answered", "expired", "withdrawn"] = Field(
        title="Status", description="waiting for an answer, answered, expired (its default taken), or withdrawn."
    )
    asked_by: Actor = Field(title="Asked by", description="Who asks.")
    asked: datetime = Field(title="Asked", description="When it was asked.")
    answer: Answer | None = Field(None, title="Answer", description="The answer, once there is one.")
    reason: str = Field("", title="Reason", description="Why it was withdrawn.")
    operation_id: str | None = Field(None, title="Operation", description="The operation waiting for the answer.")

    def option(self, id: str | None) -> Option | None:
        """The option of that id."""
        return next((option for option in self.options if option.id == id), None)


class QuestionError(Exception):
    """An answer or a change that a question refuses."""


Resolved = Callable[[Question], None]


class Questions:
    """The questions to the user, kept in the state database."""

    def __init__(self, store: Store, events: EventLog, clock: Clock) -> None:
        self._store = store
        self._events = events
        self._clock = clock
        self._listeners: list[Resolved] = []
        self._lock = threading.Lock()

    def ask(self, draft: QuestionDraft, *, asked_by: Actor, operation_id: str | None = None) -> Question:
        """Ask the user; the question waits for an answer from any client."""
        asked = self._clock.now()
        for _ in range(8):
            question = Question(
                **draft.model_dump(),
                id=f"q-{secrets.token_hex(3)}",
                status="waiting",
                asked_by=asked_by,
                asked=asked,
                operation_id=operation_id,
            )
            try:
                with self._store.transaction() as db:
                    db.execute(
                        "INSERT INTO questions (id, type, status, about_kind, about_id, asked_by, title, detail,"
                        " options, default_option, expires, urgency, asked, operation_id)"
                        " VALUES (?, ?, 'waiting', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            question.id,
                            question.type,
                            question.about.kind if question.about else None,
                            question.about.id if question.about else None,
                            asked_by.model_dump_json(),
                            question.title,
                            question.detail,
                            json.dumps([option.model_dump() for option in question.options], ensure_ascii=False),
                            question.default,
                            to_text(question.expires) if question.expires else None,
                            question.urgency,
                            to_text(asked),
                            operation_id,
                        ),
                    )
                    self._events.record(
                        "question.asked",
                        summary=f"{asked_by.describe()} asks: {question.title}",
                        actor=asked_by,
                        subject=_subject(question.id),
                        data={"type": question.type, "title": question.title, "urgency": question.urgency},
                    )
                return question
            except sqlite3.IntegrityError:
                continue
        raise QuestionError("could not find a free question id")

    def answer(self, id: str, *, by: Actor, option: str | None = None, text: str = "") -> Question:
        """Answer a waiting question, once."""
        with self._store.transaction():
            question = self.get(id)
            if question.status != "waiting":
                raise QuestionError(self._settled(question))
            chosen = question.option(option)
            if question.type != "text" and chosen is None:
                raise QuestionError(f"{id} needs one of: {', '.join(o.id for o in question.options)}")
            if question.type == "text" and option is not None and chosen is None:
                raise QuestionError(f"{id} suggests only: {', '.join(o.id for o in question.options)}")
            if question.type == "text" and chosen is None and not text.strip():
                raise QuestionError(f"{id} needs an answer in words, or one of its suggestions")
            if chosen is not None and chosen.asks is not None and (wrong := chosen.asks.problem(text)):
                raise QuestionError(f"{chosen.label} {wrong}")
            answer = Answer(option=option, text=text, by=by, time=self._clock.now())
            settled = self._settle(question, "answered", answer=answer)
            shown = chosen.label if chosen is not None else text
            self._events.record(
                "question.answered",
                summary=f"{by.describe()} answered {id}: {shown}",
                actor=by,
                subject=_subject(id),
                data={"option": option, "text": text},
            )
        return settled

    def withdraw(self, id: str, *, reason: str, by: Actor) -> Question:
        """Withdraw a waiting question: its answer is no longer needed."""
        with self._store.transaction():
            question = self.get(id)
            if question.status != "waiting":
                raise QuestionError(self._settled(question))
            settled = self._settle(question, "withdrawn", reason=reason)
            self._events.record(
                "question.withdrawn",
                summary=f"{id} was withdrawn: {reason}",
                actor=by,
                subject=_subject(id),
                data={"reason": reason},
            )
        return settled

    def expire_due(self) -> list[Question]:
        """Settle every waiting question whose time is up with its default; returns them."""
        now = self._clock.now()
        rows = self._store.read(
            "SELECT id FROM questions WHERE status = 'waiting' AND expires IS NOT NULL AND expires <= ? ORDER BY asked",
            (to_text(now),),
        )
        expired = []
        for row in rows:
            with self._store.transaction():
                question = self.get(row["id"])
                if question.status != "waiting":
                    continue
                answer = Answer(option=question.default, by=EXPIRY, time=now)
                settled = self._settle(question, "expired", answer=answer)
                default = question.option(question.default)
                self._events.record(
                    "question.expired",
                    summary=f"{question.id} was not answered in time; Clank took its default: "
                    f"{default.label if default else question.default}",
                    actor=EXPIRY,
                    subject=_subject(question.id),
                    data={"option": question.default},
                )
            expired.append(settled)
        return expired

    def get(self, id: str) -> Question:
        """One question."""
        rows = self._store.read("SELECT * FROM questions WHERE id = ?", (id,))
        if not rows:
            raise QuestionError(f"there is no question {id}")
        return _question(rows[0])

    def waiting(self) -> list[Question]:
        """The questions waiting for an answer, oldest first."""
        return [
            _question(r) for r in self._store.read("SELECT * FROM questions WHERE status = 'waiting' ORDER BY asked")
        ]

    def find(self, status: str | None = None, limit: int = 100) -> list[Question]:
        """The newest questions, optionally of one status."""
        if status is None:
            rows = self._store.read("SELECT * FROM questions ORDER BY asked DESC LIMIT ?", (limit,))
        else:
            rows = self._store.read(
                "SELECT * FROM questions WHERE status = ? ORDER BY asked DESC LIMIT ?", (status, limit)
            )
        return [_question(row) for row in rows]

    def on_resolved(self, listener: Resolved) -> Callable[[], None]:
        """Hear every question once it is answered, expired or withdrawn; returns the function that stops it."""
        with self._lock:
            self._listeners.append(listener)

        def stop() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return stop

    def _settle(self, question: Question, status: str, *, answer: Answer | None = None, reason: str = "") -> Question:
        with self._store.transaction() as db:
            db.execute(
                "UPDATE questions SET status = ?, answer = ?, reason = ? WHERE id = ?",
                (status, answer.model_dump_json() if answer else None, reason, question.id),
            )
            settled = question.model_copy(update={"status": status, "answer": answer, "reason": reason})
            self._store.after_commit(lambda: self._tell(settled))
        return settled

    def _tell(self, question: Question) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(question)
            except Exception:
                log.exception("a listener failed on question %s", question.id)

    @staticmethod
    def _settled(question: Question) -> str:
        if question.status == "answered" and question.answer is not None:
            shown = question.option(question.answer.option)
            what = shown.label if shown else question.answer.text
            return (
                f"{question.id} was already answered by {question.answer.by.describe()} "
                f"at {to_text(question.answer.time)}: {what}"
            )
        if question.status == "expired":
            return f"{question.id} expired; Clank took its default"
        return f"{question.id} was withdrawn: {question.reason}"


def _subject(id: str) -> Subject:
    return Subject(kind="question", id=id)


def _number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _question(row: Any) -> Question:
    about = Subject(kind=row["about_kind"], id=row["about_id"]) if row["about_kind"] else None
    return Question(
        id=row["id"],
        type=row["type"],
        status=row["status"],
        about=about,
        asked_by=Actor.model_validate_json(row["asked_by"]),
        title=row["title"],
        detail=row["detail"],
        options=[Option.model_validate(option) for option in json.loads(row["options"])],
        default=row["default_option"],
        expires=from_text(row["expires"]) if row["expires"] else None,
        urgency=row["urgency"],
        asked=from_text(row["asked"]),
        answer=Answer.model_validate_json(row["answer"]) if row["answer"] else None,
        reason=row["reason"],
        operation_id=row["operation_id"],
    )
