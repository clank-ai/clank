"""Design 0016 §7 and §15, and design 0003 §8.2 (revised 2026-10-29, the owner's request): `e` on the Presets page
changes the highlighted cloud preset's settings in a form filled with them, the model's limits in its labels as the
service words them; only what was changed is sent, and the service's answer (what changed, where it applies, and,
while the main slot runs it, that OpenCode windows open now keep the limits they started with) shows in a window, a
refusal on the message line in the service's words, a number that is not one in the console's. On a local preset, `e`
says where its options change instead. The form leaves Esc and Backspace to the window: Esc leaves it, sending nothing,
and Backspace erases in its fields. The keys bar and the page's explanation list the key."""

from typing import Any

import pytest
from textual.widgets import Input, Label, ListView

from clank.client import Client
from clank.components.runtime.console.presets import PresetsPage
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.form import FormScreen
from clank.kernel.home import Home
from tests.console.frames import FOLDER, focus_on, frame_when, settle
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio
WINDOWS = (
    "OpenCode windows open now keep the limits they started with until they start again; the next one started gets "
    "these."
)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, home=home, page="presets")
    app.folder = FOLDER
    return app


def patched(cloud: CloudBench) -> list[Any]:
    return [body for method, _, body in cloud.calls if method == "PATCH"]


async def highlighted(pilot: Any, app: ClankConsole, id: str) -> None:
    """The preset `id` highlighted in the page's list, the list focused."""
    await settle(pilot, lambda: any(preset["id"] == id for preset in app.data.presets))
    listed = app.query_one("#presets-list", ListView)
    await focus_on(pilot, app, listed, [preset["id"] for preset in app.data.presets].index(id))


async def opened_form(pilot: Any, app: ClankConsole) -> FormScreen:
    await pilot.press("e")
    await settle(pilot, lambda: isinstance(app.screen, FormScreen))
    assert isinstance(app.screen, FormScreen)
    return app.screen


async def test_e_opens_a_form_of_its_settings_with_the_models_limits_and_sends_only_what_changed(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset(context=65536)
    cloud_api.run("cloud-example-coder")
    app = make(client, home)
    async with app.run_test(size=(120, 44)) as pilot:
        await highlighted(pilot, app, "cloud-example-coder")
        form = await opened_form(pilot, app)
        labels = [str(label.content) for label in form.query(Label).results(Label)]
        assert (
            "Most output, in tokens: its thinking and its answer together (at most 32,768, the model's most)" in labels
        )
        assert any(label.startswith("Context, in tokens (at most 262,144, the model's window") for label in labels)
        assert {each.id: each.value for each in form.query(Input).results(Input)} == {
            "form-context": "65536", "form-max_output": "16384", "form-reasoning": "default"
        }  # fmt: skip
        form.query_one("#form-max_output", Input).value = "32768"
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        assert app.screen.heading == "cloud: Example Coder: changed"
        assert app.screen.lines[:3] == [
            "cloud: Example Coder: most output 32,768 tokens (was 16,384).",
            "The main slot runs it and follows the change from the next request.",
            WINDOWS,
        ]
    assert cloud_api.presets["cloud-example-coder"]["options"]["max_output"] == 32768
    assert patched(cloud_api) == [{"max_output": 32768}], "only what was changed"


async def test_a_refusal_is_said_in_the_services_words_and_a_number_that_is_not_one_in_the_consoles(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset(context=65536)
    app = make(client, home)
    async with app.run_test(size=(120, 44)) as pilot:
        await highlighted(pilot, app, "cloud-example-coder")
        form = await opened_form(pilot, app)
        form.query_one("#form-max_output", Input).value = "99999"
        await pilot.press("ctrl+s")
        await frame_when(pilot, app, "max_output is at most 32,768 for example-vendor/example-coder, not 99,999")
        form = await opened_form(pilot, app)
        form.query_one("#form-context", Input).value = "lots"
        await pilot.press("ctrl+s")
        await frame_when(pilot, app, "context is a whole number of tokens, not 'lots'")
    assert patched(cloud_api) == [{"max_output": 99999}], "nothing sent for a number that is not one"
    assert cloud_api.presets["cloud-example-coder"]["options"]["max_output"] == 16384


async def test_esc_leaves_the_form_sending_nothing_and_backspace_erases_in_its_fields(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset(context=65536)
    app = make(client, home)
    async with app.run_test(size=(120, 44)) as pilot:
        await highlighted(pilot, app, "cloud-example-coder")
        form = await opened_form(pilot, app)
        context = form.query_one("#form-context", Input)
        await settle(pilot, lambda: app.focused is context)
        await pilot.press("end", "backspace")
        assert context.value == "6553"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, FormScreen))
        assert isinstance(app.screen.query_one("#page-presets"), PresetsPage), "back on the page"
    assert patched(cloud_api) == []


async def test_on_a_local_preset_e_says_where_its_options_change(
    client: Client, home: Home, cloud_api: CloudBench
) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 44)) as pilot:
        await highlighted(pilot, app, "daily-262k")
        await pilot.press("e")
        await frame_when(pilot, app, "daily 262K is a local preset: its options are in its file; o, then e on Launch")
        assert not isinstance(app.screen, FormScreen)
    assert patched(cloud_api) == []


async def test_the_keys_bar_and_the_pages_explanation_list_e(client: Client, home: Home, cloud_api: CloudBench) -> None:
    cloud_api.add()
    cloud_api.write_preset(context=65536)
    app = make(client, home)
    async with app.run_test(size=(120, 44)) as pilot:
        await highlighted(pilot, app, "cloud-example-coder")
        await frame_when(pilot, app, "e change")
        _, lines = app.query_one("#page-presets", PresetsPage).explain()
        assert any("e changes its context, its most output and its thinking effort" in line for line in lines)
