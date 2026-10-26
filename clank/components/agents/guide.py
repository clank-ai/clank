"""The Guide (design 0012 §9.1-§9.7, §11 steps 9 to 11): what the owner, or a Watch for rule, does to the session the
Monitor follows, its root (§3): **Stop now** (`.`), **a note** (`m`), **Compact now** (`k`), **Pause after this step**
(`p`, `pausing.py`: the gateway's hold), **Undo the last step** (`u`) and **Drop an item** (`x`).

`offer` is a pure function of the session's flow (its view), the server that runs it, its context totals and the
gateway's requests of it that ended: each action with its key; whether it can run now and, when not, why; what it does,
briefly (`brief`), in words and as the exact call to OpenCode; what it costs: the tokens the engine reads again
(estimates, *to measure*, §10) and the time that takes at the engine's reading speed (`reading_speed`: llama.cpp's own
`prompt_per_second`, else the tokens a step read anew over its time to the first token, from the gateway's records), or
that the time is not known; whether it asks first (all but Stop, which must be quick); and the state of its last run,
read from the flow.

- **Stop** (§9.2): OpenCode's `abort` of the session, then a reject of what waits in it and its subagents (one ask
  rejected rejects the session's others, so no later "once" approves one). It runs while the session works or an ask
  waits; nothing is read again. States: stopping, then stopped once the session is idle; failed, with the reason.
- **A note** (§9.3, decision 0054): a real message of the owner's, sent with `prompt_async` and the agent and the model
  of the session's last message of the owner (the bridge reads them however far back; its answer says which it used),
  beginning with what it is about ("About step 12, `bash pytest -q`: …") when the client names it. While a call waits
  for approval, the note rejects that call instead, the note its reason: the model reads it as the call's answer, and
  no message is added. On an idle session it starts a run. Its cost, estimated: everything since the owner's previous
  message is read again (the totals' `used`, less the prompt of the first step after that message). States: written;
  waiting (stored, not read yet); read by step n; answered (read, and the run ended); not read (the run ended without
  it: send it again).
- **Compact now** (§9.6): OpenCode's `summarize`, with provider `clank`, the agent role as the model and `auto` on,
  asked without waiting (the bridge's own process holds the request until the run ends). No busy check: OpenCode
  compacts at the next step, and the work goes on after it. Its cost: a full reading of the history (the totals'
  `used`). States: asked; compacting (its band begun); done. One asked and not done is not asked again; its band is
  drawn "by you" (`SessionFlows.compaction_asked`), as OpenCode's own compactions are drawn "by OpenCode".

- **Pause after this step** (§9.4, decision 0055): `pausing.Pausing`, which the Guide lists after Compact now and
  before Undo, its state read from the gateway each time (pausing after this step, held with its timer, resumed); `p`
  again resumes.
- **Undo the last step** (§9.5, decision 0056): OpenCode's `revert` at the last part of the step before it (the flow's
  `cut`), never by message id alone, which would take back the whole turn; a step before it with no text and no call
  before its last part is taken back with it, since OpenCode would turn a revert there into one of the turn. When the
  owner's message (a note included, in OpenCode's order) comes just before, undoing the step alone is refused with that
  reason (`refused`) and **the turn** is offered: a revert at the oldest of those messages, whose text comes back in the
  note line. Refused while the session works (OpenCode refuses: stop it first), across a compaction, and when Clank's
  flow holds no message before the step. Its preview (`takes`), from the flow: the steps, the files their patch parts
  list (what OpenCode restores), the owner's messages and their words, and the subagents those steps started (their own
  sessions' changes are not taken back). While a revert is pending it is **Redo**, OpenCode's `unrevert`, until the
  owner's next message makes the undo final. Its cost is to measure. States: undone, the turn undone, final (OpenCode
  removed what it took back), redone.
- **Drop an item** (§9.7): OpenCode's own clearing of a finished call's result, the whole part written back with its
  `state.time.compacted` set; refused for a call not in the flow, undone, cleared already, not finished, in the step in
  progress (OpenCode's routes do not check), in a step that left the context, or before a compaction that summarized
  it. What it frees, estimated: the result's characters at the model's calibration for tool results, else Clank's plain
  0.3 tokens a character (decision 0087); what it costs: everything after it read once (the totals' `used`, less the
  prompt of the first step after the call's), nothing when no step has read it yet. Without an item, whether any result
  can be cleared. The drop is final until bringing a result back is measured. States: clearing, then cleared once
  OpenCode says so.

`Guide`, kept by the agents service, gathers what `offer` reads and acts through the session bridge (`sessions.py`),
which records each call as `agents.acted` with who made it: the owner from the console or the phone, or a rule. An
action that cannot run is refused with its reason (`GuideError`), and nothing is sent. What each action did last in a
session is kept in memory, as the flows are (decision 0049), and forgotten with the session's flow. A Watch for rule's
note goes through the Guide too (`Ruled`), as the rule, and never rejects a call the owner may still approve; so does
its pause. An undo carries the revert the owner confirmed and is refused when the session moved on since (what was
confirmed is what is done); OpenCode's answer to a revert or an unrevert is shown in the flow at once
(`SessionFlows.reverted`), and the words of the owner's messages an undo took back are read back from the session's
newest page of history, whole up to the bridge's cap, else the flow's words of them, said cut (`whole`). A drop tells
the flow what it freed (`SessionFlows.cleared`), drawn "by you" once OpenCode says the result is cleared.
"""

import json
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from clank.components.agents.adapters.opencode import PROVIDER
from clank.components.agents.context import ROLE, reported
from clank.components.agents.sessionflow.text import brief
from clank.components.agents.watchfor.marks import WATCH, Unavailable
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.agents.pausing import Pausing
    from clank.components.agents.review import Review
    from clank.components.agents.sessionflow.kept import SessionFlows
    from clank.components.agents.sessions import Sessions

