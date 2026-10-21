"""What a session does now (design 0012 §5, §11 step 7): the Monitor's Now panel, as the service says it, so the console
(and the phone, later) draws it without knowing an engine's or a model's numbers (decision 0067).

`now` is a pure function over the gateway's activity of the session (its own request in flight and its requests that
ended, `Gateway.activity(session, ended=True)`), the session's flow (OpenCode's status, its calls, its asks, a
compaction under way), the routes and a preset's facts by its name (the budgets, and where its engine reports each
figure), the loop guard's setting, and the moment:

- **The phase** (§5.1), from the gateway for its requests (waiting for its slot; reading the prompt, or queued, since
  the engine says nothing until it holds its lock, so the two look the same; thinking, answering or writing a call, by
  the kind of text it wrote last; waiting for its engine to start again; held while the Guide paused it; stopped by
  the loop guard) and from OpenCode for the session (running a tool, with its call; waiting for you, while an approval
  or a question waits; retrying, with its attempt and when the next is due; compacting; idle). The first that holds,
  in that order: held, waiting for you, retrying, compacting, the request in flight, a tool running, OpenCode working
  between its steps, the loop guard's stop, idle. Its `source` says which it came from; `working` whether the spinner
  turns.
- **The budgets** (§5.2): the thinking against its budget, and everything the answer writes (its thinking, its text and
  its calls) against the output limit, from the facts of the slot the request went to (of the preset that answered
  the last one, once it ended). While the request streams the counts are the gateway's, one a streamed event, said
  "about"; once it ended the answer's is the engine's own when its engine reports it, and the thinking's is the live
  count scaled to it, still "about", since usage has no count of its own for the thinking.
- **The prompt** (§5.3): this step's time to its first token (or how long it has been read), and the previous step's
  size and the part read from the cache, which arrive only with a request's end.
- **The speed** (§5.3): the gateway's tokens a second, and each step's, the newest last.
- **The call being written** (§5.3): its name and its arguments' newest characters, which only the gateway sees.
- **The loop guard** (§5.4): off (the gateway's settings, applied when it restarts); watching, with each part's newest
  share against its ratio; or what it stopped.
"""

from collections.abc import Callable, Mapping
from typing import Any

from clank.components.agents.context import reported
from clank.components.gateway.service import AGAIN, ANSWERING, HELD, READING, WAITING

Facts = Callable[[str], dict[str, Any] | None]  # a preset's facts, by its name (`Gateway.facts`)
RETRIES = 5  # OpenCode's attempts at most (design 0012 §5.1)
SPEEDS = 32  # the steps' speeds kept, the newest
ROLE = "agent"
PHASES = {
    "slot": "waiting for its slot",
    "reading": "reading the prompt (or queued)",
    "thinking": "thinking",
    "answering": "answering",
    "writing": "writing a call",
    "again": "waiting for its engine to start again",
    "tool": "running a tool",
    "you": "waiting for you",
    "retry": "retrying",
    "compacting": "compacting",
    "held": "held",
    "looped": "stopped by the loop guard",
    "between": "working, between its steps",
    "idle": "idle",
}
FROM_THE_GATEWAY = ("slot", "reading", "thinking", "answering", "writing", "again", "held", "looped")
RESTING = ("you", "held", "looped", "idle")  # no spinner: it waits for someone, or for nothing
BY_KIND = {"thinking": "thinking", "answer": "answering", "tool": "writing"}
GATEWAY_PHASES = {WAITING: "slot", READING: "reading", AGAIN: "again", HELD: "held"}


