"""The census of a model request (design 0012 §4.2, §4.3, §4.6; decisions 0051 and 0052): what fills the context the
request carries, part by part and item by item, in characters, from its body as the gateway parsed it. One pass, no
engine work; the service shares the characters out so that they add up to the engine's own count, by the loaded
model's facts (`clank/components/agents/estimate.py`).

**The parts** (`PARTS`, the style's names for them): the system prompt (`system`), the tool definitions (`tools`, each
tool's as the request gives it), the owner's messages (`yours`), the model's text (`text`), the thinking sent back
(`thinking`, OpenCode's `reasoning_content`), the tool calls (`calls`: each one's name and arguments), the tool results
(`results`) and loop text (`loop`). Thinking before the last real user message (the last message whose role is `user`;
a tool's result is not one) is counted apart (`earlier`): Qwen's reference template renders it only after that
message, and whether a model's does is its catalog entry's to say, read in the service.

**Each item** (a message's text, a thinking, a call, a result, a tool's definition) says its part (and, for loop text,
the part it came from: `of`), its characters, the index of its message (`at`; -1 for a tool's definition), the
characters after it to the request's end (`after`, for the tail a compaction keeps; earlier thinking is not counted
there), its call id (`call`: a call's own, a result's `tool_call_id`, which are OpenCode's call ids), the ids of the
calls of its message (`calls`, for a text or a thinking), its tool, what it is in words (`what`), why it is loop text
(`loop`, "" when it is not), whether a newer call with the same arguments made it one that could be freed (`again`)
and whether it is earlier thinking (`earlier`). An item without a call of its own names the calls around it, so the
service can tell its step from the session's flow: the owner's message, the first call of the answer after it
(`next`, "" when that answer made none: the step that read it); the model's text or thinking whose answer made no call,
the first call of the nearest answer before it that made one (`near`) and how many answers on from that one it is
(`hops`, 1 for the very next); the owner's message whose next answer made no call is placed as that answer is.

**Loop text** (§4.3, decision 0052), taken out of the part it came from: an item the model wrote (its text, its
thinking after the last user message, a call's arguments) that compresses over its whole length as far as a loop does,
by the loop guard's measure (`loops.share_of`, under its `ratio`, the item at least as long as its `shortest` stretch);
the result of a call whose arguments did (it echoes it, as OpenCode's error repeats a cut call); and the third and later
identical call (the same name and arguments) among the last `REPEATS` calls, with its result. What a tool gave back is
not measured by itself: a log or a table compresses that far without any loop.

**Could be freed** (§4.6): the earlier results of a call made again with the same arguments (a file read again among
them), loop text apart: the newest result is in the context too (`again`); and the loop text that is a call's result
(`loop_results`), the only loop text the Guide's Drop can clear.

**Its words**: what an item is (`what`) holds up to `WHAT` characters of the request (the owner's message, the
model's text or thinking, a call's first argument) only with `words`, which the gateway gives when it keeps its records
(`records` in `config/gateway.json`): with the records off, nothing of a prompt's text leaves the gateway, and an item
says its kind and its tool's name alone ("your message", "the result of read"), its sizes and its place.

Only the biggest items are kept (`KEPT`, and each part's `PER_PART`, earlier thinking's too), so a request of hundreds
of items is kept in a few kilobytes; the parts' characters and counts are of every item. A body of odd shapes is counted
as far as it reads, never failing (a part it does not know counts nothing). Pure: no I/O.
"""

import bisect
import json
from collections.abc import Mapping
from typing import Any

from clank.components.gateway.loops import share_of

PARTS = ("system", "tools", "yours", "text", "thinking", "calls", "results", "loop")
KEPT = 40  # the biggest items kept
PER_PART = 8  # and each part's biggest
REPEATS = 12  # the newest calls among which a call made a third time is loop text
WHAT = 80  # characters of what an item is, in words
IMAGES = ("image_url", "input_image", "image")
ORDINALS = ("third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth")


