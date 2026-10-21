"""Test support: the sessions the Monitor's boards draw, made as OpenCode keeps them and read by step 5's `Flow`, so the
Flow panel's tests draw what the service would serve (design 0012 §6, board A).

`board_a()` is board A's session ("Plan a new simulation study", in the workspace `myproject`): a todo list of five
items, the first two done, the third in progress; a glob, three reads made at once and an MCP server's tool; four
`bash` calls in a row; a subagent that finds the observables (its own flow: six `grep` and two `read`); a call stopped
in a loop, then the work going on; the owner's note, read by the step thinking now. `every_kind()` holds every kind of
node the Flow panel draws: calls made at once, a subagent with a subagent of its own, a call that failed then passed,
a dead end, a step stopped by the owner, one the loop guard stopped, a compaction, a second message of the owner's, a
note not read, a step undone. Each gives the session's view and its subagents' views, by session.
"""

import json
from datetime import UTC, datetime
from typing import Any

from clank.components.agents.console.flowtree import Node, tree
from clank.components.agents.sessionflow.flow import Flow
from tests.support.flowlines import SESSION, compacting, lines, page, status, step, text, tool, user

START = int(datetime(2026, 10, 19, 11, 58, tzinfo=UTC).timestamp() * 1000)
OBSERVABLES = "ses_observables"
HELPERS = "ses_helpers"
LABELS = "ses_labels"
LOOPED = {"name": "APIError", "data": {"message": "Clank's loop guard stopped the answer: it repeated itself"}}
ABORTED = {"name": "MessageAbortedError", "data": {"message": "Aborted"}}
TODOS = [
    "Read the simulator and last study", "List the observables", "Draft the parameter grid", "Estimate run times",
    "Write the plan file",
]  # fmt: skip


def at(seconds: float) -> int:
    """A moment of the session, in ms, `seconds` after it began."""
    return START + int(seconds * 1000)


def listed(done: int) -> list[dict[str, str]]:
    """Board A's todo list with its first `done` items completed and the next in progress."""
    return [
        {"content": content, "status": "completed" if index < done else "in_progress" if index == done else "pending",
         "priority": "high"}
        for index, content in enumerate(TODOS)
    ]  # fmt: skip


def wrote(id: str, todos: list[dict[str, str]]) -> dict[str, Any]:
    return tool(id, "todowrite", input={"todos": todos}, output=json.dumps(todos))


def bash(id: str, command: str, *, exit: int = 0, size: int = 200, state: str = "completed") -> dict[str, Any]:
    return tool(id, "bash", state, input={"command": command}, metadata={"exit": exit}, output="o" * size,
                error="Tool execution aborted")  # fmt: skip


def read(id: str, path: str, size: int) -> dict[str, Any]:
    return tool(id, "read", input={"filePath": f"/workspace/{path}"}, title=path, output="r" * size)


def grep(id: str, pattern: str, size: int = 300) -> dict[str, Any]:
    return tool(id, "grep", input={"pattern": pattern}, title=pattern, output="g" * size)


def task(id: str, session: str, title: str, size: int, state: str = "completed") -> dict[str, Any]:
    return tool(id, "task", state, input={"description": title, "prompt": title}, title=title,
                metadata={"sessionId": session}, output="t" * size)  # fmt: skip


def flow_of(session: str, messages: list[dict[str, Any]], *heard: dict[str, Any]) -> Flow:
    flow = Flow(session, workspace="myproject")
    flow.history(page(messages))
    for line in lines(list(heard)):
        flow.heard(line)
    return flow