log = logging.getLogger(__name__)
ACTIONS = ("stop", "note", "compact", "undo", "drop")
KEYS = {"stop": ".", "note": "m", "compact": "k", "undo": "u", "drop": "x"}  # design 0012 §9.1's table
TITLES = {"stop": "Stop now", "note": "Note", "compact": "Compact now", "undo": "Undo", "drop": "Drop"}
UNDO_TITLES = {"step": "Undo", "turn": "Undo turn", "redo": "Redo"}  # Undo's title by its mode
MODEL = {"providerID": PROVIDER, "modelID": ROLE}  # the gateway's agent role, as OpenCode names the model
WORKING = ("busy", "retry")
READ_LEAST = 256  # tokens a step must read anew for its time to the first token to measure the reading speed
NO_SERVER = "no OpenCode server is known to run this session: its watcher has not seen it run since the service started"
IDLE = "the session is idle and nothing waits in it: there is nothing to stop"
ASKED = "a compaction is asked already: OpenCode makes it at the session's next step"
SUBAGENT = "a subagent's session: the Guide acts on its root session (design 0012 §3)"
NOTE = "<your note>"
BUSY = "the session works: stop it first (.); OpenCode takes back no step while a session works"
NO_STEP = "the session has no step to undo"
COMPACTION = "the step before it is a compaction: undo does not take back a compaction"
UNDO_COST = "the next request is shorter; whether the engine reads anything again is to measure"
CLEARS = "[Old tool result content cleared]"  # what the model reads in a cleared result's place (message-v2.ts)
RESULTS = "tool results"  # the part of the context a call's result is, as a model's calibration names it
NOTHING_TO_CLEAR = "no finished call's result is left to clear"
FILES_SAID = 4  # files a preview names before it counts the others
# Clank's plain estimate of a text's tokens for a model with no calibration (decision 0087), as the runtime counts a
# first message's: kept here, since the agents component does not use the runtime's
PLAIN_TOKENS_PER_CHARACTER = 0.3
SAID_PAGE = 10  # the session's newest messages read back for the words of the messages an undo took back
Figures = Callable[[str, str], tuple[dict[str, Any], list[dict[str, Any]]]]  # a session's totals, its requests ended
Key = tuple[str, str]


class GuideError(Exception):
    """An action of the Guide that cannot run now, and why."""


def reading_speed(ended: list[dict[str, Any]], fields: Mapping[str, str]) -> tuple[float, int] | None:
    """The engine's reading speed, from the newest request of the session that ended well and read at least
    `READ_LEAST` tokens anew: llama.cpp's own `prompt_per_second` when its engine reports its timings, else the tokens
    it read anew (its prompt less what came from the cache) over its time to the first token; with those tokens. None
    when no request says (the cache not reported, too little read anew)."""
    for request in reversed(ended):
        if request.get("status") != 200 or request.get("error") or request.get("looped") or request.get("left"):
            continue
        if request.get("broken"):
            continue
        timings = request.get("timings") if fields.get("timings") else None
        if isinstance(timings, Mapping) and timings.get("prompt_per_second") and timings.get("prompt_n"):
            if int(timings["prompt_n"]) >= READ_LEAST:
                return round(float(timings["prompt_per_second"]), 1), int(timings["prompt_n"])
            continue
        prompt, cached = reported(request, fields.get("prompt")), reported(request, fields.get("cached"))
        first = request.get("first_ms")
        if prompt is None or cached is None or not first:
            continue
        read = prompt - cached
        if read >= READ_LEAST:
            return round(read / (float(first) / 1000), 1), read
    return None


