"""Design 0003 §9: the fake engine the runtime's tests run starts from the real adapter's plan, says it is ready in its
engine's own words (so the adapter's `ready` reads it), answers the API a check uses, and stops by its identity; told
to fail at its start, it says it ran out of GPU memory and ends, unless it was told so for another context only."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

from clank.components.runtime.adapters.engine import Launch
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.hosts.host import HostError
from clank.components.runtime.hosts.local import LocalHost
from tests.fakes.engine import program
from tests.support.served import free_port


def until(holds: Callable[[], bool], seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while not holds():
        assert time.monotonic() < deadline, "never got there"
        time.sleep(0.05)


def lines(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []


def ask(port: int, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as answer:
        found: dict[str, object] = json.loads(answer.read())
        return found


def test_it_starts_from_the_real_plan_says_it_is_ready_in_its_engines_words_answers_and_stops(tmp_path: Path) -> None:
    engine, model, port = KvmemLlamacpp("v0.16.0-rc1"), "/m/Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf", free_port()
    plan = engine.plan({}, Launch(program=program("kvmem"), model_path=model, port=port))
    host = LocalHost()
    log = tmp_path / "engine.log"
    identity = host.spawn(plan.argv, plan.env, str(tmp_path), log)
    try:
        until(lambda: any(engine.ready(line) for line in lines(log)))
        assert engine.memory_report(lines(log)), "it reports its memory as its engine does"
        listed = ask(port, "/v1/models")
        name = listed["data"][0]["id"]  # type: ignore[index]
        assert name == Path(model).name
        say = [{"role": "user", "content": "Say OK"}]
        answered = ask(port, "/v1/chat/completions", {"model": name, "messages": say})
        assert answered["choices"][0]["message"]["content"] == "OK"  # type: ignore[index]
    finally:
        assert host.stop(identity, 5) in ("stopped", "killed")


def test_told_to_fail_it_says_the_gpu_ran_out_of_memory_and_ends(tmp_path: Path) -> None:
    plan = KvmemLlamacpp("v0.16.0-rc1").plan(
        {}, Launch(program=program("kvmem", "--fake-fail-start", "oom"), model_path="/m/x.gguf", port=free_port())
    )
    host = LocalHost()
    log = tmp_path / "engine.log"
    try:
        identity = host.spawn(plan.argv, plan.env, str(tmp_path), log)
        until(lambda: not host.alive(identity))
    except HostError:
        pass  # it may end before the host has seen it run
    until(lambda: any("out of memory" in line for line in lines(log)))


def test_told_to_fail_for_another_context_only_it_starts(tmp_path: Path) -> None:
    fails_small = program("kvmem", "--fake-fail-start", "oom", "--fake-only-context", "4096")
    engine, port = KvmemLlamacpp("v0.16.0-rc1"), free_port()
    plan = engine.plan({"context": 8192}, Launch(program=fails_small, model_path="/m/x.gguf", port=port))
    host = LocalHost()
    log = tmp_path / "engine.log"
    identity = host.spawn(plan.argv, plan.env, str(tmp_path), log)
    try:
        until(lambda: any(engine.ready(line) for line in lines(log)))
    finally:
        assert host.stop(identity, 5) in ("stopped", "killed")
    assert not any("out of memory" in line for line in lines(log))
