"""Design 0012 §9.4 and §11 step 11 (decision 0055), through a gateway served in the test and the fake engine: a paused
session's request gets its headers at once and comment lines while it is held, and reaches no engine; resumed, it goes
to the engine on the same stream; the activity shows it held and its record keeps the hold; a note's release closes only
the requests held before the note was sent, and one it closed stays among its session's ended requests for its step's
flow; a session not paused is not held; and the routes that pause and resume take only the service's local token
(decision 0084), so the agent, which reaches the gateway through the edge, never can. The keep-alive is short here (50
ms) so a test sees several; the sessions are synthetic."""

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import uvicorn

from clank.components.gateway.holds import Holds
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog, recent
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import RETRIED_STATUSES, create_gateway, worded
from clank.kernel.service import server_config
from tests.components.gateway.test_server import (  # noqa: F401  (fixtures, found by their names)
    ASKED,
    engine,
    received,
    recorded,
    routes,
    started,
    table,
)
from tests.fakes.engine import REFUSAL
from tests.support.served import free_port

SESSION = "ses_0c2e9ffe1Qk2Lr8xYb3Zd7a1f0"
CHILD = "ses_0d4c3ffe0Hn5Tq1wVc6Ma7a1f1"
OTHER = "ses_0e7b2ffe3Ab4Cd5eFg6Hi7Jk8L9"
TOKEN = "local-token-of-the-test"
OWNER = {"Authorization": f"Bearer {TOKEN}"}  # the activity routes are the service's (design 0015 §10)
KEEP = 0.05
STREAMED = {**ASKED, "max_tokens": 4, "stream": True}
HELD = "held: its session is paused"


