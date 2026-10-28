"""Design 0014 §3, §10 and design 0016 §8, on Docker Engine when asked (`-m docker`): the owner's first test on Linux,
from the agent's side. OpenCode, as Clank configures it in a workspace's container, asks its model through the edge
with its workspace's key; the edge forwards to the gateway's socket, in the folder it mounts read-only; the gateway,
made and served as its process makes and serves it on Linux (its TCP socket and its Unix socket, the routes the service
gives it followed as it follows them, the provider's key held for the launch), forwards the request to OpenRouter (the
fake, playing its recording) with the owner's key and the listed model, and OpenCode prints the answer that came back.
Nothing in it is a stand-in but OpenRouter: the image, the edge, the gateway's application and OpenCode are Clank's."""

import contextlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from clank.components.gateway.keys import Keys
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway, follow
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.components.workspaces.service import Workspaces
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.service import server_config
from tests.docker.conftest import gateway_port
from tests.docker.test_escape import on_docker_engine, opened
from tests.fakes.openrouter import KEY, FakeOpenRouter, served
from tests.support.cloud import CODER, CloudBench
from tests.support.served import free_port

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
YOU = Actor(kind="user", via="console")
PRESET = "cloud-example-coder"
ASKED = "Reply with OK."
OPENCODE_SECONDS = 300  # its first start in a container reads its own files for a while


@pytest.fixture
def openrouter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenRouter]:
    """OpenRouter, played by the fake on this machine, the adapter's URL pointed at it."""
    with served() as fake:
        monkeypatch.setattr(OpenRouter, "URL", fake.url)
        yield fake


@contextlib.contextmanager
def gateway(machine: Kernel, port: int, folder: Path) -> Iterator[Routes]:
    """The gateway as its process makes it on Linux (`server.main`): its application over routes followed from the
    service every second, the provider's key held for the main slot's launch as the service hands it over, served on
    127.0.0.1 at the port and on its socket in the folder (`sockets.listeners`); its routes."""
    if sys.platform == "win32":
        raise AssertionError("the gateway's socket is Linux's")
    from clank.components.gateway.sockets import listeners, remove_sockets

    routes = Routes()
    stop = threading.Event()
    routes.update(machine.parts["gateway"].routes())
    threading.Thread(target=follow, args=(routes, machine.parts["gateway"].routes, stop), daemon=True).start()
    routes.followed = True
    keys = Keys()
    keys.put("openrouter", KEY, int(machine.parts["gateway"].routes()["slots"]["main"]["launch"]), "")
    app = create_gateway(routes, GatewaySettings(port=port), None, keys=keys, port=port)
    listening = listeners(port, folder)
    assert listening.gateway is not None, "the gateway listens on its socket"
    server = uvicorn.Server(server_config(app, "127.0.0.1", port))
    thread = threading.Thread(target=server.run, kwargs={"sockets": listening.served}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield routes
    finally:
        stop.set()
        server.should_exit = True
        thread.join(15)
        remove_sockets(listening.made)


async def test_an_agent_in_its_container_gets_its_answer_from_a_cloud_model_through_the_edge_and_the_gateway(
    machine: Kernel, openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    if sys.platform != "linux":
        pytest.skip("Docker Engine runs on Linux")
    if not on_docker_engine(machine):
        pytest.skip("this machine's Docker is not Docker Engine: its edge reaches the host's loopback")
    bench = CloudBench(machine, openrouter)
    bench.add()
    bench.write_preset(CODER)
    bench.run(PRESET)
    sockets = Path(tempfile.mkdtemp(prefix="clank-gw-"))  # short: a socket's path has at most 107 bytes
    port = free_port()
    gateway_port(machine.home, port, socket_folder=str(sockets))
    machine.settings.reload_changed()
    folder = tmp_path / "cloudy"
    folder.mkdir()
    workspaces: Workspaces = machine.parts["workspaces"]
    try:
        with gateway(machine, port, sockets) as routes:
            async with machine.operations.running():
                name = str((await opened(machine, folder))["workspace"])
            workspaces.allow_cloud(name, True, actor=YOU)
            env = machine.parts["agents"].configure(name)
            routes.update(machine.parts["gateway"].routes())  # the workspace's key, as the next second's routes have it
            argv = workspaces.exec_argv(name, ["opencode", "run", ASKED], env, terminal=False)
            said = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=OPENCODE_SECONDS, check=False)  # fmt: skip
    finally:
        shutil.rmtree(sockets, ignore_errors=True)
    chats = openrouter.chats()
    assert chats, f"OpenRouter heard nothing; OpenCode said: {said.stdout}\n{said.stderr}"
    asked = chats[0]
    assert asked.headers.get("authorization") == f"Bearer {KEY}", "the owner's key, held by the gateway alone"
    assert asked.body["model"] == CODER, "the listed model"
    assert any(ASKED in str(message.get("content")) for message in asked.body["messages"]), "the agent's request"
    assert said.returncode == 0, said.stderr
    assert "OK" in said.stdout, f"OpenCode prints the answer: {said.stdout}\n{said.stderr}"
