"""Design 0012 §3, §5.1 and §6.1 (§11 step 4) and design 0013 §5 and §7: the bridge's watch forwards the Monitor's
events, run on this machine against a fake OpenCode server replaying a synthetic session's events
(`tests/fixtures/opencode/1.19.0/session.json`).

The watch says each session's status (those busy when a server is first followed too), its sessions with their
subagents, each message and part in the Monitor's shape, the todo list, compactions, errors, questions and an instance
that ended; what a burst changes many times is said once, with its last state, a value that changed again said after
what came before it; the text as it is written comes only for the sessions the service says are shown, joined per
part. The review's lines, and the questions, their answers and an instance that ended, still come at once, after what
the burst held. A stream opened again (OpenCode's instance started again) says idle for a session that no longer runs.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections import Counter
from typing import Any

from clank.components.workspaces.sandbox import image_folder
from clank.kernel.processes import background_flags
from tests.fakes.opencode import FakeOpenCode

BRIDGE = image_folder() / "bridge.py"
BURST = "0.5,5"  # quiet for half a second, at most five: a busy machine does not split a test's burst


class Watching:
    """The bridge's `watch`, run on this machine; the lines it writes, read as they come."""

    def __init__(self, ports: str, burst: str = BURST, timeout: str = "10", quiet: str = "120") -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=background_flags(),
            env={**os.environ, "CLANK_BRIDGE_PORTS": ports, "CLANK_BRIDGE_BURST": burst,
                 "CLANK_BRIDGE_TIMEOUT": timeout, "CLANK_BRIDGE_QUIET": quiet},
        )  # fmt: skip
        self.lines: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            self.lines.put(json.loads(raw))

    def until(self, kind: str) -> list[dict[str, Any]]:
        """The lines up to the next of this type, that one included (the alive ones left out); fails after ten
        seconds."""
        found: list[dict[str, Any]] = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(deadline - time.monotonic(), 0.01))
            except queue.Empty:
                break
            if line["type"] != "alive":
                found.append(line)
            if line["type"] == kind:
                return found
        raise AssertionError(f"the watcher said no {kind} line; it said {found}")

    def burst(self, quiet: float = 2.0) -> list[dict[str, Any]]:
        """The lines that come before the watch is quiet for `quiet` seconds (the alive ones left out)."""
        found: list[dict[str, Any]] = []
        while True:
            try:
                line = self.lines.get(timeout=quiet if found else 10)
            except queue.Empty:
                return found
            if line["type"] != "alive":
                found.append(line)

    def tell(self, line: dict[str, Any]) -> None:
        """A line on the watch's input, as the service writes one."""
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(line) + "\n").encode())
        self.process.stdin.flush()

    def end(self) -> int:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.close()
        ended = self.process.wait(timeout=10)
        self.reader.join(timeout=10)
        self.process.stdout.close()
        return ended