def offer(
    view: Mapping[str, Any],
    *,
    port: int | None,
    totals: Mapping[str, Any],
    ended: list[dict[str, Any]],
    kept: Mapping[str, Mapping[str, Any]],
    item: str = "",
) -> list[dict[str, Any]]:
    """What the Guide offers for the session (module docstring): Stop, a note, Compact now, Undo and Drop (of `item`, a
    call's part id, when given)."""
    head: Mapping[str, Any] = view.get("head") or {}
    everything: list[dict[str, Any]] = list(view.get("nodes") or [])
    nodes: list[dict[str, Any]] = [node for node in everything if not node.get("undone")]
    session = str(head.get("session") or "")
    working = head.get("status") in WORKING
    asks = [node for node in nodes if node.get("kind") == "call" and node.get("asking")]
    fields: Mapping[str, str] = ((totals.get("facts") or {}).get("engine") or {}).get("fields") or {}
    speed = reading_speed(ended, fields)
    used = totals.get("used")
    said = [node for node in nodes if node.get("kind") == "said"]
    states = {action: _state(action, kept.get(action), head, nodes, everything) for action in ACTIONS}
    nowhere = SUBAGENT if head.get("parent") else NO_SERVER if port is None else ""

    stop_calls = [f"POST /session/{session}/abort"]
    stop_calls += [f'POST /permission/{ask["asking"]}/reply {{"reply": "reject"}}' for ask in asks] or [
        'then what waits in it and its subagents, rejected: POST /permission/:id/reply {"reply": "reject"}, '
        "POST /question/:id/reject"
    ]
    stop = _action(
        "stop", nowhere or ("" if working or asks else IDLE), False, states["stop"],
        brief="stops the step under way, rejects what waits",
        does="OpenCode cancels the step under way, marks its unfinished calls interrupted and rejects what waits in "
        "the session and its subagents; a stopped step with content stays in what the model reads",
        calls=stop_calls, cost={"tokens": 0, "seconds": 0.0, "words": "nothing read again"},
    )  # fmt: skip

    agent = str(next((node.get("agent") for node in reversed(said) if node.get("agent")), head.get("agent") or ""))
    model = next((node.get("model") for node in reversed(said) if node.get("model")), None) or {}
    if asks:
        ask = asks[-1]
        waits = ask.get("permission") or ask.get("tool")
        does = (f"rejects the call waiting for your approval ({waits}) with your note as the reason: the model reads "
                "it as that call's answer and goes on; no message is added")  # fmt: skip
        calls = [f'POST /permission/{ask["asking"]}/reply {{"reply": "reject", "message": "{NOTE}"}}']
        brief = "rejects the call waiting for approval with your note"
        cost = {"tokens": None, "seconds": None,
                "words": "the note, read as the call's answer: nothing earlier is expected to be read again (to "
                "measure)"}  # fmt: skip
    else:
        to = f"to {agent}" if agent else "to the session's agent"
        when = "stored at once and read at its next step" if working else "it starts a run on the server that ran it"
        does = f"a message of yours, {to} with the session's model: {when}"
        brief = f"{to}, " + ("read at its next step" if working else "starts a run")
        body: dict[str, Any] = {**({"agent": agent} if agent else {}), **({"model": model} if model else {}),
                                "parts": [{"type": "text", "text": NOTE}]}  # fmt: skip
        calls = [f"POST /session/{session}/prompt_async {json.dumps(body)}"]
        tokens = _since_said(said, nodes, used)
        cost = _cost(tokens, speed, "everything since your previous message, an estimate (to measure)")
    note = _action("note", nowhere, True, states["note"], brief=brief, does=does, calls=calls, cost=cost)

    keeps = totals.get("keeps")
    after = (
        f"the next step reads the summary and the last {keeps:,} tokens" if keeps else "the next step reads the summary"
    )
    compacting = states["compact"] is not None and states["compact"]["state"] in ("asked", "compacting")
    compact = _action(
        "compact", nowhere or (ASKED if compacting else ""), True, states["compact"],
        brief="at the session's next step",
        does=f"OpenCode's compaction agent reads the whole history and writes a summary; {after}. Asked now, it "
        "happens at the session's next step, and the work goes on after it",
        calls=[f"POST /session/{session}/summarize {json.dumps({**MODEL, 'auto': True})}"],
        cost=_cost(used if isinstance(used, int) else None, speed, "a full reading of the history (to measure)"),
    )  # fmt: skip
    undo = _undo(view, nodes, session=session, why=nowhere or (BUSY if working else ""), speed=speed,
                 state=states["undo"])  # fmt: skip
    drop = _drop(everything, nodes, session=session, nowhere=nowhere, totals=totals, speed=speed, item=item,
                 state=states["drop"])  # fmt: skip
    return [stop, note, compact, undo, drop]


def _action(
    action: str, why: str, confirm: bool, state: dict[str, Any] | None, *, brief: str, does: str, calls: list[str],
    cost: dict[str, Any], **more: Any
) -> dict[str, Any]:  # fmt: skip
    return {"action": action, "key": KEYS[action], "title": TITLES[action], "can": not why, "why": why,
            "brief": brief, "does": does, "calls": calls, "cost": cost, "confirm": confirm, "state": state,
            **more}  # fmt: skip


def _step(node: Mapping[str, Any]) -> str:
    """A step by its number; "that step" for one whose flow gives none (a flow drawn by another part)."""
    return f"step {node['n']}" if node.get("n") is not None else "that step"


