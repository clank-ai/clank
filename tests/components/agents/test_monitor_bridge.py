"""Design 0012 §3, §5.1, §6.1 and §9 (§11 step 4) and design 0013 §5 and §7: the bridge the Monitor and flows need,
run on this machine against a fake OpenCode server replaying a synthetic session's events
(`tests/fixtures/opencode/1.19.0/session.json`).

The bridge pages through a session's messages, each part in the one shape its watch also uses; a message keeps the
session's agent and model; it rejects what waits in a session and its subagents (going on past what was answered
meanwhile), clears a finished tool call's result (the whole part sent back with the time it was cleared), reverts and
unreverts, and asks for a compaction without waiting for it, ending the process that would hold the request when it
does not confirm in time. It gives one call whole (design 0012 §7: the watch cuts a call's input and output), its
input's start and its output's end past a cap.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from clank.components.workspaces.sandbox import image_folder
from clank.kernel.processes import background_flags
from tests.fakes.opencode import FakeOpenCode

BRIDGE = image_folder() / "bridge.py"
LINE = "a line of output" + chr(10)  # 17 characters


def bridge(fake: FakeOpenCode, *argv: str, given: dict[str, Any] | None = None, ports: str = "") -> dict[str, Any]:
    """One run of the bridge against the fake, its JSON answer."""
    done = subprocess.run(
        [sys.executable, str(BRIDGE), *argv], input=json.dumps(given) if given is not None else "",
        capture_output=True, text=True, timeout=60, creationflags=background_flags(),
        env={**os.environ, "CLANK_BRIDGE_PORTS": ports or f"{fake.port}-{fake.port}"},
    )  # fmt: skip
    found: dict[str, Any] = json.loads(done.stdout)
    return found


def test_the_bridge_pages_through_a_sessions_messages_each_part_in_the_watchs_shape() -> None:
    with FakeOpenCode() as fake:
        port = str(fake.port)
        newest = bridge(fake, "page", port, "ses_plan", "2")
        assert [each["info"]["id"] for each in newest["messages"]] == ["msg_04", "msg_05"], "oldest first in a page"
        assert newest["next"], "older messages are left"
        middle = bridge(fake, "page", port, "ses_plan", "2", newest["next"])
        assert [each["info"]["id"] for each in middle["messages"]] == ["msg_02", "msg_03"]
        last = bridge(fake, "page", port, "ses_plan", "2", middle["next"])
        assert [each["info"]["id"] for each in last["messages"]] == ["msg_01"]
        assert last["next"] == ""
        user = last["messages"][0]["info"]
        assert (user["role"], user["agent"], user["model"]) == ("user", "planner", {"providerID": "clank",
                                                                                     "modelID": "agent"})  # fmt: skip
        step = middle["messages"][1]
        assert step["info"]["tokens"]["cache"]["read"] == 9_100
        assert (step["info"]["parent"], step["info"]["finish"]) == ("msg_01", "tool-calls")
        assert step["info"]["completed"] > step["info"]["created"]
        start, task, bash, failed, finish = step["parts"]
        assert start == {"id": "prt_03a", "message": "msg_03", "type": "step-start"}
        assert (task["tool"], task["call"], task["subagent"]) == ("task", "call_02", "ses_child")
        assert (bash["status"], bash["exit"], bash["title"]) == ("completed", 0, "Draw the figure")
        assert (failed["status"], failed["exit"]) == ("error", 2)
        assert failed["error"].startswith("Traceback")
        assert finish["tokens"]["input"] == 12_830
        read = middle["messages"][0]["parts"][2]
        assert read["output"].endswith(f"[{read['length']:,} characters]"), "a long output cut, saying its length"
        assert read["length"] > 1500
        thinking = middle["messages"][0]["parts"][1]
        assert thinking["type"] == "reasoning"
        assert thinking["text"] == "The data should be in data/tau.csv; read it first."
        assert not bridge(fake, "page", port, "ses_gone", "2")["ok"]


def test_the_bridge_gives_one_call_whole_its_input_and_output_cut_only_past_a_cap() -> None:
    with FakeOpenCode() as fake:
        port = str(fake.port)
        with fake.store.lock:
            bash = next(part for part in fake.store.messages["ses_plan"][2]["parts"] if part["id"] == "prt_03c")
            bash["state"]["input"] = {"command": "python -m myproject.sweep " + "--size 8 " * 100, "description": "Run"}
            bash["state"]["output"] = LINE * 3000
            running = next(part for part in fake.store.messages["ses_plan"][2]["parts"] if part["id"] == "prt_03d")
            running["state"] = {"status": "running", "input": {"command": "pytest -q"}, "title": "Run the tests",
                                "metadata": {"output": "collected 9 items\n"}, "time": {"start": 1}}  # fmt: skip
        whole = bridge(fake, "part", port, "ses_plan", "msg_03", "prt_03c")
        assert whole["ok"], whole
        call = whole["part"]
        assert (call["id"], call["message"], call["tool"], call["call"], call["status"]) == (
            "prt_03c", "msg_03", "bash", "call_03", "completed")  # fmt: skip
        assert json.loads(call["input"])["command"].endswith("--size 8 " * 100), "the whole input, past the watch's cut"
        assert call["output"] == LINE * 3000, "the whole output, past the watch's cut"
        assert call["length"] == {"input": len(call["input"]), "output": 17 * 3000}
        assert call["cut"] == {"input": False, "output": False}
        capped = bridge(fake, "part", port, "ses_plan", "msg_03", "prt_03c", "1000")["part"]
        assert (len(capped["output"]), capped["cut"]["output"], capped["length"]["output"]) == (1000, True, 51000)
        assert capped["output"] == call["output"][-1000:], "a long output's end, where a command says how it ended"
        assert capped["input"] == call["input"][:1000], "an input's start"
        so_far = bridge(fake, "part", port, "ses_plan", "msg_03", "prt_03d")["part"]
        assert so_far["status"] == "running"
        assert (so_far["output"], so_far["title"]) == ("collected 9 items\n", "Run the tests"), "its output so far"
        missing = bridge(fake, "part", port, "ses_plan", "msg_03", "prt_nope")
        assert (missing["ok"], missing["error"]) == (False, "msg_03 has no part prt_nope")


def test_a_planner_session_stays_planner_after_a_note() -> None:
    """Design 0012 §9.3 and design 0013 §5: OpenCode gives a message that names no agent to build."""
    with FakeOpenCode() as fake:
        port = str(fake.port)
        assert bridge(fake, "prompt", port, "ses_plan", given={"text": "Check the axis too."})["ok"]
        [note] = fake.sent_to("/session/ses_plan/prompt_async")
        assert (note["agent"], note["model"]) == ("planner", {"providerID": "clank", "modelID": "agent"})
        newest = bridge(fake, "page", port, "ses_plan", "1")["messages"][0]["info"]
        assert (newest["role"], newest["agent"]) == ("user", "planner")
        given = {"text": "Go on.", "agent": "build", "model": {"providerID": "clank", "modelID": "fast"}}
        assert bridge(fake, "prompt", port, "ses_plan", given=given)["ok"]
        sent = fake.sent_to("/session/ses_plan/prompt_async")[-1]
        assert (sent["agent"], sent["model"]) == ("build", {"providerID": "clank", "modelID": "fast"}), "as given"


def test_a_message_finds_the_owners_last_message_however_far_back_and_its_variant() -> None:
    with FakeOpenCode() as fake:
        port = str(fake.port)
        child = fake.store.messages["ses_child"]
        child[0]["info"]["model"]["variant"] = "high"
        step = child[1]
        child += [{**step, "info": {**step["info"], "id": f"msg_c{index:03d}"}} for index in range(3, 60)]
        assert bridge(fake, "prompt", port, "ses_child", given={"text": "and the tests"})["ok"]
        [sent] = fake.sent_to("/session/ses_child/prompt_async")
        assert (sent["agent"], sent["model"], sent["variant"]) == ("explore", {"providerID": "clank",
                                                                               "modelID": "agent"}, "high")  # fmt: skip
        made = bridge(fake, "new", port, given={"title": "From the phone"})["session"]
        assert bridge(fake, "prompt", port, made, given={"text": "hello"})["ok"]
        [first] = fake.sent_to(f"/session/{made}/prompt_async")
        assert first == {"parts": [{"type": "text", "text": "hello"}]}, "a new session's first message names none"


def test_stops_reject_leaves_nothing_waiting_in_the_session_or_its_subagents_and_touches_no_other() -> None:
    """Design 0012 §9.2: OpenCode rejects a session's other asks with the first one rejected."""
    with FakeOpenCode() as fake:
        port = str(fake.port)
        fake.asks = [
            {"id": "per_1", "sessionID": "ses_plan", "permission": "edit", "patterns": ["plot.py"]},
            {"id": "per_2", "sessionID": "ses_plan", "permission": "bash", "patterns": ["rm runs"]},
            {"id": "per_3", "sessionID": "ses_child", "permission": "bash", "patterns": ["ls"]},
            {"id": "per_4", "sessionID": "ses_other", "permission": "edit", "patterns": ["README.md"]},
        ]
        fake.questions = [
            {"id": "que_1", "sessionID": "ses_child", "questions": [{"question": "Which folder?", "options": []}]},
            {"id": "que_2", "sessionID": "ses_other", "questions": [{"question": "Which file?", "options": []}]},
        ]
        found = bridge(fake, "reject", port, "ses_plan")
        assert found == {"ok": True, "rejected": ["per_1", "per_3"], "questions": ["que_1"]}
        assert [each["id"] for each in fake.asks] == ["per_4"]
        assert [each["id"] for each in fake.questions] == ["que_2"]
        assert fake.sent_to("/permission/per_1/reply") == [{"reply": "reject"}]
        assert fake.sent_to("/question/que_1/reject") == [None]
        assert bridge(fake, "reject", port, "ses_plan") == {"ok": True, "rejected": [], "questions": []}