def board_a() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Board A's session, at 12:21, and its subagent's."""
    messages, sub = board_a_messages()
    flow = flow_of(SESSION, messages, status("busy"))
    flow.requests([{"id": "r21", "time": datetime.fromtimestamp(at(480.2) / 1000, UTC).isoformat(), "seconds": 36.1,
                    "phase": "answering", "tokens": 1415, "calls": [], "session": SESSION}])  # fmt: skip
    flow.child(OBSERVABLES, {"title": "find observables", "status": "idle", "steps": 8, "calls": 8})
    child = flow_of(OBSERVABLES, sub)
    return flow.view(), {OBSERVABLES: child.view()}


def board_a_messages() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Board A's messages as OpenCode keeps them, and its subagent's."""
    # fmt: off
    messages = [
        user("msg_01", at(0), "Plan a new simulation study for myproject: which observables, which sizes, how long."),
        step("msg_02", "msg_01", at(10), [wrote("c01", listed(0))], completed=at(14)),
        step("msg_03", "msg_01", at(20), [tool("c02", "glob", input={"pattern": "**/*.py"}, title="**/*.py",
                                               output="p" * 900)], completed=at(24)),
        step("msg_04", "msg_01", at(30), [read("c03", "src/simulator.py", 18_600), read("c04", "README.md", 2_100),
                                          read("c05", "studies/notes.md", 4_000)], completed=at(40)),
        step("msg_05", "msg_01", at(50), [tool("c06", "myproject_capabilities", input={}, title="capabilities",
                                               output="m" * 6_400)], completed=at(60)),
        step("msg_06", "msg_01", at(120), [wrote("c07", listed(1))], completed=at(124)),
        *[
            step(f"msg_{7 + n:02d}", "msg_01", at(130 + 20 * n), [bash(f"c{8 + n:02d}", command)],
                 completed=at(140 + 20 * n))
            for n, command in enumerate([
                "python -m myproject observables --list", "python -m myproject describe magnetization",
                "python -m myproject describe energy", "python -m myproject describe gap",
            ])
        ],
        step("msg_11", "msg_01", at(220), [task("c12", OBSERVABLES, "find observables", 1_200)], completed=at(300)),
        *[
            step(f"msg_{12 + n:02d}", "msg_01", at(310 + 10 * n), [read(f"c{13 + n:02d}", path, 3_000)],
                 completed=at(315 + 10 * n))
            for n, path in enumerate(["docs/observables.md", "docs/estimators.md", "src/measure.py", "src/grid.py"])
        ],
        step("msg_16", "msg_01", at(360), [wrote("c17", listed(2))], completed=at(364)),
        step("msg_17", "msg_01", at(370), [read("c18", "studies/notes.md", 14_200)], completed=at(380)),
        step("msg_18", "msg_01", at(390), [bash("c19", "python -m myproject sweep --sizes 8 16 32 64 128 256",
                                                state="error")], completed=at(405), error=LOOPED),
        step("msg_19", "msg_01", at(420), [bash("c20", "ls studies/", size=100)], completed=at(470)),
        user("msg_20", at(440), "Keep the grid to 3 sizes."),
        step("msg_21", "msg_20", at(480), [text("t21", "The grid: 16, 32 and 64.", "reasoning")]),
    ]
    sub = [
        user("msg_s01", at(221), "Find the observables the simulator can measure.", session=OBSERVABLES),
        *[
            step(f"msg_s{2 + n:02d}", "msg_s01", at(230 + 5 * n), [grep(f"g{n}", pattern)], completed=at(232 + 5 * n),
                 session=OBSERVABLES)
            for n, pattern in enumerate(["def measure_", "class Observable", "observables =", "def energy",
                                         "def magnetization", "def gap"])
        ],
        step("msg_s08", "msg_s01", at(270), [read("r1", "src/measure.py", 3_000)], completed=at(275),
             session=OBSERVABLES),
        step("msg_s09", "msg_s01", at(280), [read("r2", "src/observables.py", 5_000)], completed=at(285),
             session=OBSERVABLES),
        step("msg_s10", "msg_s01", at(290), [text("s10", "Three observables: magnetization, energy, gap.")],
             completed=at(298), session=OBSERVABLES),
    ]
    # fmt: on
    return [timed(message, n) for n, message in enumerate(messages)], [timed(message, 0) for message in sub]


def timed(message: dict[str, Any], n: int) -> dict[str, Any]:
    """A message whose calls ran when its step did, a second apart, as OpenCode times them (the Tool calls panel shows
    when each started); a finished step of the session's `n`th message counted as OpenCode counts its tokens, the
    session growing about 7,000 tokens a message from 9,000, as board A's spark draws it (its growth)."""
    created = int(message["info"]["time"]["created"])
    calls = [part for part in message["parts"] if part["type"] == "tool"]
    for index, part in enumerate(calls):
        start = created + 1000 * (index + 1)
        part["state"]["time"] = {"start": start, **({"end": start + 500} if "end" in part["state"]["time"] else {})}
    info = message["info"]
    if n and info["role"] == "assistant" and info["time"].get("completed") and not info.get("error"):
        prompt = 9_000 + 7_000 * n
        info["tokens"] = {"total": prompt + 300, "input": 2_000, "output": 300, "reasoning": 0,
                          "cache": {"read": prompt - 2_000, "write": 0}}  # fmt: skip
    return message