def _undo(
    view: Mapping[str, Any], nodes: list[dict[str, Any]], *, session: str, why: str,
    speed: tuple[float, int] | None, state: dict[str, Any] | None
) -> dict[str, Any]:  # fmt: skip
    """Undo the last step (design 0012 §9.5, decision 0056): Redo while a revert is pending; else a revert at the last
    part of the step before the last (`cut`), the steps with nothing before their last part taken back with it; the
    turn, a revert at the oldest of the owner's messages just before, when one comes first (a note included, in
    OpenCode's order); refused across a compaction."""
    pending = (view.get("head") or {}).get("reverted")
    cost = _cost(None, speed, UNDO_COST)
    if pending:
        undone = [node for node in view.get("nodes") or [] if node.get("undone") and not node.get("final")]
        takes = _takes(undone)
        what = _taken(takes, turn=bool(undone) and undone[0].get("kind") == "said") or "what your undo took back"
        return _action(
            "undo", why, True, state, brief=f"brings back {what}",
            does=f"OpenCode's unrevert brings back {what}, the files as they were before your undo; it can until your "
            "next message, which makes the undo final",
            calls=[f"POST /session/{session}/unrevert"], cost=cost,
            title=UNDO_TITLES["redo"], mode="redo", revert=dict(pending), takes=takes, refused="",
        )  # fmt: skip
    ordered = [node for node in nodes if node.get("kind") in ("said", "step", "band")]
    steps = [index for index, node in enumerate(ordered) if node["kind"] == "step"]
    nothing = {"title": UNDO_TITLES["step"], "mode": "step", "revert": None, "takes": _takes([]), "refused": ""}
    if not steps:
        return _action("undo", why or NO_STEP, True, state, brief="takes back the last step", does="",
                       calls=[], cost=cost, **nothing)  # fmt: skip
    last = start = steps[-1]
    while start > 0 and ordered[start - 1]["kind"] == "step" and not ordered[start - 1].get("cut"):
        start -= 1  # OpenCode would turn a revert at its last part into one of the whole turn: it goes too
    if start == 0:
        gone = f"the message before {_step(ordered[start])} is not in Clank's flow: undo cannot name where to cut"
        return _action("undo", why or gone, True, state, brief="takes back the last step", does="", calls=[],
                       cost=cost, **nothing)  # fmt: skip
    before = ordered[start - 1]
    if before["kind"] == "band":
        return _action("undo", why or COMPACTION, True, state, brief="takes back the last step", does="", calls=[],
                       cost=cost, **nothing)  # fmt: skip
    refused = ""
    if before["kind"] == "step":
        mode, begin, revert = "step", start, {"message": str(before["id"]), "part": str(before["cut"])}
    else:
        begin = start - 1
        while begin > 0 and ordered[begin - 1]["kind"] == "said":
            begin -= 1
        mode, revert = "turn", {"message": str(ordered[begin]["id"]), "part": ""}
        refused = (f"{_step(ordered[last])} is the first after your message: undoing it alone would take back your "
                   "message too")  # fmt: skip
    takes = _takes([node for node in nodes if node["at"] >= ordered[begin]["at"]])
    what = _taken(takes, turn=mode == "turn")
    files = _files(takes["files"])
    restored = (f"the files changed since restored from OpenCode's snapshots: {files}" if files
                else "no file changed since, by OpenCode's snapshots")  # fmt: skip
    subagents = takes["subagents"]
    theirs = (f"; what its {'subagent' if subagents == 1 else f'{subagents} subagents'} changed in their own sessions "
              "is not taken back (to see)") if subagents else ""  # fmt: skip
    redo = "until your next message u redoes it (OpenCode's unrevert), and your next message makes it final"
    if mode == "step":
        does = f"OpenCode's revert at the last part of {_step(before)} takes back {what}: {restored}; {redo}{theirs}"
    else:
        does = (f"OpenCode's revert at your message takes back {what}: {restored}; the text of your message comes back "
                f"in the note line, to send again or change; {redo}{theirs}")  # fmt: skip
    body = {"messageID": revert["message"], **({"partID": revert["part"]} if revert["part"] else {})}
    return _action(
        "undo", why, True, state, brief=f"takes back {what}", does=does,
        calls=[f"POST /session/{session}/revert {json.dumps(body)}"], cost=cost,
        title=UNDO_TITLES[mode], mode=mode, revert=revert, takes=takes, refused=refused,
    )  # fmt: skip


def _takes(taken: list[dict[str, Any]]) -> dict[str, Any]:
    """What a revert takes back, from its nodes: the steps (their numbers), the files their patches list (what OpenCode
    restores), the owner's messages and their words, and the subagents those steps started."""
    steps = [node for node in taken if node.get("kind") == "step"]
    said = [node for node in taken if node.get("kind") == "said"]
    files: list[str] = []
    for node in steps:
        files += [str(file) for file in node.get("files") or [] if str(file) not in files]
    ids = {node["id"] for node in steps}
    subagents = sum(1 for node in taken if node.get("kind") == "subagent" and node.get("step") in ids)
    return {"steps": [node.get("n") for node in steps], "files": files, "said": [str(node["id"]) for node in said],
            "text": "\n\n".join(str(node["text"]) for node in said if node.get("text")),
            "subagents": subagents}  # fmt: skip


def _taken_from(nodes: list[dict[str, Any]], cut: Mapping[str, str]) -> list[dict[str, Any]] | None:
    """The nodes a revert at `cut` takes back, as OpenCode cuts: from the message after it when it names a part, else
    from the message itself; None when the flow does not hold that message."""
    ordered = [node for node in nodes if node.get("kind") in ("said", "step", "band")]
    at = next((index for index, node in enumerate(ordered) if node["id"] == cut["message"]), None)
    if at is None:
        return None
    begin = at + 1 if cut["part"] else at
    if begin >= len(ordered):
        return []
    return [node for node in nodes if node["at"] >= ordered[begin]["at"]]


def _taken(takes: Mapping[str, Any], *, turn: bool) -> str:
    """What a revert takes back, in words: "steps 2 and 3", "your message and step 2", "step 4 and your message after
    it"."""
    steps = _numbers(list(takes["steps"]))
    count = len(takes["said"])
    if not count:
        return steps
    message = "your message" if count == 1 else f"your {count} messages"
    if not steps:
        return message
    return f"{message} and {steps}" if turn else f"{steps} and {message} after it"


def _numbers(numbers: list[Any]) -> str:
    """Steps by their numbers: "step 2", "steps 2 and 3", "steps 2, 3 and 4", "steps 2 to 9"; counted ("2 steps") when
    a flow drawn by another part gives no numbers."""
    if not numbers:
        return ""
    if any(each is None for each in numbers):
        return "a step" if len(numbers) == 1 else f"{len(numbers)} steps"
    if len(numbers) == 1:
        return f"step {numbers[0]}"
    if len(numbers) > 3 and numbers == list(range(numbers[0], numbers[0] + len(numbers))):
        return f"steps {numbers[0]} to {numbers[-1]}"
    return f"steps {', '.join(str(each) for each in numbers[:-1])} and {numbers[-1]}"


def _files(files: list[str]) -> str:
    """The files a preview names, the first few and how many more."""
    shown = ", ".join(files[:FILES_SAID])
    return shown + (f" and {len(files) - FILES_SAID} more" if len(files) > FILES_SAID else "")