def test_reject_goes_on_past_an_ask_or_a_question_answered_meanwhile() -> None:
    """Answered from the terminal or the phone between the bridge's listing and its reject: OpenCode no longer finds
    it, and what was rejected is still said, so the service records it."""
    with FakeOpenCode() as fake:
        fake.asks = [
            {"id": "per_1", "sessionID": "ses_plan", "permission": "bash", "patterns": ["ls"]},
            {"id": "per_2", "sessionID": "ses_child", "permission": "bash", "patterns": ["rm runs"]},
        ]
        fake.questions = [
            {"id": "que_1", "sessionID": "ses_plan", "questions": [{"question": "Which n?", "options": []}]},
            {"id": "que_2", "sessionID": "ses_child", "questions": [{"question": "Which folder?", "options": []}]},
        ]
        fake.settled = {"per_1", "que_1"}
        found = bridge(fake, "reject", str(fake.port), "ses_plan")
        assert found == {"ok": True, "rejected": ["per_2"], "questions": ["que_2"]}


def test_a_compaction_not_confirmed_in_time_is_ended_so_it_cannot_start_after_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0012 §9.6: when `held` does not confirm within the bridge's time, the bridge says so and ends it, so no
    compaction starts that the service reported as failed (and a retry asks for no second one)."""
    spec = importlib.util.spec_from_file_location("clank_bridge_under_test", BRIDGE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    silent = tmp_path / "silent.py"
    silent.write_text("import sys, time\nsys.stdin.read()\ntime.sleep(60)\n", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(silent))  # a holder that never confirms
    monkeypatch.setattr(module, "TIMEOUT", 1.0)
    made: list[subprocess.Popen[bytes]] = []
    popen = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> "subprocess.Popen[bytes]":
        process: subprocess.Popen[bytes] = popen(*args, **kwargs)
        made.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", spy)
    try:
        with pytest.raises(RuntimeError, match="not confirmed"):
            module.hold(4096, "/session/ses_plan/summarize", {"auto": True})
        [holder] = made
        assert holder.poll() is not None, "the holder was ended"
    finally:
        for process in made:
            process.kill()
            process.wait(10)
            if process.stdout is not None:
                process.stdout.close()


def test_a_cleared_result_is_sent_back_whole_with_its_time_and_the_step_in_progress_is_refused() -> None:
    """Design 0012 §9.7: OpenCode's own clearing, `state.time.compacted` set on the whole part."""
    with FakeOpenCode() as fake:
        port = str(fake.port)
        [kept] = [part for part in fake.store.messages["ses_plan"][1]["parts"] if part["id"] == "prt_02c"]
        kept = json.loads(json.dumps(kept))
        found = bridge(fake, "clear", port, "ses_plan", "msg_02", "prt_02c")
        assert (found["ok"], found["cleared"], found["length"]) == (True, True, len(kept["state"]["output"]))
        [sent] = fake.sent_to("/session/ses_plan/message/msg_02/part/prt_02c")
        assert sent["state"]["time"] == {**kept["state"]["time"], "compacted": found["compacted"]}
        sent["state"]["time"].pop("compacted")
        assert sent == kept, "the whole part, its output too"
        again = bridge(fake, "clear", port, "ses_plan", "msg_02", "prt_02c")
        assert (again["cleared"], again["compacted"]) == (True, found["compacted"])
        assert len(fake.sent_to("/session/ses_plan/message/msg_02/part/prt_02c")) == 1, "cleared once"
        for message, part, why in (
            ("msg_05", "prt_05b", "the step in progress"),
            ("msg_02", "prt_02b", "not a finished tool call"),
            ("msg_03", "prt_03d", "not a finished tool call"),
            ("msg_01", "prt_01_t", "not a step of the model"),
            ("msg_02", "prt_none", "has no part prt_none"),
        ):
            refused = bridge(fake, "clear", port, "ses_plan", message, part)
            assert not refused["ok"]
            assert why in refused["error"]
        assert [path for _, path, _ in fake.sent] == ["/session/ses_plan/message/msg_02/part/prt_02c"]


