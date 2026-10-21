"""Design 0012 §3, §6.1, §2 and §11 step 6: the Monitor follows the newest active root session of the console's folder
(else the newest root session), reads its flow and its subagents' from the service, only what changed since the
version it holds, and draws it in the Flow panel; the heading line names the session (OpenCode, the workspace, its
title, its agent, what it does, its steps and calls, since when, that it is the newest), or says why none is followed.
A flow that did not change is neither read again nor drawn (design 0001 §5.7); what changed keeps the flow whole after
the service forgets old removals; one reading at a time; nothing is read while the page is not on screen (design 0012
§2: what asks Docker is read only while on screen). Frames: the Session view with board A's flow at 128, 88 and 60
columns."""

import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from textual.pilot import Pilot

from clank.client import Client
from clank.components.agents.console.flowpanel import FlowChart
from clank.components.agents.console.following import Following, merged, pick
from clank.components.agents.console.monitor import MonitorPage, heading
from clank.components.agents.console.nowpanel import NowView
from clank.components.agents.sessionflow import flow as flows
from clank.components.agents.sessionflow.flow import Flow
from clank.console.app import ClankConsole
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle, steady_frame
from tests.support.boards import OBSERVABLES, board_a_messages
from tests.support.flowlines import SESSION, lines, page, status, step, tool, updated, user

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
NOW = datetime(2026, 10, 19, 12, 21, tzinfo=UTC)
YOU = Actor(kind="user", via="console")
WORKSPACE = "myproject"


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def tell(kernel: Kernel, events: list[dict[str, Any]]) -> None:
    """The service's watchers hear these events of the folder's workspace."""
    for line in lines(events):
        kernel.parts["agents"].flows.heard(WORKSPACE, line)


def board(kernel: Kernel) -> None:
    """The folder is the workspace `myproject`, whose session is board A's, working, with its subagent's."""
    kernel.settings.write("workspace", WORKSPACE, {"path": FOLDER}, base=None, actor=YOU)
    messages, sub = board_a_messages()
    info = {"id": SESSION, "title": "Plan a new simulation study", "time": {"created": 1, "updated": 2}}
    child = {"id": OBSERVABLES, "parentID": SESSION, "title": "find observables", "time": {"created": 1, "updated": 2}}
    tell(kernel, [{"type": "session.updated", "properties": {"sessionID": SESSION, "info": info}}, status("busy")])
    tell(kernel, [event for message in messages for event in updated(message)])
    tell(kernel, [{"type": "session.updated", "properties": {"sessionID": OBSERVABLES, "info": child}}])
    tell(kernel, [event for message in sub for event in updated(message)])


def chart(app: ClankConsole) -> FlowChart:
    return app.query_one("#monitor-flow-chart", FlowChart)


def known(app: ClankConsole) -> bool:
    """Whether the Now panel says what the session followed does (read after its flow, plan s17)."""
    return app.query_one("#monitor-now-view", NowView).now is not None