def _drop(
    everything: list[dict[str, Any]], nodes: list[dict[str, Any]], *, session: str, nowhere: str,
    totals: Mapping[str, Any], speed: tuple[float, int] | None, item: str, state: dict[str, Any] | None
) -> dict[str, Any]:  # fmt: skip
    """Drop an item (design 0012 §9.7, decision 0056): OpenCode's own clearing of a finished call's result, never one
    of the step in progress; for `item`, what it frees and what it costs, else whether any result can be cleared."""
    steps = {node["id"]: node for node in everything if node.get("kind") == "step"}
    calls = {node["id"]: node for node in everything if node.get("kind") == "call"}
    compacted = [node["at"] for node in nodes if node.get("kind") == "band" and node.get("done")]
    does = (f"OpenCode's own clearing of a finished call's result, as its compaction clears old ones: the whole part "
            f"written back with its state.time.compacted set; from the next step the model reads \"{CLEARS}\" in its "
            "place, and the call stays. The drop is final: whether a cleared result can be brought back is to "
            "measure")  # fmt: skip

    def refused(call: Mapping[str, Any]) -> str:
        step = steps.get(str(call.get("step") or ""), {})
        if call.get("undone"):
            return "its step is undone: u brings it back, or your next message removes it"
        if call.get("cleared"):
            return "its result is cleared already"
        if call.get("status") == "error":
            return "only a finished call's result is cleared; this one failed, with no result to clear"
        if call.get("status") != "completed":
            return f"only a finished call's result is cleared; this one is {call.get('status') or 'not begun'}"
        if step.get("ended") == "working":
            return "it is in the step in progress: OpenCode would change it while it runs"
        if step.get("context") == "left":
            return "its step left the context (it ended in an error): the model does not read its result"
        if any(at > call["at"] for at in compacted):
            return "a compaction since summarized its step: the model no longer reads its result"
        return ""

    if not item:
        can = any(not refused(call) for call in calls.values())
        return _action(
            "drop", nowhere or ("" if can else NOTHING_TO_CLEAR), True, state,
            brief="clears a finished call's result: x on a call in the flow or in Tool calls", does=does,
            calls=[f"PATCH /session/{session}/message/:message/part/:part (the whole part, its state.time.compacted "
                   "set to now)"],
            cost={**_cost(None, speed, "the tokens it frees, and everything after it read once: x names the call"),
                  "freed": None},
            item=None,
        )  # fmt: skip
    call = calls.get(item)
    if call is None:
        return _action("drop", nowhere or f"no tool call {item} in the session's flow", True, state,
                       brief="clears a finished call's result", does=does, calls=[],
                       cost={**_cost(None, speed, "no call named"), "freed": None}, item=None)  # fmt: skip
    step = steps.get(str(call.get("step") or ""), {})
    rate, source = _rate(totals)
    length = call.get("length")
    freed = round(int(length) * rate) if isinstance(length, int) else None
    frees = (f"frees about {freed:,} tokens ({rate:g} tokens a character, {source})" if freed is not None
             else "the tokens it frees not known: its result's length is not known")  # fmt: skip
    after = [node for node in nodes if node.get("kind") == "step" and node["at"] > step.get("at", call["at"])]
    if not after:
        cost = {"tokens": 0, "seconds": 0.0, "freed": freed, "words": f"{frees}; nothing read again: no step has read "
                "it yet"}  # fmt: skip
    else:
        prompt = (after[0].get("request") or {}).get("prompt_tokens")
        used = totals.get("used")
        tokens = max(0, used - int(prompt)) if isinstance(used, int) and isinstance(prompt, int) else None
        found = _cost(tokens, speed, "everything after it, read once, an estimate (to measure)")
        cost = {**found, "freed": freed, "words": f"{frees}; {found['words']}"}
    what = f"step {step.get('n')}'s `{call.get('tool')}`" + (f" ({brief(call['title'], 40)})" if call.get("title")
                                                              else "")  # fmt: skip
    message = str(call.get("step") or "")
    return _action(
        "drop", nowhere or refused(call), True, state, brief=f"clears {what}'s result" + (
            f", frees about {freed:,}" if freed is not None else ""), does=does,
        calls=[f"PATCH /session/{session}/message/{message}/part/{item} (the whole part, its state.time.compacted set "
               "to now)"],
        cost=cost,
        item={"message": message, "part": item, "step": step.get("n"), "tool": str(call.get("tool") or ""),
              "title": str(call.get("title") or ""), "length": length, "freed": freed},
    )  # fmt: skip


def _rate(totals: Mapping[str, Any]) -> tuple[float, str]:
    """Tokens a character of a call's result: the model's calibration for tool results, else Clank's plain estimate
    (decision 0087); and where it comes from."""
    model: Mapping[str, Any] = (totals.get("facts") or {}).get("model") or {}
    per: Mapping[str, Any] = (model.get("calibration") or {}).get("tokens_per_character") or {}
    if isinstance(per.get(RESULTS), int | float) and per[RESULTS] > 0:
        return float(per[RESULTS]), "the model's calibration for tool results"
    return PLAIN_TOKENS_PER_CHARACTER, "Clank's plain estimate (decision 0087): the model has no calibration for them"


def _since_said(said: list[dict[str, Any]], nodes: list[dict[str, Any]], used: Any) -> int | None:
    """What a new message makes the engine read again, estimated: the totals' `used`, less the prompt of the first step
    after the owner's previous message (what the engine keeps); None when either is not known."""
    if not said or not isinstance(used, int):
        return None
    after = [node for node in nodes if node.get("kind") == "step" and list(node["at"]) > list(said[-1]["at"])]
    prompt = ((after[0].get("request") or {}).get("prompt_tokens")) if after else None
    return max(0, used - int(prompt)) if isinstance(prompt, int) else None


