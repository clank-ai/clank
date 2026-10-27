"""Shared fixtures for the components' tests: a fake clock, a temporary CLANK_HOME, and a short folder for sockets."""

import shutil
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.home import Home


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous tests on asyncio, the event loop the service uses."""
    return "asyncio"


@pytest.fixture
def clock() -> FakeClock:
    """A clock that moves only when a test moves it."""
    return FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC))


@pytest.fixture
def home(tmp_path: Path) -> Home:
    """A temporary CLANK_HOME with its folders created."""
    home = Home(tmp_path / "clank-home")
    home.ensure()
    return home


@pytest.fixture
def short() -> Iterator[Path]:
    """A short folder of the test's own, for the gateway's sockets (design 0014 §3): a socket's path holds 107 bytes,
    more than a folder under `tmp_path` may leave."""
    made = Path(tempfile.mkdtemp(prefix="clank-sock-"))
    yield made
    shutil.rmtree(made, ignore_errors=True)