def keyed(lines: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    """How many lines of each type said each thing (a part, a message, a session)."""

    def said(line: dict[str, Any]) -> str:
        for field in ("part", "message", "session"):
            value = line.get(field)
            if isinstance(value, dict):
                return str(value.get("id"))
        return str(line.get("session"))

    return Counter((line["type"], said(line)) for line in lines)


def test_the_watch_says_each_thing_a_step_changes_once_per_burst_with_its_last_state() -> None:
    with FakeOpenCode() as fake:
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            watching.until("synced")
            fake.replay("a step")
            lines = watching.burst()
            assert set(keyed(lines).values()) == {1}, f"each thing said once: {keyed(lines)}"
            parts = {line["part"]["id"]: line["part"] for line in lines if line["type"] == "part"}
            assert list(parts) == ["prt_06a", "prt_06b", "prt_06c", "prt_06d", "prt_06e"]
            assert parts["prt_06b"]["text"] == "The figure is saved; now the todo list says to check the axis."
            assert (parts["prt_06c"]["status"], parts["prt_06c"]["exit"]) == ("completed", 0)
            assert parts["prt_06e"]["tokens"]["cache"]["read"] == 12_800
            [message] = [line for line in lines if line["type"] == "message"]
            assert (message["port"], message["session"], message["message"]["finish"]) == (
                fake.port,
                "ses_plan",
                "stop",
            )
            statuses = {line["session"]: line["status"] for line in lines if line["type"] == "status"}
            assert statuses == {"ses_plan": "idle", "ses_child2": "idle"}
            kinds = [line["type"] for line in lines]
            assert kinds[-1] == "status", "a status that went busy, then idle, is said after the step's parts"
            [todo] = [line for line in lines if line["type"] == "todo"]
            assert [each["status"] for each in todo["todos"]] == ["completed", "in_progress"], "the last revision"
            sessions = {line["session"]["id"]: line["session"] for line in lines if line["type"] == "session"}
            assert sessions["ses_plan"]["title"] == "Plot tau against p (n=8)"
            assert sessions["ses_child2"]["parent"] == "ses_plan", "a subagent comes with its parent"
            assert "delta" not in kinds, "no session is shown"
        finally:
            assert watching.end() == 0


def test_the_watch_says_retries_compactions_removals_errors_questions_and_an_instance_that_ended() -> None:
    with FakeOpenCode() as fake:
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            watching.until("synced")
            fake.replay("retrying")
            [retry] = watching.burst()
            assert retry == {"type": "status", "port": fake.port, "session": "ses_plan", "status": "retry",
                             "attempt": 2, "message": "Provider is overloaded", "next": retry["next"]}  # fmt: skip
            fake.replay("compacted")
            compacted, message, part, error = watching.burst()
            assert compacted == {"type": "compacted", "port": fake.port, "session": "ses_plan"}
            assert (message["type"], message["message"], message.get("part")) == ("removed", "msg_05", None)
            assert (part["type"], part["message"], part["part"]) == ("removed", "msg_03", "prt_03d")
            assert (error["type"], error["error"]) == ("error", "The engine broke off")
            fake.replay("a question")
            question = watching.until("question")[-1]
            assert (question["request"]["id"], question["request"]["session"]) == ("que_01", "ses_plan")
            fake.replay("answered")
            replied, rejected = watching.until("answered"), watching.until("answered")
            assert (replied[-1]["request"], replied[-1]["reply"]) == ("que_01", "replied")
            assert (rejected[-1]["request"], rejected[-1]["reply"]) == ("que_02", "rejected")
            fake.replay("disposed")
            assert watching.until("disposed")[-1] == {"type": "disposed", "port": fake.port}
        finally:
            assert watching.end() == 0


def test_compactions_removals_and_errors_said_again_in_a_burst_are_said_once_with_the_last() -> None:
    with FakeOpenCode() as fake:
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            watching.until("synced")
            burst = fake.store.bursts["compacted"]
            again = json.loads(json.dumps(burst))
            again[-1]["properties"]["error"]["data"]["message"] = "The engine broke off again"
            fake.feed(*burst, *again)
            lines = watching.burst()
            assert [line["type"] for line in lines] == ["compacted", "removed", "removed", "error"]
            assert lines[-1]["error"] == "The engine broke off again"
        finally:
            assert watching.end() == 0


def test_asks_questions_answers_and_an_instance_that_ended_come_at_once_after_what_the_burst_held() -> None:
    """Design 0007 §4 and design 0012 §6.1: only the Monitor's lines wait for a burst's end; an ask or a question waits
    for nobody, and what the burst held before it comes first, so the order of what happened is kept."""
    with FakeOpenCode() as fake:
        watching = Watching(f"{fake.port}-{fake.port}", burst="6,30")  # a burst said six seconds after its last line
        try:
            watching.until("synced")
            ask = {"id": "per_9", "sessionID": "ses_plan", "permission": "bash", "patterns": ["ls"]}
            busy = {"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "busy"}}}
            for kind, events in (
                ("asked", [{"type": "permission.asked", "properties": ask}]),
                ("question", fake.store.bursts["a question"]),
                ("answered", fake.store.bursts["answered"][:1]),
                ("disposed", fake.store.bursts["disposed"]),
            ):
                started = time.monotonic()
                fake.feed(busy, *events)
                lines = watching.until(kind)
                assert time.monotonic() - started < 4, f"{kind} waited for the burst's end"
                assert [line["type"] for line in lines] == ["status", kind], "what the burst held comes first"
        finally:
            assert watching.end() == 0


def test_a_stream_opened_again_says_idle_for_a_session_that_no_longer_runs() -> None:
    """Design 0012 §3 and design 0013 §7: OpenCode's instance started again (its stream ends, its server still
    listens); a run that ended with it is not left busy, or a flow waiting for the session to be idle would wait
    forever."""
    with FakeOpenCode() as fake:
        fake.status = {"ses_plan": {"type": "busy"}, "ses_other": {"type": "busy"}}
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            first = watching.until("synced")
            assert {line["session"]: line["status"] for line in first if line["type"] == "status"} == {
                "ses_plan": "busy", "ses_other": "busy",
            }  # fmt: skip
            fake.replay("disposed")
            watching.until("disposed")
            fake.status = {"ses_other": {"type": "busy"}}
            fake.restart()
            lines = watching.burst()
            assert {line["session"]: line["status"] for line in lines if line["type"] == "status"} == {
                "ses_plan": "idle", "ses_other": "busy",
            }  # fmt: skip
        finally:
            assert watching.end() == 0


def test_a_stream_still_open_after_its_instance_ended_is_opened_again_and_hears_what_follows() -> None:
    """Design 0012 §3 and design 0013 §7: OpenCode 1.19 keeps a stream open after its instance ended but sends nothing
    more on it (measured 2026-10-22: a flow's server went silent to the watch for a whole run, so the runner waited for
    each box's time limit after the box had ended). The watch opens the stream again: a run that ended meanwhile is
    said idle, and what the new instance does is heard."""
    with FakeOpenCode() as fake:
        fake.status = {"ses_plan": {"type": "busy"}}
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            watching.until("synced")
            fake.status = {}
            fake.dispose()
            watching.until("disposed")
            lines = watching.burst()
            assert {line["session"]: line["status"] for line in lines if line["type"] == "status"} == {
                "ses_plan": "idle"
            }, "the stream opened again finds the run ended"
            fake.replay("a question")
            assert watching.until("question")[-1]["type"] == "question", "the new instance's events are heard"
        finally:
            assert watching.end() == 0


def test_a_stream_that_never_says_it_is_connected_is_opened_again() -> None:
    """Design 0012 §3 and design 0013 §7: a stream opened while OpenCode 1.19 starts says nothing at all, ever (measured
    2026-10-22: the watch follows a flow's new server within two seconds of it listening, and heard none of the run).
    The watch waits a moment for the stream to say it is connected, and opens it again when it does not."""
    with FakeOpenCode() as fake:
        fake.deaf = 1
        fake.status = {"ses_plan": {"type": "busy"}}
        watching = Watching(f"{fake.port}-{fake.port}", timeout="1")
        try:
            lines = watching.until("synced")
            if not any(line["type"] == "status" for line in lines):
                lines += watching.until("status")  # said once the stream opened again
            assert {line["session"]: line["status"] for line in lines if line["type"] == "status"} == {
                "ses_plan": "busy"
            }
            fake.replay("a question")
            assert watching.until("question")[-1]["type"] == "question", "the stream opened again hears it"
        finally:
            assert watching.end() == 0


def test_a_stream_quiet_for_a_while_is_opened_again_and_says_what_ended_meanwhile() -> None:
    """A stream that went silent some other way: the watch opens it again after `CLANK_BRIDGE_QUIET` seconds without a
    line, and a run that ended meanwhile is said idle."""
    with FakeOpenCode() as fake:
        fake.status = {"ses_plan": {"type": "busy"}}
        watching = Watching(f"{fake.port}-{fake.port}", quiet="2")
        try:
            watching.until("synced")
            fake.status = {}
            fake.dispose_silently()
            lines = watching.burst(quiet=6)
            assert {line["session"]: line["status"] for line in lines if line["type"] == "status"} == {
                "ses_plan": "idle"
            }
        finally:
            assert watching.end() == 0


def test_a_server_first_followed_says_its_busy_sessions_and_its_waiting_questions() -> None:
    """Design 0012 §3: the service knows which server runs each session from the moment its watch starts."""
    servers = FakeOpenCode.several(2)
    window, flow = servers
    try:
        flow.status = {"ses_plan": {"type": "busy"}}
        window.status = {"ses_other": {"type": "retry", "attempt": 1, "message": "overloaded", "next": 5}}
        flow.questions = [{"id": "que_9", "sessionID": "ses_plan", "questions": [{"question": "Which n?"}]}]
        watching = Watching(f"{window.port}-{flow.port}")
        try:
            lines = watching.until("synced")
            statuses = {(line["port"], line["session"]): line["status"] for line in lines if line["type"] == "status"}
            assert statuses == {(flow.port, "ses_plan"): "busy", (window.port, "ses_other"): "retry"}
            [question] = [line for line in lines if line["type"] == "question"]
            assert (question["port"], question["request"]["id"]) == (flow.port, "que_9")
        finally:
            assert watching.end() == 0
    finally:
        for each in servers:
            each.close()


def test_a_shown_sessions_text_comes_as_it_is_written_joined_per_part_and_no_other_sessions() -> None:
    """Design 0012 §6.1: deltas only for the session the page shows, in batches."""
    with FakeOpenCode() as fake:
        watching = Watching(f"{fake.port}-{fake.port}")
        try:
            watching.until("synced")
            fake.replay("a step")
            assert "delta" not in [line["type"] for line in watching.burst()], "nothing shown: no text as it is written"
            watching.tell({"shown": ["ses_plan"]})
            assert watching.until("shown")[-1] == {"type": "shown", "sessions": ["ses_plan"]}
            fake.replay("a step")
            lines = watching.burst()
            deltas = [line for line in lines if line["type"] == "delta"]
            assert [(line["part"], line["field"], line["text"]) for line in deltas] == [
                ("prt_06b", "text", "The figure is saved; now the todo list says to check the axis."),
                ("prt_06d", "text", "The axis is right."),
            ], "joined per part, and nothing of the session not shown"
            assert {(line["port"], line["session"], line["message"]) for line in deltas} == {(fake.port, "ses_plan",
                                                                                              "msg_06")}  # fmt: skip
            said = [(line["type"], line["part"] if line["type"] == "delta" else (line.get("part") or {}).get("id"))
                    for line in lines]  # fmt: skip
            assert said.index(("delta", "prt_06b")) < said.index(("part", "prt_06b")), "the text before its part's end"
            watching.tell({"shown": []})
            assert watching.until("shown")[-1]["sessions"] == []
            fake.replay("a step")
            assert "delta" not in [line["type"] for line in watching.burst()]
        finally:
            assert watching.end() == 0
