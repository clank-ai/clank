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
2026-10-23); one held open for good is left naming a process that ended, which says stopped. A restart is never half
done: a stop that fails leaves the gateway running and says why, and a state file that cannot be written keeps the
gateway's process in memory, so it is never started twice, until the file can be written. Design 0014 §3: on Linux the
service starts the gateway with its socket folder, its status names the socket (or why there is none), and a gateway
running without its socket is started again once no request is in flight, once; elsewhere nothing changes."""

import json
import logging
import os
import stat
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import httpx2
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.gateway import service as gateway_service
from clank.components.gateway import sockets
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.service import Gateway, HoldError
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import HostError, ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.kernel import files
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
        "network": {},
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
    (rig.kernel.home.config / "gateway.json").write_text(
        json.dumps({"schema": "gateway/1", "port": port, "proxy_port": free_port()}) + "\n"
    )
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


class FakeHost:
    """This machine as the gateway's part sees it: each process it starts runs until it is stopped; a stop refused
    when `refused` says why."""

    def __init__(self) -> None:
        self.running: set[int] = set()
        self.started = 0
        self.refused = ""
        self.lingering = 0  # how many more times the port reads held after a stop (a process ending slowly)
        self.argv: list[list[str]] = []  # each process's command line, in the order started

    def spawn(self, argv: Sequence[str], env: Mapping[str, str], cwd: str, log: Path) -> ProcessIdentity:
        self.argv.append(list(argv))
        self.started += 1
        pid = 4000 + self.started
        self.running.add(pid)
        return ProcessIdentity("local", pid, f"{pid}.0", "clank gateway")

    def alive(self, identity: ProcessIdentity) -> bool:
        return identity.pid in self.running

    def stop(self, identity: ProcessIdentity, seconds: float) -> str:
        if self.refused:
            raise HostError(self.refused)
        self.running.discard(identity.pid)
        return "killed"

    def listener(self, port: int) -> str | None:
        if self.lingering:
            self.lingering -= 1
            return "python.exe (process 24244)"
        return None


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> FakeHost:
    """The fake machine every gateway part of the test starts its process on; the waits between tries short."""
    found = FakeHost()
    monkeypatch.setattr(Gateway, "_host", lambda self: found)
    monkeypatch.setattr(files, "WAITS", (0.01, 0.01))
    monkeypatch.setattr(gateway_service, "FREE_POLL_SECONDS", 0.01)
    return found


def test_a_restart_whose_stop_fails_leaves_the_gateway_running_and_says_why(
    rig: Rig, http: TestClient, host: FakeHost
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    first = gateway.ensure()
    host.refused = "the process could not be ended: access denied"
    answer = http.post("/api/v1/gateway/restart", headers=AUTH)
    assert answer.status_code == 200, answer.text
    found = answer.json()
    assert (found["state"], found["pid"]) == ("running", first["pid"])
    assert "access denied" in found["problem"]
    host.refused = ""
    again = gateway.restart()
    assert (again["state"], again["problem"], host.running) == ("running", "", {again["pid"]})
    assert again["pid"] != first["pid"]


def test_a_restart_waits_for_the_stopped_gateways_port_to_be_free_before_it_starts_the_next(
    rig: Rig, host: FakeHost
) -> None:
    """On Windows the stopped gateway's process lets go of its port a moment later: the owner's restart of 2026-10-26
    found it held and failed, and model requests failed until the service started the gateway again by itself."""
    gateway: Gateway = rig.kernel.parts["gateway"]
    first = gateway.ensure()
    host.lingering = 3
    again = gateway.restart()
    assert (again["state"], again["problem"]) == ("running", "")
    assert again["pid"] != first["pid"]
    assert host.lingering == 0, "it waited until the port was free"


def test_a_gateway_whose_state_file_cannot_be_written_is_kept_in_memory_and_never_started_twice(
    rig: Rig, host: FakeHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    kept, real, held = rig.kernel.home.state / "gateway.json", os.replace, [True]

    def replace(source: str | Path, target: str | Path) -> None:
        if held[0] and Path(target) == kept:
            raise PermissionError(5, "Access is denied")
        real(source, target)

    monkeypatch.setattr(os, "replace", replace)
    first = gateway.ensure()
    assert (first["state"], kept.exists()) == ("running", False)
    assert (gateway.ensure()["pid"], host.started) == (first["pid"], 1), "adopted from memory, not started again"
    held[0] = False
    gateway.ensure()  # the file is written at the next look
    assert json.loads(kept.read_text(encoding="utf-8"))["pid"] == first["pid"]
    assert (Gateway(rig.kernel).ensure()["pid"], host.started) == (first["pid"], 1), "a restarted service adopts it"


def test_a_stop_whose_state_file_stays_held_says_stopped_and_the_next_start_takes_its_place(
    rig: Rig, host: FakeHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    kept, real = rig.kernel.home.state / "gateway.json", Path.unlink
    first = gateway.ensure()

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == kept:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert gateway.stop() == "killed"
    assert json.loads(kept.read_text(encoding="utf-8"))["pid"] == first["pid"], "left, naming the process that ended"
    assert gateway.status()["state"] == "stopped"
    second = gateway.ensure()
    assert (second["state"], host.running) == ("running", {second["pid"]})
    assert json.loads(kept.read_text(encoding="utf-8"))["pid"] == second["pid"]


def gateway_settings(rig: Rig, **values: Any) -> None:
    """The gateway's settings file with these values, read at once."""
    (rig.kernel.home.config / "gateway.json").write_text(json.dumps({"schema": "gateway/1", **values}) + "\n")
    rig.kernel.settings.reload_changed()


