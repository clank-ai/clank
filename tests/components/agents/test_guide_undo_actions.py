"""Design 0012 §9.1, §9.5 and §9.7 (§11 step 10), decisions 0056 and 0079: the Guide's Undo, Redo and Drop, run against
two fake OpenCode servers in one workspace's container (`tests/fakes/opencode.py`) with the bridge on this machine.

Undo sends OpenCode's `revert` at the last part of the step before the last, to the server that runs the session and no
other, and the flow shows it at once, from OpenCode's answer; undoing the turn names the owner's message and gives its
text back whole, read from OpenCode's newest page of the session (else the flow's words of it, said cut); Redo sends
`unrevert`; each action leaves an `agents.acted` event with who did it. An undo carries the revert the owner saw, and
one the session moved on from is refused and sends nothing. Drop writes the whole part back with its
`state.time.compacted` set, and the flow says "by you" with the tokens it freed once OpenCode says the result is
cleared; a drop of the step in progress sends nothing and says why. The routes offer Undo and Drop (of a call named),
act, and refuse with the Guide's reason. The session is found on its server however slowly that server's stream begins.
"""

import copy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.guide import Guide, GuideError
from clank.components.agents.sessions import SessionError
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents import test_monitor_sessions as shared
from tests.components.agents.test_guide_actions import AUTH, busy, idle, offered, ready, seen
from tests.fakes.opencode import FakeOpenCode, recorded
from tests.support.flowlines import finish, patch, step, text, tool, updated

kernel = shared.kernel  # the fixtures, found by their names
servers = shared.servers
until = shared.until

OWNER = Actor(kind="user", via="console")
PHONE = Actor(kind="device", via="phone")
STEP_3 = 1_760_900_240_000  # when the synthetic session's third step began (msg_05)
GUIDE = "/api/v1/agents/guide/paper/ses_plan"
LONG = "About step 3, `python check.py`: " + "there is no check.py, so skip it and go on with the figure. " * 8


def nodes(guide: Guide) -> dict[str, dict[str, Any]]:
    view = guide.flows.view("paper", "ses_plan") or {}
    return {node["id"]: node for node in view.get("nodes") or []}


def read(guide: Guide) -> None:
    """The keeper's round, as the service's own would run it: the session's history read through the bridge."""

    def done() -> bool:
        guide.flows.work()
        return "msg_02" in nodes(guide)

    until(done)


def said(server: FakeOpenCode, *messages: dict[str, Any]) -> None:
    """OpenCode stores these messages (each in place of one of its id) and says them on the stream."""
    with server.store.lock:
        stored = server.store.messages["ses_plan"]
        for message in messages:
            ids = [each["info"]["id"] for each in stored]
            if message["info"]["id"] in ids:
                stored[ids.index(message["info"]["id"])] = message
            else:
                stored.append(message)
    server.feed(*[event for message in messages for event in updated(message)])


def two_more_steps(server: FakeOpenCode) -> None:
    """The third step finishes with its text, and a fourth edits plot.py."""
    third = step("msg_05", "msg_04", STEP_3, [text("prt_05b", "Skipping the check; the figure is saved."),
                                              finish("prt_05c", "stop")], completed=STEP_3 + 10_000)  # fmt: skip
    fourth = step("msg_06", "msg_04", STEP_3 + 20_000, [tool("prt_06b", "edit", output="x" * 400), finish("prt_06c"),
                                                        patch("prt_06d", "/w/plot.py")],
                  completed=STEP_3 + 30_000)  # fmt: skip
    said(server, third, fourth)


