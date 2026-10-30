"""Design 0016 §15 (decision 0149): dev mode in the console. While it is on, the header has a pill, "dev mode: any
provider" ("dev mode" when narrow) in `attention` (as a state waiting for the owner), beside the model it changes; off,
none. On the Providers and models
page, `D` turns it on or off, asked first with the call it makes (`PUT /runtime/dev`), and the provider's policy line
says dev mode beside the record's own; the change reaches every page from the service's event."""

from datetime import UTC, datetime

import pytest

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.data import ConsoleData
from clank.console.header import header
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="providers")
    app.folder = FOLDER
    return app


def test_the_header_says_dev_mode_beside_the_model_while_it_is_on() -> None:
    data = ConsoleData(service={"started": "2026-10-21T09:00:00.000000Z"}, connected=True)
    data.slots = [{"name": "main", "status": "ready", "preset": "cloud-coder"}]
    data.presets = [{"id": "cloud-coder", "title": "cloud: Coder"}]
    data.endpoints = [{"id": "openrouter", "dev_mode": False}]
    assert "dev mode" not in header(data, None, NOW, heard=True, frame=None).plain
    data.endpoints = [{"id": "openrouter", "dev_mode": True}]
    shown = header(data, None, NOW, heard=True, frame=None)
    assert shown.plain == " ◆ CLANK   ● service up 14m  ● cloud: Coder  ● dev mode: any provider"
    pills = [(shown.plain[span.start : span.end], str(span.style)) for span in shown.spans]
    assert ("● dev mode: any provider", "$clank-attention") in pills, "in attention's color"
    narrow = header(data, None, NOW, heard=True, frame=None, width=50)
    assert narrow.plain.endswith("● dev mode"), "its short words when narrow"


async def test_capital_d_turns_dev_mode_on_asked_first_and_the_header_and_policy_say_so(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: bool(app.data.endpoints))
        await frame_when(pilot, app, "made-up key label")
        await pilot.press("D")
        await frame_when(pilot, app, "Turn dev mode on?", "PUT /api/v1/runtime/dev")
        await pilot.press("enter")
        await settle(pilot, lambda: cloud_api.kernel.parts["runtime"].settings().dev_mode)
        shown = await frame_when(pilot, app, "dev mode", "Dev mode: Clank asks for any provider")
        assert "dev mode" in shown.splitlines()[0], "the header says so"
    assert ("PUT", "runtime/dev", {"on": True}) in cloud_api.calls
