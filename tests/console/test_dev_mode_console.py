"""Design 0016 §15 (decisions 0149 and 0152): dev mode in the console. While it is on, the header has a pill, "dev
mode: any provider, any host" ("dev mode" when narrow, its words going short before the other pills') in `attention`
(as a state waiting for the owner), beside the model it changes; off, none. It is shown whatever providers there are:
the console reads dev mode itself, since it opens the agent's internet with a local model too. On the Providers and
models page, `D` turns it on or off, with or without a provider, asked first in words that say both halves (any
provider; every public host for the agent, private addresses still never) and when each applies, with the call it
makes (`PUT /runtime/dev`); the provider's policy line says dev mode beside the record's own; the change reaches every
page from the service's event. Design 0024 §4 (decision 0152): This folder's hosts line says its agent reaches every
public host while dev mode is on, its allowances kept for when it is off."""

from datetime import UTC, datetime

import pytest

from clank.client import Client
from clank.components.agents.console.folder import host_line
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.header import header
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)
PILL = "dev mode: any provider, any host"


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="providers")
    app.folder = FOLDER
    return app


def asked(app: ClankConsole) -> str:
    """What the window on top says, its lines joined as written (a frame wraps them where the window is narrow)."""
    screen = app.screen
    assert isinstance(screen, ConfirmScreen), type(screen)
    return " ".join([screen.heading, *screen.lines])


def test_the_header_says_dev_mode_beside_the_model_while_it_is_on() -> None:
    data = ConsoleData(service={"started": "2026-10-21T09:00:00.000000Z"}, connected=True)
    data.slots = [{"name": "main", "status": "ready", "preset": "cloud-coder"}]
    data.presets = [{"id": "cloud-coder", "title": "cloud: Coder"}]
    data.endpoints = [{"id": "openrouter", "dev_mode": False}]
    assert "dev mode" not in header(data, None, NOW, heard=True, frame=None).plain
    data.endpoints = [{"id": "openrouter", "dev_mode": True}]
    shown = header(data, None, NOW, heard=True, frame=None)
    assert shown.plain == f" ◆ CLANK   ● service up 14m  ● cloud: Coder  ● {PILL}"
    pills = [(shown.plain[span.start : span.end], str(span.style)) for span in shown.spans]
    assert (f"● {PILL}", "$clank-attention") in pills, "in attention's color"
    narrower = header(data, None, NOW, heard=True, frame=None, width=60)
    assert narrower.plain == " ◆ CLANK   ● service up 14m  ● cloud: Coder  ● dev mode", "its words go short first"
    narrow = header(data, None, NOW, heard=True, frame=None, width=50)
    assert narrow.plain.endswith("● dev mode"), "its short words when narrow"


def test_the_header_says_dev_mode_whatever_providers_there_are() -> None:
    data = ConsoleData(service={"started": "2026-10-21T09:00:00.000000Z"}, connected=True)
    data.endpoints = []
    data.dev = {"on": True, "said": "Dev mode is on"}
    assert header(data, None, NOW, heard=True, frame=None).plain.endswith(f"● {PILL}"), (
        "a local model only: dev mode opens the agent's internet all the same"
    )
    data.dev = {"on": False, "said": "Dev mode is off"}
    data.endpoints = [{"id": "openrouter", "dev_mode": True}]
    assert "dev mode" not in header(data, None, NOW, heard=True, frame=None).plain, "the console's own reading decides"


def test_this_folder_says_its_agent_reaches_every_public_host_while_dev_mode_is_on() -> None:
    view = {"workspace": "paper", "hosts": {"pypi.org": "allowed 2026-10-26 by the console"}}
    line = host_line(view)
    assert line is not None
    assert line.plain.startswith("Hosts its agent reaches: pypi.org")
    line = host_line(view, dev=True)
    assert line is not None
    assert line.plain.startswith("Hosts its agent reaches: every public host, in dev mode")
    assert "pypi.org" in line.plain, "the allowances kept for when it is off"
    line = host_line({"workspace": "paper", "hosts": {}}, dev=True)
    assert line is not None
    assert "when it is off: none" in line.plain


async def test_capital_d_turns_dev_mode_on_asked_first_and_the_header_and_policy_say_so(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    app = make(client, home)
    async with app.run_test(size=(170, 40)) as pilot:  # the pill whole
        await settle(pilot, lambda: bool(app.data.endpoints))
        await frame_when(pilot, app, "made-up key label")
        await pilot.press("D")
        await frame_when(pilot, app, "Turn dev mode on?", "PUT /api/v1/runtime/dev")
        words = asked(app)
        for needed in ("any of the model's providers", "data_collection allow", "every public host at once",
                       "private addresses", "still never", "OpenCode", "next start"):  # fmt: skip
            assert needed in words, needed
        await pilot.press("enter")
        await settle(pilot, lambda: cloud_api.kernel.parts["runtime"].settings().dev_mode)
        shown = await frame_when(pilot, app, PILL, "Dev mode: Clank asks for any provider")
        assert PILL in shown.splitlines()[0], "the header says so"
    assert ("PUT", "runtime/dev", {"on": True}) in cloud_api.calls


async def test_capital_d_turns_dev_mode_on_and_off_without_a_cloud_provider(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    runtime = cloud_api.kernel.parts["runtime"]
    app = make(client, home)
    async with app.run_test(size=(170, 40)) as pilot:  # the pill whole
        await settle(pilot, lambda: app.data.endpoints == [] and app.data.dev is not None)
        await pilot.press("D")
        await frame_when(pilot, app, "Turn dev mode on?", "PUT /api/v1/runtime/dev")
        await pilot.press("enter")
        await settle(pilot, lambda: runtime.settings().dev_mode)
        shown = await frame_when(pilot, app, PILL)
        assert PILL in shown.splitlines()[0], "the header says so, with no provider"
        await pilot.press("D")
        await frame_when(pilot, app, "Turn dev mode off?")
        assert "only the hosts allowed" in asked(app)
        await pilot.press("enter")
        await settle(pilot, lambda: not runtime.settings().dev_mode)
        await settle(pilot, lambda: "dev mode" not in render_header(app))
    assert [call for call in cloud_api.calls if call[1] == "runtime/dev"] == [
        ("PUT", "runtime/dev", {"on": True}), ("PUT", "runtime/dev", {"on": False}),
    ]  # fmt: skip


def render_header(app: ClankConsole) -> str:
    """The header's words as the console has them now."""
    return header(app.data, app.activity, NOW, heard=True, frame=None).plain
