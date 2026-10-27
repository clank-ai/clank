"""Design 0005 §4 (decision 0012): who may reach the phone page, pairing, and what a paired device sees and does.

The phone's app answers only through Tailscale: from this machine's loopback (where `tailscale serve` connects from),
with Tailscale's verified login, that login this computer's own user's, never a request Funnel brought from the
internet. Tailscale's proxy names the phone's tailnet address in `X-Forwarded-For`; the listener, served as the service
serves it, takes the connection's own address, never that header. The page itself then shows; everything else needs a
paired device's token. A code made on the computer pairs one device, once, before it expires; wrong codes are counted
and entry rests after eight; a token works only with the login it paired with and stops working when revoked. Every
action carries the page's own header. A paired device sees the model, the workspaces and what waits, and the files the
agents sent (served from an outbox only, by name)."""

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient

from clank import registry
from clank.components.remote import tailnet
from clank.components.remote.app import COOKIE, create_phone_app
from clank.components.remote.devices import TRIES, PairingError
from clank.components.remote.service import phone_config
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform
from tests.support.served import free_port

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


def paired(kernel: Kernel, phone: TestClient) -> None:
    code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    answer = phone.post("/api/pair", json={"code": f"{code[:4]}-{code[4:].lower()}"}, headers=ACT)
    assert answer.status_code == 200, answer.text
    assert COOKIE in phone.cookies


def test_the_page_answers_only_through_tailscale_to_this_computers_own_user(kernel: Kernel, phone: TestClient) -> None:
    assert phone.get("/", headers=THROUGH_TAILSCALE).status_code == 200
    assert phone.get("/").status_code == 403, "no Tailscale login: not through Tailscale"
    assert phone.get("/", headers={"Tailscale-User-Login": "someone@else.com"}).status_code == 403
    funnel = phone.get("/", headers={**THROUGH_TAILSCALE, "Tailscale-Funnel-Request": "?1"})
    assert funnel.status_code == 403, "Funnel brings the internet: never"
    app = create_phone_app(kernel.parts["remote"])
    with TestClient(app, base_url="https://desk.tail0.ts.net:8445", client=("100.64.0.9", 50000)) as elsewhere:
        assert elsewhere.get("/", headers=THROUGH_TAILSCALE).status_code == 403, "only Tailscale's serve connects"
    page = phone.get("/", headers=THROUGH_TAILSCALE)
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert phone.get("/app.js", headers=THROUGH_TAILSCALE).status_code == 200
    assert phone.get("/secrets.json", headers=THROUGH_TAILSCALE).status_code == 404


