"""Design 0016 §9, §10 and §11 (decisions 0103, 0111 and 0112): every path to the provider passes one gate, right
before the request is sent, whatever held it first. A paused session's request, resumed while a cloud model serves, is
refused for a workspace kept on this machine, kept from the cloud when its session used Notion, and sent without
Clank's Notion tools when it may go; a request held at a spending limit is looked at again once the limit is raised, so
a workspace kept on this machine meanwhile, or a session marked local only meanwhile, never reaches the provider. A
refusal told inside a held stream says what held it (a pause, the limit, the workspace's question), and is worded to be
retried when nothing was sent (the provider unreachable). The sessions, pages and words here are made up."""

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx2

from clank.components.gateway.holds import Holds
from clank.components.gateway.marks import LocalMarks
from tests.components.gateway.test_cloud_forwarding import ASKS, SESSION, WORKSPACE_KEY, cloud_slot, forwarding
from tests.fakes.openrouter import FakeOpenRouter

TOKEN = "made-up-service-token"
OWNER = {"Authorization": f"Bearer {TOKEN}"}
NOTION = "clank_notion_"
READ_NOTION: list[dict[str, Any]] = [
    {"role": "user", "content": "Find my made-up note."},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c-1", "type": "function", "function": {"name": "clank_notion_search", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "c-1", "content": "A made-up page of research."},
]  # fmt: skip
NOTION_TOOL = {"type": "function", "function": {"name": "clank_notion_page", "parameters": {"type": "object"}}}


def table(url: str, models: str, limit: float | None = None) -> dict[str, Any]:
    """The routes: the cloud slot, the workspace `cloudy` with its bound, and today's spending against a limit."""
    bound = {"workspace": "cloudy", "models": models, "answered": True, "question": None}
    return {"slots": {"main": cloud_slot(url)}, "roles": {"agent": "main"}, "default_slot": "main",
            "workspaces": {hashlib.sha256(WORKSPACE_KEY.encode()).hexdigest(): bound}, "local_only": [NOTION],
            "cost": {"day_usd": 5.0, "month_usd": 5.0, "limit_day_usd": limit, "limit_month_usd": None, "taken": 0,
                     "run": ""}}  # fmt: skip


def resumed(url: str, body: dict[str, Any]) -> list[str]:
    """A request of a paused session, resumed once its first comment line came: every line of its stream."""
    assert httpx2.put(f"{url}/holds/{SESSION}", json={"by": "you"}, headers=OWNER, timeout=10).status_code == 200
    got: list[str] = []
    sent = {"Authorization": f"Bearer {WORKSPACE_KEY}", "X-Session-Id": SESSION}
    with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body, headers=sent, timeout=30) as answer:
        for line in answer.iter_lines():
            if not line:
                continue
            got.append(line)
            if len(got) == 1:
                assert httpx2.delete(f"{url}/holds/{SESSION}", headers=OWNER, timeout=10).status_code == 200
    return got


def held_then(url: str, then: Any) -> list[str]:
    """A request held at the spending limit: `then` is done once its first comment line came."""
    got: list[str] = []
    sent = {"Authorization": f"Bearer {WORKSPACE_KEY}", "X-Session-Id": SESSION}
    with httpx2.stream("POST", f"{url}/v1/chat/completions", json=ASKS, headers=sent, timeout=30) as answer:
        for line in answer.iter_lines():
            if not line:
                continue
            got.append(line)
            if len(got) == 1:
                then()
    return got


