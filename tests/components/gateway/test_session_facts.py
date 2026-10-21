"""Design 0012 §3 and §11 step 2: the gateway names each model request's session, and for a subagent's request its
parent, from the headers OpenCode sends with it (`X-Session-Id`, `x-parent-session-id`, read in any case), in its
activity (each request in flight, and the last that ended) and in its records in brief; a request that names no session
works as before and names none. Design 0012 §5.2: the tokens a streamed answer brings are counted by kind, its thinking,
its text and its tool calls. Design 0012 §5.4: a request in flight shows its loop guard's newest share of each part it
reads. Design 0012 §7: the gateway's activity and live view follow the session they are asked for. Design 0012 §4.1
(§11 step 3): a session's request that ended keeps the engine's own usage and timings, so each figure is read where
that engine reports it. Design 0012 §4.2 (§11 step 12): the gateway makes the census of each request from its body and
keeps it with the session's requests that ended, never in its records. The sessions here are synthetic."""

import logging
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest

from clank.components.gateway import server
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import recent
from clank.components.gateway.routing import Routes
from clank.components.gateway.sessions import session_of
from clank.components.runtime.adapters import ENGINES
from tests.components.gateway.test_server import (  # noqa: F401  (fixtures, found by their names)
    ASKED,
    engine,
    gateway,
    recorded,
    routes,
    serving,
    started,
    table,
)
from tests.support.served import free_port

SESSION = "ses_0c2e9ffe1Qk2Lr8xYb3Zd7a1f0"
CHILD = "ses_0d4c3ffe0Hn5Tq1wVc6Ma7a1f1"


def during(url: str, headers: dict[str, str], tokens: int = 40) -> dict[str, Any]:
    """A streamed request with these headers: what the gateway's activity said once its fifth token had come; the
    answer is then read to its end."""
    body = {**ASKED, "max_tokens": tokens, "stream": True}
    with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body, headers=headers, timeout=30) as answer:
        lines = answer.iter_lines()
        while '"w4 "' not in next(lines):
            pass
        now: dict[str, Any] = httpx2.get(f"{url}/activity", timeout=10).json()
        for _ in lines:
            pass
    return now


def settled(url: str) -> dict[str, Any]:
    """The gateway's activity once no request is in flight."""
    deadline = time.monotonic() + 10
    while (done := httpx2.get(f"{url}/activity", timeout=10).json())["requests"]:
        assert time.monotonic() < deadline, "a request stayed in flight after its answer ended"
        time.sleep(0.05)
    found: dict[str, Any] = done
    return found


def test_a_session_and_its_parent_are_read_from_opencodes_headers_in_any_case() -> None:
    assert session_of({"X-Session-Id": f" {CHILD} ", "x-parent-session-id": SESSION}) == (CHILD, SESSION)
    assert session_of({"x-session-id": SESSION, "user-agent": "opencode/1.19.0"}) == (SESSION, "")
    assert session_of({"user-agent": "vscode"}) == ("", "")
    assert session_of(None) == ("", "")


def test_a_request_with_a_session_id_shows_its_session_in_flight_when_it_ended_and_in_its_record(
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    now = during(gateway, {"X-Session-Id": SESSION})
    [flying] = now["requests"]
    assert (flying["session"], flying["parent"]) == (SESSION, "")
    last = settled(gateway)["last"]
    assert (last["session"], last["parent"]) == (SESSION, "")
    [brief] = recent(tmp_path / "traffic", 5)
    assert (brief["session"], brief["parent"]) == (SESSION, "")


def test_a_subagents_request_shows_its_parent(gateway: str, tmp_path: Path) -> None:  # noqa: F811
    headers = {"X-Session-Id": CHILD, "x-parent-session-id": SESSION}
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=ASKED, headers=headers, timeout=30)
    assert answer.status_code == 200, answer.text
    last = settled(gateway)["last"]
    assert (last["session"], last["parent"]) == (CHILD, SESSION)
    [brief] = recent(tmp_path / "traffic", 5)
    assert (brief["session"], brief["parent"]) == (CHILD, SESSION)


def test_a_request_without_the_header_still_works_and_names_no_session(
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=ASKED, timeout=30)
    assert answer.status_code == 200, answer.text
    assert answer.json()["choices"][0]["message"]["content"] == "OK"
    last = settled(gateway)["last"]
    assert (last["session"], last["parent"], last["status"]) == ("", "", 200)
    [brief] = recent(tmp_path / "traffic", 5)
    assert (brief["session"], brief["parent"]) == ("", "")


