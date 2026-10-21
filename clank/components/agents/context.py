"""A session's context totals (design 0012 §4.1 and §4.4, decision 0067): how much of the window the session uses, how
much is left before its agent program compacts it, the share read from the cache, what sits on the GPU and whose
conversation the engine holds, from the loaded slot's facts only, never from one engine's or one model's numbers.

`totals` is a pure function over what the gateway says (the session's activity with its requests that ended, and each
slot's newest request), the routes (each slot's preset and its facts) and a preset's facts by its name:

- **The last finished step** is the session's own newest request that ended well (its status 200, no error, not
  stopped by the loop guard, its client still there, its stream not broken off by the engine). Its figures are read
  where the facts of the preset that answered it say its engine reports them (`fields`: `usage.prompt_tokens`,
  `timings.cache_n`, ...); a figure the engine does not report is absent (`None`, and `cache_reported` false), never a
  number.
- **The window is the step's**: the facts of the preset that answered the last finished step, and with no step yet the
  slot's facts now. When the slot runs another preset now (`switched`), the window, the line and the GPU line change
  with the next step (design 0012 §4).
- **Used** is the step's prompt and its answer, the figure OpenCode's compaction reads; **left** is the compaction line
  (the agent program's rule, `AgentProgram.compaction`) less it.
- **On the GPU**: an engine with an exact window attends that many tokens exactly and keeps the rest in system memory;
  one without attends its whole window, on the GPU or, for an engine that runs on the CPU, in system memory; a cloud
  model (design 0016 §13) attends its whole window in the cloud (`device: cloud`).
- **Whose conversation the engine holds**: the slot's newest request that reached its engine. When it is another
  session's (a subagent's too, or a request of no session) and the engine keeps one conversation, the engine is taken:
  the session's next step reads its whole prompt again (design 0012 §3). An engine that may keep several is never
  said to be taken. An engine that holds no conversation is `lost`, whoever's request it read last: the slot is not
  ready (its state: stopped, starting, ...), it runs another preset than the step's (`switched`), or its engine
  stopped or started again since that request (`restarted`, the gateway's `gone`); a request in flight in a ready
  slot is in its engine now.
- **The parts** (§4.2, §11 step 12; `estimate.py`): what fills the window, part by part and item by item, estimated
  from the gateway's census of the last finished step's request (its items' steps from the session's flow, `view`),
  by the facts of the preset that answered it (`parts`, None when the gateway made no census of it); and each part's
  tokens of every step whose census and prompt are known (`steps`, oldest first), by the facts of the preset that
  answered each.
"""

from collections.abc import Callable, Mapping
from typing import Any

from clank.components.agents.adapters.program import Compaction
from clank.components.agents.estimate import estimate, shares

Facts = Callable[[str], dict[str, Any] | None]  # a preset's facts, by its name (`Gateway.facts`)
Rule = Callable[[int, int], Compaction | None]  # the agent program's compaction, for a window and an output limit
ROLE = "agent"


