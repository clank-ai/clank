"""Design 0001 §6.1-§6.5, design 0004 §2 and design 0016 §8: the gateway sends a request for a role to the engine of the
role's slot, with the model name the runtime's settings give and in that engine's own fields (KVMem takes llama.cpp's);
a streamed answer streams; with no engine running the request is refused, saying how to load one; a request that comes
while the slot switches waits for the new engine; a client that leaves mid-answer makes the engine stop; OpenCode's
title requests are answered by the gateway itself; `/v1/models` lists the roles; and every request is recorded, its
credentials never. An engine that breaks off a request before answering anything (it crashed) has the request sent again
once its slot is served again (the runtime restarts it), on the same stream; one that breaks off after answering, or
whose slot does not come back, ends the stream with an error that says so, and so does one whose slot was switched to a
cloud model meanwhile: what was meant for this machine is never sent to the cloud by the gateway itself. A stream that
stops without its end (no finish reason, no `[DONE]`) has broken off too: on Linux a crashed engine's connection is
closed cleanly, so nothing else shows it. The loop guard (design 0004 §2, decision 0040): an answer or a tool call that
repeats itself is stopped soon, the engine stops writing it, and the stream ends with an error that says what repeated;
with the guard off it runs to its end."""

import contextlib
import json
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn

from clank.components.gateway import routing
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.loops import LoopGuard
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import _guarded, create_gateway
from clank.kernel.service import server_config
from tests.fakes.engine import program
from tests.support.served import free_port

MODEL = "qwen3.8-27b"
TITLE_SYSTEM = "You are a title generator. You output ONLY a thread title. Nothing else."


