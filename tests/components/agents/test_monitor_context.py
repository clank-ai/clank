"""Design 0012 §3, §4, §4.1, §4.4 and §11 step 3, decision 0067: a session's context totals come from the loaded slot's
facts only (its engine adapter's context facts, its model's catalog entry), with both engine styles, KVMem and upstream
llama.cpp: how much of the window the session's last finished step used (its prompt and its answer, as its engine
reports them), how much is left before OpenCode compacts (262,144 and 16,384 give 245,760) and what a compaction keeps
(15,000), the share read from the cache where each engine reports it, what sits on the GPU (under KVMem a stored size of
at most 36,864 all of it, above it 36,864 and the rest in system memory; under llama.cpp its whole window attended), a
figure an engine does not report absent and never a number, the window changed at the next step after a slot switch,
and the engine marked as taken by another session's request. A step whose stream the engine broke off is not a finished
step, and an engine that stopped, started again or was switched holds no conversation, whoever's request it read last.
The sessions here are synthetic."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.context import totals
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.runtime.catalog import catalog
from clank.components.runtime.kinds import Preset
from clank.components.runtime.service import preset_facts
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.components.gateway.test_server import ASKED, serving, started, table
from tests.fakes.platform import FakePlatform
from tests.support.served import free_port

SESSION = "ses_0c2e9ffe1Qk2Lr8xYb3Zd7a1f0"
OTHER = "ses_0e5d7ffe2Pq8Rs3tUv4Wx5y6z7"
CHILD = "ses_0d4c3ffe0Hn5Tq1wVc6Ma7a1f1"
TIME = "2026-10-19T12:31:00.000000Z"
KVMEM, LLAMACPP = ("kvmem-llamacpp", "v0.16.0-rc1"), ("llamacpp", "b11588")
PRESETS = {
    "daily-262k": Preset(title="daily 262K", engine=KVMEM[0], engine_version=KVMEM[1], model="qwen3.8-27b"),
    "frontier-96k": Preset(title="frontier 96K", engine=KVMEM[0], engine_version=KVMEM[1], model="qwen3.8-27b",
                           options={"context": 98304, "kvmem.budget": 24576, "max_output": 8192}),
    "cpu-8k": Preset(title="CPU 8K", engine=LLAMACPP[0], engine_version=LLAMACPP[1], model="qwen2.5-coder-0.5b",
                     options={"max_output": 1024}),
}  # fmt: skip


def facts_of(name: str) -> dict[str, Any] | None:
    """A preset's facts, as the runtime gives them: the real adapters' and the catalog's."""
    preset = PRESETS.get(name)
    return None if preset is None else preset_facts(name, preset, catalog()[preset.model])


