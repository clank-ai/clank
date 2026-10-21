"""Design 0003 §8.2 and the M1.5 plan's task 3: the console's Presets page shows each preset with its serving setup and
model, its fit in the GPU's memory now or why it cannot run, and its last start; Enter switches the main slot to the
highlighted one, `c` checks it in a window, `v` shows its file. Design 0003 §4.1: the highlighted preset's settings
list the sampling in effect, the values it sets first, then the engine's own defaults in words."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from textual.widgets import ListView

from clank.client import Client
from clank.components.runtime.console.presets import settings_text
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from tests.components.runtime.conftest import Rig
from tests.components.runtime.consoles import page_text, serve
from tests.console.frames import settle

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 11, 45, tzinfo=UTC)


@pytest.fixture
def served(rig: Rig) -> Iterator[Client]:
    with serve(rig) as client:
        yield client


async def test_each_preset_shows_its_fit_or_why_it_cannot_run_and_enter_switches_to_it(
    rig: Rig, served: Client
) -> None:
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=rig.kernel.home, page="presets")
    async with app.run_test(size=(120, 44)) as pilot:
        await settle(pilot, lambda: "fits, 13,157 MiB to spare" in page_text(app, "presets"), seconds=30)
        shown = page_text(app, "presets")
        assert "fake KVMem" in shown
        assert "kvmem-llamacpp v0.16.0-rc1 · tiny" in shown
        assert "daily 262K" in shown
        assert "cannot run: the catalog has no model qwen3.8-27b" in shown
        listed = app.query_one("#presets-list", ListView)
        listed.focus()
        listed.index = [preset["id"] for preset in app.data.presets].index("fake-kvmem-small")
        await pilot.press("enter")
        await settle(pilot, lambda: rig.runtime.state.slot("main").status == "ready", seconds=60)
        assert rig.runtime.state.slot("main").preset == "fake-kvmem-small"
        await settle(pilot, lambda: "last started" in page_text(app, "presets"), seconds=20)
        await pilot.press("v")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        assert app.screen.heading.startswith("fake KVMem small: ")
        assert '  "engine": "kvmem-llamacpp",' in app.screen.lines
        await pilot.press("escape")
        await pilot.press("c")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen) and "Check of" in app.screen.heading)
        assert isinstance(app.screen, DetailsScreen)
        assert app.screen.heading == "Check of fake KVMem small"


COOL = {"title": "cool", "source": "user", "file": "cool.json", "engine": "kvmem-llamacpp",
        "engine_version": "v0.16.0-rc1", "host": "", "model": "tiny", "slot": "main", "notes": "",
        "options": {"sampling.temperature": 0.6}}  # fmt: skip
TEMPERATURE = {"key": "sampling.temperature", "label": "Temperature", "value": 0.6, "source": "preset",
               "engine_default_words": "1.0 thinking, 0.7 not thinking"}  # fmt: skip
TOP_P = {"key": "sampling.top_p", "label": "Top p", "value": None, "source": "unset",
         "engine_default_words": "0.95 thinking, 0.80 not thinking"}  # fmt: skip


def sampling_line(preset: dict[str, object]) -> str | None:
    return next((line for line in settings_text(preset, None).splitlines() if line.startswith("sampling")), None)


def test_the_settings_list_the_sampling_in_effect_the_values_set_first() -> None:
    assert sampling_line({**COOL, "sampling": [TEMPERATURE, TOP_P]}) == (
        "sampling       set: temperature 0.6; the engine's own: top_p 0.95 thinking, 0.80 not thinking"
    )
    unset = {**TEMPERATURE, "value": None, "source": "unset"}
    assert sampling_line({**COOL, "sampling": [unset, TOP_P]}) == (
        "sampling       the engine's own: temperature 1.0 thinking, 0.7 not thinking · top_p 0.95 thinking, 0.80 "
        "not thinking"
    )
    assert sampling_line({**COOL, "sampling": []}) is None, "an engine without sampling options shows none"
