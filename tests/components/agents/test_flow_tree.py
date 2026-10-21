"""Design 0012 §6.2-§6.4 and §11 step 6 (decision 0050): what the Monitor's Flow panel draws of a session's flow, as a
tree. The owner's message is the root and the main branches (a plan's steps, the todo list's items, or the owner's
messages) are its children, each marked by its state, a planned one on a line not taken yet; a branch's work comes in
time order: a step's calls made at once are one node that fans out to each, a run of one tool folds into one node
(`read ×3`), a call that failed then passed folds into its tries; a subagent is a branch of its own, with its own flow's
work when it is given; the owner's note joins the branch of the step under way when it was sent; the step working now
is the newest node; a step that left the context is drawn apart from one the owner stopped and kept; a dead end ends in
its mark; steps undone are a side lane, folded; a compaction is a band, and the branches above it fold into it. Folds:
a done branch folds to one line, the branch in progress is always open, a fold that holds the newest node is open
while it works, and the owner's own fold or open wins over the default. Design 0012 §9.4 (§11 step 11): a hold is drawn
on its step's line, before its work, "held by you 12:22 to 12:25", and one a note closed says so ("until a note").
Design 0012 §9.5 and §9.7 (§11 step 10): steps undone say that u redoes them until they are final, and then that they
are; a result the Guide cleared says "result cleared by you" with the tokens it freed, one OpenCode cleared itself only
that it is cleared. The flows are made by step 5's `Flow` from synthetic sessions."""

import json
from datetime import UTC, datetime
from typing import Any

from clank.components.agents.console.flowtree import Node, tree, what
from clank.components.agents.sessionflow.flow import Flow
from tests.support.flowlines import (
    SESSION,
    compacting,
    lines,
    page,
    removed,
    reverted,
    status,
    step,
    text,
    tool,
    updated,
    user,
)


def outline(node: Node, depth: int = 0) -> list[str]:
    """The tree as indented lines: its line not taken yet (┄), its mark, its words, its detail, its end, whether it is
    folded; a folded node's children left out, as the panel leaves them out."""
    line = "┄ " if node.line == "not yet" else ""
    mark = f"{node.mark} " if node.mark else ""
    detail = f" · {node.detail}" if node.detail else ""
    end = f" {node.end}" if node.end else ""
    shown = ["  " * depth + f"{line}{mark}{node.words}{detail}{end}{' [folded]' if node.folded else ''}"]
    for child in [] if node.folded else node.children:
        shown += outline(child, depth + 1)
    return shown


def find(node: Node, id: str) -> Node:
    """The node of this id, anywhere in the tree."""
    if node.id == id:
        return node
    for child in node.children:
        try:
            return find(child, id)
        except KeyError:
            continue
    raise KeyError(id)


def stamp(ms: int) -> str:
    """A time as the gateway writes it."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def todo(content: str, state: str) -> dict[str, str]:
    return {"content": content, "status": state, "priority": "medium"}


def wrote(id: str, todos: list[dict[str, str]]) -> dict[str, Any]:
    """OpenCode's `todowrite` call."""
    return tool(id, "todowrite", input={"todos": todos}, output=json.dumps(todos))


def bash(id: str, command: str, *, exit: int = 0, output: str = "ok", state: str = "completed") -> dict[str, Any]:
    return tool(id, "bash", state, input={"command": command}, metadata={"exit": exit}, output=output)


def read(id: str, path: str, size: int = 100) -> dict[str, Any]:
    return tool(id, "read", input={"filePath": f"/workspace/{path}"}, title=path, output="x" * size)


def flow_of(messages: list[dict[str, Any]], *heard: dict[str, Any]) -> Flow:
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(messages))
    for line in lines(list(heard)):
        flow.heard(line)
    return flow


LISTED = [todo("Read the data", "completed"), todo("Draw the figure", "in_progress"), todo("Write it up", "pending")]


