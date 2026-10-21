"""Design 0002 §2.3 and §2.14: over real HTTP, the event stream first says it is connected, then every client that
follows it hears who is connected, as clients join and leave (a live event, not kept)."""

from collections.abc import Generator, Iterator
from datetime import UTC, datetime

import pytest

from clank import registry
from clank.client import ServerEvent
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform
from tests.support.live import live_service


@pytest.fixture
def kernel(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC)), registry.components())
    yield kernel
    kernel.close()


def test_the_stream_says_it_is_connected_then_who_is_connected(kernel: Kernel) -> None:
    with live_service(kernel, name="console") as console:
        messages: Generator[ServerEvent, None, None] = console.events()
        try:
            first = next(messages)
            assert first.name == "connected"
            clients = next(messages)
            assert (clients.name, clients.data["data"]["clients"]) == ("service.clients", ["console"])
            assert clients.id is None
        finally:
            messages.close()