def table(port: int | None, status: str = "ready") -> dict[str, Any]:
    """The service's routes: the main slot running KVMem, as `GET /gateway/routes` answers."""
    slot = {
        "status": status, "port": port, "engine": "kvmem-llamacpp", "version": "v0.16.0-rc1", "model_name": MODEL,
        "preset": "daily-262k", "title": "daily 262K", "context": 262144, "output": 8192,
    }  # fmt: skip
    return {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main"}


@contextlib.contextmanager
def started(log: Path, *fake: str, style: str = "kvmem") -> Iterator[int]:
    """A fake engine (KVMem unless another style is named) with its own flags, listening; its port."""
    port = free_port()
    argv = [*program(style, *fake), "-m", "/m/q.gguf", "--port", str(port)]
    with log.open("wb") as output:
        process = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 20
        while "listening on" not in log.read_text(encoding="utf-8", errors="replace"):
            assert time.monotonic() < deadline, "the fake engine never listened"
            time.sleep(0.05)
        yield port
    finally:
        process.kill()
        process.wait(60)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    """A fake KVMem, answering one token every 50 ms; its port and its log."""
    log = tmp_path / "engine.log"
    with started(log, "--fake-token-seconds", "0.05") as port:
        yield port, log


@pytest.fixture
def routes(engine: tuple[int, Path]) -> Routes:
    found = Routes()
    found.update(table(engine[0]))
    return found


@contextlib.contextmanager
def serving(routes: Routes, settings: GatewaySettings, tmp_path: Path) -> Iterator[str]:
    """The gateway with these settings, served for real on their port; its base URL."""
    app = create_gateway(routes, settings, TrafficLog(tmp_path / "traffic", 256, 14))
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


@pytest.fixture
def gateway(routes: Routes, tmp_path: Path) -> Iterator[str]:
    """The gateway, served for real on a free port; its base URL."""
    with serving(routes, GatewaySettings(port=free_port(), hold_seconds=10), tmp_path) as url:
        yield url


def received(log: Path) -> list[dict[str, Any]]:
    """The requests the fake engine took, as it logged them."""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return [json.loads(line.removeprefix("received ")) for line in lines if line.startswith("received ")]


def recorded(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for file in sorted((tmp_path / "traffic").glob("*.jsonl")) for line in file.read_text(
        encoding="utf-8").splitlines()]  # fmt: skip


ASKED = {"model": "agent", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 3}


def test_a_request_reaches_the_slots_engine_with_its_model_name_and_in_its_own_fields(
    gateway: str, engine: tuple[int, Path], tmp_path: Path
) -> None:
    body = {**ASKED, "enable_thinking": False}
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=body, headers={"Authorization": "Bearer local"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["choices"][0]["message"]["content"] == "OK"
    [took] = received(engine[1])
    assert (took["model"], took["chat_template_kwargs"]) == (MODEL, {"enable_thinking": False})
    assert "enable_thinking" not in took
    [record] = recorded(tmp_path)
    assert (record["role"], record["slot"], record["preset"], record["status"]) == (
        "agent",
        "main",
        "daily-262k",
        200,
    )
    assert record["notes"] == ["enable_thinking became chat_template_kwargs.enable_thinking"]
    assert "Bearer local" not in json.dumps(record)


def test_a_streamed_answer_streams_and_its_usage_and_first_token_are_recorded(gateway: str, tmp_path: Path) -> None:
    body = {**ASKED, "max_tokens": 4, "stream": True, "stream_options": {"include_usage": True}}
    pieces: list[str] = []
    with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
        assert answer.status_code == 200
        for line in answer.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                for choice in json.loads(line[6:]).get("choices", []):
                    pieces.append(choice.get("delta", {}).get("content") or "")
    assert "".join(pieces) == "w0 w1 w2 w3 "
    [record] = recorded(tmp_path)
    assert record["usage"]["completion_tokens"] == 4
    assert record["first_token_ms"] > 0
    assert record["answer"] == "w0 w1 w2 w3 "


def test_the_live_view_follows_a_streamed_answer_as_it_comes_and_keeps_it_after(gateway: str) -> None:
    body = {**ASKED, "max_tokens": 20, "stream": True}
    seen: list[dict[str, Any]] = []
    with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
        for line in answer.iter_lines():
            if line.startswith("data: w") or '"w3 "' in line:
                seen.append(httpx2.get(f"{gateway}/activity/live", timeout=10).json())
    middle = next(found for found in seen if found["flying"] and found["length"])
    assert middle["parts"][0][0] == "answer"
    assert middle["asked"] == "Hi"
    done = httpx2.get(f"{gateway}/activity/live", timeout=10).json()
    assert done["flying"] is False
    assert "".join(text for _, text in done["parts"]) == "".join(f"w{index} " for index in range(20))
    newer = httpx2.get(f"{gateway}/activity/live", params={"after": done["length"] - 4}, timeout=10).json()
    assert newer["parts"] == [["answer", "w19 "]]


def test_with_no_engine_running_the_request_is_refused_saying_how_to_load_one(gateway: str, routes: Routes) -> None:
    routes.update(table(None, "stopped"))
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=ASKED, timeout=30)
    assert answer.status_code == 503
    assert "clank model load" in answer.json()["error"]["message"]


def test_a_request_that_comes_while_the_slot_switches_waits_for_the_new_engine(
    gateway: str, routes: Routes, engine: tuple[int, Path]
) -> None:
    routes.update(table(None, "starting"))
    threading.Timer(0.8, lambda: routes.update(table(engine[0]))).start()
    started = time.monotonic()
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=ASKED, timeout=30)
    assert answer.status_code == 200, answer.text
    assert time.monotonic() - started >= 0.7


def test_a_client_that_leaves_mid_answer_makes_the_engine_stop(gateway: str, engine: tuple[int, Path]) -> None:
    body = {**ASKED, "max_tokens": 400, "stream": True}
    with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
        seen = 0
        for line in answer.iter_lines():
            seen += line.startswith("data: ")
            if seen == 3:
                break
    deadline = time.monotonic() + 15
    while "client left after" not in engine[1].read_text(encoding="utf-8", errors="replace"):
        assert time.monotonic() < deadline, "the engine went on generating for a client that had left"
        time.sleep(0.1)
    left = next(line for line in engine[1].read_text(encoding="utf-8").splitlines() if "client left after" in line)
    assert int(left.split()[-2]) < 400


def test_opencodes_title_request_is_answered_by_the_gateway(gateway: str, engine: tuple[int, Path]) -> None:
    body = {"model": "agent", "stream": False, "messages": [
        {"role": "system", "content": TITLE_SYSTEM},
        {"role": "user", "content": "Generate a title for this conversation:\n"},
        {"role": "user", "content": "Fix the parser\nIt fails on empty files."},
    ]}  # fmt: skip
    answer = httpx2.post(f"{gateway}/v1/chat/completions", json=body, timeout=30)
    assert answer.status_code == 200
    assert answer.json()["choices"][0]["message"]["content"] == "Fix the parser"
    assert received(engine[1]) == [], "the engine was not asked"


def test_models_lists_the_roles(gateway: str) -> None:
    listed = httpx2.get(f"{gateway}/v1/models", timeout=10).json()
    assert [model["id"] for model in listed["data"]] == ["agent"]


