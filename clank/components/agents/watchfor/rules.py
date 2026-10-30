"""The Watch for rules (design 0012 §8, decision 0053): each a pure function of a session's flow, as the service keeps
it (`Flow.view()`: its head and its nodes in time order), and of the facts of the slot its requests reach (`Facts`).

`find` runs every rule, in §8's order, and returns what each found (`Found`): the rule, a key, the node the mark shows
on, and why, in words that name what it rests on: the facts it read and the rule's own count. A rule finds the same
things in the same flow however often it runs, each under the same key, so the marks kept in the service (`marks.py`)
take each once; a flow read again after a restart finds the same keys. Nodes a revert took back (`undone`) are left
out.

A rule over a stretch of calls (the same call three times or more in the last 12, four failures or more in the last 8,
one file edited six times or more in the last 30, as the prototype's monitor counted them) finds the call where a streak
reached its count, and again only after the count fell below it: a loop of twenty calls is one mark, not eighteen.

The facts come from the slot (design 0012 §4: whatever model is loaded): its window and output limit, the thinking
budget of its preset, and, once design 0012's step 3 says it, whose conversation the engine holds. A rule whose fact is
not known stays quiet: it never guesses a number. The compaction line is OpenCode's, the window less the output limit,
all of it since Clank lifts OpenCode's own cap of 32,000 above it (design 0012 §4.1, decision 0153: `counted_output`);
a step's size is OpenCode's total for it, else its prompt and answer added.
"""

import itertools
import json
import re
from collections import Counter
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from clank.components.agents.adapters.opencode import counted_output
from clank.components.agents.sessionflow.text import brief

LOOP_WORDS = "Clank's loop guard stopped the answer"  # the gateway's words (its `LOOPED`), as OpenCode keeps them
ENGINE_WORDS = ("the engine broke off", "the engine stopped before answering", "the engine did not answer")
SAME_CALL = (3, 12)  # the same call this many times or more in the last so many calls
FAILING = (4, 8)  # failures
ONE_FILE = (6, 30)  # edits of one file
NEAR = 0.9  # within a tenth of a budget
PACE_STEPS = 3  # the last finished steps whose growth gives the pace
RETRIES = 5  # OpenCode's attempts at most
EDITS = ("edit", "write", "multiedit", "patch", "apply_patch")
FILE = re.compile(r'"(?:filePath|file_path|path)"\s*:\s*"([^"]+)"')
WORKING = ("busy", "retry")
WHY = 160  # characters of a call's words a mark quotes


@dataclass(frozen=True)
class Rule:
    """A rule: its title, when it fires in words (design 0012 §8's table), and whose facts it reads."""

    title: str
    fires: str
    source: str


@dataclass(frozen=True)
class Facts:
    """The facts of the slot a session's requests reach; None for one not known."""

    context: int | None = None  # the window, in tokens
    output: int | None = None  # the output limit
    thinking: int | None = None  # the thinking budget (-1 or 0: none)
    holds: str | None = None  # the session whose conversation the engine holds


@dataclass(frozen=True)
class Found:
    """What a rule found: the rule, its key (the same however often it runs), the node its mark shows on, why, and
    what the mark offers (a note not read: "send again")."""

    rule: str
    key: str
    node: str
    why: str
    offer: str = ""


RULES: dict[str, Rule] = {
    "waiting_for_you": Rule("Waiting for you", "an approval or a question waits", "OpenCode"),
    "engine_broke_off": Rule("The engine broke off", "the last request ended in the engine's error", "the gateway"),
    "loop_guard_stopped": Rule("The loop guard stopped an answer", "a request ended model_looped", "the gateway"),
    "asks_about_a_repeat": Rule(
        "OpenCode asks about a repeated call",
        "OpenCode asks about the same call made again (its doom_loop ask); unanswered, it stalls a run left alone",
        "OpenCode",
    ),
    "same_call_again": Rule("The same call again", "the same call three times or more in the last 12", "the flow"),
    "failing_again": Rule("Failing again", "four failures or more in the last 8 calls", "the flow"),
    "one_file_again": Rule(
        "One file again and again", "one file edited six times or more in the last 30 calls", "the flow"
    ),
    "call_then_step_failed": Rule(
        "A call ran, then its step failed",
        "a step ended in an error after one of its calls had started: the file may have changed, and the model is "
        "not told",
        "the flow",
    ),
    "stopped_with_an_ask_waiting": Rule(
        "Stopped with an approval waiting",
        "the session stopped while an ask waits: the ask stays, and a later answer could still let it run",
        "OpenCode",
    ),
    "note_not_read": Rule("A note not read", "a note was stored, and the run ended without reading it", "the flow"),
    "retrying": Rule("OpenCode retrying", "OpenCode tries a request again, attempt n of at most 5", "OpenCode"),
    "compaction_near": Rule(
        "Compaction near", "the next step would likely pass the compaction line, at the last steps' pace", "the flow"
    ),
    "budget_near": Rule(
        "Thinking or answer near its budget",
        "the thinking or the answer is within a tenth of its budget",
        "the gateway",
    ),
    "engine_taken": Rule(
        "The engine taken by another session",
        "another session's request reset the engine's conversation, so the next step reads it again",
        "the gateway",
    ),
}


