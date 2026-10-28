"""The Docker tests' rules and kernel (design 0004 §8, design 0002 §3.3): they run only when asked (`-m docker`), with
this machine's Docker running; they build Clank's sandbox image when it is not built (about a gigabyte, once), so they
are run when the owner allows it. Their kernel has a CLANK_HOME of its own, so the containers, networks and volumes
they make carry its id; each is removed after the test, whatever happened (the image is kept: workspaces use it).
Design 0014 §4: on Docker Engine a folder shows the host's owners, and the agent works as user 1000, so where this
machine's user is another (GitHub's runners are 1001) each test opens its folders to every user before a container
sees them (`for_the_agent`)."""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from clank import registry
from clank.kernel.clock import SystemClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the Docker tests unless they were asked for."""
    if "docker" in (config.getoption("markexpr") or ""):
        return
    skip = pytest.mark.skip(reason="it uses this machine's Docker and may build an image: run with -m docker")
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def docker(*arguments: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    """`docker` with these arguments, its output and errors as text."""
    return subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=timeout, check=False)


AGENT = 1000  # the agent's user id in Clank's containers (sandbox.USER)


def for_the_agent(folder: Path) -> Path:
    """The folder, its folders and files opened to every user where this machine's user is not the agent's (design 0014
    §4), so the agent may read and write them; elsewhere, and for links, as it is."""
    if sys.platform == "win32":
        return folder
    if os.getuid() == AGENT:
        return folder
    for path in [folder, *folder.rglob("*")]:
        if not path.is_symlink():
            path.chmod(0o777 if path.is_dir() else 0o666)
    return folder


def gateway_port(home: Home, port: int, socket_folder: str = "") -> None:
    """The port the edge forwards (the gateway's, which the test's own server takes), and on Docker Engine the folder of
    the socket it forwards to (design 0014 §3); the gateway itself not started."""
    settings: dict[str, object] = {"schema": "gateway/1", "start": False, "port": port}
    if socket_folder:
        settings["socket_folder"] = socket_folder
    (home.config / "gateway.json").write_text(json.dumps(settings) + "\n", encoding="utf-8")


@pytest.fixture
def machine(tmp_path: Path) -> Iterator[Kernel]:
    """A kernel of a CLANK_HOME of its own on this machine's Docker; what it made is removed after the test."""
    if docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("Docker does not run: start it with `clank docker start`")
    home = Home(tmp_path / "clank-home")
    home.ensure()
    gateway_port(home, 18210)
    kernel = open_kernel(home, SystemClock(), registry.components())
    try:
        yield kernel
    finally:
        kernel.close()
        label = f"label=clank.home={home.id}"
        containers = docker("ps", "--all", "--quiet", "--filter", label).stdout.split()
        if containers:
            docker("rm", "--force", *containers)
        volumes = docker("volume", "ls", "--format", "{{.Name}}").stdout.split()
        mine = [name for name in volumes if name.startswith(f"clank-{home.id}-")]
        if mine:
            docker("volume", "rm", *mine)
        networks = docker("network", "ls", "--quiet", "--filter", label).stdout.split()
        if networks:
            docker("network", "rm", *networks)
