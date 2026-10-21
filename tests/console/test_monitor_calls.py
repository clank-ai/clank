"""Design 0012 §2, §7 and §11 step 7: the Monitor's Tool calls panel lists the followed session's calls newest first,
each with when it started, its tool, what it does and its result's size in characters; a failed one in the failed
color, marked ✗; one running in the now color. Enter on a call reads it whole through the bridge, a `docker exec`, so
only on Enter while the page is on screen, and shows it in a window: its input, its output (its end, past the bridge's
cap) and its error; when the bridge cannot give it whole (an older sandbox image), the window shows what the flow keeps
of it and why. Nothing reaches the bridge while the page is not on screen. A session followed with no call yet says so.
When rows are short, Tool calls gives up rows first (design 0012 §2's room), so at 160 by 40 no panel is cut."""

from datetime import UTC
from typing import Any

import pytest

from clank.client import Client
from clank.components.agents.console.callspanel import ROWS, CallScreen, CallsList, line, rows
from clank.components.agents.console.monitor import Empty
from clank.components.agents.sessionflow.flow import Flow
from clank.components.agents.sessions import SessionError
from clank.console.app import ClankConsole
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle
from tests.console.test_monitor_flow import WORKSPACE, YOU, board, make, opened, tell
from tests.support.boards import board_a_messages
from tests.support.flowlines import PORT, SESSION, lines, status, step, text, updated, user

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def board_a_view() -> dict[str, Any]:
    """Board A's flow, as the service keeps it."""
    messages, _ = board_a_messages()
    flow = Flow(SESSION, workspace=WORKSPACE)
    for each in lines([event for message in messages for event in updated(message)]):
        flow.heard(each)
    return flow.view()


def test_tool_calls_are_listed_newest_first_with_their_time_tool_what_they_do_and_their_size_a_failed_one_in_red() -> (
    None
):
    listed = rows(board_a_view())
    assert [row["id"] for row in listed[:3]] == ["c20", "c19", "c18"], "newest first"
    newest, failed, read = (line(row, 60, UTC) for row in listed[:3])
    assert newest.plain == "12:05:01   bash      ls studies/                   100 chars"
    assert failed.plain == "12:04:31 ✗ bash      python -m myproject sweep --sizes 8 16…", "no result: no size"
    assert any(span.style == "$clank-failed" for span in failed.spans), "a failed call in the failed color"
    assert read.plain == "12:04:11   read      studies/notes.md            14.2K chars"
    assert len(listed) == 20, "every call of the session, its subagents' in their own flows"
    for width in range(10, 120):
        assert all(line(row, width, UTC).cell_length <= width for row in listed), width
    running = line({**listed[0], "status": "running", "length": None}, 60, UTC)
    assert running.plain.startswith("12:05:01 ● bash      ls studies/")
    assert not running.plain.endswith("chars"), "no result yet"


def bridged(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, refusal: str = "") -> list[list[str]]:
    """The bridge in the workspace's container, as the service runs it (`docker exec`): each run's arguments, and a
    call given whole (or the refusal)."""
    ran: list[list[str]] = []

    def bridge(workspace: str, argv: list[str], given: Any = None, timeout: float = 10) -> dict[str, Any]:
        ran.append(list(argv))
        if refusal:
            raise SessionError(refusal)
        output = "".join(f"line {n}\n" for n in range(400))
        return {"ok": True, "part": {"id": argv[4], "message": argv[3], "tool": "bash", "call": "call_c20",
                                     "status": "completed", "title": "", "input": '{"command": "ls studies/"}',
                                     "output": output, "error": "", "length": {"input": 26, "output": len(output)},
                                     "cut": {"input": False, "output": False}}}  # fmt: skip

    monkeypatch.setattr(kernel.parts["agents"].sessions, "_bridge", bridge)
    return ran


def parts(ran: list[list[str]]) -> list[list[str]]:
    """The bridge's runs that read a call whole (the console's other pages run it too: the MCP servers' list)."""
    return [argv for argv in ran if argv[0] == "part"]


def window(app: ClankConsole) -> CallScreen:
    screen = app.screen
    assert isinstance(screen, CallScreen)
    return screen


