"""Design 0001 §6 (the Requests page, 2026-10-15): the gateway's kept requests are read back newest first, across the
days' files and from each file's end, each in brief (who asked, its status, its tokens in, cached and out, its first
token, total time and speed, the start of what was asked); one is found by its id with what was asked (the last
message the user wrote) and what was answered. A line still being written is skipped. Design 0004 §2: a request the
loop guard stopped says so in brief. Design 0012 §3: a record in brief names its session and its parent, from the
headers it kept."""

import json
from pathlib import Path
from typing import Any

from clank.components.gateway import records
from clank.components.gateway.records import find, recent


def record(id: str, time: str, *, asked: str = "Plot the code dimension", out: int = 600) -> dict[str, Any]:
    return {
        "id": id, "time": time, "client": "172.18.0.3", "headers": {"user-agent": "opencode/1.19.0"},
        "role": "agent", "stream": True, "slot": "main", "preset": "daily-262k", "engine": "kvmem-llamacpp v0.16",
        "model_sent": "qwen3.8-27b", "notes": "", "wait_ms": 2.0, "status": 200,
        "request": {"model": "agent", "max_tokens": 16384, "tools": [{}, {}],
                    "messages": [{"role": "system", "content": "be useful"},
                                 {"role": "user", "content": [{"type": "text", "text": asked}]},
                                 {"role": "tool", "content": "42"}]},
        "first_token_ms": 1000.0, "total_ms": 11000.0, "answer": "Saved runs/figures/plot.png",
        "usage": {"prompt_tokens": 20000, "prompt_cache_hit_tokens": 19000, "completion_tokens": out},
    }  # fmt: skip


def write(folder: Path, day: str, rows: list[dict[str, Any]], tail: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row) + "\n" for row in rows) + tail
    (folder / f"{day}.jsonl").write_text(text, encoding="utf-8")


def test_the_newest_requests_come_first_across_days_each_in_brief(tmp_path: Path) -> None:
    write(tmp_path, "2026-10-14", [record("r-1", "2026-10-14T20:00:00Z"), record("r-2", "2026-10-14T21:00:00Z")])
    write(tmp_path, "2026-10-15", [record("r-3", "2026-10-15T01:00:00Z", out=0)], tail='{"id": "r-4", "ti')
    found = recent(tmp_path, 10)
    assert [row["id"] for row in found] == ["r-3", "r-2", "r-1"], "the half-written line is skipped"
    brief = found[1]
    assert (brief["client"], brief["role"], brief["status"]) == ("opencode", "agent", 200)
    assert (brief["prompt_tokens"], brief["cached_tokens"], brief["completion_tokens"]) == (20000, 19000, 600)
    assert brief["per_second"] == 60.0, "600 tokens in the 10 s after the first"
    assert (brief["messages"], brief["tools"]) == (3, 2)
    assert brief["asked_start"] == "Plot the code dimension"
    assert found[0]["per_second"] is None
    assert [row["id"] for row in recent(tmp_path, 2)] == ["r-3", "r-2"]


def test_a_request_the_loop_guard_stopped_says_so_in_brief(tmp_path: Path) -> None:
    looped = "its tool call bash repeated itself (…)"
    stopped = {**record("r-9", "2026-10-18T16:04:17Z"), "looped": looped,
               "error": f"Clank's loop guard stopped the answer: {looped}; ask again"}  # fmt: skip
    write(tmp_path, "2026-10-18", [record("r-8", "2026-10-18T16:03:57Z"), stopped])
    found = recent(tmp_path, 5)
    assert [(row["id"], row["looped"]) for row in found] == [("r-9", True), ("r-8", False)]
    assert found[0]["error"].startswith("Clank's loop guard stopped the answer")


def test_a_long_day_is_read_from_its_end_in_pieces(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(records, "CHUNK", 300)  # a record is longer than a piece: lines cross the pieces' edges
    write(tmp_path, "2026-10-15", [record(f"r-{n}", f"2026-10-15T01:{n:02d}:00Z") for n in range(30)])
    assert [row["id"] for row in recent(tmp_path, 30)] == [f"r-{n}" for n in reversed(range(30))]


def test_one_request_is_found_with_what_was_asked_and_answered(tmp_path: Path) -> None:
    write(tmp_path, "2026-10-15", [record("r-7", "2026-10-15T01:00:00Z", asked="Make the figure, please")])
    found = find(tmp_path, "r-7")
    assert found is not None
    assert found["asked"] == "Make the figure, please"
    assert found["answer"] == "Saved runs/figures/plot.png"
    assert (found["model_sent"], found["max_tokens"]) == ("qwen3.8-27b", 16384)
    assert find(tmp_path, "r-8") is None
    assert recent(tmp_path / "none", 5) == []


def test_a_record_in_brief_names_its_session_and_its_parent(tmp_path: Path) -> None:
    child = record("r-2", "2026-10-19T01:00:01Z")
    child["headers"] = {**child["headers"], "x-session-id": "ses_child", "x-parent-session-id": "ses_root"}
    write(tmp_path, "2026-10-19", [record("r-1", "2026-10-19T01:00:00Z"), child])
    found = recent(tmp_path, 5)
    assert [(row["id"], row["session"], row["parent"]) for row in found] == [
        ("r-2", "ses_child", "ses_root"),
        ("r-1", "", ""),
    ], "a record that names no session (completion, or one kept before) names none"
    shown = find(tmp_path, "r-2")
    assert shown is not None
    assert (shown["session"], shown["parent"]) == ("ses_child", "ses_root")
