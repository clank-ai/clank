"""Design 0012 §9.1, §9.5 and §9.7 (§11 step 10), decision 0056: what the Guide offers for Undo (`u`) and Drop (`x`),
a pure function of the session's flow, the server that runs it, its context totals and the gateway's figures.

Undo takes back the last step with OpenCode's `revert` at the last part of the step before it, never a revert by
message id alone; a step before it with nothing OpenCode counts before its last part is taken back with it. For the
first step after the owner's message (a note included) it is refused with the reason and offers to undo the turn, a
revert at that message, whose text comes back. It waits for the session to stop, does not cross a compaction, and while
a revert is pending it is Redo, `unrevert`, until the next message makes it final. Its preview lists the steps, the
files and the owner's messages it takes back.

Drop clears one finished call's result, never one of the step in progress; it says the tokens it frees (the result's
characters at the model's calibration for tool results, else a plain 0.3 tokens a character) and what it costs:
everything after the item read once, or nothing when no step has read it yet. Their states are read from the flow.
"""

from typing import Any

from clank.components.agents import guide
from clank.components.agents.guide import offer
from clank.components.agents.sessionflow.flow import Flow
from clank.components.runtime import service as runtime
from tests.components.agents.test_guide import ENDED, TOTALS, request
from tests.support.flowlines import (
    SESSION,
    compacting,
    finish,
    lines,
    page,
    patch,
    removed,
    reverted,
    status,
    step,
    text,
    tool,
    updated,
    user,
)

BEGUN = 1_760_900_000_000  # ms, OpenCode's clock


def heard(flow: Flow, events: list[dict[str, Any]]) -> None:
    for line in lines(events):
        flow.heard(line)


def made(messages: list[dict[str, Any]], state: str = "idle", prompts: dict[str, int] | None = None) -> Flow:
    """A flow of these messages, its status, and each step's request with its prompt."""
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(messages))
    flow.requests([request(f"r-{id}", next(each["info"]["time"]["created"] for each in messages
                                          if each["info"]["id"] == id) + 300, prompt)
                   for id, prompt in (prompts or {}).items()])  # fmt: skip
    heard(flow, [status(state)])
    return flow


def edits(id: str, parent: str, at: int, *files: str, content: bool = True) -> dict[str, Any]:
    """A finished step that edits files (a call, its finish, its patch), or that only thinks."""
    n = id.removeprefix("msg_")  # its parts' ids sort after its step-start's, as OpenCode's ids do
    parts = [tool(f"prt_{n}_b", "edit", output="x" * 4_000)] if content else [text(f"prt_{n}_b", "Hmm.", "reasoning")]
    return step(id, parent, at, [*parts, finish(f"prt_{n}_c"), *([patch(f"prt_{n}_d", *files)] if files else [])],
                completed=at + 900)  # fmt: skip


def offered(flow: Flow, **given: Any) -> dict[str, dict[str, Any]]:
    chosen: dict[str, Any] = {"port": 4096, "totals": TOTALS, "ended": ENDED, "kept": {}, **given}
    return {each["action"]: each for each in offer(flow.view(), **chosen)}


def three() -> list[dict[str, Any]]:
    """The owner's message, then three steps: the first edits plot.py, the second only thinks, the third edits two
    files."""
    return [
        user("msg_00", BEGUN, "Plot tau.", agent="planner"),
        edits("msg_01", "msg_00", BEGUN + 1_000, "/w/plot.py"),
        edits("msg_02", "msg_00", BEGUN + 2_000, content=False),
        edits("msg_03", "msg_00", BEGUN + 3_000, "/w/a.py", "/w/b.py"),
    ]


def test_undo_cuts_at_the_previous_steps_last_part_and_previews_its_steps_and_files() -> None:
    flow = made([user("msg_00", BEGUN, "Plot tau."), edits("msg_01", "msg_00", BEGUN + 1_000, "/w/plot.py"),
                 edits("msg_02", "msg_00", BEGUN + 2_000, "/w/a.py", "/w/b.py")])  # fmt: skip
    undo = offered(flow)["undo"]
    assert (undo["key"], undo["title"], undo["mode"], undo["can"], undo["confirm"]) == ("u", "Undo", "step", True, True)
    assert undo["revert"] == {"message": "msg_01", "part": "prt_01_d"}, "the step before's last part, named"
    assert undo["calls"] == ['POST /session/ses_plan/revert {"messageID": "msg_01", "partID": "prt_01_d"}']
    assert undo["takes"] == {"steps": [2], "files": ["/w/a.py", "/w/b.py"], "said": [], "text": "", "subagents": 0}
    assert "step 2" in undo["does"]
    assert "/w/a.py" in undo["does"]
    assert "u redoes it" in undo["does"]
    assert (undo["cost"]["tokens"], "to measure" in undo["cost"]["words"]) == (None, True)
    assert undo["refused"] == ""