def test_the_session_is_found_on_its_server_however_slowly_its_stream_begins(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy machine: each server's stream says it is connected, then its thread waits before it goes on; what the
    session says meanwhile still reaches the watcher, and the session is found on the server that runs it."""
    window, flow = servers
    window.connected_pause = flow.connected_pause = 1.0
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    assert guide.sessions.runs("paper", "ses_plan") == flow.port


def test_undo_reverts_at_the_previous_steps_last_part_on_the_server_that_runs_it(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    two_more_steps(flow)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"] and offered(guide, "undo")["mode"] == "step")
    undo = offered(guide, "undo")
    assert undo["revert"] == {"message": "msg_05", "part": "prt_05c"}, "the step before's last part, its text before"
    assert (undo["takes"]["steps"], undo["takes"]["files"]) == ([4], ["/w/plot.py"])
    answer = guide.undo("paper", "ses_plan", actor=OWNER, message="msg_05", part="prt_05c", steps=[4], said=[])
    assert (answer["state"], answer["mode"], answer["port"]) == ("undone", "step", flow.port)
    assert answer["revert"] == {"message": "msg_05", "part": "prt_05c"}, "what the console needs, not OpenCode's diff"
    assert flow.sent_to("/session/ses_plan/revert") == [{"messageID": "msg_05", "partID": "prt_05c"}]
    assert window.sent == [], "nothing reached the server that does not run the session"
    redo = offered(guide, "undo")
    assert (redo["mode"], redo["state"]["state"], redo["state"]["what"]) == ("redo", "undone", "step 4"), (
        "shown at once, from OpenCode's answer"
    )
    assert nodes(guide)["msg_06"]["undone"] is True


def test_undo_the_turn_names_your_message_and_gives_its_text_back(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    flow.store.messages["ses_plan"][3]["parts"][0]["text"] = LONG  # the owner's second message, longer than a brief
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"])
    undo = offered(guide, "undo")
    assert (undo["mode"], undo["revert"], undo["refused"]) == ("turn", {"message": "msg_04", "part": ""}, (
        "step 3 is the first after your message: undoing it alone would take back your message too"))  # fmt: skip
    assert undo["takes"]["text"].endswith("…"), "the flow keeps a message's words cut"
    answer = guide.undo("paper", "ses_plan", actor=OWNER, message="msg_04", steps=[3], said=["msg_04"])
    assert flow.sent_to("/session/ses_plan/revert") == [{"messageID": "msg_04"}], "the message alone: the whole turn"
    assert (answer["mode"], answer["text"], answer["whole"]) == ("turn", LONG, True), "read back from OpenCode"
    assert offered(guide, "undo")["state"]["state"] == "turn undone"
    guide.redo("paper", "ses_plan", actor=OWNER)

    def unread(*args: Any, **named: Any) -> Any:
        raise SessionError("the bridge did not answer")

    monkeypatch.setattr(guide.sessions, "page", unread)
    again = guide.undo("paper", "ses_plan", actor=OWNER, message="msg_04", steps=[3], said=["msg_04"])
    assert (again["text"], again["whole"]) == (undo["takes"]["text"], False), "else the flow's words, said cut"


def test_redo_unreverts_and_each_action_leaves_an_agents_acted_event(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"])
    guide.undo("paper", "ses_plan", actor=OWNER, message="msg_04", steps=[3], said=["msg_04"])
    redo = offered(guide, "undo")
    assert (redo["mode"], redo["title"], redo["calls"]) == ("redo", "Redo", ["POST /session/ses_plan/unrevert"])
    with pytest.raises(GuideError, match="an undo is pending"):
        guide.undo("paper", "ses_plan", actor=OWNER, message="msg_04", steps=[3], said=["msg_04"])
    answer = guide.redo("paper", "ses_plan", actor=PHONE)
    assert (answer["state"], answer["port"]) == ("redone", flow.port)
    assert [path for _, path, _ in flow.sent] == ["/session/ses_plan/revert", "/session/ses_plan/unrevert"]
    after = offered(guide, "undo")
    assert (after["mode"], after["state"]["state"], after["state"]["what"]) == (
        "turn", "redone", "your message and step 3"
    )  # fmt: skip
    with pytest.raises(GuideError, match="Redo cannot run now: nothing is undone"):
        guide.redo("paper", "ses_plan", actor=OWNER)
    guide.drop("paper", "ses_plan", "prt_02c", actor=OWNER)
    acted = kernel.events.after(0, types=["agents.acted"])
    assert [(event.data["action"], event.actor.describe()) for event in acted] == [
        ("undo", "you (console)"), ("redo", "device phone"), ("clear", "you (console)"),
    ]  # fmt: skip
    assert {event.data["port"] for event in acted} == {flow.port}


def test_an_undo_the_session_moved_on_from_is_refused_and_sends_nothing(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"])
    shown = offered(guide, "undo")["revert"]
    two_more_steps(flow)
    seen(guide, lambda: offered(guide, "undo")["revert"] != shown)
    with pytest.raises(GuideError, match="the session moved on since you looked: Undo would now take back step 4"):
        guide.undo(
            "paper", "ses_plan", actor=OWNER, message=shown["message"], part=shown["part"], steps=[], said=["msg_04"]
        )
    busy(flow)
    seen(guide, lambda: not offered(guide, "undo")["can"])
    with pytest.raises(GuideError, match=r"Undo cannot run now: the session works: stop it first \(\.\)"):
        guide.undo("paper", "ses_plan", actor=OWNER, message="msg_05", part="prt_05c", steps=[4], said=[])
    assert flow.sent == []
    assert window.sent == []
    assert kernel.events.after(0, types=["agents.acted"]) == []


def test_drop_sends_the_whole_part_with_its_time_compacted_and_the_flow_says_by_you(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    seen(guide, lambda: offered(guide, "drop")["can"])
    found = next(each for each in guide.offer("paper", "ses_plan", item="prt_02c")["actions"]
                 if each["action"] == "drop")  # fmt: skip
    assert (found["can"], found["item"]["step"], found["item"]["freed"]) == (True, 1, 887), "2,958 characters at 0.3"
    answer = guide.drop("paper", "ses_plan", "prt_02c", actor=OWNER)
    assert (answer["state"], answer["port"], answer["item"]["message"]) == ("cleared", flow.port, "msg_02")
    [sent] = flow.sent_to("/session/ses_plan/message/msg_02/part/prt_02c")
    part = copy.deepcopy(
        next(each for each in recorded()["messages"]["ses_plan"][1]["parts"] if each["id"] == "prt_02c")
    )
    compacted = sent["state"]["time"]["compacted"]
    part["state"]["time"]["compacted"] = compacted
    assert (sent, isinstance(compacted, int)) == (part, True), "the whole part, its time compacted set"
    assert window.sent == []
    assert offered(guide, "drop")["state"]["state"] == "clearing", "until OpenCode says it is cleared"
    flow.feed({"type": "message.part.updated", "properties": {"sessionID": "ses_plan", "part": sent}})
    seen(guide, lambda: nodes(guide)["prt_02c"]["cleared"])
    call = nodes(guide)["prt_02c"]
    assert (call["cleared_by"], call["freed"]) == ("you", 887)
    assert offered(guide, "drop")["state"]["state"] == "cleared"


def test_a_drop_of_the_step_in_progress_sends_nothing_and_says_why(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    working = step("msg_05", "msg_04", STEP_3, [text("prt_05b", "Reading the figure."),
                                                tool("prt_05e", "read", output="y" * 80)])  # fmt: skip
    said(flow, working)
    seen(guide, lambda: "prt_05e" in nodes(guide))
    with pytest.raises(GuideError, match="Drop cannot run now: it is in the step in progress"):
        guide.drop("paper", "ses_plan", "prt_05e", actor=OWNER)
    with pytest.raises(GuideError, match="no tool call prt_gone in the session's flow"):
        guide.drop("paper", "ses_plan", "prt_gone", actor=OWNER)
    with pytest.raises(GuideError, match="Drop names the call whose result it clears"):
        guide.drop("paper", "ses_plan", "", actor=OWNER)
    assert flow.sent == []
    assert window.sent == []
    assert kernel.events.after(0, types=["agents.acted"]) == []


def test_the_routes_offer_undo_and_drop_act_and_refuse_with_the_reason(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"])
    said = flow.store.messages["ses_plan"][3]["parts"][0]["text"]
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        found = http.get(f"{GUIDE}?item=prt_02c", headers=AUTH).json()
        drop = next(each for each in found["actions"] if each["action"] == "drop")
        assert (drop["item"]["part"], drop["item"]["freed"]) == ("prt_02c", 887)
        moved = http.post(
            f"{GUIDE}/undo", json={"message": "msg_03", "part": "prt_03e", "steps": [3], "said": []}, headers=AUTH
        )
        assert (moved.status_code, "moved on since you looked" in moved.json()["error"]["message"]) == (409, True)
        assert http.post(f"{GUIDE}/undo", json={}, headers=AUTH).status_code == 422, "the revert confirmed is named"
        undone = http.post(f"{GUIDE}/undo", json={"message": "msg_04", "steps": [3], "said": ["msg_04"]},
                           headers=AUTH)  # fmt: skip
        assert (undone.status_code, undone.json()["mode"], undone.json()["text"]) == (200, "turn", said)
        assert http.post(f"{GUIDE}/redo", headers=AUTH).json()["state"] == "redone"
        assert http.post(f"{GUIDE}/drop", json={"part": "prt_02c"}, headers=AUTH).json()["state"] == "cleared"
        refused = http.post(f"{GUIDE}/drop", json={"part": "prt_gone"}, headers=AUTH)
        assert (refused.status_code, "no tool call prt_gone" in refused.json()["error"]["message"]) == (409, True)
    assert [path for _, path, _ in flow.sent] == [
        "/session/ses_plan/revert", "/session/ses_plan/unrevert", "/session/ses_plan/message/msg_02/part/prt_02c"
    ]  # fmt: skip


def test_an_undo_that_names_no_revert_is_refused_and_sends_nothing(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["can"])
    with pytest.raises(GuideError, match="Undo names the revert you confirmed"):
        guide.undo("paper", "ses_plan", actor=OWNER, message="", steps=[], said=[])
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        empty = http.post(f"{GUIDE}/undo", json={"message": "", "steps": [], "said": []}, headers=AUTH)
        assert empty.status_code == 422, "never what is offered now, unseen"
    assert flow.sent == []


def test_an_undo_that_would_now_take_back_more_than_it_showed_is_refused(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)
    third = step("msg_05", "msg_04", STEP_3, [text("prt_05b", "Skipping the check."), finish("prt_05c", "stop")],
                 completed=STEP_3 + 10_000)  # fmt: skip
    thinks = step("msg_06", "msg_04", STEP_3 + 20_000, [text("prt_06b", "Hmm.", "reasoning"), finish("prt_06c")],
                  completed=STEP_3 + 30_000)  # fmt: skip
    said(flow, third, thinks)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["takes"]["steps"] == [4])
    shown = offered(guide, "undo")
    assert shown["revert"] == {"message": "msg_05", "part": "prt_05c"}
    edits = step("msg_07", "msg_04", STEP_3 + 40_000, [tool("prt_07b", "edit"), finish("prt_07c")],
                 completed=STEP_3 + 50_000)  # fmt: skip
    said(flow, edits)
    seen(guide, lambda: offered(guide, "undo")["takes"]["steps"] == [4, 5])
    assert offered(guide, "undo")["revert"] == shown["revert"], "the same cut, which now takes back step 5 too"
    with pytest.raises(GuideError, match="the session moved on since you looked: Undo would now take back steps 4"):
        guide.undo("paper", "ses_plan", actor=OWNER, message="msg_05", part="prt_05c", steps=[4], said=[])
    assert flow.sent == []
    answer = guide.undo("paper", "ses_plan", actor=OWNER, message="msg_05", part="prt_05c", steps=[4, 5], said=[])
    assert (answer["revert"], answer["why"]) == ({"message": "msg_05", "part": "prt_05c"}, ""), (
        "OpenCode kept the cut: at step 5's own last part, nothing but thinking before it, it would take the turn"
    )


def test_the_fake_opencode_reverts_as_opencode_does(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As read in OpenCode's `session/revert.ts` (1.18.31's program, to confirm against 1.19.0): a revert at a part with
    no text or tool part before it in its message is a revert from the owner's last message; a busy session is not
    reverted; the owner's next message keeps the cut message, without its parts from the cut on, and removes the
    messages after it."""
    window, flow = servers
    sessions = shared.watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    busy(flow)
    until(lambda: sessions.runs("paper", "ses_plan") == flow.port)
    assert sessions.revert("paper", flow.port, "ses_plan", "msg_05", "prt_05b", actor=OWNER)["messageID"] == "msg_04", (
        "only a step-start before the text: the whole turn"
    )
    sessions.unrevert("paper", flow.port, "ses_plan", actor=OWNER)
    kept = sessions.revert("paper", flow.port, "ses_plan", "msg_03", "prt_03e", actor=OWNER)
    assert (kept["messageID"], kept["partID"]) == ("msg_03", "prt_03e"), "calls before the finish: the cut stays"
    flow.status["ses_plan"] = {"type": "busy"}
    with pytest.raises(SessionError):
        sessions.unrevert("paper", flow.port, "ses_plan", actor=OWNER)
    with pytest.raises(SessionError):
        sessions.revert("paper", flow.port, "ses_plan", "msg_02", "prt_02d", actor=OWNER)
    del flow.status["ses_plan"]
    sessions.send("paper", flow.port, "ses_plan", "Use a log scale.", actor=OWNER)
    stored = flow.store.messages["ses_plan"]
    assert [each["info"]["id"] for each in stored][:4] == ["msg_01", "msg_02", "msg_03", "msg_new01"]
    assert [part["id"] for part in stored[2]["parts"]] == ["prt_03a", "prt_03b", "prt_03c", "prt_03d"]
    assert "revert" not in flow.store.sessions["ses_plan"], "made final"


def test_an_undo_opencode_takes_further_back_gives_back_the_words_it_took_and_says_so(
    kernel: Kernel,
    servers: list[FakeOpenCode],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, flow = servers
    flow.store.messages["ses_plan"][3]["parts"][0]["text"] = LONG
    guide = ready(kernel, servers, tmp_path, monkeypatch)
    read(guide)  # the flow keeps step 3's text, prt_05b, which OpenCode has since lost
    bare = step("msg_05", "msg_04", STEP_3, [finish("prt_05c", "stop")], completed=STEP_3 + 10_000)
    fourth = step("msg_06", "msg_04", STEP_3 + 20_000, [tool("prt_06b", "edit"), finish("prt_06c")],
                  completed=STEP_3 + 30_000)  # fmt: skip
    said(flow, bare, fourth)
    idle(flow)
    seen(guide, lambda: offered(guide, "undo")["revert"] == {"message": "msg_05", "part": "prt_05c"})
    answer = guide.undo("paper", "ses_plan", actor=OWNER, message="msg_05", part="prt_05c", steps=[4], said=[])
    assert answer["revert"] == {"message": "msg_04", "part": ""}, "nothing OpenCode counts before the cut: the turn"
    assert answer["why"].startswith("OpenCode took back from msg_04, not prt_05c: your message and steps 3 and 4")
    assert (answer["text"], answer["whole"]) == (LONG, True), "the words of the message it took back too"
    assert (answer["takes"]["said"], answer["takes"]["steps"]) == (["msg_04"], [3, 4])
    state = offered(guide, "undo")["state"]
    assert (state["state"], state["what"]) == ("turn undone", "your message and steps 3 and 4")