def test_tailscales_forwarded_address_does_not_hide_that_it_connected_from_this_machine(kernel: Kernel) -> None:
    port = free_port()
    server = uvicorn.Server(phone_config(create_phone_app(kernel.parts["remote"]), port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the phone's listener never started"
        time.sleep(0.01)
    try:
        forwarded = {**THROUGH_TAILSCALE, "X-Forwarded-For": "100.101.102.103", "X-Forwarded-Proto": "https"}
        page = httpx2.get(f"http://127.0.0.1:{port}/", headers=forwarded, timeout=10)
        assert page.status_code == 200, page.text
        me = httpx2.get(f"http://127.0.0.1:{port}/api/me", headers=forwarded, timeout=10)
        assert me.status_code == 401, "it asks for pairing, as a phone through Tailscale should see"
    finally:
        server.should_exit = True
        thread.join(15)


def test_a_device_pairs_once_with_a_code_from_the_computer_and_then_is_known(kernel: Kernel, phone: TestClient) -> None:
    assert phone.get("/api/me", headers=THROUGH_TAILSCALE).status_code == 401
    assert phone.get("/api/overview", headers=THROUGH_TAILSCALE).status_code == 401
    code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    assert phone.post("/api/pair", json={"code": code}, headers=THROUGH_TAILSCALE).status_code == 403, (
        "an action needs the page's own header"
    )
    assert phone.post("/api/pair", json={"code": code}, headers=ACT).status_code == 200
    assert phone.get("/api/me", headers=THROUGH_TAILSCALE).json() == {"device": "my phone", "login": OWNER}
    phone.cookies.clear()
    again = phone.post("/api/pair", json={"code": code}, headers=ACT)
    assert again.status_code == 403, "a code pairs once"
    [device] = [row for row in kernel.parts["remote"].status()["devices"] if not row["revoked"]]
    assert device["login"] == OWNER
    events = kernel.events.after(0, types=["remote.paired"])
    assert [event.data["name"] for event in events] == ["my phone"]


def test_a_pairing_code_canceled_on_the_computer_no_longer_pairs(kernel: Kernel, phone: TestClient) -> None:
    remote = kernel.parts["remote"]
    code = remote.pair("my phone", actor=YOU)["code"]
    assert remote.status()["pairing"]["name"] == "my phone"
    assert remote.cancel_pairing(actor=YOU)["canceled"] is True
    assert remote.status()["pairing"] is None
    answer = phone.post("/api/pair", json={"code": code}, headers=ACT)
    assert answer.status_code == 403, "a canceled code does not pair"
    assert remote.cancel_pairing(actor=YOU)["canceled"] is False, "nothing waits any more"
    [canceled] = kernel.events.after(0, types=["remote.pairing_canceled"])
    assert canceled.summary == "you (console) canceled the pairing code for my phone"


def test_wrong_codes_are_counted_and_an_expired_code_does_not_pair(kernel: Kernel, clock: FakeClock) -> None:
    devices = kernel.parts["remote"].devices
    code, _ = devices.new_code("phone")
    clock.advance(16 * 60)
    with pytest.raises(PairingError, match="does not pair"):
        devices.pair(code, OWNER)
    code, _ = devices.new_code("phone")
    for _ in range(TRIES - 1):
        with pytest.raises(PairingError, match="does not pair"):
            devices.pair("WRONG234", OWNER)
    with pytest.raises(PairingError, match="too many wrong codes"):
        devices.pair(code, OWNER)
    clock.advance(16 * 60)  # the window passes; that code expired meanwhile, so a new one
    code, _ = devices.new_code("phone")
    device, token = devices.pair(code, OWNER)
    assert devices.device(token, OWNER) is not None
    assert devices.device(token, "someone@else.com") is None, "a token works only with the login it paired with"
    devices.revoke(device.id)
    assert devices.device(token, OWNER) is None
    clock.advance(31 * 86400)


def test_a_paired_device_sees_the_model_the_workspaces_and_the_files_sent(
    kernel: Kernel, phone: TestClient, tmp_path: Path
) -> None:
    paired(kernel, phone)
    folder = tmp_path / "paper"
    (folder / ".clank" / "outbox").mkdir(parents=True)
    (folder / ".clank" / "outbox" / "20261015-tau.png").write_bytes(b"\x89PNG")
    note = {"file": "20261015-tau.png", "caption": "tau vs p", "from": "runs/tau.png", "sent": 1792038183.0}
    (folder / ".clank" / "outbox" / "20261015-tau.png.json").write_text(json.dumps(note), encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    found = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
    assert found["model"]["status"] == "stopped"
    assert found["workspaces"] == [{"name": "paper", "state": "not made", "servers": [], "problem": ""}]
    assert [(file["workspace"], file["caption"]) for file in found["files"]] == [("paper", "tau vs p")]
    image = phone.get("/api/files/paper/20261015-tau.png", headers=THROUGH_TAILSCALE)
    assert (image.status_code, image.content) == (200, b"\x89PNG")
    assert phone.get("/api/files/paper/20261015-tau.png.json", headers=THROUGH_TAILSCALE).status_code == 404
    assert phone.get("/api/files/paper/..%2F..%2Fsecret", headers=THROUGH_TAILSCALE).status_code == 404
    refused = phone.post("/api/sessions/paper/start", json={"text": "send me the figure"}, headers=ACT)
    assert refused.status_code == 409, "its container does not run: said, in the bridge's words"
    assert "does not run" in refused.json()["error"]


def test_the_overview_reads_every_running_workspaces_sessions_at_once(
    kernel: Kernel, phone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0025 §3: the phone's first screen waited for one workspace after another (12 s on the owner's PC with five
    running, 2026-10-26); their sessions are read side by side, a refusal said in its workspace."""
    from clank.components.agents.service import SessionError

    paired(kernel, phone)
    rows = [{"name": name, "state": "running"} for name in ("a", "b", "c")]
    monkeypatch.setattr(kernel.parts["workspaces"], "workspaces", lambda: rows)

    def servers(name: str) -> list[dict[str, Any]]:
        time.sleep(0.4)
        if name == "c":
            raise SessionError("c's watcher said nothing")
        return [{"port": 4096, "sessions": [], "permissions": [], "questions": []}]

    monkeypatch.setattr(kernel.parts["agents"].sessions, "servers", servers)
    began = time.perf_counter()
    found = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
    assert time.perf_counter() - began < 1.0, "side by side, not 1.2 s one after another"
    assert [(each["name"], len(each["servers"]), each["problem"]) for each in found["workspaces"]] == [
        ("a", 1, ""), ("b", 1, ""), ("c", 0, "c's watcher said nothing")
    ]  # fmt: skip


def test_every_exchange_with_a_device_is_kept_whole_and_shown_to_it_and_to_the_computer(
    kernel: Kernel, phone: TestClient, tmp_path: Path
) -> None:
    """Transparency: what a phone asked and what it was sent, its token and its pairing code never kept."""
    paired(kernel, phone)
    token = phone.cookies[COOKIE]
    first = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
    phone.get("/api/overview", headers=THROUGH_TAILSCALE)
    phone.get("/", headers=THROUGH_TAILSCALE)
    listed = phone.get("/api/traffic", headers=THROUGH_TAILSCALE).json()["exchanges"]
    page, again, overview, pairing = listed[:4]
    assert [(each["method"], each["path"], each["status"]) for each in (page, again, overview, pairing)] == [
        ("GET", "/", 200),
        ("GET", "/api/overview", 200),
        ("GET", "/api/overview", 200),
        ("POST", "/api/pair", 200),
    ]
    assert pairing["device_name"] == "my phone", "the pairing names the device it made"
    assert "response" not in overview, "a list holds no bodies"
    whole = phone.get(f"/api/traffic/{overview['id']}", headers=THROUGH_TAILSCALE).json()
    assert whole["response"] == first
    assert phone.get(f"/api/traffic/{again['id']}", headers=THROUGH_TAILSCALE).json()["same_as"] == overview["id"]
    code = phone.get(f"/api/traffic/{pairing['id']}", headers=THROUGH_TAILSCALE).json()["request"]["code"]
    assert code == "••••••••", "a pairing code is masked"
    remote = kernel.parts["remote"]
    assert {each["id"] for each in listed} <= {each["id"] for each in remote.traffic.recent(pairing["device"])}
    kept = "".join(file.read_text(encoding="utf-8") for file in (kernel.home.logs / "phone").glob("*.jsonl"))
    assert token not in kept, "the device's token is never kept"
    kernel.parts["remote"].pair("other", actor=YOU)
    app = create_phone_app(kernel.parts["remote"])
    with TestClient(app, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50001)) as other:
        paired(kernel, other)
        assert other.get(f"/api/traffic/{overview['id']}", headers=THROUGH_TAILSCALE).status_code == 404


def test_tailscale_says_this_machines_name_and_user_or_why_not() -> None:
    status = {"BackendState": "Running", "Self": {"DNSName": "desk.tail0.ts.net.", "UserID": 7},
              "User": {"7": {"LoginName": "Owner@Example.com"}}}  # fmt: skip

    def run(argv: Any) -> Answer:
        return Answer(0, json.dumps(status), "")

    assert tailnet.read(run) == tailnet.Tailnet("desk.tail0.ts.net", OWNER)
    stopped = tailnet.read(lambda argv: Answer(0, json.dumps({"BackendState": "Stopped"}), ""))
    assert "Stopped" in stopped.problem
    assert tailnet.read(lambda argv: Answer(None, "", "Tailscale is not installed")).problem.startswith("Tailscale")
    funnel = {"AllowFunnel": {"desk.tail0.ts.net:8445": True}}
    assert tailnet.funnel_on("desk.tail0.ts.net", 8445, lambda argv: Answer(0, json.dumps(funnel), ""))
    assert not tailnet.funnel_on("desk.tail0.ts.net", 8446, lambda argv: Answer(0, json.dumps(funnel), ""))


def test_remote_access_is_off_until_turned_on_and_a_code_comes_with_the_pages_address(kernel: Kernel) -> None:
    remote = kernel.parts["remote"]
    assert remote.status()["on"] is False
    made = remote.pair("phone", actor=YOU)
    assert made["url"] == "https://desk.tail0.ts.net:8445/"
    assert len(made["code"]) == 8
    assert remote.status()["pairing"]["name"] == "phone"
    assert remote.switch(True, actor=YOU)["on"] is True
    assert [event.data["on"] for event in kernel.events.after(0, types=["remote.switched"])] == [True]
