"""Design 0012 §4.6, §4.7, §9.7 and §11 step 12: `x` drops the highlighted item through the Guide's Drop (step 10), by
the same path as the Session view's `x`: the Guide is asked about that call first (what it frees, what it costs, or why
it cannot run), then its window asks, and only Enter in that window clears the result. In the Context view, Enter or
`x` on a part of What is in it lists the part's items, and Enter on a row of Could be freed that drops (the loop text,
the earlier results of calls made again) lists its items, each in a window where ↑↓ highlight one and `x` drops it; an
item that is not a call's result says why and opens nothing. In the Session view, `x` with Biggest in the context
focused drops the item it highlights. Neither the key that opens a window nor Enter in the window of items acts in it.
The session and its request are synthetic."""

from typing import Any

import pytest

from clank.client import Client
from clank.components.agents.console.biggestpanel import BiggestList
from clank.components.agents.console.contextfreed import FreedList
from clank.components.agents.console.contextview import PartsList
from clank.components.agents.console.guidepanel import GuideList
from clank.components.agents.console.itemsscreen import ItemsScreen
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import settle
from tests.console.test_monitor_context import gateway_of
from tests.console.test_monitor_context_view import activity
from tests.console.test_monitor_flow import board, make, opened

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def dropping(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Board A's session with its census, its server known, and the Guide's Drop recorded: the parts it cleared."""
    gateway_of(kernel, monkeypatch, activity(), "daily-262k")
    board(kernel)
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    done: list[str] = []

    def dropped(workspace: str, session: str, part: str, *, actor: Any) -> Any:
        done.append(part)
        return {"state": "cleared"}

    monkeypatch.setattr(agents.guide, "drop", dropped)
    return done


async def ready(pilot: Any, app: ClankConsole) -> None:
    """The Monitor open, the Guide's actions and the estimate read."""
    await opened(pilot, app)
    listed = app.query_one("#monitor-guide-list", GuideList)
    await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
    await settle(pilot, lambda: bool(app.query_one(BiggestList).shown))


async def pick(pilot: Any, app: ClankConsole, call: str) -> ItemsScreen:
    """In the items' window: the row of this call highlighted."""
    await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
    window = app.screen
    assert isinstance(window, ItemsScreen)
    window.listed.index = [row.get("call") for row in window.rows].index(call)
    await settle(pilot, lambda: window.listed.index is not None and window.rows[window.listed.index]["call"] == call)
    return window


async def test_x_on_a_part_lists_its_items_and_x_there_drops_the_highlighted_result_once_confirmed(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        await pilot.press("f10")
        listed = app.query_one(PartsList)
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        listed.index = [row["part"] for row in listed.shown].index("results")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("x")
        await pick(pilot, app, "call_c03")
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert asking.heading == "Drop step 3's `read` result", "the Session view's window, read for that call"
        assert any("The drop is final" in line for line in asking.lines)
        assert done == [], "nothing until Enter in the window"
        await pilot.press("enter")
        await settle(pilot, lambda: done == ["c03"])
        listed.focus()
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        window = await pick(pilot, app, "call_c04")
        assert window.heading.startswith("tool results")
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ItemsScreen))
        assert done == ["c03"]


async def test_enter_on_a_drop_row_of_could_be_freed_lists_its_items_and_x_drops_one(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        await pilot.press("f10")
        listed = app.query_one(FreedList)
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        listed.index = [row["what"] for row in listed.shown].index("again")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        window = await pick(pilot, app, "call_c05")
        assert any("the Guide's Drop" in line for line in window.notes)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert app.screen is window, "Enter does nothing in the window of items"
        assert done == []
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: done == ["c05"])


async def test_x_on_an_item_that_is_not_a_calls_result_says_why_and_opens_nothing(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        page = app.query_one("#page-monitor")
        await pilot.press("f10")
        listed = app.query_one(PartsList)
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        listed.index = [row["part"] for row in listed.shown].index("system")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
        await pilot.press("x")
        await settle(pilot, lambda: "Drop cannot run now: it clears a call's result, and this is the system prompt"
                     in str(app.query_one("#message").render()))  # fmt: skip
        assert app.screen is page.screen
        assert done == []


async def test_x_with_biggest_focused_drops_the_item_it_highlights(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        listed = app.query_one(BiggestList)
        await pilot.press("b")
        await settle(pilot, lambda: app.focused is listed)
        listed.index = [row.get("call") for row in listed.shown].index("call_c18")
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert asking.heading == "Drop step 16's `read` result"
        await pilot.press("enter")
        await settle(pilot, lambda: done == ["c18"])


async def test_esc_in_the_window_of_items_closes_it_quietly(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        page = app.query_one("#page-monitor")
        await pilot.press("f10")
        listed = app.query_one(PartsList)
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
        await pilot.press("escape")
        await settle(pilot, lambda: app.screen is page.screen)
        await pilot.pause(0.3)
        assert "Drop" not in str(app.query_one("#message").render()), "Esc says nothing"
        assert done == []


async def test_keys_in_the_window_of_items_never_reach_the_page_under_it(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    dropping(kernel, monkeypatch)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await ready(pilot, app)
        await pilot.press("f10")
        listed = app.query_one(PartsList)
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        listed.index = [row["part"] for row in listed.shown].index("results")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        window = await pick(pilot, app, "call_c03")
        await pilot.press("k")
        await pilot.pause(0.3)
        assert app.screen is window, "k opens no second window over it"
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.3)
        assert "highlight a part" not in str(app.query_one("#message").render()), "the page did not take the x too"