def two_branches() -> Flow:
    """A todo list of three: the first done, the second in progress, the third planned."""
    return flow_of(
        [
            user("msg_01", 1_000, "Plot tau against p."),
            step(
                "msg_02",
                "msg_01",
                2_000,
                [
                    wrote(
                        "c1",
                        [
                            todo("Read the data", "in_progress"),
                            todo("Draw the figure", "pending"),
                            todo("Write it up", "pending"),
                        ],
                    )
                ],
                completed=2_100,
            ),
            step("msg_03", "msg_01", 3_000, [read("c2", "data/tau.csv", 2_400)], completed=3_100),
            step("msg_04", "msg_01", 4_000, [wrote("c3", LISTED)], completed=4_100),
            step("msg_05", "msg_01", 5_000, [bash("c4", "python plot.py")], completed=5_100),
        ],
        status("busy"),
    )


def test_the_owner_is_the_root_and_the_main_branches_are_its_children_each_marked_by_its_state() -> None:
    root = tree(two_branches().view())
    assert (root.kind, root.words) == ("root", "You")
    assert outline(root) == [
        "You",
        "  before the todo list · 1 call [folded]",
        "  ✓ Read the data · 2 calls [folded]",
        "  ● Draw the figure",
        "    bash python plot.py · 2 chars",
        "  ┄ ○ Write it up",
    ]
    branch = find(root, "todo:2")
    assert (branch.tone, branch.folds) == ("$clank-now", False), "the branch in progress is always open"
    assert find(root, "todo:1").tone == "$clank-good"
    assert find(root, "todo:3").tone == "$clank-quiet"


def test_a_branchs_calls_come_in_time_order_and_a_run_of_one_tool_folds_into_one_node() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Plot tau against p."),
        step("msg_02", "msg_01", 2_000, [read("c1", "a.py", 1_500)], completed=2_100),
        step("msg_03", "msg_01", 3_000, [read("c2", "b.py", 2_500)], completed=3_100),
        step("msg_04", "msg_01", 4_000, [read("c3", "c.py")], completed=4_100),
        step("msg_05", "msg_01", 5_000, [bash("c4", "pytest -q")], completed=5_100),
        step("msg_06", "msg_01", 6_000, [tool("c5", "notion_search", input={"query": "tau"}, output="y" * 6_400)],
             completed=6_100),
    ])  # fmt: skip
    root = tree(flow.view(), folds={"said:msg_01": False})
    assert outline(root)[1:] == [
        "  ✓ Plot tau against p.",
        "    read ×3 [folded]",
        "    bash pytest -q · 2 chars",
        "    notion_search tau · 6.4K chars",
    ]
    run = find(root, "run:c1")
    calls = [node for node in flow.view()["nodes"] if node["kind"] == "call"]
    assert [what(call) for call in calls] == ["a.py", "b.py", "c.py", "pytest -q", "tau"]
    assert [child.words for child in run.children] == ["a.py", "b.py", "c.py"], "the run opens to its calls"
    assert [child.detail for child in run.children] == ["1.5K chars", "2.5K chars", "100 chars"]
    assert run.tone == "$clank-call-reading"
    assert find(root, "c4").tone == "$clank-call-running"
    assert find(root, "c5").tone == "$clank-call-mcp", "a tool OpenCode does not have itself is an MCP server's"


def test_calls_made_at_once_are_one_node_that_fans_out_to_each() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Plot tau against p."),
        step("msg_02", "msg_01", 2_000, [read("c1", "a.py"), read("c2", "b.py"), read("c3", "c.py")], completed=2_100),
        step("msg_03", "msg_01", 3_000, [read("c4", "d.py"), tool("c5", "grep", input={"pattern": "def tau"})],
             completed=3_100),
    ])  # fmt: skip
    root = tree(flow.view(), folds={"said:msg_01": False})
    assert outline(root)[1:] == [
        "  ✓ Plot tau against p.",
        "    read ×3 at once",
        "      a.py · 100 chars",
        "      b.py · 100 chars",
        "      c.py · 100 chars",
        "    2 at once: read, grep",
        "      read d.py · 100 chars",
        "      grep def tau · 4 chars",
    ]
    assert find(root, "together:msg_02").kind == "together"


