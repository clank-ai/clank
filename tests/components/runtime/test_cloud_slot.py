"""Design 0016 §7 and §14 (decisions 0105 and 0107): the main slot runs a cloud preset in an engine's place. Its load
plans the connection (the provider, its agreement, its key, the model in the provider's list), starts nothing on this
machine, passes its health with the key accepted and one tiny request whose cost is kept, and leaves the slot ready with
a route the gateway follows (the launch keeps it, never a key; its reach and agreement read live); without a key or the
agreement the plan refuses, saying what to do. A switch from an engine stops the engine first, and back starts it after;
a failed health returns to the last configuration that worked. After a restart of the service the slot stays ready while
its record, agreement and key remain; the watch asks for the key now and then, a refused key failing the slot and an
unanswered one leaving it ready, marked. A model is usable when the main slot is ready, or a preset for it can load now:
an engine preset whose engine is installed and whose model is downloaded, or a cloud preset whose provider is agreed and
whose key is set; with none, the answer says to add one."""

import json
from collections.abc import Iterator
from typing import Any

import anyio
import httpx2
import pytest

from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import KEY, FakeOpenRouter

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
                            "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip


@pytest.fixture
def cloud(rig: Rig, openrouter: FakeOpenRouter) -> Iterator[Rig]:
    """The rig with OpenRouter agreed, its key set and a cloud preset; any engine started stopped afterwards."""
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    yield rig
    slot = rig.runtime.state.slot("main")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


async def run(rig: Rig, type: str, **params: str) -> Operation:
    started = await rig.kernel.operations.start(type, {"slot": "main", **params}, actor=YOU)
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(started.id)


def logged(rig: Rig, operation: Operation) -> str:
    return "\n".join(line.text for line in rig.kernel.operations.log_lines(operation.id))


async def test_a_load_of_a_cloud_preset_starts_nothing_here_and_leaves_the_slot_ready_with_its_route(
    cloud: Rig, openrouter: FakeOpenRouter
) -> None:
    async with cloud.kernel.operations.running():
        done = await run(cloud, "runtime.load", preset="cloud: Example Coder")
    assert done.status == "done", done.error
    assert [step.name for step in done.steps] == ["plan", "start", "health", "measure"]
    said = logged(cloud, done)
    assert "nothing starts on this machine" in said
    assert "OK in" in said
    slot = cloud.runtime.state.slot("main")
    assert (slot.status, slot.preset, slot.pid, slot.port, slot.host) == (
        "ready", "cloud-example-coder", None, None, None
    )  # fmt: skip
    launch = cloud.runtime.state.launch(slot.launch_id or 0)
    assert (launch.endpoint, launch.engine, launch.outcome, launch.cost_usd) == ("openrouter", "", "ready", 0.000021)
    [tiny] = openrouter.chats()
    assert tiny.body["model"] == CODER
    assert tiny.body["max_tokens"] == 16
    assert tiny.body["provider"] == {"data_collection": "deny"}
    assert tiny.headers["authorization"] == f"Bearer {KEY}"
    route = cloud.runtime.route("main")
    assert {key: route[key] for key in ("provider", "endpoint", "base_url", "model_name", "reach", "agreed")} == {
        "provider": "endpoint", "endpoint": "openrouter", "base_url": openrouter.url, "model_name": CODER,
        "reach": "cloud", "agreed": True,
    }  # fmt: skip
    assert (route["launch"], route["read_timeout"], route["engine"], route["port"]) == (launch.id, 600, None, None)
    assert route["adds"] == {"provider": {"data_collection": "deny"}}
    assert route["prices"] == pytest.approx({"in": 3e-7, "out": 1.2e-6, "cached_in": 3e-8})
    assert (route["context"], route["output"], route["images"], route["status"]) == (65536, 16384, False, "ready")
    assert KEY not in json.dumps(route)
    assert KEY not in json.dumps(launch.model_dump(mode="json"))
    assert cloud.runtime.state.slot("main").last_good is not None


async def test_the_route_reads_the_agreement_live_so_withdrawing_it_applies_at_once(cloud: Rig) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")
    cloud.runtime.endpoints.change("openrouter", {"agreed": ""}, actor=YOU)
    assert cloud.runtime.route("main")["agreed"] is False


