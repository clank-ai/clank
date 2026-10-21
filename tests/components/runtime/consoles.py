"""Test support for the runtime's console pages: the rig's API served for real, its GPU holding 1,105 MiB more while
the slot's fake engine runs; a page's text; and a choice made in the picker."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from textual.pilot import Pilot
from textual.widgets import Label, ListView

from clank.client import Client
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.console.app import ClankConsole
from clank.console.pick import PickScreen
from tests.components.runtime.conftest import Rig
from tests.console.frames import settle
from tests.support.live import live_service


def running(rig: Rig) -> ProcessIdentity | None:
    """The process the main slot runs, as the slot keeps it."""
    slot = rig.runtime.state.slot("main")
    if slot.pid is None:
        return None
    return ProcessIdentity(slot.host or "", slot.pid, slot.started or "", slot.command or "")


@contextmanager
def serve(rig: Rig) -> Iterator[Client]:
    """The rig's API, answering until the block ends; what the slot still runs is stopped after it."""

    def gpu() -> GpuMemory:
        identity = running(rig)
        return GpuMemory(16303, 3146 if identity is not None and LocalHost().alive(identity) else 2041)

    rig.runtime.read_gpu = gpu
    try:
        with live_service(rig.kernel) as client:
            yield client
    finally:
        identity = running(rig)
        if identity is not None:
            LocalHost().stop(identity, 5)


def page_text(app: ClankConsole, page: str) -> str:
    """Everything a page shows, its labels joined."""
    return "\n".join(str(label.content) for label in app.query(f"#page-{page} Label").results(Label))


async def pick(pilot: Pilot[Any], app: ClankConsole, label: str) -> None:
    """Choose a label in the picker on screen."""
    await settle(pilot, lambda: isinstance(app.screen, PickScreen))
    screen = app.screen
    assert isinstance(screen, PickScreen)
    screen.query_one(ListView).index = [choice.label for choice in screen.choices].index(label)
    await pilot.press("enter")
