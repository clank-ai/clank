"""Design 0003 §8.2 and the M1.5 plan's task 4: the console's Launch options page shows a preset's options, each with
its value, where it comes from (the preset, Clank's default), what the engine receives for it or why nothing, and what
it does; then the command line and the memory estimate with its fit. It shows the preset `o` chose on the Presets page
(else the main slot's, else the first); `p` picks another; `e` opens its file in the editor the system gives JSON
files. Design 0011 §8 (board E12): its panel is titled "(preset): launch options" after the preset it shows."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Label, ListView

from clank.client import Client
from clank.components.runtime.console import options as options_page
from clank.console.app import ClankConsole
from clank.console.panel import Panel
from tests.components.runtime.conftest import Rig
from tests.components.runtime.consoles import page_text, pick, serve
from tests.console.frames import settle

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 11, 45, tzinfo=UTC)


@pytest.fixture
def served(rig: Rig) -> Iterator[Client]:
    with serve(rig) as client:
        yield client


def option(app: ClankConsole, name: str) -> str:
    """The value shown beside an option's name."""
    for row in app.query("#launch-options .row"):
        if str(row.query_one(".name", Label).content) == name:
            return str(row.query_one(".value", Label).content)
    return ""


async def test_each_option_says_its_value_source_and_flags_and_e_opens_the_presets_file(
    rig: Rig, served: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(options_page, "open_file", opened.append)
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=rig.kernel.home, page="presets")
    async with app.run_test(size=(150, 60)) as pilot:
        await settle(pilot, lambda: "fits, 13,157" in page_text(app, "presets"), seconds=30)
        listed = app.query_one("#presets-list", ListView)
        listed.focus()
        listed.index = [preset["id"] for preset in app.data.presets].index("fake-kvmem")
        await pilot.press("o")
        await settle(pilot, lambda: "FITS: 13,157 MiB to spare" in page_text(app, "launch"), seconds=30)
        assert app.query_one("#launch-options-panel", Panel).title == "fake KVMem: launch options"
        shown = page_text(app, "launch").splitlines()
        context = option(app, "Context")
        assert ("8,192 tokens" in context, "the preset" in context, "-c 8192" in context) == (True, True, True)
        batch = option(app, "Batch")
        assert ("Clank's default" in batch, "(the engine's own default)" in batch) == (True, True)
        assert any(" -c 8192 " in line for line in shown), "the command line"
        await pilot.press("e")
        await settle(pilot, lambda: bool(opened))
        assert Path(opened[0]).name == "fake-kvmem.json"
        await pilot.press("p")
        await pick(pilot, app, "fake KVMem small")
        await settle(pilot, lambda: "4,096" in option(app, "Context"), seconds=30)
        assert app.query_one("#launch-options-panel", Panel).title == "fake KVMem small: launch options"
