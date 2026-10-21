"""Test support: sessions generated from a seed, for the Monitor's edge cases (design 0012 §11 step 6, revised at the
owner's comment on the prototype: "we need to be sure we are testing out edge cases for dealing with this in
practice"), and the checks every drawing of a flow must pass.

`generated(seed)` makes a session as OpenCode keeps it, read by step 5's `Flow`: up to 60 steps, each with up to 8
calls made at once, of every kind of tool (an MCP server's with a long name too); long paths and commands, wide
characters; calls that fail, bash exit codes, a step stopped or failing; subagents, and subagents within those, up to
three deep, each with its own session; notes sent while a step was under way; compactions; a revert; the branches from
the owner's messages, a todo list or a Clank plan. It gives the session's view and its subagents' views, by session.
`junctions_line_up` and `drawn_once` say what is wrong with a drawing ("" or [] when nothing is).
"""

import json
import random
from typing import Any

from rich.cells import get_character_cell_size

from clank.components.agents.console.flowchart import Drawn
from clank.components.agents.console.flowtree import Node
from clank.components.agents.sessionflow.flow import Flow
from clank.console.style import current
from tests.support.flowlines import SESSION, compacting, lines, page, status, step, text, tool, user

TOOLS = ["read", "grep", "glob", "bash", "edit", "write", "webfetch", "todowrite", "notion_search",
         "a_very_long_mcp_server_name_with_a_very_long_tool_name_for_testing"]  # fmt: skip
WORDS = ["src", "tests", "data", "a_rather_long_folder_name_that_goes_on", "數據", "分析", "plot", "fit", "τ", "café"]
PLAN = "docs/plans/generated.md"


def _path(rng: random.Random) -> str:
    return "/".join(rng.choice(WORDS) for _ in range(rng.randint(1, 9))) + rng.choice([".py", ".csv", ".md", ""])


def _call(rng: random.Random, id: str, last: bool) -> dict[str, Any]:
    name = rng.choice(TOOLS)
    state = rng.choice(["completed"] * 6 + ["error", "running" if last else "completed"])
    size = rng.choice([0, 12, 999, 1000, 18_600, 99_999, 100_000, 2_500_000])
    if name == "bash":
        said = [*WORDS, "python", "-m", "pytest", "--verbose"]
        command = " ".join(rng.choice(said) for _ in range(rng.randint(1, 40)))
        return tool(id, "bash", state, input={"command": command}, metadata={"exit": rng.choice([0, 0, 0, 1, 2, 137])},
                    output="o" * size, error="Tool execution aborted")  # fmt: skip
    if name == "todowrite":
        todos = [{"content": f"Item {n}", "status": "pending", "priority": "low"} for n in range(rng.randint(1, 5))]
        return tool(id, name, state, input={"todos": todos}, output=json.dumps(todos))
    path = _path(rng)
    return tool(id, name, state, input={"filePath": path, "pattern": path}, title=rng.choice([path, ""]),
                output="x" * size, error=rng.choice(["", "File not found: " + path]))  # fmt: skip


def _session(rng: random.Random, session: str, start: int, depth: int, subagents: dict[str, dict[str, Any]]) -> Flow:
    """One session's flow, its subagents' flows put in `subagents`."""
    messages: list[dict[str, Any]] = []
    clock = start
    said = f"{session}_m0"
    named = rng.random() < 0.2 and depth == 0
    words = f"Implement the plan in this file: {PLAN}" if named else " ".join(rng.choice(WORDS) for _ in range(30))
    messages.append(user(said, clock, words, session=session))
    steps = rng.randint(0, 60 if depth == 0 else 8)
    children: list[tuple[str, int]] = []
    for n in range(steps):
        clock += rng.randint(100, 5000)
        last = n == steps - 1
        made = rng.choice([0, 1, 1, 1, 1, 2, 3, 8])
        parts: list[dict[str, Any]] = []
        for k in range(made):
            id = f"{session}_c{n}_{k}"
            if depth < 3 and rng.random() < 0.08:
                child = f"{session}_s{n}_{k}"
                parts.append(
                    tool(
                        id,
                        "task",
                        "completed",
                        input={"description": "find " + _path(rng)},
                        title="find " + _path(rng),
                        metadata={"sessionId": child},
                        output="t" * 1200,
                    )
                )
                children.append((child, clock))  # fmt: skip
            else:
                parts.append(_call(rng, id, last))
        if not made:
            parts.append(text(f"{session}_t{n}", " ".join(rng.choice(WORDS) for _ in range(rng.randint(0, 50)))))
        error = None
        if rng.random() < 0.06:
            error = {"name": rng.choice(["MessageAbortedError", "APIError"]), "data": {"message": "x" * 200}}
        completed = None if last and rng.random() < 0.5 else clock + rng.randint(10, 3000)
        messages.append(step(f"{session}_a{n}", said, clock, parts, completed=completed, error=error, session=session))
        if completed is not None and rng.random() < 0.08:
            note = f"{session}_n{n}"
            messages.append(user(note, clock + 5, "a note " + "x" * rng.randint(0, 300), session=session))
        if rng.random() < 0.05:
            clock += 10
            band = f"{session}_b{n}"
            messages.append(compacting(band, f"{session}_a{n}", clock, auto=rng.random() < 0.5, session=session))
            messages.append(step(f"{session}_y{n}", band, clock + 1, [text(f"{session}_ys{n}", "summary")],
                                 completed=clock + 2, summary=True, session=session))  # fmt: skip
        if rng.random() < 0.05 and depth == 0:
            clock += 10
            said = f"{session}_u{n}"
            messages.append(user(said, clock, "and then " + "y" * rng.randint(0, 200), session=session))
    flow = Flow(session, workspace="w")
    flow.history(page(messages))
    if named:
        boxes = "\n".join(f"- [{'x' if rng.random() < 0.4 else ' '}] Step {n} " + "z" * rng.randint(0, 90)
                          for n in range(rng.randint(1, 12)))  # fmt: skip
        flow.planned(f"---\nkind: plan\nstatus: implementing\n---\n\n# A plan\n\n## Steps\n\n{boxes}\n")
    heard: list[dict[str, Any]] = []
    if rng.random() < 0.6:
        heard.append(status("busy", session=session))
    if rng.random() < 0.1 and len(messages) > 3:
        revert = rng.choice(messages[1:])["info"]["id"]
        info = {"id": session, "title": "t", "time": {"created": 1, "updated": 2}, "revert": {"messageID": revert}}
        heard.append({"type": "session.updated", "properties": {"sessionID": session, "info": info}})
    for line in lines(heard):
        flow.heard(line)
    for child, began in children:
        own = _session(rng, child, began, depth + 1, subagents)
        brief = own.view()["head"]
        flow.child(child, {key: brief.get(key) for key in ("title", "status", "steps", "calls")})
        subagents[child] = own.view()
    return flow


