"""Design 0012 §6.1 and §11 step 5 (decision 0049): the service keeps a flow for every session its watchers see, in
memory. A session joined mid-run is read from OpenCode's history, its earlier steps marked done before Clank watched
(run against the fake OpenCode with the bridge on this machine, and read through the API, whole or what changed); a
flow is read again after its server's instance ended, and after its watcher started again once that watcher synced;
the gateway is asked for a session's requests after its steps change, and they are paired with its steps; the plan a
session carries out is read from the workspace's folder, and again when the agent edits it; a subagent's flow tells
its parent's what it says; only the newest flows of a workspace are kept. Design 0012 §9.4 (§11 step 11): a session
whose request the gateway holds is asked again each round until it goes on, since no line comes while it is held. A
flow whose server ended is not read (nor tried again) until a server answers on its port again or its session is heard
again, and the log says once that the window closed; a reading that keeps failing is said once.
"""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import anyio.to_thread
import pytest
from fastapi.testclient import TestClient

from clank.client import Client
from clank.components.agents.adapters.opencode import prompt
from clank.components.agents.sessionflow import kept as kept_module
from clank.components.agents.sessionflow.kept import SessionFlows
from clank.components.agents.sessions import ServerGone
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from tests.components.agents.test_monitor_sessions import (  # noqa: F401  (fixtures, found by their names)
    OWNER,
    kernel,
    servers,
    until,
    watched,
)
from tests.fakes.opencode import FakeOpenCode
from tests.support.flowlines import SESSION, history, lines, page, status, step, text, tool, updated, user

WORKSPACE = "paper"


class FakeSessions:
    """The sessions' bridge as the keeper uses it: lines heard, pages of history read (and how often), a server."""

    def __init__(self, pages: dict[str, dict[str, Any]] | None = None) -> None:
        self.pages = pages or {}
        self.heard: list[Callable[[str, dict[str, Any]], None]] = []
        self.read: list[tuple[int, str, str]] = []
        self.failing = 0  # how many pages fail before one is read, as a container gone or a refusal would
        self.failure: Exception = RuntimeError("the bridge refused: the container is not running")  # how they fail
        self.reading: Callable[[str], None] = lambda session: None  # what happens while a page is read
        self.running: int | None = 4096  # the server the watchers saw run every session (None: its server ended)

    def listen(self, heard: Callable[[str, dict[str, Any]], None]) -> None:
        self.heard.append(heard)

    def runs(self, workspace: str, session: str) -> int | None:
        return self.running

    def page(self, workspace: str, port: int, session: str, *, limit: int = 50, before: str = "") -> dict[str, Any]:
        self.read.append((port, session, before))
        self.reading(session)
        if self.failing:
            self.failing -= 1
            raise self.failure
        return self.pages.get(session, {"messages": [], "next": ""})

    def say(self, events: list[dict[str, Any]], port: int = 4096) -> None:
        for line in lines(events, port):
            self.tell(line)

    def tell(self, line: dict[str, Any]) -> None:
        """One line of the watcher's own (`started`, `synced`, `gone`, `server`), as the keeper hears it."""
        for heard in self.heard:
            heard(WORKSPACE, line)


def keeper(sessions: FakeSessions, asked: list[str] | None = None, found: dict[str, Any] | None = None,
           plans: dict[str, str] | None = None) -> SessionFlows:  # fmt: skip
    """A keeper over the fake sessions, with a gateway that answers `found` and a folder that holds `plans`."""

    def ask(session: str) -> dict[str, Any]:
        (asked if asked is not None else []).append(session)
        return found or {"requests": [], "ended": []}

    return SessionFlows(sessions, ask, lambda workspace, named: (plans or {}).get(named))


def ids(flows: SessionFlows, session: str = SESSION, kind: str = "step") -> list[str]:
    found = flows.flow(WORKSPACE, session)
    assert found is not None
    return [node["id"] for node in found["nodes"] if node["kind"] == kind]