@contextlib.contextmanager
def holding(table: Routes, tmp_path: Path, token: str | None = TOKEN, hold_seconds: int = 10) -> Iterator[str]:
    """The gateway with holds (a keep-alive of `KEEP`) and the service's token, served for real; its base URL."""
    settings = GatewaySettings(port=free_port(), hold_seconds=hold_seconds)
    app = create_gateway(table, settings, TrafficLog(tmp_path / "traffic", 256, 14), holds=Holds(KEEP), token=token)
    server = uvicorn.Server(server_config(app, "127.0.0.1", settings.port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{settings.port}"
    finally:
        server.should_exit = True
        thread.join(15)


def owner(url: str, method: str, path: str, body: dict[str, Any] | None = None) -> httpx2.Response:
    """The service asking the gateway, with its token."""
    return httpx2.request(method, f"{url}/{path}", json=body, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)


def pause(url: str, session: str = SESSION) -> None:
    answer = owner(url, "PUT", f"holds/{session}", {"by": "you (console)"})
    assert answer.status_code == 200, answer.text


def resume(url: str, session: str = SESSION) -> dict[str, Any]:
    answer = owner(url, "DELETE", f"holds/{session}")
    assert answer.status_code == 200, answer.text
    found: dict[str, Any] = answer.json()
    return found


@contextlib.contextmanager
def asking(url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> Iterator[httpx2.Response]:
    """A streamed request with these headers, open."""
    with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body or STREAMED, headers=headers,
                       timeout=30) as answer:  # fmt: skip
        yield answer


def comments(lines: Iterator[str], count: int) -> list[str]:
    """The next `count` comment lines of a stream (blank lines passed over)."""
    found: list[str] = []
    while len(found) < count:
        line = next(lines)
        if line:
            found.append(line)
    return found


def flying(url: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = httpx2.get(f"{url}/activity", headers=OWNER, timeout=10).json()["requests"]
    return found


def test_a_held_request_gets_its_headers_at_once_and_comment_lines_while_held_and_reaches_no_engine(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            assert answer.status_code == 200
            assert answer.headers["content-type"].startswith("text/event-stream")
            lines = answer.iter_lines()
            said = comments(lines, 4)
            assert said[0].startswith(f": held by Clank: session {SESSION} is paused by you (console) since ")
            assert said[1:] == [": held"] * 3, "a comment line each keep-alive, nothing else"
            assert received(engine[1]) == [], "nothing reached the engine while held"
            resume(url)
            rest = [line for line in lines if line]
        assert rest[-1] == "data: [DONE]"


def test_resuming_forwards_the_held_request_on_the_same_stream(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 2)
            ended = resume(url)
            text = "".join(json.loads(line[5:])["choices"][0]["delta"].get("content") or ""
                           for line in lines if line.startswith("data: {"))  # fmt: skip
        assert (ended["session"], ended["held"]) == (SESSION, 1)
        assert text == "w0 w1 w2 w3 "
        [took] = received(engine[1])
        assert took["model"] == "qwen3.8-27b"
        assert owner(url, "GET", "holds").json() == {"pauses": []}


def test_a_held_request_shows_as_held_in_the_activity_and_its_record_keeps_the_hold(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 6)
            [request] = flying(url)
            assert request["phase"] == HELD
            assert {key: request["held"][key] for key in ("session", "by")} == {"session": SESSION,
                                                                                 "by": "you (console)"}  # fmt: skip
            [shown] = owner(url, "GET", "holds").json()["pauses"]
            assert shown["session"] == SESSION
            assert [(each["id"], each["session"]) for each in shown["held"]] == [(request["id"], SESSION)]
            resume(url)
            for _ in lines:
                pass
        [record] = recorded(tmp_path)
        assert {key: record["held"][key] for key in ("session", "by", "how")} == {
            "session": SESSION, "by": "you (console)", "how": "resumed"}  # fmt: skip
        assert record["held"]["seconds"] >= 5 * KEEP
        assert record["wait_ms"] < record["held"]["seconds"] * 1000, "timed from the resume, the hold apart"
        [brief] = recent(tmp_path / "traffic", 5)
        assert brief["held_seconds"] == record["held"]["seconds"]
        last = httpx2.get(f"{url}/activity", headers=OWNER, timeout=10).json()["last"]
        assert last["held"]["how"] == "resumed"


def test_a_request_of_a_session_not_paused_is_not_held(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url, OTHER)
        for headers in ({"X-Session-Id": SESSION}, {}):
            with asking(url, headers) as answer:
                lines = [line for line in answer.iter_lines() if line]
            assert not any(line.startswith(":") for line in lines)
            assert lines[-1] == "data: [DONE]"
        assert len(received(engine[1])) == 2
        assert "held" not in recorded(tmp_path)[0]


def test_the_holds_routes_refuse_a_caller_without_the_services_token(
    routes: Routes,  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        for headers in ({}, {"Authorization": "Bearer not-the-token"}, {"Authorization": TOKEN}):
            for method, path in (("PUT", f"holds/{SESSION}"), ("DELETE", f"holds/{SESSION}"), ("GET", "holds"),
                                 ("POST", f"holds/{SESSION}/release")):  # fmt: skip
                answer = httpx2.request(method, f"{url}/{path}", json={"by": "the agent"}, headers=headers, timeout=10)
                assert answer.status_code == 401, (method, path, headers)
                assert "owner's" in answer.json()["error"]["message"]
        assert owner(url, "GET", "holds").json() == {"pauses": []}, "nothing was paused"
    with holding(routes, tmp_path, token=None) as url:
        answer = owner(url, "PUT", f"holds/{SESSION}", {"by": "you"})
        assert answer.status_code == 503
        assert "token" in answer.json()["error"]["message"]


def test_a_subagent_is_held_with_its_parent(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": CHILD, "x-parent-session-id": SESSION}) as answer:
            lines = answer.iter_lines()
            [said] = comments(lines, 1)
            assert said.startswith(f": held by Clank: session {SESSION} is paused")
            [request] = flying(url)
            assert (request["phase"], request["session"], request["held"]["session"]) == (HELD, CHILD, SESSION)
            assert received(engine[1]) == []
            resume(url)
            assert [line for line in lines if line][-1] == "data: [DONE]"
        assert len(received(engine[1])) == 1


def test_a_note_closes_the_hold_with_an_empty_step_and_the_next_request_is_held_again(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 2)
            released = owner(url, "POST", f"holds/{SESSION}/release")
            rest = [line for line in lines if line and not line.startswith(":")]
        assert released.json() == {"session": SESSION, "released": 1}
        [step, done] = rest
        [choice] = json.loads(step.removeprefix("data: "))["choices"]
        assert (choice["delta"].get("content"), choice["finish_reason"]) == ("", "stop"), "an empty step that ended"
        assert done == "data: [DONE]"
        assert received(engine[1]) == [], "the empty step is the gateway's own"
        [record] = recorded(tmp_path)
        assert (record["local"], record["held"]["how"]) == ("released", "released")
        assert httpx2.get(f"{url}/activity", headers=OWNER, timeout=10).json()["served"] == 0, (
            "never counted, as a title"
        )
        doing = httpx2.get(
            f"{url}/activity", params={"session": SESSION, "ended": "true"}, headers=OWNER, timeout=10
        ).json()
        [ended] = doing["ended"]
        assert (ended["id"], ended["held"]["how"]) == (record["id"], "released"), "its step's flow keeps the hold"
        assert doing["last"] is None, "never the session's last request"
        [pause_] = owner(url, "GET", "holds").json()["pauses"]
        assert pause_["session"] == SESSION, "the pause stays"
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            [said] = comments(lines, 1)
            assert said.startswith(": held by Clank"), "the request that carries the note is held again"
            resume(url)
            assert [line for line in lines if line][-1] == "data: [DONE]"


def test_a_release_leaves_held_a_request_that_came_after_the_time_it_names(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 1)
            before = {"before": "2026-01-01T00:00:00.000Z"}  # the message was sent before this request was held
            released = owner(url, "POST", f"holds/{SESSION}/release", before)
            assert released.json() == {"session": SESSION, "released": 0}, "it may carry the message: it stays held"
            assert [request["phase"] for request in flying(url)] == [HELD]
            unread = owner(url, "POST", f"holds/{SESSION}/release", {"before": "not a time"})
            assert unread.status_code == 400
            assert "before" in unread.json()["error"]["message"]
            resume(url)
            assert [line for line in lines if line][-1] == "data: [DONE]"
        assert len(received(engine[1])) == 1, "resumed, it reached the engine"


def test_a_request_not_streamed_is_held_without_headers_until_resumed(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        found: dict[str, Any] = {}

        def ask() -> None:
            answer = httpx2.post(f"{url}/v1/chat/completions", json=ASKED, headers={"X-Session-Id": SESSION},
                                 timeout=30)  # fmt: skip
            found.update(status=answer.status_code, body=answer.json(), at=time.monotonic())

        thread = threading.Thread(target=ask)
        thread.start()
        deadline = time.monotonic() + 10
        while not flying(url):
            assert time.monotonic() < deadline, "the request never came"
            time.sleep(0.02)
        time.sleep(5 * KEEP)
        assert found == {}, "no headers while held"
        assert flying(url)[0]["phase"] == HELD
        resumed_at = time.monotonic()
        resume(url)
        thread.join(15)
        assert found["status"] == 200
        assert found["body"]["choices"][0]["message"]["content"] == "OK"
        assert found["at"] >= resumed_at
        assert recorded(tmp_path)[0]["held"]["how"] == "resumed"


def test_a_held_request_whose_client_left_is_forgotten_and_reaches_no_engine(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            comments(answer.iter_lines(), 2)
        deadline = time.monotonic() + 10
        while flying(url) or owner(url, "GET", "holds").json()["pauses"][0]["held"]:
            assert time.monotonic() < deadline, "a request whose client left stayed held"
            time.sleep(0.02)
        assert resume(url)["held"] == 0
        assert received(engine[1]) == []
        assert not (tmp_path / "traffic").exists() or recorded(tmp_path) == [], "not recorded, as one never begun"


def error_of(lines: list[str]) -> dict[str, Any]:
    """The error event a stream ended with."""
    [event] = [json.loads(line[5:]) for line in lines if line.startswith("data: {") and '"error"' in line]
    found: dict[str, Any] = event["error"]
    return found


def test_words_not_to_be_retried_hold_none_of_opencodes_retry_words() -> None:
    said = ("upstream unavailable: Service Unavailable (503), rate_limit hit, Rate limited after 15000 tokens; "
            "Overloaded; quota exhausted; Too Many Requests")  # fmt: skip
    error = json.loads(worded(said, retried=False)[len(b"data: ") :])["error"]
    whole = json.dumps(error).lower()
    for word in ("unavailable", "rate_limit", "rate limit", "overloaded", "exhausted", "too many requests"):
        assert word not in whole, word
    for status in RETRIED_STATUSES:
        assert status not in whole, status
    assert "1 5 0 0 0 tokens" in error["message"], "a number that holds a retried status, spaced out"
    assert error["code"] == "engine_refused"
    retried = json.loads(worded("no model runs in the main slot", retried=True)[len(b"data: ") :])["error"]
    assert "unavailable" in retried["message"]
    assert retried["code"] == "unavailable"


def test_a_slot_that_is_not_served_after_resuming_is_an_error_event_worded_to_be_retried(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 1)
            routes.update(table(None, "stopped"))
            resume(url)
            rest = [line for line in lines if line]
        error = error_of(rest)
        assert error["code"] == "unavailable"
        assert error["message"].startswith("the model is unavailable for now: no model runs in the main slot")
        assert "held while its session was paused" in error["message"]
        [record] = recorded(tmp_path)
        assert (record["status"], record["error"]["code"], record["held"]["how"]) == (503, "no_engine", "resumed")
        assert received(engine[1]) == []


def test_an_engines_own_refusal_after_resuming_is_worded_so_opencode_does_not_retry_it(tmp_path: Path) -> None:
    for status, code in ((400, "engine_refused"), (503, "unavailable")):
        with started(tmp_path / f"engine-{status}.log", "--fake-refuse", str(status)) as port:
            table_ = Routes()
            table_.update(table(port))
            with holding(table_, tmp_path / str(status)) as url:
                pause(url)
                with asking(url, {"X-Session-Id": SESSION}) as answer:
                    lines = answer.iter_lines()
                    comments(lines, 1)
                    resume(url)
                    rest = [line for line in lines if line]
                error = error_of(rest)
                assert error["code"] == code
                assert "the request exceeds the available context size" in error["message"]
                [record] = recorded(tmp_path / str(status))
                assert (record["status"], record["error"]) == (status, REFUSAL)
        if status == 400:
            assert "15000" not in error["message"]
            assert "1 5 0 0 0 tokens" in error["message"]


def test_the_wait_for_a_starting_slot_after_resuming_keeps_the_comment_lines(
    routes: Routes,  # noqa: F811
    engine: tuple[int, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    with holding(routes, tmp_path) as url:
        pause(url)
        with asking(url, {"X-Session-Id": SESSION}) as answer:
            lines = answer.iter_lines()
            comments(lines, 1)
            routes.update(table(None, "starting"))
            resume(url)
            waiting = comments(lines, 3)
            assert waiting == [": held by Clank: resumed; waiting for the model's slot"] * 3
            routes.update(table(engine[0]))
            rest = [line for line in lines if line]
        assert rest[-1] == "data: [DONE]"
        assert len(received(engine[1])) == 1
