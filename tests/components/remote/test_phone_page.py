"""Design 0005 §5 (transparency): on the console's Phone page, Enter on a paired device opens everything it and this
computer exchanged, newest first; the highlighted exchange shows what the device sent and what it was sent back. Design
0011 §7: the window's list is a panel whose note counts the exchanges and what was sent to the device. Design 0025 §2:
`p` shows a QR carrying the pair link, with the link and the code under it, and what to check on the iPhone when the
page will not load; while remote access is on, the page says how the phone reaches it, checked from this PC, and `r`
checks again."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from textual.widgets import Label, ListView

from clank import registry
from clank.client import Client
from clank.components.remote import probes, tailnet
from clank.components.remote.app import create_phone_app
from clank.components.remote.console.traffic import TrafficScreen
from clank.components.remote.probes import Public, Reached
from clank.components.workspaces import service as workspaces_service
from clank.console.app import ClankConsole
from clank.console.form import FormScreen
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.console.frames import focus_on, settle
from tests.fakes import tailscale as fake
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


async def test_p_shows_a_qr_that_carries_the_pair_link_with_the_link_and_the_code_under_it(
    kernel: Kernel, served: Client
) -> None:
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="phone")
    async with app.run_test(size=(160, 60)) as pilot:
        code_label = app.query_one("#phone-code", Label)
        await settle(pilot, lambda: "p makes a code" in str(code_label.content), seconds=20)
        await pilot.press("p")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: "Scan it with the iPhone" in str(code_label.content), seconds=20)
        shown = str(code_label.content)
        assert "█" in shown, "the QR, drawn as text"
        assert "https://desk.tail0.ts.net:8445/pair?code=" in shown
        assert "or type the code" in shown
        assert "for phone, until" in shown
        assert "Page won't load? On the iPhone: Tailscale on, iCloud Private Relay off." in shown


async def test_the_page_says_how_the_phone_reaches_it_checked_from_this_pc_and_r_checks_again(
    kernel: Kernel, served: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    seen = (NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z")

    def said() -> tuple[dict[str, Any], str]:
        asked.append("status")
        return fake.status(fake.phone(LastSeen=seen)), ""

    monkeypatch.setattr(tailnet, "status", said)
    monkeypatch.setattr(tailnet, "serve_config", lambda: fake.served(funnel=(443,)))
    monkeypatch.setattr(probes, "reach", lambda url, timeout=5.0: Reached(200, 240.0))
    monkeypatch.setattr(probes, "public_addresses", lambda name, **options: Public(("203.0.113.5",)))
    remote = kernel.parts["remote"]
    remote.zone = UTC
    remote.switch(True, actor=YOU)
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="phone")
    async with app.run_test(size=(160, 60)) as pilot:
        checkup = app.query_one("#phone-checkup", Label)
        await settle(pilot, lambda: "my-iphone" in str(checkup.content), seconds=20)
        shown = str(checkup.content)
        assert "How the phone reaches it, checked 07:00:00 (r checks again)" in shown
        assert "warn  my-iphone" in shown
        assert "offline on your tailnet (last seen 3 h ago)" in shown
        assert "open the Tailscale app on the iPhone and switch it on (it says Connected), then scan the QR again" in (
            shown
        )
        assert "turn off iCloud Private Relay (Settings, your name, iCloud, Private Relay)" in shown
        before = len(asked)
        await pilot.press("r")
        await settle(pilot, lambda: len(asked) > before, seconds=20)
