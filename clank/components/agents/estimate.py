"""The context's parts, estimated (design 0012 §4.2, §4.3, §4.6; decisions 0051, 0052 and 0067): what fills a
session's context window, part by part and item by item, in tokens, from the gateway's census of the request of its
last finished step (`clank/components/gateway/census.py`: each part's characters and its biggest items) and the facts
of the preset that answered it, never one engine's or one model's numbers.

- **The template's rule** (the model's catalog entry, `template.earlier_thinking`): thinking before the last real user
  message is left out (`dropped`, Qwen's reference template), kept (`kept`), or the model has no thinking part at all
  (`none`); a model whose template is not known keeps it, and says so (`unknown`).
- **The calibration** (`calibration.tokens_per_character`, by part): each part's characters weigh as many tokens a
  character as the model's calibration says, a part it does not name the mean of those it does; without one, every part
  counts alike by its characters, and the estimate says so (`how`).
- **The shares** add up to the engine's own count of the prompt exactly (the largest remainder: each part gets the whole
  tokens of its share, and the parts with the largest fractions one more), so the estimate never claims more or fewer
  tokens than the engine read (`shares`).
- **Each item** of the biggest the census kept, in tokens (its characters weighed as its part's), with its step: the
  step that made its call (a result's or a call's id, or the first call of a message, joined to the flow's call and its
  step's number); the owner's message, the step that read it (the step of the answer after it); the model's text or
  thinking whose answer made no call, the step as many steps on from the one that made the nearest call before it as its
  answer is answers on (`hops`), when the flow says none of those steps made a call; else none, never a guess. An item
  with a call names that call's part in the flow (`node`), which the Guide's Drop clears. A result cleared (its call's
  `cleared` in the flow) is marked, with who cleared it and what that freed when it was the owner through the Guide's
  Drop (`cleared_by`, `freed`), and so is an item inside the tail a compaction keeps (`kept`: the characters after it
  and its own, at the prompt's tokens a character, within the agent program's `keeps`).
- **Where the room went** (`groups`): the tool results by tool, the system prompt and tool definitions (OpenCode's own,
  sent with every step), the thinking sent back, loop text, the owner's messages, the model's text and the calls; the
  biggest `GROUPS`.
- **Could be freed** (`freed`, §4.6): the loop text in tool results and the earlier results of calls made again (each
  dropped by the Guide's Drop, design 0012 §9.7, the only items it clears), less the results already cleared; the loop
  text the model wrote, which only compacting clears (offered to Compact now, never to Drop); and compacting now (about
  the prompt less what a compaction keeps; its summary is not known before it is written).
- **The newest** (`suffix`, §4.4): the tokens from the last user message on, about, or from where the cache stopped
  matching when that is later (KVMem keeps them on the GPU at every step); `since` says which (`message`, `cache`).

`shares` gives each part's tokens alone, for a step whose census kept only its numbers (the Context view's last ten
steps and its chart). Pure: no I/O.
"""

from collections.abc import Callable, Mapping
from typing import Any

LABELS = {
    "system": "system prompt", "tools": "tool definitions", "yours": "your messages", "text": "the model's text",
    "thinking": "thinking sent back", "calls": "tool calls", "results": "tool results", "loop": "loop text",
}  # fmt: skip
GROUPS = 6  # where the room went: the biggest groups
Rate = Callable[[str], float]