def find(view: dict[str, Any], facts: Facts) -> list[Found]:
    """What every rule finds in a flow's view, in §8's order."""
    nodes = [node for node in view.get("nodes") or [] if not node.get("undone")]
    head = view.get("head") or {}
    found: list[Found] = []
    for name, check in CHECKS.items():
        found += [Found(name, key, node, why, offer) for key, node, why, offer in check(head, nodes, facts)]
    return found


Hit = tuple[str, str, str, str]  # key, node, why, offer
Check = Callable[[dict[str, Any], list[dict[str, Any]], Facts], list[Hit]]


def _of(nodes: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [node for node in nodes if node.get("kind") == kind]


GIVEN = ("filePath", "path", "command", "pattern", "url", "query", "description", "name")  # what says most, in order
GIVEN_FIELD = re.compile(r'"(\w+)":\s*"((?:[^"\\]|\\.)*)"')  # a whole "key": "text" in an input cut short


def call_words(call: dict[str, Any]) -> str:
    """What a call does, briefly: its title; else what its input touches (the file, as a path in the folder, the
    command, the question asked), never the input whole ("(edit): {"filePath": ...}" in the events, 2026-10-26)."""
    if call.get("title"):
        return brief(str(call["title"]), WHY)
    given = _given(call.get("input"))
    questions = given.get("questions")
    if isinstance(questions, list) and questions and isinstance(questions[0], dict):
        return brief(str(questions[0].get("question") or ""), WHY)
    for key in GIVEN:
        value = given.get(key)
        if isinstance(value, str) and value:
            return brief(value.removeprefix("/workspace/"), WHY)
    return ""


def _given(found: Any) -> dict[str, Any]:
    """A call's input as fields: as given, else its JSON text read, else each whole field before the text was cut."""
    if isinstance(found, dict):
        return found
    if not isinstance(found, str):
        return {}
    try:
        read = json.loads(found)
    except ValueError:
        fields: dict[str, Any] = {}
        for match in GIVEN_FIELD.finditer(found):
            try:
                fields.setdefault(match.group(1), json.loads(f'"{match.group(2)}"'))
            except ValueError:
                continue
        return fields
    return read if isinstance(read, dict) else {}


def _words(call: dict[str, Any]) -> str:
    """What a call does, briefly, after a colon; nothing when nothing says it."""
    words = call_words(call)
    return f": {words}" if words else ""


def _waiting_for_you(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    hits: list[Hit] = []
    for call in _of(nodes, "call"):
        if call.get("asking") and call.get("permission") != "doom_loop":
            why = f"{call['tool']} asks for your approval ({call.get('permission') or 'a permission'}){_words(call)}"
            hits.append((f"ask:{call['asking']}", call["id"], why, ""))
        elif call.get("tool") == "question" and call.get("status") in ("pending", "running"):
            hits.append((f"question:{call['id']}", call["id"], f"the model asks you a question{_words(call)}", ""))
    return hits


def _broke(step: dict[str, Any]) -> str:
    """The engine's error that ended a step's request (or the step, in the gateway's words), "" for none."""
    request = step.get("request") or {}
    if request.get("broken"):
        return str(request["broken"])
    if request.get("error") and not request.get("looped"):
        return str(request["error"])
    error = str(step.get("error") or "")
    return error if any(words in error for words in ENGINE_WORDS) else ""


def _engine_broke_off(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    hits: list[Hit] = []
    for step in _of(nodes, "step"):
        if said := _broke(step):
            hits.append(
                (f"broke:{step['id']}", step["id"], f"step {step['n']}'s request ended: {brief(said, WHY)}", "")
            )
    return hits


def _loop_guard_stopped(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    hits: list[Hit] = []
    for step in _of(nodes, "step"):
        looped = str((step.get("request") or {}).get("looped") or "")
        if not looped and not str(step.get("error") or "").startswith(LOOP_WORDS):
            continue
        what = looped or "it repeated itself"
        where = "is not in the context" if step.get("context") == "left" else "stays in the context"
        why = f"step {step['n']}'s answer was stopped by the loop guard: {brief(what, WHY)}; that answer {where}"
        hits.append((f"looped:{step['id']}", step["id"], why, ""))
    return hits


def _asks_about_a_repeat(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    return [
        (f"ask:{call['asking']}", call["id"],
         f"OpenCode asks whether {call['tool']} may run again, the same call made again and again: "
         f"{call_words(call)}", "")
        for call in _of(nodes, "call")
        if call.get("asking") and call.get("permission") == "doom_loop"
    ]  # fmt: skip


def streaks(
    calls: list[dict[str, Any]], value: Callable[[dict[str, Any]], Hashable | None], count: int, window: int
) -> list[tuple[int, Hashable, list[int]]]:
    """Each call where a value's count in the last `window` calls reached `count`, not while it stayed there: its index,
    the value, and the indexes of the calls that count."""
    found: list[tuple[int, Hashable, list[int]]] = []
    on: set[Hashable] = set()
    values = [value(call) for call in calls]
    for index in range(len(calls)):
        start = max(0, index - window + 1)
        counted = Counter(each for each in values[start : index + 1] if each is not None)
        on = {each for each in on if counted.get(each, 0) >= count}
        mine = values[index]
        if mine is not None and counted[mine] >= count and mine not in on:
            on.add(mine)
            found.append((index, mine, [at for at in range(start, index + 1) if values[at] == mine]))
    return found


def _numbers(indexes: list[int]) -> str:
    """Calls by their numbers in the session, in words: "calls 4, 7 and 12"."""
    shown = [str(index + 1) for index in indexes]
    return "calls " + (", ".join(shown[:-1]) + " and " + shown[-1] if len(shown) > 1 else shown[0])


def _same_call_again(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    calls = _of(nodes, "call")
    count, window = SAME_CALL
    hits: list[Hit] = []
    for index, _, counted in streaks(calls, lambda call: (call.get("tool"), call.get("input")), count, window):
        call = calls[index]
        said = brief(call.get("input") or call.get("title") or "", WHY)
        why = (f"{call['tool']} {said} {len(counted)} times in the last {window} calls ({_numbers(counted)}); the "
               f"rule: {count} or more in the last {window}")  # fmt: skip
        hits.append((f"same:{call['id']}", call["id"], why, ""))
    return hits


def _failing_again(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    calls = _of(nodes, "call")
    count, window = FAILING
    hits: list[Hit] = []
    for index, _, counted in streaks(calls, lambda call: True if call.get("failed") else None, count, window):
        tools = ", ".join(str(calls[at]["tool"]) for at in counted)
        why = (f"{len(counted)} of the last {window} calls failed ({tools}: {_numbers(counted)}); the rule: {count} or "
               f"more in the last {window}")  # fmt: skip
        hits.append((f"failing:{calls[index]['id']}", calls[index]["id"], why, ""))
    return hits


def edited(call: dict[str, Any]) -> str | None:
    """The file a call edits ("" for an edit whose file cannot be read, None for a call that edits none)."""
    if call.get("tool") not in EDITS:
        return None
    text = str(call.get("input") or "")
    try:
        given = json.loads(text)
    except ValueError:
        given = None
    if isinstance(given, dict):
        for key in ("filePath", "file_path", "path"):
            if isinstance(given.get(key), str):
                return str(given[key])
    match = FILE.search(text)
    return match.group(1) if match else (str(call.get("title") or "") or None)


def _one_file_again(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    calls = _of(nodes, "call")
    count, window = ONE_FILE
    hits: list[Hit] = []
    for index, file, counted in streaks(calls, edited, count, window):
        why = (f"{file} edited {len(counted)} times in the last {window} calls ({_numbers(counted)}); the rule: "
               f"{count} or more in the last {window}")  # fmt: skip
        hits.append((f"file:{calls[index]['id']}", calls[index]["id"], why, ""))
    return hits


def _call_then_step_failed(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    calls = {call["id"]: call for call in _of(nodes, "call")}
    hits: list[Hit] = []
    for step in _of(nodes, "step"):
        if step.get("ended") != "failed":
            continue
        ran = [calls[id] for id in step.get("calls") or [] if id in calls and calls[id].get("started")]
        if ran:
            names = ", ".join(f"{call['tool']} {call_words(call)}".rstrip() for call in ran[:3])
            why = (f"step {step['n']} ended in an error ({brief(step.get('error') or '', WHY)}) after its calls had "
                   f"started ({names}); the model is not told what they did")  # fmt: skip
            hits.append((f"ran:{step['id']}", step["id"], why, ""))
    return hits


def _stopped_with_an_ask_waiting(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    if head.get("status") in WORKING:
        return []
    return [
        (f"stopped:{call['asking']}", call["id"],
         f"the session stopped while {call['tool']}'s ask ({call.get('permission') or 'a permission'}) waits: the ask "
         f"stays, and a later answer could still let it run: {call_words(call)}", "")
        for call in _of(nodes, "call")
        if call.get("asking")
    ]  # fmt: skip


def _note_not_read(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    return [
        (f"note:{said['id']}", said["id"],
         f"your note \"{brief(said.get('text') or '', WHY)}\" was stored, and the run ended without reading it",
         "send again")
        for said in _of(nodes, "said")
        if said.get("note") and said.get("state") == "not read"
    ]  # fmt: skip


def _retrying(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    if head.get("status") != "retry":
        return []
    steps = _of(nodes, "step")
    newest = steps[-1]["id"] if steps else ""
    said = brief(head.get("retry") or "", WHY)
    why = f"OpenCode tries again, attempt {head.get('attempt') or '?'} of at most {RETRIES}" + (
        f": {said}" if said else ""
    )
    return [(f"retry:{newest}", newest, why, "")]


def size(step: dict[str, Any]) -> int:
    """A finished step's size in the context: OpenCode's total for it, else its prompt and its answer added."""
    tokens = step.get("tokens") or {}
    if tokens.get("total"):
        return int(tokens["total"])
    cache = tokens.get("cache") or {}
    parts = (tokens.get("input"), tokens.get("output"), tokens.get("reasoning"), cache.get("read"), cache.get("write"))
    return sum(int(part or 0) for part in parts)


def _compaction_near(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    if not facts.context or not facts.output:
        return []
    counted = counted_output(facts.output)
    line = facts.context - counted
    bands = [index for index, node in enumerate(nodes) if node.get("kind") == "band"]
    since = nodes[bands[-1] + 1 :] if bands else nodes
    finished = [step for step in _of(since, "step")
                if step.get("ended") == "finished" and not step.get("summary") and size(step)]  # fmt: skip
    if not finished:
        return []
    sizes = [size(step) for step in finished[-(PACE_STEPS + 1) :]]
    growth = [later - earlier for earlier, later in itertools.pairwise(sizes) if later > earlier]
    pace = sum(growth) // len(growth) if growth else 0
    used = sizes[-1]
    if used + pace < line:
        return []
    why = (f"{used:,} of {line:,} tokens used before OpenCode compacts (the window {facts.context:,} less the output "
           f"limit {counted:,}), growing about {pace:,} a step: the next step would likely pass "
           f"it")  # fmt: skip
    return [(f"compaction:{len(bands)}", finished[-1]["id"], why, "")]


def _budget_near(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    hits: list[Hit] = []
    for step in _of(nodes, "step"):
        request = step.get("request") or {}
        if not request.get("id"):
            continue
        about = "about " if request.get("flying") else ""
        thinking = int((request.get("counts") or {}).get("thinking") or 0)
        if facts.thinking and facts.thinking > 0 and thinking >= NEAR * facts.thinking:
            why = (f"step {step['n']}'s thinking reached {about}{thinking:,} tokens of its {facts.thinking:,}-token "
                   f"budget; the rule: within a tenth of it")  # fmt: skip
            hits.append((f"thinking:{request['id']}", step["id"], why, ""))
        written = int(request.get("tokens") or 0)
        if facts.output and written >= NEAR * facts.output:
            why = (f"step {step['n']}'s answer reached {about}{written:,} tokens of the output limit, "
                   f"{facts.output:,} (its thinking, its text and its calls); the rule: within a tenth of "
                   f"it")  # fmt: skip
            hits.append((f"answer:{request['id']}", step["id"], why, ""))
    return hits


def _engine_taken(head: dict[str, Any], nodes: list[dict[str, Any]], facts: Facts) -> list[Hit]:
    session = str(head.get("session") or "")
    if not facts.holds or facts.holds == session or head.get("status") not in WORKING:
        return []
    steps = _of(nodes, "step")
    newest = steps[-1]["id"] if steps else ""
    why = (f"the engine holds another session's conversation now ({facts.holds}), so this session's next step reads "
           f"its context again")  # fmt: skip
    return [(f"taken:{facts.holds}:{newest}", newest, why, "")]


CHECKS: dict[str, Check] = {
    "waiting_for_you": _waiting_for_you,
    "engine_broke_off": _engine_broke_off,
    "loop_guard_stopped": _loop_guard_stopped,
    "asks_about_a_repeat": _asks_about_a_repeat,
    "same_call_again": _same_call_again,
    "failing_again": _failing_again,
    "one_file_again": _one_file_again,
    "call_then_step_failed": _call_then_step_failed,
    "stopped_with_an_ask_waiting": _stopped_with_an_ask_waiting,
    "note_not_read": _note_not_read,
    "retrying": _retrying,
    "compaction_near": _compaction_near,
    "budget_near": _budget_near,
    "engine_taken": _engine_taken,
}