def test_a_call_that_failed_then_passed_folds_as_its_tries() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Run the tests."),
        step("msg_02", "msg_01", 2_000, [bash("c1", "pytest -q", exit=1)], completed=2_100),
        step("msg_03", "msg_01", 3_000, [bash("c2", "pytest -q")], completed=3_100),
    ])  # fmt: skip
    root = tree(flow.view(), folds={"said:msg_01": False})
    assert outline(root)[1:] == ["  ✓ Run the tests.", "    bash pytest -q · 2 tries [folded]"]
    tries = find(root, "tries:c1")
    assert [child.mark for child in tries.children] == ["✗", ""]


def test_steps_that_join_no_branch_hang_from_a_branch_of_their_own() -> None:
    root = tree(two_branches().view())
    other = root.children[0]
    assert (other.id, other.words, other.tone) == ("other", "before the todo list", "$clank-quiet")
    assert [child.words for child in other.children] == ["todowrite"]


def test_a_subagent_is_a_branch_of_its_own_with_its_own_flows_work_when_given() -> None:
    asked = tool("c1", "task", input={"description": "Find the helpers"}, title="Find the helpers",
                 metadata={"sessionId": "ses_child"}, output="z" * 1_200)  # fmt: skip
    flow = flow_of([user("msg_01", 1_000, "Plot."), step("msg_02", "msg_01", 2_000, [asked], completed=9_000)])
    child = Flow("ses_child", workspace="paper")
    child.history(page([
        user("msg_c1", 2_100, "Find the helpers", session="ses_child"),
        step("msg_c2", "msg_c1", 2_200, [tool("g1", "grep", input={"pattern": "plot"}),
                                         tool("g2", "grep", input={"pattern": "axis"})],
             completed=2_300, session="ses_child"),
        step("msg_c3", "msg_c1", 2_400, [read("r1", "plot.py")], completed=2_500, session="ses_child"),
    ]))  # fmt: skip
    flow.child("ses_child", {"title": "Find the helpers", "status": "idle", "steps": 2, "calls": 3})
    alone = tree(flow.view(), folds={"said:msg_01": False})
    branch = find(alone, "c1:ses_child")
    assert (branch.kind, branch.mark, branch.tone) == ("subagent", "◆", "$clank-brand")
    assert (branch.words, branch.detail) == ("subagent: Find the helpers", "2 steps, 3 calls · 1.2K chars back")
    assert branch.children == [], "its own flow not given: its brief only"
    given = tree(flow.view(), folds={"said:msg_01": False, "c1:ses_child": False},
                 subagents={"ses_child": child.view()})  # fmt: skip
    assert outline(given)[2:] == [
        "    ◆ subagent: Find the helpers · 2 steps, 3 calls · 1.2K chars back",
        "      grep ×2 at once",
        "        plot · 4 chars",
        "        axis · 4 chars",
        "      read plot.py · 100 chars",
    ]
    assert find(given, "c1:ses_child/r1").words == "read plot.py", "its nodes are its own, under its branch"


def test_a_note_joins_the_branch_of_the_step_under_way_when_it_was_sent_with_its_state() -> None:
    flow = Flow(SESSION)
    for line in lines([*updated(user("msg_01", 1_000, "Plot tau.")), status("busy"),
                       *updated(step("msg_02", "msg_01", 2_000, [bash("c1", "ls", state="running")])),
                       *updated(user("msg_03", 2_500, "Keep the grid to 3 sizes."))]):  # fmt: skip
        flow.heard(line)
    root = tree(flow.view())
    note = find(root, "msg_03")
    assert (note.kind, note.mark, note.words, note.detail) == ("note", "✎", "your note: Keep the grid to 3 sizes.",
                                                                "waiting")  # fmt: skip
    assert note.tone == "$clank-part-yours"
    assert [child.id for child in root.children] == ["said:msg_01"], "a note is no branch of its own"
    for line in lines(
        [
            *updated(step("msg_02", "msg_01", 2_000, [bash("c1", "ls")], completed=3_000)),
            *updated(step("msg_04", "msg_03", 3_100, [bash("c2", "python grid.py", state="running")])),
        ]
    ):
        flow.heard(line)  # fmt: skip
    root = tree(flow.view())
    assert [child.id for child in find(root, "said:msg_01").children] == ["c1", "msg_03", "c2"]
    assert find(root, "msg_03").detail == "", "read: nothing more to say"


