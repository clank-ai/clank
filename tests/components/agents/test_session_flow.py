"""Design 0012 §6.1-§6.4 and §11 step 5 (decisions 0049 and 0050): a session's flow, built from the bridge watch's lines
and pages of the session's history (the synthetic session of plan s14 and small sessions made here, turned into the
bridge's shapes by the bridge's own functions).

One step is one assistant message: its calls, made at once, fan out from it; a call that failed becomes a dead end once
the agent moves on; a step that ended in an error leaves the context, while one the owner stopped stays when it has
content; a message or a part removed leaves the flow. Design 0012 §9.6: the band of a compaction the Guide asked for
is the owner's.
"""

from typing import Any

from clank.components.agents.sessionflow.flow import KEEP, Flow, slim
from tests.support.flowlines import (
    SESSION,
    burst,
    compacting,
    history,
    lines,
    page,
    status,
    step,
    text,
    tool,
    updated,
    user,
)


def nodes(flow: Flow, *kinds: str) -> list[dict[str, Any]]:
    """The flow's nodes of these kinds, in time order."""
    return [node for node in flow.view()["nodes"] if node["kind"] in kinds]


def by_id(flow: Flow) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in flow.view()["nodes"]}


def heard(flow: Flow, events: list[dict[str, Any]]) -> None:
    for line in lines(events):
        flow.heard(line)


def test_parts_become_a_step_with_its_calls_made_at_once_fanned_out() -> None:
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(history()))
    shown = [(node["kind"], node["id"]) for node in nodes(flow, "said", "step", "call")]
    assert shown == [
        ("said", "msg_01"), ("step", "msg_02"), ("call", "prt_02c"), ("step", "msg_03"), ("call", "prt_03b"),
        ("call", "prt_03c"), ("call", "prt_03d"), ("said", "msg_04"), ("step", "msg_05"),
    ]  # fmt: skip
    found = by_id(flow)
    first, second, third = found["msg_02"], found["msg_03"], found["msg_05"]
    assert (first["n"], first["said"], first["calls"], first["together"]) == (1, "msg_01", ["prt_02c"], 1)
    assert first["thinking"] == len("The data should be in data/tau.csv; read it first.")
    assert (first["ended"], first["context"], first["finish"]) == ("finished", "in", "tool-calls")
    assert first["tokens"]["input"] == 9214
    assert (second["n"], second["together"]) == (2, 3), "three calls made at once, in one answer"
    assert second["calls"] == ["prt_03b", "prt_03c", "prt_03d"]
    assert (third["n"], third["said"], third["ended"]) == (3, "msg_04", "working")
    assert third["text"] == "Skipping the check; the figure is saved."
    read = found["prt_02c"]
    assert (read["step"], read["tool"], read["call"], read["status"], read["title"]) == (
        "msg_02", "read", "call_01", "completed", "data/tau.csv"
    )  # fmt: skip
    assert read["length"] > 1500, "the output's whole length, though the bridge cut it"
    assert found["msg_01"]["text"].startswith("Plot tau against p")
    assert [node["at"] for node in flow.view()["nodes"]] == sorted(node["at"] for node in flow.view()["nodes"])
    heard(flow, burst("a step"))
    live = by_id(flow)["msg_06"]
    assert (live["n"], live["said"], live["ended"], live["text"]) == (4, "msg_04", "finished", "The axis is right.")
    assert [by_id(flow)[call]["status"] for call in live["calls"]] == ["completed"]
    head = flow.view()["head"]
    assert (head["session"], head["workspace"], head["port"], head["status"]) == (SESSION, "paper", 4096, "idle")
    assert (head["steps"], head["calls"], head["title"]) == (4, 5, "Plot tau against p (n=8)")


def test_a_step_that_ended_in_an_error_is_marked_not_in_the_context_and_a_stopped_one_is_kept() -> None:
    aborted = {"name": "MessageAbortedError", "data": {"message": "Aborted"}}
    failed = {"name": "APIError", "data": {"message": "Clank's loop guard stopped the answer"}}
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [text("p1", "Reading the data.")], completed=3_000, error=aborted),
        step("msg_03", "msg_01", 4_000, [text("p2", "again and again", "reasoning")], completed=5_000, error=aborted),
        step("msg_04", "msg_01", 6_000, [text("p3", "I will plot")], completed=7_000, error=failed),
        step("msg_05", "msg_01", 8_000, [text("p4", "Done.")], completed=9_000),
    ]))  # fmt: skip
    found = by_id(flow)
    assert (found["msg_02"]["ended"], found["msg_02"]["context"]) == ("stopped", "in"), "stopped, with text: kept"
    assert (found["msg_03"]["ended"], found["msg_03"]["context"]) == ("stopped", "left"), "only thinking: left out"
    assert (found["msg_04"]["ended"], found["msg_04"]["context"]) == ("failed", "left")
    assert found["msg_04"]["error"] == "Clank's loop guard stopped the answer"
    assert (found["msg_05"]["ended"], found["msg_05"]["context"]) == ("finished", "in")