def every_kind() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """A session with every kind of node, its subagents' sessions too; idle, its last step undone."""
    # fmt: off
    s = SESSION
    messages = [
        user("msg_01", at(0), "Plot tau against p for n=8 and n=16, with the axis labeled."),
        step("msg_02", "msg_01", at(10), [read("c01", "data/tau.csv", 24_000), read("c02", "plot.py", 3_100),
                                          read("c03", "README.md", 900)], completed=at(20)),
        step("msg_03", "msg_01", at(30), [read("c04", "src/fit.py", 7_700), grep("c05", "def tau")],
             completed=at(40)),
        step("msg_04", "msg_01", at(50), [task("c06", HELPERS, "find the plotting helpers", 2_300)], completed=at(90)),
        step("msg_05", "msg_01", at(100), [bash("c07", "pytest -q tests/test_plot.py", exit=1, size=4_000)],
             completed=at(110)),
        step("msg_06", "msg_01", at(120), [bash("c08", "pytest -q tests/test_plot.py", size=600)], completed=at(130)),
        step("msg_07", "msg_01", at(140), [bash("c09", "make figure", exit=2, size=1_800)], completed=at(150)),
        step("msg_08", "msg_01", at(160), [text("p08", "I will draw it by hand instead.")], completed=at(170),
             error=ABORTED),
        step("msg_09", "msg_01", at(180), [tool("c10", "edit", input={"filePath": "/workspace/plot.py"},
                                                title="plot.py", output="Edit applied.")], completed=at(190)),
        step("msg_10", "msg_01", at(200), [bash("c11", "python plot.py --n 8 16 " + "--verbose " * 12, state="error")],
             completed=at(215), error=LOOPED),
        compacting("msg_11", "msg_10", at(220)),
        step("msg_12", "msg_11", at(225), [text("s12", "The session so far: ...")], completed=at(240), summary=True),
        step("msg_13", "msg_01", at(250), [tool("c12", "notion_search", input={"query": "tau figure style"},
                                                output="n" * 6_400)], completed=at(260)),
        user("msg_14", at(300), "Now label the axis: p on x, tau on y."),
        step("msg_15", "msg_14", at(310), [tool("c13", "edit", input={"filePath": "/workspace/plot.py"},
                                                title="plot.py", output="Edit applied.")], completed=at(330)),
        user("msg_16", at(320), "Use LaTeX for tau."),
        step("msg_17", "msg_14", at(340), [text("p17", "The axis is labeled: p on x, $\\tau$ on y.")],
             completed=at(350)),
        user("msg_18", at(360), "Also save it as a PDF."),
        step("msg_19", "msg_18", at(370), [bash("c14", "python plot.py --pdf", size=80)], completed=at(380)),
    ]
    flow = flow_of(s, messages)
    info = {"id": s, "title": "Plot tau", "time": {"created": 1, "updated": 2}, "revert": {"messageID": "msg_19"}}
    for line in lines([{"type": "session.updated", "properties": {"sessionID": s, "info": info}}]):
        flow.heard(line)
    flow.child(HELPERS, {"title": "find the plotting helpers", "status": "idle", "steps": 3, "calls": 3})
    helpers = flow_of(HELPERS, [
        user("msg_h01", at(51), "Find the plotting helpers.", session=HELPERS),
        step("msg_h02", "msg_h01", at(55), [grep("h1", "def plot_"), grep("h2", "import matplotlib")],
             completed=at(60), session=HELPERS),
        step("msg_h03", "msg_h01", at(62), [task("h3", LABELS, "check the axis labels", 500)], completed=at(80),
             session=HELPERS),
    ])
    helpers.child(LABELS, {"title": "check the axis labels", "status": "idle", "steps": 1, "calls": 1})
    labels = flow_of(LABELS, [
        user("msg_l01", at(63), "Check the axis labels.", session=LABELS),
        step("msg_l02", "msg_l01", at(65), [read("l1", "src/axes.py", 1_100)], completed=at(70), session=LABELS),
    ])
    # fmt: on
    return flow.view(), {HELPERS: helpers.view(), LABELS: labels.view()}


def opened(view: dict[str, Any], subagents: dict[str, dict[str, Any]]) -> dict[str, bool]:
    """Every fold of a flow opened (a folded node keeps its children in the tree, so one look finds them all)."""
    found: dict[str, bool] = {}

    def visit(node: Node) -> None:
        if node.folds:
            found[node.id] = False
        for child in node.children:
            visit(child)

    visit(tree(view, {}, subagents))
    return found