def test_the_gateway_says_what_it_does_now_and_how_the_last_request_went(gateway: str) -> None:
    idle = {"requests": [], "served": 0, "last": None, "slots": {}, "guard": {"on": True, "ratio": 0.06}}
    assert httpx2.get(f"{gateway}/activity", timeout=10).json() == idle, "the loop guard as it applies it"
    body = {**ASKED, "max_tokens": 40, "stream": True}
    with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=30) as answer:
        lines = answer.iter_lines()
        while '"w4 "' not in next(lines):  # five tokens have come
            pass
        now = httpx2.get(f"{gateway}/activity", timeout=10).json()
        for _ in lines:
            pass
    [flying] = now["requests"]
    assert (flying["role"], flying["slot"], flying["phase"]) == ("agent", "main", "answering")
    assert flying["tokens"] >= 5
    assert flying["seconds"] > 0
    deadline = time.monotonic() + 10
    while (done := httpx2.get(f"{gateway}/activity", timeout=10).json())["requests"]:
        assert time.monotonic() < deadline, "the request stayed in flight after its answer ended"
        time.sleep(0.05)
    assert done["served"] == 1
    last = done["last"]
    assert (last["role"], last["slot"], last["status"], last["tokens"], last["error"]) == ("agent", "main", 200, 40, "")
    assert 0 < last["per_second"] <= 25, "the fake engine sends one token every 50 ms"


def streamed(gateway: str, tokens: int) -> tuple[str, list[dict[str, Any]]]:
    """A streamed request's answer, and the error events it ended with, if any."""
    body = {**ASKED, "max_tokens": tokens, "stream": True}
    pieces: list[str] = []
    errors: list[dict[str, Any]] = []
    with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=60) as answer:
        assert answer.status_code == 200
        for line in answer.iter_lines():
            if not line.startswith("data: {"):
                continue
            event = json.loads(line[6:])
            if "error" in event:
                errors.append(event["error"])
            for choice in event.get("choices", []):
                pieces.append(choice.get("delta", {}).get("content") or "")
    return "".join(pieces), errors