def test_a_failed_call_becomes_a_dead_end_once_the_agent_moves_on() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Run the tests."),
        step("msg_02", "msg_01", 2_000, [
            tool("c1", "bash", "completed", input={"command": "pytest -q"}, metadata={"exit": 1}),
            tool("c2", "read", "error", error="no such file"),
            tool("c3", "bash", "completed", input={"command": "ls"}, metadata={"exit": 0}),
        ], completed=3_000),
    ]))  # fmt: skip
    found = by_id(flow)
    assert [(found[id]["failed"], found[id]["dead_end"]) for id in ("c1", "c2", "c3")] == [
        (True, False), (True, False), (False, False)
    ], "failed, on the main line while it is the newest step"  # fmt: skip
    assert (found["c1"]["exit"], found["c2"]["error"]) == (1, "no such file")
    heard(flow, [*updated(step("msg_03", "msg_01", 4_000, [text("p1", "Fixing the import.")]))])
    found = by_id(flow)
    assert [found[id]["dead_end"] for id in ("c1", "c2", "c3")] == [True, True, False], "the agent moved on"


def test_a_message_or_a_part_removed_leaves_the_flow() -> None:
    flow = Flow(SESSION)
    flow.history(page(history()))
    assert {"msg_05", "prt_03d"} <= set(by_id(flow))
    heard(flow, burst("compacted"))
    found = by_id(flow)
    assert "msg_05" not in found
    assert "prt_03d" not in found
    assert found["msg_03"]["calls"] == ["prt_03b", "prt_03c"]
    assert flow.view()["head"]["error"] == "The engine broke off"


def test_a_line_about_another_session_or_a_status_changes_only_its_own_facts() -> None:
    flow = Flow(SESSION)
    heard(flow, [status("busy"), status("busy", session="ses_other")])
    assert flow.view()["head"]["status"] == "busy"
    heard(flow, [*updated(user("msg_x", 1, "Other work.", session="ses_other")), status("idle", session="ses_other")])
    assert flow.view()["nodes"] == []
    assert flow.view()["head"]["status"] == "busy"
    heard(flow, [status("retry", attempt=2, message="Provider is overloaded", next=5)])
    head = flow.view()["head"]
    assert (head["status"], head["attempt"], head["retry"], head["next"]) == ("retry", 2, "Provider is overloaded", 5)


def test_task_metadata_becomes_a_subagents_branch_from_its_call() -> None:
    flow = Flow(SESSION)
    flow.history(page(history()))
    found = by_id(flow)
    branch = found["prt_03b:ses_child"]  # its call's and its session's
    assert (branch["kind"], branch["session"], branch["call"], branch["step"], branch["status"]) == (
        "subagent", "ses_child", "prt_03b", "msg_03", "completed"
    )  # fmt: skip
    assert (branch["title"], branch["gave"]) == ("Find the plotting helpers", "plot.py draws every figure.")
    assert found["prt_03b"]["subagent"] == "ses_child"
    order = [node["id"] for node in flow.view()["nodes"]]
    assert order.index("prt_03b") < order.index("prt_03b:ses_child") < order.index("prt_03c"), (
        "the branch opens from its call"
    )
    assert (branch["steps"], branch["state"]) == (None, ""), "its own flow not known yet"
    flow.child("ses_child", {"title": "Find the plotting helpers (@explore subagent)", "status": "idle", "steps": 1,
                             "calls": 1, "parent": SESSION})  # fmt: skip
    branch = by_id(flow)["prt_03b:ses_child"]
    assert (branch["steps"], branch["calls"], branch["state"]) == (1, 1, "idle")
    flow.child("ses_child2", {"title": "Read the axis labels (@explore subagent)", "status": "busy", "steps": 0,
                              "calls": 0, "parent": SESSION})  # fmt: skip
    started = by_id(flow)["ses_child2"]
    assert (started["call"], started["step"], started["state"]) == ("", "msg_05", "busy"), "from the newest step"
    assert [node["id"] for node in flow.view()["nodes"]][-1] == "ses_child2"


