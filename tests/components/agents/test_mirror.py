"""Design 0023 §2 (decision 0139): the mirror the service keeps of the sessions clients follow, built from the watchers'
lines alone. A followed session's messages and parts are assembled from `message`, `part` and `delta` lines (a delta
appends to its part's text, a part line replaces the part whole, a removal takes a message or a part away), its status
from `status` lines, and the permissions and questions open from `asked`, `replied`, `question` and `answered`; a
session not followed leaves nothing. Its history merges once; a page from memory names the message to read before,
and the cursor OpenCode gave for what the mirror does not hold. The sessions a workspace's watcher saw are known,
newest first. The mirror is bounded: past `FULL_BYTES` the oldest parts' text falls back to its brief, and a session no
client read for `FORGET_MINUTES` is forgotten."""

from typing import Any

import pytest

from clank.components.agents import mirror as mirror_module
from clank.components.agents.mirror import FORGET_MINUTES, Mirror

W = "paper"
S = "ses_plan"


def session_line(id: str = S, title: str = "A plan", updated: int = 10, parent: str | None = None,
                 deleted: bool = False, port: int = 4096) -> dict[str, Any]:  # fmt: skip
    return {"type": "session", "port": port, "deleted": deleted, "session": {
        "id": id, "parent": parent, "title": title, "created": 1, "updated": updated, "revert": {}, "compacting": False,
    }}  # fmt: skip


def message_line(id: str, role: str, created: int, session: str = S) -> dict[str, Any]:
    return {"type": "message", "port": 4096, "session": session, "message": {
        "id": id, "session": session, "role": role, "agent": "build", "created": created, "completed": None,
    }}  # fmt: skip


def part_line(id: str, message: str, text: str, kind: str = "text", session: str = S) -> dict[str, Any]:
    return {"type": "part", "port": 4096, "session": session, "part": {
        "id": id, "message": message, "type": kind, "text": text, "length": len(text), "whole": True,
    }}  # fmt: skip


def delta_line(part: str, message: str, text: str, session: str = S) -> dict[str, Any]:
    return {"type": "delta", "port": 4096, "session": session, "message": message, "part": part, "field": "text",
            "text": text}  # fmt: skip


def status_line(status: str, session: str = S) -> dict[str, Any]:
    return {"type": "status", "port": 4096, "session": session, "status": status}


def test_a_followed_sessions_messages_and_parts_are_assembled_from_the_watchers_lines() -> None:
    mirror = Mirror()
    mirror.heard(W, session_line())
    mirror.heard(W, message_line("msg_01", "user", 100))
    assert mirror.conversation(W, S, 30) is None, "not followed: nothing kept"
    mirror.follow(W, S)
    mirror.merge(W, S, {"messages": [], "next": ""})
    before = mirror.version(W, S)
    mirror.heard(W, status_line("busy"))
    mirror.heard(W, message_line("msg_02", "user", 200))
    mirror.heard(W, message_line("msg_03", "assistant", 300))
    mirror.heard(W, delta_line("prt_03b", "msg_03", "The "))
    mirror.heard(W, delta_line("prt_03b", "msg_03", "figure"))
    mirror.heard(W, part_line("prt_03a", "msg_03", "thinking…", kind="reasoning"))
    mirror.heard(W, {"type": "part", "port": 4096, "session": "ses_other", "part": {
        "id": "prt_x", "message": "msg_x", "type": "text", "text": "elsewhere", "length": 9}})  # fmt: skip
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert [m["info"]["id"] for m in found["messages"]] == ["msg_02", "msg_03"], "in time order; msg_01 came before"
    [reasoning, text] = found["messages"][1]["parts"]
    assert (reasoning["type"], reasoning["text"]) == ("reasoning", "thinking…")
    assert (text["type"], text["text"], text["length"]) == ("text", "The figure", 10), "deltas appended, in order"
    assert found["busy"] is True
    assert found["title"] == "A plan"
    assert mirror.version(W, S) > before
    mirror.heard(W, part_line("prt_03b", "msg_03", "The figure is saved."))
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert found["messages"][1]["parts"][1]["text"] == "The figure is saved.", "a part line replaces the part whole"
    mirror.heard(W, {"type": "removed", "port": 4096, "session": S, "message": "msg_03", "part": "prt_03a"})
    mirror.heard(W, status_line("idle"))
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert [p["id"] for p in found["messages"][1]["parts"]] == ["prt_03b"]
    assert found["busy"] is False
    mirror.heard(W, {"type": "removed", "port": 4096, "session": S, "message": "msg_03"})
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert [m["info"]["id"] for m in found["messages"]] == ["msg_02"]


