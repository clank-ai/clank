"""Design 0012 §2, §9.1, §9.5 and §9.7 (§11 step 10): the Monitor's Guide panel lists Undo (Undo turn, or Redo while a
revert is pending) and Drop with their keys, what each does briefly, and under one that ran its state (undone, the turn
undone, final, redone; clearing, cleared). On the Session view `u` asks first, its window the preview (the steps, the
files and the owner's messages it takes back, and why the step alone is refused when the turn is offered) and the exact
call; Enter undoes, sending the revert the window showed, and after the turn is undone the note window opens with its
text; `u` while a revert is pending redoes. `x` drops the call under the flow's cursor, or the call highlighted in Tool
calls when that panel has the focus: its window asks first, says what it frees and costs and that the drop is final;
one that cannot run says why on the message line. They are the Session view's keys: on the Flow view they open nothing
of the Guide's. An undo is sent with the revert and what it takes back as its window showed them, the words it gives
back open whole in a window of several lines (Esc keeps them for `m`), and a warning that OpenCode took back more is
shown in a window; `?` says an action's last state whole."""

from datetime import UTC
from typing import Any

import pytest
from textual.content import Content
from textual.widgets import TextArea

from clank.client import Client
from clank.components.agents.console.guidepanel import GuideList, lines, whole
from clank.components.agents.guide import offer
from clank.console.confirm import ConfirmScreen
from clank.console.details import DetailsScreen
from clank.console.editor import EditScreen
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_guide import ENDED, TOTALS
from tests.components.agents.test_guide_undo_and_drop import heard, made, three
from tests.console.frames import settle
from tests.console.test_monitor_flow import board, chart, make, opened, tell
from tests.support.flowlines import reverted, status

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
TIME = "2026-10-20T04:12:00.000Z"
WORDS = 'Plot it so:\n\n    plt.loglog(n, tau)\n    plt.savefig("tau.pdf")\n\nKeep the grid to 3 sizes.'


def plain(found: list[Content]) -> list[str]:
    return [line.plain for line in found]


def test_the_panel_lists_undo_and_drop_with_their_keys_and_states() -> None:
    flow = made(three())
    shown = plain(lines({"actions": offer(flow.view(), port=4096, totals=TOTALS, ended=ENDED, kept={})}, 200, UTC))
    assert shown[-2:] == [
        "u Undo        takes back steps 2 and 3 · its cost to measure",
        "x Drop        clears a finished call's result: x on a call in the flow or in Tool calls",
    ]
    heard(flow, [reverted("msg_01", "prt_01_d")])
    kept: dict[str, dict[str, Any]] = {
        "undo": {"state": "undone", "ids": ["msg_02", "msg_03"], "what": "steps 2 and 3", "time": TIME,
                 "by": "you (console)"},
        "drop": {"state": "cleared", "part": "prt_01_b", "what": "step 1's `edit`", "time": TIME,
                 "by": "you (console)"},
    }  # fmt: skip
    shown = plain(lines({"actions": offer(flow.view(), port=4096, totals=TOTALS, ended=ENDED, kept=kept)}, 200, UTC))
    assert shown[-4:] == [
        "u Redo        brings back steps 2 and 3 · its cost to measure",
        "  steps 2 and 3 undone: u redoes them until your next message · 04:12 · you (console)",
        "x Drop        clears a finished call's result: x on a call in the flow or in Tool calls",
        "  clearing step 1's `edit` result · 04:12 · you (console)",
    ]
    turn = {**kept["undo"], "mode": "turn", "what": "your message and step 2"}
    gone = made(three())
    shown = plain(lines({"actions": offer(gone.view(), port=4096, totals=TOTALS, ended=ENDED,
                                          kept={"undo": turn})}, 200, UTC))  # fmt: skip
    assert "  your message and step 2 brought back · 04:12 · you (console)" in shown, "redone: no revert pending"
    assert all(len(line) <= 40 for line in plain(lines({"actions": offer(flow.view(), port=4096, totals=TOTALS,
                                                                         ended=ENDED, kept=kept)}, 40)))  # fmt: skip


