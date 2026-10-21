"""The Monitor's flow as a tree (design 0012 §6.2-§6.4, decision 0050): what the Flow panel draws of a session's flow,
before it is laid out in lines (`flowchart.py`).

The flow is the service's (`sessionflow/flow.py`, its `view()`, as `GET /agents/flow/{workspace}/{session}` serves it).
The owner's message is the root ("You"); the main branches (the flow's items: a Clank plan's steps, the todo list's
items, or the owner's messages) are its children, each marked by its state (done, now, planned on a line not taken
yet, canceled); steps that join none hang from a branch of their own ("before the plan"). A branch holds its work in
time order:

- a call: its tool and what it does (its command, its title, its file or its pattern) and the size of its result,
  colored by its kind (the style's `calls`: reading, running, editing, an MCP server's tool), running ●, failed ✗, a
  dead end (failed, and a later step began) ending in ⊘;
- a step's calls made at once, one node that fans out to each (`read ×3 at once`);
- a run of one tool in a row, folded into one node (`bash ×4`), and a call that failed then passed, into its tries; a
  failed call never folds into a run, so a failure stays in sight;
- a subagent (◆, from the `task` call that started it), with its own flow's work under it when its flow is given
  (`subagents`, by session; within a subagent, its own subagents the same way);
- the owner's note (✎), in the branch of the step under way when it was sent, saying when it waits or was not read;
  the owner's other messages, in the branch of the step that answers them, when they are not the branches themselves;
- a step without calls: the step working now (its phase, from the gateway's request it pairs with), its answer, or
  how it ended; a step that failed is drawn apart from one the owner stopped, the first out of the context, the second
  kept when it had content (step 5's rule); a step that failed or was stopped after its calls ends in a node of its own;
- the steps a revert undid, a side lane in the `dim` color, folded, saying that u redoes them until the owner's next
  message, then that they are final (design 0012 §9.5);
- a call whose result is cleared says so, "result cleared by you, freed about 18.6K" when the Guide cleared it (the
  tokens it freed, estimated, said as the Guide says it; design 0012 §9.7);
- a step's request the gateway held while its session was paused (design 0012 §9.4), on the step's line before its work,
  ⏸ "held by you 12:22 to 12:25", or "held by you since 12:22" in `attention` while it is held (its times in the
  console's zone, `zone`).

A compaction is a band: a child of the root where it happened, holding the branches above it, folded (design 0012 §6.3:
"everything above it folded"), compacted "by OpenCode" or "by you" (one the Guide asked for, §9.6). Each node says
whether it folds and whether it is folded: a done or canceled branch, a run, tries, steps undone, a band and a finished
subagent fold by default; the branch in progress after the last band never folds; a fold that holds the newest node
(`Node.now` on the root, never a step undone) opens while that node works (running, or waiting for an approval); the
owner's own choice (`folds`, by node id) wins over the rest. A folded branch says how many calls it holds. What an
inference rests on (a dead end, a guessed branch, a note not read) is in `why`, for the node's details. Ids are the
flow's own (a call's, a step's), a group's made from its first (`run:<call>`, `together:<step>`), a branch's its item's
key (`todo:2`) after the last band, and its item's key and its band's id inside a band (`todo:2@<band>`), so the branch
in progress keeps its id (the owner's folds and cursor on it) when a compaction comes; a subagent's work under its
node's (`<subagent>/<call>`).
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from clank.components.agents.sessionflow.text import brief
from clank.components.workspaces.service import WORKSPACE
from clank.console.style import current
from clank.console.text import count
from clank.kernel.clock import from_text

TEXT, QUIET, DIM = "$clank-text", "$clank-quiet", "$clank-dim"
GOOD, NOW, FAILED, ATTENTION = "$clank-good", "$clank-now", "$clank-failed", "$clank-attention"
YOURS, ANSWER, SUBAGENT = "$clank-part-yours", "$clank-part-text", "$clank-brand"
READING = frozenset({"read", "glob", "grep", "list", "ls", "webfetch", "websearch", "codesearch", "lsp"})
RUNNING = frozenset({"bash"})
EDITING = frozenset({"edit", "write", "patch", "multiedit", "apply_patch"})
OWN = frozenset({"task", "todowrite", "todoread", "question", "skill", "invalid", "batch", "plan_enter", "plan_exit"})
NOTHING_TO_SAY = frozenset({"todowrite", "todoread"})  # their input is a whole list: the tool's name says it
WHAT = ("filePath", "file_path", "path", "pattern", "url", "query", "description", "prompt", "command")
PAIR = re.compile(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)')  # a key and its text, in an input cut short
OTHER = {"plan": "before the plan", "todo": "before the todo list"}
DEEPEST = 8  # subagents within subagents drawn at most this deep (the '/' in a node's id count how deep)
WORKING = ("busy", "retry")


@dataclass
class Node:
    """One node of the drawn flow."""

    id: str
    kind: str  # root, branch, other, call, together, run, tries, subagent, note, said, step, end, undone, band, hold
    words: str
    tone: str = TEXT
    mark: str = ""
    mark_tone: str = ""  # the mark's color when it is not the words' ("" for the same)
    detail: str = ""  # what it says after its words, in `quiet`: a size, a count, a state
    detail_tone: str = QUIET
    children: list["Node"] = field(default_factory=list)
    folds: bool = False  # whether ← and → fold and open it
    folded: bool = False
    line: str = "solid"  # how the line from its parent reaches it: solid, or "not yet" (┄)
    end: str = ""  # what ends it: the dead end's mark
    why: str = ""  # what an inference rests on
    at: list[Any] = field(default_factory=list)  # its place in time, the flow's
    now: str = ""  # on the root: the newest node's id
    tool: str = ""
    what: str = ""
    step: str = ""  # the flow's step it belongs to
    undone: bool = False
    final: bool = False  # undone, and removed by OpenCode since: kept in the flow for good (design 0012 §9.5)
    default: bool = False  # folded unless the owner said otherwise
    always_open: bool = False
    when_folded: str = ""  # what it adds to its detail while folded


def tree(
    view: dict[str, Any],
    folds: dict[str, bool] | None = None,
    subagents: dict[str, dict[str, Any]] | None = None,
    zone: tzinfo | None = None,
) -> Node:
    """The flow as a tree: the owner's message the root, the main branches its children (design 0012 §6.2); its times
    in `zone` (None: this computer's)."""
    return _Tree(view, folds or {}, subagents or {}, zone).root()


def what(call: dict[str, Any]) -> str:
    """What a call does, briefly: a command's line, else its title, else its file, pattern or address ("" for a call
    whose name says it all)."""
    tool = str(call.get("tool") or "")
    if tool in NOTHING_TO_SAY:
        return ""
    given = _given(call.get("input"))
    if tool == "bash" and given.get("command"):
        return flat(given["command"])
    if call.get("title"):
        return flat(call["title"])
    for key in WHAT:
        if isinstance(given.get(key), str) and given[key].strip():
            return flat(given[key].removeprefix(WORKSPACE + "/"))
    said = flat(call.get("input"))
    return "" if said in ("", "{}") else said


def tone_of(tool: str) -> str:
    """A tool's color: its kind's, from the style's `calls` (one OpenCode does not have itself is an MCP server's)."""
    if tool in READING:
        return "$clank-call-reading"
    if tool in RUNNING:
        return "$clank-call-running"
    if tool in EDITING:
        return "$clank-call-editing"
    return TEXT if tool in OWN else "$clank-call-mcp"


def chars(length: int) -> str:
    """A text's size in characters, briefly: 812 chars, 18.6K chars, 1.2M chars."""
    if length < 1000:
        return count(length, "char")
    if length < 100_000:
        return f"{length / 1000:.1f}K chars"
    if length < 1_000_000:
        return f"{length / 1000:.0f}K chars"
    return f"{length / 1_000_000:.1f}M chars"


def short(tokens: int) -> str:
    """A count of tokens, briefly: 812, 18.6K, 1.2M."""
    if tokens < 1000:
        return str(tokens)
    if tokens < 1_000_000:
        return f"{tokens / 1000:.1f}K"
    return f"{tokens / 1_000_000:.1f}M"


def flat(text: Any) -> str:
    """A text on one line, without control characters, briefly."""
    return "".join(each for each in brief(text) if unicodedata.category(each) != "Cc")


def _given(input: Any) -> dict[str, Any]:
    """A call's input as the bridge keeps it (JSON, perhaps cut short), as a mapping."""
    if isinstance(input, dict):
        return input
    try:
        found = json.loads(str(input or ""))
    except ValueError:
        return {key: value for key, value in PAIR.findall(str(input or ""))}
    return found if isinstance(found, dict) else {}


def _at(node: dict[str, Any]) -> list[Any]:
    return list(node.get("at") or [])


def _before(one: list[Any], other: list[Any]) -> bool:
    try:
        return bool(one < other)
    except TypeError:
        return False


class _Facts:
    """What one flow says, by step: its calls, the subagents from its calls and those not from a call yet."""

    def __init__(self, view: dict[str, Any]) -> None:
        nodes = view.get("nodes") or []
        self.calls: dict[str, list[dict[str, Any]]] = {}
        self.subagents: dict[str, dict[str, Any]] = {}
        self.loose: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            if node.get("kind") == "call":
                self.calls.setdefault(str(node.get("step")), []).append(node)
            elif node.get("kind") == "subagent":
                if node.get("call"):
                    self.subagents[str(node["call"])] = node
                else:
                    self.loose.setdefault(str(node.get("step")), []).append(node)
        self.steps = [node for node in nodes if node.get("kind") == "step" and not node.get("summary")]


class _Tree:
    """Builds the tree of one view, then settles its folds."""

    def __init__(
        self,
        view: dict[str, Any],
        folds: dict[str, bool],
        subagents: dict[str, dict[str, Any]],
        zone: tzinfo | None = None,
    ) -> None:
        self.view, self.folds, self.subagents, self.zone = view, folds, subagents, zone
        self.marks, self.glyphs = current().marks, current().tree

    def root(self) -> Node:
        view, facts = self.view, _Facts(self.view)
        head = view.get("head") or {}
        nodes = sorted(view.get("nodes") or [], key=_at)
        source = str(head.get("branches") or "said")
        said = [node for node in nodes if node.get("kind") == "said"]
        noted = {f"said:{node['id']}" for node in said if node.get("note")}
        items = [dict(item) for item in view.get("items") or [] if item.get("key") not in noted]
        if source == "said" and items and head.get("status") in WORKING:  # a note is no branch: the last one works
            for item in items:
                item["state"] = "now" if item is items[-1] else ("done" if item["state"] == "now" else item["state"])
        placed = self._placed(nodes, said, items, source)
        bands = [node for node in nodes if node.get("kind") == "band"]
        per: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for node in nodes:
            if node["id"] in placed:
                era = sum(1 for band in bands if _before(_at(band), _at(node)))
                per.setdefault((era, placed[node["id"]]), []).append(node)
        root = Node("root", "root", "You", YOURS, always_open=True)
        seen = {key for _, key in per}
        for era in range(len(bands) + 1):
            last = era == len(bands)
            where = "" if last else f"@{bands[era]['id']}"  # a copy in a band: the band's; the last era: its own
            branches = []
            if per.get((era, "")):
                branches.append(self._other(where, per[(era, "")], facts, source))
            for item in items:
                entries = per.get((era, item["key"]), [])
                if entries or (last and (item["key"] not in seen or item.get("state") == "now")):
                    branches.append(self._branch(item, where, entries, facts, last=last, said=source == "said"))
            if last:
                root.children += branches
            else:
                root.children.append(self._band(bands[era], branches))
        newest = self._newest(root)
        root.now = newest[-1].id if newest else ""
        live = bool(newest) and newest[-1].mark in (self.marks.on, self.marks.asks)
        self._settle(root, {node.id for node in newest} if live else set())
        return root

    def _placed(
        self, nodes: list[dict[str, Any]], said: list[dict[str, Any]], items: list[dict[str, Any]], source: str
    ) -> dict[str, str]:
        """The branch each step, note and message of the owner's belongs to ("" for none), by its id: a step its own,
        a note that of the step under way when it was sent, a message that of the step that answers it."""
        keys = {item["key"] for item in items}
        first = said[0]["id"] if said else ""
        placed: dict[str, str] = {}
        noted: dict[str, str] = {}
        last: str | None = None
        for node in nodes:
            kind = node.get("kind")
            if kind == "step" and not node.get("summary"):
                key = str(node.get("item") or "")
                key = noted.get(key, key if key in keys else "")
                placed[node["id"]] = last = key
            elif kind == "said" and node.get("note"):
                key = last if last is not None else ""
                placed[node["id"]] = noted[f"said:{node['id']}"] = key
            elif kind == "said" and source != "said" and node["id"] != first:
                answered = next((each for each in nodes if each.get("kind") == "step" and each.get("said") == node["id"]
                                 and not each.get("summary")), None)  # fmt: skip
                key = str(answered.get("item") or "") if answered is not None else (last or "")
                placed[node["id"]] = key if key in keys else ""
        return placed

    def _branch(
        self, item: dict[str, Any], where: str, entries: list[dict[str, Any]], facts: _Facts, *, last: bool, said: bool
    ) -> Node:
        state = str(item.get("state") or "planned")
        marks = {"done": self.marks.done, "now": self.marks.on}
        tones = {"done": GOOD, "now": NOW}
        node = Node(f"{item['key']}{where}", "branch", flat(item.get("title")), tones.get(state, QUIET),
                    marks.get(state, self.marks.off), why=str(item.get("why") or ""))  # fmt: skip
        if said:
            node.mark_tone, node.tone = node.tone, YOURS
        if state == "planned":
            node.line = "not yet"
        node.detail = " · ".join(
            word for word, holds in (("a guess", item.get("guessed")), ("canceled", state == "canceled")) if holds
        )
        node.children = self._work(entries, facts, "")
        node.default = state in ("done", "canceled")
        node.always_open = last and state == "now"
        node.when_folded = count(_calls(node), "call")
        return node

    def _other(self, where: str, entries: list[dict[str, Any]], facts: _Facts, source: str) -> Node:
        node = Node(f"other{where}", "other", OTHER.get(source, "other steps"), QUIET, default=True)
        node.children = self._work(entries, facts, "")
        node.when_folded = count(_calls(node), "call")
        return node

    def _band(self, band: dict[str, Any], branches: list[Node]) -> Node:
        who = "OpenCode" if band.get("auto") and not band.get("asked") else "you"
        words = f"compacted by {who}" if band.get("done") else f"compacting, asked by {who}"
        steps = {step for branch in branches for step in _steps(branch)}
        detail = f"above it: {count(len(steps), 'step')}, {count(sum(_calls(each) for each in branches), 'call')}"
        return Node(band["id"], "band", words, QUIET, detail=detail, children=branches, at=_at(band), default=True)

    def _work(self, entries: list[dict[str, Any]], facts: _Facts, prefix: str) -> list[Node]:
        """A branch's work, in time order: each step's units, the owner's notes and messages; steps undone gathered
        into a side lane, then tries and runs folded."""
        units: list[Node] = []
        for entry in entries:
            if entry.get("kind") == "step":
                units += self._step(entry, facts, prefix)
            elif entry.get("note"):
                units.append(self._note(entry, prefix))
            else:
                units.append(Node(prefix + entry["id"], "said", f"you: {flat(entry.get('text'))}", YOURS,
                                  at=_at(entry), undone=bool(entry.get("undone")),
                                  final=bool(entry.get("final"))))  # fmt: skip
        found: list[Node] = []
        index = 0
        while index < len(units):
            end = index + 1
            lane = (units[index].undone, units[index].final)
            while end < len(units) and (units[end].undone, units[end].final) == lane:
                end += 1
            if units[index].undone:
                found.append(self._undone(units[index:end], prefix))
            else:
                found += self._runs(self._tries(units[index:end], prefix), prefix)
            index = end
        return found

    def _step(self, step: dict[str, Any], facts: _Facts, prefix: str) -> list[Node]:
        """A step's units: its calls (made at once: one node that fans out), its subagents, and, without calls, what
        it is doing or how it ended; after calls, how it ended when it failed or was stopped."""
        calls = facts.calls.get(step["id"], [])
        made = [self._call(call, facts, prefix) for call in calls]
        loose = [self._subagent(each, None, prefix) for each in facts.loose.get(step["id"], [])]
        units = [self._together(step, made, prefix)] if len(made) > 1 else made
        units += loose
        ended = self._ended(step, prefix, after=bool(units))
        if ended is not None:
            units.append(ended)
        held = self._held(step, prefix)
        if held is not None:
            units.insert(0, held)
        for unit in units:
            unit.undone, unit.final, unit.step = bool(step.get("undone")), bool(step.get("final")), step["id"]
        return units

    def _ended(self, step: dict[str, Any], prefix: str, *, after: bool) -> Node | None:
        """How a step ended, when it is to be said: working, answered, failed or stopped; after calls, only failed or
        stopped."""
        ended, kept = step.get("ended"), step.get("context") == "in"
        id, at = prefix + step["id"] + (":end" if after else ""), [*_at(step), 1_000_000_000] if after else _at(step)
        if ended == "failed":
            return Node(id, "end" if after else "step", f"failed: {flat(step.get('error'))}", FAILED, self.marks.failed,
                        detail="not in the context" if not kept else "", at=at)  # fmt: skip
        if ended == "stopped":
            return Node(id, "end" if after else "step", "stopped by you", ATTENTION, self.glyphs.dead_end, at=at,
                        detail="kept in the context" if kept else "not in the context")  # fmt: skip
        if after:
            return None
        if ended == "working":
            request = step.get("request") or {}
            flying = bool(request.get("flying"))
            words = str(request.get("phase") or "working") if flying else "working"
            tokens = request.get("tokens") if flying else None
            return Node(id, "step", words, NOW, self.marks.on, detail=f"about {tokens:,} tokens" if tokens else "",
                        at=at)  # fmt: skip
        if step.get("text"):
            return Node(id, "step", f"answered: {flat(step['text'])}", ANSWER, at=at)
        return Node(id, "step", "finished without text", QUIET, at=at)

    def _held(self, step: dict[str, Any], prefix: str) -> Node | None:
        """The gateway's hold of the step's request, while its session was paused (design 0012 §9.4): by whom, from
        when to when (and "until a note" when a note closed it), or since when while it is held."""
        held = (step.get("request") or {}).get("held")
        if not isinstance(held, dict) or not held.get("since"):
            return None
        who, since = _who(str(held.get("by") or "")), self._clock(str(held["since"]))
        if held.get("until"):
            closed = ", until a note" if held.get("how") == "released" else ""
            words, tone = f"held by {who} {since} to {self._clock(str(held['until']))}{closed}", QUIET
        else:
            words, tone = f"held by {who} since {since}", ATTENTION
        return Node(prefix + step["id"] + ":held", "hold", words, tone, self.marks.held, at=_at(step))

    def _clock(self, text: str) -> str:
        """A time the gateway wrote, as the hour and minute in the console's zone."""
        try:
            return from_text(text).astimezone(self.zone).strftime("%H:%M")
        except ValueError:
            return "?"

    def _call(self, call: dict[str, Any], facts: _Facts, prefix: str) -> Node:
        sub = facts.subagents.get(str(call["id"]))
        if sub is not None:
            return self._subagent(sub, call, prefix)
        tool, said = str(call.get("tool") or ""), what(call)
        node = Node(prefix + call["id"], "call", f"{tool} {said}".strip(), tone_of(tool), at=_at(call), tool=tool,
                    what=said)  # fmt: skip
        status, length, exit = call.get("status"), call.get("length"), call.get("exit")
        if call.get("failed"):
            node.mark, node.tone = self.marks.failed, FAILED
            reason = f"exit status {exit}" if isinstance(exit, int) and exit != 0 else "an error"
            node.detail = f"exit {exit}" if isinstance(exit, int) and exit != 0 else flat(call.get("error")) or "failed"
            if call.get("dead_end"):
                node.end = self.glyphs.dead_end
                node.why = f"it ended in {reason} and the agent moved on: a later step began, so it is a dead end"
        elif status == "running":
            node.mark, node.mark_tone = self.marks.on, NOW
        elif status == "pending":
            node.mark, node.mark_tone = self.marks.off, QUIET
        elif isinstance(length, int):
            node.detail = chars(length)
        if call.get("asking"):
            node.mark, node.mark_tone, node.detail = self.marks.asks, ATTENTION, "waits for your approval"
            node.detail_tone = ATTENTION
        if call.get("cleared"):
            node.detail = "result cleared"
            freed = call.get("freed")
            if call.get("cleared_by"):
                node.detail = (
                    f"result cleared by you, freed about {short(freed)}" if isinstance(freed, int) else node.detail
                )
                node.why = (f"you cleared its result (design 0012 §9.7): about {freed:,} tokens freed, an estimate"
                            if isinstance(freed, int) else "you cleared its result (design 0012 §9.7)")  # fmt: skip
        return node

    def _subagent(self, sub: dict[str, Any], call: dict[str, Any] | None, prefix: str) -> Node:
        """A subagent: its task, its brief (steps, calls, what it gave back) and, its flow given, its own work, down
        to `DEEPEST` subagents within subagents (each adds a '/' to its work's ids)."""
        id = prefix + sub["id"]
        at = _at(call) if call is not None else _at(sub)
        node = Node(id, "subagent", f"subagent: {flat(sub.get('title'))}", SUBAGENT, self.marks.brand, at=at,
                    tool="task", what=flat(sub.get("title")))  # fmt: skip
        status = str((call or {}).get("status") or "")
        said = []
        if sub.get("steps") is not None:
            said.append(f"{count(int(sub['steps']), 'step')}, {count(int(sub.get('calls') or 0), 'call')}")
        if status == "completed" and isinstance((call or {}).get("length"), int):
            said.append(f"{chars(int(call['length']))} back")  # type: ignore[index]
        if call is not None and call.get("failed"):
            node.tone, node.mark = FAILED, self.marks.failed
            said.append(flat(call.get("error")) or "failed")
        node.detail = " · ".join(said)
        view = self.subagents.get(str(sub.get("session")))
        if view is not None and id.count("/") < DEEPEST:
            facts = _Facts(view)
            notes = [each for each in view.get("nodes") or [] if each.get("kind") == "said" and each.get("note")]
            entries = sorted([*facts.steps, *notes], key=_at)
            node.children = self._work(entries, facts, id + "/")
        node.default = status in ("completed", "error") or (call is None and sub.get("state") not in WORKING)
        return node

    def _together(self, step: dict[str, Any], made: list[Node], prefix: str) -> Node:
        tools = list(dict.fromkeys(node.tool for node in made))
        if len(tools) == 1 and tools[0] != "task":
            words, tone = f"{tools[0]} ×{len(made)} at once", tone_of(tools[0])
            for node in made:
                node.words = node.what or node.tool
        else:
            words, tone = f"{len(made)} at once: {', '.join(tools)}", TEXT
        return Node(f"{prefix}together:{step['id']}", "together", words, tone, children=made, at=made[0].at)

    def _note(self, note: dict[str, Any], prefix: str) -> Node:
        state = str(note.get("state") or "")
        node = Node(prefix + note["id"], "note", f"your note: {flat(note.get('text'))}", YOURS, self.marks.note,
                    at=_at(note), undone=bool(note.get("undone")))  # fmt: skip
        if state in ("waiting", "not read"):
            node.detail, node.detail_tone = state, ATTENTION
        if state == "not read":
            node.why = "the run ended without reading it: a note sent as a run ends can miss its last step"
        return node

    def _tries(self, units: list[Node], prefix: str) -> list[Node]:
        """A call that failed, then the same call again until it passed: one node, its tries."""
        found: list[Node] = []
        index = 0
        while index < len(units):
            first = units[index]
            end = index
            while end < len(units) and _again(units[end], first) and units[end].mark == self.marks.failed:
                end += 1
            if end > index and end < len(units) and _again(units[end], first) and units[end].mark != self.marks.failed:
                tried = units[index : end + 1]
                for node in tried:
                    node.words = node.what or node.tool
                found.append(Node(f"{prefix}tries:{first.id.removeprefix(prefix)}", "tries",
                                  f"{first.tool} {first.what}".strip(), tone_of(first.tool),
                                  detail=f"{len(tried)} tries", children=tried, at=first.at, tool=first.tool,
                                  default=True, step=first.step))  # fmt: skip
                index = end + 1
            else:
                found.append(first)
                index += 1
        return found

    def _runs(self, units: list[Node], prefix: str) -> list[Node]:
        """A run of one tool in a row, none of its calls failed: one node (`bash ×4`)."""
        found: list[Node] = []
        index = 0
        while index < len(units):
            first = units[index]
            end = index + 1
            while end < len(units) and _runs_on(units[end], first, self.marks.failed):
                end += 1
            if end - index > 1 and _runs_on(first, first, self.marks.failed):
                run = units[index:end]
                for node in run:
                    node.words = node.what or node.tool
                found.append(Node(f"{prefix}run:{first.id.removeprefix(prefix)}", "run", f"{first.tool} ×{len(run)}",
                                  tone_of(first.tool), children=run, at=first.at, tool=first.tool, default=True,
                                  step=first.step))  # fmt: skip
                index = end
            else:
                found.append(first)
                index += 1
        return found

    def _undone(self, units: list[Node], prefix: str) -> Node:
        """Steps a revert undid: a side lane, dim, folded; u redoes them until OpenCode removed them, then final."""
        for each in units:
            for node in _walk(each):
                node.tone = node.mark_tone = node.detail_tone = DIM
        steps = {node.step for node in units if node.step}
        final = all(node.final for node in units)
        how = "final" if final else "u redoes"
        kept = "your next message made it final: OpenCode removed what it took back, kept here as your guidance's log"
        why = kept if final else "until your next message, u redoes it (OpenCode's unrevert)"
        return Node(f"{prefix}undone:{units[0].id.removeprefix(prefix)}", "undone", "undone by you", DIM,
                    detail=f"{count(len(steps), 'step')} · {how}", children=units, at=units[0].at, default=True,
                    undone=True, final=final, why=why)  # fmt: skip

    def _newest(self, root: Node) -> list[Node]:
        """The path from the root to the newest node that has a place in time and nothing under it, never one undone."""
        best: list[Node] = []

        def visit(node: Node, path: list[Node]) -> None:
            nonlocal best
            path = [*path, node]
            if node.undone:
                return
            if not node.children:
                if node.at and (not best or not _before(node.at, best[-1].at)):
                    best = path
                return
            for child in node.children:
                visit(child, path)

        visit(root, [])
        return best

    def _settle(self, node: Node, holding: set[str]) -> None:
        """Each node's folds: the owner's choice, else its default, a fold that holds the newest node open; the branch
        in progress never folded."""
        for child in node.children:
            self._settle(child, holding)
        node.folds = bool(node.children) and not node.always_open
        wanted = self.folds.get(node.id)
        node.folded = node.folds and (wanted if wanted is not None else node.default and node.id not in holding)
        if node.folded and node.when_folded:
            node.detail = " · ".join(each for each in (node.detail, node.when_folded) if each)


def _who(by: str) -> str:
    """Who paused, as a hold says it: you (from any client), a Watch for rule, or as the gateway was told."""
    if by == "you" or by.startswith("you ("):
        return "you"
    if by == "Clank (watch for)":
        return "a Watch for rule"
    return by or "Clank"


def _walk(node: Node) -> list[Node]:
    """A node and every node under it."""
    found = [node]
    for child in node.children:
        found += _walk(child)
    return found


def _steps(node: Node) -> set[str]:
    """The steps a node's work comes from (a subagent's own steps are its own)."""
    found = {node.step} if node.step else set()
    if node.kind != "subagent":
        for child in node.children:
            found |= _steps(child)
    return found


def _calls(node: Node) -> int:
    """How many calls a node holds (a subagent counts as its `task` call; its own calls are its own)."""
    if node.kind in ("call", "subagent"):
        return 1
    return sum(_calls(child) for child in node.children)


def _again(node: Node, first: Node) -> bool:
    """Whether a node is the same call as the first: the same tool doing the same."""
    return node.kind == "call" and node.tool == first.tool and node.what == first.what


def _runs_on(node: Node, first: Node, failed: str) -> bool:
    """Whether a node goes on a run of the first's tool: a call of it that did not fail."""
    return node.kind == "call" and node.tool == first.tool and node.mark != failed