def test_the_step_working_now_is_the_newest_node() -> None:
    flow = flow_of([user("msg_01", 1_000, "Plot tau."), step("msg_02", "msg_01", 2_000, [bash("c1", "ls")],
                                                              completed=2_100),
                    step("msg_03", "msg_01", 3_000, [text("t1", "thinking about it", "reasoning")])],
                   status("busy"))  # fmt: skip
    root = tree(flow.view())
    now = find(root, "msg_03")
    assert (now.kind, now.mark, now.tone, now.words) == ("step", "●", "$clank-now", "working")
    assert root.now == "msg_03"
    running = flow_of(
        [user("msg_01", 1_000, "Plot tau."), step("msg_02", "msg_01", 2_000, [bash("c1", "pytest", state="running")])],
        status("busy"),
    )
    root = tree(running.view())
    assert (root.now, find(root, "c1").mark, find(root, "c1").mark_tone) == ("c1", "●", "$clank-now")


def test_a_step_that_left_the_context_is_drawn_apart_from_one_stopped_and_kept() -> None:
    aborted = {"name": "MessageAbortedError", "data": {"message": "Aborted"}}
    looped = {"name": "APIError", "data": {"message": "Clank's loop guard stopped the answer"}}
    flow = flow_of([
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [text("p1", "Reading the data.")], completed=2_500, error=aborted),
        step("msg_03", "msg_01", 3_000, [bash("c1", "python loop.py")], completed=3_500, error=looped),
        step("msg_04", "msg_01", 4_000, [text("p2", "Done.")], completed=4_500),
    ])  # fmt: skip
    root = tree(flow.view(), folds={"said:msg_01": False})
    assert outline(root)[1:] == [
        "  ✓ Plot tau.",
        "    ⊘ stopped by you · kept in the context",
        "    bash python loop.py · 2 chars",
        "    ✗ failed: Clank's loop guard stopped the answer · not in the context",
        "    answered: Done.",
    ]
    assert find(root, "msg_03:end").tone == "$clank-failed"


def test_a_dead_end_ends_in_its_mark_and_a_failed_call_still_under_way_does_not() -> None:
    failing = [user("msg_01", 1_000, "Plot."), step("msg_02", "msg_01", 2_000, [bash("c1", "make", exit=2)])]
    root = tree(flow_of(failing, status("busy")).view())
    call = find(root, "c1")
    assert (call.mark, call.tone, call.detail, call.end) == ("✗", "$clank-failed", "exit 2", "")
    moved = flow_of([*failing, step("msg_03", "msg_01", 3_000, [bash("c2", "ls")])], status("busy"))
    call = find(tree(moved.view()), "c1")
    assert call.end == "⊘", "a later step began: the agent moved on"
    assert "exit status 2" in call.why, "an inference says why"
    assert "later step" in call.why


def test_steps_undone_are_a_side_lane_folded() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Plot."),
        step("msg_02", "msg_01", 2_000, [bash("c1", "ls")], completed=2_100),
        step("msg_03", "msg_01", 3_000, [bash("c2", "rm -r out")], completed=3_100),
        step("msg_04", "msg_01", 4_000, [bash("c3", "make")], completed=4_100),
    ])  # fmt: skip
    info = {"id": SESSION, "title": "Plot", "time": {"created": 1, "updated": 2}, "revert": {"messageID": "msg_03"}}
    for line in lines([{"type": "session.updated", "properties": {"sessionID": SESSION, "info": info}}]):
        flow.heard(line)
    root = tree(flow.view(), folds={"said:msg_01": False})
    assert outline(root)[1:] == [
        "  ✓ Plot.",
        "    bash ls · 2 chars",
        "    undone by you · 2 steps · u redoes [folded]",
    ]
    undone = find(root, "undone:c2")
    assert (undone.tone, [child.id for child in undone.children]) == ("$clank-dim", ["c2", "c3"])


