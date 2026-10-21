"""Design 0012 §2, §9.1, §9.2, §9.3 and §9.6 (§11 step 9): the Monitor's Guide panel lists Stop now, a note and Compact
now with their keys, what each does briefly and what it costs, and under an action that ran its last state, when and by
whom; an action that cannot run now is drawn quiet with its reason. A note is about the node under the flow's cursor (a
call, its step and its words; a step, its number). On the Session view the page takes the keys: `.` stops at once, `m`
opens the note's window (what it is about filled in, which the owner may change) and sends it, `k` asks first (Enter
does it, Esc leaves it); one that cannot run says why on the message line. Design 0012 §9.4 (§11 step 11): the panel
lists the pause after Compact now with its state and its timer (pausing after this step, held, resumed), and `p` asks
first, then pauses the session, and `p` again resumes it. Frame: the Session view at 160 columns with board A's session
followed and its Guide."""

from datetime import UTC
from typing import Any

import pytest
from textual.content import Content
from textual.widgets import Input

from clank.client import Client
from clank.components.agents.console.flowtree import tree
from clank.components.agents.console.guidepanel import GuideList, about, lines
from clank.components.agents.guide import offer
from clank.console.confirm import ConfirmScreen
from clank.console.form import FormScreen
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_guide import ENDED, TOTALS, working
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_flow import board, chart, known, make, opened
from tests.support.flowlines import SESSION, tool

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def plain(found: list[Content]) -> list[str]:
    return [line.plain for line in found]


def test_the_panel_lists_stop_note_and_compact_with_their_keys_costs_and_states() -> None:
    kept = {"stop": {"state": "failed", "why": "the bridge refused", "time": "2026-10-20T04:12:00.000Z",
                     "by": "you (console)"}}  # fmt: skip
    guide = {"actions": offer(working().view(), port=4096, totals=TOTALS, ended=ENDED, kept=kept)}
    said = plain(lines(guide, 200, UTC))
    assert said == [
        ". Stop now    stops the step under way, rejects what waits · nothing read again",
        "  failed: the bridge refused · 04:12 · you (console)",
        "m Note        to planner, read at its next step · about 5,000 tokens read again, about 2.5 s",
        "k Compact now at the session's next step · about 21,000 tokens read again, about 10.5 s",
        "u Undo turn   the session works: stop it first (.); OpenCode takes back no step while a session works",
        "x Drop        no finished call's result is left to clear",
    ]
    assert all(len(line) <= 40 for line in plain(lines(guide, 40))), "no line wider than the panel"
    assert plain(lines(None, 40)) == ["no session yet"]


def test_an_action_that_cannot_run_is_grayed_with_its_reason() -> None:
    guide = {"actions": offer(working("idle").view(), port=4096, totals=TOTALS, ended=ENDED, kept={})}
    [stop, note, _, undo, _] = lines(guide, 200)
    assert stop.plain == ". Stop now    the session is idle and nothing waits in it: there is nothing to stop"
    assert any("quiet" in str(span.style) for span in stop.spans if "idle" in stop.plain[span.start : span.end])
    assert note.plain.startswith("m Note        to planner, starts a run")
    assert undo.plain == "u Undo turn   takes back your message and steps 4 and 5 · its cost to measure"


def test_the_note_is_about_the_node_under_the_flows_cursor() -> None:
    from tests.components.agents.test_guide import BEGUN, hear

    flow = working()
    hear(flow, [{"type": "message.updated", "properties": {"sessionID": SESSION, "info": {
        "id": "msg_07", "sessionID": SESSION, "role": "assistant", "parentID": "msg_04",
        "time": {"created": BEGUN + 70_000}, "agent": "planner", "modelID": "agent", "providerID": "clank"}}},
        {"type": "message.part.updated", "properties": {"sessionID": SESSION, "part": {
            **tool("c7", "bash", "completed", input={"command": "pytest -q"}), "sessionID": SESSION,
            "messageID": "msg_07"}}}])  # fmt: skip
    view = flow.view()
    nodes: dict[str, Any] = {}

    def walk(node: Any) -> None:
        nodes[node.id] = node
        for child in node.children:
            walk(child)

    root = tree(view)
    walk(root)
    assert about(nodes["c7"], view) == "step 6, `bash pytest -q`"
    assert about(nodes["msg_06"], view) == "step 5"
    assert about(root, view) == ""
    assert about(None, view) == ""


