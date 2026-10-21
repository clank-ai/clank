"""Shared fixtures for the components' tests: a fake clock and a temporary CLANK_HOME."""

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
