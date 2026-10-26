"""Design 0025 §2 (decision 0143): installing the phone app once. The console makes a pair link whose code is spent by
the device that opens it (no typing); the page it gets pairs the device, keeps its cookie and shows the steps to add
the app to the Home Screen, with a one-time install claim in the icon's start link (the manifest's `start_url`); the
installed app's first launch trades the claim for the device's token (the Safari tab's stops working: the pairing moved
into the app), a claim is spent once and lapses after an hour; a device's token renews on each use and lapses only
after thirty days unused (no ceiling from its pairing)."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.remote import tailnet
from clank.components.remote.app import COOKIE, create_phone_app
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

OWNER = "owner@example.com"
YOU = Actor(kind="user", via="console")
THROUGH_TAILSCALE = {"Tailscale-User-Login": OWNER}
ACT = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["remote"], "owner_login", lambda: OWNER)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", OWNER))
    yield kernel
    kernel.close()


@pytest.fixture
def phone(kernel: Kernel) -> Iterator[TestClient]:
    app = create_phone_app(kernel.parts["remote"])
    with TestClient(app, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50000)) as client:
        yield client


def opened_link(kernel: Kernel, phone: TestClient) -> tuple[str, str]:
    """A pair link made and opened: the install claim in its page, and the Safari tab's cookie."""
    made = kernel.parts["remote"].pair_link("my phone", actor=YOU)
    answer = phone.get("/pair", params={"code": made["code"]}, headers=THROUGH_TAILSCALE)
    assert answer.status_code == 200, answer.text
    found = re.search(r"manifest\.webmanifest\?claim=([A-Za-z0-9_-]+)", answer.text)
    assert found is not None, "the manifest link carries the install claim"
    return found.group(1), answer.cookies[COOKIE]


def test_the_pair_link_pairs_the_device_by_its_code_and_shows_the_install_steps_once(
    kernel: Kernel, phone: TestClient
) -> None:
    remote = kernel.parts["remote"]
    made = remote.pair_link("my phone", actor=YOU)
    assert made["link"] == f"https://desk.tail0.ts.net:8445/pair?code={made['code']}"
    assert made["expires"]
    assert phone.get("/pair", params={"code": made["code"]}).status_code == 403, "not through Tailscale"
    answer = phone.get("/pair", params={"code": made["code"]}, headers=THROUGH_TAILSCALE)
    assert answer.status_code == 200, answer.text
    assert COOKIE in answer.cookies, "paired by the code in the link: nothing typed"
    assert "Add to Home Screen" in answer.text
    assert "manifest.webmanifest?claim=" in answer.text
    assert [device.name for device in remote.devices.all()] == ["my phone"]
    again = phone.get("/pair", params={"code": made["code"]}, headers=THROUGH_TAILSCALE)
    assert again.status_code == 403, "a code pairs once"
    assert "does not pair" in again.text


def test_the_installed_app_trades_its_claim_for_the_token_once_and_a_claim_lapses_after_an_hour(
    kernel: Kernel, clock: FakeClock, phone: TestClient
) -> None:
    claim, safari = opened_link(kernel, phone)
    phone.cookies.clear()  # the Home Screen app's storage is apart from Safari's
    launched = phone.get("/", params={"claim": claim}, headers=THROUGH_TAILSCALE)
    assert launched.status_code == 200
    assert COOKIE in launched.cookies, "the first launch trades the claim for the token"
    token = launched.cookies[COOKIE]
    phone.cookies.clear()
    phone.cookies.set(COOKIE, token)
    assert phone.get("/api/me", headers=THROUGH_TAILSCALE).status_code == 200
    phone.cookies.clear()
    phone.cookies.set(COOKIE, safari)
    assert phone.get("/api/me", headers=THROUGH_TAILSCALE).status_code == 401, (
        "the pairing moved from Safari into the app"
    )
    phone.cookies.clear()
    again = phone.get("/", params={"claim": claim}, headers=THROUGH_TAILSCALE)
    assert again.status_code == 200, "the page still loads"
    assert COOKIE not in again.cookies, "a claim is spent once"
    claim2, _ = opened_link(kernel, phone)
    phone.cookies.clear()
    clock.advance(3601)
    late = phone.get("/", params={"claim": claim2}, headers=THROUGH_TAILSCALE)
    assert COOKIE not in late.cookies, "a claim lapses after an hour"


def test_a_devices_token_renews_on_use_and_lapses_only_after_thirty_days_unused(
    kernel: Kernel, clock: FakeClock, phone: TestClient
) -> None:
    code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    assert phone.post("/api/pair", json={"code": code}, headers=ACT).status_code == 200
    for _ in range(6):  # 120 days of use: no ceiling from the pairing
        clock.advance(20 * 86400)
        assert phone.get("/api/me", headers=THROUGH_TAILSCALE).status_code == 200
    clock.advance(31 * 86400)
    assert phone.get("/api/me", headers=THROUGH_TAILSCALE).status_code == 401, "thirty days unused: it lapsed"


def test_the_manifest_carries_the_devices_start_link(phone: TestClient) -> None:
    plain = phone.get("/manifest.webmanifest", headers=THROUGH_TAILSCALE)
    assert plain.status_code == 200
    assert plain.json()["start_url"] == "./"
    assert plain.json()["display"] == "standalone"
    claimed = phone.get("/manifest.webmanifest", params={"claim": "abc-123"}, headers=THROUGH_TAILSCALE)
    assert claimed.json()["start_url"] == "./?claim=abc-123"
    assert claimed.json()["name"] == "Clank"