def now(
    session: str,
    doing: Mapping[str, Any],
    view: Mapping[str, Any] | None,
    routes: Mapping[str, Any],
    facts_of: Facts,
    guard: Mapping[str, Any],
    moment: float,
) -> dict[str, Any]:
    """What the session does now (module docstring); `moment` in seconds since the epoch."""
    flying = [request for request in doing.get("requests") or [] if request.get("session", session) == session]
    request: dict[str, Any] | None = flying[-1] if flying else None
    ended: list[dict[str, Any]] = list(doing.get("ended") or [])
    last: dict[str, Any] | None = doing.get("last") or (ended[-1] if ended else None)
    head: Mapping[str, Any] = (view or {}).get("head") or {}
    nodes = [node for node in (view or {}).get("nodes") or [] if not node.get("undone")]
    steps = [node for node in nodes if node.get("kind") == "step"]
    state, detail, call = _phase(request, last, head, nodes, moment)
    seconds = request.get("seconds") if request is not None else None
    if state == "tool" and call is not None and call.get("started"):
        seconds = round(max(moment - float(call["started"]) / 1000, 0.0), 1)
    facts = _facts(request, last, routes, facts_of)
    running = (
        None if call is None or state != "tool" else {key: call.get(key) or "" for key in ("tool", "title", "input")}
    )
    return {
        "session": session,
        "state": state,
        "phase": PHASES[state],
        "source": "gateway" if state in FROM_THE_GATEWAY else "OpenCode",
        "detail": detail,
        "working": state not in RESTING,
        "step": steps[-1].get("n") if steps else None,
        "seconds": seconds,
        "request": {"id": request["id"], "flying": True} if request is not None else None,
        "call": running,
        **_budgets(request, last, facts),
        "prompt": _prompt(request, ended, facts_of),
        "writing": request.get("writing") if request is not None and state == "writing" else None,
        "speed": _speed(request, ended, last),
        "guard": _guard(request, last, guard, state, str(doing.get("state") or "running")),
    }


def _phase(
    request: Mapping[str, Any] | None,
    last: Mapping[str, Any] | None,
    head: Mapping[str, Any],
    nodes: list[dict[str, Any]],
    moment: float,
) -> tuple[str, str, dict[str, Any] | None]:
    """The phase's key, its detail and the call it is about, the first of §5.1's rows that holds."""
    status = str(head.get("status") or "idle")
    calls = [node for node in nodes if node.get("kind") == "call"]
    gateway = GATEWAY_PHASES.get(str((request or {}).get("phase") or ""), "")
    if request is not None and gateway == "held":
        held = request.get("held") or {}
        return "held", f"the Guide paused it ({held.get('by') or 'you'})", None
    asking = [call for call in calls if call.get("asking")]
    if asking:
        call = asking[-1]
        return "you", f"{call.get('tool')} asks for your approval ({call.get('permission') or 'a permission'})", call
    questions = [
        call for call in calls if call.get("tool") == "question" and call.get("status") in ("pending", "running")
    ]
    if questions:
        return "you", "the model asks you a question", questions[-1]
    if status == "retry":
        return "retry", _retry(head, moment), None
    if any(node.get("kind") == "band" and not node.get("done") for node in nodes):
        doing = PHASES[_streaming(request)] if request is not None else ""
        return "compacting", f"its summary: {doing}" if doing else "", None
    if request is not None:
        return _streaming(request), "", None
    running = [call for call in calls if call.get("status") == "running"]
    if running:
        return "tool", "", running[-1]
    if status == "busy":
        return "between", "", None
    if last is not None and last.get("looped"):
        return "looped", "the session is idle; that text is not in the context", None
    return "idle", "", None


def _streaming(request: Mapping[str, Any]) -> str:
    """A request in flight's phase: the gateway's, and while it answers, by the kind of text it wrote last."""
    phase = str(request.get("phase") or "")
    if phase == ANSWERING:
        return BY_KIND.get(str(request.get("newest") or ""), "answering")
    return GATEWAY_PHASES.get(phase, "answering")


def _retry(head: Mapping[str, Any], moment: float) -> str:
    """OpenCode's attempt, when the next is due, and its words."""
    said = f"attempt {head.get('attempt') or '?'} of at most {RETRIES}"
    due = head.get("next")
    if isinstance(due, int | float) and not isinstance(due, bool):
        said += f", the next in {max(round(float(due) / 1000 - moment), 0)} s"
    words = str(head.get("retry") or "")
    return f"{said}: {words}" if words else said


def _facts(
    request: Mapping[str, Any] | None, last: Mapping[str, Any] | None, routes: Mapping[str, Any], facts_of: Facts
) -> Mapping[str, Any]:
    """The facts the budgets are read with: the slot's the request in flight went to; else the preset's that answered
    the last request; else the agent role's slot's now."""
    slots: Mapping[str, Any] = routes.get("slots") or {}
    if request is not None:
        route = slots.get(str(request.get("slot") or "")) or {}
        if route.get("status") == "ready" and route.get("facts"):
            return dict(route["facts"])
    if last is not None and last.get("preset"):
        found = facts_of(str(last["preset"]))
        if found:
            return found
    name = str((routes.get("roles") or {}).get(ROLE) or routes.get("default_slot") or "main")
    route = slots.get(name) or {}
    return dict(route.get("facts") or {}) if route.get("status") == "ready" else {}