def calls(app: ClankConsole) -> CallsList:
    return app.query_one("#monitor-calls-list", CallsList)


async def test_enter_on_a_call_reads_it_whole_through_the_bridge_once_and_only_while_the_page_is_on_screen(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = bridged(kernel, monkeypatch)
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        await settle(pilot, lambda: len(calls(app).shown) > 0)
        await pilot.pause(1.5)
        assert parts(ran) == [], "the panel lists the calls from the flow: nothing through the bridge"
        await pilot.press("t", "enter")
        await settle(pilot, lambda: isinstance(app.screen, CallScreen))
        assert parts(ran) == [["part", str(PORT), SESSION, "msg_19", "c20"]], "the newest call, read whole once"
        shown = "\n".join(window(app).lines)
        assert "line 399" in shown, "its whole output"
        assert "Its output (3,490 characters)" in shown
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, CallScreen))
        await pilot.press("down", "enter")
        await settle(pilot, lambda: isinstance(app.screen, CallScreen))
        assert parts(ran)[-1] == ["part", str(PORT), SESSION, "msg_18", "c19"], "the call highlighted"
        await pilot.press("escape", "f1")
        await settle(pilot, lambda: not page.display)
        count = len(parts(ran))
        await pilot.pause(1.5)
        assert len(parts(ran)) == count, "nothing reaches the bridge for the Monitor while the page is not on screen"


async def test_a_call_the_bridge_cannot_give_whole_shows_what_the_flow_keeps_and_why(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = "myproject's container runs an older sandbox image: stop the workspace and open it again"
    bridged(kernel, monkeypatch, refusal=older)
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        await settle(pilot, lambda: len(calls(app).shown) > 0)
        await pilot.press("t", "down", "enter")
        await settle(pilot, lambda: isinstance(app.screen, CallScreen))
        shown = "\n".join(window(app).lines)
        assert f"Not read whole: {older}" in shown
        assert "python -m myproject sweep --sizes 8 16 32 64 128 256" in shown, "what the flow keeps of it"
        assert "Tool execution aborted" in shown, "its error"


async def test_a_session_followed_with_no_call_yet_says_so_in_tool_calls(
    kernel: Kernel, client: Client, home: Home
) -> None:
    kernel.settings.write("workspace", WORKSPACE, {"path": FOLDER}, base=None, actor=YOU)
    info = {"id": SESSION, "title": "A fresh session", "time": {"created": 1, "updated": 2}}
    tell(kernel, [{"type": "session.updated", "properties": {"sessionID": SESSION, "info": info}}, status("busy")])
    tell(kernel, [*updated(user("msg_1", 1000, "Plan the study.")),
                  *updated(step("msg_2", "msg_1", 2000, [text("p_1", "Reading the notes.")]))])  # fmt: skip
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        said = app.query_one("#monitor-session-calls").query_one(Empty)
        await settle(pilot, lambda: page.seen is not None and page.seen.head is not None)
        await settle(pilot, lambda: str(said.content) == "no tool call yet")
        assert said.display
        assert not calls(app).display


async def test_when_rows_are_short_tool_calls_give_up_rows_so_no_panel_is_cut(
    kernel: Kernel, client: Client, home: Home
) -> None:
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 40)) as pilot:
        page = await opened(pilot, app)
        await settle(pilot, lambda: len(calls(app).shown) > 0)
        await settle(pilot, lambda: page.max_scroll_y == 0 and calls(app).size.height > 0)
        await pilot.pause(0.6)  # a few ticks: it stays so
        assert page.max_scroll_y == 0, "the Session view fits the page: nothing below its last row"
        assert 0 < calls(app).size.height < ROWS, "Tool calls gave up rows"
        bottom = page.scrollable_content_region.bottom
        for panel in page.panels("session"):
            if panel.display and panel.region.height:
                assert panel.region.bottom <= bottom, f"{panel.id} is not cut"
    taller = make(client, home)
    async with taller.run_test(size=(160, 60)) as pilot:
        await opened(pilot, taller)
        await settle(pilot, lambda: calls(taller).size.height == ROWS)  # with room, it keeps its rows
