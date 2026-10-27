"""Design 0014 §3 (decision 0071, option (a)): on Docker Engine the edge reaches the gateway through its socket. The
platform adapter's name decides the edge's way: `docker-engine` gets the socket, its folder mounted read-only at
/run/clank and the edge running as the owner; every other adapter (Docker Desktop, on every system) keeps the host's
loopback, exactly as before. Opening a workspace whose folder holds the gateway's socket folder, or is inside it, is
refused, saying why; a socket folder inside a workspace's folder keeps every workspace from opening on Docker Engine,
naming that workspace and `socket_folder`. While the gateway runs, opening a workspace on Docker Engine asks the
gateway's health through the edge, and makes the edge again when it does not answer; one that still does not answer
refuses the opening, saying why. These run on every system: the gateway is told it is on Linux, its socket folder a
short one of the test's own."""

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.gateway import sockets
from clank.components.gateway.service import Gateway
from clank.components.workspaces import edge as workspaces_edge
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import edge_spec, image_tag, names
from clank.components.workspaces.service import Workspaces
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
REFUSED = "no answer: [Errno 111] Connection refused"


class Engine(FakePlatform):
    """The fake platform under Docker Engine's adapter name."""

    NAME = "docker-engine"
    LABEL = "Fake Docker Engine"


class Desktop(FakePlatform):
    """The fake platform under Docker Desktop's adapter name."""

    NAME = "docker-desktop"
    LABEL = "Fake Docker Desktop"