def test_a_subagent_session_continued_by_a_later_task_call_is_a_branch_from_each_call() -> None:
    flow = Flow(SESSION)
    asked = [tool("c1", "task", metadata={"sessionId": "ses_child"}, output="plot.py draws every figure.")]
    again = [tool("c2", "task", metadata={"sessionId": "ses_child"}, output="axes.py labels them.")]
    flow.history(page([
        user("msg_01", 1_000, "Find the plotting helpers."),
        step("msg_02", "msg_01", 2_000, asked, completed=2_500),
        step("msg_03", "msg_01", 3_000, again, completed=3_500),
    ]))  # fmt: skip
    branches = nodes(flow, "subagent")
    assert [(node["id"], node["session"], node["call"], node["gave"]) for node in branches] == [
        ("c1:ses_child", "ses_child", "c1", "plot.py draws every figure."),
        ("c2:ses_child", "ses_child", "c2", "axes.py labels them."),
    ]  # fmt: skip
    every = [node["id"] for node in flow.view()["nodes"]]
    assert len(every) == len(set(every)), "every node its own id, so what changed is placed by it"


def test_a_permission_asked_for_a_call_waits_on_that_call_until_it_is_replied() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Clean the runs."),
        step("msg_02", "msg_01", 2_000, [tool("c1", "bash", "running", call="call_9",
                                              input={"command": "rm -r runs"})]),
    ]))  # fmt: skip
    ask = {"id": "per_1", "sessionID": SESSION, "permission": "bash", "patterns": ["rm -r runs"],
           "tool": {"messageID": "msg_02", "callID": "call_9"}}  # fmt: skip
    heard(flow, [{"type": "permission.asked", "properties": ask}])
    assert (by_id(flow)["c1"]["asking"], by_id(flow)["c1"]["permission"]) == ("per_1", "bash")
    other = {**ask, "id": "per_2", "sessionID": "ses_other"}
    heard(flow, [{"type": "permission.asked", "properties": other}])
    assert by_id(flow)["c1"]["asking"] == "per_1", "another session's ask is not this call's"
    heard(flow, [{"type": "permission.replied",
                  "properties": {"sessionID": SESSION, "requestID": "per_1", "reply": "once"}}])  # fmt: skip
    assert (by_id(flow)["c1"]["asking"], by_id(flow)["c1"]["permission"]) == ("", "")


def test_a_compaction_becomes_a_band_across_the_flow() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [text("p1", "Reading.")], completed=3_000),
        compacting("msg_03", "msg_02", 4_000),
        step("msg_04", "msg_03", 5_000, [text("p2", "The session so far: ...")], summary=True),
    ]))  # fmt: skip
    found = by_id(flow)
    band = found["msg_03"]
    assert (band["kind"], band["auto"], band["summary"], band["done"]) == ("band", True, "msg_04", False)
    assert found["msg_04"]["summary"] is True
    assert flow.view()["head"]["compactions"] == 1
    assert all(item["key"] != "said:msg_03" for item in flow.view()["items"]), "a compaction is not the owner's"
    heard(
        flow,
        [
            *updated(
                step("msg_04", "msg_03", 5_000, [text("p2", "The session so far: ...")], completed=6_000, summary=True)
            ),
            {"type": "session.compacted", "properties": {"sessionID": SESSION}},
        ],
    )
    assert by_id(flow)["msg_03"]["done"] is True
    other = Flow(SESSION)  # a compaction said without its message: a band where it was heard
    other.history(page([user("msg_01", 1_000, "Plot tau."), step("msg_02", "msg_01", 2_000, [], completed=3_000)]))
    heard(other, [{"type": "session.compacted", "properties": {"sessionID": SESSION}}])
    [band] = nodes(other, "band")
    assert (band["done"], band["at"] > by_id(other)["msg_02"]["at"]) == (True, True)


def test_the_band_of_a_compaction_the_guide_asked_for_is_the_owners() -> None:
    """Design 0012 §9.6: the Guide asks with `auto` on, as OpenCode's own compactions are, so the flow is told."""
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [text("p1", "Reading.")], completed=3_000),
        compacting("msg_03", "msg_02", 4_000),
        step("msg_04", "msg_03", 5_000, [text("p2", "The session so far: ...")], completed=6_000, summary=True),
    ]))  # fmt: skip
    assert by_id(flow)["msg_03"]["asked"] is False, "OpenCode's own"
    flow.compaction_asked()
    heard(flow, [
        *updated(step("msg_05", "msg_04", 7_000, [text("p3", "Going on.")], completed=8_000)),
        *updated(compacting("msg_06", "msg_05", 9_000)),
    ])  # fmt: skip
    found = by_id(flow)
    assert (found["msg_03"]["asked"], found["msg_06"]["asked"]) == (False, True), "the next band after the asking"
    heard(flow, [*updated(compacting("msg_07", "msg_06", 10_000))])
    assert by_id(flow)["msg_07"]["asked"] is False, "one asking, one band"