def test_a_request_the_engine_broke_off_before_answering_is_sent_again_once_its_slot_is_back(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    crashing = ("--fake-prompt-seconds", "5", "--fake-crash-after", "1.5")  # it dies while it reads the prompt
    with started(tmp_path / "a.log", *crashing) as first, started(tmp_path / "b.log") as second:
        routes.update(table(first))

        def restarted() -> None:  # what the runtime does when its engine ends
            time.sleep(2.0)
            routes.update(table(None, "starting"))
            time.sleep(1.0)
            routes.update(table(second))

        threading.Thread(target=restarted, daemon=True).start()
        answer, errors = streamed(gateway, 4)
    assert (answer, errors) == ("w0 w1 w2 w3 ", [])
    [record] = recorded(tmp_path)
    assert record["again"] == "the engine broke off before answering; sent again once the slot was served again"
    assert record["answer"] == "w0 w1 w2 w3 "
    assert "left" not in record


def test_a_request_the_engine_broke_off_while_its_slot_switched_to_a_cloud_model_ends_saying_so(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    from tests.components.gateway.test_cloud_forwarding import cloud_slot

    crashing = ("--fake-prompt-seconds", "5", "--fake-crash-after", "1.5")
    with started(tmp_path / "a.log", *crashing) as first:
        routes.update(table(first))

        def switched() -> None:  # the owner loads a cloud model in the slot meanwhile
            time.sleep(2.0)
            routes.update(table(None, "starting"))
            time.sleep(1.0)
            routes.update({**table(None), "slots": {"main": cloud_slot("http://127.0.0.1:9")}})

        threading.Thread(target=switched, daemon=True).start()
        answer, errors = streamed(gateway, 4)
    assert answer == ""
    assert [error["code"] for error in errors] == ["engine_broke_off"]
    assert "now runs the cloud model" in errors[0]["message"]


def test_an_engine_that_breaks_off_after_answering_ends_the_stream_with_an_error_that_says_so(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    with started(tmp_path / "a.log", "--fake-token-seconds", "0.3", "--fake-crash-after", "1.2") as port:
        routes.update(table(port))
        answer, errors = streamed(gateway, 20)
    assert answer.startswith("w0 ")
    assert [error["code"] for error in errors] == ["engine_broke_off"]
    assert "after answering" in errors[0]["message"]
    [record] = recorded(tmp_path)
    assert record["broken"].startswith("the engine broke off its answer")


def test_a_slot_that_does_not_come_back_ends_the_stream_with_an_error(
    routes: Routes, gateway: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routing, "SETTLE_SECONDS", 1.0)
    with started(tmp_path / "a.log", "--fake-prompt-seconds", "5", "--fake-crash-after", "1.5") as port:
        routes.update(table(port))
        threading.Timer(2.0, lambda: routes.update(table(None, "failed"))).start()
        answer, errors = streamed(gateway, 4)
    assert answer == ""
    assert [error["code"] for error in errors] == ["engine_broke_off"]
    assert "not served again" in errors[0]["message"]


def test_a_stream_that_stops_without_its_end_after_answering_ends_with_an_error_that_says_so(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    with started(tmp_path / "a.log", "--fake-end-after", "3") as port:
        routes.update(table(port))
        answer, errors = streamed(gateway, 8)
    assert answer == "w0 w1 w2 "
    assert [error["code"] for error in errors] == ["engine_broke_off"]
    [record] = recorded(tmp_path)
    assert record["broken"].startswith("the engine broke off its answer")


def test_a_stream_that_stops_without_its_end_before_answering_is_sent_again_once_its_slot_is_back(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    with started(tmp_path / "a.log", "--fake-end-after", "0") as first, started(tmp_path / "b.log") as second:
        routes.update(table(first))

        def restarted() -> None:  # what the runtime does when its engine ends
            time.sleep(1.0)
            routes.update(table(None, "starting"))
            time.sleep(1.0)
            routes.update(table(second))

        threading.Thread(target=restarted, daemon=True).start()
        answer, errors = streamed(gateway, 4)
    assert (answer, errors) == ("w0 w1 w2 w3 ", [])
    [record] = recorded(tmp_path)
    assert record["again"] == "the engine broke off before answering; sent again once the slot was served again"


def test_a_client_that_leaves_an_answer_sent_again_is_kept_as_having_left(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    crashing = ("--fake-prompt-seconds", "5", "--fake-crash-after", "1.5")  # it dies while it reads the prompt
    with (
        started(tmp_path / "a.log", *crashing) as first,
        started(tmp_path / "b.log", "--fake-token-seconds", "0.05") as second,
    ):
        routes.update(table(first))

        def restarted() -> None:  # what the runtime does when its engine ends
            time.sleep(2.0)
            routes.update(table(None, "starting"))
            time.sleep(1.0)
            routes.update(table(second))

        threading.Thread(target=restarted, daemon=True).start()
        body = {**ASKED, "max_tokens": 400, "stream": True}
        with httpx2.stream("POST", f"{gateway}/v1/chat/completions", json=body, timeout=60) as answer:
            seen = 0
            for line in answer.iter_lines():
                seen += line.startswith("data: {")
                if seen == 3:
                    break  # the client leaves the resent answer
        deadline = time.monotonic() + 15
        while not (kept := recorded(tmp_path)):
            assert time.monotonic() < deadline, "the request was never kept"
            time.sleep(0.05)
    [record] = kept
    assert record["again"].startswith("the engine broke off before answering")
    assert record["left"] == "the client left before the answer ended"
    assert "waiting_again" not in record


def test_a_whole_answer_the_engine_broke_off_is_asked_again_once_its_slot_is_back(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    with (
        started(tmp_path / "a.log", "--fake-prompt-seconds", "5", "--fake-crash-after", "1.5") as first,
        started(tmp_path / "b.log") as second,
    ):
        routes.update(table(first))
        threading.Timer(2.0, lambda: routes.update(table(second))).start()  # another engine serves the slot
        answer = httpx2.post(f"{gateway}/v1/chat/completions", json=ASKED, timeout=60)
    assert answer.status_code == 200, answer.text
    assert answer.json()["choices"][0]["message"]["content"] == "OK"
    [record] = recorded(tmp_path)
    assert record["again"].startswith("the engine broke off before answering")


def left_after(log: Path) -> int:
    """How many tokens the fake engine had written when the gateway left it (waiting for it to say so)."""
    deadline = time.monotonic() + 15
    while "client left after" not in (text := log.read_text(encoding="utf-8", errors="replace")):
        assert time.monotonic() < deadline, "the engine went on writing"
        time.sleep(0.05)
    return int(next(line for line in text.splitlines() if "client left after" in line).split()[-2])


LOOPING = ("--fake-token-seconds", "0.002", "--fake-loop-after", "5")  # 20,000 tokens would take 40 s
OFF = "Ask again; to let such an answer through, set loop_guard to false in config/gateway.json and run clank gateway "
OFF += "restart."


def test_an_answer_that_repeats_itself_is_stopped_and_the_stream_ends_with_an_error_that_says_so(
    routes: Routes, gateway: str, tmp_path: Path
) -> None:
    with started(tmp_path / "a.log", *LOOPING) as port:
        routes.update(table(port))
        answer, errors = streamed(gateway, 20000)
        left = left_after(tmp_path / "a.log")
    assert answer.startswith("w0 w1 w2 w3 w4 </f>\n</invoke>\n</functions>\n")
    assert [error["code"] for error in errors] == ["model_looped"]
    assert errors[0]["message"] == f"Clank's loop guard stopped the answer: its answer repeated itself. {OFF}"
    assert not any(character.isdigit() for character in errors[0]["message"]), "OpenCode retries by numbers"
    assert left < 1500, f"the engine stopped writing soon after: {left} tokens of 20,000"
    [record] = recorded(tmp_path)
    assert record["looped"].startswith("its answer repeated itself (its newest 2,000 characters compress to ")
    assert record["error"] == errors[0]["message"]
    assert "left" not in record, "the gateway ended it; the client did not leave"


def test_a_tool_call_that_repeats_itself_is_stopped_too(routes: Routes, gateway: str, tmp_path: Path) -> None:
    with started(tmp_path / "a.log", *LOOPING, "--fake-loop-in", "tool") as port:
        routes.update(table(port))
        _, errors = streamed(gateway, 20000)
        left = left_after(tmp_path / "a.log")
    assert [error["code"] for error in errors] == ["model_looped"]
    assert errors[0]["message"] == f"Clank's loop guard stopped the answer: its tool call bash repeated itself. {OFF}"
    assert left < 1500


def test_a_thinking_that_repeats_itself_is_stopped_too(routes: Routes, gateway: str, tmp_path: Path) -> None:
    with started(tmp_path / "a.log", *LOOPING, "--fake-loop-in", "thinking") as port:
        routes.update(table(port))
        _, errors = streamed(gateway, 20000)
        left = left_after(tmp_path / "a.log")
    assert [error["code"] for error in errors] == ["model_looped"]
    assert errors[0]["message"] == f"Clank's loop guard stopped the answer: its thinking repeated itself. {OFF}"
    assert left < 1500


def test_each_tool_call_of_an_answer_is_read_apart_by_its_index() -> None:
    guard = LoopGuard()

    def call(index: int, arguments: str, name: str = "") -> None:
        function = {"arguments": arguments, **({"name": name} if name else {})}
        _guarded({"tool_calls": [{"index": index, "function": function}]}, guard)

    call(0, "", "bash")
    call(1, "", "bash")
    for _ in range(64):  # 1,792 characters each: not yet a stretch
        call(0, "</f>\n</invoke>\n</functions>\n")
        call(1, "</f>\n</invoke>\n</functions>\n")
    assert guard.tripped is None, "two calls are two parts"
    for _ in range(20):
        call(0, "</f>\n</invoke>\n</functions>\n")
    assert guard.brief == "its tool call bash repeated itself"


def test_the_gateway_reads_the_stretches_its_settings_give(routes: Routes, tmp_path: Path) -> None:
    longer = GatewaySettings(port=free_port(), hold_seconds=10, loop_windows=[4000])
    with started(tmp_path / "a.log", *LOOPING) as port, serving(routes, longer, tmp_path) as url:
        routes.update(table(port))
        _, errors = streamed(url, 20000)
    assert [error["code"] for error in errors] == ["model_looped"]
    [record] = recorded(tmp_path)
    assert record["looped"].startswith("its answer repeated itself (its newest 4,000 characters compress to ")


def test_with_the_loop_guard_off_an_answer_that_repeats_itself_runs_to_its_end(routes: Routes, tmp_path: Path) -> None:
    off = GatewaySettings(port=free_port(), hold_seconds=10, loop_guard=False)
    with started(tmp_path / "a.log", "--fake-loop-after", "5") as port, serving(routes, off, tmp_path) as url:
        routes.update(table(port))
        answer, errors = streamed(url, 1500)
    assert errors == []
    assert answer.count("</invoke>") == len(range(2, 1495, 6)), "every one of the 1,495 looping tokens came"