def test_a_step_with_nothing_before_its_last_part_is_taken_back_with_the_step_after_it() -> None:
    undo = offered(made(three()))["undo"]
    assert undo["revert"] == {"message": "msg_01", "part": "prt_01_d"}, "OpenCode would take the turn back at msg_02"
    assert (undo["takes"]["steps"], undo["takes"]["files"]) == ([2, 3], ["/w/a.py", "/w/b.py"])
    assert "steps 2 and 3" in undo["does"]


def test_undo_of_the_first_step_after_your_message_is_refused_and_offers_undo_the_turn() -> None:
    flow = made([*three()[:2], user("msg_02", BEGUN + 5_000, "Use a log scale."),
                 edits("msg_03", "msg_02", BEGUN + 6_000, "/w/plot.py")])  # fmt: skip
    undo = offered(flow)["undo"]
    assert (undo["mode"], undo["title"], undo["can"]) == ("turn", "Undo turn", True)
    assert undo["refused"] == (
        "step 2 is the first after your message: undoing it alone would take back your message too"
    )
    assert undo["revert"] == {"message": "msg_02", "part": ""}
    assert undo["calls"] == ['POST /session/ses_plan/revert {"messageID": "msg_02"}']
    assert undo["takes"] == {"steps": [2], "files": ["/w/plot.py"], "said": ["msg_02"], "text": "Use a log scale.",
                             "subagents": 0}  # fmt: skip
    assert "note line" in undo["does"]
    noted = made([*three()[:1], edits("msg_01", "msg_00", BEGUN + 1_000, "/w/plot.py"),
                  user("msg_02", BEGUN + 1_500, "Keep it short."),
                  edits("msg_03", "msg_00", BEGUN + 2_000)])  # fmt: skip
    assert next(node for node in noted.view()["nodes"] if node["id"] == "msg_02")["note"] is True, "sent while step 1"
    assert offered(noted)["undo"]["revert"] == {"message": "msg_02", "part": ""}, "the note goes with the turn"
    first = offered(made(three()[:2]))["undo"]
    assert (first["mode"], first["revert"], first["takes"]["text"]) == ("turn", {"message": "msg_00", "part": ""},
                                                                         "Plot tau.")  # fmt: skip
    summary = step("msg_05", "msg_04", BEGUN + 9_000, [text("prt_05_a", "The summary.")], completed=BEGUN + 9_500,
                   summary=True)  # fmt: skip
    after = offered(made([*three(), compacting("msg_04", "msg_03", BEGUN + 8_000), summary]))["undo"]
    assert (after["can"], after["why"]) == (False, "the step before it is a compaction: undo does not take back a "
                                            "compaction")  # fmt: skip


def test_undo_waits_for_the_session_to_stop_and_redo_follows_until_your_next_message() -> None:
    busy = offered(made(three(), "busy"))["undo"]
    assert (busy["can"], busy["why"]) == (False, "the session works: stop it first (.); OpenCode takes back no step "
                                          "while a session works")  # fmt: skip
    assert offered(made(three()), port=None)["undo"]["why"].startswith("no OpenCode server")
    assert offered(made([user("msg_00", BEGUN, "Hi.")]))["undo"]["why"] == "the session has no step to undo"
    flow = made(three())
    heard(flow, [reverted("msg_01", "prt_01_d")])
    redo = offered(flow)["undo"]
    assert (redo["mode"], redo["title"], redo["can"], redo["key"]) == ("redo", "Redo", True, "u")
    assert redo["calls"] == ["POST /session/ses_plan/unrevert"]
    assert "steps 2 and 3" in redo["brief"]
    assert "until your next message" in redo["does"]
    heard(flow, [removed("msg_02"), removed("msg_03"), removed("msg_01", "prt_01_d"), reverted()])
    heard(flow, updated(user("msg_04", BEGUN + 9_000, "Use a log scale.")))
    final = offered(flow)["undo"]
    assert final["mode"] == "turn", "the next message made it final: step 1 is the last, the first after yours"
    assert final["takes"]["said"] == ["msg_00", "msg_04"], "your message after the last step would go too: said"


