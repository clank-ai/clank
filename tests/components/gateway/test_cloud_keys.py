"""Design 0016 §5 (decision 0106): the service hands the gateway a cloud provider's key, behind its local token, while a
cloud model is loaded. The gateway's `/keys` routes take only the service's token and never answer a value; a load
hands the key once, read through the kernel by `gateway` for its launch; a new key set while loaded replaces it; an
unload takes it back; a gateway started again gets it at the next look; a request waits while the key is not there and
goes once it is; and a key that appears in a request is replaced in its record by `…` and its last four."""

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
import uvicorn

from clank.components.gateway.keys import Keys
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from clank.components.gateway.service import Gateway
from clank.kernel.access import local_token
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from clank.kernel.service import server_config
from tests.components.gateway.test_server import ASKED, engine, recorded, started, table  # noqa: F401
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import KEY, FakeOpenRouter
from tests.support.served import free_port

YOU = Actor(kind="user", via="console")
TOKEN = "local-token-of-the-test"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter",
                            "model": "example-vendor/example-coder", "options": {"context": 65536}}  # fmt: skip


@contextlib.contextmanager
def gateway_served(table: Routes, tmp_path: Path, token: str | None = TOKEN, keys: Keys | None = None) -> Iterator[str]:
    """The gateway with the service's token, served for real; its base URL."""
    settings = GatewaySettings(port=free_port(), hold_seconds=5)
    app = create_gateway(table, settings, TrafficLog(tmp_path / "traffic", 256, 14), token=token, keys=keys)
    server = uvicorn.Server(server_config(app, "127.0.0.1", settings.port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{settings.port}"
    finally:
        server.should_exit = True
        thread.join(15)


def owner(url: str, method: str, path: str, body: dict[str, Any] | None = None, token: str = TOKEN) -> httpx2.Response:
    return httpx2.request(method, f"{url}/{path}", json=body, headers={"Authorization": f"Bearer {token}"}, timeout=10)


def test_the_keys_routes_take_only_the_services_token(tmp_path: Path) -> None:
    with gateway_served(Routes(), tmp_path) as url:
        for method, path in (("GET", "keys"), ("PUT", "keys/openrouter"), ("DELETE", "keys/openrouter")):
            refused = owner(url, method, path, {"key": KEY, "launch": 1}, token="an-agents-guess")
            assert refused.status_code == 401, path
            assert KEY not in refused.text
    with gateway_served(Routes(), tmp_path, token=None) as url:
        assert owner(url, "GET", "keys").status_code == 503


def test_the_gateway_holds_a_key_in_memory_and_never_answers_its_value(tmp_path: Path) -> None:
    with gateway_served(Routes(), tmp_path) as url:
        put = owner(url, "PUT", "keys/openrouter", {"key": KEY, "launch": 12, "set": "2026-10-21T09:13:00.000Z"})
        assert put.json() == {
            "endpoint": "openrouter",
            "ends": KEY[-4:],
            "launch": 12,
            "set": "2026-10-21T09:13:00.000Z",
        }
        listed = owner(url, "GET", "keys")
        assert listed.json() == {"keys": [put.json()]}
        assert KEY not in put.text + listed.text
        assert owner(url, "DELETE", "keys/openrouter").json() == {"forgotten": "openrouter"}
        assert owner(url, "GET", "keys").json() == {"keys": []}
    assert not [path for path in tmp_path.rglob("*") if path.is_file() and KEY.encode() in path.read_bytes()]


def used_by_gateway(rig: Rig) -> list[dict[str, Any]]:
    return [
        event.data for event in rig.kernel.events.latest(100, types=["secret.used"]) if event.data["user"] == "gateway"
    ]


async def load(rig: Rig) -> Operation:
    async with rig.kernel.operations.running():
        started_ = await rig.kernel.operations.start(
            "runtime.load", {"slot": "main", "preset": "cloud-example-coder"}, actor=YOU
        )
        with anyio.fail_after(60):
            return await rig.kernel.operations.wait(started_.id)


@pytest.mark.anyio
async def test_a_load_hands_the_key_once_a_new_key_replaces_it_and_an_unload_takes_it_back(
    rig: Rig, openrouter: FakeOpenRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    gateway: Gateway = rig.kernel.parts["gateway"]
    with gateway_served(Routes(), tmp_path, token=local_token(rig.kernel.home)) as url:
        port = int(url.rsplit(":", 1)[1])
        monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": port, "problem": ""})
        assert gateway.sync_keys() == []
        gateway.keys_due.clear()
        done = await load(rig)
        assert done.status == "done", done.error
        assert gateway.keys_due.is_set(), "the slot's change makes the keys due"
        launch = rig.runtime.state.slot("main").launch_id
        [held] = gateway.sync_keys()
        assert (held["endpoint"], held["ends"], held["launch"]) == ("openrouter", KEY[-4:], launch)
        assert [each["why"] for each in used_by_gateway(rig)] == [f"launch {launch}: cloud: Example Coder"]
        gateway.sync_keys()
        assert len(used_by_gateway(rig)) == 1, "a key already held for the launch is not read again"
        rig.clock.advance(60)
        rig.kernel.secrets.put("endpoint/openrouter", "key", "made-up-openrouter-key-two", actor=YOU)
        assert gateway.keys_due.is_set()
        [replaced] = gateway.sync_keys()
        assert replaced["ends"] == "-two"
        async with rig.kernel.operations.running():
            unloading = await rig.kernel.operations.start("runtime.unload", {"slot": "main"}, actor=YOU)
            with anyio.fail_after(30):
                await rig.kernel.operations.wait(unloading.id)
        assert gateway.sync_keys() == []
        assert owner(url, "GET", "keys", token=local_token(rig.kernel.home)).json() == {"keys": []}


@pytest.mark.anyio
async def test_a_gateway_started_again_gets_the_key_at_the_next_look(
    rig: Rig, openrouter: FakeOpenRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    gateway: Gateway = rig.kernel.parts["gateway"]
    await load(rig)
    for _ in range(2):  # the first gateway, then one started again with nothing in memory
        with gateway_served(Routes(), tmp_path, token=local_token(rig.kernel.home)) as url:
            port = int(url.rsplit(":", 1)[1])
            monkeypatch.setattr(gateway, "status", lambda port=port: {"state": "running", "port": port, "problem": ""})
            [held] = gateway.sync_keys()
            assert held["endpoint"] == "openrouter"


@pytest.mark.anyio
async def test_a_request_for_a_cloud_slot_waits_while_its_key_is_not_there_and_goes_once_it_is() -> None:
    routes = Routes()
    keys = Keys()
    routes.keyed = keys.has
    slot = {
        "status": "ready", "busy": False, "provider": "endpoint", "endpoint": "openrouter", "launch": 7,
        "base_url": "http://127.0.0.1:9/api/v1", "model_name": "example-vendor/example-coder", "preset": "c",
    }  # fmt: skip
    routes.update({"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main"})
    found, why = await routes.ready("agent", 0.3)
    assert found is None
    assert "does not hold the key of openrouter" in why
    keys.put("openrouter", KEY, 6, "")
    assert (await routes.ready("agent", 0.3))[0] is None, "a key held for another launch is not this launch's"

    async def later() -> None:
        await anyio.sleep(0.3)
        keys.put("openrouter", KEY, 7, "")

    async with anyio.create_task_group() as group:
        group.start_soon(later)
        found, _ = await routes.ready("agent", 5)
    assert found is not None
    assert (found.endpoint, found.launch, found.serving) == ("openrouter", 7, True)


def test_a_key_in_a_request_is_replaced_in_its_record(engine: tuple[int, Path], tmp_path: Path) -> None:  # noqa: F811
    keys = Keys()
    keys.put("openrouter", KEY, 1, "")
    found = Routes()
    found.update(table(engine[0]))
    with gateway_served(found, tmp_path, keys=keys) as url:
        body = {**ASKED, "messages": [{"role": "user", "content": f"my key is {KEY}, keep it"}]}
        answer = httpx2.post(f"{url}/v1/chat/completions", json=body, timeout=30)
        assert answer.status_code == 200, answer.text
    [record] = recorded(tmp_path)
    kept = json.dumps(record, ensure_ascii=False)
    assert KEY not in kept
    assert f"my key is …{KEY[-4:]}, keep it" in kept
    assert keys.scrub(f"echo {KEY}!") == f"echo …{KEY[-4:]}!"