async def test_dot_stops_at_once_m_sends_a_note_and_k_asks_first(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    done: list[tuple[str, dict[str, Any]]] = []

    def stopped(workspace: str, session: str, *, actor: Any) -> Any:
        done.append(("stop", {"session": session}))
        return {"state": "stopping"}

    def compacted(workspace: str, session: str, *, actor: Any) -> Any:
        done.append(("compact", {"session": session}))
        return {"state": "asked"}

    def noted(workspace: str, session: str, text: str, *, actor: Any, about: str = "", reject: bool = True) -> Any:
        done.append(("note", {"text": text, "about": about}))
        return {"sent": True}

    monkeypatch.setattr(agents.guide, "stop", stopped)
    monkeypatch.setattr(agents.guide, "compact", compacted)
    monkeypatch.setattr(agents.guide, "note", noted)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)
        await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
        await settle(pilot, lambda: chart(app).cursor == "msg_21")
        await pilot.press("full_stop")
        await settle(pilot, lambda: done == [("stop", {"session": SESSION})])
        await pilot.press("k")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert any("summarize" in line for line in asking.lines)
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
        await pilot.press("k", "enter")
        await settle(pilot, lambda: done[-1] == ("compact", {"session": SESSION}))
        await pilot.press("m")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        assert app.screen.query_one("#form-about", Input).value == "step 19"
        await pilot.press(*"Use a log scale.", "ctrl+s")
        await settle(pilot, lambda: done[-1] == ("note", {"text": "Use a log scale.", "about": "step 19"}))
        assert [each for each, _ in done] == ["stop", "compact", "note"]


async def test_an_action_that_cannot_run_says_why_and_the_session_view_with_the_guide_at_160_columns(
    kernel: Kernel, client: Client, home: Home
) -> None:
    board(kernel)  # no watcher saw the session run: no server to act on
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)
        await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await pilot.press("full_stop")
        await settle(pilot, lambda: "Stop now cannot run now: no OpenCode server" in str(
            app.query_one("#message").render()))  # fmt: skip
        await settle(pilot, lambda: known(app))
        assert_frame(await steady_frame(pilot, app), "monitor-session-guide-160")


def test_the_panel_lists_the_pause_with_its_state_and_its_timer() -> None:
    pause = {"action": "pause", "key": "p", "title": "Pause", "can": True, "why": "",
             "brief": "after this step: its next request waits in the gateway", "does": "", "calls": [],
             "cost": {"tokens": 0, "seconds": 0.0, "words": "nothing while held: nothing is read again"},
             "confirm": True, "paused": False, "state": None}  # fmt: skip
    assert plain(lines({"actions": [pause]}, 200, UTC)) == [
        "p Pause       after this step: its next request waits in the gateway · nothing read again",
    ]
    held = {"state": "held", "time": "2026-10-20T12:22:00.000Z", "by": "you (console)", "why": "", "step": None,
            "seconds": 187.4}  # fmt: skip
    resume = {**pause, "title": "Resume", "brief": "the held request goes to the model", "paused": True, "state": held}
    assert plain(lines({"actions": [resume]}, 200, UTC)) == [
        "p Resume      the held request goes to the model · nothing read again",
        "  held 3:07: p resumes it · 12:22 · you (console)",
    ]
    waiting = {**resume, "state": {**held, "state": "pausing after this step", "seconds": None}}
    assert plain(lines({"actions": [waiting]}, 200, UTC))[1] == "  pausing after this step · 12:22 · you (console)"


async def test_p_pauses_the_session_once_confirmed_and_p_again_resumes_it(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    agents = kernel.parts["agents"]
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, session: 4096)
    done: list[str] = []
    paused = [False]

    def action(workspace: str, session: str) -> dict[str, Any]:
        return {"action": "pause", "key": "p", "title": "Resume" if paused[0] else "Pause", "can": True, "why": "",
                "brief": "after this step", "does": "the next model request waits in the gateway",
                "calls": [f"PUT /holds/{session}"], "cost": {"tokens": 0, "seconds": 0.0, "words": "nothing"},
                "confirm": True, "paused": paused[0], "state": None, "session": session}  # fmt: skip

    def pause(workspace: str, session: str, *, actor: Any) -> dict[str, Any]:
        done.append(f"pause {session}")
        paused[0] = True
        return {"session": session}

    def resume(workspace: str, session: str, *, actor: Any) -> dict[str, Any]:
        done.append(f"resume {session}")
        paused[0] = False
        return {"session": session}

    monkeypatch.setattr(agents.pausing, "action", action)
    monkeypatch.setattr(agents.pausing, "pause", pause)
    monkeypatch.setattr(agents.pausing, "resume", resume)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one("#monitor-guide-list", GuideList)
        await settle(pilot, lambda: listed.guide is not None and bool(listed.guide.get("actions")))
        await pilot.press("p")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asking = app.screen
        assert isinstance(asking, ConfirmScreen)
        assert any("PUT /holds/" in line for line in asking.lines)
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
        assert done == [], "Esc leaves it"
        await pilot.press("p", "enter")
        await settle(pilot, lambda: done == [f"pause {SESSION}"])
        await settle(pilot, lambda: listed.guide is not None and next(
            each for each in listed.guide["actions"] if each["action"] == "pause")["paused"])  # fmt: skip
        await pilot.press("p", "enter")
        await settle(pilot, lambda: done == [f"pause {SESSION}", f"resume {SESSION}"])
