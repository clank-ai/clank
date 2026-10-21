"""Design 0016 §11 and decision 0104: when a cloud spending limit is reached, the header and Home say the cloud is
paused, in the service's words, with `L` to raise it; `L` anywhere then opens the limits, sent as amounts through
`PUT /gateway/cost/limits`; the limit question's `raise` takes its amount in one field, as any option that takes a typed
answer does (the service says what it takes: a number, its unit and its bounds), the answer's text holding it; the
banner goes once the service says the limit was raised."""

from datetime import UTC, datetime

import pytest
from textual.widgets import Input

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.form import FormScreen
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)
PAUSED = "cloud paused: today's limit of $5.00 reached ($5.02 spent) · L raise"


def make(client: Client, home: Home, page: str = "home") -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page)
    app.folder = FOLDER
    return app


def paused(cloud: CloudBench) -> None:
    cloud.add()
    cloud.set_limits(day_usd=5.0)
    cloud.spend(4.0, requests=40)


async def test_a_limit_reached_shows_the_banner_and_l_raises_it_until_the_banner_goes(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    paused(cloud_api)
    app = make(client, home, "models")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "cloud $4.00 today" in render_text(app))
        cloud_api.reach("day", 1.02)
        await settle(pilot, lambda: PAUSED in render_text(app).splitlines()[0])
        await pilot.press("L")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        day = app.screen.query_one("#form-day", Input)
        day.value = "10"
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: PAUSED not in render_text(app))
    assert ("PUT", "gateway/cost/limits", {"day_usd": 10.0, "month_usd": None}) in cloud_api.calls
    assert cloud_api.limits["day_usd"] == 10.0


async def test_the_questions_raise_takes_its_amount_in_one_field(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    paused(cloud_api)
    app = make(client, home, "questions")
    async with app.run_test(size=(200, 50)) as pilot:
        cloud_api.reach("day", 1.02)
        await settle(pilot, lambda: "r Raise it to …" in render_text(app))
        await pilot.press("right", "r")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        assert "Raise it to … (USD, 5.03 to 100000)" in render_text(app)
        await pilot.press(*"12.50", "enter")
        await settle(pilot, lambda: cloud_api.paused is None)
        await settle(pilot, lambda: PAUSED not in render_text(app))
    assert cloud_api.limits["day_usd"] == 12.5