def generated(seed: int) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """A session generated from a seed, and its subagents' sessions."""
    rng = random.Random(seed)
    subagents: dict[str, dict[str, Any]] = {}
    flow = _session(rng, SESSION, 1_760_000_000_000, 0, subagents)
    return flow.view(), subagents


def junctions_line_up(drawn: Drawn) -> list[str]:
    """What is wrong with the junctions: each `┬`, `├` and `│` has a line below it in its column (`│`, `├` or `└`),
    each `├`, `└` and `│` has one above it (`┬`, `├`, `│`) or its node's first cell (children under their node)."""
    glyphs = current().tree
    rows = [cells(line.plain) for line in drawn.lines]
    starts = [{span.start for span in spans if span.id} for spans in drawn.spans]
    down, up = {glyphs.down, glyphs.branch, glyphs.last}, {glyphs.split, glyphs.branch, glyphs.down}
    wrong = []

    def at(row: int, column: int) -> str:
        return rows[row][column] if 0 <= row < len(rows) and column < len(rows[row]) else " "

    for row, line in enumerate(rows):
        connectors = {column for span in drawn.spans[row] if not span.id for column in range(span.start, span.end)}
        for column, glyph in enumerate(line):
            if column not in connectors:
                continue
            if glyph in (glyphs.split, glyphs.branch, glyphs.down) and at(row + 1, column) not in down:
                wrong.append(f"line {row}, column {column}: {glyph} leads down to nothing")
            if (
                glyph in (glyphs.branch, glyphs.last, glyphs.down)
                and at(row - 1, column) not in up
                and (row == 0 or column not in starts[row - 1])
            ):
                wrong.append(f"line {row}, column {column}: {glyph} hangs from nothing")
    return wrong


def cells(text: str) -> list[str]:
    """A line as its cells: a wide character in its first cell, "" in the next."""
    found: list[str] = []
    for each in text:
        found += [each] + [""] * (get_character_cell_size(each) - 1)
    return found


def drawn_once(drawn: Drawn, root: Node) -> list[str]:
    """What is wrong with which nodes are drawn: each node not hidden by a fold (or by a node cut short for room) is
    drawn in exactly one span, the nodes in reading order go down the lines, and the spans of a line follow each other
    without a gap or an overlap, as wide as the line."""
    wrong = []
    seen: dict[str, int] = {}
    for row, spans in enumerate(drawn.spans):
        at = 0
        for span in spans:
            if span.start != at or span.end <= span.start:
                wrong.append(f"line {row}: a span at {span.start} after {at}")
            at = span.end
            if span.id:
                seen[span.id] = seen.get(span.id, 0) + 1
        if at != drawn.lines[row].cell_length:
            wrong.append(f"line {row}: its spans cover {at} of its {drawn.lines[row].cell_length} cells")
    wanted: list[str] = []

    def visit(node: Node) -> None:
        wanted.append(node.id)
        if not node.folded and node.id not in drawn.short:
            for child in node.children:
                visit(child)

    visit(root)
    wrong += [f"{id} drawn {seen.get(id, 0)} times" for id in wanted if seen.get(id, 0) != 1]
    wrong += [f"{id} drawn, though hidden" for id in seen if id not in wanted]
    rows = [drawn.row[id] for id in drawn.order]
    if rows != sorted(rows):
        wrong.append("the reading order goes up a line")
    return wrong