def test_a_note_sent_while_busy_is_delivered_at_the_next_step() -> None:
    flow = Flow(SESSION)
    heard(flow, [*updated(user("msg_01", 1_000, "Plot tau.")), status("busy"),
                 *updated(step("msg_02", "msg_01", 2_000, [tool("c1", "bash", "running")]))])  # fmt: skip
    heard(flow, [*updated(user("msg_03", 2_500, "About step 1: use n=8."))])
    note = by_id(flow)["msg_03"]
    assert (note["note"], note["state"], note["read_by"]) == (True, "waiting", "")
    assert by_id(flow)["msg_01"]["note"] is False
    heard(flow, [*updated(step("msg_02", "msg_01", 2_000, [tool("c1", "bash")], completed=3_000)),
                 *updated(step("msg_04", "msg_03", 3_100, [text("p1", "Using n=8.")]))])  # fmt: skip
    note = by_id(flow)["msg_03"]
    assert (note["state"], note["read_by"]) == ("read", "msg_04")
    told = Flow(SESSION)  # the same, read from the history: a message sent while a step was under way
    told.history(page([
        user("msg_01", 1_000, "Plot tau."), step("msg_02", "msg_01", 2_000, [], completed=3_000),
        user("msg_03", 2_500, "About step 1: use n=8."), step("msg_04", "msg_03", 3_100, [], completed=4_000),
        user("msg_05", 5_000, "Now the axis."),
    ]))  # fmt: skip
    found = by_id(told)
    assert [(found[id]["note"], found[id]["read_by"]) for id in ("msg_01", "msg_03", "msg_05")] == [
        (False, "msg_02"), (True, "msg_04"), (False, "")
    ]  # fmt: skip


def test_two_notes_sent_during_one_step_are_both_read_by_the_next_step() -> None:
    """Design 0012 §9.3: a note is stored at once and read at the next step, whatever message that step answers."""
    flow = Flow(SESSION)
    heard(flow, [*updated(user("msg_01", 1_000, "Plot tau.")), status("busy"),
                 *updated(step("msg_02", "msg_01", 2_000, [tool("c1", "bash", "running")]))])  # fmt: skip
    heard(flow, [*updated(user("msg_03", 2_500, "Use n=8.")), *updated(user("msg_04", 2_600, "And label the axis."))])
    heard(flow, [*updated(step("msg_02", "msg_01", 2_000, [tool("c1", "bash")], completed=3_000)),
                 *updated(step("msg_05", "msg_04", 3_100, [text("p1", "Using n=8, axis labeled.")],
                               completed=3_500)), status("idle")])  # fmt: skip
    found = by_id(flow)
    assert [(found[id]["note"], found[id]["state"], found[id]["read_by"]) for id in ("msg_03", "msg_04")] == [
        (True, "read", "msg_05"), (True, "read", "msg_05")
    ]  # fmt: skip
    told = Flow(SESSION)  # the same, read from the history
    told.history(page([
        user("msg_01", 1_000, "Plot tau."), step("msg_02", "msg_01", 2_000, [], completed=3_000),
        user("msg_03", 2_500, "Use n=8."), user("msg_04", 2_600, "And label the axis."),
        step("msg_05", "msg_04", 3_100, [], completed=3_500),
    ]))  # fmt: skip
    found = by_id(told)
    assert [(found[id]["state"], found[id]["read_by"]) for id in ("msg_03", "msg_04")] == [
        ("read", "msg_05"), ("read", "msg_05")
    ]  # fmt: skip


def test_a_note_the_run_ended_without_reading_is_marked_not_read() -> None:
    flow = Flow(SESSION)
    heard(flow, [*updated(user("msg_01", 1_000, "Plot tau.")), status("busy"),
                 *updated(step("msg_02", "msg_01", 2_000, [text("p1", "Done.")]))])  # fmt: skip
    heard(flow, [*updated(user("msg_03", 2_500, "Also save it as a PDF."))])
    heard(flow, [*updated(step("msg_02", "msg_01", 2_000, [text("p1", "Done.")], completed=2_600)), status("idle")])
    assert (by_id(flow)["msg_03"]["state"], by_id(flow)["msg_03"]["read_by"]) == ("not read", "")