def test_a_paused_request_resumed_for_a_workspace_kept_on_this_machine_never_reaches_the_provider(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    holds = Holds(keep_seconds=0.2)
    with forwarding(cloud_slot(openrouter.url), tmp_path, token=TOKEN, holds=holds) as (url, routes):
        routes.update(table(openrouter.url, "this-machine"))
        got = resumed(url, ASKS)
    assert openrouter.chats() == [], "a workspace kept on this machine reached the provider"
    assert "cloudy is kept on this machine" in got[-1]


def test_a_paused_request_resumed_whose_session_read_notion_is_kept_from_the_cloud(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    holds = Holds(keep_seconds=0.2)
    with forwarding(cloud_slot(openrouter.url), tmp_path, token=TOKEN, holds=holds) as (url, routes):
        routes.update(table(openrouter.url, "cloud"))
        got = resumed(url, {**ASKS, "messages": READ_NOTION})
    assert openrouter.chats() == [], "a page read from Notion reached the provider"
    assert "never goes to the cloud model" in got[-1]


def test_a_paused_request_resumed_that_may_go_is_sent_without_clanks_notion_tools(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    holds = Holds(keep_seconds=0.2)
    with forwarding(cloud_slot(openrouter.url), tmp_path, token=TOKEN, holds=holds) as (url, routes):
        routes.update(table(openrouter.url, "cloud"))
        resumed(url, {**ASKS, "tools": [*ASKS["tools"], NOTION_TOOL]})
    [sent] = openrouter.chats()
    assert [tool["function"]["name"] for tool in sent.body["tools"]] == ["bash"]


def test_a_request_held_at_the_limit_for_a_workspace_kept_local_meanwhile_never_reaches_the_provider(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, routes):
        routes.update(table(openrouter.url, "cloud", limit=5.0))

        def narrowed_then_raised() -> None:
            routes.update(table(openrouter.url, "this-machine", limit=5.0))  # the owner keeps it on this machine
            routes.update(table(openrouter.url, "this-machine", limit=10.0))  # then raises the limit

        got = held_then(url, narrowed_then_raised)
    assert openrouter.chats() == [], "a workspace kept on this machine while held reached the provider"
    assert "cloudy is kept on this machine" in got[-1]


def test_a_request_held_at_the_limit_whose_session_was_marked_local_meanwhile_never_reaches_the_provider(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    marks = LocalMarks(tmp_path / "local-only.json")
    with forwarding(cloud_slot(openrouter.url), tmp_path, marks=marks) as (url, routes):
        routes.update(table(openrouter.url, "cloud", limit=5.0))

        def marked_then_raised() -> None:
            marks.mark(SESSION, "clank_notion_search")  # another request of the session read Notion meanwhile
            routes.update(table(openrouter.url, "cloud", limit=10.0))

        got = held_then(url, marked_then_raised)
    assert openrouter.chats() == [], "a session marked local only while held reached the provider"
    assert "never goes to the cloud model" in got[-1]


def test_a_refusal_inside_a_stream_held_at_the_limit_says_so_and_unreachable_is_to_be_retried(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot("http://127.0.0.1:9"), tmp_path) as (url, routes):
        routes.update(
            {**table(openrouter.url, "cloud", limit=5.0), "slots": {"main": cloud_slot("http://127.0.0.1:9")}}
        )
        got = held_then(url, lambda: routes.update({**table(openrouter.url, "cloud", limit=10.0),
                                                    "slots": {"main": cloud_slot("http://127.0.0.1:9")}}))  # fmt: skip
    error = json.loads(got[-1][len("data: ") :])["error"]
    assert error["code"] == "unavailable", "never sent: OpenCode may send it again"
    assert "held at the cloud spending limit" in error["message"]
    assert "paused" not in error["message"]


def test_a_refusal_inside_a_stream_held_for_a_pause_says_its_session_was_paused(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    holds = Holds(keep_seconds=0.2)
    with forwarding(cloud_slot(openrouter.url), tmp_path, token=TOKEN, holds=holds) as (url, routes):
        routes.update(table(openrouter.url, "this-machine"))
        got = resumed(url, ASKS)
    error = json.loads(got[-1][len("data: ") :])["error"]
    assert error["code"] == "engine_refused"
    assert "held while its session was paused" in error["message"]
