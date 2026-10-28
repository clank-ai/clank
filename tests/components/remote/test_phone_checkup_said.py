"""Design 0025 §2 (when the page does not load): where the checkup is said. The service checks only while remote access
is on; it keeps what Tailscale said for a few seconds and what its own address answered for a few minutes (each opening
is an exchange in the listener's log), asks public DNS only while Funnel is on, and asks everything again at once when
told to. Its local API serves it (`GET /remote/checkup`); `clank remote status` prints it under the status, `clank
remote pair` says under the QR what to check on the iPhone when the page will not load, and `clank doctor` adds it
while remote access is on, without the service."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.machine import cli as machine_cli
from clank.components.machine.kinds import MachineProfile
from clank.components.remote import probes, tailnet
from clank.components.remote.probes import Public, Reached
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.service import DockerReading, PlatformStatus
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform
from tests.fakes.tailscale import HOST, OWNER, phone, served, status
from tests.support.served import free_port

NOW = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)
YOU = Actor(kind="user", via="console")
OPENED = f"open https://{HOST}:8445/"
HINT = "Page won't load? On the iPhone: Tailscale on, iCloud Private Relay off."


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the checkup asked, in order: Tailscale's status and what it serves, this PC's own address, public DNS.
    Tailscale says the owner's iPhone is offline and Funnel is on for port 443."""
    calls: list[str] = []

    def said() -> tuple[dict[str, Any], str]:
        calls.append("status")
        return status(phone()), ""

    def serving() -> dict[str, Any]:
        calls.append("serve")
        return served(funnel=(443,))

    def opened(url: str, timeout: float = probes.REACH_TIMEOUT) -> Reached:
        calls.append(f"open {url}")
        return Reached(200, 240.0)

    def resolved(name: str, **options: Any) -> Public:
        calls.append(f"dns {name}")
        return Public(("203.0.113.5",))

    monkeypatch.setattr(tailnet, "status", said)
    monkeypatch.setattr(tailnet, "serve_config", serving)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet(HOST, OWNER))
    monkeypatch.setattr(probes, "reach", opened)
    monkeypatch.setattr(probes, "public_addresses", resolved)
    return calls


@pytest.fixture
def kernel(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, FakeClock(NOW), registry.components())
    kernel.parts["remote"].zone = UTC
    yield kernel
    kernel.close()


@pytest.fixture
def commands(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The commands, clients of the kernel's API served in the test."""
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield


def test_the_checkup_runs_only_while_remote_access_is_on_and_keeps_its_answers_until_asked_afresh(
    kernel: Kernel, asked: list[str]
) -> None:
    remote = kernel.parts["remote"]
    assert remote.checkup() == {"on": False, "at": "", "checks": []}
    assert asked == [], "nothing is asked while remote access is off"
    remote.switch(True, actor=YOU)
    first = remote.checkup()
    assert (first["on"], first["at"]) == (True, "2026-10-26T20:00:00.000Z")
    assert [check["id"] for check in first["checks"]][:3] == ["phone:my-iphone", "heard", "funnel"]
    assert asked == ["status", "serve", OPENED, f"dns {HOST}"]
    assert remote.checkup()["checks"] == first["checks"]
    assert len(asked) == 4, "kept: nothing is asked again at once"
    kernel.clock.advance(20)  # type: ignore[attr-defined]
    remote.checkup()
    assert asked[4:] == ["status", "serve"], "Tailscale is asked again after a few seconds; the address is not opened"
    remote.checkup(fresh=True)
    assert asked[6:] == ["status", "serve", OPENED, f"dns {HOST}"], "asked afresh: everything again"


def test_clank_remote_status_prints_the_checkup_under_the_status(
    kernel: Kernel, asked: list[str], commands: None
) -> None:
    remote = kernel.parts["remote"]
    remote.switch(True, actor=YOU)
    result = CliRunner().invoke(main, ["remote", "status"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("Remote access on")
    assert "How the phone reaches it, checked from this PC:" in lines
    assert any(
        line.startswith("  warn  my-iphone") and line.endswith("offline on your tailnet (last seen 3 h ago)")
        for line in lines
    ), result.output
    assert "-> open the Tailscale app on the iPhone and switch it on (it says Connected), then scan the QR again" in (
        result.output
    )
    assert "-> on the iPhone, turn off iCloud Private Relay" in result.output
    assert asked[:3] == ["status", "serve", OPENED], "asked afresh"
    found = json.loads(CliRunner().invoke(main, ["remote", "status", "--json"]).output)
    assert found["checkup"]["checks"][0]["id"] == "phone:my-iphone"
    remote.switch(False, actor=YOU)
    assert "How the phone reaches it" not in CliRunner().invoke(main, ["remote", "status"]).output


def test_clank_remote_pair_says_under_the_qr_what_to_check_on_the_iphone_when_the_page_will_not_load(
    asked: list[str], commands: None
) -> None:
    result = CliRunner().invoke(main, ["remote", "pair", "my phone"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    scan = next(index for index, line in enumerate(lines) if line.startswith("Scan it with the iPhone's camera"))
    assert lines[scan + 1] == HINT, "the line under the QR's own"


def test_the_doctor_adds_the_phones_checkup_while_remote_access_is_on_without_the_service(
    home: Home, asked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(machine_cli, "detect", lambda *args, **kwargs: MachineProfile())
    monkeypatch.setattr(machine_cli, "run_command", lambda arguments: None)
    stopped = PlatformStatus(adapter="fake", label="Fake Docker", state="stopped")
    monkeypatch.setattr(machine_cli, "read_platform", lambda home: DockerReading(status=stopped, starts=True))
    settings = home.config / "remote.json"
    settings.write_text(json.dumps({"schema": "remote/1", "on": False}), encoding="utf-8")
    quiet = CliRunner().invoke(main, ["doctor"], env={"CLANK_HOME": str(home.root)})
    assert "Phone:" not in quiet.output
    assert asked == [], "nothing is asked while remote access is off"
    settings.write_text(json.dumps({"schema": "remote/1", "on": True, "port": free_port()}), encoding="utf-8")
    result = CliRunner().invoke(main, ["doctor"], env={"CLANK_HOME": str(home.root)})
    lines = result.output.splitlines()
    assert any("Phone: my-iphone" in line and "offline on your tailnet (last seen " in line for line in lines)
    assert any("Phone: The listener" in line and "Clank's service does not run" in line for line in lines)
    assert any("Phone: Funnel" in line for line in lines)
    assert "-> start it: `clank serve --background`" in result.output
    assert asked == ["status", "serve", f"dns {HOST}"], "its address is not opened while nothing listens"
