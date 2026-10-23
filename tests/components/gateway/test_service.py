"""Design 0004 §2 and design 0001 §6.6: the service tells the gateway its routes (the main slot's state, whether an
operation is changing it, and while an engine runs, its port, its serving setup and version, the model name it answers
to, its preset and the preset's context and output limits, and, design 0012 §4 and decision 0067, the preset's facts,
its engine's and its model's; the role `agent` is the main slot's); it starts the
gateway's process, and after a restart of the service it adopts the one still running instead of starting another;
`clank gateway status` says where it listens and which process it is, and `GET /gateway/activity` what it does now.
Design 0012 §7: `GET /gateway/activity` and `GET /gateway/live` follow the session they are asked for, and its
subagents too when `subagents` asks for them. Design 0012 §9.4 (§11 step 11): the service pauses and resumes a session
in the gateway with its local token, and `GET /gateway/holds` says what is paused and held; a gateway from before
pausing, still running, is never taken for one that paused. A stop forgets the gateway's process though its state file
is held open a moment by another reader (Windows refuses to delete it then: `clank gateway restart` answered 500 on
2026-10-23)."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import httpx2
import pytest
from fastapi.testclient import TestClient

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.service import Gateway, HoldError
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.kernel.access import local_token
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.gateway.test_hold_gateway import holding
from tests.components.gateway.test_server import ASKED, serving
from tests.components.runtime.conftest import Rig
from tests.support.served import free_port

YOU = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client
    slot = rig.runtime.state.slot("main")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


def routes(http: TestClient) -> dict[str, Any]:
    answer = http.get("/api/v1/gateway/routes", headers=AUTH)
    assert answer.status_code == 200, answer.text
    found: dict[str, Any] = answer.json()
    return found


@pytest.mark.anyio
async def test_the_routes_give_the_main_slots_engine_its_model_name_and_its_limits(rig: Rig, http: TestClient) -> None:
    assert routes(http) == {
        "slots": {name: {"status": "stopped", "busy": False, "port": None, "engine": None, "version": None,
                         "model_name": None, "preset": None, "title": None, "context": None, "output": None,
                         "images": None, "thinking": None, "facts": None, "provider": None, "endpoint": None,
                         "adapter": None, "base_url": None, "reach": None, "agreed": None, "launch": None,
                         "read_timeout": None, "adds": None, "prices": None}
                  for name in ("main", "fast", "vision")},
        "roles": {"agent": "main", "completion": "fast", "vision": "vision"},
        "default_slot": "main",
        "demand": {"vision": "on-demand"},
        "workspaces": {},
        "local_only": ["clank_notion_"],
        "local_only_given": False,
        "cost": {"day_usd": 0.0, "month_usd": 0.0, "taken": 0, "run": "", "limit_day_usd": None,
                 "limit_month_usd": None},
    }  # fmt: skip
    rig.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3150)]
    async with rig.kernel.operations.running():
        started = await rig.kernel.operations.start(
            "runtime.load", {"slot": "main", "preset": "fake KVMem small"}, actor=YOU
        )
        with anyio.fail_after(60):
            done = await rig.kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    main = routes(http)["slots"]["main"]
    assert (main["status"], main["busy"], main["port"]) == ("ready", False, rig.port)
    assert (main["engine"], main["version"], main["model_name"]) == ("kvmem-llamacpp", "v0.16.0-rc1", "tiny")
    assert (main["preset"], main["title"], main["context"], main["output"]) == (
        "fake-kvmem-small",
        "fake KVMem small",
        4096,
        16384,
    )
    assert main["images"] is False, "the fake KVMem preset has no projector: its model reads no images (design 0008)"
    assert main["thinking"] == 4096, (
        "its preset's thinking budget, which the Monitor's Watch for reads (design 0012 §8)"
    )
    facts = main["facts"]
    assert facts == rig.runtime.facts("fake-kvmem-small"), "its preset's facts (design 0012 §4, decision 0067)"
    assert (facts["engine"]["window"], facts["engine"]["exact"]["tokens"], facts["model"]["id"]) == (4096, 2048, "tiny")
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert gateway.facts("fake KVMem") == rig.runtime.facts("fake KVMem"), "any preset's, through the gateway's service"


@pytest.mark.anyio
async def test_a_slot_an_operation_is_changing_is_busy(rig: Rig, http: TestClient) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    rig.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3150)]
    async with rig.kernel.operations.running():
        started = await rig.kernel.operations.start("runtime.load", {"slot": "main", "preset": "fake KVMem"}, actor=YOU)
        assert gateway.routes()["slots"]["main"]["busy"] is True
        with anyio.fail_after(60):
            await rig.kernel.operations.wait(started.id)
    assert gateway.routes()["slots"]["main"]["busy"] is False


def test_the_service_starts_the_gateway_adopts_it_after_a_restart_and_says_what_it_does(
    rig: Rig, http: TestClient
) -> None:
    port = free_port()
    (rig.kernel.home.config / "gateway.json").write_text(json.dumps({"schema": "gateway/1", "port": port}) + "\n")
    rig.kernel.settings.reload_changed()
    gateway: Gateway = rig.kernel.parts["gateway"]
    try:
        first = gateway.ensure()
        assert (first["state"], first["port"]) == ("running", port)
        assert gateway.answers(10), "the gateway answers on its port"
        again = Gateway(rig.kernel).ensure()  # the service restarted: a new part, the same process
        assert (again["state"], again["pid"]) == ("running", first["pid"])
        shown = http.get("/api/v1/gateway", headers=AUTH).json()
        assert (shown["state"], shown["pid"], shown["url"]) == ("running", first["pid"], f"http://127.0.0.1:{port}/v1")
        doing = http.get("/api/v1/gateway/activity", headers=AUTH).json()
        assert doing == {"state": "running", "port": port, "problem": "", "requests": [], "served": 0, "last": None,
                         "slots": {}, "guard": {"on": True, "ratio": 0.06}}  # fmt: skip
    finally:
        assert gateway.stop() in ("stopped", "killed")
    assert gateway.status()["state"] == "stopped"
    assert gateway.activity() == {
        "state": "stopped", "port": port, "problem": "", "requests": [], "served": 0, "last": None
    }  # fmt: skip


def test_the_services_activity_and_live_text_follow_one_session(
    rig: Rig, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = free_port()
    with serving(Routes(), GatewaySettings(port=port, hold_seconds=0), tmp_path) as url:
        sent = (
            {"X-Session-Id": "ses_a"},
            {"X-Session-Id": "ses_c", "x-parent-session-id": "ses_a"},
            {"X-Session-Id": "ses_b"},
        )
        for headers in sent:  # no engine runs: each is refused, and is its session's last
            refused = httpx2.post(f"{url}/v1/chat/completions", json=ASKED, headers=headers, timeout=30)
            assert refused.status_code == 503
        gateway: Gateway = rig.kernel.parts["gateway"]
        monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": port, "problem": ""})
        both = {"session": "ses_a", "subagents": "true"}
        live = http.get("/api/v1/gateway/live", params={"session": "ses_a"}, headers=AUTH).json()
        doing = http.get("/api/v1/gateway/activity", params={"session": "ses_a"}, headers=AUTH).json()
        live_both = http.get("/api/v1/gateway/live", params=both, headers=AUTH).json()
        doing_both = http.get("/api/v1/gateway/activity", params=both, headers=AUTH).json()
        newest = http.get("/api/v1/gateway/activity", headers=AUTH).json()
    assert (live["meta"]["session"], live["flying"], live["problem"]) == ("ses_a", False, "")
    assert (doing["last"]["session"], doing["served"]) == ("ses_a", 3)
    assert (live_both["meta"]["session"], live_both["meta"]["parent"]) == ("ses_c", "ses_a"), "its subagent's"
    assert doing_both["last"]["session"] == "ses_c"
    assert newest["last"]["session"] == "ses_b"


def test_the_service_pauses_and_resumes_a_session_in_the_gateway_with_its_token(
    rig: Rig, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    with holding(Routes(), tmp_path, token=local_token(rig.kernel.home)) as url:
        port = int(url.rsplit(":", 1)[1])
        monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": port, "problem": ""})
        paused = gateway.pause("ses_a", "you (console)")
        assert (paused["session"], paused["by"], paused["already"], paused["held"]) == (
            "ses_a", "you (console)", False, []
        )  # fmt: skip
        answer = http.get("/api/v1/gateway/holds", headers=AUTH)
        assert answer.status_code == 200, answer.text
        assert ([each["session"] for each in answer.json()["pauses"]], answer.json()["problem"]) == (["ses_a"], "")
        assert gateway.release("ses_a", "2026-10-20T12:22:00.000Z") == 0
        with pytest.raises(HoldError, match="before"):
            gateway.release("ses_a", "not a time")  # the time reaches the gateway, which reads it
        ended = gateway.resume("ses_a")
        assert ended is not None
        assert (ended["session"], ended["held"]) == ("ses_a", 0)
        assert gateway.resume("ses_a") is None, "not paused"
        assert gateway.holds() == {"pauses": [], "problem": ""}
    monkeypatch.setattr(gateway, "status", lambda: {"state": "stopped", "port": port, "problem": ""})
    with pytest.raises(HoldError, match="the gateway does not run"):
        gateway.pause("ses_a", "you (console)")
    assert gateway.release("ses_a", "2026-10-20T12:22:00.000Z") == 0, "nothing is held where nothing runs"
    assert gateway.holds() == {"pauses": [], "problem": "the gateway does not run"}


def test_a_gateway_from_before_pausing_is_never_taken_for_one_that_paused(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": free_port(), "problem": ""})

    def older(method: str, url: str, **given: Any) -> httpx2.Response:
        """A gateway still running from before this build, adopted by the service: no /holds, FastAPI's own 404."""
        return httpx2.Response(404, json={"detail": "Not Found"}, request=httpx2.Request(method, url))

    monkeypatch.setattr(httpx2, "request", older)
    with pytest.raises(HoldError, match="clank gateway restart"):
        gateway.pause("ses_a", "you (console)")
    with pytest.raises(HoldError, match="clank gateway restart"):
        gateway.resume("ses_a")
    with pytest.raises(HoldError, match="clank gateway restart"):
        gateway.release("ses_a", "2026-10-20T12:22:00.000Z")
    assert "clank gateway restart" in gateway.holds()["problem"]


def test_a_stop_forgets_the_gateway_though_its_file_is_held_open_a_moment(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    kept = rig.kernel.home.state / "gateway.json"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps({"host": "local", "pid": 1, "started": "0", "command": "x", "port": 1}) + "\n")
    monkeypatch.setattr(gateway, "_host", lambda: SimpleNamespace(stop=lambda identity, seconds: "stopped"))
    real, held = Path.unlink, [2]

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == kept and held[0]:
            held[0] -= 1
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert gateway.stop() == "stopped"
    assert not kept.exists()
