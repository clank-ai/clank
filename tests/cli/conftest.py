"""Shared fixtures for the commands' tests: a temporary CLANK_HOME, and a service in the test, OpenRouter answered by
its fake (plan s35, task 18)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.client import Client
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import open_kernel
from clank.kernel.home import Home
from tests.fakes.openrouter import served as served_openrouter
from tests.support.cloud import CloudBench


@pytest.fixture
def home(tmp_path: Path) -> Home:
    """A temporary CLANK_HOME with its folders created."""
    home = Home(tmp_path / "clank-home")
    home.ensure()
    return home


@pytest.fixture
def cloud_api(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[CloudBench]:
    """A kernel served in the test, the commands its clients, OpenRouter answered by its fake (the adapter's URL
    pointed at it); the bench, its kernel at `kernel`, the cloud's calls noted."""
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 21, 9, 12, tzinfo=UTC)), registry.components())
    with served_openrouter() as fake:
        monkeypatch.setattr(OpenRouter, "URL", fake.url)
        bench = CloudBench(kernel, fake)
        app = create_app(kernel, token="t", port=7720)
        bench.record(app)
        with TestClient(app, base_url="http://127.0.0.1:7720") as http:
            monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
            yield bench
    kernel.close()
