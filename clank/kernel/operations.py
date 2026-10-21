"""Operations: anything that takes more than a moment runs in the service as an operation (design 0002 §2.4).

A switch, a trial, a build, a download, a doctor run: each is a record with its status (queued, running, waiting for the
user, done, failed, canceled, interrupted), its steps and progress, its log, its result and who started it. Operations
run in the service, never in a client, so closing a client stops nothing and every client sees the same progress. Each
kind of operation declares its steps and which of them are safe to run again. Each step is recorded when it starts and
when it ends. An operation that needs something another one holds (a lock) is refused, naming the first and who started
it. A request that carries a key starts at most one operation, however often it is sent. An operation can wait for the
user's answer to a question (`OperationContext.ask`); the answer may come from any client, on any thread. When the
service stops, the operations in flight are left as they are; at the next start `recover` marks them interrupted,
withdraws their open questions, and lets each kind check what actually happened. An interrupted operation is tried
again only by asking (`retry`), and never when a step that is not safe to repeat had started.
"""

import json
import secrets
import sqlite3
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeVar

import anyio
import anyio.from_thread
import anyio.lowlevel
from anyio.abc import TaskGroup
from pydantic import BaseModel, Field
from pydantic_core import to_jsonable_python

from clank.kernel.clock import Clock, from_text, to_text
from clank.kernel.events import CLANK, Actor, EventLog, EventType, Subject
from clank.kernel.questions import Answer, Question, QuestionDraft, QuestionError, Questions
from clank.kernel.records import StateKind
from clank.kernel.store import Store

T = TypeVar("T")
Status = Literal["queued", "running", "waiting", "done", "failed", "canceled", "interrupted"]
UNFINISHED = ("queued", "running", "waiting")

EVENT_TYPES = [
    EventType("operation.started", "An operation started.", {"type": "The kind of operation.", "title": "Its title."}),
    EventType(
        "operation.step",
        "A step of an operation started or ended.",
        {
            "number": "The step's number.",
            "name": "The step's name.",
            "status": "running, done or failed.",
            "of": "How many steps the operation has.",
        },
    ),
    EventType(
        "operation.waiting",
        "An operation waits for the user's answer to a question.",
        {"question": "The question's id."},
    ),
    EventType(
        "operation.resumed",
        "An operation goes on after the user's answer.",
        {"question": "The question's id.", "answer": "The option taken."},
    ),
    EventType(
        "operation.log",
        "A line of an operation's log, as it is written.",
        {"text": "The line.", "step": "The number of the step that wrote it, if any."},
        live=True,
    ),
    EventType(
        "operation.finished",
        "An operation ended: done, failed or canceled.",
        {"status": "done, failed or canceled.", "error": "What went wrong, if it did.", "result": "Its result."},
    ),
    EventType(
        "operation.interrupted",
        "An operation was cut short by a stop of the service; it is not repeated on its own.",
        {"last_step": "The step it was in."},
    ),
    EventType(
        "operation.reconciled",
        "After a restart, an interrupted operation's kind checked what actually happened.",
        {"note": "What it found."},
    ),
]


class Step(BaseModel):
    """One step of an operation, as it ran."""

    number: int = Field(title="Number", description="Its place among the operation's steps, from 1.")
    name: str = Field(title="Name", description="What the step does, such as stop.")
    status: Literal["running", "done", "failed", "canceled"] = Field(
        title="Status", description="running, done, failed, or canceled (cut short by a cancel)."
    )
    repeatable: bool = Field(title="Safe to repeat", description="Whether running it again could do harm.")
    started: datetime = Field(title="Started", description="When it started.")
    finished: datetime | None = Field(None, title="Finished", description="When it ended.")
    detail: str = Field("", title="Detail", description="Why it failed, when it did.")