async def test_an_engines_route_says_its_provider_and_reach(rig: Rig) -> None:
    async with rig.kernel.operations.running():
        done = await run(rig, "runtime.load", preset="fake KVMem")
    try:
        assert done.status == "done", done.error
        route = rig.runtime.route("main")
        assert (route["provider"], route["reach"], route["endpoint"], route["base_url"]) == (
            "engine", "this-machine", None, None
        )  # fmt: skip
    finally:
        slot = rig.runtime.state.slot("main")
        LocalHost().stop(ProcessIdentity("local", slot.pid or 0, slot.started or "", slot.command or ""), 5)


@pytest.mark.parametrize(
    ("missing", "words"),
    [
        ("key", "no key is set for openrouter: Providers and models, k; or clank endpoint key openrouter"),
        ("agreement", "openrouter is not agreed to: Add a model, or clank endpoint add openrouter, asks you first"),
    ],
)
async def test_without_a_key_or_the_agreement_the_plan_refuses_saying_what_to_do(
    cloud: Rig, openrouter: FakeOpenRouter, missing: str, words: str
) -> None:
    if missing == "key":
        cloud.kernel.secrets.remove("endpoint/openrouter", actor=YOU)
    else:
        cloud.runtime.endpoints.change("openrouter", {"agreed": ""}, actor=YOU)
    async with cloud.kernel.operations.running():
        done = await run(cloud, "runtime.load", preset="cloud-example-coder")
    assert done.status == "failed"
    assert words in (done.error or "")
    assert openrouter.chats() == []
    assert cloud.runtime.state.slot("main").status == "stopped"


async def test_a_model_the_provider_no_longer_lists_is_refused_at_the_plan(cloud: Rig) -> None:
    cloud.preset("cloud-gone", {**CLOUD, "title": "cloud gone", "model": "example-vendor/gone"})
    async with cloud.kernel.operations.running():
        done = await run(cloud, "runtime.load", preset="cloud gone")
    assert done.status == "failed"
    assert "OpenRouter lists no model example-vendor/gone" in (done.error or "")


async def test_a_switch_from_an_engine_stops_it_first_and_back_starts_it_after(
    cloud: Rig, openrouter: FakeOpenRouter
) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="fake KVMem")
        engine = cloud.runtime.state.slot("main")
        identity = ProcessIdentity("local", engine.pid or 0, engine.started or "", engine.command or "")
        to_cloud = await run(cloud, "runtime.switch", preset="cloud-example-coder")
        assert to_cloud.status == "done", to_cloud.error
        assert not LocalHost().alive(identity), "the engine was stopped"
        assert cloud.runtime.state.slot("main").preset == "cloud-example-coder"
        back = await run(cloud, "runtime.switch", preset="fake KVMem")
    assert back.status == "done", back.error
    slot = cloud.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("ready", "fake-kvmem")
    assert "nothing stops at OpenRouter" in logged(cloud, back)
    launches = cloud.runtime.state.launches(5)
    assert [(launch.preset, launch.outcome) for launch in launches[:2]] == [
        ("fake-kvmem", "ready"), ("cloud-example-coder", "stopped")
    ]  # fmt: skip


async def test_a_failed_health_returns_to_the_last_configuration_that_worked(
    cloud: Rig, openrouter: FakeOpenRouter
) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="fake KVMem")
        openrouter.play("no credits")
        done = await run(cloud, "runtime.switch", preset="cloud-example-coder")
    assert done.status == "failed"
    assert "Your OpenRouter credits are used up" in (done.error or "")
    assert "back to fake KVMem, which runs again" in (done.error or "")
    slot = cloud.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("ready", "fake-kvmem")


async def test_unloading_a_cloud_slot_stops_nothing_at_the_provider(cloud: Rig) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")
        done = await run(cloud, "runtime.unload")
    assert done.status == "done", done.error
    slot = cloud.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("stopped", None)
    assert cloud.runtime.state.launch(cloud.runtime.state.launches(1)[0].id).outcome == "stopped"


