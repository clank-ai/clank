"""Test support: the bridge watch's lines and pages of a session's history, made from OpenCode's events and messages by
the bridge's own functions (its `Watch` and `seen_message`, `seen_part`), for the tests of a session's flow (design
0012 §6.1). OpenCode's shapes are built by the small makers below, or read from the synthetic session of plan s14
(`tests/fixtures/opencode/1.19.0/session.json`)."""

import functools
import importlib.util
import json
from types import ModuleType
from typing import Any

from clank.components.workspaces.sandbox import image_folder
from tests.fakes.opencode import recorded

PORT = 4096
SESSION = "ses_plan"
MODEL = {"providerID": "clank", "modelID": "agent"}


@functools.cache
def bridge() -> ModuleType:
    """The bridge, loaded as a module of this process."""
    spec = importlib.util.spec_from_file_location("clank_bridge_for_flows", image_folder() / "bridge.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lines(events: list[dict[str, Any]], port: int = PORT) -> list[dict[str, Any]]:
    """The lines the watch says for these events as one burst, in its order (what it holds written at the burst's end,
    after what it says at once)."""
    module = bridge()
    watch = module.Watch()
    said: list[dict[str, Any]] = []
    watch._write = said.append  # what the watch would print
    for event in events:
        watch._heard(port, b"data: " + json.dumps(event).encode())
    watch._write_held()
    return said


def page(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """A page of history as the bridge's `page` gives it: OpenCode's messages (each `{"info", "parts"}`), oldest
    first, in the Monitor's shapes; none older."""
    module = bridge()
    ordered = sorted(messages, key=lambda each: (each["info"]["time"]["created"], each["info"]["id"]))
    return {
        "messages": [
            {"info": module.seen_message(each["info"]), "parts": [module.seen_part(part) for part in each["parts"]]}
            for each in ordered
        ],
        "next": "",
    }


def history(session: str = SESSION) -> list[dict[str, Any]]:
    """The synthetic session's messages, as OpenCode keeps them."""
    found: list[dict[str, Any]] = recorded()["messages"][session]
    return found


def burst(name: str) -> list[dict[str, Any]]:
    """One of the synthetic session's bursts of events."""
    found: list[dict[str, Any]] = recorded()["bursts"][name]
    return found


def user(id: str, created: int, text: str, *, session: str = SESSION, agent: str = "build") -> dict[str, Any]:
    """The owner's message, as OpenCode keeps it."""
    info = {"id": id, "sessionID": session, "role": "user", "time": {"created": created}, "agent": agent,
            "model": MODEL}  # fmt: skip
    return {"info": info, "parts": [{"id": f"{id}_t", "sessionID": session, "messageID": id, "type": "text",
                                     "text": text}]}  # fmt: skip


def compacting(id: str, parent: str, created: int, *, auto: bool = True, session: str = SESSION) -> dict[str, Any]:
    """OpenCode's message that asks for a compaction: the owner's in form, with a compaction part."""
    asked = user(id, created, "", session=session)
    asked["parts"] = [{"id": f"{id}_c", "sessionID": session, "messageID": id, "type": "compaction", "auto": auto}]
    return asked


def step(
    id: str,
    parent: str,
    created: int,
    parts: list[dict[str, Any]],
    *,
    completed: int | None = None,
    error: dict[str, Any] | None = None,
    session: str = SESSION,
    summary: bool = False,
    finish: str | None = None,
) -> dict[str, Any]:
    """A step (an answer), as OpenCode keeps it, with its parts (each made by `part`, `tool` or `text`); its finish
    OpenCode's for its parts unless given (`length`: cut off at the output limit)."""
    time: dict[str, Any] = {"created": created}
    if completed is not None:
        time["completed"] = completed
    info: dict[str, Any] = {
        "id": id, "sessionID": session, "role": "assistant", "time": time, "parentID": parent, "modelID": "agent",
        "providerID": "clank", "mode": "build", "agent": "build", "cost": 0,
        "tokens": {"total": 0, "input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    }  # fmt: skip
    if completed is not None and error is None:
        info["finish"] = "tool-calls" if any(each["type"] == "tool" for each in parts) else "stop"
    if finish is not None:
        info["finish"] = finish
    if error is not None:
        info["error"] = error
    if summary:
        info["summary"] = True
    owned = [{**each, "sessionID": session, "messageID": id} for each in parts]
    return {"info": info, "parts": [{"id": f"{id}_s", "sessionID": session, "messageID": id, "type": "step-start"},
                                    *owned]}  # fmt: skip


def tool(
    id: str,
    name: str,
    status: str = "completed",
    *,
    call: str = "",
    input: dict[str, Any] | None = None,
    output: str = "done",
    metadata: dict[str, Any] | None = None,
    error: str = "",
    title: str = "",
) -> dict[str, Any]:
    """A tool call's part."""
    ended = {"end": 2} if status in ("completed", "error") else {}
    state: dict[str, Any] = {"status": status, "input": input or {}, "title": title, "metadata": metadata or {},
                             "time": {"start": 1, **ended}}  # fmt: skip
    if status == "completed":
        state["output"] = output
    if status == "error":
        state["error"] = error or "it failed"
    return {"id": id, "type": "tool", "callID": call or f"call_{id}", "tool": name, "state": state}


def text(id: str, said: str, kind: str = "text") -> dict[str, Any]:
    """A text or reasoning part."""
    return {"id": id, "type": kind, "text": said}


def finish(id: str, reason: str = "tool-calls") -> dict[str, Any]:
    """A step's finish part."""
    return {"id": id, "type": "step-finish", "reason": reason, "tokens": {}, "cost": 0}


def patch(id: str, *files: str) -> dict[str, Any]:
    """A patch part: the files a step changed, as OpenCode's snapshots saw them (what its revert restores)."""
    return {"id": id, "type": "patch", "hash": f"h_{id}", "files": list(files)}


def removed(message: str, part: str = "", session: str = SESSION) -> dict[str, Any]:
    """OpenCode's event that a message (or one of its parts) was removed."""
    if part:
        properties = {"sessionID": session, "messageID": message, "partID": part}
        return {"type": "message.part.removed", "properties": properties}
    return {"type": "message.removed", "properties": {"sessionID": session, "messageID": message}}


def reverted(message: str = "", part: str = "", session: str = SESSION) -> dict[str, Any]:
    """The session updated with what a revert took back (from `message`, at `part`), or with none."""
    info: dict[str, Any] = {"id": session, "title": "Plot", "time": {"created": 1, "updated": 2}}
    if message:
        info["revert"] = {"messageID": message, **({"partID": part} if part else {})}
    return {"type": "session.updated", "properties": {"sessionID": session, "info": info}}


def updated(message: dict[str, Any]) -> list[dict[str, Any]]:
    """The events OpenCode sends for a message and its parts, as they stand."""
    session = message["info"]["sessionID"]
    events = [{"type": "message.updated", "properties": {"sessionID": session, "info": message["info"]}}]
    events += [{"type": "message.part.updated", "properties": {"sessionID": session, "part": part}}
               for part in message["parts"]]  # fmt: skip
    return events


def status(kind: str, session: str = SESSION, **more: Any) -> dict[str, Any]:
    """A session's status event: idle, busy, or retry with its attempt."""
    return {"type": "session.status", "properties": {"sessionID": session, "status": {"type": kind, **more}}}