@contextlib.contextmanager
def opened(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    """A kernel whose Docker is `platform`."""
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    try:
        yield kernel
    finally:
        kernel.close()


@pytest.fixture
def engine() -> Engine:
    return Engine(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    with opened(home, clock, engine, monkeypatch) as found:
        yield found


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "work" / "My Project"
    found.mkdir(parents=True)
    return found


def on_linux(kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The gateway as on Linux, its socket folder `folder` (its settings say so; it is not started): its socket."""
    monkeypatch.setattr(sockets, "LINUX", True)
    settings = {"schema": "gateway/1", "start": False, "socket_folder": str(folder)}
    (kernel.home.config / "gateway.json").write_text(json.dumps(settings) + "\n", encoding="utf-8")
    kernel.settings.reload_changed()
    return folder.resolve() / "gateway.sock"


def gateway_runs(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway's status says it runs."""
    gateway: Gateway = kernel.parts["gateway"]
    real = gateway.status
    monkeypatch.setattr(gateway, "status", lambda: {**real(), "state": "running"})


def workspaces(kernel: Kernel) -> Workspaces:
    part: Workspaces = kernel.parts["workspaces"]
    return part


async def run(kernel: Kernel, kind: str, params: dict[str, Any]) -> Operation:
    started = await kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(30):
        return await kernel.operations.wait(started.id)


def through_the_edge(platform: FakePlatform, edge: str) -> list[str]:
    """What was done to the edge, its health asked through it said as `ask`."""
    return ["ask" if call.startswith(f"in {edge}:") else call for call in platform.calls if edge in call]


async def test_on_docker_engine_the_edge_forwards_to_the_gateways_socket_as_the_owner(
    kernel: Kernel, engine: Engine, folder: Path, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket = on_linux(kernel, short / "sockets", monkeypatch)
    monkeypatch.setattr(workspaces_edge, "owner_ids", lambda: "1001:1002")
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    edge = names(kernel.home.id).edge
    assert engine.specs[edge] == edge_spec(
        kernel.home.id, image_tag(), gateway_port=18210, proxy_port=18211, socket_folder=str(socket.parent),
        user="1001:1002",
    )  # fmt: skip
    assert socket.parent.is_dir(), "made ready before the edge mounts it, though the gateway does not run"
    assert "ask" not in through_the_edge(engine, edge), "the gateway does not run: its health is not asked"


async def test_on_docker_desktop_the_edge_still_forwards_to_the_hosts_loopback(
    home: Home, clock: FakeClock, folder: Path, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop = Desktop(state="running")
    with opened(home, clock, desktop, monkeypatch) as kernel:
        on_linux(kernel, short / "sockets", monkeypatch)  # Docker Desktop on Linux too
        gateway_runs(kernel, monkeypatch)
        async with kernel.operations.running():
            done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert done.status == "done", done.error
        edge = names(kernel.home.id).edge
        assert desktop.specs[edge] == edge_spec(kernel.home.id, image_tag(), gateway_port=18210, proxy_port=18211)
        assert "ask" not in through_the_edge(desktop, edge), "nothing is asked through it"


async def test_a_workspace_folder_that_holds_the_socket_folder_is_refused(
    kernel: Kernel, engine: Engine, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And one inside it: its container would see the gateway's socket, and go around the edge."""
    socket = on_linux(kernel, short / "work" / "sockets", monkeypatch)
    inside = socket.parent / "notes"
    inside.mkdir(parents=True)
    async with kernel.operations.running():
        holding = await run(kernel, "workspaces.open", {"folder": str(short / "work"), "yes": True})
        within = await run(kernel, "workspaces.open", {"folder": str(inside), "yes": True})
    assert holding.status == "failed"
    assert f"holds the gateway's socket folder ({socket.parent})" in holding.error
    assert "socket_folder in config/gateway.json" in holding.error, "it says what to do"
    assert within.status == "failed"
    assert f"is inside the gateway's socket folder ({socket.parent})" in within.error
    assert kernel.settings.records("workspace") == [], "no workspace is made"
    assert "holds the gateway's socket folder" in workspaces(kernel).folder_view(str(short / "work"))["problem"]


async def test_a_socket_folder_inside_a_workspaces_folder_keeps_every_workspace_from_opening_saying_which(
    kernel: Kernel, engine: Engine, folder: Path, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paper = (short / "paper").resolve()
    paper.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(paper)}, base=None, actor=YOU)  # before the folder moved
    socket = on_linux(kernel, paper / "sockets", monkeypatch)
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "failed"
    assert f"the gateway's socket folder {socket.parent} is inside the folder of the workspace paper" in done.error
    assert "socket_folder in config/gateway.json" in done.error
    assert f"run {names(kernel.home.id).edge}" not in engine.calls, "the edge is not made"


async def test_an_edge_that_no_longer_reaches_the_gateway_is_made_again(
    kernel: Kernel, engine: Engine, folder: Path, short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its socket's folder removed and made again while it ran, say: the edge keeps the folder it mounted."""
    socket = on_linux(kernel, short / "sockets", monkeypatch)
    gateway_runs(kernel, monkeypatch)
    answers = [Answer(1, "", REFUSED), Answer(0, "", "")]
    asked: list[list[str]] = []

    def inside(argv: list[str], given: bytes | None) -> Answer:
        asked.append(argv)
        return answers.pop(0)

    engine.inside = inside
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert done.status == "done", done.error
        home = names(kernel.home.id)
        inner = home.inner("my-project")
        assert through_the_edge(engine, home.edge) == [
            f"run {home.edge}", f"join {home.edge} {inner}", "ask", f"stop {home.edge}", f"remove {home.edge}",
            f"run {home.edge}", f"join {home.edge} {inner}", "ask",
        ]  # fmt: skip
        assert asked[0][:2] == ["python3", "-c"]
        assert asked[0][3] == "18210", "the gateway's port, inside the edge"
        log = " ".join(line.text for line in kernel.operations.log_lines(done.id))
        assert f"the edge does not reach the gateway ({REFUSED}): it is made again" in log
        answers[:] = [Answer(1, "", REFUSED), Answer(1, "", REFUSED)]
        again = await run(kernel, "workspaces.open", {"folder": str(folder)})
    assert again.status == "failed"
    assert f"the edge does not reach the gateway through its socket {socket}, even made again" in again.error
    assert "clank gateway status" in again.error, "it says where to look"