class Operation(StateKind):
    """Something slow that runs in the service, step by step."""

    KIND = "operation"
    LABEL = "Operation"
    HELP = "Something that takes more than a moment, run by the service step by step: a switch, a download, a check."

    id: str = Field(title="Id", description="The operation's name, such as op-1f2e3d4c.")
    type: str = Field(title="Type", description="The kind of operation, such as docker.stop.")
    title: str = Field(title="Title", description="What it does, in a few words.")
    status: Status = Field(
        title="Status", description="queued, running, waiting (for the user), done, failed, canceled or interrupted."
    )
    started_by: Actor = Field(title="Started by", description="Who started it, and through which client.")
    created: datetime = Field(title="Created", description="When it was started.")
    updated: datetime = Field(title="Updated", description="When it last changed.")
    finished: datetime | None = Field(None, title="Finished", description="When it ended.")
    cancelable: bool = Field(title="Can be canceled", description="Whether the user can stop it while it runs.")
    params: dict[str, Any] = Field(default_factory=dict, title="Parameters", description="What it was asked to do.")
    result: dict[str, Any] | None = Field(None, title="Result", description="What it produced, once done.")
    error: str = Field("", title="Error", description="Why it failed, was canceled, or was interrupted.")
    request_key: str | None = Field(
        None, title="Request key", description="The key of the request that started it; the same key starts no other."
    )
    locks: list[str] = Field(default_factory=list, title="Locks", description="What it holds while it runs.")
    waiting_on: str | None = Field(None, title="Waiting on", description="The question it waits for, if any.")
    planned_steps: int = Field(title="Steps planned", description="How many steps its kind declares.")
    steps: list[Step] = Field(default_factory=list, title="Steps", description="The steps it has run so far.")
    retry_of: str | None = Field(None, title="Retry of", description="The operation it tries again, if any.")

    def progress(self) -> str:
        """How far it is: "2 of 3: stop"."""
        if not self.steps:
            return f"0 of {self.planned_steps}"
        last = self.steps[-1]
        return f"{last.number} of {self.planned_steps}: {last.name}"


class LogLine(BaseModel):
    """One line of an operation's log."""

    number: int = Field(title="Number", description="Its place in the log, from 1.")
    step: int | None = Field(None, title="Step", description="The number of the step that wrote it, if any.")
    time: datetime = Field(title="Time", description="When it was written.")
    text: str = Field(title="Text", description="What it says.")


@dataclass(frozen=True)
class StepSpec:
    """A step a kind of operation declares, and whether it is safe to run again."""

    name: str
    repeatable: bool = True


@dataclass(frozen=True)
class Reconciliation:
    """What a kind of operation found when it checked, after a restart, what actually happened."""

    note: str


def _no_locks(params: Mapping[str, Any]) -> Sequence[str]:
    return ()


Run = Callable[["OperationContext"], Awaitable[Mapping[str, Any] | None]]
Reconcile = Callable[[Operation], Awaitable[Reconciliation]]


@dataclass(frozen=True)
class OperationType:
    """A kind of operation: its steps, how to run it, how to check after a restart, what it locks."""

    name: str
    title: str
    steps: tuple[StepSpec, ...]
    run: Run
    reconcile: Reconcile | None = None
    cancelable: bool = True
    locks: Callable[[Mapping[str, Any]], Sequence[str]] = _no_locks
    owner: str = "kernel"


class OperationError(Exception):
    """An operation that cannot be started, canceled or tried again as asked."""


class Busy(OperationError):
    """Something the operation needs is held by another one."""


class Canceled(Exception):
    """The operation was canceled: raised inside it at its next check, or by the operation itself with the reason it
    shows (an answer of cancel)."""


class OperationContext:
    """What a running operation uses: its parameters, its steps, its log, questions to the user, cancellation."""

    def __init__(self, operations: "Operations", operation: Operation, kind: OperationType) -> None:
        self._operations = operations
        self._operation = operation
        self._kind = kind
        self._step: int | None = None

    @property
    def id(self) -> str:
        """The operation's id."""
        return self._operation.id

    @property
    def params(self) -> Mapping[str, Any]:
        """What it was asked to do."""
        return self._operation.params

    @property
    def actor(self) -> Actor:
        """Who started it."""
        return self._operation.started_by

    @asynccontextmanager
    async def step(self, name: str) -> AsyncIterator[None]:
        """Run one declared step, recording its start and its end (or its failure)."""
        numbers = {spec.name: number for number, spec in enumerate(self._kind.steps, start=1)}
        if name not in numbers:
            raise OperationError(f"{self._kind.name} declares no step named {name!r}")
        self.check_canceled()
        spec = self._kind.steps[numbers[name] - 1]
        self._operations._step_started(self._operation, numbers[name], name, spec.repeatable)
        self._step = numbers[name]
        try:
            yield
        except Canceled as stopped:
            reason = self._operations._cancel_reason(self._operation.id, stopped)
            self._operations._step_ended(self._operation, numbers[name], name, "canceled", reason)
            raise
        except Exception as error:
            self._operations._step_ended(
                self._operation, numbers[name], name, "failed", str(error) or type(error).__name__
            )
            raise
        finally:
            self._step = None
        self._operations._step_ended(self._operation, numbers[name], name, "done")

    def log(self, text: str) -> None:
        """Add a line to the operation's log, under the step that writes it; clients see it as it is written."""
        self._operations._log(self._operation, text, self._step)

    async def ask(self, draft: QuestionDraft) -> Answer:
        """Ask the user and wait for the answer (or the question's default, if it expires)."""
        self.check_canceled()
        return await self._operations._ask(self._operation, draft)

    def check_canceled(self) -> None:
        """Raise `Canceled` if the user canceled the operation."""
        if self._operations._is_canceled(self._operation.id):
            raise Canceled()

    async def run_blocking(self, function: Callable[..., T], *args: Any) -> T:
        """Run a slow, blocking call (a command, a file copy) off the service's event loop."""
        return await anyio.to_thread.run_sync(function, *args)