def test_a_result_cleared_by_you_and_steps_undone_for_good_are_drawn_so() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Plot."),
        step("msg_02", "msg_01", 2_000, [read("c1", "data/tau.csv", 62_000), read("c4", "data/p.csv")],
             completed=2_100),
        step("msg_03", "msg_01", 3_000, [bash("c2", "rm -r out")], completed=3_100),
    ])  # fmt: skip
    flow.cleared("c1", 18_600)
    yours, theirs = read("c1", "data/tau.csv", 62_000), read("c4", "data/p.csv")
    yours["state"]["time"]["compacted"] = theirs["state"]["time"]["compacted"] = 2_500
    for line in lines([*updated(step("msg_02", "msg_01", 2_000, [yours, theirs], completed=2_100)),
                       reverted("msg_03")]):  # fmt: skip
        flow.heard(line)
    root = tree(flow.view(), folds={"said:msg_01": False, "together:msg_02": False})
    cleared = find(root, "c1")
    assert cleared.detail == "result cleared by you, freed about 18.6K", "an estimate, said so as the Guide says it"
    assert "about 18,600 tokens" in cleared.why, "an estimate, said so in its details"
    assert find(root, "c4").detail == "result cleared", "OpenCode's own clearing is not yours"
    assert find(root, "undone:c2").detail == "1 step · u redoes", "until your next message"
    for line in lines([removed("msg_03"), reverted()]):
        flow.heard(line)
    assert find(tree(flow.view()), "undone:c2").detail == "1 step · final", "OpenCode removed it: kept, for good"


def test_a_compaction_is_a_band_and_the_branches_above_it_fold_into_it() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [bash("c1", "ls")], completed=2_100),
        step("msg_03", "msg_01", 3_000, [bash("c2", "make")], completed=3_100),
        compacting("msg_04", "msg_03", 4_000),
        step("msg_05", "msg_04", 5_000, [text("s1", "The session so far.")], completed=5_500, summary=True),
        step("msg_06", "msg_01", 6_000, [bash("c3", "python plot.py")]),
    ], status("busy"))  # fmt: skip
    root = tree(flow.view())
    assert outline(root) == [
        "You",
        "  compacted by OpenCode · above it: 2 steps, 2 calls [folded]",
        "  ● Plot tau.",
        "    bash python plot.py · 2 chars",
    ]
    band = find(root, "msg_04")
    assert band.kind == "band"
    assert [child.id for child in band.children] == ["said:msg_01@msg_04"], "what it folds: the branches above it"
    opened = tree(flow.view(), folds={"msg_04": False, "said:msg_01@msg_04": False})
    assert outline(opened)[1:4] == ["  compacted by OpenCode · above it: 2 steps, 2 calls", "    ● Plot tau.",
                                    "      bash ×2 [folded]"]  # fmt: skip
    assert find(opened, "said:msg_01@msg_04").folds, "only the branch in progress after the last band is always open"


def test_a_branch_keeps_its_id_when_a_compaction_comes_so_the_owners_folds_and_cursor_stay_on_it() -> None:
    before = [
        user("msg_01", 1_000, "Plot tau."),
        step("msg_02", "msg_01", 2_000, [bash("c1", "ls")], completed=2_100),
        step("msg_03", "msg_01", 3_000, [bash("c2", "make")], completed=3_100),
    ]
    root = tree(flow_of(before, status("busy")).view())
    assert [child.id for child in root.children] == ["said:msg_01"]
    after = flow_of([
        *before,
        compacting("msg_04", "msg_03", 4_000),
        step("msg_05", "msg_04", 5_000, [text("s1", "The session so far.")], completed=5_500, summary=True),
        step("msg_06", "msg_01", 6_000, [bash("c3", "python plot.py")]),
    ], status("busy"))  # fmt: skip
    root = tree(after.view(), folds={"said:msg_01": True})
    assert [child.id for child in root.children] == ["msg_04", "said:msg_01"], "the branch in progress: the same id"
    assert [child.id for child in find(root, "msg_04").children] == ["said:msg_01@msg_04"], "its copy: the band's"
    assert root.children[1].children, "the owner's choice stays on the branch in progress (always open)"


