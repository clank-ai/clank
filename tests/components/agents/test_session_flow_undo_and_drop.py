"""Design 0012 §9.5 and §9.7 (§11 step 10): what a session's flow says for the Guide's Undo and Drop.

A step names the part a revert at its end cuts at: its last part, when a text or a tool part comes before it (OpenCode
1.19.0's `session/revert.ts` turns a revert at a part with neither before it into a revert of the whole turn), and the
files its patch parts list, which a revert restores. The head names the revert pending; the steps it undid stay in the
flow once OpenCode removes them at the owner's next message, final. A call whose result the Guide cleared says so, with
the tokens it freed; one OpenCode cleared itself does not.
"""

from typing import Any

from clank.components.agents.sessionflow.flow import Flow
from tests.support.flowlines import (
    finish,
    lines,
    page,
    patch,
    removed,
    reverted,
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


def by_id(flow: Flow) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in flow.view()["nodes"]}


def session() -> Flow:
    """The owner's message and three finished steps: the first edits a file, the second only thinks, the third edits
    two files."""
    flow = Flow("ses_plan", workspace="paper")
    flow.history(page([
        user("msg_00", BEGUN, "Plot tau."),
        step("msg_01", "msg_00", BEGUN + 1_000, [text("prt_01a", "Editing."), tool("prt_01b", "edit"),
                                                 finish("prt_01c"), patch("prt_01d", "/w/plot.py")],
             completed=BEGUN + 2_000),
        step("msg_02", "msg_00", BEGUN + 3_000, [text("prt_02a", "Hmm.", kind="reasoning"), finish("prt_02b")],
             completed=BEGUN + 4_000),
        step("msg_03", "msg_00", BEGUN + 5_000, [tool("prt_03a", "edit"), tool("prt_03b", "write"),
                                                 finish("prt_03c"), patch("prt_03d", "/w/a.py", "/w/b.py")],
             completed=BEGUN + 6_000),
    ]))  # fmt: skip
    return flow


def test_a_step_names_the_part_a_revert_cuts_at_and_the_files_it_changed() -> None:
    nodes = by_id(session())
    assert (nodes["msg_01"]["cut"], nodes["msg_01"]["files"]) == ("prt_01d", ["/w/plot.py"])
    assert (nodes["msg_02"]["cut"], nodes["msg_02"]["files"]) == ("", []), "nothing but thinking before its last part"
    assert (nodes["msg_03"]["cut"], nodes["msg_03"]["files"]) == ("prt_03d", ["/w/a.py", "/w/b.py"])
    alone = Flow("ses_plan")
    alone.history(page([user("msg_00", BEGUN, "Hi."), step("msg_01", "msg_00", BEGUN + 1, [text("prt_01a", "Hi.")])]))
    assert by_id(alone)["msg_01"]["cut"] == "", "its text is its last part: nothing before it"
    assert session().view()["head"]["reverted"] is None


def test_steps_undone_stay_in_the_flow_final_once_opencode_removes_them() -> None:
    flow = session()
    heard(flow, [reverted("msg_01", "prt_01d")])
    nodes = by_id(flow)
    assert flow.view()["head"]["reverted"] == {"message": "msg_01", "part": "prt_01d"}
    assert [nodes[id]["undone"] for id in ("msg_01", "prt_01b", "msg_02", "msg_03", "prt_03a")] == [
        False, False, True, True, True
    ]  # fmt: skip
    assert not any(node.get("final") for node in nodes.values()), "until the next message, u redoes it"
    heard(flow, [removed("msg_02"), removed("msg_03"), removed("msg_01", "prt_01d"), reverted()])
    heard(flow, updated(user("msg_04", BEGUN + 9_000, "Use a log scale.")))
    nodes = by_id(flow)
    assert flow.view()["head"]["reverted"] is None
    finals = {(nodes[id]["undone"], nodes[id].get("final")) for id in ("msg_02", "msg_03", "prt_03b")}
    assert finals == {(True, True)}, "kept, final: the flow is the log of the owner's guidance"
    assert (nodes["msg_01"]["undone"], nodes["msg_01"]["files"]) == (False, []), "its patch part went with the cut"
    heard(flow, [removed("msg_04")])
    assert "msg_04" not in by_id(flow), "a message removed that no revert undid leaves the flow"


def test_a_result_the_guide_cleared_is_marked_by_you_with_the_tokens_it_freed() -> None:
    flow = session()
    flow.cleared("prt_03a", 1_250)
    call = by_id(flow)["prt_03a"]
    assert (call["cleared"], call["cleared_by"], call["freed"]) == (False, "", None), "not cleared until OpenCode says"
    compacted = tool("prt_03a", "edit")
    compacted["state"]["time"]["compacted"] = BEGUN + 8_000
    pruned = tool("prt_01b", "edit")
    pruned["state"]["time"]["compacted"] = BEGUN + 8_000
    heard(flow, updated(step("msg_03", "msg_00", BEGUN + 5_000, [compacted], completed=BEGUN + 6_000)))
    heard(flow, updated(step("msg_01", "msg_00", BEGUN + 1_000, [pruned], completed=BEGUN + 2_000)))
    nodes = by_id(flow)
    assert (nodes["prt_03a"]["cleared"], nodes["prt_03a"]["cleared_by"], nodes["prt_03a"]["freed"]) == (
        True, "you", 1_250
    )  # fmt: skip
    assert (nodes["prt_01b"]["cleared"], nodes["prt_01b"]["cleared_by"], nodes["prt_01b"]["freed"]) == (
        True, "", None
    ), "OpenCode's own clearing is not the owner's"  # fmt: skip
