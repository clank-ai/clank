"""Design 0023 §3: the conversation stream, `GET /agents/conversation/stream`, over real HTTP. It says it is connected,
then gives a snapshot (the conversation route's answer, with its version), then each change of the mirror as an event
whose id is its version: the status, a message, a part's text as it is written (`delta`), the waits; while the session
works, a `readout` event each second; a change the mirror hears is on the stream within the gather window (design 0023
§6); `after` (or `Last-Event-ID`) resumes from a version, and a client behind what the log keeps gets a snapshot again;
when the folder's newest session changes and none was named, the stream says which and ends, so the client opens the
new one. A folder with no session yet gets a snapshot saying so."""

import statistics
import threading
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.client import ServerEvent
from clank.components.agents import mirror as mirror_module
from clank.components.agents.service import Agents
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.agents.test_conversation import server, session
from tests.fakes.platform import FakePlatform
from tests.support.live import live_service

YOU = Actor(kind="user", via="console")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def ready(kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Agents:
    """Workspace paper on `folder`, one server listing ses_new (busy), a history of one message."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    agents: Agents = kernel.parts["agents"]
    running = [server(4096, session("ses_new", "busy", 20, "the newest"))]
    monkeypatch.setattr(agents.sessions, "servers", lambda workspace: running)
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, id: None)

    def page(
        workspace: str, port: int, id: str, *, limit: int = 50, before: str = "", whole: bool = False
    ) -> dict[str, Any]:
        return {"messages": [{"info": {"id": "msg_1", "role": "user", "created": 100}, "parts": [
            {"id": "prt_1", "message": "msg_1", "type": "text", "text": "Plot it.", "length": 8, "whole": True}]}],
            "next": ""}  # fmt: skip

    monkeypatch.setattr(agents.sessions, "page", page)
    return agents


def line(kind: str, **more: Any) -> dict[str, Any]:
    return {"type": kind, "port": 4096, "session": "ses_new", **more}


def until(events: Generator[ServerEvent, None, None], name: str, seconds: float = 10) -> list[ServerEvent]:
    """The events up to the next of this name, that one included."""
    found: list[ServerEvent] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        event = next(events)
        found.append(event)
        if event.name == name:
            return found
    raise AssertionError(f"no {name} event; got {[e.name for e in found]}")


def test_the_stream_gives_a_snapshot_then_each_change_with_its_version_and_the_readout_while_busy(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    with live_service(kernel) as client:
        events = client.stream("agents/conversation/stream", folder=str(tmp_path / "paper"), quiet=15)
        try:
            [connected, snapshot] = until(events, "snapshot")
            assert connected.name == "connected"
            assert snapshot.data["session"]["id"] == "ses_new"
            assert snapshot.data["session"]["busy"] is True, "learned from the servers listed"
            assert [m["info"]["id"] for m in snapshot.data["messages"]] == ["msg_1"]
            version = snapshot.data["version"]
            assert snapshot.id == version

            def feed() -> None:
                time.sleep(0.2)
                agents.sessions.heard(
                    "paper",
                    line("message", message={"id": "msg_2", "session": "ses_new", "role": "assistant", "created": 200}),
                )
                agents.sessions.heard("paper", line("delta", message="msg_2", part="prt_2", field="text", text="The "))
                agents.sessions.heard("paper", line("delta", message="msg_2", part="prt_2", field="text", text="fit"))

            threading.Thread(target=feed, daemon=True).start()
            heard = until(events, "delta")
            kinds = [e.name for e in heard]
            assert kinds[: kinds.index("delta")] == ["message"] or "readout" in kinds, kinds
            message = next(e for e in heard if e.name == "message")
            assert message.data["message"]["id"] == "msg_2"
            assert message.id == version + 1, "each change's id is its version"
            delta = heard[-1]
            assert delta.data == {"type": "delta", "message": "msg_2", "part": "prt_2", "text": "The "}
            assert delta.id == version + 2
            second = until(events, "delta")[-1]
            assert second.data["text"] == "fit"
            readout = until(events, "readout", seconds=5)[-1]
            assert "slot" in readout.data["readout"], "the model's readout, each second while the session works"
            agents.sessions.heard("paper", line("status", status="idle"))
            status = until(events, "status")[-1]
            assert status.data == {"type": "status", "busy": False, "status": "idle"}
            assert status.id == version + 4
        finally:
            events.close()


def test_a_change_the_mirror_hears_is_on_the_stream_within_the_gather_window(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    with live_service(kernel) as client:
        events = client.stream("agents/conversation/stream", folder=str(tmp_path / "paper"), quiet=15)
        try:
            until(events, "snapshot")
            took: list[float] = []
            for n in range(20):
                heard = time.perf_counter()
                agents.sessions.heard("paper", line("delta", message="msg_1", part="prt_1", field="text", text=str(n)))
                while until(events, "delta")[-1].data["text"] != str(n):
                    pass
                took.append(time.perf_counter() - heard)
                time.sleep(0.05)
            # The gather window is 0.1 s (design 0023 §3: a burst comes as one flush); the bound leaves room for a
            # busy machine, the number itself is kept in design 0023 §6.
            assert statistics.median(took) < 0.5, f"median {statistics.median(took):.3f} s"
            assert max(took) < 2.0, f"max {max(took):.3f} s"
        finally:
            events.close()


def test_a_client_resumes_from_its_version_or_gets_a_snapshot_when_behind_and_follows_a_new_session(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mirror_module, "CHANGES", 4)
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    folder = str(tmp_path / "paper")
    with live_service(kernel) as client:
        first = until(client.stream("agents/conversation/stream", folder=folder, quiet=15), "snapshot")[-1]
        version = first.data["version"]
        for n in range(3):
            agents.sessions.heard("paper", line("delta", message="msg_1", part="prt_1", field="text", text=str(n)))
        resumed = client.stream("agents/conversation/stream", folder=folder, after=version, after_session="ses_new",
                                quiet=15)  # fmt: skip
        try:
            events = until(resumed, "delta")
            assert [e.name for e in events] == ["connected", "delta"], "no snapshot: the changes since, from the log"
            assert events[-1].id == version + 1
            assert until(resumed, "delta")[-1].data["text"] == "1"
        finally:
            resumed.close()
        other = client.stream("agents/conversation/stream", folder=folder, after=version, after_session="ses_old",
                              quiet=15)  # fmt: skip
        try:
            assert [e.name for e in until(other, "snapshot")] == ["connected", "snapshot"], (
                "a version of another session means nothing here: a snapshot"
            )
        finally:
            other.close()
        for n in range(3, 8):
            agents.sessions.heard("paper", line("delta", message="msg_1", part="prt_1", field="text", text=str(n)))
        behind = client.stream("agents/conversation/stream", folder=folder, after=version, quiet=15)
        try:
            events = until(behind, "snapshot")
            assert [e.name for e in events] == ["connected", "snapshot"], "behind the four changes kept: a snapshot"
            assert events[-1].data["messages"][0]["parts"][0]["text"] == "Plot it.01234567"
        finally:
            behind.close()
        kept: list[dict[str, Any]] = []
        monkeypatch.setattr(agents.flows, "flows", lambda workspace: kept)
        moved = client.stream("agents/conversation/stream", folder=folder, session="ses_new", quiet=15)
        following = client.stream("agents/conversation/stream", folder=folder, quiet=15)
        try:
            assert until(moved, "snapshot")[-1].data["session"]["id"] == "ses_new"
            assert until(following, "snapshot")[-1].data["session"]["id"] == "ses_new"
            kept.append({"session": "ses_later", "title": "a later one"})  # the owner started another session
            agents.sessions.heard("paper", {"type": "session", "port": 4096, "deleted": False, "session": {
                "id": "ses_later", "parent": None, "title": "a later one", "created": 300, "updated": 300,
                "revert": {}, "compacting": False}})  # fmt: skip
            agents.sessions.heard("paper", line("status", status="busy"))
            assert until(moved, "status")[-1].data["busy"] is True, "the one named stays"
            events = until(following, "session", seconds=5)
            assert events[-1].data == {"id": "ses_later"}, "none named: the newest session changed, the client reopens"
        finally:
            moved.close()
            following.close()


def test_a_folder_with_no_session_yet_gets_a_snapshot_saying_so(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    monkeypatch.setattr(agents.sessions, "servers", lambda workspace: [])
    with live_service(kernel) as client:
        events = client.stream("agents/conversation/stream", folder=str(tmp_path / "paper"), quiet=15)
        try:
            snapshot = until(events, "snapshot")[-1]
            assert snapshot.data["session"] is None
            assert snapshot.data["workspace"] == "paper"
        finally:
            events.close()
        nowhere = client.stream("agents/conversation/stream", folder=str(tmp_path / "elsewhere"), quiet=15)
        try:
            assert until(nowhere, "snapshot")[-1].data["workspace"] is None
        finally:
            nowhere.close()
