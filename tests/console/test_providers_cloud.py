"""Design 0016 §15: the Providers and models page's Cloud panel. With a provider: its title, its agreement, its key (its
last four and its label, never the rest), its data policy, OpenRouter's own count for the key, Clank's spending today
and this month against the limits, its last check and its presets, in the service's words; without one, how to add
one. Each key calls its route: `a` Add a model at Cloud, `k` the key again in a hidden field, `c` the check (its items
in a window), `o` the data policy (asked first), `L` the limits (a form, sent as typed), `r` remove (asked first;
refused while in use, in the service's words)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from textual import events
from textual.widgets import ContentSwitcher, Input

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.form import SecretField
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.fakes.openrouter import KEY
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="providers")
    app.folder = FOLDER
    return app


async def opened(pilot: Any, app: ClankConsole, *words: str) -> str:
    await settle(pilot, lambda: bool(app.data.meters) and app.data.endpoints is not None)
    return await frame_when(pilot, app, *words)


def provided(cloud: CloudBench) -> None:
    cloud.add()
    cloud.write_preset()
    cloud.spend(0.42, requests=31)
    cloud.set_limits(day_usd=5.0)


async def test_the_cloud_panel_with_a_provider(client: Client, home: Home, cloud_api: CloudBench) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(128, 50)) as pilot:
        frame = await opened(pilot, app, "made-up key label", "cloud $0.42 today")
        assert KEY[:-4] not in frame
        assert_frame(frame, "providers-cloud")


async def test_the_cloud_panel_without_a_provider_says_how_to_add_one(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        frame = await opened(pilot, app, "a adds one")
        assert_frame(frame, "providers-cloud-none")
        await pilot.press("a")
        await settle(pilot, lambda: app.query_one("#pages", ContentSwitcher).current == "page-addmodel")
        await frame_when(pilot, app, "openrouter.ai")


async def test_k_sets_the_key_again_in_a_hidden_field(client: Client, home: Home, cloud_api: CloudBench) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await opened(pilot, app, "made-up key label")
        await pilot.press("k")
        await settle(pilot, lambda: bool(app.screen.query(SecretField)))
        app.post_message(events.Paste(KEY))
        await settle(pilot, lambda: "…-key" in render_text(app))
        assert KEY[:-4] not in render_text(app)
        await pilot.press("enter")
        await settle(pilot, lambda: any(path.endswith("/key") for _, path, _ in cloud_api.calls))
        await frame_when(pilot, app, "OpenRouter took the key")


async def test_c_checks_and_shows_each_item(client: Client, home: Home, cloud_api: CloudBench) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await opened(pilot, app, "made-up key label")
        await pilot.press("c")
        frame = await frame_when(pilot, app, "Check of OpenRouter")
        assert "today's $5.00" in frame
    assert ("POST", "runtime/endpoints/openrouter/check", {}) in cloud_api.calls


async def test_o_changes_the_data_policy_asked_first(client: Client, home: Home, cloud_api: CloudBench) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await opened(pilot, app, "made-up key label")
        await pilot.press("o")
        await frame_when(pilot, app, "data_collection allow")
        await pilot.press("enter")
        await settle(pilot, lambda: cloud_api.endpoint is not None
                     and cloud_api.endpoint["options"]["data_collection"] == "allow")  # fmt: skip


async def test_capital_l_sets_the_limits_in_a_form(client: Client, home: Home, cloud_api: CloudBench) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await opened(pilot, app, "made-up key label")
        await pilot.press("L")
        await settle(pilot, lambda: bool(app.screen.query(Input)))
        month = app.screen.query_one("#form-month", Input)
        month.value = "40"
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: cloud_api.limits["month_usd"] == 40.0)
    assert ("PUT", "gateway/cost/limits", {"day_usd": 5.0, "month_usd": 40.0}) in cloud_api.calls, "as amounts"


async def test_r_removes_asked_first_and_while_in_use_says_why_not(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    provided(cloud_api)
    app = make(client, home)
    async with app.run_test(size=(88, 40)) as pilot:
        await opened(pilot, app, "made-up key label")
        await pilot.press("r")
        await frame_when(pilot, app, "Remove OpenRouter?")
        await pilot.press("enter")
        frame = await frame_when(pilot, app, "openrouter is in use")
        assert "cloud-example-coder" in frame
    assert cloud_api.endpoint is not None