async def opened(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    return page


def test_the_newest_active_root_session_is_followed_else_the_newest_root() -> None:
    heads = [
        {"session": "ses_child", "parent": "ses_a", "status": "busy"},
        {"session": "ses_b", "parent": "", "status": "idle"},
        {"session": "ses_a", "parent": "", "status": "busy"},
    ]  # newest heard first
    assert pick(heads) == heads[2], "the newest active root session, not a subagent's"
    assert pick([heads[1], {**heads[2], "status": "idle"}]) == heads[1], "none active: the newest root"
    assert pick([heads[0]]) is None, "a subagent alone is followed only from its parent"


def test_what_changed_since_a_version_brings_a_flow_up_to_date() -> None:
    messages, _ = board_a_messages()
    flow = Flow(SESSION, workspace=WORKSPACE)
    flow.history(page(messages[:10]))
    held = merged(None, flow.changes(0))
    for line in lines([event for message in messages[10:] for event in updated(message)]):
        flow.heard(line)
    since = held["version"]
    held = merged(held, flow.changes(since))
    whole = flow.view()
    assert [node["id"] for node in held["nodes"]] == [node["id"] for node in whole["nodes"]]
    assert held["nodes"] == whole["nodes"]
    assert (held["items"], held["head"], held["version"]) == (whole["items"], whole["head"], whole["version"])
    assert merged(held, flow.changes(held["version"]))["nodes"] == whole["nodes"], "nothing changed: the same"


def test_a_flow_kept_up_to_date_stays_whole_after_the_service_forgets_old_removals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(flows, "REMOVED_KEPT", 2)
    flow = Flow(SESSION, workspace=WORKSPACE)
    calls = [tool(f"c{n}", "bash", input={"command": f"echo {n}"}) for n in range(6)]
    for line in lines([*updated(user("msg_01", 1_000, "Count.")),
                       *updated(step("msg_02", "msg_01", 2_000, calls, completed=2_100))]):  # fmt: skip
        flow.heard(line)
    held = merged(None, flow.changes(0))
    base = flow.base
    for n in range(5):
        removed = {"sessionID": SESSION, "messageID": "msg_02", "partID": f"c{n}"}
        for line in lines([{"type": "message.part.removed", "properties": removed}]):
            flow.heard(line)
        changes = flow.changes(held["version"])
        assert changes["whole"] is False, "the client is not behind the service's base: only what changed"
        held = merged(held, changes)
        assert held["nodes"] == flow.view()["nodes"], f"after removal {n + 1}"
    assert flow.base != base, "the service forgot the oldest removals: its base moved"


def test_one_reading_at_a_time_a_second_one_meanwhile_asks_nothing() -> None:
    entered, release = threading.Event(), threading.Event()
    asked: list[str] = []

    class Slow:
        def get(self, path: str, **params: Any) -> Any:
            asked.append(path)
            if len(asked) == 1:
                entered.set()
                release.wait(5)
            if path == "workspaces/folder":
                return {"workspace": ""}
            raise AssertionError(path)

    following = Following(Slow(), FOLDER)  # type: ignore[arg-type]
    first = threading.Thread(target=following.read)
    first.start()
    assert entered.wait(5)
    try:
        assert following.read() is None, "a reading under way: none meanwhile"
        assert asked == ["workspaces/folder"], "and it asked the service nothing"
    finally:
        release.set()
        first.join(5)


async def test_the_monitor_draws_the_followed_sessions_flow_and_names_it_in_the_heading(
    kernel: Kernel, client: Client, home: Home
) -> None:
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        frame = await steady_frame(pilot, app)
        page = app.query_one("#page-monitor", MonitorPage)
        said = heading("session", page.seen, UTC).plain
        assert said == (
            "OpenCode · workspace myproject · “Plan a new simulation study” · build · working · 19 steps, 20 calls · "
            "since 11:58 · the newest of this folder"
        )
        assert said[:100] in frame, "the heading line, cut where the page is narrower (? says it whole)"
        assert chart(app).cursor == "msg_21", "following now"
        await pilot.press("f", "up", "up", "up", "up", "up", "up", "up", "right")
        await settle(pilot, lambda: any("subagent: find observables" in line.plain for line in chart(app).drawn.lines))
        assert chart(app).following is False


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 40), False, "monitor-session-flow-160"), ((160, 40), True, "monitor-session-flow-160-f5"),
     ((82, 50), False, "monitor-session-flow-82")],
)  # fmt: skip
async def test_the_session_view_with_board_as_flow_at_128_88_and_60_columns(
    kernel: Kernel, client: Client, home: Home, size: tuple[int, int], f5: bool, name: str
) -> None:
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=size) as pilot:
        await opened(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await settle(pilot, lambda: known(app))
        assert_frame(await steady_frame(pilot, app), name)


async def test_a_flow_that_did_not_change_is_not_read_again_or_drawn(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    app = make(client, home)
    asked: list[str] = []
    get = Client.get

    def counted(self: Client, path: str, **params: Any) -> Any:
        asked.append(path)
        return get(self, path, **params)

    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await steady_frame(pilot, app)
        monkeypatch.setattr(Client, "get", counted)
        laid = chart(app).laid_out
        await settle(pilot, lambda: asked.count(f"agents/flow/{WORKSPACE}") >= 2, seconds=5)
        assert f"agents/flow/{WORKSPACE}/{SESSION}" not in asked, "its version did not move: not read again"
        assert chart(app).laid_out == laid, "nothing drawn again"
        tell(kernel, [status("idle")])
        await settle(pilot, lambda: page.seen is not None and (page.seen.head or {}).get("status") == "idle")
        assert f"agents/flow/{WORKSPACE}/{SESSION}" in asked, "it changed: read again, what changed only"


async def test_nothing_is_read_while_the_page_is_not_on_screen(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    board(kernel)
    app = make(client, home)
    asked: list[str] = []
    get = Client.get

    def counted(self: Client, path: str, **params: Any) -> Any:
        asked.append(path)
        return get(self, path, **params)

    async with app.run_test(size=(160, 50)) as pilot:
        page = await opened(pilot, app)
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await pilot.press("f1")
        await settle(pilot, lambda: not page.display)
        await pilot.pause(0.3)  # a reading that began before
        monkeypatch.setattr(Client, "get", counted)
        await pilot.pause(2.5)
        assert not [path for path in asked if path.startswith("agents/flow") or path == "workspaces/folder"]
        await pilot.press("f10")
        await settle(pilot, lambda: f"agents/flow/{WORKSPACE}" in asked, seconds=5)


async def test_with_no_session_the_heading_says_why(kernel: Kernel, client: Client, home: Home) -> None:
    kernel.settings.write("workspace", WORKSPACE, {"path": FOLDER}, base=None, actor=YOU)
    app = make(client, home)
    async with app.run_test(size=(200, 40)) as pilot:
        await opened(pilot, app)
        frame = await frame_when(pilot, app, "has been seen working")
    assert "No session yet · none of myproject's sessions has been seen working since the service started" in frame
    assert "no session yet" in frame, "the Flow panel says so too"