def test_history_merges_once_and_older_pages_come_from_memory_then_from_opencodes_cursor() -> None:
    mirror = Mirror()
    mirror.follow(W, S)
    assert mirror.conversation(W, S, 30) is None, "followed, its history not read yet"
    page = {"messages": [
        {"info": {"id": f"msg_0{n}", "role": "user" if n % 2 else "assistant", "created": n * 100}, "parts": [
            {"id": f"prt_0{n}", "message": f"msg_0{n}", "type": "text", "text": f"m{n}", "length": 2, "whole": True}]}
        for n in (2, 3, 4)
    ], "next": "cursor-before-2"}  # fmt: skip
    mirror.merge(W, S, page)
    newest = mirror.conversation(W, S, 2)
    assert newest is not None
    assert [m["info"]["id"] for m in newest["messages"]] == ["msg_03", "msg_04"]
    assert newest["next"] == "msg_03", "the message to read before"
    assert newest["from_opencode"] == "", "the mirror holds older ones itself"
    older = mirror.conversation(W, S, 2, before="msg_03")
    assert older is not None
    assert [m["info"]["id"] for m in older["messages"]] == ["msg_02"]
    assert older["next"] == "msg_02"
    assert older["from_opencode"] == "cursor-before-2", "what comes before msg_02 is OpenCode's to give, once"
    mirror.merge(W, S, {"messages": [
        {"info": {"id": "msg_01", "role": "user", "created": 100}, "parts": []}], "next": ""})  # fmt: skip
    first = mirror.conversation(W, S, 2, before="msg_02")
    assert first is not None
    assert [m["info"]["id"] for m in first["messages"]] == ["msg_01"]
    assert (first["next"], first["from_opencode"]) == ("", ""), "the session's first message"
    assert mirror.conversation(W, S, 10) is not None
    assert len(mirror.conversation(W, S, 10)["messages"]) == 4, "merged, not doubled"  # type: ignore[index]


def test_permissions_and_questions_open_are_those_asked_and_not_yet_answered() -> None:
    mirror = Mirror()
    mirror.follow(W, S)
    mirror.merge(W, S, {"messages": [], "next": ""})
    mirror.heard(W, {"type": "asked", "port": 4096, "request": {
        "id": "per_1", "sessionID": S, "permission": "edit", "patterns": ["a.py"], "metadata": {"diff": "+x"}},
        "input": None})  # fmt: skip
    mirror.heard(W, {"type": "asked", "port": 4096, "request": {
        "id": "per_2", "sessionID": "ses_other", "permission": "bash", "patterns": ["rm"], "metadata": {}}})  # fmt: skip
    mirror.heard(W, {"type": "question", "port": 4096, "request": {"id": "que_1", "session": S, "questions": [
        {"question": "Which n?", "header": "n", "options": [{"label": "8"}]}]}})  # fmt: skip
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert found["waiting"] == {
        "permissions": [{"id": "per_1", "session": S, "permission": "edit", "patterns": ["a.py"],
                         "metadata": {"diff": "+x"}}],
        "questions": [{"id": "que_1", "session": S, "questions": [
            {"question": "Which n?", "header": "n", "options": [{"label": "8"}]}]}],
    }  # fmt: skip
    mirror.heard(W, {"type": "replied", "port": 4096, "request": "per_1", "session": S, "reply": "once"})
    mirror.heard(W, {"type": "answered", "port": 4096, "request": "que_1", "session": S, "reply": "replied"})
    found = mirror.conversation(W, S, 30)
    assert found is not None
    assert found["waiting"] == {"permissions": [], "questions": []}


def test_the_sessions_a_watcher_saw_are_known_newest_first_with_their_status_and_port() -> None:
    mirror = Mirror()
    assert mirror.sessions(W) == []
    mirror.heard(W, session_line("ses_a", "First", updated=10))
    mirror.heard(W, session_line("ses_b", "Second", updated=20, port=4097))
    mirror.heard(W, session_line("ses_c", "A subagent's", updated=30, parent="ses_b"))
    mirror.heard(
        W, {**status_line("busy", session="ses_b"), "port": 4097}
    )  # its status comes from the server that runs it
    assert mirror.sessions(W) == [
        {"id": "ses_b", "title": "Second", "parent": None, "created": 1, "updated": 20, "status": "busy",
         "port": 4097},
        {"id": "ses_a", "title": "First", "parent": None, "created": 1, "updated": 10, "status": "idle",
         "port": 4096},
    ], "root sessions, newest first; a subagent's beside them is not a root"  # fmt: skip
    assert mirror.port(W, "ses_c") == 4096
    mirror.heard(W, session_line("ses_a", "First", updated=10, deleted=True))
    assert [each["id"] for each in mirror.sessions(W)] == ["ses_b"]
    assert mirror.sessions("elsewhere") == []


def test_the_mirror_is_bounded_old_text_falls_back_to_its_brief_and_sessions_unread_are_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mirror_module, "FULL_BYTES", 43_000)  # five parts of 10,000; two cut to their brief fit
    now = [0.0]
    mirror = Mirror(clock=lambda: now[0])
    mirror.follow(W, S)
    mirror.merge(W, S, {"messages": [], "next": ""})
    for n in range(1, 6):
        mirror.heard(W, message_line(f"msg_0{n}", "assistant", n * 100))
        mirror.heard(W, part_line(f"prt_0{n}", f"msg_0{n}", "x" * 10_000))
    found = mirror.conversation(W, S, 10)
    assert found is not None
    texts = [m["parts"][0] for m in found["messages"]]
    assert [len(t["text"]) < 10_000 for t in texts] == [True, True, False, False, False], "the oldest fell back"
    assert texts[0]["length"] == 10_000, "its length still says what it was"
    assert texts[0].get("whole") is False
    assert texts[-1]["whole"] is True
    now[0] = FORGET_MINUTES * 60 - 1
    assert mirror.forget() == []
    now[0] = FORGET_MINUTES * 60 + 1
    assert mirror.forget() == [(W, S)], "no client read it for half an hour"
    assert mirror.conversation(W, S, 10) is None
    assert mirror.followed(W) == []
