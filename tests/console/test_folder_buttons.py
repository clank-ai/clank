"""Design 0011 §12.1, §12.7 and §12.9 (This folder's buttons, board K2; a button that cannot act now; narrow windows):
under the steps a row leads with "Next:" and the key of the first step not done, and `g` when more are; Then work
holds a column of the ways to start working (`a`, `c`, `f`) and a row of its settings (`m`, `p`, `r`, `w`, `i`); each
button is one of the page's declared keys, and a click on one does what its key does. `a` is dimmed until every
required step is done, and the keys that work on the workspace until it is opened: focused, the message line says why,
and pressed, by a click or the key, they say why and the page's `press` is not called. At 128, 88 and 60 columns every
group's lines stay inside it, and the frames are the snapshots `folder-128`, `folder-88` and `folder-60`."""

from datetime import UTC, datetime

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console.folder import FolderPage, next_keys
from clank.console.app import ClankConsole
from clank.console.buttons import Buttons
from clank.console.pages import Page
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="folder")
    app.folder = FOLDER
    return app


def keys_of(app: ClankConsole, group: str) -> list[str]:
    return [each.key.key for each in app.query_one(f"#{group}", Buttons).buttons]


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


def test_the_next_row_leads_with_next_and_the_first_steps_key_and_g_when_more_are_or_with_ready() -> None:
    assert next_keys([("docker", "s"), ("a model", "l")]) == ("Next:", [("s", "start Docker"), "g"])
    assert next_keys([("the gateway", "g")]) == ("Next:", ["g"])
    assert next_keys([("this folder", "")]) == ("", [])
    lead, ready = next_keys([])
    assert lead == "Ready:"
    assert [each[0] for each in ready] == ["a", "c"]
    assert [each[0] for each in next_keys([("its software", "e")])[1]] == ["a", "c", "e"]


async def test_this_folders_groups_hold_its_declared_keys(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(128, 50)) as pilot:
        await frame_when(pilot, app, "Get ready to work here", "Next:")
        assert keys_of(app, "folder-next") == ["l", "g"]
        assert app.query_one("#folder-next", Buttons).lead == "Next:"
        assert keys_of(app, "folder-ways") == ["a", "c", "f"]
        assert keys_of(app, "folder-settings") == ["m", "p", "r", "w", "i"]
        declared = {key.key: key for key in FolderPage.KEYS}
        for group in app.query_one("#page-folder", Page).query(Buttons).results(Buttons):
            for each in group.buttons:
                assert each.key is declared[each.key.key], (group.id, each.key.key)


async def test_a_click_on_a_button_does_what_its_key_does(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(128, 50)) as pilot:
        await frame_when(pilot, app, "Get ready to work here", "Next:")
        page = app.query_one("#page-folder", Page)
        pressed: list[str] = []

        def press(key: str) -> bool:
            pressed.append(key)
            return True

        page.press = press  # type: ignore[method-assign]
        await pilot.click("#folder-next", offset=(len("Next:  "), 0))
        await pilot.pause()
        assert pressed == ["l"]
        assert app.focused is app.query_one("#folder-next", Buttons)


async def test_the_keys_that_cannot_act_now_are_dimmed_say_why_and_are_not_pressed(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(128, 50)) as pilot:
        await frame_when(pilot, app, "Get ready to work here", "Next:")
        settings, ways = app.query_one("#folder-settings", Buttons), app.query_one("#folder-ways", Buttons)
        assert {settings.state(index) for index in range(len(settings.buttons))} == {"unable"}
        assert ways.state(0) == "unable", "a: not every required step is done"
        assert ways.state(1) == "normal"
        page = app.query_one("#page-folder", Page)
        pressed: list[str] = []

        def press(key: str) -> bool:
            pressed.append(key)
            return True

        page.press = press  # type: ignore[method-assign]
        settings.focus()
        await settle(pilot, lambda: "open the workspace first (o)" in message(app))
        assert settings.state(0) == "unable_focused"
        await pilot.press("enter")
        await pilot.press("m")
        await pilot.click("#folder-ways", offset=(1, 0))
        await settle(pilot, lambda: "Not ready yet" in message(app))
        assert pressed == []


@pytest.mark.parametrize("width", [128, 88, 60])
async def test_this_folder_at_three_widths_every_group_inside_its_room(client: Client, home: Home, width: int) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 60)) as pilot:
        frame = await frame_when(pilot, app, "Get ready to work here", "Next:")
        for group in app.query_one("#page-folder", Page).query(Buttons).results(Buttons):
            lines, _ = group.lines(group.size.width)
            assert all(line.cell_length <= group.size.width for line in lines), group.id
        assert_frame(frame, f"folder-{width}")