async def test_u_asks_first_then_undoes_and_the_turns_text_opens_in_the_note_window(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    tell(kernel, [status("idle")])
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    done: list[tuple[Any, ...]] = []
    given = {"answer": {"state": "undone", "mode": "turn", "text": "Keep the grid to 3 sizes.", "whole": True}}

    def undone(workspace: str, session: str, *, actor: Any, message: str, part: str, steps: Any, said: Any) -> Any:
        done.append(("undo", message, part, *steps, *said))
        return given["answer"]

    def redone(workspace: str, session: str, *, actor: Any) -> Any:
        done.append(("redo",))
        return {"state": "redone"}

    def noted(workspace: str, session: str, text: str, *, actor: Any, about: str = "", reject: bool = True) -> Any:
        done.append(("note", text, about))
        return {"sent": True}

    monkeypatch.setattr(agents.guide, "undo", undone)
    monkeypatch.setattr(agents.guide, "redo", redone)
    monkeypatch.setattr(agents.guide, "note", noted)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)

        def undo() -> dict[str, Any]:
            return next(each for each in (listed.guide or {}).get("actions") or [] if each["action"] == "undo")

        await settle(pilot, lambda: listed.guide is not None and undo()["can"])
        await pilot.press("u")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert asking.heading == "Undo turn"
        assert asking.lines[0] == (
            "step 19 is the first after your message: undoing it alone would take back your message too."
        )
        assert any('revert {"messageID": "msg_20"}' in line for line in asking.lines), "the exact call"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
        assert done == [], "Esc leaves it"
        given["answer"] = {"state": "undone", "mode": "turn", "text": WORDS, "whole": True}
        await pilot.press("u", "enter")
        await settle(pilot, lambda: isinstance(app.screen, EditScreen))
        assert done == [("undo", "msg_20", "", 19, "msg_20")], "the revert the window showed, and what it takes back"
        assert words(app) == WORDS, "line breaks, indentation and each message whole"
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: done[-1] == ("note", WORDS, ""))
        tell(kernel, [reverted("msg_20")])
        await settle(pilot, lambda: undo()["mode"] == "redo")
        await pilot.press("u")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        redo = app.screen
        assert isinstance(redo, ConfirmScreen)
        assert redo.heading == "Redo"
        await pilot.press("enter")
        await settle(pilot, lambda: done[-1] == ("redo",))
        given["answer"] = {"state": "undone", "mode": "step", "text": "Go on.", "whole": True}
        tell(kernel, [reverted()])
        await settle(pilot, lambda: undo()["mode"] == "turn")
        await pilot.press("u", "enter")
        await settle(pilot, lambda: isinstance(app.screen, EditScreen))
        assert words(app) == "Go on.", "any words an undo gives back"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, EditScreen))
        await pilot.press("m")
        await settle(pilot, lambda: isinstance(app.screen, EditScreen))
        assert words(app) == "Go on.", "Esc keeps them: m opens them again"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, EditScreen))
        further = "OpenCode took back from msg_20, not msg_21_s: your message and step 19, more than the preview said"
        given["answer"] = {"state": "undone", "mode": "turn", "text": "", "whole": True, "why": further}
        await pilot.press("u", "enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        told = app.screen
        assert isinstance(told, DetailsScreen)
        assert further in told.lines, "in a window, not a line the next message overwrites"
        await pilot.press("escape")
        given["answer"] = {**given["answer"], "text": "Keep the grid to 3 sizes."}
        await pilot.press("u", "enter")
        await settle(pilot, lambda: isinstance(app.screen, EditScreen))
        noting = app.screen
        assert isinstance(noting, EditScreen)
        assert further in noting.note, "said in the window that carries the words back"


def words(app: Any) -> str:
    """The words in the window that gives them back."""
    found: str = app.screen.query_one("#edit-text", TextArea).text
    return found


def test_the_guides_question_mark_says_the_reason_of_an_actions_last_state() -> None:
    flow = made(three())
    heard(flow, [reverted("msg_00")])
    further = "OpenCode took back from msg_00, not prt_01_d: your message and steps 1 to 3, more than the preview said"
    kept = {"undo": {"state": "undone", "mode": "turn", "ids": ["msg_00"], "what": "your message and steps 1 to 3",
                     "time": TIME, "by": "you (console)", "why": further}}  # fmt: skip
    said = whole({"actions": offer(flow.view(), port=4096, totals=TOTALS, ended=ENDED, kept=kept)})
    assert any(line.startswith("u Redo: ") and further in line for line in said), "the panel cuts it; ? says it whole"


async def up_to(pilot: Any, app: Any, id: str) -> None:
    """Up the flow until its cursor is on the node `id`."""
    for _ in range(40):
        if chart(app).cursor == id:
            return
        await pilot.press("up")
    assert chart(app).cursor == id


async def test_x_drops_the_call_under_the_flows_cursor_once_confirmed(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    done: list[str] = []

    def dropped(workspace: str, session: str, part: str, *, actor: Any) -> Any:
        done.append(part)
        return {"state": "cleared"}

    monkeypatch.setattr(agents.guide, "drop", dropped)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)
        await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
        await settle(pilot, lambda: chart(app).cursor == "msg_21")
        await pilot.press("f")
        await up_to(pilot, app, "c20")  # the newest call that finished
        await pilot.press("x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert asking.heading == "Drop step 18's `bash` result"
        assert any("The drop is final" in line for line in asking.lines)
        assert any("/message/msg_19/part/c20" in line for line in asking.lines), "the exact call"
        assert any(line.startswith("What it costs: frees about 30 tokens") for line in asking.lines)
        await pilot.press("enter")
        await settle(pilot, lambda: done == ["c20"])
        await up_to(pilot, app, "c19")  # the call before it, which failed
        await pilot.press("x")
        await settle(pilot, lambda: "Drop cannot run now: only a finished call's result is cleared; this one "
                        "failed" in str(app.query_one("#message").render()))  # fmt: skip
        await pilot.press("t", "x")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: done == ["c20", "c20"])  # Tool calls' highlighted call: the newest


async def test_u_and_x_do_nothing_of_the_guides_on_the_flow_view(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    tell(kernel, [status("idle")])
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)
        await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
        await pilot.press("f10", "f10")
        await settle(pilot, lambda: page.view == "flow")
        await pilot.press("u", "x")
        await pilot.pause(0.3)
        assert app.screen is page.screen, "no window of the Guide's opened: they are the Session view's keys"
        assert page.view == "flow"