def _cost(tokens: int | None, speed: tuple[float, int] | None, what: str) -> dict[str, Any]:
    """The tokens read again and the time that takes at the engine's reading speed, in words too."""
    if tokens is None:
        return {"tokens": None, "seconds": None, "words": f"not known yet: {what}"}
    if speed is None:
        return {"tokens": tokens, "seconds": None,
                "words": f"about {tokens:,} tokens read again: {what}; the time not known: no step of this session "
                "read enough anew to measure the engine's reading speed"}  # fmt: skip
    seconds = round(tokens / speed[0], 1)
    return {"tokens": tokens, "seconds": seconds,
            "words": f"about {tokens:,} tokens read again, about {seconds:,} s at {speed[0]:,.0f} tokens a second: "
            f"{what}"}  # fmt: skip


def _state(
    action: str, kept: Mapping[str, Any] | None, head: Mapping[str, Any], nodes: list[dict[str, Any]],
    everything: list[dict[str, Any]]
) -> dict[str, Any] | None:  # fmt: skip
    """The state of the action's last run, as the flow shows it now (module docstring); `nodes` are those not undone,
    `everything` the flow's nodes."""
    if not kept:
        return None
    shown = {"state": str(kept.get("state") or ""), "time": kept.get("time") or "", "by": kept.get("by") or "",
             "why": kept.get("why") or "", "step": None}  # fmt: skip
    if action in ("undo", "drop"):
        shown["what"] = str(kept.get("what") or "")
    working = head.get("status") in WORKING
    if shown["state"] == "failed":
        return shown
    if action == "undo" and shown["state"] in ("undone", "redone"):
        shown["state"] = _undo_state(kept, head, everything)
    elif action == "drop" and shown["state"] == "cleared":
        call = next((node for node in everything if node["id"] == kept.get("part")), None)
        shown["state"] = "clearing" if call is not None and not call.get("cleared") else "cleared"
    if action == "stop" and shown["state"] == "stopping":
        waiting = any(node.get("kind") == "call" and node.get("asking") for node in nodes)
        shown["state"] = "stopping" if working or waiting else "stopped"
    elif action == "note" and kept.get("text") and kept.get("mode") != "reject":
        shown.update(_note_state(str(kept["text"]), working, nodes))
    elif action == "compact" and shown["state"] in ("asked", "compacting"):
        bands = [node for node in nodes if node.get("kind") == "band"]
        count = int(kept.get("bands") or 0)
        if len(bands) > count:
            shown["state"] = "done" if bands[count].get("done") else "compacting"
    return shown


def _undo_state(kept: Mapping[str, Any], head: Mapping[str, Any], everything: list[dict[str, Any]]) -> str:
    """An undo's state, read from the flow: final once OpenCode removed what it took back; undone (the turn undone)
    while its revert is pending; else brought back (redone), by Redo or elsewhere."""
    ids = {str(id) for id in kept.get("ids") or []}
    found = [node for node in everything if node["id"] in ids]
    if any(node.get("final") for node in found) or (ids and not found):
        return "final"
    if head.get("reverted") and found and all(node.get("undone") for node in found):
        return "turn undone" if kept.get("mode") == "turn" else "undone"
    return "redone"