def census(body: Mapping[str, Any], ratio: float, shortest: int, *, words: bool = True) -> dict[str, Any]:
    """The census of a request's body (module docstring), measured with the loop guard's `ratio` and `shortest`
    stretch; without its `words`, no item says any text of the request (module docstring)."""

    def of(said: str) -> str:
        return f": {_words(said)}" if words else ""

    def does(arguments: str) -> str:
        return f" {_first(arguments)}".rstrip() if words else ""

    raw = body.get("messages") if isinstance(body, Mapping) else None
    messages = [message if isinstance(message, dict) else {} for message in (raw if isinstance(raw, list) else [])]
    last_user = max((index for index, message in enumerate(messages) if message.get("role") == "user"), default=-1)
    items: list[dict[str, Any]] = []
    images = 0
    tools = body.get("tools") if isinstance(body, Mapping) else None
    for definition in tools if isinstance(tools, list) else []:
        name = str(((definition or {}).get("function") or {}).get("name") or "") if isinstance(definition, dict) else ""
        items.append(_item("tools", len(json.dumps(definition, ensure_ascii=False)), -1, tool=name,
                           what=f"the definition of {name or 'a tool'}"))  # fmt: skip
    named: dict[str, tuple[str, str]] = {}  # each call's id: its name and its arguments
    answers: list[tuple[int, str]] = []  # each answer's message index and its first call's id ("" for none)
    for index, message in enumerate(messages):
        role = message.get("role")
        if role in ("system", "developer"):
            items.append(_item("system", len(_text(message.get("content"))), index, what="the system prompt"))
        elif role == "user":
            said = _text(message.get("content"))
            images += _images(message.get("content"))
            items.append(_item("yours", len(said), index, what=f"your message{of(said)}"))
        elif role == "assistant":
            calls = _calls(message.get("tool_calls"))
            ids = [id for id, _, _ in calls if id]
            answers.append((index, ids[0] if ids else ""))
            thought = _text(message.get("reasoning_content") or message.get("reasoning"))
            if thought:
                items.append(_item("thinking", len(thought), index, calls=ids, what=f"thinking{of(thought)}",
                                   earlier=index < last_user, text=thought))  # fmt: skip
            said = _text(message.get("content"))
            if said:
                items.append(_item("text", len(said), index, calls=ids, what=f"the model's text{of(said)}",
                                   text=said))  # fmt: skip
            for id, name, arguments in calls:
                named[id] = (name, arguments)
                items.append(_item("calls", len(name) + len(arguments), index, call=id, tool=name,
                                   what=f"{name}{does(arguments)}".strip(), text=arguments))  # fmt: skip
        elif role in ("tool", "function"):
            id = str(message.get("tool_call_id") or "")
            name, arguments = named.get(id, (str(message.get("name") or ""), ""))
            which = f"{name}{does(arguments)}".strip() if name else "a call"
            items.append(_item("results", len(_text(message.get("content"))), index, call=id, tool=name,
                               what=f"the result of {which}"))  # fmt: skip
    _around(items, answers)
    _loops(items, ratio, shortest)
    _again(items)
    return _counted(items, last_user, images, len(messages))


def _item(part: str, chars: int, at: int, **fields: Any) -> dict[str, Any]:
    found = {"part": part, "of": part, "chars": chars, "at": at, "after": 0, "call": "", "calls": [], "tool": "",
             "what": "", "loop": "", "again": False, "earlier": False, "near": "", "next": "", "hops": 0}  # fmt: skip
    return {**found, **fields}


def _around(items: list[dict[str, Any]], answers: list[tuple[int, str]]) -> None:
    """The calls around an item without one of its own (module docstring): `next` for the owner's message, `near` for
    the model's text or thinking whose answer made no call. One pass over the answers, then a binary search for each
    item, so a chat of thousands of answers costs little more than its length."""
    indices = [index for index, _ in answers]
    newest: list[int] = []  # for each answer, the place of the newest answer up to it that made a call (-1: none)
    for place, (_, first) in enumerate(answers):
        newest.append(place if first else (newest[-1] if newest else -1))

    def around(item: dict[str, Any], place: int) -> None:
        """The answer at `place` made no call: the call before it, and how many answers on it is (`hops`)."""
        before = newest[place - 1] if place > 0 else -1
        if before >= 0:
            item["near"], item["hops"] = answers[before][1], place - before

    for item in items:
        if item["part"] == "yours":
            after = bisect.bisect_right(indices, item["at"])
            if after < len(answers) and answers[after][1]:
                item["next"] = answers[after][1]
            elif after < len(answers):
                around(item, after)  # the step that read it made no call: placed as that answer is
        elif item["part"] in ("text", "thinking") and not item["calls"]:
            around(item, bisect.bisect_left(indices, item["at"]))


def _loops(items: list[dict[str, Any]], ratio: float, shortest: int) -> None:
    """Mark loop text (module docstring): items that compress like a loop, the results that echo them, and calls made
    a third time among the newest `REPEATS`."""
    looped: dict[str, str] = {}  # a call's id: why its result is loop text
    for item in items:
        written = str(item.get("text") or "")
        measured = item["part"] in ("text", "thinking", "calls") and not item["earlier"] and len(written) >= shortest
        if measured and (share := share_of(written)) < ratio:
            item["loop"] = f"it compresses to {share:.1%} of its size"
            if item["call"]:
                looped[item["call"]] = "the result of a call that repeated itself"
    calls = [item for item in items if item["part"] == "calls"]
    seen: dict[tuple[str, str], int] = {}
    for item in calls[-REPEATS:]:
        key = (item["tool"], str(item.get("text") or ""))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3 and not item["loop"]:
            nth = ORDINALS[min(seen[key], len(ORDINALS) + 2) - 3]
            item["loop"] = f"the same call a {nth} time in the last twelve"
            if item["call"]:
                looped.setdefault(item["call"], f"the result of a call made a {nth} time in the last twelve")
    for item in items:
        if item["part"] == "results" and item["call"] in looped and not item["loop"]:
            item["loop"] = looped[item["call"]]
    for item in items:
        if item["loop"]:
            item["part"] = "loop"


