"""Design 0012 §2, §5 and §11 step 7: the Monitor's Now panel says what the followed session does this second, as the
service says it: the phase in §5.1's words (reading the prompt "or queued"), the step and its seconds, the prompt, the
thinking and the output against their budgets ("about" while counted live), the call being written, the speed with a
spark of each step's, and the loop guard; no line wider than the panel. The spinner is a cell of its own, so a turn
touches only that cell (design 0012 §2). While the model writes, the page redraws at most four times a second (§2,
design 0001 §5.7), and it reads what the session does now four times a second only while the session works, once a
second while it does not, and never while the page is not on screen. Frames: the Session view at 128 columns while the
model writes a call."""

import time
from typing import Any

import pytest
from textual.content import Content
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console import monitor
from clank.components.agents.console.following import Seen
from clank.components.agents.console.nowpanel import NowSpin, NowView, head, lines
from clank.components.agents.now import now
from clank.console import app as console_app
from clank.console.app import ClankConsole
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import ended, facts_of, held, route
from tests.components.agents.test_monitor_now import MOMENT, ON, a_call, a_step, flying, view, with_requests
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_flow import board, chart, make, opened
from tests.support import flowlines

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
PARTS = [{"part": "thinking", "name": "", "share": 0.31, "stretch": 2000},
         {"part": "tool 0", "name": "bash", "share": 0.124, "stretch": 2000}]  # fmt: skip
WRITING = {"tool": "bash", "arguments": '{"command": "python -m myproject.sweep --sizes 3"'}
BEFORE = (ended("r-1", 100000, 900, cached=96000, per_second=41.0),
          ended("r-2", 153614, 1415, cached=147815, per_second=47.5))  # fmt: skip


def writing(session: str = flowlines.SESSION, seconds: float = 36.1) -> dict[str, Any]:
    """The gateway's activity of a session whose step 30 writes a `bash` call."""
    counts = {"thinking": 1203, "answer": 40, "tool": 172}
    request = flying(newest="tool", writing=WRITING, counts=counts, session=session, seconds=seconds,
                     loop_guard={"ratio": 0.06, "parts": PARTS})  # fmt: skip
    return with_requests(request, ended_too=BEFORE)


def plain(found: dict[str, Any], width: int = 200) -> list[str]:
    return [head(found).plain, *[line.plain for line in lines(found, width)]]


def told(gateway: dict[str, Any], flow: dict[str, Any] | None, preset: str | None = "daily-262k",
         guard: dict[str, Any] = ON) -> dict[str, Any]:  # fmt: skip
    """What the service says the board's session does now."""
    return now(flowlines.SESSION, gateway, flow, route(preset), facts_of, guard, MOMENT)


def test_the_now_panel_says_the_phase_its_budgets_the_prompt_the_call_being_written_the_speed_and_the_loop_guard() -> (
    None
):
    said = plain(told(writing(), view("busy", a_step(30))))
    assert said[0] == "writing a call · step 30 · 36.1 s"
    assert said[1] == "prompt      read in 1.0 s"
    assert said[2] == "last prompt 147,815 cached, 5,799 new", "the step before's: a prompt's size comes at its end"
    assert said[3].startswith("thinking    ███")
    assert said[3].endswith(" about 1,203 of 4,096")
    assert said[4].endswith(" about 1,415 of 16,384")
    assert said[5] == "writing     bash python -m myproject.sweep --sizes 3", "its first argument's name left out"
    assert said[6].startswith("speed       48 tok/s  ")
    assert len(said[6]) == len("speed       48 tok/s  ") + 3, "a spark cell for each step's speed"
    assert said[7] == "loop guard  thinking 31%, bash 12% · limit 6%"
    reading = flying("reading the prompt", seconds=3.2, first_ms=None, session=flowlines.SESSION)
    assert plain(told(with_requests(reading, ended_too=BEFORE), view()))[:2] == [
        "reading the prompt (or queued) · 3.2 s",
        "prompt      being read for 3.2 s (or queued)",
    ]
    tool = told(with_requests(), view("busy", a_step(31), a_call(input='{"command": "pytest -q"}')))
    assert plain(tool)[0] == "running a tool · step 31 · 4.0 s · bash pytest -q"
    counts = {"thinking": 1203, "answer": 40, "tool": 172}
    finished = {**ended("r-3", 150000, 1502, cached=148000, per_second=48.0), "counts": counts}
    idle = told(with_requests(ended_too=(*BEFORE, finished)), view("idle", a_step(30, "finished")),
                guard={"on": False, "ratio": 0.06})  # fmt: skip
    said = plain(idle)
    assert said[0] == "idle · step 30"
    assert said[2] == "last prompt 148,000 cached, 2,000 new", "the last step's own, once it ended"
    assert said[4].endswith(" 1,502 of 16,384"), "the engine's own count, no longer about"
    assert said[3].endswith(" about 1,277 of 4,096"), "the thinking scaled to it, still about"
    assert said[5] == "writing     no call being written"
    assert said[7] == "loop guard  off (config/gateway.json, applied when the gateway restarts)"
    stopped = told(with_requests(ended_too=(ended("r-4", 9000, 300, looped="its thinking repeated itself"),)),
                   view("idle", a_step(31, "failed")))  # fmt: skip
    assert (
        plain(stopped)[0]
        == "stopped by the loop guard · step 31 · the session is idle; that text is not in the context"
    )
    assert plain(stopped)[7] == "loop guard  stopped its thinking repeated itself"


