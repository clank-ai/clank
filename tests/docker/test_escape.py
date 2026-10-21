"""Design 0004 §3 and §8, design 0002 §3.3 (M4's escape tests), on this machine's Docker when asked (`-m docker`): a
workspace's container sees its folder and nothing else of the machine (its mounts, a subprocess, a symlink that points
out of the folder); from inside it nothing answers but the edge: not the internet (by address or by name, IPv4 or
IPv6), not the machine, not another workspace; the edge answers, forwarding to the gateway's port; and the container
runs as the image's user, with no capability, within its limits."""

import contextlib
import os
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.workspaces.sandbox import names
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.docker.conftest import docker, gateway_port

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


@pytest.fixture
def gateway(machine: Kernel) -> Iterator[int]:
    """A server where the gateway listens (127.0.0.1 only, as the gateway does), and the settings that name its port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Hello)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    gateway_port(machine.home, server.server_port)
    machine.settings.reload_changed()
    yield server.server_port
    server.shutdown()
    server.server_close()


async def opened(kernel: Kernel, folder: Path) -> dict[str, Any]:
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
