"""Design 0012 §2 and §7 (§11 step 7): `l` on the Session view shows the live text, a panel under the Flow with the
followed session's request as it is written (its thinking dimmed, its answer, its calls' arguments in the calls'
color), from the gateway's live view of that session (`GET /gateway/live?session=`); `l` again hides it. The text is
read from the offset already held, so each reading brings only what is new (one at a time, the next once the last
one's answer is in, however slowly it comes), and a new request is read from its start;
it is read only while it is shown: on the Session view, with the page on screen. Frames: the Session view at 128
columns with the live text."""

import time
from functools import partial
from typing import Any

import pytest

from clank.client import Client
from clank.components.agents.console.following import Watching
from clank.components.agents.console.livepanel import LiveView
from clank.components.agents.console.monitor import MonitorPage
from clank.console.app import ClankConsole
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import facts_of, route
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_flow import board, chart, known, make, opened
from tests.console.test_monitor_now import gateway_of, streaming, writing
from tests.support.flowlines import SESSION

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
THINKING = "The grid needs three sizes; the user asked for 16, 32 and 64. "
CALL = '\n→ bash {"command": "python -m myproject sweep --sizes 16 32 64"'


def written(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, switch: int = 0) -> list[dict[str, Any]]:
    """The gateway's live view of the session: request r-9 writes its thinking and a call, a little more at each look
    until it is whole; after `switch` looks (if given), r-10 begins. Each look's question is kept."""
    asked: list[dict[str, Any]] = []
    whole = [["thinking", THINKING * 3], ["tool", CALL]]

    def live(after: int = 0, id: str = "", session: str = "", subagents: bool = False) -> dict[str, Any]:
        asked.append({"after": after, "id": id, "session": session})
        if switch and len(asked) > switch:  # the next request began
            parts, length, request = [["answer", "Done: the grid is written."]], 26, "r-10"
        else:
            text = "".join(part[1] for part in whole)
            length = min(len(text), 60 + 20 * len(asked))
            parts, request = _from(whole, after, length), "r-9"
        meta = {"id": request, "phase": "answering", "tokens": length // 4, "seconds": 36.0, "role": "agent",
                "per_second": 48.0, "session": SESSION, "parent": ""}  # fmt: skip
        return {"newest": request, "id": request, "flying": True, "meta": meta, "asked": "Keep the grid to 3 sizes.",
                "length": length, "parts": parts, "problem": ""}  # fmt: skip

    monkeypatch.setattr(kernel.parts["gateway"], "live", live)
    monkeypatch.setattr(kernel.parts["gateway"], "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(kernel.parts["gateway"], "facts", facts_of)
    return asked


def _from(parts: list[list[str]], after: int, length: int) -> list[list[str]]:
    """The parts of a text between two offsets."""
    found, start = [], 0
    for kind, text in parts:
        end = start + len(text)
        if end > after and start < length:
            found.append([kind, text[max(0, after - start) : max(0, length - start)]])
        start = end
    return found


def shows(page: MonitorPage, view: str) -> bool:
    return page.view == view


def live(app: ClankConsole) -> LiveView:
    return app.query_one("#monitor-live-view", LiveView)


async def test_l_shows_the_followed_sessions_live_text_and_hides_it_again(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, writing())
    written(kernel, monkeypatch)
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 60)) as pilot:
        await opened(pilot, app)
        panel = app.query_one("#monitor-session-live")
        assert not panel.display, "hidden until l"
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await pilot.press("l")
        await settle(pilot, lambda: panel.region.height > 0 and "python -m myproject sweep" in live(app).text.plain)
        assert any(span.style == "$clank-part-calls" for span in live(app).text.spans), "a call in the calls' color"
        assert live(app).text.plain.startswith(THINKING)
        await settle(pilot, lambda: known(app) and live(app).text.plain.endswith('--sizes 16 32 64"'))
        assert_frame(await steady_frame(pilot, app), "monitor-session-live-160")
        await pilot.press("l")
        await settle(pilot, lambda: panel.region.height == 0)


@pytest.mark.parametrize("slow", [False, True])
async def test_the_live_text_is_read_from_its_offset_only_while_shown_and_a_new_request_from_its_start(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch, slow: bool
) -> None:
    streaming(kernel, monkeypatch)
    asked = written(kernel, monkeypatch, switch=12)
    if slow:  # a slower machine: a reading's answer reaches the page well after its question is done
        text = Watching.text

        def slowly(self: Watching, session: str, after: int, request: str) -> dict[str, Any] | None:
            found = text(self, session, after, request)
            time.sleep(0.6)
            return found

        monkeypatch.setattr(Watching, "text", slowly)
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 60)) as pilot:
        await opened(pilot, app)
        await pilot.pause(1.5)
        assert asked == [], "not read while hidden"
        await pilot.press("l")
        await settle(pilot, lambda: len(asked) >= 5)
        assert asked[0] == {"after": 0, "id": "", "session": SESSION}, "the session's own, from its start"
        assert all(each["session"] == SESSION for each in asked)
        assert [each["after"] for each in asked[1:4]] == [80, 100, 120], "each from the offset held"
        assert asked[1]["id"] == "r-9", "the request it follows"
        await settle(pilot, lambda: live(app).request == "r-10")
        await settle(pilot, lambda: live(app).text.plain == "Done: the grid is written.")
        begun = next(index for index, each in enumerate(asked) if each["id"] == "r-10")
        assert asked[begun]["after"] == 0, "a new request: read from its start"
        page = app.query_one("#page-monitor", MonitorPage)
        for view in ("context", "flow"):  # F10 to the Context view, then to the Flow view: the live text is not on them
            await pilot.press("f10")
            await settle(pilot, partial(shows, page, view))
            await pilot.pause(0.5)  # a reading that began before
            count = len(asked)
            await pilot.pause(1.5)
            assert len(asked) == count, f"not read on the {view} view, where it is not shown"
        await pilot.press("f10")  # the Session view again, where it is still shown
        count = len(asked)
        await settle(pilot, lambda: len(asked) > count)
        await pilot.press("l")
        await pilot.pause(0.5)
        count = len(asked)
        await pilot.pause(1.5)
        assert len(asked) == count, "hidden: not read"
