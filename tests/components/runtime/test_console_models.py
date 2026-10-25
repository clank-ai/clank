"""Design 0003 §8.1 and the M1.5 plan's task 2: the console's Models page shows each slot (its state since when and
why, what it runs and where), the memory its engine took beside its estimate and the GPU's use now, and the last
switches; `l` loads a preset picked from a list, `c` checks the slot's preset in a window, `u` unloads; a load refused
as busy says so on the message line, in the service's words."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.runtime.state import InstallRecord
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from tests.components.runtime.conftest import Rig
from tests.components.runtime.consoles import page_text as text_of
from tests.components.runtime.consoles import pick, serve
from tests.console.frames import assert_frame, frame_when, settle
from tests.fakes.engine import program

FOLDER = str(Path(__file__).parents[2] / "fixtures" / "Clank")  # the folder named in the recorded frames

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 11, 45, tzinfo=UTC)


@pytest.fixture
def served(rig: Rig) -> Iterator[Client]:
    with serve(rig) as client:
        yield client


def page_text(app: ClankConsole) -> str:
    return text_of(app, "models")


async def test_the_models_page_shows_the_slot_and_l_loads_c_checks_and_u_unloads(rig: Rig, served: Client) -> None:
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=rig.kernel.home, page="models", folder=FOLDER)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "never started" in page_text(app))
        assert_frame(await frame_when(pilot, app, "never started", "2,041 of 16,303"), "runtime-models-stopped")
        await pilot.press("l")
        await pick(pilot, app, "fake KVMem")
        await settle(pilot, lambda: "READY" in page_text(app), seconds=60)
        await settle(pilot, lambda: "3,146 of 16,303" in page_text(app), seconds=20)
        shown = page_text(app)
        assert "fake KVMem · tiny · kvmem-llamacpp v0.16.0-rc1 on local" in shown
        assert "it took 1,105 MiB (estimated 1,105)" in shown
        assert "fake KVMem" in str(app.query_one("#models-launches", Label).content)
        await pilot.press("c")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        assert app.screen.heading == "Check of fake KVMem"
        assert any(line.startswith("ok    fit") for line in app.screen.lines)
        await pilot.press("escape")
        await pilot.press("u")
        await settle(pilot, lambda: "STOPPED" in page_text(app) and "unloaded" in page_text(app), seconds=60)


async def test_a_load_refused_as_busy_says_so_in_the_services_words(rig: Rig, served: Client, tmp_path: Path) -> None:
    slow = InstallRecord(
        setup="kvmem-llamacpp", version="v0.16.0-rc1", host="local", folder=str(tmp_path), how="test",
        program=list(program("kvmem", "--fake-start-seconds", "5")),
    )  # fmt: skip
    rig.runtime.state.add_install(slow, rig.clock.now())
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=rig.kernel.home, page="models", folder=FOLDER)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: "never started" in page_text(app))
        await pilot.press("l")
        await pick(pilot, app, "fake KVMem")
        await settle(pilot, lambda: "STARTING" in page_text(app), seconds=30)
        await pilot.press("l")
        await pick(pilot, app, "fake KVMem small")
        message = app.query_one("#message", Label)
        await settle(pilot, lambda: "is in use by Load a preset" in str(message.content), seconds=20)
        assert "! slot:main is in use by Load a preset (op-" in str(message.content)
        await settle(pilot, lambda: "READY" in page_text(app), seconds=60)