def test_revert_names_the_part_and_unrevert_brings_it_back() -> None:
    """Design 0012 §9.5: the revert names the part, so a step is taken back, not the owner's message with it."""
    with FakeOpenCode() as fake:
        port = str(fake.port)
        found = bridge(fake, "revert", port, "ses_plan", "msg_03", "prt_03e")
        cut = {key: found["revert"][key] for key in ("messageID", "partID")}
        assert (found["ok"], found["reverted"], cut) == (True, True, {"messageID": "msg_03", "partID": "prt_03e"})
        assert "diff" in found["revert"], "OpenCode's whole revert, as it answered"
        assert "partID" not in bridge(fake, "revert", port, "ses_plan", "msg_04")["revert"], "the message alone"
        assert fake.sent_to("/session/ses_plan/revert") == [{"messageID": "msg_03", "partID": "prt_03e"},
                                                            {"messageID": "msg_04"}]  # fmt: skip
        assert bridge(fake, "unrevert", port, "ses_plan") == {"ok": True, "unreverted": True, "revert": {}}
        assert "revert" not in fake.store.sessions["ses_plan"]


def test_summarize_returns_at_once_and_its_request_stays_open_until_opencode_answers() -> None:
    """Design 0012 §9.6: OpenCode answers a compaction only once the run ends; the bridge's calls time out after 10 s,
    and a client that leaves could end what it asked for."""
    with FakeOpenCode() as fake:
        port = str(fake.port)
        started = time.monotonic()
        found = bridge(fake, "summarize", port, "ses_plan")
        assert time.monotonic() - started < 8, "it does not wait for the compaction"
        assert found == {"ok": True, "asked": True, "answered": False}
        assert fake.sent_to("/session/ses_plan/summarize") == [
            {"providerID": "clank", "modelID": "agent", "auto": True}
        ]
        assert fake.answered == []
        fake.release.set()
        until(lambda: fake.answered == ["ses_plan"])  # the answer reached the request, still open
        given = {"providerID": "clank", "modelID": "agent"}
        refused = bridge(fake, "summarize", port, "ses_gone", given=given)
        assert not refused["ok"]
        assert refused["error"].startswith("OpenCode answered 404"), "an error OpenCode answers at once is said"