def test_drop_is_refused_for_the_step_in_progress_and_says_what_it_frees_and_costs() -> None:
    running = step("msg_03", "msg_00", BEGUN + 3_000, [tool("prt_03_b", "read", output="y" * 100),
                                                       tool("prt_03_e", "bash", "running")])  # fmt: skip
    cleared = tool("prt_02_e", "read", output="z" * 50)
    cleared["state"]["time"]["compacted"] = BEGUN + 2_500
    second = step("msg_02", "msg_00", BEGUN + 2_000, [tool("prt_02_b", "read", output="w" * 10), cleared],
                  completed=BEGUN + 2_900)  # fmt: skip
    messages = [*three()[:2], second, running]
    flow = made(messages, "busy", prompts={"msg_01": 9_000, "msg_02": 12_000, "msg_03": 14_000})  # fmt: skip
    drop = offered(flow, item="prt_01_b")["drop"]
    assert (drop["key"], drop["title"], drop["can"], drop["confirm"]) == ("x", "Drop", True, True)
    assert drop["item"] == {"message": "msg_01", "part": "prt_01_b", "step": 1, "tool": "edit", "title": "",
                            "length": 4_000, "freed": 1_200}  # fmt: skip
    assert drop["calls"] == [
        "PATCH /session/ses_plan/message/msg_01/part/prt_01_b (the whole part, its state.time.compacted set to now)"
    ]
    assert "[Old tool result content cleared]" in drop["does"]
    assert "final" in drop["does"]
    assert (drop["cost"]["freed"], drop["cost"]["tokens"], drop["cost"]["seconds"]) == (1_200, 9_000, 4.5), (
        "21,000 used less the 12,000 of step 2, which read it first, at 2,000 tokens a second"
    )
    assert "0.3 tokens a character" in drop["cost"]["words"]
    assert guide.PLAIN_TOKENS_PER_CHARACTER == runtime.PLAIN_TOKENS_PER_CHARACTER, "the runtime's plain estimate"
    facts: dict[str, Any] = dict(TOTALS["facts"])  # type: ignore[call-overload]
    calibrated = {**TOTALS, "facts": {**facts, "model": {"calibration": {
        "tokens_per_character": {"tool results": 0.25}, "measured": "2026-10-19"}}}}  # fmt: skip
    assert offered(flow, item="prt_01_b", totals=calibrated)["drop"]["cost"]["freed"] == 1_000
    refused = {item: offered(flow, item=item)["drop"]["why"] for item in
               ("prt_03_b", "prt_03_e", "prt_02_e", "prt_gone")}  # fmt: skip
    assert refused == {
        "prt_03_b": "it is in the step in progress: OpenCode would change it while it runs",
        "prt_03_e": "only a finished call's result is cleared; this one is running",
        "prt_02_e": "its result is cleared already",
        "prt_gone": "no tool call prt_gone in the session's flow",
    }
    general = offered(flow)["drop"]
    assert (general["can"], general["item"]) == (True, None), "a result can be cleared: x names which"
    unread = made([*three()[:2]], prompts={"msg_01": 9_000})
    assert offered(unread, item="prt_01_b")["drop"]["cost"]["tokens"] == 0, "no step has read it yet"


def test_undo_and_drop_states_are_read_from_the_flow() -> None:
    flow = made(three())
    undone = {"state": "undone", "ids": ["msg_02", "msg_03"], "what": "steps 2 and 3", "time": "", "by": "you"}
    heard(flow, [reverted("msg_01", "prt_01_d")])
    assert offered(flow, kept={"undo": undone})["undo"]["state"]["state"] == "undone"
    assert offered(flow, kept={"undo": undone})["undo"]["state"]["what"] == "steps 2 and 3"
    heard(flow, [removed("msg_02"), removed("msg_03"), reverted()])
    assert offered(flow, kept={"undo": undone})["undo"]["state"]["state"] == "final"
    again = made(three())
    assert offered(again, kept={"undo": undone})["undo"]["state"]["state"] == "redone", "brought back elsewhere"
    flow = made(three())
    asked = {"state": "cleared", "part": "prt_01_b", "what": "step 1, `edit`", "time": "", "by": "you"}
    assert offered(flow, kept={"drop": asked})["drop"]["state"]["state"] == "clearing"
    compacted = tool("prt_01_b", "edit", output="x" * 4_000)
    compacted["state"]["time"]["compacted"] = BEGUN + 5_000
    heard(flow, updated(step("msg_01", "msg_00", BEGUN + 1_000, [compacted], completed=BEGUN + 1_900)))
    assert offered(flow, kept={"drop": asked})["drop"]["state"]["state"] == "cleared"