def totals(
    session: str,
    doing: Mapping[str, Any],
    routes: Mapping[str, Any],
    facts_of: Facts,
    compaction: Rule,
    view: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The session's context totals, as the Monitor's Context window panel shows them, and its parts, their items'
    steps read from its flow (`view`) (module docstring)."""
    step = _last_finished(doing.get("ended") or [])
    flying = [request for request in doing.get("requests") or [] if request.get("slot")]
    name = str((step or {}).get("slot") or (flying[-1]["slot"] if flying else "") or _role_slot(routes))
    route: Mapping[str, Any] = (routes.get("slots") or {}).get(name) or {}
    now = route.get("facts") if route.get("status") == "ready" else None
    facts = (facts_of(str(step["preset"])) if step is not None and step.get("preset") else None) or now
    engine: Mapping[str, Any] = (facts or {}).get("engine") or {}
    fields: Mapping[str, str] = engine.get("fields") or {}
    window, output = engine.get("window"), engine.get("output")
    rule = compaction(int(window), int(output)) if window and output else None
    prompt = reported(step, fields.get("prompt"))
    answer = reported(step, fields.get("output"))
    used = prompt + answer if prompt is not None and answer is not None else None
    cached = reported(step, fields.get("cached"))
    slot = {"name": name, "status": route.get("status") or "stopped", "preset": route.get("preset"),
            "title": route.get("title")}  # fmt: skip
    held: Mapping[str, Any] | None = (doing.get("slots") or {}).get(name)
    switched = _switched(step, facts, now)
    shown = None if step is None else {"id": step.get("id"), "time": step.get("time"), "preset": step.get("preset")}
    return {
        "session": session,
        "gateway": {"state": str(doing.get("state") or ""), "problem": str(doing.get("problem") or "")},
        "slot": slot,
        "facts": facts,
        "step": shown,
        "window": window,
        "output": output,
        "line": rule.line if rule else None,
        "keeps": rule.keeps if rule else None,
        "rule": rule.rule if rule else "",
        "prompt": prompt,
        "answer": answer,
        "used": used,
        "left": rule.line - used if rule is not None and used is not None else None,
        "share": used / window if used is not None and window else None,
        "cached": cached,
        "cache_reported": bool(fields.get("cached")),
        "cache_share": round(cached / prompt, 4) if cached is not None and prompt else None,
        "gpu": _gpu(engine, used) if engine else None,
        "holder": _holder(session, held, engine, _lost(str(slot["status"]), held, switched)),
        "switched": switched,
        "parts": estimate((step or {}).get("census"), prompt, facts, view, rule.keeps if rule else None, cached),
        "steps": steps(doing.get("ended") or [], facts_of, facts),
    }


def steps(ended: list[dict[str, Any]], facts_of: Facts, fallback: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Each part's tokens of every step whose census and prompt are known, oldest first: its request's id, its prompt
    and its parts, by the facts of the preset that answered it (`fallback` for one that names none)."""
    found: list[dict[str, Any]] = []
    known: dict[str, Mapping[str, Any] | None] = {}
    for request in ended:
        census = request.get("census")
        if not census:
            continue
        preset = str(request.get("preset") or "")
        if preset not in known:
            known[preset] = (facts_of(preset) if preset else None) or fallback
        facts = known[preset]
        fields: Mapping[str, str] = ((facts or {}).get("engine") or {}).get("fields") or {}
        prompt = reported(request, fields.get("prompt"))
        parts = shares(census, prompt, facts)
        if prompt and parts:
            found.append({"request": request.get("id"), "prompt": prompt, "parts": parts})
    return found


def _role_slot(routes: Mapping[str, Any]) -> str:
    """The slot the agent's requests go to."""
    return str((routes.get("roles") or {}).get(ROLE) or routes.get("default_slot") or "main")


def _last_finished(ended: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The newest request that ended well: answered (200), no error, not stopped by the loop guard, its client there."""
    well = [request for request in ended if request.get("status") == 200 and not request.get("error")
            and not request.get("looped") and not request.get("left") and not request.get("broken")]  # fmt: skip
    return well[-1] if well else None


def reported(request: Mapping[str, Any] | None, path: str | None) -> int | None:
    """A number the engine reported at a dotted path of a request (`usage.prompt_tokens`); None when it did not."""
    if request is None or not path:
        return None
    found: Any = request
    for name in path.split("."):
        found = found.get(name) if isinstance(found, Mapping) else None
    return int(found) if isinstance(found, int | float) and not isinstance(found, bool) else None


CLOUD_GPU = "does not apply: the model runs at its cloud provider, not on this machine"  # design 0016 §13, in words


def _gpu(engine: Mapping[str, Any], stored: int | None) -> dict[str, Any]:
    """What the engine attends of the stored conversation: exactly its exact window on the GPU and the rest in system
    memory, or its whole window, on the GPU or in system memory (an engine on the CPU), or in the cloud (a cloud
    model, design 0016 §13)."""
    cloud = str(engine.get("provider") or "").startswith("cloud ")
    exact: Mapping[str, Any] | None = engine.get("exact")
    tokens = int(exact["tokens"]) if exact else None
    attended = None if stored is None else (min(stored, tokens) if tokens is not None else stored)
    return {
        "device": "cloud" if cloud else "gpu" if engine.get("on_gpu") else "cpu",
        "exact": tokens,
        "block": exact.get("block") if exact else None,
        "first": exact.get("first") if exact else None,
        "picks": str(exact.get("picks") or "") if exact else "",
        "stored": stored,
        "attended": attended,
        "elsewhere": None if stored is None or attended is None else stored - attended,
        **({"said": CLOUD_GPU} if cloud else {}),
    }


def _lost(status: str, held: Mapping[str, Any] | None, switched: Mapping[str, Any] | None) -> str:
    """Why the slot's engine holds no conversation now, "" when it may: the slot is not ready (its state), it runs
    another preset than the step's, or its engine changed since the newest request ended there."""
    if status != "ready":
        return status
    if held and held.get("flying"):
        return ""  # in its engine now
    if switched:
        return "switched"
    return "restarted" if held and held.get("gone") else ""


def _holder(
    session: str, held: Mapping[str, Any] | None, engine: Mapping[str, Any], lost: str
) -> dict[str, Any] | None:
    """The slot's newest request that reached its engine, and what it means for the session: its own, a subagent's,
    whether the engine was taken (it keeps one conversation, and this is another's), or why it holds none (`lost`)."""
    if not held and not lost:
        return None
    found = dict(held or {})
    own = not lost and found.get("session") == session
    return {
        **found,
        "this": own,
        "subagent": not lost and not own and found.get("parent") == session,
        "taken": not lost and not own and bool(engine.get("one_conversation")),
        "lost": lost,
    }


def _switched(
    step: Mapping[str, Any] | None, facts: Mapping[str, Any] | None, now: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """The slot's preset now, when it is another than the one whose facts the totals were read with."""
    if step is None or not now or not facts or now.get("preset") == facts.get("preset"):
        return None
    engine = now.get("engine") or {}
    return {"preset": now.get("preset"), "title": now.get("title"), "window": engine.get("window"),
            "output": engine.get("output")}  # fmt: skip