def test_the_gateway_counts_a_streamed_answers_thinking_and_its_text_apart(
    routes: Routes,  # noqa: F811
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    with started(tmp_path / "a.log", "--fake-loop-after", "5", "--fake-loop-in", "thinking") as port:
        routes.update(table(port))
        body = {**ASKED, "max_tokens": 12, "stream": True}
        with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
            for _ in answer.iter_lines():
                pass
        last = settled(gateway)["last"]
    assert last["counts"] == {"thinking": 7, "answer": 5, "tool": 0}
    assert last["tokens"] == 12


def test_the_gateway_counts_a_streamed_tool_calls_tokens_as_tool_while_it_streams_and_at_its_end(
    routes: Routes,  # noqa: F811
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    fake = ("--fake-loop-after", "5", "--fake-loop-in", "tool", "--fake-token-seconds", "0.05")
    with started(tmp_path / "a.log", *fake) as port:
        routes.update(table(port))
        body = {**ASKED, "max_tokens": 20, "stream": True}
        with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
            lines = answer.iter_lines()
            calls = 0
            while calls < 2:  # the call's first two pieces have come
                calls += '"tool_calls"' in next(lines)
            [flying] = httpx2.get(f"{gateway}/activity", timeout=10).json()["requests"]
            for _ in lines:
                pass
        last = settled(gateway)["last"]
    assert (flying["counts"]["thinking"], flying["counts"]["answer"]) == (0, 5)
    assert flying["counts"]["tool"] >= 2
    assert flying["tokens"] == sum(flying["counts"].values())
    assert last["counts"] == {"thinking": 0, "answer": 5, "tool": 15}


def test_the_gateway_shows_the_loop_guards_newest_share_of_a_streamed_answer(
    routes: Routes,  # noqa: F811
    tmp_path: Path,
) -> None:
    short = GatewaySettings(port=free_port(), hold_seconds=10, loop_windows=[256])
    with started(tmp_path / "a.log", "--fake-token-seconds", "0.01") as port, serving(routes, short, tmp_path) as url:
        routes.update(table(port))
        body = {**ASKED, "max_tokens": 200, "stream": True}
        with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body, timeout=30) as answer:
            lines = answer.iter_lines()
            while '"w90 "' not in next(lines):  # about 330 characters of the answer have come
                pass
            now = httpx2.get(f"{url}/activity", timeout=10).json()
            for _ in lines:
                pass
    shown = now["requests"][0]["loop_guard"]
    assert shown["ratio"] == 0.06
    [part] = shown["parts"]
    assert (part["part"], part["name"], part["stretch"]) == ("answer", "", 256)
    assert 0.06 < part["share"] < 1, "an ordinary answer keeps most of its size"


def test_the_live_view_of_the_gateway_follows_the_session_it_is_asked_for(gateway: str) -> None:  # noqa: F811
    body = {**ASKED, "max_tokens": 40, "stream": True}
    post = f"{gateway}/v1/chat/completions"
    with (
        httpx2.stream("POST", post, json=body, headers={"X-Session-Id": SESSION}, timeout=30) as first,
        httpx2.stream("POST", post, json=body, headers={"X-Session-Id": CHILD}, timeout=30) as second,
    ):
        lines = [first.iter_lines(), second.iter_lines()]
        for each in lines:
            while '"w4 "' not in next(each):
                pass
        mine = httpx2.get(f"{gateway}/activity/live", params={"session": SESSION}, timeout=10).json()
        theirs = httpx2.get(f"{gateway}/activity/live", params={"session": CHILD}, timeout=10).json()
        doing = httpx2.get(f"{gateway}/activity", params={"session": SESSION}, timeout=10).json()
        for each in lines:
            for _ in each:
                pass
    assert (mine["flying"], mine["meta"]["session"], theirs["meta"]["session"]) == (True, SESSION, CHILD)
    assert mine["id"] != theirs["id"]
    assert mine["parts"][0][1].startswith("w0 w1 w2 w3 w4 ")
    assert [request["id"] for request in doing["requests"]] == [mine["id"]]


def test_the_gateway_keeps_the_ids_of_the_calls_an_answer_made(
    routes: Routes,  # noqa: F811
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Design 0012 §6.1 (§11 step 5): an answer's tool-call ids equal OpenCode's call ids, which confirm the pairing of
    a session's requests with its steps."""
    fake = ("--fake-loop-after", "5", "--fake-loop-in", "tool", "--fake-token-seconds", "0.05")
    with started(tmp_path / "a.log", *fake) as port:
        routes.update(table(port))
        body = {**ASKED, "max_tokens": 20, "stream": True}
        headers = {"X-Session-Id": SESSION}
        with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, headers=headers, timeout=30) as answer:
            lines = answer.iter_lines()
            calls = 0
            while calls < 2:
                calls += '"tool_calls"' in next(lines)
            [flying] = httpx2.get(f"{gateway}/activity", timeout=10).json()["requests"]
            for _ in lines:
                pass
        settled(gateway)
        found = httpx2.get(f"{gateway}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()
    assert (flying["calls"], flying["time"] != "") == (["call-1"], True)
    assert found["last"]["calls"] == ["call-1"]
    assert [(each["id"], each["calls"]) for each in found["ended"]] == [(found["last"]["id"], ["call-1"])]


@pytest.mark.parametrize(
    ("style", "adapter", "version"), [("kvmem", "kvmem-llamacpp", "v0.16.0-rc1"), ("llamacpp", "llamacpp", "b11588")]
)
def test_each_fake_engine_style_reports_its_cached_tokens_in_its_own_field_through_the_gateway(
    routes: Routes,  # noqa: F811
    gateway: str,  # noqa: F811
    tmp_path: Path,
    style: str,
    adapter: str,
    version: str,
) -> None:
    """Design 0012 §4.1 (§11 step 3), decision 0067: the gateway keeps each engine's own usage and timings with a
    session's request that ended, so the cache's share is read where that engine's facts say it reports it."""
    fake = ("--fake-prompt-tokens", "40000", "--fake-cached-tokens", "39000")
    with started(tmp_path / f"{style}.log", *fake, style=style) as port:
        routes.update({**table(port), "slots": {"main": {**table(port)["slots"]["main"], "engine": adapter,
                                                         "version": version}}})  # fmt: skip
        body = {**ASKED, "max_tokens": 6, "stream": True, "stream_options": {"include_usage": True}}
        headers = {"X-Session-Id": SESSION}
        with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, headers=headers, timeout=30) as answer:
            for _ in answer.iter_lines():
                pass
        settled(gateway)
        found = httpx2.get(f"{gateway}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()
    [ended] = found["ended"]
    fields = ENGINES.get(adapter)(version).context_facts({}).fields
    assert (reported(ended, fields["prompt"]), reported(ended, fields["output"])) == (40000, 6)
    assert reported(ended, fields["cached"]) == 39000, f"{style}: where {adapter} reports its cache"
    assert (ended["preset"], found["slots"]["main"]["session"]) == ("daily-262k", SESSION)


def reported(ended: dict[str, Any], path: str) -> Any:
    """A figure of a request that ended, at a dotted path (`usage.prompt_tokens`)."""
    found: Any = ended
    for name in path.split("."):
        found = found.get(name) if isinstance(found, dict) else None
    return found


def test_the_gateway_makes_a_census_of_each_request_and_keeps_it_out_of_its_records(
    gateway: str,  # noqa: F811
    tmp_path: Path,
) -> None:
    messages = [
        {"role": "system", "content": "You are a careful agent."},
        {"role": "user", "content": "Read the notes."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_c18", "type": "function",
             "function": {"name": "read", "arguments": '{"filePath": "/workspace/studies/notes.md"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_c18", "content": "n" * 1200},
    ]  # fmt: skip
    body = {"model": "agent", "messages": messages, "max_tokens": 3}
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=body, headers={"X-Session-Id": SESSION}, timeout=30)
    assert answer.status_code == 200
    settled(gateway)
    [ended] = httpx2.get(f"{gateway}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()["ended"]
    census = ended["census"]
    assert (census["chars"]["system"], census["chars"]["yours"], census["chars"]["results"]) == (24, 15, 1200)
    assert next(item for item in census["items"] if item["part"] == "results")["call"] == "call_c18"
    assert all("census" not in record for record in recorded(tmp_path)), "never in the records"


def test_with_records_off_the_census_the_gateway_keeps_carries_no_text_of_the_request(
    routes: Routes,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Design 0012 §4.2: with the records off, nothing of a prompt's text leaves the gateway: its census keeps counts,
    kinds, tool names and sizes only."""
    secret = "Plan the merger quietly"
    messages = [
        {"role": "user", "content": secret},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_c18", "type": "function",
             "function": {"name": "read", "arguments": '{"filePath": "/workspace/merger/terms.md"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_c18", "content": "the terms"},
    ]  # fmt: skip
    with serving(routes, GatewaySettings(port=free_port(), hold_seconds=10, records=False), tmp_path) as url:
        body = {"model": "agent", "messages": messages, "max_tokens": 3}
        answer = httpx2.post(f"{url}/v1/chat/completions", json=body, headers={"X-Session-Id": SESSION}, timeout=30)
        assert answer.status_code == 200
        settled(url)
        found = httpx2.get(f"{url}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()
    said = str(found["ended"][0]["census"])
    assert secret not in said
    assert "merger" not in said
    assert found["ended"][0]["census"]["chars"]["yours"] == len(secret)


def test_a_census_that_fails_never_fails_the_request_and_is_logged_as_a_count_without_its_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Design 0012 §4.2: whatever goes wrong in a census, the request goes on as it was, without one; the log says how
    many failed, never what the request held."""

    def failing(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Plan the merger quietly")

    monkeypatch.setattr(server, "census", failing)
    with caplog.at_level(logging.WARNING):
        assert server.counted({"messages": []}, GatewaySettings()) is None
        assert server.counted({"messages": []}, GatewaySettings()) is None
    said = " ".join(record.getMessage() for record in caplog.records)
    assert "2" in said
    assert "merger" not in said