def test_a_done_branch_folds_to_one_line_and_the_branch_in_progress_is_always_open() -> None:
    root = tree(two_branches().view(), folds={"todo:2": True})
    assert not find(root, "todo:2").folded, "the branch in progress is always open, whatever was asked"
    done = find(root, "todo:1")
    assert (done.folded, done.folds, done.detail) == (True, True, "2 calls")


def test_the_owners_fold_or_open_wins_over_the_default() -> None:
    root = tree(two_branches().view(), folds={"todo:1": False, "c4": True})
    done = find(root, "todo:1")
    assert (done.folded, done.detail, [child.id for child in done.children]) == (False, "", ["c2", "c3"])


def test_a_fold_that_holds_the_newest_node_is_open_by_default() -> None:
    flow = flow_of([
        user("msg_01", 1_000, "Read everything."),
        step("msg_02", "msg_01", 2_000, [read("c1", "a.py")], completed=2_100),
        step("msg_03", "msg_01", 3_000, [read("c2", "b.py")], completed=3_100),
        step("msg_04", "msg_01", 4_000, [tool("c3", "read", "running", input={"filePath": "c.py"})]),
    ], status("busy"))  # fmt: skip
    root = tree(flow.view())
    run = find(root, "run:c1")
    assert (run.folded, root.now) == (False, "c3")


def test_a_hold_is_drawn_held_by_you_from_when_to_when() -> None:
    begun = int(datetime(2026, 10, 20, 12, 20, tzinfo=UTC).timestamp() * 1000)
    flow = flow_of([user("msg_01", begun, "Plot tau."),
                    step("msg_02", "msg_01", begun + 60_000, [bash("c1", "pytest -q")], completed=begun + 400_000),
                    step("msg_03", "msg_01", begun + 420_000, [])], status("busy"))  # fmt: skip
    resumed = {"session": SESSION, "by": "you (console)", "since": stamp(begun + 120_000),
               "until": stamp(begun + 300_000), "how": "resumed", "seconds": 180.0}  # fmt: skip
    holding = {"session": SESSION, "by": "Clank (watch for)", "since": stamp(begun + 420_500)}
    flow.requests([{"id": "r-1", "time": stamp(begun + 60_100), "held": resumed},
                   {"id": "r-2", "time": stamp(begun + 420_100), "held": holding,
                    "phase": "held: its session is paused"}])  # fmt: skip
    root = tree(flow.view(), zone=UTC)
    held = find(root, "msg_02:held")
    assert (held.kind, held.mark, held.words, held.tone) == ("hold", "⏸", "held by you 12:22 to 12:25", "$clank-quiet")
    holding_now = find(root, "msg_03:held")
    assert (holding_now.mark, holding_now.words, holding_now.tone) == (
        "⏸", "held by a Watch for rule since 12:27", "$clank-attention"
    )  # fmt: skip
    assert find(root, "msg_03").words == "held: its session is paused"
    shown = outline(root)
    assert shown.index("    ⏸ held by you 12:22 to 12:25") < shown.index("    bash pytest -q · 2 chars"), (
        "the hold comes before its step's work, on its line"
    )  # fmt: skip


def test_a_hold_a_note_closed_is_drawn_until_the_note() -> None:
    begun = int(datetime(2026, 10, 20, 12, 20, tzinfo=UTC).timestamp() * 1000)
    flow = flow_of([user("msg_01", begun, "Plot tau."),
                    step("msg_02", "msg_01", begun + 120_000, [], completed=begun + 300_100),
                    user("msg_03", begun + 299_000, "Skip step 3."),
                    step("msg_04", "msg_03", begun + 310_000, [])], status("busy"))  # fmt: skip
    released = {"session": SESSION, "by": "you (console)", "since": stamp(begun + 120_100),
                "until": stamp(begun + 300_000), "how": "released", "seconds": 179.9}  # fmt: skip
    flow.requests([{"id": "r-1", "time": stamp(begun + 120_100), "held": released}])
    held = find(tree(flow.view(), zone=UTC), "msg_02:held")
    assert (held.mark, held.words, held.tone) == ("⏸", "held by you 12:22 to 12:25, until a note", "$clank-quiet")