async def test_the_cloud_slot_stays_ready_across_a_restart_of_the_service(cloud: Rig) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")
    await cloud.runtime.adopt()
    slot = cloud.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("ready", "cloud-example-coder")
    cloud.kernel.secrets.remove("endpoint/openrouter", actor=YOU)
    await cloud.runtime.adopt()
    slot = cloud.runtime.state.slot("main")
    assert slot.status == "stopped"
    assert "no key is set for openrouter" in slot.reason


async def test_a_key_refused_at_the_watch_fails_the_slot(cloud: Rig, openrouter: FakeOpenRouter) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")
        await cloud.runtime.watch_once(health=True)
        assert cloud.runtime.state.slot("main").status == "ready"
        openrouter.key = "another-made-up-key"
        await cloud.runtime.watch_once(health=True)
    slot = cloud.runtime.state.slot("main")
    assert slot.status == "failed"
    assert "OpenRouter refused the key: it may have been deleted; set a new one" in slot.reason
    assert cloud.runtime.state.launch(cloud.runtime.state.launches(1)[0].id).outcome == "stopped"
    restarts = [op for op in cloud.kernel.operations.find(limit=20) if op.type == "runtime.restart"]
    assert restarts == [], "an engine's crash rule never applies"


async def test_a_provider_that_does_not_answer_the_watch_leaves_the_slot_ready_marked(
    cloud: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")

    def unreachable(*args: Any, **kwargs: Any) -> httpx2.Response:
        raise httpx2.ConnectError("made-up: the network is down")

    monkeypatch.setattr("clank.components.runtime.endpoints.httpx2.request", unreachable)
    await cloud.runtime.watch_once(health=True)
    slot = cloud.runtime.state.slot("main")
    assert slot.status == "ready"
    assert slot.reason.startswith("not reached since ")


async def test_the_runtime_settings_name_the_cloud_watch_and_the_fallback_preset(rig: Rig) -> None:
    settings = rig.runtime.settings()
    assert (settings.cloud_health_seconds, settings.fallback_preset) == (300, "daily-262k")


def usable(rig: Rig) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as http:
        answer = http.get("/api/v1/runtime/usable", headers={"Authorization": "Bearer t"})
    assert answer.status_code == 200, answer.text
    found: dict[str, Any] = answer.json()
    return found


async def test_with_nothing_installed_and_no_provider_no_model_is_usable_and_it_says_what_to_do(rig: Rig) -> None:
    rig.runtime.state.remove_install("kvmem-llamacpp", "v0.16.0-rc1", "local")
    found = usable(rig)
    assert found == {
        "usable": False,
        "why": "no model runs in the main slot, and no preset for it can load here: add one (Add a model)",
        "main": {"status": "stopped", "preset": None, "title": "", "provider": ""},
        "candidates": [],
    }


async def test_a_cloud_preset_with_its_key_is_a_candidate(cloud: Rig) -> None:
    cloud.runtime.state.remove_install("kvmem-llamacpp", "v0.16.0-rc1", "local")
    found = usable(cloud)
    assert found["usable"] is True
    assert found["candidates"] == [
        {"preset": "cloud-example-coder", "title": "cloud: Example Coder", "provider": "cloud openrouter"}
    ]
    cloud.kernel.secrets.remove("endpoint/openrouter", actor=YOU)
    assert usable(cloud)["usable"] is False


async def test_an_engine_preset_whose_model_is_downloaded_is_a_candidate(rig: Rig) -> None:
    found = usable(rig)
    assert found["usable"] is True
    assert {"preset": "fake-kvmem", "title": "fake KVMem", "provider": "kvmem-llamacpp v0.16.0-rc1"} in found[
        "candidates"
    ]


async def test_the_main_slot_ready_is_usable(cloud: Rig) -> None:
    async with cloud.kernel.operations.running():
        await run(cloud, "runtime.load", preset="cloud-example-coder")
    found = usable(cloud)
    assert found["usable"] is True
    assert found["main"] == {"status": "ready", "preset": "cloud-example-coder", "title": "cloud: Example Coder",
                             "provider": "cloud openrouter"}  # fmt: skip
    assert found["why"] == "the main slot runs cloud: Example Coder"
