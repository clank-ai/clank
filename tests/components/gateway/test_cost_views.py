"""Design 0016 §11 and §12 (decisions 0104 and 0108): what the cloud cost, as every client reads it from the service and
none recomputes. Today and this month are this computer's local days, the periods' bounds given with their words (a
day the clocks change is 25 or 23 hours long, its bounds each at the offset of its own moment); a
session's cost counts its subagents'; a flow's is its boxes' sessions'; an estimate shows apart (≈) until it is exact;
the runtime's own requests (a load's health, a check, a test) are counted in the totals; a workspace's own today and
this month are given beside them when asked (`?workspace=`), the limits staying the whole cloud's; the lists take a
revision and give only what changed since; and the limits are written to `config/cost.json`, recorded with who set
them."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows.runs import BoxRun, Run, Try
from clank.components.gateway.service import Gateway
from clank.kernel.api import create_app
from clank.kernel.clock import to_text
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")
ZONE = timezone(timedelta(hours=-4))


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


class ClocksGoBack(tzinfo):
    """A made-up zone whose clocks go back an hour at 06:00 UTC on 2026-11-01: UTC-4 before, UTC-5 after."""

    CHANGE = datetime(2026, 11, 1, 6, 0)

    def utcoffset(self, moment: datetime | None) -> timedelta:
        wall = (moment or datetime(2026, 12, 1)).replace(tzinfo=None)
        return timedelta(hours=-4) if wall < datetime(2026, 11, 1, 1, 0) else timedelta(hours=-5)

    def dst(self, moment: datetime | None) -> timedelta | None:
        return None

    def tzname(self, moment: datetime | None) -> str:
        return "made-up"

    def fromutc(self, moment: datetime) -> datetime:
        utc = moment.replace(tzinfo=None)
        return (utc + (timedelta(hours=-4) if utc < self.CHANGE else timedelta(hours=-5))).replace(tzinfo=self)


def entry(seq: int, time: str, usd: float, how: str = "usage", **values: Any) -> dict[str, Any]:
    return {"seq": seq, "time": time, "id": f"r-{seq}", "session": "ses_a", "parent": "", "workspace": "notes",
            "endpoint": "openrouter", "preset": "cloud-example-coder", "model": "example-vendor/example-coder",
            "generation": f"gen-{seq}", "tokens": {"in": 100, "cached": 0, "out": 10, "thinking": 0}, "usd": usd,
            "how": how, "status": 200, "code": "", **values}  # fmt: skip


def costs(rig: Rig) -> Gateway:
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.costs.zone = ZONE
    return gateway


def test_today_and_this_month_are_this_computers_days_across_midnight(rig: Rig, http: TestClient) -> None:
    gateway = costs(rig)
    rig.clock.set(datetime(2026, 10, 21, 5, 0, tzinfo=UTC))  # 01:00 on the 21st at UTC-4
    gateway.costs.keep_entries("run-a", [
        entry(1, "2026-10-21T03:00:00.000Z", 1.0),  # 23:00 on the 20th, here
        entry(2, "2026-10-21T04:30:00.000Z", 2.0),  # 00:30 on the 21st
        entry(3, "2026-09-30T12:00:00.000Z", 4.0),  # last month
    ])  # fmt: skip
    view = http.get("/api/v1/gateway/cost", headers=AUTH).json()
    assert (view["today"]["usd"], view["today"]["requests"], view["month"]["usd"]) == (2.0, 1, 3.0)
    assert (view["currency"], view["days"], view["zone"]) == ("USD", "local", "UTC-04:00")
    assert (view["today"]["from"], view["today"]["until"], view["today"]["local"]) == (
        "2026-10-21T04:00:00.000Z", "2026-10-22T04:00:00.000Z", "2026-10-21"
    )  # fmt: skip
    assert (view["month"]["from"], view["month"]["local"]) == ("2026-10-01T04:00:00.000Z", "2026-10")
    assert (view["today"]["said"], view["month"]["said"]) == ("$2.00 today", "$3.00 this month")
    assert view["said"] == "cloud $2.00 today · $3.00 this month"
    assert (view["paused"], view["warned"], view["revision"]) == (None, None, 3)
    gateway.costs.announce()
    gateway.costs.announce()
    [told] = rig.kernel.events.latest(types=["gateway.cost"])
    assert told.data == {"today_usd": 2.0, "month_usd": 3.0, "estimated_usd": 0.0}
    assert told.summary == "cloud $2.00 today · $3.00 this month"
    assert view["limits"] == {"day_usd": None, "month_usd": None, "warn_at": 0.8, "said": "no daily or monthly limit"}


def test_a_day_the_clocks_change_runs_from_its_own_midnight_to_the_next(rig: Rig, http: TestClient) -> None:
    gateway = costs(rig)
    gateway.costs.zone = ClocksGoBack()
    rig.clock.set(datetime(2026, 11, 1, 12, 0, tzinfo=UTC))  # 07:00 on the 1st, after the clocks went back
    gateway.costs.keep_entries("run-a", [
        entry(1, "2026-11-01T03:30:00.000Z", 1.0),  # 23:30 on October 31st, here
        entry(2, "2026-11-01T04:30:00.000Z", 2.0),  # 00:30 on the 1st, before the change
    ])  # fmt: skip
    view = http.get("/api/v1/gateway/cost", headers=AUTH).json()
    assert (view["today"]["from"], view["today"]["until"]) == ("2026-11-01T04:00:00.000Z", "2026-11-02T05:00:00.000Z")
    assert (view["month"]["from"], view["month"]["until"]) == ("2026-11-01T04:00:00.000Z", "2026-12-01T05:00:00.000Z")
    assert (view["today"]["usd"], view["month"]["usd"], view["zone"]) == (2.0, 2.0, "UTC-05:00")


def test_in_the_systems_own_zone_each_bound_is_at_the_offset_of_its_own_moment(rig: Rig, http: TestClient) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert gateway.costs.zone is None, "the system's zone, with its own changes of the clock"
    rig.clock.set(datetime(2026, 11, 15, 17, 0, tzinfo=UTC))
    today = rig.clock.now().astimezone().date()
    view = http.get("/api/v1/gateway/cost", headers=AUTH).json()

    def midnight(day: Any) -> str:
        return to_text(datetime(day.year, day.month, day.day).astimezone())  # the system's rules for that moment

    assert (view["today"]["from"], view["today"]["until"]) == (midnight(today), midnight(today + timedelta(days=1)))
    assert (view["month"]["from"], view["month"]["until"]) == (
        midnight(today.replace(day=1)), midnight(datetime(2026, 12, 1)))  # fmt: skip


def test_an_estimate_shows_apart_until_it_is_exact_and_the_runtimes_own_requests_count(
    rig: Rig, http: TestClient
) -> None:
    gateway = costs(rig)
    rig.clock.set(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))
    gateway.costs.keep_entries("run-a", [entry(1, "2026-10-21T15:00:00.000Z", 0.03, "estimate")])
    rig.runtime.endpoints.keep_check("openrouter", "test", True, [], 0.01)
    view = http.get("/api/v1/gateway/cost", headers=AUTH).json()
    assert view["today"]["usd"] == pytest.approx(0.04)
    assert view["today"]["estimated_usd"] == pytest.approx(0.03)
    assert view["today"]["said"] == "≈ $0.04 today"
    [row] = http.get("/api/v1/gateway/cost/requests", headers=AUTH).json()
    assert (row["how"], row["said"]) == ("estimate", "≈ $0.03")


def test_a_workspaces_own_cost_is_given_beside_the_whole_clouds_when_asked(rig: Rig, http: TestClient) -> None:
    gateway = costs(rig)
    rig.clock.set(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))
    gateway.costs.keep_entries("run-a", [
        entry(1, "2026-10-21T15:00:00.000Z", 0.50),
        entry(2, "2026-10-21T15:10:00.000Z", 0.25, "estimate", workspace="lab"),
        entry(3, "2026-10-02T15:00:00.000Z", 1.00, workspace="lab"),
    ])  # fmt: skip
    rig.runtime.endpoints.keep_check("openrouter", "test", True, [], 0.01)
    whole = http.get("/api/v1/gateway/cost", headers=AUTH).json()
    assert whole["workspace"] is None
    lab = http.get("/api/v1/gateway/cost", params={"workspace": "lab"}, headers=AUTH).json()
    assert lab["today"]["usd"] == pytest.approx(0.76), "the whole cloud's, the runtime's own counted in"
    mine = lab["workspace"]
    assert mine["name"] == "lab"
    assert (mine["today"]["usd"], mine["today"]["requests"], mine["today"]["estimated_usd"]) == (0.25, 1, 0.25)
    assert (mine["month"]["usd"], mine["month"]["requests"]) == (1.25, 2)
    assert (mine["today"]["said"], mine["month"]["said"]) == ("≈ $0.25 today", "≈ $1.25 this month")
    assert (mine["today"]["from"], mine["month"]["local"]) == (lab["today"]["from"], "2026-10")


def test_a_sessions_cost_counts_its_subagents_and_the_lists_give_only_what_changed(rig: Rig, http: TestClient) -> None:
    gateway = costs(rig)
    rig.clock.set(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))
    gateway.costs.keep_entries("run-a", [
        entry(1, "2026-10-21T15:00:00.000Z", 0.5),
        entry(2, "2026-10-21T15:01:00.000Z", 0.25, session="ses_child", parent="ses_a"),
        entry(3, "2026-10-21T15:02:00.000Z", 1.0, session="ses_b", workspace="lab"),
    ])  # fmt: skip
    answer = http.get("/api/v1/gateway/cost/sessions", headers=AUTH)
    assert answer.headers["x-clank-revision"] == "3"
    sessions = {row["session"]: row for row in answer.json()}
    assert set(sessions) == {"ses_a", "ses_b"}
    assert (sessions["ses_a"]["usd"], sessions["ses_a"]["requests"], sessions["ses_a"]["rev"]) == (0.75, 2, 2)
    assert sessions["ses_a"]["said"] == "$0.75 · 2 requests"
    assert [row["session"] for row in http.get("/api/v1/gateway/cost/sessions?workspace=lab", headers=AUTH).json()] == [
        "ses_b"
    ]
    assert http.get("/api/v1/gateway/cost/sessions?after=2", headers=AUTH).json()[0]["session"] == "ses_b"
    requests = http.get("/api/v1/gateway/cost/requests?session=ses_a", headers=AUTH).json()
    assert [row["id"] for row in requests] == ["r-2", "r-1"]
    assert [row["id"] for row in http.get("/api/v1/gateway/cost/requests?after=2", headers=AUTH).json()] == ["r-3"]


def test_a_flows_cost_is_its_boxes_sessions(rig: Rig) -> None:
    gateway = costs(rig)
    rig.clock.set(datetime(2026, 10, 21, 16, 0, tzinfo=UTC))
    gateway.costs.keep_entries("run-a", [
        entry(1, "2026-10-21T15:00:00.000Z", 0.5, session="ses_box1"),
        entry(2, "2026-10-21T15:01:00.000Z", 0.25, session="ses_sub", parent="ses_box1"),
        entry(3, "2026-10-21T15:02:00.000Z", 1.0, session="ses_box2"),
        entry(4, "2026-10-21T15:03:00.000Z", 9.0, session="ses_elsewhere"),
    ])  # fmt: skip
    flows = rig.kernel.parts["flows"]
    run = Run(flow="notes/study", number=1, workspace="notes", version="v1", status="done", started_by=YOU,
              created=rig.clock.now(), boxes={
                  "plan": BoxRun(tries=[Try(number=1, started=rig.clock.now(), session="ses_box1")]),
                  "write": BoxRun(tries=[Try(number=1, started=rig.clock.now(), session="ses_box2")]),
                  "you": BoxRun()})  # fmt: skip
    flows.runner.runs.save(run)
    found = flows.cost("notes/study")
    assert (found["usd"], found["requests"], found["estimated_usd"]) == (1.75, 3, 0.0)
    assert found["boxes"] == {"plan": {"usd": 0.75, "requests": 2, "said": "$0.75 · 2 requests"},
                              "write": {"usd": 1.0, "requests": 1, "said": "$1.00 · 1 request"}}  # fmt: skip
    assert found["said"] == "$1.75 · 3 requests"
    assert flows.cost("notes/other") is None


def test_the_limits_are_written_to_their_file_and_recorded(rig: Rig, http: TestClient) -> None:
    answer = http.put("/api/v1/gateway/cost/limits", json={"day_usd": 5.0}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    assert answer.json()["limits"] == {"day_usd": 5.0, "month_usd": None, "warn_at": 0.8,
                                       "said": "today's limit $5.00; no monthly limit"}  # fmt: skip
    written = json.loads((rig.kernel.home.config / "cost.json").read_text(encoding="utf-8"))
    assert written == {"schema": "cost/1", "day_usd": 5.0}
    http.put("/api/v1/gateway/cost/limits", json={"month_usd": 40}, headers=AUTH)
    removed = http.put("/api/v1/gateway/cost/limits", json={"day_usd": None}, headers=AUTH).json()["limits"]
    assert (removed["day_usd"], removed["month_usd"]) == (None, 40.0)
    [changed, *_] = rig.kernel.events.latest(types=["settings.changed"])
    assert (changed.data["kind"], changed.actor.via) == ("cost", "console")
    refused = http.put("/api/v1/gateway/cost/limits", json={"day_usd": -1}, headers=AUTH)
    assert refused.status_code == 422