def until(found: Callable[[], Any], seconds: float = 10) -> Any:
    """What `found` gives once it gives something; fails after `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("it did not happen in time")


def test_a_steps_error_keeps_its_name_so_a_stop_tells_apart_from_a_failure() -> None:
    """Design 0012 §6.3 and §9.2 (§11 step 5): OpenCode keeps a step the owner stopped with a `MessageAbortedError`,
    which stays in the context when it has content, and leaves out of it a step that failed; the message's shape keeps
    the error's name beside its words."""
    spec = importlib.util.spec_from_file_location("clank_bridge_under_test", BRIDGE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    step = {"id": "msg_07", "sessionID": "ses_plan", "role": "assistant", "time": {"created": 1, "completed": 2}}
    stopped = module.seen_message({**step, "error": {"name": "MessageAbortedError", "data": {"message": "Aborted"}}})
    failed = module.seen_message({**step, "error": {"name": "APIError", "data": {"message": "The engine broke off"}}})
    assert (stopped["error"], stopped["error_name"]) == ("Aborted", "MessageAbortedError")
    assert (failed["error"], failed["error_name"]) == ("The engine broke off", "APIError")
    assert module.seen_message(step)["error_name"] == ""
    assert "error_name" not in module.seen_message({**step, "role": "user"}), "the owner's message has no error"
