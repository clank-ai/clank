"""Design 0021 §4: the agent panel's conversation. `Sessions.reach` finds the server that reaches a session: the one the
service heard it on, else one of the workspace's servers that lists it, else the first that runs (every OpenCode server
of a folder reads the sessions it keeps on disk), else none. `GET /agents/conversation?folder=` composes, for the
folder's workspace, its session (the one named, else the newest the service keeps a flow of, else the newest root
session a server lists, so a panel opened after the service restarted still has one), the server that reaches it, a
page of its messages as the bridge reads them (the newest, or those before a cursor) with the cursor of the page before,
whether it is busy, and the permissions and questions waiting in it; a folder with no workspace, or a workspace with no
session, answers what there is."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.service import Agents
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
HEADERS = {"Authorization": "Bearer t"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def server(port: int, *sessions: dict[str, Any], **waiting: list[dict[str, Any]]) -> dict[str, Any]:
    """A server of the workspace as the bridge lists it."""
    return {"port": port, "terminal": port == 4096, "sessions": list(sessions), "children": [],
            "permissions": waiting.get("permissions", []), "questions": waiting.get("questions", [])}  # fmt: skip


def session(id: str, status: str = "idle", updated: int = 0, title: str = "") -> dict[str, Any]:
    return {"id": id, "title": title or id, "parent": None, "created": updated, "updated": updated, "status": status}


def test_the_server_that_reaches_a_session_is_the_one_heard_else_one_that_lists_it_else_the_first_that_runs(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = kernel.parts["agents"].sessions
    running = [server(4096, session("ses_a")), server(4100, session("ses_b"))]
    heard: dict[str, int] = {}
    monkeypatch.setattr(sessions, "runs", lambda workspace, id: heard.get(id))
    monkeypatch.setattr(sessions, "servers", lambda workspace: running)
    assert sessions.reach("paper", "ses_b") == 4100, "a server that lists it"
    assert sessions.reach("paper", "ses_gone") == 4096, "else the first that runs"
    heard["ses_b"] = 4200
    assert sessions.reach("paper", "ses_b") == 4200, "the one the service heard it on first"
    running.clear()
    assert sessions.reach("paper", "ses_gone") is None

    def broken(workspace: str) -> list[dict[str, Any]]:
        raise RuntimeError("the container does not answer")

    monkeypatch.setattr(sessions, "servers", broken)
    assert sessions.reach("paper", "ses_gone") is None, "a container that does not answer reaches nothing"


def test_the_conversation_is_the_folders_session_its_page_of_messages_whether_it_is_busy_and_what_waits_in_it(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    agents: Agents = kernel.parts["agents"]
    kept: list[dict[str, Any]] = [{"session": "ses_new", "title": "the newest"}]
    monkeypatch.setattr(agents.flows, "flows", lambda workspace: kept if workspace == "paper" else [])
    permission = {"id": "per_1", "session": "ses_new", "permission": "bash", "patterns": ["rm -r out"], "metadata": {}}
    question = {"id": "que_1", "session": "ses_other", "questions": []}
    running = [server(4096, session("ses_new", "busy", 20, "the newest"), session("ses_old", "idle", 10, "older"),
                      permissions=[permission], questions=[question])]  # fmt: skip
    monkeypatch.setattr(agents.sessions, "servers", lambda workspace: running)
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, id: None)
    pages: list[tuple[int, str, int, str]] = []

    def page(workspace: str, port: int, id: str, *, limit: int = 50, before: str = "") -> dict[str, Any]:
        pages.append((port, id, limit, before))
        return {"messages": [{"info": {"id": "msg_1", "role": "user"}, "parts": []}], "next": "cursor_1"}

    monkeypatch.setattr(agents.sessions, "page", page)
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:

        def asked(**params: Any) -> dict[str, Any]:
            found: dict[str, Any] = client.get("/api/v1/agents/conversation", params=params, headers=HEADERS).json()
            return found

        found = asked(folder=str(folder))
        older = asked(folder=str(folder), session="ses_old", limit=10, before="cursor_1")
        kept.clear()  # the service restarted: it keeps no flow yet
        listed = asked(folder=str(folder))
        nowhere = asked(folder=str(tmp_path / "elsewhere"))
        running.clear()
        empty = asked(folder=str(folder))
    assert found["workspace"] == "paper"
    assert found["session"] == {"id": "ses_new", "title": "the newest", "port": 4096, "busy": True}
    assert found["messages"] == [{"info": {"id": "msg_1", "role": "user"}, "parts": []}]
    assert found["next"] == "cursor_1"
    assert found["waiting"] == {"permissions": [permission], "questions": []}, "only what waits in this session"
    assert pages[0] == (4096, "ses_new", 30, ""), "the newest page by default"
    assert older["session"]["id"] == "ses_old"
    assert older["session"]["busy"] is False
    assert pages[1] == (4096, "ses_old", 10, "cursor_1")
    assert listed["session"]["id"] == "ses_new", "the newest root session a server lists"
    assert nowhere["workspace"] is None
    assert (nowhere["session"], nowhere["messages"], nowhere["next"]) == (None, [], "")
    assert empty["workspace"] == "paper"
    assert empty["session"] is None, "no server runs, no session kept"