def estimate(
    census: Mapping[str, Any] | None,
    prompt: int | None,
    facts: Mapping[str, Any] | None,
    view: Mapping[str, Any] | None = None,
    keeps: int | None = None,
    cached: int | None = None,
) -> dict[str, Any] | None:
    """The parts, their items, where the room went and what could be freed (module docstring), from a step's census and
    its engine's count of its prompt; None without either."""
    model: Mapping[str, Any] = (facts or {}).get("model") or {}
    weighed = _weighed(census, model)
    if census is None or weighed is None or not prompt or prompt <= 0:
        return None
    rule, rate, chars, counts, weights = weighed
    tokens = _shared(weights, prompt)
    scale = prompt / sum(weights.values())
    counted = sum(chars[name] for name in weights)
    calls, order, nodes = _flow(view)
    items = []
    for item in census.get("items") or []:
        if item.get("earlier") and rule in ("dropped", "none"):
            continue
        whole, call = int(item.get("chars") or 0), str(item.get("call") or "")
        node = nodes.get(call) or {}
        tail = (int(item.get("after") or 0) + whole) * prompt / counted if counted else None
        items.append({
            "part": item.get("part"), "of": item.get("of"), "chars": whole, "call": call,
            "tokens": round(whole * rate(str(item.get("part"))) * scale), "what": item.get("what") or "",
            "tool": item.get("tool") or "", "step": _step(item, calls, order), "loop": item.get("loop") or "",
            "again": bool(item.get("again")), "cleared": bool(node.get("cleared")), "node": str(node.get("id") or ""),
            "cleared_by": str(node.get("cleared_by") or ""), "freed": node.get("freed"),
            "earlier": bool(item.get("earlier")),
            "kept": keeps is not None and tail is not None and not item.get("earlier") and tail <= keeps,
        })  # fmt: skip
    items.sort(key=lambda item: -item["tokens"])
    parts = []
    for name in weights:
        biggest = next((item for item in items if item["part"] == name), None)
        parts.append({"part": name, "label": LABELS.get(name, name), "tokens": tokens[name],
                      "share": tokens[name] / prompt, "items": counts.get(name, 0), "chars": chars[name],
                      "biggest": biggest})  # fmt: skip
    suffix = round(int(census.get("from_last_user") or 0) * prompt / counted) if counted else None
    since = "message"
    if suffix is not None and cached is not None and max(prompt - cached, 0) < suffix:
        suffix, since = max(prompt - cached, 0), "cache"
    return {
        "tokens": prompt,
        "calibrated": bool((model.get("calibration") or {}).get("tokens_per_character")),
        "how": _how(model, prompt),
        "thinking": rule,
        "parts": parts,
        "items": items,
        "groups": _groups(census, tokens, counts, rate, scale),
        "freed": _freed(census, tokens, counts, rate, scale, prompt, keeps, items),
        "suffix": suffix,
        "since": since,
        "images": int(census.get("images") or 0),
        "keeps": keeps,
    }


def shares(census: Mapping[str, Any] | None, prompt: int | None, facts: Mapping[str, Any] | None) -> dict[str, int]:
    """Each part's tokens of a step's prompt (module docstring), {} without a census or a count."""
    weighed = _weighed(census, (facts or {}).get("model") or {})
    if weighed is None or not prompt or prompt <= 0:
        return {}
    return _shared(weighed[4], prompt)


def _weighed(
    census: Mapping[str, Any] | None, model: Mapping[str, Any]
) -> tuple[str, Rate, dict[str, int], dict[str, int], dict[str, float]] | None:
    """The template's rule, each part's rate, characters and items by the rule, and its weight; None when nothing
    weighs."""
    if not census:
        return None
    template: Mapping[str, Any] = model.get("template") or {}
    rule = str(template.get("earlier_thinking") or "unknown")
    per: Mapping[str, float] = (model.get("calibration") or {}).get("tokens_per_character") or {}
    mean = sum(per.values()) / len(per) if per else 1.0

    def rate(part: str) -> float:
        return float(per.get(part, mean))

    chars = {str(name): int(value or 0) for name, value in (census.get("chars") or {}).items()}
    counts = {str(name): int(value or 0) for name, value in (census.get("counts") or {}).items()}
    if rule in ("kept", "unknown") and "thinking" in chars:
        chars["thinking"] += int(census.get("earlier") or 0)
        counts["thinking"] = counts.get("thinking", 0) + int(census.get("earlier_items") or 0)
    weights = {name: chars[name] * rate(name) for name in chars if not (name == "thinking" and rule == "none")}
    if sum(weights.values()) <= 0:
        return None
    return rule, rate, chars, counts, weights


def _shared(weights: Mapping[str, float], prompt: int) -> dict[str, int]:
    """The prompt's tokens shared out by weight, adding up to it exactly (the largest remainder)."""
    total = sum(weights.values())
    exact = {name: weight * prompt / total for name, weight in weights.items()}
    whole = {name: int(value) for name, value in exact.items()}
    left = prompt - sum(whole.values())
    for name in sorted(exact, key=lambda name: exact[name] - whole[name], reverse=True)[:left]:
        whole[name] += 1
    return whole


def _how(model: Mapping[str, Any], prompt: int) -> str:
    said = f"each part's characters, shared out so the parts add up to the engine's own count of {prompt:,} tokens"
    name = str(model.get("name") or "the model")
    calibration = model.get("calibration") or {}
    if calibration.get("tokens_per_character"):
        return f"{said}; {name} is calibrated ({calibration.get('measured')}): each part by its own tokens a character"
    return f"{said}; {name} is not calibrated, so every part counts alike by its characters"


