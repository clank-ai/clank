"""Design 0013 §6 and §9 (decision 0064): deciding a DECOMPOSE's proposals never hangs the service while a client
follows its events, as the console, VS Code and the phone do: each event is handed to the service's event loop and its
teller waits for it there, so the driver, which holds the run at the DECOMPOSE on that loop, never waits for what a
decision holds. The owner accepting through the API's route, and the phone accepting them all by answering the question
about them, both while the run is held, go on at once, and the tasks run next. Run against the fake bridge and a
synthetic folder."""

import contextlib
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import anyio
import anyio.from_thread
import anyio.lowlevel
import anyio.to_thread
import pytest

from clank.kernel.events import Actor, Event
from tests.components.flows.rig import OWNER, WORKSPACE, Rig, decomposing, make_rig, running, until
from tests.components.flows.test_proposals_decided import proposed

pytestmark = pytest.mark.anyio
PHONE = Actor(kind="user", via="phone")
HUNG = 5.0  # seconds a follower waits for the event loop before it says the loop hung


@pytest.fixture
def rig(home: Any, clock: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, decomposing())
    yield made
    made.kernel.close()


def follow(rig: Rig) -> list[str]:
    """A client following the events, as the API's event stream does: each event told on another thread is handed to
    the event loop, its teller waiting until the loop takes it; here it waits at most `HUNG` seconds, so a loop that
    hangs fails the test instead of hanging it. The events the loop did not take in time, by type."""
    token, loop = anyio.lowlevel.current_token(), threading.get_ident()
    hung: list[str] = []

    def hand(handed: threading.Event) -> None:
        with contextlib.suppress(RuntimeError):  # the loop ended
            anyio.from_thread.run_sync(lambda: None, token=token)
        handed.set()

    def follower(event: Event) -> None:
        if threading.get_ident() == loop or hung:
            return
        handed = threading.Event()
        threading.Thread(target=hand, args=(handed,), daemon=True).start()
        if not handed.wait(HUNG):
            hung.append(event.type)

    rig.kernel.events.subscribe(follower)
    return hung


async def held(rig: Rig) -> list[str]:
    """The DECOMPOSE proposed two tasks and ended, the run held at it for them, and a client following the events."""
    await proposed(rig, 2)
    await until(lambda: waits_for_proposals(rig))
    return follow(rig)


def waits_for_proposals(rig: Rig) -> bool:
    waiting = rig.run().waiting
    return waiting is not None and waiting.kind == "proposals"


async def decided(rig: Rig, decide: Callable[[], Any]) -> None:
    """`decide` on a worker thread, as the API's routes run it; the tasks it accepts then run next."""
    await anyio.to_thread.run_sync(decide)
    await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


async def test_the_owner_accepting_while_a_client_follows_the_events_never_hangs_the_service(rig: Rig) -> None:
    flows = rig.kernel.parts["flows"]
    async with running(rig.kernel):
        hung = await held(rig)
        await decided(rig, lambda: flows.decide(WORKSPACE, "study", "accept", [], every=True, actor=OWNER))
    assert hung == [], f"the event loop hung while {hung[0]} was told"
    assert [each.state for batch in rig.runner.proposing.batches.of_run(rig.run()) for each in batch.proposals] == [
        "accepted",
        "accepted",
    ]


async def test_the_phone_accepting_all_while_a_client_follows_the_events_never_hangs_the_service(rig: Rig) -> None:
    async with running(rig.kernel):
        hung = await held(rig)
        asked = rig.run().waiting
        assert asked is not None
        await decided(rig, lambda: rig.kernel.questions.answer(asked.question, by=PHONE, option="accept"))
    assert hung == [], f"the event loop hung while {hung[0]} was told"
    assert [each.state for batch in rig.runner.proposing.batches.of_run(rig.run()) for each in batch.proposals] == [
        "accepted",
        "accepted",
    ]
