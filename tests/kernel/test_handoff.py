"""Design 0002 §2.3: a thread that records an event, or hands the service's event loop any other work, never waits for
the loop to take it, so a thread holding a lock the loop then waits for (review mode's, which a flow's box takes as it
starts) cannot freeze the service (decision 0158)."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

import clank
from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import event_stream
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK
from clank.kernel.handoff import Handoff
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.fakes.platform import FakePlatform

STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    options=[Option(id="stop", label="Stop it", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.mark.anyio
async def test_a_thread_holding_a_lock_records_an_event_while_the_loop_waits_for_that_lock(kernel: Kernel) -> None:
    lock, held, recorded = threading.Lock(), threading.Event(), threading.Event()

    def watcher() -> None:  # review mode's watcher thread: it asks its question under its lock
        with lock:
            held.set()
            time.sleep(0.2)  # the loop is waiting for the lock by now
            kernel.questions.ask(STOP, asked_by=CLANK)
            recorded.set()

    stream = event_stream(kernel, after=kernel.events.last_id(), types=["question.asked"])
    await stream.__anext__()  # connected: the stream hears every new event from here
    thread = threading.Thread(target=watcher, name="a watcher", daemon=True)
    thread.start()
    await anyio.to_thread.run_sync(held.wait)
    took = lock.acquire(timeout=5)  # on the loop itself, as a flow's box start takes review mode's lock
    if took:
        lock.release()
    assert took, "the thread waited for the loop while holding the lock the loop waited for"
    assert recorded.wait(5)
    with anyio.fail_after(5):
        chunk = await stream.__anext__()
    assert "question.asked" in chunk, "what was handed over still reaches the stream"
    await stream.aclose()


@pytest.mark.anyio
async def test_work_handed_to_a_busy_loop_from_a_thread_returns_at_once_and_runs_in_order() -> None:
    handoff, ran, returned = Handoff(), [], []

    def hand() -> None:
        began = time.monotonic()
        for number in range(3):
            handoff.call(ran.append, number)
        returned.append(time.monotonic() - began)

    thread = threading.Thread(target=hand)
    thread.start()
    time.sleep(0.5)  # the loop is busy: nothing handed to it can run yet
    thread.join(5)
    assert returned, "the thread ended"
    assert returned[0] < 0.25, "the thread waited for the busy loop"
    await anyio.sleep(0.05)
    assert ran == [0, 1, 2]
    handoff.call(ran.append, 3)
    assert ran[-1] == 3, "on the loop's own thread it runs at once"


def test_nothing_in_clank_waits_for_the_event_loop_from_a_thread() -> None:
    sources = Path(clank.__file__).parent.rglob("*.py")
    waiting = [path.name for path in sources if "from_thread." in path.read_text(encoding="utf-8")]
    assert waiting == [], "hand work to the loop through kernel/handoff.py, which never waits"
