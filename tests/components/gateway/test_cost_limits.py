"""Design 0016 §11 (decisions 0104 and 0108): the optional daily and monthly limits pause the cloud. At 80% of a limit
the owner is told once; at the limit, each new cloud request is held before it is sent (a stream kept alive with comment
lines), and the owner is asked once whether to raise it: *double* raises it and the held stream goes on, *raise* takes
an amount within its bounds (at least a cent above what was spent, so a raise always lets the cloud go on), *keep*
leaves it held until the day ends; a raise that still leaves the spending at the limit asks again, with the new numbers;
requests in flight finish; a local request is never held; the gateway counts the requests the service has not taken
yet, so a burst between two takes is counted."""

import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2
import pytest

from clank.components.gateway.service import Gateway
from clank.components.gateway.spool import Spool
from clank.kernel.events import Actor
from clank.kernel.questions import QuestionError
from tests.components.gateway.test_cloud_forwarding import ASKS, WORKSPACE_KEY, cloud_slot, forwarding
from tests.components.gateway.test_cost_views import entry
from tests.components.gateway.test_server import engine, table  # noqa: F401  (engine: a fixture)
from tests.components.runtime.conftest import Rig
from tests.fakes.openrouter import FakeOpenRouter

PHONE = Actor(kind="device", via="phone")
HELD = ": held by Clank: the cloud spending limit is reached"
ZONE = timezone(timedelta(hours=-4))


def spending(routes: Any, day: float, limit: float | None, taken: int = 0, run: str = "") -> None:
    found = routes._raw  # the routes as the service gave them, the spending changed
    routes.update({**found, "cost": {"day_usd": day, "month_usd": day, "taken": taken, "run": run,
                                     "limit_day_usd": limit, "limit_month_usd": None}})  # fmt: skip


def streamed(url: str) -> tuple[list[str], threading.Event]:
    """A streamed request sent in a thread: its lines as they come, and when it ended."""
    got: list[str] = []
    done = threading.Event()

    def send() -> None:
        headers = {"Authorization": f"Bearer {WORKSPACE_KEY}", "X-Session-Id": "ses_made_up"}
        with httpx2.stream("POST", f"{url}/v1/chat/completions", json=ASKS, headers=headers, timeout=30) as answer:
            got.extend(line for line in answer.iter_lines() if line)
        done.set()

    threading.Thread(target=send, daemon=True).start()
    return got, done


def until(found: Any, seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while not found():
        assert time.monotonic() < deadline, "it did not come"
        time.sleep(0.05)


def test_at_the_limit_a_cloud_request_is_held_and_goes_on_once_raised(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, routes):
        spending(routes, 5.02, 5.0)
        got, done = streamed(url)
        until(lambda: HELD in got)
        time.sleep(0.3)
        assert openrouter.chats() == [], "held before it is sent"
        spending(routes, 5.02, 10.0)
        until(done.is_set)
    assert got[0] == HELD
    assert [line for line in got if line.startswith("data:")] == openrouter.exchange("stream")["response"]["stream"]


def test_kept_paused_it_is_held_until_the_day_ends(openrouter: FakeOpenRouter, tmp_path: Path) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, routes):
        spending(routes, 5.02, 5.0)
        got, done = streamed(url)
        until(lambda: HELD in got)
        spending(routes, 0.0, 5.0)  # the service's new day
        until(done.is_set)
    assert len(openrouter.chats()) == 1


def test_requests_in_flight_finish_and_a_local_request_is_never_held(
    openrouter: FakeOpenRouter,
    tmp_path: Path,
    engine: tuple[int, Path],  # noqa: F811
) -> None:
    openrouter.token_seconds = 0.2
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, routes):
        got, done = streamed(url)
        until(lambda: any(line.startswith("data:") for line in got))
        spending(routes, 6.0, 5.0)
        until(done.is_set)
    assert got[-1] == "data: [DONE]", "the request in flight finished"
    local = tmp_path / "local"
    local.mkdir()
    with forwarding(table(engine[0])["slots"]["main"], local) as (url, routes):
        spending(routes, 6.0, 5.0)
        answer = httpx2.post(f"{url}/v1/chat/completions", json={**ASKS, "stream": False, "max_tokens": 3},
                             headers={"Authorization": f"Bearer {WORKSPACE_KEY}"}, timeout=30)  # fmt: skip
    assert answer.status_code == 200


def test_a_burst_between_two_takes_is_counted(openrouter: FakeOpenRouter, tmp_path: Path) -> None:
    spool = Spool(tmp_path / "state")
    spool.add(entry(0, "2026-10-21T15:00:00.000Z", 0.02))
    with forwarding(cloud_slot(openrouter.url), tmp_path, spool=spool) as (url, routes):
        spending(routes, 4.99, 5.0, taken=0, run=spool.run)
        got, done = streamed(url)
        until(lambda: HELD in got)
        spending(routes, 5.01, 5.0, taken=1, run=spool.run)
        time.sleep(0.3)
        assert openrouter.chats() == [], "the request the service took is counted once, and the limit still holds"
        spending(routes, 5.01, 10.0, taken=1, run=spool.run)
        until(done.is_set)