def _budgets(
    request: Mapping[str, Any] | None, last: Mapping[str, Any] | None, facts: Mapping[str, Any]
) -> dict[str, Any]:
    """The thinking and the answer against their budgets: live and "about" while the request streams, the engine's
    count once it ended."""
    engine: Mapping[str, Any] = facts.get("engine") or {}
    thinking_budget = engine.get("thinking_budget")
    budget = int(thinking_budget) if isinstance(thinking_budget, int) and thinking_budget > 0 else None
    limit = int(engine["output"]) if engine.get("output") else None
    shown = request if request is not None else last
    if shown is None:
        return {"thinking": None, "output": None, "of": ""}
    counts: Mapping[str, Any] = shown.get("counts") or {}
    heard = sum(int(value or 0) for value in counts.values())
    thinking = int(counts.get("thinking") or 0)
    if request is not None:
        return {"thinking": {"tokens": thinking, "about": True, "budget": budget},
                "output": {"tokens": int(request.get("tokens") or heard), "about": True, "budget": limit},
                "of": "this step"}  # fmt: skip
    fields: Mapping[str, Any] = engine.get("fields") or {}
    exact = reported(shown, fields.get("output"))
    written = exact if exact is not None else int(shown.get("tokens") or heard)
    scaled = round(thinking * exact / heard) if exact is not None and heard else thinking
    return {"thinking": {"tokens": scaled, "about": True, "budget": budget},
            "output": {"tokens": written, "about": exact is None, "budget": limit},
            "of": "the last step"}  # fmt: skip


def _prompt(request: Mapping[str, Any] | None, ended: list[dict[str, Any]], facts_of: Facts) -> dict[str, Any]:
    """This step's time to its first token (or whether it is still read), and the previous step's prompt size and the
    part read from the cache, where its engine reports them."""
    first = None
    if request is not None:
        first = request.get("first_ms")
    elif ended:
        first = ended[-1].get("first_ms")
    size = cached = None
    for each in reversed(ended):
        fields: Mapping[str, Any] = ((facts_of(str(each.get("preset"))) or {}).get("engine") or {}).get("fields") or {}
        size = reported(each, fields.get("prompt"))
        if size is not None:
            cached = reported(each, fields.get("cached"))
            break
    return {
        "first_ms": first,
        "reading": request is not None and request.get("phase") == READING,
        "tokens": size,
        "cached": cached,
        "of": "the previous step" if request is not None else "the last step",
    }


def _speed(
    request: Mapping[str, Any] | None, ended: list[dict[str, Any]], last: Mapping[str, Any] | None
) -> dict[str, Any]:
    """The tokens a second now (the request in flight's, else the last's), and each step's, the newest last."""
    steps = [float(each["per_second"]) for each in ended if each.get("per_second")]
    current = request.get("per_second") if request is not None else (last or {}).get("per_second")
    if request is not None and request.get("per_second"):
        steps.append(float(request["per_second"]))
    return {"now": current, "steps": steps[-SPEEDS:]}


def _guard(
    request: Mapping[str, Any] | None,
    last: Mapping[str, Any] | None,
    guard: Mapping[str, Any],
    state: str,
    gateway: str,
) -> dict[str, Any]:
    """The loop guard: off; watching, with each part's newest share; or what it stopped; nothing while the gateway, in
    which it runs, does not run. `guard` is the setting the running gateway applies, with what its settings file says
    now (`file`) when the two may differ: a change waits for the gateway's restart (`restart`)."""
    on, ratio = bool(guard.get("on")), guard.get("ratio")
    file = guard.get("file")
    restart = isinstance(file, Mapping) and (bool(file.get("on")) != on or (on and file.get("ratio") != ratio))
    stopped = str((last or {}).get("looped") or "") if request is None else ""
    if not on:
        return {"on": False, "ratio": ratio, "parts": [], "stopped": stopped, "said": "off", "restart": restart}
    watching = (request or {}).get("loop_guard")
    parts = list((watching or {}).get("parts") or [])
    if stopped:
        said = f"stopped the last answer: {stopped}"
    elif gateway != "running":
        said = f"the gateway is {gateway}"
    elif request is not None and watching is None:
        early = state in ("slot", "reading", "held", "again")
        said = "watching · nothing written yet" if early else "not reading this answer: it is not streamed"
    else:
        said = "watching · nothing repeats"
    return {"on": True, "ratio": (watching or {}).get("ratio") or ratio, "parts": parts, "stopped": stopped,
            "said": said, "restart": restart}  # fmt: skip