def route(preset: str | None) -> dict[str, Any]:
    """The routes, the main slot running a preset (or nothing)."""
    found = PRESETS.get(preset or "")
    slot = {"status": "ready" if found else "stopped", "busy": False, "preset": preset if found else None,
            "title": found.title if found else None,
            "facts": facts_of(preset) if preset and found else None}  # fmt: skip
    return {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main"}


def ended(
    id: str, prompt: int, answer: int, *, preset: str = "daily-262k", cached: int | None = None, style: str = "kvmem",
    **fields: Any,
) -> dict[str, Any]:  # fmt: skip
    """A request of the session that ended, as the gateway's activity gives it, with its engine's own figures."""
    usage: dict[str, Any] = {"prompt_tokens": prompt, "completion_tokens": answer}
    timings = None
    if cached is not None and style == "kvmem":
        usage["prompt_cache_hit_tokens"] = cached
    if cached is not None and style == "llamacpp":
        timings = {"prompt_n": prompt - cached, "cache_n": cached, "predicted_n": answer}
    return {"id": id, "time": TIME, "role": "agent", "slot": "main", "session": SESSION, "parent": "", "status": 200,
            "seconds": 12.0, "tokens": answer, "counts": {"thinking": 0, "answer": answer, "tool": 0},
            "per_second": 40.0, "prompt_tokens": prompt, "error": "", "looped": "", "left": False, "calls": [],
            "preset": preset, "usage": usage, "timings": timings, **fields}  # fmt: skip


def held(id: str, session: str, parent: str = "", flying: bool = False, gone: bool = False) -> dict[str, Any]:
    """A slot's newest request (`gone`: its engine stopped, started again or was switched since)."""
    return {"id": id, "session": session, "parent": parent, "time": TIME, "flying": flying, "gone": gone}


def doing(*requests: dict[str, Any], slots: dict[str, Any] | None = None) -> dict[str, Any]:
    """The gateway's activity of the session, with its requests that ended; the slot's newest is its last unless
    given."""
    newest = {"main": held(requests[-1]["id"], SESSION)} if requests else {}
    return {"state": "running", "port": 18210, "problem": "", "requests": [], "served": len(requests),
            "last": requests[-1] if requests else None, "ended": list(requests),
            "slots": newest if slots is None else slots}  # fmt: skip


def context(activity: dict[str, Any], routes: dict[str, Any]) -> dict[str, Any]:
    return totals(SESSION, activity, routes, facts_of, OpenCode().compaction)


def test_262144_and_16384_give_a_compaction_line_of_245760_and_a_compaction_keeps_15000() -> None:
    rule = OpenCode().compaction(262144, 16384)
    assert rule is not None
    assert (rule.line, rule.keeps) == (245760, 15000)
    assert "OpenCode" in rule.rule
    assert OpenCode().compaction(262144, 64000).line == 262144 - 32000, "the output limit counted up to 32,000"
    assert OpenCode().compaction(8192, 128).keeps == 2016, "a quarter of the line"
    assert OpenCode().compaction(4096, 1024).keeps == 2000, "at least 2,000"
    shown = context(doing(), route("daily-262k"))
    assert (shown["window"], shown["output"], shown["line"], shown["keeps"]) == (262144, 16384, 245760, 15000)


def test_used_is_the_last_finished_steps_prompt_and_answer_and_left_is_the_line_less_it() -> None:
    looped = ended("r-3", 160000, 300, looped="the same closing tags again")
    left = ended("r-4", 0, 0, left=True)
    failed = {**ended("r-5", 0, 0), "status": 500, "error": "the engine broke off", "usage": None}
    shown = context(doing(ended("r-1", 100000, 2000), ended("r-2", 150000, 2661), looped, left, failed),
                    route("daily-262k"))  # fmt: skip
    assert shown["step"] == {"id": "r-2", "time": TIME, "preset": "daily-262k"}, "a stopped or failed one left"
    assert (shown["prompt"], shown["answer"], shown["used"]) == (150000, 2661, 152661)
    assert shown["left"] == 93099, "245,760 less 152,661"
    assert shown["share"] == pytest.approx(152661 / 262144)


def test_under_kvmem_a_stored_size_of_at_most_36864_is_all_on_the_gpu() -> None:
    shown = context(doing(ended("r-1", 30000, 6864)), route("daily-262k"))
    assert shown["gpu"] == {"device": "gpu", "exact": 36864, "block": 128, "first": 128,
                            "picks": "by likeness to the last user message", "stored": 36864, "attended": 36864,
                            "elsewhere": 0}  # fmt: skip


def test_under_kvmem_above_36864_the_rest_is_in_system_memory() -> None:
    gpu = context(doing(ended("r-1", 150000, 2661)), route("daily-262k"))["gpu"]
    assert (gpu["stored"], gpu["attended"], gpu["elsewhere"]) == (152661, 36864, 115797)


def test_under_llamacpp_the_whole_window_is_attended() -> None:
    shown = context(doing(ended("r-1", 6000, 100, preset="cpu-8k")), route("cpu-8k"))
    assert shown["gpu"] == {"device": "cpu", "exact": None, "block": None, "first": None, "picks": "",
                            "stored": 6100, "attended": 6100, "elsewhere": 0}  # fmt: skip
    assert (shown["window"], shown["output"], shown["line"]) == (8192, 1024, 8192 - 1024)


def test_the_cache_share_is_read_where_each_engine_says_it_reports_it() -> None:
    kvmem = context(doing(ended("r-1", 40000, 100, cached=39000)), route("daily-262k"))
    assert (kvmem["cached"], kvmem["cache_reported"], kvmem["cache_share"]) == (39000, True, 0.975)
    cpu = context(doing(ended("r-1", 6000, 100, preset="cpu-8k", cached=5400, style="llamacpp")), route("cpu-8k"))
    assert (cpu["cached"], cpu["cache_share"]) == (5400, 0.9), "llama.cpp's, in its timings"
    crossed = context(doing(ended("r-1", 6000, 100, preset="cpu-8k", cached=5400, style="kvmem")), route("cpu-8k"))
    assert (crossed["cached"], crossed["cache_share"]) == (None, None), "llama.cpp never reports it in its usage"
    assert crossed["cache_reported"] is True, "this engine reports it; this step's answer did not"


def test_a_figure_an_engine_does_not_report_is_absent_never_a_number() -> None:
    def silent(name: str) -> dict[str, Any] | None:
        found = facts_of(name)
        assert found is not None
        fields = {key: path for key, path in found["engine"]["fields"].items() if key != "cached"}
        return {**found, "engine": {**found["engine"], "fields": fields}}

    activity = doing(ended("r-1", 40000, 100, cached=39000))
    shown = totals(SESSION, activity, route("daily-262k"), silent, OpenCode().compaction)
    assert (shown["cached"], shown["cache_reported"], shown["cache_share"]) == (None, False, None)
    assert shown["used"] == 40100, "what it reports is still read"


def test_a_slot_switch_to_another_preset_changes_the_window_at_the_next_step() -> None:
    first = ended("r-1", 90000, 1000)
    before = context(doing(first), route("frontier-96k"))
    assert (before["window"], before["line"], before["gpu"]["exact"]) == (262144, 245760, 36864), "the step's preset's"
    assert before["switched"] == {"preset": "frontier-96k", "title": "frontier 96K", "window": 98304, "output": 8192}
    after = context(doing(first, ended("r-2", 91000, 500, preset="frontier-96k")), route("frontier-96k"))
    assert (after["window"], after["line"], after["switched"]) == (98304, 98304 - 8192, None)
    assert after["gpu"]["exact"] == 24576
    assert after["facts"]["preset"] == "frontier-96k"


def test_another_sessions_request_marks_the_engine_as_taken() -> None:
    mine = ended("r-1", 40000, 100)
    own = context(doing(mine), route("daily-262k"))
    assert own["holder"] == {**held("r-1", SESSION), "this": True, "subagent": False, "taken": False, "lost": ""}
    for slots, why in [
        ({"main": held("r-2", OTHER, flying=True)}, "another session's request in flight"),
        ({"main": held("r-2", OTHER)}, "another session's request that ended"),
        ({"main": held("r-2", "")}, "a request of no session"),
    ]:
        holder = context(doing(mine, slots=slots), route("daily-262k"))["holder"]
        assert (holder["this"], holder["taken"]) == (False, True), why
    child = context(doing(mine, slots={"main": held("r-3", CHILD, SESSION, True)}), route("daily-262k"))["holder"]
    assert (child["subagent"], child["taken"]) == (True, True), "a subagent's is another conversation"
    cpu = context(doing(ended("r-1", 6000, 100, preset="cpu-8k"), slots={"main": held("r-2", OTHER)}), route("cpu-8k"))
    assert (cpu["holder"]["this"], cpu["holder"]["taken"]) == (False, False), "llama.cpp may keep several"
    assert context(doing(mine, slots={}), route("daily-262k"))["holder"] is None, "none since the gateway started"


def test_a_step_whose_stream_the_engine_broke_off_is_not_the_last_finished_step() -> None:
    broken = {**ended("r-2", 0, 0), "usage": None, "broken": "the engine broke off its answer: its stream stopped"}
    shown = context(doing(ended("r-1", 150000, 2661), broken), route("daily-262k"))
    assert (shown["step"]["id"], shown["used"], shown["left"]) == ("r-1", 152661, 93099), "the step before it"
    unreported = context(doing(ended("r-1", 150000, 2661), {**ended("r-2", 0, 0), "usage": None}), route("daily-262k"))
    assert (unreported["step"]["id"], unreported["used"]) == ("r-2", None), "it ended well: its size is not known"


def test_an_engine_that_stopped_started_again_or_was_switched_holds_no_conversation() -> None:
    mine = ended("r-1", 150000, 2661)
    for routes, slots, lost in [
        (route(None), None, "stopped"),
        ({**route("daily-262k"), "slots": {"main": {**route("daily-262k")["slots"]["main"], "status": "starting"}}},
         None, "starting"),
        (route("frontier-96k"), None, "switched"),
        (route("daily-262k"), {"main": held("r-1", SESSION, gone=True)}, "restarted"),
        (route(None), {}, "stopped"),
    ]:  # fmt: skip
        holder = context(doing(mine, slots=slots), routes)["holder"]
        assert (holder["this"], holder["taken"], holder["lost"]) == (False, False, lost), lost
    flying = context(doing(mine, slots={"main": held("r-2", SESSION, flying=True)}), route("frontier-96k"))["holder"]
    assert (flying["this"], flying["lost"]) == (True, ""), "its next step is in the new engine now"
    taken = context(doing(mine, slots={"main": held("r-2", OTHER)}), route("daily-262k"))["holder"]
    assert (taken["taken"], taken["lost"]) == (True, ""), "taken, not lost"


def test_with_no_step_ended_the_window_is_the_slots_and_what_is_used_is_not_known() -> None:
    shown = context(doing(), route("daily-262k"))
    assert (shown["step"], shown["used"], shown["left"], shown["cached"]) == (None, None, None, None)
    assert (shown["window"], shown["line"], shown["facts"]["preset"]) == (262144, 245760, "daily-262k")
    assert (shown["gpu"]["exact"], shown["gpu"]["stored"], shown["gpu"]["attended"]) == (36864, None, None)
    nothing = context(doing(), route(None))
    assert (nothing["facts"], nothing["window"], nothing["line"], nothing["gpu"]) == (None, None, None, None)
    assert nothing["slot"] == {"name": "main", "status": "stopped", "preset": None, "title": None}


@pytest.mark.parametrize(
    ("style", "engine", "preset"), [("kvmem", KVMEM, "daily-262k"), ("llamacpp", LLAMACPP, "cpu-8k")]
)
def test_the_totals_read_each_fake_engine_styles_own_fields_through_the_gateway(
    tmp_path: Path, style: str, engine: tuple[str, str], preset: str
) -> None:
    fake = ("--fake-prompt-tokens", "40000", "--fake-cached-tokens", "39000")
    with started(tmp_path / f"{style}.log", *fake, style=style) as port:
        slot = {**table(port)["slots"]["main"], "engine": engine[0], "version": engine[1], "preset": preset}
        routes = Routes()
        routes.update({**table(port), "slots": {"main": slot}})
        with serving(routes, GatewaySettings(port=free_port(), hold_seconds=10), tmp_path) as url:
            body = {**ASKED, "max_tokens": 6, "stream": True, "stream_options": {"include_usage": True}}
            headers = {"X-Session-Id": SESSION}
            with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body, headers=headers, timeout=30) as answer:
                for _ in answer.iter_lines():
                    pass
            activity: dict[str, Any] = {}
            for _ in range(200):
                activity = httpx2.get(f"{url}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()
                if activity.get("ended"):
                    break
    shown = context(activity, route(preset))
    assert (shown["used"], shown["cached"], shown["cache_share"]) == (40006, 39000, 0.975), style
    assert shown["holder"]["this"] is True


def test_a_stream_the_engine_broke_off_after_a_good_step_leaves_that_steps_totals_through_the_gateway(
    tmp_path: Path,
) -> None:
    fake = ("--fake-prompt-tokens", "40000", "--fake-end-after", "3")
    with started(tmp_path / "kvmem.log", *fake) as port:
        slot = {**table(port)["slots"]["main"], "preset": "daily-262k"}
        routes = Routes()
        routes.update({**table(port), "slots": {"main": slot}})
        with serving(routes, GatewaySettings(port=free_port(), hold_seconds=10), tmp_path) as url:
            headers = {"X-Session-Id": SESSION}
            for tokens in (3, 8):  # a good step, then one the engine breaks off after 3 tokens
                body = {**ASKED, "max_tokens": tokens, "stream": True, "stream_options": {"include_usage": True}}
                with httpx2.stream("POST", f"{url}/v1/chat/completions", json=body, headers=headers,
                                   timeout=30) as answer:  # fmt: skip
                    for _ in answer.iter_lines():
                        pass
            activity: dict[str, Any] = {}
            for _ in range(200):
                activity = httpx2.get(f"{url}/activity", params={"session": SESSION, "ended": True}, timeout=10).json()
                if len(activity.get("ended") or []) == 2:
                    break
    assert activity["ended"][-1]["broken"], "the second step broke off"
    shown = context(activity, route("daily-262k"))
    assert (shown["step"]["id"], shown["used"]) == (activity["ended"][0]["id"], 40003)


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def test_the_services_context_route_gives_a_sessions_totals(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = kernel.parts["gateway"]
    asked: list[tuple[Any, ...]] = []

    def activity(session: str = "", subagents: bool = False, ended_too: bool = False) -> dict[str, Any]:
        asked.append((session, subagents, ended_too))
        return doing(ended("r-1", 150000, 2661, cached=148000))

    monkeypatch.setattr(gateway, "activity", activity)
    monkeypatch.setattr(gateway, "routes", lambda: route("daily-262k"))
    monkeypatch.setattr(gateway, "facts", facts_of)
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:
        answer = http.get(f"/api/v1/agents/context/myproject/{SESSION}", headers={"Authorization": "Bearer t"})
    assert answer.status_code == 200, answer.text
    shown = answer.json()
    assert (shown["workspace"], shown["session"], shown["used"], shown["left"]) == ("myproject", SESSION, 152661, 76715)
    assert (shown["window"], shown["line"]) == (262144, 229376), "the margin OpenCode is told of: 16,384 by default"
    assert shown["facts"]["engine"]["label"] == "KVMem/llama.cpp"
    assert asked == [(SESSION, False, True)], "the session's own requests, with those that ended"
