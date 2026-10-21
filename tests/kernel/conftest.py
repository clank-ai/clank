"""Shared fixtures for the kernel's tests: a fake clock, a temporary CLANK_HOME, and its migrated state database."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.store import Store, kernel_migrations

START = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous tests on asyncio, the event loop the service uses."""
    return "asyncio"


@pytest.fixture
def clock() -> FakeClock:
    """A clock that moves only when a test moves it."""
    return FakeClock(START)


@pytest.fixture
def home(tmp_path: Path) -> Home:
    """A temporary CLANK_HOME with its folders created."""
    home = Home(tmp_path / "clank-home")
    home.ensure()
    return home


@pytest.fixture
def store(home: Home) -> Iterator[Store]:
    """The state database in that CLANK_HOME, with the kernel's migrations applied; closed after the test."""
    store = Store(home.database)
    store.migrate(kernel_migrations())
    yield store
    store.close()