def test_a_loop_guard_setting_that_waits_for_the_gateways_restart_is_said() -> None:
    waiting = {"on": False, "ratio": 0.06, "file": {"on": True, "ratio": 0.06}}
    off = told(with_requests(ended_too=BEFORE), view("idle", a_step(30, "finished")), guard=waiting)
    assert plain(off)[7] == "loop guard  off in the running gateway; on once it restarts (config/gateway.json)"
    guarding = {"on": True, "ratio": 0.06, "file": {"on": False, "ratio": 0.06}}
    on = plain(told(writing(), view("busy", a_step(30)), guard=guarding))[7]
    assert on == "loop guard  thinking 31%, bash 12% · limit 6% · changed in config/gateway.json: at its restart"


def test_no_now_line_is_wider_than_the_panel() -> None:
    retry = view("retry", attempt=3, retry="Provider is overloaded " * 9, next=(MOMENT + 30) * 1000)
    cases = [
        told(writing(), view("busy", a_step(30))),
        told(with_requests(), retry, preset="cpu-8k"),
        told(with_requests(), None, preset=None),
        {"session": flowlines.SESSION, "unavailable": "the gateway did not answer in 2 seconds"},
    ]
    for width in range(12, 161):
        for found in cases:
            assert all(isinstance(line, Content) and line.cell_length <= width for line in lines(found, width)), width
    assert lines(None, 40) == []
    assert head(None).plain == "no session yet"