def test_on_linux_the_service_starts_the_gateway_with_its_socket(
    rig: Rig, host: FakeHost, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0014 §3: on Linux the gateway's start names its socket folder, checked and made the owner's alone, and
    its state keeps the socket; a folder that may not be used starts it without one, and its status says why."""
    monkeypatch.setattr(sockets, "LINUX", True)  # what the service does on Linux, wherever the test runs
    folder = short / "sockets"
    gateway_settings(rig, socket_folder=str(folder))
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.ensure()
    assert host.argv[-1][-2:] == ["--socket-folder", str(folder.resolve())]
    kept = json.loads((rig.kernel.home.state / "gateway.json").read_text(encoding="utf-8"))
    assert kept["socket"] == str(folder.resolve() / "gateway.sock")
    assert folder.is_dir(), "made before the gateway starts"
    if sys.platform == "linux":
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, "the owner's alone"
    gateway.stop()
    gateway_settings(rig, socket_folder=str(rig.kernel.home.root / "sockets"))
    started = gateway.ensure()
    assert "--socket-folder" not in host.argv[-1]
    assert started["socket"] is None
    assert "it was started without one: the gateway's socket folder" in started["socket_problem"]
    assert "is inside Clank's own folder, CLANK_HOME" in started["socket_problem"]


def test_the_gateways_status_names_its_socket(
    rig: Rig, http: TestClient, host: FakeHost, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0014 §3: `GET /gateway` and `clank gateway status` name the socket the edge reaches the gateway by, or
    say why there is none."""
    monkeypatch.setattr(sockets, "LINUX", True)
    gateway_settings(rig, socket_folder=str(short))
    there: set[Path] = set()
    monkeypatch.setattr(sockets, "is_socket", lambda path: path in there)
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.ensure()
    path = short.resolve() / "gateway.sock"
    waiting = http.get("/api/v1/gateway", headers=AUTH).json()
    assert (waiting["socket"], waiting["socket_problem"]) == (
        None, f"its socket {path} is not there: it is started again once no request is in flight"
    )  # fmt: skip
    there.add(path)  # the gateway made it
    shown = http.get("/api/v1/gateway", headers=AUTH).json()
    assert (shown["socket"], shown["socket_problem"]) == (str(path), "")
    monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7725", "t", name="cli", http=http))
    said = CliRunner().invoke(main, ["gateway", "status"])
    assert said.exit_code == 0, said.output
    assert f"gateway: its socket, the edge's way in on Docker Engine: {path}" in said.output
    there.clear()
    said = CliRunner().invoke(main, ["gateway", "status"])
    assert f"gateway: no socket for the edge: its socket {path} is not there" in said.output


def test_off_linux_the_gateway_has_no_socket(rig: Rig, host: FakeHost, monkeypatch: pytest.MonkeyPatch) -> None:
    """Design 0014 §3: Docker Desktop reaches the host's loopback, so on Windows and macOS nothing changes."""
    monkeypatch.setattr(sockets, "LINUX", False)
    gateway: Gateway = rig.kernel.parts["gateway"]
    started = gateway.ensure()
    assert "--socket-folder" not in host.argv[-1]
    assert (started["socket"], started["socket_problem"]) == (None, "")
    assert gateway.socket_path() is None
    assert gateway.edge_socket() is None
    assert gateway.keep_socket() == ""


def test_a_gateway_running_without_its_socket_is_started_again_once_idle(
    rig: Rig, host: FakeHost, short: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Design 0014 §3: one started before the gateway listened on a socket and adopted as it is, and one whose socket's
    folder was removed while it ran, are started again once no request is in flight; once only, so one that cannot
    make its socket is not started again and again, and a file where the socket goes is left, saying so."""
    monkeypatch.setattr(sockets, "LINUX", True)
    gateway_settings(rig, socket_folder=str(short))
    path = short.resolve() / "gateway.sock"
    there: set[Path] = set()
    monkeypatch.setattr(sockets, "is_socket", lambda found: found in there)
    gateway: Gateway = rig.kernel.parts["gateway"]
    flying: list[dict[str, Any]] = [{"id": "r-1"}]
    monkeypatch.setattr(gateway, "activity", lambda: {"state": "running", "problem": "", "requests": list(flying)})
    host.running.add(4999)  # a gateway from before, adopted: its state names no socket
    older = {"host": "local", "pid": 4999, "started": "4999.0", "command": "clank gateway", "port": 18210}
    (rig.kernel.home.state / "gateway.json").write_text(json.dumps(older) + "\n", encoding="utf-8")
    before = "it was started before the gateway listened on a socket"
    assert gateway.status()["socket_problem"] == f"{before}: it is started again once no request is in flight"
    assert (gateway.keep_socket(), host.started) == ("", 0), "a request in flight: not now"
    flying.clear()
    with caplog.at_level(logging.WARNING, logger="clank.components.gateway.service"):
        assert gateway.keep_socket() == f"started again without a request in flight: {before}"
    assert (host.started, 4999 in host.running) == (1, False)
    assert f"the gateway runs without its socket ({before}): it is started again" in caplog.text
    there.add(path)  # the gateway started again made its socket
    assert (gateway.keep_socket(), gateway.status()["socket"]) == ("", str(path))
    there.clear()  # its folder removed while it ran
    assert gateway.keep_socket() == f"started again without a request in flight: its socket {path} is not there"
    assert host.started == 2
    assert gateway.keep_socket() == "", "started again for its socket, it still has none: not again"
    assert host.started == 2
    assert "started again for it, it still has none" in gateway.status()["socket_problem"]
    gateway.stop()
    gateway.ensure()
    path.write_text("the owner's\n", encoding="utf-8")  # a file where the socket goes
    assert gateway.keep_socket() == ""
    assert host.started == 3
    assert (
        gateway.status()["socket_problem"]
        == f"{path} is there and is not its socket: remove it, then clank gateway restart"
    )
