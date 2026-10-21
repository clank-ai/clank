"""Design 0005 §5 (transparency): on the console's Phone page, Enter on a paired device opens everything it and this
computer exchanged, newest first; the highlighted exchange shows what the device sent and what it was sent back. Design
0011 §7: the window's list is a panel whose note counts the exchanges and what was sent to the device."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from textual.widgets import Label, ListView

from clank import registry
from clank.client import Client
from clank.components.remote import tailnet
from clank.components.remote.app import create_phone_app
from clank.components.remote.console.traffic import TrafficScreen
from clank.components.workspaces import service as workspaces_service
from clank.console.app import ClankConsole
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.console.frames import focus_on, settle
from tests.fakes.platform import FakePlatform
from tests.support.live import live_service

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 15, 7, 0, tzinfo=UTC)
OWNER = "owner@example.com"
YOU = Actor(kind="user", via="console")
THROUGH_TAILSCALE = {"Tailscale-User-Login": OWNER}


@pytest.fixture
def kernel(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, FakeClock(NOW), registry.components())
    monkeypatch.setattr(kernel.parts["remote"], "owner_login", lambda: OWNER)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", OWNER))
    yield kernel
    kernel.close()


@pytest.fixture
def served(kernel: Kernel) -> Iterator[Client]:
    with live_service(kernel) as client:
        yield client


def screen_text(screen: TrafficScreen) -> str:
    return "\n".join(str(label.content) for label in screen.query(Label))


async def test_enter_on_a_device_shows_what_it_and_this_computer_exchanged(kernel: Kernel, served: Client) -> None:
    code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    app_ = create_phone_app(kernel.parts["remote"])
    with TestClient(app_, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50000)) as phone:
        phone.post("/api/pair", json={"code": code}, headers={**THROUGH_TAILSCALE, "X-Clank-Phone": "1"})
        phone.get("/api/overview", headers=THROUGH_TAILSCALE)
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="phone")
    async with app.run_test(size=(160, 48)) as pilot:
        devices = app.query_one("#phone-devices", ListView)
        await settle(
            pilot, lambda: "my phone" in "\n".join(str(each.content) for each in devices.query(Label)), seconds=20
        )
        await focus_on(pilot, app, devices, 0)
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, TrafficScreen))
        screen = app.screen
        assert isinstance(screen, TrafficScreen)
        await settle(pilot, lambda: "GET  /api/overview" in screen_text(screen), seconds=20)
        await settle(pilot, lambda: "sent to the device" in screen_text(screen), seconds=20)
        assert '"model"' in screen_text(screen), "the overview it was sent, whole"
        assert "POST /api/pair" in screen_text(screen)
        listed = screen.query_one("#traffic-list-panel", Panel)
        await settle(pilot, lambda: listed.note.startswith("2 newest exchanges · ") and listed.note in render_text(app))
        assert listed.note.endswith(" sent to it")
        await pilot.press("escape")