def _flow(
    view: Mapping[str, Any] | None,
) -> tuple[dict[str, int], list[Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """From the session's flow: each call's step number, by its call id; the steps in the context, in order; and
    each call's node, by its call id (its part, which the Guide's Drop names, and whether and by whom its result was
    cleared)."""
    nodes = [node for node in (view or {}).get("nodes") or [] if not node.get("undone")]
    steps = {node["id"]: node for node in nodes if node.get("kind") == "step"}
    calls = {
        str(node["call"]): int(steps[node["step"]]["n"])
        for node in nodes
        if node.get("kind") == "call" and node.get("call") and node.get("step") in steps
    }
    order = [node for node in steps.values() if node.get("context") != "left"]
    nodes_of = {str(node["call"]): node for node in nodes if node.get("kind") == "call" and node.get("call")}
    return calls, order, nodes_of


def _step(item: Mapping[str, Any], calls: Mapping[str, int], order: list[Mapping[str, Any]]) -> int | None:
    """The step an item came with (module docstring), None when the flow does not say."""
    if item.get("call"):
        return calls.get(str(item["call"]))
    if item.get("calls"):
        return calls.get(str(item["calls"][0]))
    if item.get("next"):
        return calls.get(str(item["next"]))
    if item.get("near") and (before := calls.get(str(item["near"]))) is not None:
        hops = max(int(item.get("hops") or 1), 1)
        later = sorted((step for step in order if int(step.get("n") or 0) > before), key=lambda step: int(step["n"]))
        if len(later) >= hops and not any(step.get("calls") for step in later[:hops]):
            return int(later[hops - 1]["n"])
    return None


def _groups(
    census: Mapping[str, Any], tokens: Mapping[str, int], counts: Mapping[str, int], rate: Rate, scale: float
) -> list[dict[str, Any]]:
    """Where the room went: the biggest groups, each in words with its tokens and share."""
    prompt = sum(tokens.values())
    found: list[tuple[str, int]] = []
    for tool, (chars, count) in (census.get("tools") or {}).items():
        found.append((f"{tool}: {count} result{'' if count == 1 else 's'}", round(chars * rate("results") * scale)))
    own = tokens.get("system", 0) + tokens.get("tools", 0)
    found.append(("the system prompt and tool definitions, every step", own))
    for name in ("thinking", "loop", "yours", "text", "calls"):
        if name in tokens:
            count = counts.get(name, 0)
            found.append((f"{LABELS[name]}: {count} item{'' if count == 1 else 's'}", tokens[name]))
    found = sorted((each for each in found if each[1] > 0), key=lambda each: -each[1])[:GROUPS]
    return [{"words": words, "tokens": shown, "share": shown / prompt if prompt else 0.0} for words, shown in found]


def _freed(
    census: Mapping[str, Any],
    tokens: Mapping[str, int],
    counts: Mapping[str, int],
    rate: Rate,
    scale: float,
    prompt: int,
    keeps: int | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """What could be freed, and how: the loop text in tool results and the earlier results of calls made again (the
    Guide's Drop, an item at a time), each less the results already cleared (by the Guide's Drop or by OpenCode); the
    loop text the model wrote, which only compacting clears; and compacting now (the Guide's Compact now)."""
    found = []
    results = census.get("loop_results") or [0, 0]
    gone = [item for item in items if item["cleared"] and item["part"] == "loop" and item["of"] == "results"]
    dropped = round(results[0] * rate("loop") * scale)
    loop, count = dropped - sum(item["tokens"] for item in gone), int(results[1]) - len(gone)
    if loop > 0 and count > 0:
        found.append({"what": "loop", "words": "the loop text in tool results", "tokens": loop, "items": count,
                      "how": "drop"})  # fmt: skip
    again = census.get("again") or [0, 0]
    gone = [item for item in items if item["cleared"] and item["again"]]
    count = int(again[1]) - len(gone)
    freed = round(again[0] * rate("results") * scale) - sum(item["tokens"] for item in gone)
    if count > 0 and freed > 0:
        found.append({"what": "again", "words": "the earlier results of calls made again", "tokens": freed,
                      "items": count, "how": "drop"})  # fmt: skip
    kept, count = tokens.get("loop", 0) - dropped, counts.get("loop", 0) - int(results[1])
    if kept > 0 and count > 0:  # the model's own words: no Drop clears them, a compaction does
        found.append({"what": "loop_kept", "words": "the loop text the model wrote, which only compacting clears",
                      "tokens": kept, "items": count, "how": "compact"})  # fmt: skip
    if keeps is not None and prompt > keeps:
        found.append({"what": "compact", "words": "compact now: OpenCode sums the session up", "tokens": prompt - keeps,
                      "items": 0, "how": "compact"})  # fmt: skip
    return found