def limited(rig: Rig, day: float | None, spent: list[float]) -> Gateway:
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.costs.zone = ZONE
    rig.clock.set(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))
    if day is not None:
        gateway.set_limits({"day_usd": day}, actor=Actor(kind="user", via="console"))
    gateway.costs.keep_entries(
        "run-a", [entry(index + 1, "2026-10-21T15:00:00.000Z", usd) for index, usd in enumerate(spent)]
    )
    return gateway


def test_at_eighty_percent_the_owner_is_told_once(rig: Rig) -> None:
    gateway = limited(rig, 5.0, [4.02])
    gateway.costs.check_limits()
    gateway.costs.check_limits()
    [warned] = rig.kernel.events.latest(types=["gateway.limit_warned"])
    assert warned.data == {"by": "day", "spent_usd": 4.02, "limit_usd": 5.0}
    assert warned.attention
    assert warned.summary == "cloud: $4.02 of today's $5.00"
    assert gateway.cost()["warned"] == {"by": "day", "spent_usd": 4.02, "limit_usd": 5.0,
                                        "said": "cloud: $4.02 of today's $5.00"}  # fmt: skip


def test_at_the_limit_the_owner_is_asked_once_and_double_raises_it(rig: Rig) -> None:
    gateway = limited(rig, 5.0, [5.02])
    gateway.costs.check_limits()
    gateway.costs.check_limits()
    [reached] = rig.kernel.events.latest(types=["gateway.limit_reached"])
    [question] = rig.kernel.questions.waiting()
    assert reached.data == {"by": "day", "spent_usd": 5.02, "limit_usd": 5.0, "question": question.id}
    assert question.title == "Cloud spending reached today's limit of $5.00 ($5.02 spent): raise it?"
    assert [(option.id, option.key) for option in question.options] == [("double", "y"), ("raise", "r"), ("keep", "n")]
    raising = question.option("raise")
    assert raising is not None
    assert raising.asks is not None
    assert (raising.asks.min, raising.asks.unit, raising.asks.step) == (5.03, "USD", 0.01), "a cent above it"
    with pytest.raises(QuestionError):
        rig.kernel.questions.answer(question.id, by=PHONE, option="raise", text="5.02")
    assert (question.default, question.urgency) == ("keep", "high")
    assert question.expires == datetime(2026, 10, 22, 4, 0, tzinfo=UTC), "when the day ends"
    paused = gateway.cost()["paused"]
    assert (paused["by"], paused["question"], paused["spent_usd"]) == ("day", question.id, 5.02)
    assert paused["said"] == "cloud paused: today's limit of $5.00 reached ($5.02 spent)"
    assert gateway.routes()["cost"]["limit_day_usd"] == 5.0
    rig.kernel.questions.answer(question.id, by=PHONE, option="double")
    assert gateway.cost()["limits"]["day_usd"] == 10.0
    assert gateway.cost()["paused"] is None
    [raised] = rig.kernel.events.latest(types=["gateway.limit_raised"])
    assert raised.data == {"by": "day", "limit_usd": 10.0, "who": "device phone"}


def test_a_raise_that_still_leaves_the_spending_at_the_limit_asks_again(rig: Rig) -> None:
    gateway = limited(rig, 5.0, [12.0])  # requests in flight passed the limit by far
    gateway.costs.check_limits()
    [question] = rig.kernel.questions.waiting()
    rig.kernel.questions.answer(question.id, by=PHONE, option="double")
    assert gateway.cost()["limits"]["day_usd"] == 10.0
    paused = gateway.cost()["paused"]
    assert paused is not None, "still at the limit"
    [again] = rig.kernel.questions.waiting()
    assert again.id != question.id
    assert again.title == "Cloud spending reached today's limit of $10.00 ($12.00 spent): raise it?"
    assert (paused["question"], paused["limit_usd"]) == (again.id, 10.0)


def test_raise_takes_an_amount_and_keep_waits_for_the_day_to_end(rig: Rig) -> None:
    gateway = limited(rig, 5.0, [5.02])
    gateway.costs.check_limits()
    [question] = rig.kernel.questions.waiting()
    rig.kernel.questions.answer(question.id, by=PHONE, option="raise", text="12.50")
    assert gateway.cost()["limits"]["day_usd"] == 12.5
    gateway.costs.keep_entries("run-a", [entry(9, "2026-10-21T15:30:00.000Z", 8.0)])
    gateway.costs.check_limits()
    [again] = rig.kernel.questions.waiting()
    rig.kernel.questions.answer(again.id, by=PHONE, option="keep")
    assert gateway.cost()["paused"] is not None
    rig.clock.set(datetime(2026, 10, 22, 5, 0, tzinfo=UTC))  # the next day, here
    gateway.costs.check_limits()
    assert gateway.cost()["paused"] is None
    [ended, *_] = rig.kernel.events.latest(types=["gateway.limit_raised"])
    assert ended.data["who"] == "the day ended"
