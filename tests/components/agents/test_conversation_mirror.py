"""Design 0023 §2 (decision 0139): the agent panel's conversation is read from the service's mirror, never from the
container at each read, run against the fake OpenCode with the bridge on this machine. The first read of a session
follows it (the watch told) and reads its history once, whole; after that, what the model writes reaches the
conversation through the watcher's lines alone: ten reads while a step streams start no process in the container, the
text comes whole (longer than the Monitor's brief), and the newest words are there. A session's older messages are
read from OpenCode once more only when a client asks for what the mirror does not hold."""

from pathlib import Path
from typing import Any

import pytest

from clank.components.agents.service import Agents
from clank.kernel.core import Kernel
from clank.kernel.processes import Answer
from tests.components.agents import test_monitor_sessions as shared
from tests.fakes.opencode import FakeOpenCode

kernel = shared.kernel  # the fixtures, found by their names
servers = shared.servers
until = shared.until

LONG = "The decay is exponential. " * 300  # 7,800 characters: more than the Monitor's brief of a part holds


def test_the_conversation_is_read_from_the_mirror_and_no_process_starts_after_the_history(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, flow = servers
    shared.watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    platform = kernel.parts["workspaces"].platform
    inside = platform.inside
    started: list[list[str]] = []

    def counted(argv: list[str], given: bytes | None) -> Answer:
        started.append(argv[2:])
        answer: Answer = inside(argv, given)
        return answer

    platform.inside = counted
    agents: Agents = kernel.parts["agents"]
    first = agents.conversation(str(tmp_path))
    assert first["session"] is not None
    assert first["session"]["id"] == "ses_plan"
    assert [m["info"]["id"] for m in first["messages"]][-1] == "msg_05", (
        "the history's newest page (msg_06 comes with a step)"
    )
    assert started[-1][:2] == ["page", str(first["session"]["port"])]
    assert "--whole" in started[-1]
    assert [each[0] for each in started].count("servers") <= 1, "the sessions listed once, until the watcher says them"
    assert len(started) <= 2
    after_history = len(started)

    flow.replay("a step")  # msg_06 and its parts, as OpenCode sends them: the message first, then its parts
    flow.feed(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_plan",
                "part": {
                    "id": "prt_long",
                    "sessionID": "ses_plan",
                    "messageID": "msg_06",
                    "type": "text",
                    "text": LONG,
                },
            },
        }
    )
    flow.feed(
        {
            "type": "message.part.delta",
            "properties": {
                "sessionID": "ses_plan",
                "messageID": "msg_06",
                "partID": "prt_long",
                "field": "text",
                "delta": " Done.",
            },
        }
    )

    def long_part() -> dict[str, Any] | None:
        found = agents.conversation(str(tmp_path))
        parts = [p for m in found["messages"] for p in m["parts"] if p.get("id") == "prt_long"]
        return parts[0] if parts and parts[0]["text"].endswith("Done.") else None

    part = until(long_part)
    assert part["text"] == LONG + " Done.", "whole, with the words as they were written"
    assert part["whole"] is True
    for _ in range(10):
        agents.conversation(str(tmp_path))
    assert len(started) == after_history, f"a read started a process: {started[after_history:]}"
    assert agents.mirror.followed("paper") == ["ses_plan"]

    older = agents.conversation(str(tmp_path), before=first["messages"][0]["info"]["id"], limit=5)
    assert older["session"] is not None
    assert len(started) <= after_history + 1, "what the mirror does not hold is read once"
    assert all(m["info"]["id"] not in {x["info"]["id"] for x in first["messages"]} for m in older["messages"])
