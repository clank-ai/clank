"""Design 0016 §10 (decision 0111): local-only content never reaches the cloud model. Before a request goes to the
cloud, the gateway removes from its tools Clank's Notion tools and each tool of a server marked local (as OpenCode names
them), saying so in its notes; a request whose messages call one is refused (403 `local_only`), and so is every later
request of its session, and of the subagents it starts, even once a compaction folded the call away: the gateway marks a
session the first time any of its requests shows such a call, whatever slot serves it, and keeps the marks in
`state/local-only.json`, so they survive a restart. A local model is given every tool, and a new session goes to the
cloud. Clank's Notion tools are kept from the cloud by the gateway itself, whatever the routes name; and while the
service says the tools kept from the cloud were not given yet, no request goes to the cloud (503, to be retried)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx2

from clank.components.gateway.marks import LocalMarks
from tests.components.gateway.test_cloud_forwarding import (
    ASKS,
    WORKSPACE_KEY,
    cloud_slot,
    forwarding,
    recorded,
)
from tests.components.gateway.test_server import engine, received, table  # noqa: F401  (engine: a fixture)
from tests.fakes.openrouter import FakeOpenRouter

PREFIXES = ["clank_notion_", "lit_"]
TOOLS = [
    {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
    for name in ("bash", "clank_notion_page", "lit_search", "plot_draw")
]
CALLED: list[dict[str, Any]] = [
    {"role": "user", "content": "Read the made-up page."},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "clank_notion_page", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "made-up page text"},
]  # fmt: skip
COMPACTED: list[dict[str, Any]] = [{"role": "user", "content": "A summary of what came before."}]
SESSION, CHILD, OTHER = "ses_made_up_one", "ses_made_up_child", "ses_made_up_other"


def asked(url: str, messages: list[dict[str, Any]], session: str, parent: str = "") -> httpx2.Response:
    headers = {"Authorization": f"Bearer {WORKSPACE_KEY}", "X-Session-Id": session}
    if parent:
        headers["x-parent-session-id"] = parent
    body = {**ASKS, "stream": False, "tools": TOOLS, "messages": messages}
    return httpx2.post(f"{url}/v1/chat/completions", json=body, headers=headers, timeout=30)


def test_local_only_tools_are_removed_from_a_cloud_request_and_kept_for_a_local_one(
    openrouter: FakeOpenRouter,
    tmp_path: Path,
    engine: tuple[int, Path],  # noqa: F811
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, local_only=PREFIXES) as (url, _):
        assert asked(url, COMPACTED, OTHER).status_code == 200
    [sent] = openrouter.chats()
    assert [tool["function"]["name"] for tool in sent.body["tools"]] == ["bash", "plot_draw"]
    [record] = recorded(tmp_path)
    assert "2 local-only tools held back from the cloud model: clank_notion_page, lit_search" in record["notes"]
    local = tmp_path / "local"
    local.mkdir()
    with forwarding(table(engine[0])["slots"]["main"], local, local_only=PREFIXES) as (url, _):
        assert asked(url, [{"role": "user", "content": "Hi"}], OTHER).status_code == 200
    [took] = received(engine[1])
    assert len(took["tools"]) == 4


def test_a_session_that_used_a_local_tool_is_refused_the_cloud_even_after_a_compaction(
    openrouter: FakeOpenRouter,
    tmp_path: Path,
    engine: tuple[int, Path],  # noqa: F811
) -> None:
    marks = tmp_path / "local-only.json"
    local = tmp_path / "local"
    local.mkdir()
    with forwarding(table(engine[0])["slots"]["main"], local, local_only=PREFIXES, marks=LocalMarks(marks)) as (url, _):
        assert asked(url, CALLED, SESSION).status_code == 200, "a local model reads it"
    assert json.loads(marks.read_text(encoding="utf-8"))["sessions"][SESSION]["tool"] == "clank_notion_page"
    with forwarding(cloud_slot(openrouter.url), tmp_path, local_only=PREFIXES, marks=LocalMarks(marks)) as (url, _):
        refused = asked(url, CALLED, SESSION)
        compacted = asked(url, COMPACTED, SESSION)
        child = asked(url, COMPACTED, CHILD, parent=SESSION)
        fresh = asked(url, COMPACTED, OTHER)
    for answer in (refused, compacted, child):
        assert answer.status_code == 403
        error = answer.json()["error"]
        assert error["code"] == "local_only"
        assert error["message"].startswith("this session used Notion, which never goes to the cloud model")
        assert "start a new session to use it, or load a local model" in error["message"]
    assert fresh.status_code == 200
    assert len(openrouter.chats()) == 1, "only the new session's request went"


def test_clanks_notion_tools_are_kept_from_the_cloud_whatever_the_routes_name(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, local_only=[]) as (url, _):
        answer = httpx2.post(f"{url}/v1/chat/completions", json={**ASKS, "tools": TOOLS},
                             headers={"Authorization": f"Bearer {WORKSPACE_KEY}"}, timeout=30)  # fmt: skip
        refused = httpx2.post(f"{url}/v1/chat/completions", json={**ASKS, "messages": CALLED},
                              headers={"Authorization": f"Bearer {WORKSPACE_KEY}"}, timeout=30)  # fmt: skip
    assert answer.status_code == 200, answer.text
    [sent] = openrouter.chats()
    assert "clank_notion_page" not in [tool["function"]["name"] for tool in sent.body["tools"]]
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "local_only")


def test_no_request_goes_to_the_cloud_while_the_tools_kept_from_it_were_not_given(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, local_only=PREFIXES) as (url, routes):
        bound = {"workspace": "cloudy", "models": "cloud", "answered": True, "question": None}
        named = {hashlib.sha256(WORKSPACE_KEY.encode()).hexdigest(): bound}
        routes.update({"slots": {"main": cloud_slot(openrouter.url)}, "roles": {"agent": "main"},
                       "default_slot": "main", "workspaces": named, "local_only": ["clank_notion_"],
                       "local_only_given": False})  # fmt: skip
        answer = httpx2.post(f"{url}/v1/chat/completions", json={**ASKS, "stream": False},
                             headers={"Authorization": f"Bearer {WORKSPACE_KEY}"}, timeout=30)  # fmt: skip
    assert (answer.status_code, answer.json()["error"]["code"]) == (503, "local_only_unknown")
    assert openrouter.chats() == []


def test_a_call_of_a_local_servers_tool_names_the_server(openrouter: FakeOpenRouter, tmp_path: Path) -> None:
    called = [{**CALLED[1], "tool_calls": [{"id": "c2", "type": "function",
                                            "function": {"name": "lit_search", "arguments": "{}"}}]}]  # fmt: skip
    with forwarding(cloud_slot(openrouter.url), tmp_path, local_only=PREFIXES) as (url, _):
        answer = asked(url, [CALLED[0], *called], SESSION)
    assert answer.status_code == 403
    assert answer.json()["error"]["message"].startswith("this session used lit, marked local")


def test_the_marks_survive_a_restart_of_the_gateway(tmp_path: Path) -> None:
    path = tmp_path / "local-only.json"
    first = LocalMarks(path)
    assert first.mark(SESSION, "clank_notion_page") is True
    assert first.mark(SESSION, "clank_notion_page") is False, "marked once"
    again = LocalMarks(path)
    assert again.marked(SESSION) == "clank_notion_page"
    assert again.marked(OTHER) == ""