def test_steps_a_revert_took_back_are_marked_undone() -> None:
    flow = Flow(SESSION)
    flow.history(page(history()))

    def reverted(revert: dict[str, Any]) -> list[str]:
        info = {"id": SESSION, "title": "Plot tau against p", "time": {"created": 1, "updated": 2}, "revert": revert}
        heard(flow, [{"type": "session.updated", "properties": {"sessionID": SESSION, "info": info}}])
        return [node["id"] for node in flow.view()["nodes"] if node.get("undone")]

    assert reverted({"messageID": "msg_04"}) == ["msg_04", "msg_05"]
    assert reverted({"messageID": "msg_03", "partID": "prt_03e"}) == ["msg_04", "msg_05"], "the part's message stays"
    assert reverted({"messageID": "msg_03"})[:4] == ["msg_03", "prt_03b", "prt_03b:ses_child", "prt_03c"]
    assert reverted({}) == [], "unrevert brings everything back"


def test_the_console_gets_only_what_changed_since_its_version() -> None:
    flow = Flow(SESSION)
    flow.history(page(history()))
    first = flow.changes(0)
    assert first["whole"] is True
    assert [node["id"] for node in first["nodes"]] == [node["id"] for node in flow.view()["nodes"]]
    assert "items" in first
    seen = first["version"]
    assert flow.view()["version"] == seen, "nothing changed: the same version"
    quiet = flow.changes(seen)
    assert (quiet["whole"], quiet["nodes"], quiet["removed"], "items" in quiet) == (False, [], [], False)
    assert quiet["head"]["session"] == SESSION, "the head comes every time"
    heard(flow, [status("busy", session="ses_other")])
    assert flow.changes(seen)["version"] == seen, "a line about another session changes nothing"
    shown = nodes_now(flow)
    heard(flow, burst("a step"))
    after = flow.changes(seen)
    assert after["version"] > seen
    assert {node["id"] for node in after["nodes"]} == differ(shown, nodes_now(flow)), "exactly the nodes that changed"
    assert {"msg_06", "prt_06c"} <= {node["id"] for node in after["nodes"]}
    assert all(node["v"] == after["version"] for node in after["nodes"])
    assert after["items"][-1]["source"] == "todo", "the branches changed: they come too"
    shown = nodes_now(flow)
    heard(flow, burst("compacted"))
    removed = flow.changes(after["version"])
    assert sorted(removed["removed"]) == ["msg_05", "prt_03d"]
    assert {node["id"] for node in removed["nodes"]} == differ(shown, nodes_now(flow))
    assert "msg_03" in {node["id"] for node in removed["nodes"]}, "its calls changed"


def nodes_now(flow: Flow) -> dict[str, dict[str, Any]]:
    """The flow's nodes as they are now, without their versions."""
    return {node["id"]: {key: value for key, value in node.items() if key != "v"} for node in flow.view()["nodes"]}


def differ(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> set[str]:
    """The nodes new or changed."""
    return {id for id, node in after.items() if before.get(id) != node}


def test_a_version_older_than_a_rebuild_gets_the_whole_flow() -> None:
    old = Flow(SESSION)
    old.history(page(history()))
    kept = old.changes(0)["version"]
    again = Flow(SESSION)  # the flow made again: the service started again, or the flow was dropped and seen again
    again.history(page(history()))
    found = again.changes(kept)
    assert (found["whole"], len(found["nodes"])) == (True, len(again.view()["nodes"]))
    assert found["base"] > kept
    assert again.changes(found["version"] + 1_000)["whole"] is True, "a version this flow never had"


def test_a_flow_keeps_texts_briefly_with_their_whole_lengths() -> None:
    """Design 0012 §6.1: a flow is kept for every session the watchers see, so it keeps briefs, not whole texts; the
    whole is one read of the history away."""
    long = "word " * 1_200
    thinking = slim({"id": "p1", "message": "msg_02", "type": "reasoning", "text": long, "length": len(long)})
    assert (len(thinking["text"]) <= KEEP, thinking["length"]) == (True, len(long))
    output = slim({"id": "c1", "message": "msg_02", "type": "tool", "tool": "bash", "output": long, "input": "{}"})
    assert len(output["output"]) <= KEEP
    written = slim({"id": "c2", "message": "msg_02", "type": "tool", "tool": "todowrite", "output": long})
    assert written["output"] == long, "a todo list is read from its call's output"
    flow = Flow(SESSION)
    thought = [text("p1", long, "reasoning"), text("p2", long)]
    flow.history(page([user("msg_01", 1_000, "Think hard."), step("msg_02", "msg_01", 2_000, thought)]))
    found = by_id(flow)["msg_02"]
    assert (found["thinking"], found["length"], len(found["text"]) <= 300) == (len(long), len(long), True)