class Operations:
    """The operations of the service: started, followed, canceled, recovered after a restart."""

    def __init__(
        self, store: Store, events: EventLog, questions: Questions, clock: Clock, types: Iterable[OperationType]
    ) -> None:
        self._store = store
        self._events = events
        self._questions = questions
        self._clock = clock
        self._types = {kind.name: kind for kind in types}
        self._lock = threading.Lock()
        self._held: dict[str, str] = {}
        self._canceled: dict[str, Actor] = {}
        self._waiting: dict[str, anyio.Event] = {}
        self._done: dict[str, anyio.Event] = {}
        self._group: TaskGroup | None = None
        self._token: Any = None
        self._loop_thread: int | None = None
        questions.on_resolved(self._resolved)

    def add_type(self, kind: OperationType) -> None:
        """Declare one more kind of operation (a component's); a name declared twice is refused."""
        if kind.name in self._types:
            raise OperationError(f"the kind of operation {kind.name!r} is declared twice")
        self._types[kind.name] = kind

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Run operations while the block lasts; leaving it stops those still in flight, as a stop of the service."""
        async with anyio.create_task_group() as group:
            self._group = group
            self._token = anyio.lowlevel.current_token()
            self._loop_thread = threading.get_ident()
            try:
                yield
            finally:
                group.cancel_scope.cancel()
                self._group = None

    async def start(
        self,
        type: str,
        params: Mapping[str, Any] | None = None,
        *,
        actor: Actor,
        request_key: str | None = None,
        retry_of: str | None = None,
    ) -> Operation:
        """Start an operation; the same request key returns the one already started."""
        kind = self._types.get(type)
        if kind is None:
            raise OperationError(f"there is no kind of operation named {type!r}")
        if self._group is None:
            raise OperationError("operations are not running (the service runs them)")
        if request_key is not None:
            rows = self._store.read("SELECT id FROM operations WHERE request_key = ?", (request_key,))
            if rows:
                return self.get(rows[0]["id"])
        values = to_jsonable_python(dict(params or {}))
        names = list(kind.locks(values))
        with self._lock:
            for name in names:
                holder = self._held.get(name)
                if holder is not None:
                    first = self.get(holder)
                    raise Busy(
                        f"{name} is in use by {first.title} ({first.id}), started by {first.started_by.describe()}"
                    )
            operation = self._insert(kind, values, actor, request_key, names, retry_of)
            for name in names:
                self._held[name] = operation.id
            self._done[operation.id] = anyio.Event()
        self._group.start_soon(self._run, operation.id, kind)
        return operation

    async def wait(self, id: str) -> Operation:
        """Wait until an operation ends; returns it."""
        done = self._done.get(id)
        if done is not None:
            await done.wait()
        return self.get(id)

    def get(self, id: str) -> Operation:
        """One operation, with its steps."""
        rows = self._store.read("SELECT * FROM operations WHERE id = ?", (id,))
        if not rows:
            raise OperationError(f"there is no operation {id}")
        steps = self._store.read("SELECT * FROM operation_steps WHERE operation_id = ? ORDER BY number", (id,))
        return _operation(rows[0], steps)

    def find(self, status: str | None = None, limit: int = 50) -> list[Operation]:
        """The newest operations, optionally of one status."""
        if status is None:
            rows = self._store.read("SELECT id FROM operations ORDER BY created DESC LIMIT ?", (limit,))
        else:
            rows = self._store.read(
                "SELECT id FROM operations WHERE status = ? ORDER BY created DESC LIMIT ?", (status, limit)
            )
        return [self.get(row["id"]) for row in rows]

    def log_lines(self, id: str, after: int = 0) -> list[LogLine]:
        """An operation's log, from the line after `after` on."""
        self.get(id)
        rows = self._store.read(
            "SELECT number, step, time, text FROM operation_log WHERE operation_id = ? AND number > ? ORDER BY number",
            (id, after),
        )
        return [
            LogLine(number=row["number"], step=row["step"], time=from_text(row["time"]), text=row["text"])
            for row in rows
        ]

    async def cancel(self, id: str, *, actor: Actor) -> Operation:
        """Ask a running operation to stop at its next check (and withdraw the question it waits for)."""
        operation = self.get(id)
        if operation.status not in UNFINISHED:
            raise OperationError(f"{operation.title} ({id}) has already ended: {operation.status}")
        if not operation.cancelable:
            raise OperationError(f"{operation.title} ({id}) cannot be canceled once it has started")
        with self._lock:
            self._canceled[id] = actor
        if operation.waiting_on is not None:
            with suppress(QuestionError):
                self._questions.withdraw(
                    operation.waiting_on, reason=f"the operation was canceled by {actor.describe()}", by=actor
                )
        return self.get(id)

    async def recover(self) -> list[Operation]:
        """At the service's start: mark the operations it left unfinished as interrupted, and reconcile each."""
        rows = self._store.read(
            "SELECT id FROM operations WHERE status IN ('queued', 'running', 'waiting') ORDER BY created"
        )
        interrupted = []
        for row in rows:
            operation = self.get(row["id"])
            last = operation.steps[-1].name if operation.steps else None
            now = to_text(self._clock.now())
            with self._store.transaction() as db:
                db.execute(
                    "UPDATE operations SET status = 'interrupted', updated = ?, finished = ?, error = ?, "
                    "waiting_on = NULL WHERE id = ?",
                    (now, now, "the service stopped while it ran", operation.id),
                )
                self._events.record(
                    "operation.interrupted",
                    summary=f"{operation.title} was interrupted by a stop of the service"
                    + (f" (in the step {last})" if last else ""),
                    actor=CLANK,
                    subject=_subject(operation.id),
                    data={"last_step": last},
                )
            if operation.waiting_on is not None:
                with suppress(QuestionError):
                    self._questions.withdraw(
                        operation.waiting_on,
                        reason="the service restarted; the operation that asked was interrupted",
                        by=CLANK,
                    )
            note = await self._reconcile(operation)
            self._events.record(
                "operation.reconciled",
                summary=f"{operation.title}: {note}",
                actor=CLANK,
                subject=_subject(operation.id),
                data={"note": note},
            )
            interrupted.append(self.get(operation.id))
        return interrupted

    async def retry(self, id: str, *, actor: Actor) -> Operation:
        """Start an interrupted or failed operation again, when every step it had started is safe to repeat."""
        operation = self.get(id)
        if operation.status not in ("interrupted", "failed"):
            raise OperationError(f"only an interrupted or failed operation is tried again; {id} is {operation.status}")
        unsafe = [step.name for step in operation.steps if not step.repeatable]
        if unsafe:
            raise OperationError(
                f"{operation.title} ({id}) cannot simply be tried again: "
                f"the step {unsafe[0]} had started and is not safe to run again"
            )
        return await self.start(operation.type, operation.params, actor=actor, retry_of=id)

    async def _reconcile(self, operation: Operation) -> str:
        kind = self._types.get(operation.type)
        if kind is None:
            return "this kind of operation is no longer known to Clank"
        if kind.reconcile is None:
            return "this kind of operation cannot check what it did; look before trying it again"
        try:
            return (await kind.reconcile(operation)).note
        except Exception as error:
            return f"checking what happened failed: {error}"

    def _insert(
        self,
        kind: OperationType,
        params: dict[str, Any],
        actor: Actor,
        request_key: str | None,
        locks: list[str],
        retry_of: str | None,
    ) -> Operation:
        now = self._clock.now()
        for _ in range(8):
            operation = Operation(
                id=f"op-{secrets.token_hex(4)}",
                type=kind.name,
                title=kind.title,
                status="running",
                started_by=actor,
                created=now,
                updated=now,
                cancelable=kind.cancelable,
                params=params,
                request_key=request_key,
                locks=locks,
                planned_steps=len(kind.steps),
                retry_of=retry_of,
            )
            try:
                with self._store.transaction() as db:
                    db.execute(
                        "INSERT INTO operations (id, type, title, status, started_by, created, updated, cancelable,"
                        " params, request_key, locks, planned_steps, retry_of)"
                        " VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation.id,
                            kind.name,
                            kind.title,
                            actor.model_dump_json(),
                            to_text(now),
                            to_text(now),
                            int(kind.cancelable),
                            json.dumps(params, ensure_ascii=False),
                            request_key,
                            json.dumps(locks),
                            len(kind.steps),
                            retry_of,
                        ),
                    )
                    self._events.record(
                        "operation.started",
                        summary=f"{actor.describe()} started {kind.title}",
                        actor=actor,
                        subject=_subject(operation.id),
                        data={"type": kind.name, "title": kind.title},
                    )
                return operation
            except sqlite3.IntegrityError:
                if request_key is not None:
                    raise
                continue
        raise OperationError("could not find a free operation id")

    async def _run(self, id: str, kind: OperationType) -> None:
        operation = self.get(id)
        context = OperationContext(self, operation, kind)
        try:
            result = await kind.run(context)
        except Canceled as stopped:
            self._finish(operation, "canceled", error=self._cancel_reason(id, stopped))
        except anyio.get_cancelled_exc_class():  # spelling: keep (AnyIO's own name)
            raise
        except Exception as error:
            self._finish(operation, "failed", error=str(error) or type(error).__name__)
        else:
            self._finish(operation, "done", result=dict(result) if result else {})
        finally:
            with self._lock:
                for name in operation.locks:
                    if self._held.get(name) == id:
                        del self._held[name]
                self._canceled.pop(id, None)
                done = self._done.pop(id, None)
            if done is not None:
                done.set()

    def _cancel_reason(self, id: str, stopped: Canceled) -> str:
        by = self._canceled.get(id)
        return str(stopped) or (f"canceled by {by.describe()}" if by else "canceled")

    def _finish(
        self, operation: Operation, status: Status, *, result: dict[str, Any] | None = None, error: str = ""
    ) -> None:
        now = to_text(self._clock.now())
        if status == "done":
            summary = f"{operation.title}: done"
        elif status == "failed":
            summary = f"{operation.title} failed: {error}"
        else:
            summary = f"{operation.title} was {error}"
        with self._store.transaction() as db:
            db.execute(
                "UPDATE operations SET status = ?, updated = ?, finished = ?, result = ?, error = ?, waiting_on = NULL"
                " WHERE id = ?",
                (
                    status,
                    now,
                    now,
                    json.dumps(to_jsonable_python(result)) if result is not None else None,
                    error,
                    operation.id,
                ),
            )
            self._events.record(
                "operation.finished",
                summary=summary,
                actor=Actor(kind="clank", via=operation.type),
                subject=_subject(operation.id),
                data={"status": status, "error": error, "result": result},
            )

    def _step_started(self, operation: Operation, number: int, name: str, repeatable: bool) -> None:
        now = to_text(self._clock.now())
        with self._store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO operation_steps (operation_id, number, name, status, repeatable, started)"
                " VALUES (?, ?, ?, 'running', ?, ?)",
                (operation.id, number, name, int(repeatable), now),
            )
            db.execute("UPDATE operations SET updated = ? WHERE id = ?", (now, operation.id))
            self._step_event(operation, number, name, "running")

    def _step_ended(self, operation: Operation, number: int, name: str, status: str, detail: str = "") -> None:
        now = to_text(self._clock.now())
        with self._store.transaction() as db:
            db.execute(
                "UPDATE operation_steps SET status = ?, finished = ?, detail = ? WHERE operation_id = ? AND number = ?",
                (status, now, detail, operation.id, number),
            )
            db.execute("UPDATE operations SET updated = ? WHERE id = ?", (now, operation.id))
            self._step_event(operation, number, name, status)

    def _step_event(self, operation: Operation, number: int, name: str, status: str) -> None:
        shown = "started" if status == "running" else status
        self._events.record(
            "operation.step",
            summary=f"{operation.title}: step {number} of {operation.planned_steps}, {name}: {shown}",
            actor=Actor(kind="clank", via=operation.type),
            subject=_subject(operation.id),
            data={"number": number, "name": name, "status": status, "of": operation.planned_steps},
        )

    def _log(self, operation: Operation, text: str, step: int | None) -> None:
        with self._store.transaction() as db:
            db.execute(
                "INSERT INTO operation_log (operation_id, number, step, time, text) VALUES (?,"
                " (SELECT COALESCE(MAX(number), 0) + 1 FROM operation_log WHERE operation_id = ?), ?, ?, ?)",
                (operation.id, operation.id, step, to_text(self._clock.now()), text),
            )
        self._events.publish_live(
            "operation.log",
            summary=text,
            actor=Actor(kind="clank", via=operation.type),
            subject=_subject(operation.id),
            data={"text": text, "step": step},
        )

    async def _ask(self, operation: Operation, draft: QuestionDraft) -> Answer:
        waiter = anyio.Event()
        with self._lock:
            self._waiting[operation.id] = waiter
        try:
            question = self._questions.ask(
                draft, asked_by=Actor(kind="clank", via=operation.type), operation_id=operation.id
            )
            self._set_waiting(operation, question)
            await waiter.wait()
        finally:
            with self._lock:
                self._waiting.pop(operation.id, None)
        settled = self._questions.get(question.id)
        if settled.status == "withdrawn" or settled.answer is None:
            raise Canceled()
        self._set_resumed(operation, settled)
        return settled.answer

    def _set_waiting(self, operation: Operation, question: Question) -> None:
        now = to_text(self._clock.now())
        with self._store.transaction() as db:
            db.execute(
                "UPDATE operations SET status = 'waiting', waiting_on = ?, updated = ? WHERE id = ?",
                (question.id, now, operation.id),
            )
            self._events.record(
                "operation.waiting",
                summary=f"{operation.title} waits for your answer: {question.title}",
                actor=Actor(kind="clank", via=operation.type),
                subject=_subject(operation.id),
                data={"question": question.id},
            )

    def _set_resumed(self, operation: Operation, question: Question) -> None:
        now = to_text(self._clock.now())
        option = question.answer.option if question.answer else None
        with self._store.transaction() as db:
            db.execute(
                "UPDATE operations SET status = 'running', waiting_on = NULL, updated = ? WHERE id = ?",
                (now, operation.id),
            )
            self._events.record(
                "operation.resumed",
                summary=f"{operation.title} goes on",
                actor=Actor(kind="clank", via=operation.type),
                subject=_subject(operation.id),
                data={"question": question.id, "answer": option},
            )

    def _resolved(self, question: Question) -> None:
        if question.operation_id is None:
            return
        with self._lock:
            waiter = self._waiting.get(question.operation_id)
        if waiter is None:
            return
        if threading.get_ident() == self._loop_thread:
            waiter.set()
        else:
            anyio.from_thread.run_sync(waiter.set, token=self._token)

    def _is_canceled(self, id: str) -> bool:
        with self._lock:
            return id in self._canceled


def _subject(id: str) -> Subject:
    return Subject(kind="operation", id=id)


def _operation(row: Any, steps: Sequence[Any]) -> Operation:
    return Operation(
        id=row["id"],
        type=row["type"],
        title=row["title"],
        status=row["status"],
        started_by=Actor.model_validate_json(row["started_by"]),
        created=from_text(row["created"]),
        updated=from_text(row["updated"]),
        finished=from_text(row["finished"]) if row["finished"] else None,
        cancelable=bool(row["cancelable"]),
        params=json.loads(row["params"]),
        result=json.loads(row["result"]) if row["result"] else None,
        error=row["error"],
        request_key=row["request_key"],
        locks=json.loads(row["locks"]),
        waiting_on=row["waiting_on"],
        planned_steps=row["planned_steps"],
        steps=[
            Step(
                number=step["number"],
                name=step["name"],
                status=step["status"],
                repeatable=bool(step["repeatable"]),
                started=from_text(step["started"]),
                finished=from_text(step["finished"]) if step["finished"] else None,
                detail=step["detail"],
            )
            for step in steps
        ],
        retry_of=row["retry_of"],
    )