def gateway_of(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, activity: dict[str, Any]) -> None:
    """The service's gateway, as if the followed session's step 30 were writing a call on KVMem."""
    gateway = kernel.parts["gateway"]
    activity["slots"] = {"main": held("r-9", flowlines.SESSION, flying=True)}
    monkeypatch.setattr(gateway, "activity", lambda session="", subagents=False, ended=False: activity)
    monkeypatch.setattr(gateway, "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(gateway, "facts", facts_of)


def now_view(app: ClankConsole) -> NowView:
    return app.query_one("#monitor-now-view", NowView)


async def test_the_session_view_while_the_model_writes_at_128_columns(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, writing())
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await settle(pilot, lambda: "writing a call" in str(now_view(app).query_one("#now-head", Label).content))
        assert_frame(await steady_frame(pilot, app), "monitor-session-now-160")


async def test_the_spinner_touches_only_its_own_cells(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, writing())
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        view_ = now_view(app)
        await settle(pilot, lambda: "writing a call" in str(view_.query_one("#now-head", Label).content))
        await steady_frame(pilot, app)
        panel = app.query_one("#monitor-session-now").region
        spin = view_.query_one(NowSpin).region
        draws, before = view_.draws, render_text(app).splitlines()
        for frame in range(1, 6):
            view_.spin(frame)
            await pilot.pause(0.05)
            after = render_text(app).splitlines()
            changed = {(y, x) for y in range(panel.y, panel.bottom) for x in range(panel.x, panel.right)
                       if _cell(before, y, x) != _cell(after, y, x)}  # fmt: skip
            assert changed <= {(spin.y, x) for x in range(spin.x, spin.right)}, f"frame {frame}: only its cell"
            before = after
        assert view_.draws == draws, "the panel's other lines were not drawn again"
        assert view_.turns >= 5


def _cell(frame: list[str], y: int, x: int) -> str:
    row = frame[y] if y < len(frame) else ""
    return row[x] if x < len(row) else " "


def streaming(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The service's gateway, as if the followed session's answer streamed on: each look at it finds more tokens and
    more time (the state the test changes: `working` False makes the session's request end)."""
    state: dict[str, Any] = {"looks": 0, "working": True}

    def activity(session: str = "", subagents: bool = False, ended: bool = False) -> dict[str, Any]:
        state["looks"] += 1
        if not state["working"]:
            return {**with_requests(ended_too=BEFORE), "slots": {}}
        counts = {"thinking": 1203 + state["looks"], "answer": 40, "tool": 172}
        request = flying(newest="tool", writing=WRITING, counts=counts, session=flowlines.SESSION,
                         seconds=36.1 + state["looks"] / 10)  # fmt: skip
        return {**with_requests(request, ended_too=BEFORE), "slots": {}}

    gateway = kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "activity", activity)
    monkeypatch.setattr(gateway, "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(gateway, "facts", facts_of)
    return state


async def test_while_the_model_writes_the_page_redraws_at_most_four_times_a_second(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    streaming(kernel, monkeypatch)
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        view_ = now_view(app)
        await settle(pilot, lambda: "writing a call" in str(view_.query_one("#now-head", Label).content))
        redraws, draws, began = page.redraws, view_.draws, time.monotonic()
        await pilot.pause(3.0)
        seconds = time.monotonic() - began
        assert page.redraws - redraws <= 4 * seconds + 1, "the page: at most four redraws a second"
        assert view_.draws - draws <= 4 * seconds + 1
        assert view_.draws - draws >= 2 * seconds, "what the session does now, read and drawn while it works"


async def test_now_is_read_four_times_a_second_only_while_the_session_works_and_never_while_the_page_is_not_on_screen(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = streaming(kernel, monkeypatch)
    board(kernel)
    app = make(client, home)
    asked: list[str] = []
    get = Client.get

    def counted(self: Client, path: str, **params: Any) -> Any:
        asked.append(path)
        return get(self, path, **params)

    now_path = f"agents/now/myproject/{flowlines.SESSION}"
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        await settle(pilot, lambda: "writing a call" in str(now_view(app).query_one("#now-head", Label).content))
        monkeypatch.setattr(Client, "get", counted)
        await pilot.pause(2.0)
        assert asked.count(now_path) >= 5, "about four times a second while the session works"
        state["working"] = False
        kernel.parts["agents"].flows.heard("myproject", {"type": "status", "port": flowlines.PORT,
                                                         "session": flowlines.SESSION, "status": "idle"})  # fmt: skip
        await settle(pilot, lambda: str(now_view(app).query_one("#now-head", Label).content).startswith("idle"))
        asked.clear()
        await pilot.pause(2.0)
        assert 1 <= asked.count(now_path) <= 3, "about once a second while it does not"
        await pilot.press("f1")
        await settle(pilot, lambda: not page.display)
        await pilot.pause(0.3)  # a reading that began before
        asked.clear()
        await pilot.pause(1.5)
        assert not [path for path in asked if path.startswith(("agents/now", "agents/flow", "gateway/live"))], (
            "nothing read while the page is not on screen"
        )


async def test_a_session_followed_again_shows_what_it_does_now_though_that_did_not_change(
    kernel: Kernel, client: Client, home: Home
) -> None:
    board(kernel)
    kernel.parts["agents"].flows.heard("myproject", {"type": "status", "port": flowlines.PORT,
                                                     "session": flowlines.SESSION, "status": "idle"})  # fmt: skip
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        said = now_view(app).query_one("#now-head", Label)
        await settle(pilot, lambda: str(said.content).startswith("idle"))
        followed = page.seen
        assert followed is not None
        page._came = Seen("myproject")  # for a moment the folder's workspace had no session to follow
        await settle(pilot, lambda: str(said.content) == "no session yet")
        page._came = followed  # then the same session again, idle as before
        await settle(pilot, lambda: str(said.content).startswith("idle"))
        assert now_view(app).now is not None


async def test_a_tool_running_turns_only_the_now_cell_at_most_four_times_a_second_not_the_consoles_spinner(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(console_app, "SPIN_SECONDS", 0.1)  # the console's own spinner, not held still here
    monkeypatch.setattr(monitor, "TURN_SECONDS", 0.2)  # nor the page's
    board(kernel)  # the session works between its steps; the gateway is stopped, so no model request is in flight
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        view_ = now_view(app)
        await settle(pilot, lambda: view_.working)
        frame, turns, began = app.frame, view_.turns, time.monotonic()
        await pilot.pause(2.0)
        seconds = time.monotonic() - began
        assert not app.busy(), "the session's work is not the console's: no operation, no model request"
        assert app.frame == frame, "the console's spinner stays still"
        assert "working" not in str(app.query_one("#header-left", Label).content)
        assert 2 <= view_.turns - turns <= 4 * seconds + 1, "the Now cell turns on the page's ticks"
        streaming(kernel, monkeypatch)  # now a model request streams: the console's spinner turns, as before
        await settle(pilot, lambda: app.frame > frame)
        turns, began = view_.turns, time.monotonic()
        await pilot.pause(2.0)
        seconds = time.monotonic() - began
        assert view_.turns - turns <= 4 * seconds + 1, "the Now cell keeps the page's rhythm, not the console's ten"
