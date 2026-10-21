"""Design 0012 §2 and §8 (decision 0053): the Monitor's Watch for panel lists the newest marks the rules left, each with
its rule, its session and why, a mark not seen yet in the attention color; Enter on the panel opens the marks it lists
(§2's keys: Enter opens a mark), each whole, and so they are seen. Beside "Monitor" in the menu, the count of marks
not seen yet, gone once they are seen, from the console or elsewhere (the event stream says so). Until the page follows
a session's marks (design 0012 §3), the panel lists the marks of every session; with none, it says what it said before
("no session yet")."""

from typing import Any

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console.monitor import Empty
from clank.components.agents.console.watchfor import MarksList
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.agents.test_watch_for_rules import LIMITS, bash, steps_with
from tests.console.frames import settle
from tests.console.test_monitor_page import make, monitor, opened
from tests.support.flowlines import SESSION, lines, updated

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
YOU = Actor(kind="user", via="console")


def marked(kernel: Kernel, session: str = SESSION) -> list[dict[str, Any]]:
    """A session that made the same call three times: its marks."""
    agents = kernel.parts["agents"]
    messages = steps_with([bash(f"c{n}", "pytest -q") for n in range(1, 4)])
    events = [event for message in messages for event in updated(message)]
    for line in lines(events):
        agents.flows.heard("paper", {**line, "session": session} if line.get("session") else line)
    agents.marks.watch(agents.flows, lambda: LIMITS)
    return list(agents.marks.marks(session=session))


def menu_entry(app: ClankConsole) -> str:
    return str(app.query_one("#menu-monitor Label", Label).content)


async def test_the_watch_for_panel_lists_the_newest_marks_each_with_why(
    client: Client, kernel: Kernel, home: Home
) -> None:
    [mark] = marked(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        listed = page.query_one(MarksList)
        await settle(pilot, lambda: "The same call again" in str(listed.content))
        shown = str(listed.content)
        assert "3 times in the last 12" in shown, "why, as far as the panel's width allows"
        assert listed.display
        assert not page.query_one("#monitor-session-watch").query_one(Empty).display, "no longer empty"
        assert "The same call again" in render_text(app)
        await pilot.press("w")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        opened_whole = " ".join(str(label.content) for label in app.screen.query(Label))
        assert "3 times in the last 12 calls (calls 1, 2 and 3)" in opened_whole, "the mark whole"
        assert "It fires when the same call three times or more in the last 12" in opened_whole
        await settle(pilot, lambda: kernel.parts["agents"].marks.unseen() == 0)
        await pilot.press("escape")
        await settle(pilot, lambda: page.badge(0) is None)
    [event] = kernel.events.after(0, types=["agents.marks_seen"])
    assert event.data["marks"] == [mark["id"]]
    assert (event.actor.kind, event.actor.via) == ("user", "console")


async def test_the_menu_shows_how_many_marks_are_not_seen_beside_monitor(
    client: Client, kernel: Kernel, home: Home
) -> None:
    marked(kernel)
    marked(kernel, "ses_other")
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: menu_entry(app).endswith("2"))
        assert menu_entry(app).startswith("F10 Monitor")
        kernel.parts["agents"].marks.seen(session="ses_other", actor=YOU)
        await settle(pilot, lambda: menu_entry(app).endswith("1"))
        kernel.parts["agents"].marks.seen(actor=YOU)
        await settle(pilot, lambda: menu_entry(app).strip() == "F10 Monitor")
        assert monitor(app).badge(0) is None
