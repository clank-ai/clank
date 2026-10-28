"""Design 0004 §3 and §8, design 0002 §3.3 (M4's escape tests), on this machine's Docker when asked (`-m docker`): a
workspace's container sees its folder and nothing else of the machine (its mounts, a subprocess, a symlink that points
out of the folder); from inside it nothing answers but the edge: not the internet (by address or by name, IPv4 or
IPv6), not the machine, not another workspace; the edge answers, forwarding to the gateway's port; and the container
runs as the image's user, with no capability, within its limits. Design 0014 §3 and §4, on Linux: the gateway's
stand-in listens where the gateway does on each platform (on Docker Engine on a socket, in a short folder of its own
that the test's `config/gateway.json` names; elsewhere on 127.0.0.1); on Docker Engine the edge reaches it through that
socket, mounting nothing but its folder (read-only) and Clank's programs, as the owner; and the host's own address on a
workspace's network answers nothing (the probe listens on that address only, never on every address)."""

import contextlib
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.workspaces.sandbox import names
from clank.components.workspaces.service import Workspaces
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.docker.conftest import docker, for_the_agent, gateway_port
from tests.support.served import free_port

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
YOU = Actor(kind="user", via="console")
OPEN_SECONDS = 1800  # the first open builds the image


class Hello(BaseHTTPRequestHandler):
    """The gateway's stand-in: it says who it is."""

    def do_GET(self) -> None:
        body = b"the gateway, through the edge"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if sys.platform != "win32":  # Unix sockets: the type checker knows them only off Windows

    class UnixHello(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        """The gateway's stand-in on a socket, where the gateway listens for the edge on Docker Engine."""

        daemon_threads = True


def on_docker_engine(kernel: Kernel) -> bool:
    """Whether this machine's Docker is Docker Engine, whose edge reaches the gateway through its socket."""
    workspaces: Workspaces = kernel.parts["workspaces"]
    return workspaces.platform.NAME == "docker-engine"


@pytest.fixture
def gateway(machine: Kernel) -> Iterator[int]:
    """A server where the gateway listens, and the settings that name it: on Docker Engine its socket, in a short folder
    of its own (design 0014 §3); elsewhere 127.0.0.1 only. The port the edge forwards."""
    server: socketserver.BaseServer
    folder = None
    if sys.platform != "win32" and on_docker_engine(machine):
        folder = Path(tempfile.mkdtemp(prefix="clank-gw-"))
        server, port = UnixHello(str(folder / "gateway.sock"), Hello), free_port()
        gateway_port(machine.home, port, socket_folder=str(folder))
    else:
        local = ThreadingHTTPServer(("127.0.0.1", 0), Hello)
        server, port = local, local.server_port
        gateway_port(machine.home, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    machine.settings.reload_changed()
    yield int(port)
    server.shutdown()
    server.server_close()
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)


async def opened(kernel: Kernel, folder: Path) -> dict[str, Any]:
    for_the_agent(folder)
    started = await kernel.operations.start("workspaces.open", {"folder": str(folder), "yes": True}, actor=YOU)
    with anyio.fail_after(OPEN_SECONDS):
        done = await kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    return dict(done.result or {})


def inside(container: str, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """A Python script run in the container, as its user, with its arguments."""
    return docker("exec", container, "python3", "-c", script, *arguments, timeout=60)


REACH = """
import socket, sys
host, port, family = sys.argv[1], int(sys.argv[2]), getattr(socket, sys.argv[3])
try:
    address = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)[0][4]
except OSError as error:
    print("no name:", error); raise SystemExit(0)
try:
    socket.create_connection(address[:2], timeout=5).close()
    print("reached")
except OSError as error:
    print("not reached:", error)
"""


def reaches(container: str, host: str, port: int, family: str = "AF_INET") -> bool:
    """Whether a connection from the container reaches a host's port (a name that does not resolve does not)."""
    found = inside(container, REACH, host, str(port), family)
    assert found.returncode == 0, found.stderr
    return found.stdout.strip() == "reached"


async def test_a_container_sees_its_folder_and_nothing_else_of_the_machine(machine: Kernel, tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "mine.txt").write_text("in the folder\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the folder\n", encoding="utf-8")
    with contextlib.suppress(OSError):  # Windows makes symlinks only in developer mode or as an administrator
        os.symlink(tmp_path / "secret.txt", folder / "out.txt")
    async with machine.operations.running():
        container = (await opened(machine, folder))["container"]
    assert docker("exec", container, "cat", "/workspace/mine.txt").stdout == "in the folder\n"
    mounts = docker("exec", container, "cat", "/proc/mounts").stdout
    host_paths = [line for line in mounts.splitlines() if " /workspace " in line]
    assert len(host_paths) == 1, mounts
    found = inside(container, "import os; print([f for r, d, fs in os.walk('/') for f in fs if f == 'secret.txt'])")
    assert found.stdout.strip() == "[]", "nothing outside the folder is there, whatever looks"
    if (folder / "out.txt").is_symlink():
        assert docker("exec", container, "cat", "/workspace/out.txt").returncode != 0
    who = docker("exec", container, "sh", "-c", "id -u; grep CapEff /proc/self/status").stdout.split()
    assert who[0] == "1000"
    assert who[-1] == "0000000000000000", "no capability"


async def test_from_inside_nothing_answers_but_the_edge(machine: Kernel, gateway: int, tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    async with machine.operations.running():
        a = (await opened(machine, first))["container"]
        b = (await opened(machine, second))["container"]
    assert not reaches(a, "1.1.1.1", 443), "the internet by address"
    assert not reaches(a, "pypi.org", 443), "the internet by name"
    assert not reaches(a, "2606:4700:4700::1111", 443, "AF_INET6"), "the internet over IPv6"
    assert not reaches(a, "host.docker.internal", gateway), "the machine, around the edge"
    docker("exec", "--detach", b, "python3", "-m", "http.server", "8000")
    address = docker("inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", b).stdout
    assert not reaches(a, address.strip(), 8000), "another workspace"
    assert not reaches(a, b, 8000), "another workspace, by its name"
    answer = inside(
        a, f"import urllib.request; print(urllib.request.urlopen('http://edge:{gateway}/').read().decode())"
    )
    assert answer.stdout.strip() == "the gateway, through the edge", answer.stderr
    home = names(machine.home.id)
    joined = docker(
        "inspect", "--format", "{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{end}}", home.edge
    )
    assert set(joined.stdout.split()) == {home.outer, home.inner("first"), home.inner("second")}


async def test_a_container_runs_within_its_limits(machine: Kernel, tmp_path: Path) -> None:
    folder = tmp_path / "limited"
    folder.mkdir()
    machine.settings.write("workspace", "limited", {"path": str(folder), "cpus": 1, "memory_mib": 1024}, base=None,
                           actor=YOU)  # fmt: skip
    async with machine.operations.running():
        container = (await opened(machine, folder))["container"]
    limits = docker(
        "exec", container, "sh", "-c", "cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.max /sys/fs/cgroup/pids.max"
    )
    cpu, memory, processes = limits.stdout.splitlines()
    assert cpu.split() == ["100000", "100000"], "one CPU"
    assert int(memory) == 1024 * 1024 * 1024
    assert processes == "1024"


async def test_the_edge_reaches_the_gateway_on_linux(machine: Kernel, gateway: int, tmp_path: Path) -> None:
    """Design 0014 §3: on Docker Engine the edge forwards the gateway's port to its socket, in the folder it mounts
    read-only at /run/clank (its only mount besides Clank's programs), and runs as the owner, so it may open it."""
    if sys.platform != "linux":
        pytest.skip("Docker Engine runs on Linux")
    if not on_docker_engine(machine):
        pytest.skip("this machine's Docker is not Docker Engine: its edge reaches the host's loopback")
    folder = tmp_path / "linux"
    folder.mkdir()
    async with machine.operations.running():
        container = (await opened(machine, folder))["container"]
    answer = inside(
        container, f"import urllib.request; print(urllib.request.urlopen('http://edge:{gateway}/').read().decode())"
    )
    assert answer.stdout.strip() == "the gateway, through the edge", answer.stderr
    edge = names(machine.home.id).edge
    mounts = {
        each["Destination"]: each for each in json.loads(docker("inspect", "--format", "{{json .Mounts}}", edge).stdout)
    }
    assert set(mounts) == {"/opt/clank", "/run/clank"}, "Clank's programs and the gateway's socket folder, nothing else"
    assert not mounts["/opt/clank"]["RW"]
    assert not mounts["/run/clank"]["RW"], "read-only"
    workspaces: Workspaces = machine.parts["workspaces"]
    assert mounts["/run/clank"]["Source"] == str(workspaces.socket_folder())
    assert docker("inspect", "--format", "{{.Config.User}}", edge).stdout.strip() == f"{os.getuid()}:{os.getgid()}"


async def test_on_linux_the_hosts_own_address_on_a_workspaces_network_answers_nothing(
    machine: Kernel, tmp_path: Path
) -> None:
    """Design 0014 §4: on Docker Engine the host may have an address on each bridge network, where a server listening
    on every address (an SSH server, say) would answer the agent. The probe listens on that address only, read with
    `docker network inspect`, never on every address; a host with no address there refuses the probe's bind, which
    proves the same."""
    if sys.platform != "linux":
        pytest.skip("the host's own address on a bridge network: Docker on Linux")
    folder = tmp_path / "probe"
    folder.mkdir()
    async with machine.operations.running():
        container = (await opened(machine, folder))["container"]
    network = names(machine.home.id).inner("probe")
    found = docker("network", "inspect", "--format", "{{range .IPAM.Config}}{{.Gateway}} {{end}}", network)
    addresses = [each for each in found.stdout.split() if ":" not in each]  # IPv4: the workspaces' networks have no v6
    if not addresses:
        return  # Docker gave the network no host address: nothing of the machine's is there
    try:
        probe = ThreadingHTTPServer((addresses[0], 0), Hello)
    except OSError:
        return  # the host has no address there
    threading.Thread(target=probe.serve_forever, daemon=True).start()
    try:
        assert not reaches(container, addresses[0], probe.server_port), "the host's own address on its network"
    finally:
        probe.shutdown()
        probe.server_close()