def _note_state(text: str, working: bool, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """A note's state: its message in the flow (the newest with its text), read by which step, answered."""
    said = next((node for node in reversed(nodes) if node.get("kind") == "said" and node.get("text") == brief(text)),
                None)  # fmt: skip
    if said is None:
        return {"state": "written"}
    if said.get("state") == "not read":
        return {"state": "not read", "why": "the run ended without reading it: send it again"}
    read = next((node for node in nodes if node.get("kind") == "step" and node["id"] == said.get("read_by")), None)
    if read is not None:
        return {"state": "read" if working else "answered", "step": read.get("n")}
    return {"state": "waiting" if working or said.get("note") else "written"}


class Guide:
    """The Guide's actions on the sessions the service watches, and what each did last in each session."""

    def __init__(
        self,
        sessions: "Sessions",
        flows: "SessionFlows",
        review: "Review",
        figures: Figures,
        now: Callable[[], str],
        pausing: "Pausing | None" = None,
    ) -> None:
        self.sessions, self.flows, self.review, self._figures, self._now = sessions, flows, review, figures, now
        self.pausing = pausing  # the pause, the gateway's (design 0012 §9.4); None: not offered
        self._lock = threading.Lock()
        self._kept: dict[Key, dict[str, dict[str, Any]]] = {}

    def offer(self, workspace: str, session: str, *, pause: bool = True, item: str = "") -> dict[str, Any]:
        """What the Guide offers for the session now (`offer`, Drop for `item` when given), with the server that runs
        it; with `pause`, the pause after Compact now and before Undo, as §9.1's table lists it after the note
        (`Pausing.action`, read from the gateway)."""
        view, port = self._session(workspace, session)
        totals, ended = self._figures(workspace, session)
        with self._lock:
            kept = {action: dict(found) for action, found in self._kept.get((workspace, session), {}).items()}
        actions = offer(view, port=port, totals=totals, ended=ended, kept=kept, item=item)
        if pause and self.pausing is not None:
            undo = next(index for index, each in enumerate(actions) if each["action"] == "undo")
            actions.insert(undo, self.pausing.action(workspace, session))
        return {"workspace": workspace, "session": session, "port": port, "actions": actions}

    def stop(self, workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        """Stop the session now: abort it, then reject what waits in it and its subagents."""
        port, _ = self._can(workspace, session, "stop")
        self._keep(workspace, session, "stop", actor, "stopping")
        try:
            self.sessions.stop(workspace, port, session, actor=actor)
        except Exception as error:
            self._keep(workspace, session, "stop", actor, "failed", why=str(error))
            raise
        try:
            rejected = self.sessions.reject(workspace, port, session, actor=actor)
        except Exception as error:  # stopped, but what waits is left: said, so the owner answers it
            why = f"stopped, but what waits in it could not be rejected: {error}"
            self._keep(workspace, session, "stop", actor, "stopping", why=why)
            return {"state": "stopping", "port": port, "rejected": [], "questions": [], "why": why}
        return {"state": "stopping", "port": port, **rejected}

    def note(
        self, workspace: str, session: str, text: str, *, actor: Actor, about: str = "", reject: bool = True
    ) -> dict[str, Any]:
        """Send the model a note, beginning with what it is about; while a call waits for approval (and `reject`),
        reject that call with the note as its reason instead."""
        if not text.strip():
            raise GuideError("an empty note is not sent")
        said = f"About {about.strip()}: {text.strip()}" if about.strip() else text.strip()
        port, _ = self._can(workspace, session, "note")
        view, _ = self._session(workspace, session)
        asks = [node for node in view.get("nodes") or [] if node.get("kind") == "call" and node.get("asking")
                and not node.get("undone")]  # fmt: skip
        try:
            if reject and asks:
                ask = str(asks[-1]["asking"])
                self.review.reply(workspace, port, ask, "reject", actor=actor, message=said)
                self._keep(workspace, session, "note", actor, "sent", text=said, mode="reject")
                return {"sent": True, "port": port, "text": said, "rejected": ask}
            sent = self.sessions.send(workspace, port, session, said, actor=actor)
        except Exception as error:
            self._keep(workspace, session, "note", actor, "failed", why=str(error), text=said)
            raise
        self._keep(workspace, session, "note", actor, "written", text=said)
        return {"sent": True, "port": port, "text": said, "agent": sent.get("agent", ""),
                "model": sent.get("model") or {}}  # fmt: skip

    def compact(self, workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        """Ask OpenCode to compact the session at its next step, without waiting for it."""
        port, _ = self._can(workspace, session, "compact")
        view, _ = self._session(workspace, session)
        bands = sum(1 for node in view.get("nodes") or [] if node.get("kind") == "band")
        try:
            found = self.sessions.compact(workspace, port, session, actor=actor, model=dict(MODEL))
        except Exception as error:
            self._keep(workspace, session, "compact", actor, "failed", why=str(error))
            raise
        self.flows.compaction_asked(workspace, session, bands)
        self._keep(workspace, session, "compact", actor, "asked", bands=bands)
        return {"state": "asked", "port": port, **found}

    def undo(
        self, workspace: str, session: str, *, actor: Actor, message: str, part: str = "", steps: Sequence[int],
        said: Sequence[str]
    ) -> dict[str, Any]:  # fmt: skip
        """Undo the last step, or the turn, with OpenCode's revert at the message and part the owner confirmed
        (`message`, `part`) and what its window said it takes back (`steps`, `said`: the numbers of the steps, the ids
        of the owner's messages), never what is offered now unseen: refused when it names no revert, or when the cut or
        what it takes back changed since, so what was confirmed is what is done. The flow shows the revert at once,
        from OpenCode's answer; the words of the owner's messages it took back are read back (`_said`)."""
        if not message:
            raise GuideError("Undo names the revert you confirmed: its message, and its part")
        port, found = self._can(workspace, session, "undo")
        if found["mode"] == "redo":
            raise GuideError("an undo is pending: u redoes it (Redo), or your next message makes it final")
        revert, takes, mode = found["revert"], found["takes"], found["mode"]
        what = _taken(takes, turn=mode == "turn")
        confirmed = (message, part, list(steps), list(said))
        if confirmed != (revert["message"], revert["part"], takes["steps"], takes["said"]):
            raise GuideError(f"the session moved on since you looked: Undo would now take back {what}; look again")
        view, _ = self._session(workspace, session)
        ids = [
            str(node["id"])
            for node in view.get("nodes") or []
            if node.get("kind") == "step" and not node.get("undone") and node.get("n") in takes["steps"]
        ]
        ids += list(takes["said"])  # fmt: skip
        try:
            kept = self.sessions.revert(workspace, port, session, revert["message"], revert["part"], actor=actor)
        except Exception as error:
            self._keep(workspace, session, "undo", actor, "failed", why=str(error), what=what, mode=mode)
            raise
        if not kept.get("messageID"):
            why = "OpenCode answered with nothing taken back"
            self._keep(workspace, session, "undo", actor, "failed", why=why, what=what, mode=mode)
            raise GuideError(f"Undo did not run: {why}")
        cut = {"message": str(kept["messageID"]), "part": str(kept.get("partID") or "")}  # its snapshot and diff left
        warned = ""
        if cut != revert:  # OpenCode cut elsewhere: what it took back, read from the flow, its words given back too
            taken = _taken_from([node for node in view.get("nodes") or [] if not node.get("undone")], cut)
            if taken is not None:
                takes = _takes(taken)
                mode = "turn" if taken and taken[0].get("kind") == "said" else mode
                what = _taken(takes, turn=mode == "turn")
                ids = [str(node["id"]) for node in taken if node.get("kind") in ("step", "said")]
            warned = (f"OpenCode took back from {cut['message']}, not {revert['part'] or revert['message']}: {what}, "
                      f"more than the preview said; u redoes it")  # fmt: skip
        self.flows.reverted(workspace, session, {"messageID": cut["message"], "partID": cut["part"]})
        self._keep(workspace, session, "undo", actor, "undone", ids=ids, what=what, mode=mode, revert=revert,
                   why=warned)  # fmt: skip
        text, whole = self._said(workspace, port, session, view, takes) if takes["said"] else ("", True)
        return {"state": "undone", "port": port, "mode": mode, "revert": cut, "takes": takes, "text": text,
                "whole": whole, "why": warned}  # fmt: skip

    def redo(self, workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        """Bring back what the pending undo took back, with OpenCode's unrevert, until the owner's next message."""
        port, found = self._can(workspace, session, "undo")
        if found["mode"] != "redo":
            raise GuideError("Redo cannot run now: nothing is undone")
        view, _ = self._session(workspace, session)
        ids = [str(node["id"]) for node in view.get("nodes") or []
               if node.get("undone") and not node.get("final") and node.get("kind") in ("step", "said")]  # fmt: skip
        what = str(found["brief"]).removeprefix("brings back ")
        try:
            kept = self.sessions.unrevert(workspace, port, session, actor=actor)
        except Exception as error:
            self._keep(workspace, session, "undo", actor, "failed", why=str(error), what=what)
            raise
        self.flows.reverted(workspace, session, kept or None)
        self._keep(workspace, session, "undo", actor, "redone", ids=ids, what=what, mode="redo")
        return {"state": "redone", "port": port, "takes": found["takes"]}

    def drop(self, workspace: str, session: str, part: str, *, actor: Actor) -> dict[str, Any]:
        """Clear the result of the call `part`, as OpenCode's own compaction does; refused for the step in progress."""
        if not part:
            raise GuideError("Drop names the call whose result it clears")
        port, found = self._can(workspace, session, "drop", item=part)
        item = found["item"]
        what = f"step {item['step']}'s `{item['tool']}`"
        try:
            cleared = self.sessions.clear(workspace, port, session, item["message"], part, actor=actor)
        except Exception as error:
            self._keep(workspace, session, "drop", actor, "failed", why=str(error), part=part, what=what)
            raise
        self.flows.cleared(workspace, session, part, item["freed"])
        self._keep(workspace, session, "drop", actor, "cleared", part=part, what=what, freed=item["freed"])
        return {"state": "cleared", "port": port, "item": item, **cleared}

    def _said(
        self, workspace: str, port: int, session: str, view: Mapping[str, Any], takes: Mapping[str, Any]
    ) -> tuple[str, bool]:
        """The words of the owner's messages a revert took back, whole up to the bridge's cap, read from the session's
        newest page of history (`SAID_PAGE` messages); those not read there, the flow's words of them; and whether
        every one is whole."""
        words = {str(node["id"]): str(node.get("text") or "") for node in view.get("nodes") or []
                 if node.get("kind") == "said"}  # fmt: skip
        read: dict[str, tuple[str, bool]] = {}
        try:
            page = self.sessions.page(workspace, port, session, limit=SAID_PAGE)
        except Exception as error:  # the flow's words, said cut
            log.warning("the words of %s in %s could not be read back: %s", session, workspace, error)
            page = {}
        for message in page.get("messages") or []:
            id = str((message.get("info") or {}).get("id") or "")
            texts = [part for part in message.get("parts") or [] if part.get("type") == "text"
                     and not part.get("synthetic")]  # fmt: skip
            if id in takes["said"] and texts:
                said = "\n\n".join(str(part.get("text") or "") for part in texts)
                whole = all(int(part.get("length") or 0) == len(str(part.get("text") or "")) for part in texts)
                read[id] = (said, whole)
        found = [read.get(id, (words.get(id, ""), False)) for id in takes["said"]]
        return "\n\n".join(said for said, _ in found if said), all(whole for _, whole in found)

    def _session(self, workspace: str, session: str) -> tuple[dict[str, Any], int | None]:
        """The session's flow (its view) and the server that runs it; refused when Clank keeps no flow of it."""
        view = self.flows.view(workspace, session)
        if view is None:
            raise GuideError(f"Clank keeps no flow of {session} in {workspace}: its watcher has not seen that session")
        return view, self.sessions.runs(workspace, session)

    def _can(self, workspace: str, session: str, action: str, item: str = "") -> tuple[int, dict[str, Any]]:
        """The server an action goes to and the action as offered now (Drop of `item`), once it can run now; refused
        with why when it cannot."""
        offered = self.offer(workspace, session, pause=False, item=item)  # Stop must be quick: the gateway not asked
        found = next(each for each in offered["actions"] if each["action"] == action)
        if not found["can"]:
            raise GuideError(f"{found['title']} cannot run now: {found['why']}")
        port: int = offered["port"]
        return port, found

    def _keep(self, workspace: str, session: str, action: str, actor: Actor, state: str, **more: Any) -> None:
        """What an action did last in the session; what it did in a session whose flow is no longer kept goes."""
        watched = self.flows.keys()
        with self._lock:
            for gone in set(self._kept) - watched:
                del self._kept[gone]
            kept = self._kept.setdefault((workspace, session), {})
            kept[action] = {"state": state, "time": self._now(), "by": actor.describe(), "why": "", **more}


class Ruled:
    """What a Watch for rule asks of the Guide (`marks.Acting`, design 0012 §8): its note, sent as the rule (never as
    the answer to an ask: a rule does not reject a call the owner may approve); its pause, the gateway's hold of the
    session's root, as the rule (step 11)."""

    def __init__(self, guide: Guide) -> None:
        self.guide = guide

    def note(self, workspace: str, port: int | None, session: str, text: str) -> None:
        """The rule's note, through the Guide, to the server that runs the session."""
        self.guide.note(workspace, session, text, actor=WATCH, reject=False)

    def pause(self, workspace: str, session: str) -> None:
        """The rule's pause, through the Guide's pause: the session's root held after its step."""
        if self.guide.pausing is None:
            raise Unavailable("pausing goes through the gateway's hold (design 0012 §11 step 11), not given here")
        self.guide.pausing.pause(workspace, session, actor=WATCH)
