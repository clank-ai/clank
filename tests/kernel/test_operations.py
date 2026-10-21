"""Design 0002 §2.4: anything slow runs in the service as an operation: its steps recorded as they start and end, locks
that refuse a second one, request keys that never start one twice, cancellation, waiting for the user's answer, and
after a restart, operations marked interrupted and reconciled instead of blindly repeated."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import pytest

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, EventLog
from clank.kernel.operations import (
    Busy,
    Canceled,
    Operation,
    OperationContext,
    OperationError,
    Operations,
    OperationType,
    Reconciliation,
    StepSpec,
)
from clank.kernel.questions import Option, QuestionDraft, Questions
from clank.kernel.store import Store

pytestmark = pytest.mark.anyio

YOU = Actor(kind="user", via="console")
GO_ON = QuestionDraft(
    type="approval",
    title="Go on?",
    options=[Option(id="yes", label="Yes"), Option(id="no", label="No")],
    default="no",
)


async def three_steps(context: OperationContext) -> dict[str, Any]:
    for name in ("check", "stop", "verify"):
        async with context.step(name):
            context.log(f"doing {name}")
    return {"stopped": True}


async def fails_in_stop(context: OperationContext) -> None:
    async with context.step("check"):
        pass
    async with context.step("stop"):
        raise RuntimeError("Docker did not answer")
    async with context.step("verify"):
        pass


async def asks(context: OperationContext) -> dict[str, Any]:
    async with context.step("check"):
        answer = await context.ask(GO_ON)
    return {"answer": answer.option}


async def asks_until_half_past(context: OperationContext) -> dict[str, Any]:
    async with context.step("check"):
        answer = await context.ask(GO_ON.model_copy(update={"expires": datetime(2026, 10, 11, 12, 30, tzinfo=UTC)}))
    return {"answer": answer.option}


async def sends_then_asks(context: OperationContext) -> dict[str, Any]:
    async with context.step("check"):
        pass
    async with context.step("send"):
        answer = await context.ask(GO_ON)
    return {"answer": answer.option}


async def loops_until_canceled(context: OperationContext) -> None:
    async with context.step("check"):
        while True:
            context.check_canceled()
            await anyio.sleep(0.001)


async def gives_up(context: OperationContext) -> None:
    async with context.step("check"):
        raise Canceled("canceled: you (console) answered Cancel")


async def checked(operation: Operation) -> Reconciliation:
    return Reconciliation(f"checked {operation.type}: Docker is running")


def one_slot(params: Mapping[str, Any]) -> list[str]:
    return [f"slot:{params.get('slot', 'main')}"]


STEPS = (StepSpec("check"), StepSpec("stop"), StepSpec("verify"))
TYPES = [
    OperationType("test.three", "Three steps", STEPS, three_steps),
    OperationType("test.fails", "Fails in stop", STEPS, fails_in_stop),
    OperationType("test.asks", "Asks first", STEPS, asks, reconcile=checked, locks=one_slot),
    OperationType("test.expires", "Asks until half past", STEPS, asks_until_half_past),
    OperationType("test.loops", "Loops", STEPS, loops_until_canceled),
    OperationType("test.stubborn", "Cannot stop", STEPS, loops_until_canceled, cancelable=False),
    OperationType("test.gives_up", "Gives up", STEPS, gives_up),
    OperationType("test.sends", "Sends once", (StepSpec("check"), StepSpec("send", repeatable=False)), sends_then_asks),
]


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, registry.event_types())


@pytest.fixture
def questions(store: Store, log: EventLog, clock: FakeClock) -> Questions:
    return Questions(store, log, clock)


@pytest.fixture
def make(store: Store, log: EventLog, questions: Questions, clock: FakeClock) -> Callable[[], Operations]:
    return lambda: Operations(store, log, questions, clock, TYPES)


async def finished(operations: Operations, id: str) -> Operation:
    with anyio.fail_after(10):
        return await operations.wait(id)


async def until(operations: Operations, id: str, status: str) -> Operation:
    for _ in range(2000):
        operation = operations.get(id)
        if operation.status == status:
            return operation
        await anyio.sleep(0.001)
    raise AssertionError(f"{id} never became {status}; it is {operations.get(id).status}")


async def test_an_operation_runs_its_steps_in_order_and_records_each(
    make: Callable[[], Operations], log: EventLog
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.three", actor=YOU)
        done = await finished(operations, started.id)
    assert (done.status, done.result, done.error) == ("done", {"stopped": True}, "")
    assert [(step.name, step.status) for step in done.steps] == [
        ("check", "done"),
        ("stop", "done"),
        ("verify", "done"),
    ]
    assert done.progress() == "3 of 3: verify"
    assert done.started_by == YOU
    kinds = [event.type for event in log.after(0)]
    assert kinds[0] == "operation.started"
    assert kinds.count("operation.step") == 6
    assert kinds[-1] == "operation.finished"


async def test_an_operations_log_is_kept_with_the_step_of_each_line_and_read_from_any_line_on(
    make: Callable[[], Operations],
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.three", actor=YOU)
        await finished(operations, started.id)
    lines = [(line.number, line.step, line.text) for line in operations.log_lines(started.id)]
    assert lines == [(1, 1, "doing check"), (2, 2, "doing stop"), (3, 3, "doing verify")]
    assert [line.text for line in operations.log_lines(started.id, after=2)] == ["doing verify"]


async def test_a_failing_step_fails_the_operation_and_stops_it(make: Callable[[], Operations]) -> None:
    operations = make()
    async with operations.running():
        failed = await finished(operations, (await operations.start("test.fails", actor=YOU)).id)
    assert failed.status == "failed"
    assert "Docker did not answer" in failed.error
    assert [(step.name, step.status) for step in failed.steps] == [("check", "done"), ("stop", "failed")]


async def test_a_second_operation_needing_the_same_lock_is_refused_naming_the_first(
    make: Callable[[], Operations], questions: Questions
) -> None:
    operations = make()
    async with operations.running():
        first = await operations.start("test.asks", {"slot": "main"}, actor=YOU)
        await until(operations, first.id, "waiting")
        with pytest.raises(
            Busy, match=rf"slot:main is in use by Asks first \({first.id}\), started by you \(console\)"
        ):
            await operations.start("test.asks", {"slot": "main"}, actor=YOU)
        other = await operations.start("test.asks", {"slot": "fast"}, actor=YOU)
        await until(operations, other.id, "waiting")
        for waiting in questions.waiting():
            questions.answer(waiting.id, by=YOU, option="yes")
        await finished(operations, first.id)
        await finished(operations, other.id)


async def test_the_same_request_key_returns_the_operation_already_started(make: Callable[[], Operations]) -> None:
    operations = make()
    async with operations.running():
        first = await operations.start("test.three", actor=YOU, request_key="phone-1234")
        again = await operations.start("test.three", actor=YOU, request_key="phone-1234")
        await finished(operations, first.id)
    assert again.id == first.id
    assert len(operations.find()) == 1


async def test_canceling_stops_a_cancelable_operation_at_its_next_check(make: Callable[[], Operations]) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.loops", actor=YOU)
        await until(operations, started.id, "running")
        while not operations.get(started.id).steps:  # cancel inside the step, not before it starts
            await anyio.sleep(0.001)
        await operations.cancel(started.id, actor=YOU)
        canceled = await finished(operations, started.id)
    assert canceled.status == "canceled"
    assert canceled.error == "canceled by you (console)"
    assert [(step.name, step.status, step.detail) for step in canceled.steps] == [
        ("check", "canceled", "canceled by you (console)")
    ]


async def test_an_operation_that_cancels_itself_with_a_reason_shows_that_reason(
    make: Callable[[], Operations],
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.gives_up", actor=YOU)
        done = await finished(operations, started.id)
    assert (done.status, done.error) == ("canceled", "canceled: you (console) answered Cancel")
    assert [(step.status, step.detail) for step in done.steps] == [
        ("canceled", "canceled: you (console) answered Cancel")
    ]


async def test_an_operation_that_cannot_be_canceled_says_so(make: Callable[[], Operations]) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.stubborn", actor=YOU)
        with pytest.raises(OperationError, match="cannot be canceled"):
            await operations.cancel(started.id, actor=YOU)


async def test_waiting_for_the_user_resumes_with_the_answer(
    make: Callable[[], Operations], questions: Questions
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.asks", actor=YOU)
        waiting = await until(operations, started.id, "waiting")
        assert waiting.waiting_on is not None
        questions.answer(waiting.waiting_on, by=YOU, option="yes")
        done = await finished(operations, started.id)
    assert (done.status, done.result) == ("done", {"answer": "yes"})


async def test_an_answer_given_from_another_thread_wakes_the_operation(
    make: Callable[[], Operations], questions: Questions
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.asks", actor=YOU)
        waiting = await until(operations, started.id, "waiting")
        question = waiting.waiting_on
        assert question is not None
        await anyio.to_thread.run_sync(lambda: questions.answer(question, by=YOU, option="yes"))
        done = await finished(operations, started.id)
    assert done.result == {"answer": "yes"}


async def test_an_expired_question_resumes_it_with_the_default(
    make: Callable[[], Operations], questions: Questions, clock: FakeClock
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.expires", actor=YOU)
        await until(operations, started.id, "waiting")
        clock.advance(timedelta(days=1).total_seconds())
        questions.expire_due()
        done = await finished(operations, started.id)
    assert done.result == {"answer": "no"}


async def test_expiry_without_an_expiry_time_leaves_the_question_waiting(
    make: Callable[[], Operations], questions: Questions
) -> None:
    operations = make()
    async with operations.running():
        started = await operations.start("test.asks", actor=YOU)
        await until(operations, started.id, "waiting")
        assert questions.expire_due() == []
        await operations.cancel(started.id, actor=YOU)
        assert (await finished(operations, started.id)).status == "canceled"


async def test_after_a_restart_unfinished_operations_are_interrupted_their_questions_withdrawn_and_reconciled(
    make: Callable[[], Operations], questions: Questions, log: EventLog
) -> None:
    before = make()
    async with before.running():
        started = await before.start("test.asks", actor=YOU)
        waiting = await until(before, started.id, "waiting")
    assert before.get(started.id).status == "waiting"
    after = make()
    [interrupted] = await after.recover()
    assert interrupted.id == started.id
    assert interrupted.status == "interrupted"
    assert waiting.waiting_on is not None
    assert questions.get(waiting.waiting_on).status == "withdrawn"
    [note] = log.after(0, types=["operation.reconciled"])
    assert note.data["note"] == "checked test.asks: Docker is running"


async def test_retrying_an_interrupted_operation_runs_it_again_when_its_steps_are_repeatable(
    make: Callable[[], Operations], questions: Questions
) -> None:
    before = make()
    async with before.running():
        started = await before.start("test.asks", actor=YOU)
        await until(before, started.id, "waiting")
    after = make()
    await after.recover()
    async with after.running():
        retried = await after.retry(started.id, actor=YOU)
        waiting = await until(after, retried.id, "waiting")
        assert waiting.waiting_on is not None
        questions.answer(waiting.waiting_on, by=YOU, option="yes")
        done = await finished(after, retried.id)
    assert (done.status, done.retry_of) == ("done", started.id)


async def test_retrying_is_refused_when_a_step_that_had_started_is_not_repeatable(
    make: Callable[[], Operations],
) -> None:
    before = make()
    async with before.running():
        started = await before.start("test.sends", actor=YOU)
        await until(before, started.id, "waiting")
    after = make()
    await after.recover()
    async with after.running():
        with pytest.raises(OperationError, match="the step send had started and is not safe to run again"):
            await after.retry(started.id, actor=YOU)