def test_a_session_joined_mid_run_marks_its_earlier_steps_before_clank_watched(
    kernel: Kernel,  # noqa: F811
    servers: list[FakeOpenCode],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _ = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{window.port}", monkeypatch)
    flows: SessionFlows = kernel.parts["agents"].flows
    window.feed({"type": "session.status", "properties": {"sessionID": SESSION, "status": {"type": "busy"}}})
    until(lambda: sessions.runs(WORKSPACE, SESSION) == window.port)
    flows.work()  # its round: the history is read through the bridge, as the service's own round would
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:
        client = Client("http://127.0.0.1:7729", "t", name="console", http=http)
        whole = client.get(f"agents/flow/{WORKSPACE}/{SESSION}")
        steps = {node["id"]: node for node in whole["nodes"] if node["kind"] == "step"}
        assert (whole["whole"], list(steps)) == (True, ["msg_02", "msg_03", "msg_05"])
        assert [steps[id]["before"] for id in steps] == [True, True, False], "under way when joined: watched"
        assert whole["head"]["before"] == 2
        assert whole["head"]["status"] == "busy"
        [listed] = [each for each in client.get(f"agents/flow/{WORKSPACE}")["flows"] if each["session"] == SESSION]
        assert (listed["steps"], listed["version"]) == (3, whole["version"])
        said = {"id": "prt_05b", "sessionID": SESSION, "messageID": "msg_05", "type": "text",
                "text": "Skipping the check; the figure is saved as tau-final.png."}  # fmt: skip
        window.feed({"type": "message.part.updated", "properties": {"sessionID": SESSION, "part": said}})
        until(lambda: "tau-final.png" in str(flows.flow(WORKSPACE, SESSION)))
        changed = client.get(f"agents/flow/{WORKSPACE}/{SESSION}", since=whole["version"])
        assert changed["whole"] is False
        assert [node["id"] for node in changed["nodes"]] == ["msg_05"], "only what changed"
        found = http.get(f"/v1/agents/flow/{WORKSPACE}/ses_none", headers={"Authorization": "Bearer t"})
        assert found.status_code == 404
    assert "/session/ses_plan/message" in window.read, "the history was read from the server that runs it"


def test_a_flow_is_read_again_after_its_servers_instance_ended() -> None:
    first = page(history()[:3])
    sessions = FakeSessions({SESSION: first})
    flows = keeper(sessions)
    sessions.say([status("busy")])
    flows.work()
    assert ids(flows) == ["msg_02", "msg_03"]
    assert len(sessions.read) == 1
    flows.work()
    assert len(sessions.read) == 1, "read once, then kept by the lines"
    sessions.pages[SESSION] = page(history())
    sessions.say([{"type": "server.instance.disposed", "properties": {"directory": "/workspace"}}])
    flows.work()
    assert len(sessions.read) == 2
    found = flows.flow(WORKSPACE, SESSION)
    assert found is not None
    steps = {node["id"]: node["before"] for node in found["nodes"] if node["kind"] == "step"}
    assert steps == {"msg_02": True, "msg_03": True, "msg_05": False}, "what the instance missed is not 'before'"
    sessions.tell({"type": "started"})
    flows.work()
    assert len(sessions.read) == 2, "a watcher started again: it reads nothing before it synced"
    sessions.tell({"type": "synced", "ports": [4096]})
    flows.work()
    assert len(sessions.read) == 3, "synced: read again"


def befores(flows: SessionFlows) -> dict[str, bool]:
    found = flows.flow(WORKSPACE, SESSION)
    assert found is not None
    return {node["id"]: node["before"] for node in found["nodes"] if node["kind"] == "step"}


def test_a_flow_whose_reading_failed_is_read_again_later_and_still_marks_its_earlier_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    monkeypatch.setattr(kept_module, "monotonic", lambda: now[0])
    sessions = FakeSessions({SESSION: page(history())})
    sessions.failing = 2
    flows = keeper(sessions)
    sessions.say([status("busy")])
    flows.work()
    assert len(sessions.read) == 1
    sessions.say([status("busy")])  # a line meanwhile: it does not read it at once, nor forget the reading
    flows.work()
    assert len(sessions.read) == 1, "it waits before it tries again"
    now[0] += kept_module.RETRY_SECONDS
    flows.work()
    assert len(sessions.read) == 2, "failed again: it waits twice as long"
    now[0] += kept_module.RETRY_SECONDS
    flows.work()
    assert len(sessions.read) == 2
    now[0] += kept_module.RETRY_SECONDS
    flows.work()
    assert len(sessions.read) == 3
    assert befores(flows) == {"msg_02": True, "msg_03": True, "msg_05": False}, "still its first reading"
    flows.work()
    assert len(sessions.read) == 3, "read: not read again"


def test_a_watcher_started_again_leaves_a_new_flows_first_reading_its_own() -> None:
    sessions = FakeSessions({SESSION: page(history())})
    flows = keeper(sessions)
    sessions.say([status("busy")])
    sessions.tell({"type": "started"})
    sessions.tell({"type": "synced", "ports": [4096]})
    flows.work()
    assert befores(flows) == {"msg_02": True, "msg_03": True, "msg_05": False}


def closed(caplog: pytest.LogCaptureFixture) -> list[str]:
    """What the keeper said of windows that closed."""
    return [record.getMessage() for record in caplog.records if "closed" in record.getMessage()]


def test_a_flow_whose_server_ended_is_read_no_more_until_its_server_is_back_and_that_is_said_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """On the owner's machine, 2026-10-26: the histories of two sessions whose OpenCode had ended were asked for more
    than a thousand times in a day, each refusal logged ("Connection refused")."""
    now = [100.0]
    monkeypatch.setattr(kept_module, "monotonic", lambda: now[0])
    sessions = FakeSessions({SESSION: page(history())})
    sessions.failing = 1  # its server ends as it is first read
    flows = keeper(sessions)
    sessions.say([status("busy")])
    with caplog.at_level(logging.WARNING, logger=kept_module.__name__):
        flows.work()
        assert len(sessions.read) == 1
        sessions.running = None  # the watchers saw its server end
        sessions.tell({"type": "gone", "port": 4096})
        for _ in range(5):
            now[0] += kept_module.RETRY_MOST
            flows.work()
        assert len(sessions.read) == 1, "nothing to read it from: not tried again"
        sessions.tell({"type": "gone", "port": 4096})
        sessions.tell({"type": "started"})
        sessions.tell({"type": "synced", "ports": []})
        flows.work()
    assert len(sessions.read) == 1
    assert closed(caplog) == ["the OpenCode window of paper on port 4096 closed: its sessions are kept as they were"]
    sessions.tell({"type": "server", "port": 4096, "terminal": True})  # a window answers on its port again
    flows.work()
    assert len(sessions.read) == 2, "read once a server answers there again"
    assert befores(flows) == {"msg_02": True, "msg_03": True, "msg_05": False}, "still its first reading"


def test_a_watcher_started_again_reads_its_flows_once_it_synced_and_sets_aside_those_whose_server_ended(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sessions = FakeSessions()
    sessions.running = None  # each flow is read from the server its lines came from
    flows = keeper(sessions)
    sessions.say([status("busy")])
    sessions.say([status("idle", session="ses_other")], port=4097)
    flows.work()
    assert sorted((port, session) for port, session, _ in sessions.read) == [(4096, SESSION), (4097, "ses_other")]
    with caplog.at_level(logging.WARNING, logger=kept_module.__name__):
        sessions.tell({"type": "started"})
        flows.work()
        assert len(sessions.read) == 2, "nothing read before the watcher synced"
        sessions.tell({"type": "synced", "ports": [4096]})
        flows.work()
        flows.work()
    assert sessions.read[2:] == [(4096, SESSION, "")], "the server that still runs: read again; the other: not"
    assert closed(caplog) == ["the OpenCode window of paper on port 4097 closed: its sessions are kept as they were"]
    sessions.say([status("busy", session="ses_other")], port=4098)  # its session goes on in another window
    flows.work()
    assert sessions.read[3:] == [(4098, "ses_other", "")], "heard again: read again, from where it runs now"


def test_a_reading_that_finds_its_server_gone_is_not_tried_again_until_the_server_is_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    now = [100.0]
    monkeypatch.setattr(kept_module, "monotonic", lambda: now[0])
    sessions = FakeSessions({SESSION: page(history())})
    sessions.failing = 1
    sessions.failure = ServerGone("no OpenCode runs on port 4096 any more: it was closed or it ended")
    flows = keeper(sessions)
    sessions.say([status("busy")])
    with caplog.at_level(logging.WARNING, logger=kept_module.__name__):
        flows.work()
        for _ in range(3):
            now[0] += kept_module.RETRY_MOST
            flows.work()
    assert len(sessions.read) == 1, "the bridge said its server is gone: not tried again"
    assert closed(caplog) == ["the OpenCode window of paper on port 4096 closed: its sessions are kept as they were"]
    assert not [record for record in caplog.records if "could not be read" in record.getMessage()]
    sessions.say([status("busy")])  # its server speaks again
    flows.work()
    assert len(sessions.read) == 2
    assert befores(flows) == {"msg_02": True, "msg_03": True, "msg_05": False}


def test_a_reading_that_keeps_failing_is_said_once_until_it_is_read(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    now = [100.0]
    monkeypatch.setattr(kept_module, "monotonic", lambda: now[0])
    sessions = FakeSessions({SESSION: page(history())})
    sessions.failing = 4
    flows = keeper(sessions)
    sessions.say([status("busy")])
    with caplog.at_level(logging.WARNING, logger=kept_module.__name__):
        for _ in range(6):
            flows.work()
            now[0] += kept_module.RETRY_MOST
    assert len(sessions.read) == 5, "tried again after each wait, then read"
    said = [record.getMessage() for record in caplog.records]
    assert said == [
        "the history of ses_plan in paper could not be read: the bridge refused: the container is not running "
        "(tried again, a little later each time)"
    ]


def test_a_round_reads_a_few_flows_and_stops_between_them_when_the_service_stops() -> None:
    sessions = FakeSessions()
    flows = keeper(sessions)
    sessions.say([status("idle", session=f"ses_{n}") for n in range(kept_module.READS + 2)])
    flows.work()
    assert len(sessions.read) == kept_module.READS, "a round reads a few: the others wait for the next"
    flows.work()
    assert len(sessions.read) == kept_module.READS + 2
    sessions.say([{"type": "server.instance.disposed", "properties": {"directory": "/workspace"}}])
    sessions.reading = lambda session: flows.stop()  # the service stops while the first is read
    flows.work()
    assert len(sessions.read) == kept_module.READS + 3, "stopped between two readings"


def test_stopping_the_service_does_not_wait_for_a_reading_under_way() -> None:
    entered, released = threading.Event(), threading.Event()

    def reading(session: str) -> None:  # a `docker exec` that takes its time
        entered.set()
        released.wait(10)

    sessions = FakeSessions()
    sessions.reading = reading
    flows = keeper(sessions)
    sessions.say([status("busy")])

    async def stopped() -> float:
        async with anyio.create_task_group() as group:
            group.start_soon(flows.run)
            await anyio.to_thread.run_sync(entered.wait, 10)
            began = time.monotonic()
            group.cancel_scope.cancel()
        return time.monotonic() - began

    try:
        assert anyio.run(stopped) < 5, "a docker exec under way is left to end by itself"
    finally:
        released.set()


def test_a_sessions_requests_are_asked_of_the_gateway_after_its_steps_change_and_paired() -> None:
    asked: list[str] = []
    begun = "2025-10-19T19:33:20.300000Z"  # 1760902400300 ms: a moment after the step began
    found = {"requests": [], "ended": [{"id": "r-1", "session": SESSION, "time": begun, "calls": ["call_7"],
                                        "seconds": 3.0, "per_second": 52.5, "prompt_tokens": 9000},
                                       {"id": "r-x", "session": "ses_other", "time": begun, "calls": []}]}  # fmt: skip
    sessions = FakeSessions()
    flows = keeper(sessions, asked, found)
    sessions.say(
        [
            *updated(user("msg_01", 1_760_902_399_000, "Plot tau.")),
            status("busy"),
            *updated(step("msg_02", "msg_01", 1_760_902_400_000, [tool("c1", "bash", call="call_7")])),
        ]
    )
    flows.work()
    assert asked == [SESSION], "asked once in a round, however many lines"
    flow = flows.flow(WORKSPACE, SESSION)
    assert flow is not None
    [shown] = [node for node in flow["nodes"] if node["kind"] == "step"]
    assert (shown["request"]["id"], shown["request"]["confirmed"], shown["request"]["per_second"]) == (
        "r-1", True, 52.5
    )  # fmt: skip
    flows.work()
    assert asked == [SESSION], "nothing changed: not asked again"


def test_a_session_whose_request_the_gateway_holds_is_asked_again_each_round_until_it_goes_on() -> None:
    asked: list[str] = []
    begun = "2025-10-19T19:33:20.300000Z"
    hold = {"session": SESSION, "by": "you (console)", "since": begun}
    held: dict[str, Any] = {"id": "r-1", "session": SESSION, "time": begun, "calls": [],
                            "phase": "held: its session is paused", "held": hold}  # fmt: skip
    found: dict[str, Any] = {"requests": [held], "ended": []}
    sessions = FakeSessions()
    flows = keeper(sessions, asked, found)
    sessions.say([*updated(user("msg_01", 1_760_902_399_000, "Plot tau.")), status("busy"),
                  *updated(step("msg_02", "msg_01", 1_760_902_400_000, []))])  # fmt: skip
    flows.work()
    flows.work()
    assert asked == [SESSION, SESSION], "held: no line comes, so it is asked again each round"
    found["requests"] = [{**held, "phase": "answering", "held": {**hold, "until": begun, "how": "resumed"}}]
    flows.work()
    flows.work()
    assert asked == [SESSION, SESSION, SESSION], "gone on: asked no more until its steps change"


def test_a_plans_file_is_read_in_the_workspaces_folder_and_again_when_it_is_edited(
    kernel: Kernel,  # noqa: F811
    tmp_path: Path,
) -> None:
    folder = tmp_path / "paper"
    (folder / "studies").mkdir(parents=True)
    plan = folder / "studies" / "plan.md"
    written = "---\nkind: plan\nstatus: implementing\n---\n\n## Steps\n\n- [{}] Write it\n- [ ] Run it\n"
    plan.write_text(written.format(" "), encoding="utf-8")
    kernel.settings.write("workspace", WORKSPACE, {"path": str(folder)}, base=None, actor=OWNER)
    sessions = FakeSessions()
    flows = SessionFlows(sessions, lambda session: {}, kept_module.plan_reader(kernel))
    sessions.say([*updated(user("msg_01", 1_000, prompt("implement.md").replace("$ARGUMENTS", "studies/plan.md"))),
                  *updated(step("msg_02", "msg_01", 2_000, [text("p1", "Writing it.")]))])  # fmt: skip
    flows.work()
    flows.work()  # what its reading from the history made due
    found = flows.flow(WORKSPACE, SESSION)
    assert found is not None
    assert [(item["title"], item["state"]) for item in found["items"]] == [
        ("Write it", "planned"), ("Run it", "planned")
    ]  # fmt: skip
    plan.write_text(written.format("x"), encoding="utf-8")
    flows.work()
    unread = flows.flow(WORKSPACE, SESSION)
    assert unread is not None
    assert unread["items"][0]["state"] == "planned", "not read again until it is edited"
    sessions.say([{"type": "file.edited", "properties": {"file": "/workspace/studies/plan.md"}}])
    flows.work()
    shown = flows.flow(WORKSPACE, SESSION)
    assert shown is not None
    assert shown["items"][0]["state"] == "done"
    outside = kept_module.plan_reader(kernel)
    assert outside(WORKSPACE, "../elsewhere/plan.md") is None, "never a file outside the folder"
    (tmp_path / "elsewhere.md").write_text(written.format(" "), encoding="utf-8")
    assert outside(WORKSPACE, (tmp_path / "elsewhere.md").as_posix()) is None, "nor on another path or drive"
    (folder / "notes.md").write_text("- [ ] not a plan\n", encoding="utf-8")
    assert outside(WORKSPACE, "notes.md") is None, "a file whose header does not say it is a plan"


def test_a_subagents_flow_tells_its_parents_what_it_says() -> None:
    sessions = FakeSessions({SESSION: page(history()), "ses_child": page(history("ses_child"))})
    flows = keeper(sessions)
    sessions.say([status("busy")])
    child = {"id": "ses_child", "parentID": SESSION, "title": "Find the plotting helpers",
             "time": {"created": 1, "updated": 2}}  # fmt: skip
    sessions.say([{"type": "session.updated", "properties": {"sessionID": "ses_child", "info": child}},
                  status("idle", session="ses_child")])  # fmt: skip
    flows.work()
    flows.work()
    found = flows.flow(WORKSPACE, SESSION)
    assert found is not None
    [branch] = [node for node in found["nodes"] if node["kind"] == "subagent"]
    assert (branch["session"], branch["steps"], branch["calls"], branch["state"]) == ("ses_child", 1, 1, "idle")


def test_only_the_newest_flows_of_a_workspace_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kept_module, "KEPT", 3)
    sessions = FakeSessions()
    flows = keeper(sessions)
    sessions.say([status("busy", session="ses_1")])
    for n in range(2, 6):
        sessions.say([status("idle", session=f"ses_{n}")])
    assert [each["session"] for each in flows.flows(WORKSPACE)] == ["ses_5", "ses_4", "ses_1"], "working is kept"
    sessions.say([status("idle", session="ses_9")])
    assert [each["session"] for each in flows.flows(WORKSPACE)] == ["ses_9", "ses_5", "ses_1"]


def test_a_session_deleted_leaves_the_flows_kept() -> None:
    sessions = FakeSessions()
    flows = keeper(sessions)
    sessions.say([status("idle"), status("idle", session="ses_other")])
    info = {"id": SESSION, "title": "Plot tau against p", "time": {"created": 1, "updated": 2}}
    sessions.say([{"type": "session.deleted", "properties": {"sessionID": SESSION, "info": info}}])
    assert [each["session"] for each in flows.flows(WORKSPACE)] == ["ses_other"]
    assert flows.flow(WORKSPACE, SESSION) is None