def _again(items: list[dict[str, Any]]) -> None:
    """The earlier results of a call made again with the same arguments, loop text apart: they could be freed."""
    newest: dict[tuple[str, str], str] = {}
    keys: dict[str, tuple[str, str]] = {}
    for item in items:
        if item["of"] == "calls" and item["call"]:
            key = (item["tool"], str(item.get("text") or ""))
            keys[item["call"]] = key
            newest[key] = item["call"]
    for item in items:
        made = keys.get(item["call"]) if item["part"] == "results" else None
        if made is not None and newest[made] != item["call"]:
            item["again"] = True


def _counted(items: list[dict[str, Any]], last_user: int, images: int, messages: int) -> dict[str, Any]:
    """The parts' characters and counts, the results by tool, what could be freed, each item's characters after it,
    and the biggest items kept."""
    chars, counts = dict.fromkeys(PARTS, 0), dict.fromkeys(PARTS, 0)
    tools: dict[str, list[int]] = {}
    again = [0, 0]
    loop_results = [0, 0]  # loop text that is a call's result: the only loop text the Guide's Drop can clear
    earlier = [0, 0]
    for item in items:
        if item["earlier"]:
            earlier[0] += item["chars"]
            earlier[1] += 1
            continue
        chars[item["part"]] += item["chars"]
        counts[item["part"]] += 1
        if item["part"] == "results":
            found = tools.setdefault(item["tool"] or "a call", [0, 0])
            found[0] += item["chars"]
            found[1] += 1
        if item["again"]:
            again[0] += item["chars"]
            again[1] += 1
        if item["part"] == "loop" and item["of"] == "results":
            loop_results[0] += item["chars"]
            loop_results[1] += 1
    left = sum(chars.values())
    for item in items:
        item.pop("text", None)  # what it wrote, read for its loops and calls made again: never kept
        if not item["earlier"]:
            left -= item["chars"]
            item["after"] = left
    shown = [item for item in items if not item["earlier"]]
    kept = {id(item) for item in sorted(shown, key=lambda item: -item["chars"])[:KEPT]}
    for part in (*PARTS, "earlier"):
        own = [item for item in items if (item["earlier"] if part == "earlier" else item["part"] == part
                                          and not item["earlier"])]  # fmt: skip
        kept |= {id(item) for item in sorted(own, key=lambda item: -item["chars"])[:PER_PART]}
    biggest = sorted((item for item in items if id(item) in kept), key=lambda item: -item["chars"])
    return {
        "chars": chars,
        "earlier": earlier[0],
        "earlier_items": earlier[1],
        "counts": counts,
        "items": biggest,
        "tools": tools,
        "again": again,
        "loop_results": loop_results,
        "from_last_user": sum(item["chars"] for item in items if item["at"] >= last_user >= 0 and not item["earlier"]),
        "images": images,
        "messages": messages,
    }


def _text(content: Any) -> str:
    """A message's text: its content, or the text of each of its parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return ""


def _images(content: Any) -> int:
    if not isinstance(content, list):
        return 0
    return sum(1 for part in content if isinstance(part, dict) and part.get("type") in IMAGES)


def _calls(raw: Any) -> list[tuple[str, str, str]]:
    """A message's calls: each one's id, name and arguments (as sent, or written as JSON)."""
    found = []
    for call in raw if isinstance(raw, list) else []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            continue
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            arguments = "" if arguments is None else json.dumps(arguments, ensure_ascii=False)
        found.append((str(call.get("id") or ""), str(function.get("name") or ""), arguments))
    return found


def _first(arguments: str) -> str:
    """What a call does, briefly: its first argument's value that is text (a command, a file), "" for arguments that
    hold none, else the arguments' start."""
    try:
        given = json.loads(arguments)
    except ValueError:
        return _words(arguments)
    if isinstance(given, dict):
        return next((_words(value) for value in given.values() if isinstance(value, str) and value.strip()), "")
    return _words(arguments)


def _words(text: str) -> str:
    said = " ".join(text.split())
    return said if len(said) <= WHAT else said[: WHAT - 1] + "…"
