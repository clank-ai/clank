"""Test support: a real Clank service in its own process, on a free port, for the tests of the service and commands.
Its home's gateway is not started with it (`quiet`): a test service would otherwise start a real gateway on the
gateway's port, beside the owner's, and leave it running, since the gateway outlives the service by design."""

import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import httpx2
import psutil

from clank.kernel.access import Connection, local_token, read_connection
from clank.kernel.home import Home


def free_port() -> int:
    """A TCP port nothing listens on right now, always of five digits, so what shows it is laid out the same way in
    every run (the console's snapshots)."""
    while True:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port: int = probe.getsockname()[1]
        if port >= 10000:
            return port


def quiet(home: Home) -> None:
    """Make the home's gateway one the service does not start, unless the home already says otherwise."""
    settings = home.config / "gateway.json"
    if not settings.exists():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text('{\n  "schema": "gateway/1",\n  "start": false\n}\n', encoding="utf-8")


def clank(home: Home, *args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run `python -m clank` with a CLANK_HOME, and wait for it."""
    quiet(home)
    environment = {**os.environ, "CLANK_HOME": str(home.root)}
    return subprocess.run(
        [sys.executable, "-m", "clank", *args], env=environment, capture_output=True, text=True, timeout=timeout
    )


@contextmanager
def served(home: Home, port: int | None = None) -> Iterator[tuple["subprocess.Popen[str]", Connection, list[str]]]:
    """A service running for `home`, its connection, and what it prints (read as it comes, by a thread: a service whose
    output nobody read would block once the pipe was full); killed afterwards if it is still running."""
    quiet(home)
    environment = {**os.environ, "CLANK_HOME": str(home.root)}
    process = subprocess.Popen(
        [sys.executable, "-m", "clank", "serve", "--port", str(port or free_port())],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output: list[str] = []
    reader = threading.Thread(target=lambda: output.extend(process.stdout or []), daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 30
        connection = None
        while connection is None:
            if process.poll() is not None:
                reader.join(5)
                raise AssertionError(f"the service exited ({process.returncode}): {''.join(output)}")
            if time.monotonic() > deadline:
                raise AssertionError("the service did not start within 30 seconds")
            time.sleep(0.1)
            connection = read_connection(home)
        yield process, connection, output
    finally:
        stop(home)
        try:
            family = [psutil.Process(process.pid), *psutil.Process(process.pid).children(recursive=True)]
        except psutil.NoSuchProcess:
            family = []
        for member in family:
            with suppress(psutil.NoSuchProcess):
                member.kill()
        process.wait(10)
        reader.join(5)
        if process.stdout:
            process.stdout.close()


def stop(home: Home) -> None:
    """Ask the service of `home`, if one answers, to stop, and wait until it has (on Windows the venv's python.exe is
    a launcher whose child is the real service, so killing the launcher alone would leave the service running)."""
    connection = read_connection(home)
    if connection is None:
        return
    try:
        httpx2.post(
            f"{connection.url}/api/v1/service/stop",
            headers={"Authorization": f"Bearer {local_token(home)}"},
            timeout=5,
        )
    except httpx2.TransportError:
        return
    deadline = time.monotonic() + 15
    while read_connection(home) is not None and time.monotonic() < deadline:
        time.sleep(0.1)
