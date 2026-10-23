"""Clank's bridge to the OpenCode servers in this container (design 0005 §2): the Clank service runs it with `docker
exec`, one run an action, and reads the JSON it prints (`{"ok": true, ...}`, or `{"ok": false, "error": ...}`).

OpenCode serves its API while its terminal interface runs (Clank starts each with `--port`, on the container's loopback
only), or without a terminal (`serve`). Actions:

    servers                          each server on a port from FIRST to LAST: its root sessions, their status, the
                                     permissions and questions waiting, and whether it runs a terminal interface
                                     (`terminal`: an `opencode --port` process, not `opencode serve`); its subagents'
                                     sessions beside them (`children`, each with its `parent`)
    messages PORT SESSION [LIMIT]    a session's last messages, briefly (text, tools with title and state, files)
    page PORT SESSION [LIMIT] [BEFORE]
                                     a page of a session's messages, oldest first, each part in the shape the watch
                                     says it (design 0012 §6.1), and the cursor of the page before it (`next`, "" at
                                     the first message): OpenCode's own `limit`, `before` and `X-Next-Cursor`
    prompt PORT SESSION              send the message on standard input ({"text": ..., "files": [{"url", "mime",
                                     "filename"}]}, a file:// URL in the folder for an image) without waiting for the
                                     answer, with the agent and the model of the session's last message of the owner
                                     (OpenCode gives a message that names none to `build`), or those given
                                     ({"agent": ..., "model": {"providerID", "modelID"}}; design 0012 §9.3)
    new PORT                         start a session ({"title": ...} on standard input); its id
    abort PORT SESSION               stop what the session does
    reject PORT SESSION              reject what waits in the session and its subagents: their asks (one at a time:
                                     OpenCode rejects a session's other asks with the first) and their questions
                                     (design 0012 §9.2)
    clear PORT SESSION MESSAGE PART  clear a finished tool call's result as OpenCode's own compaction does: the whole
                                     part written back with `state.time.compacted` set; refused for the step in
                                     progress (design 0012 §9.7)
    revert PORT SESSION MESSAGE [PART]
                                     take back the session from that message (that part) on: its files restored, its
                                     later messages dropped at its next message (design 0012 §9.5)
    unrevert PORT SESSION            bring back what the last revert took back
    summarize PORT SESSION           compact the session ({"providerID", "modelID"} on standard input, else the
                                     session's model) without waiting: OpenCode answers only once the run ends, so
                                     `held`, a process of the bridge's own in a session of its own, keeps the request
                                     open until then (design 0012 §9.6); `answered` when it answered at once
    permission PORT ID REPLY         once, always or reject; a reject may carry a note for the model ({"message": ...}
                                     on standard input)
    question PORT ID                 the answers on standard input ({"answers": [[...], ...]})
    free-port                        the first port no server listens on
    serve                            start OpenCode without a terminal ({"env": {...}} on standard input); its port
    mcp                              each server's MCP servers, each with its status (connected, disabled, failed and
                                     why, needs_auth)
    mcp-start PORT NAME              connect an MCP server the agent knows; one it does not is added, its OpenCode
                                     entry on standard input ({"config": {...}})
    mcp-stop PORT NAME               disconnect an MCP server: its tools leave the agent until it is started again
    agents PORT                      the agents Tab cycles through in the terminal interface, in its order
    cycle PORT COUNT                 do what Tab does in the terminal interface, COUNT times (design 0009 §7)
    show PORT SESSION                show a session that runs already in the terminal interface on PORT, a window
                                     still starting waited for ({"wait": seconds} on standard input) and the session
                                     shown again a few seconds later (design 0013 §15); whether it was shown
    implement PORT                   a new session whose first message ({"text": ..., "title": ...} on standard input)
                                     is sent by `build`, or the agent given ("agent"), then shown in the terminal
                                     interface, which then takes that agent (design 0009 §8); with "wait", a window
                                     still starting is waited for that many seconds, and the session shown again a
                                     few seconds later (a planning session, design 0013 §15); its id
    watch                            follow every server's events until standard input closes, a JSON line for each
                                     thing the service needs (design 0007 §4): `asked` (a permission, those waiting
                                     when a server is first followed too; a change with its tool call's input),
                                     `replied`, `edited` (a file written), `agent` (the agent a message was sent to,
                                     and whether its server runs a terminal interface; design 0009 §7), `gone` (a
                                     server stopped), `synced` (the servers running at its start were read) and
                                     `alive` now and then; and the Monitor's (design 0012 §6.1), each with its port:
                                     `status` (a session's: idle, busy, or retry; those it runs when a server is first
                                     followed too), `session` (created, updated or deleted; a subagent's with its
                                     parent), `message`, `part`, `removed`, `todo`, `compacted`, `error`, `question`
                                     and `answered` (a question asked, replied or rejected), `disposed` (OpenCode's
                                     instance ended: its stream is opened again), and `delta` (the text as it is
                                     written) for the sessions shown only: a line {"shown": [SESSION, ...]} on standard
                                     input names them, answered `shown`. What a burst changes many times is said once,
                                     with its last state

It uses Python's standard library only, so it runs in any workspace's container, whatever the folder installs.
"""

import contextlib
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

FIRST, LAST = (int(part) for part in os.environ.get("CLANK_BRIDGE_PORTS", "4096-4127").split("-"))
TIMEOUT = float(os.environ.get("CLANK_BRIDGE_TIMEOUT", "10"))  # seconds a request waits for its answer
TEXT = 6000  # characters of a part's text kept
OUTPUT = 1500  # of a tool's output
INPUT = 400  # of a tool's input
WHOLE = 200_000  # characters of a call's input and of its output given whole (`part`), at most
TODOS = 200  # items of a todo list kept
DIFF = 20000  # of a permission's diff
SERVE_SECONDS = 30.0
CONNECT_SECONDS = 90.0  # a server's start, which OpenCode waits for
SCAN_SECONDS = 2.0  # how often `watch` looks for servers that started
ALIVE_SECONDS = 15.0  # how often `watch` says it still runs
CHANGE_INPUT = 2_000_000  # characters of a change's tool call `watch` passes on (its old and new text, or content)
WATCHER = os.path.join(tempfile.gettempdir(), "clank-watch.pid")
SHOWN_SECONDS = 10.0  # how long `implement` waits for its first message before showing the session
SHOW_AGAIN = tuple(float(part) for part in os.environ.get("CLANK_BRIDGE_SHOW_AGAIN", "2,3").split(",") if part)
# the pauses before `implement` shows again a session on a window it waited for: one just started may not hear the first
WINDOW_STEP = 0.25  # seconds between looks at a window's port while `implement` waits for it
BUILD = "build"
PAGE = 50  # messages a page of `page` holds unless asked for another number
PAGES = 500  # the most it holds
SAID_PAGE = 20  # messages read at a time, from the newest, to find the owner's last one
SAID_PAGES = 100  # pages read at most to find it
ROUNDS = 50  # asks `reject` answers at most, one at a time
FAMILY = 200  # sessions `reject` reaches at most: a session, its subagents, theirs
BURST_QUIET, BURST_MOST = (float(part) for part in os.environ.get("CLANK_BRIDGE_BURST", "0.1,0.25").split(","))
# `watch` writes what it holds once its streams were quiet for BURST_QUIET seconds, or BURST_MOST after the first line
# held: at most four times a second while the model writes, as the console redraws (design 0012 §2)
WAIT_SECONDS = 1.0  # how long `held` waits for OpenCode's answer before saying it holds the request
HELD_SECONDS = 12 * 3600.0  # how long it holds one at most


def fetch(port: int, method: str, path: str, body: Any = None, timeout: float | None = TIMEOUT) -> tuple[Any, Any]:
    """One request to the server on `port`: its answer read as JSON (None when it has none), and its headers."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        raw = answer.read()
        said = answer.headers
    return (json.loads(raw) if raw.strip() else None), said


def call(port: int, method: str, path: str, body: Any = None, timeout: float | None = TIMEOUT) -> Any:
    """One request to the server on `port`; its answer read as JSON (None when it has none)."""
    return fetch(port, method, path, body, timeout)[0]


def listening(port: int) -> bool:
    """Whether something listens on the port, on the container's loopback."""
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def cut(text: Any, limit: int) -> str:
    """A text (or a value, as JSON) cut at `limit` characters, saying how long it was."""
    value = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return value if len(value) <= limit else value[:limit] + f" … [{len(value):,} characters]"


def terminal_ports(proc: str = "/proc") -> set[int]:
    """The ports of the OpenCode processes that run a terminal interface (`opencode ... --port N`, not `opencode
    serve`), from the processes' command lines; none where there is no /proc."""
    found: set[int] = set()
    try:
        entries = os.listdir(proc)
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc, entry, "cmdline"), "rb") as running:
                argv = [part.decode(errors="replace") for part in running.read().split(b"\0") if part]
        except OSError:
            continue
        named = any(os.path.basename(part) == "opencode" for part in argv[:2])  # itself, or node running it
        if not named or "serve" in argv or "--port" not in argv:
            continue
        try:
            found.add(int(argv[argv.index("--port") + 1]))
        except (IndexError, ValueError):
            continue
    return found


def agents(port: int) -> list[str]:
    """The agents Tab cycles through in a terminal interface, in its order: the primary ones that are shown."""
    return [
        str(agent["name"])
        for agent in call(port, "GET", "/agent") or []
        if agent.get("mode") in ("primary", "all") and not agent.get("hidden")
    ]


def implement(port: int, text: str, title: str, agent: str = BUILD, wait: float = 0.0) -> dict[str, Any]:
    """A new session whose first message `agent` is sent (`build` unless named), shown in the terminal interface once
    that message is there (a session shown takes its last message's agent, measured on OpenCode 1.19). With `wait`, a
    window still starting is waited for that many seconds, and the session is shown again after `SHOW_AGAIN`'s pauses,
    since a terminal interface just started may not hear the first (design 0013 §15). Each request then waits for its
    answer as long as the window was waited for: OpenCode readies itself on a new window's first requests, which took
    longer than `TIMEOUT` on the owner's machine."""
    if not text.strip():
        raise ValueError("an empty message is not sent")
    waited = not listening(port)
    deadline = time.monotonic() + wait
    while not listening(port):
        if time.monotonic() >= deadline:
            raise ValueError(f"no OpenCode window answered on port {port} within {wait:g} seconds")
        time.sleep(WINDOW_STEP)
    patient = max(TIMEOUT, wait)
    session = call(port, "POST", "/session", {"title": title} if title else {}, timeout=patient)["id"]
    asked = {"agent": agent, "parts": [{"type": "text", "text": text}]}
    call(port, "POST", f"/session/{session}/prompt_async", asked, timeout=patient)
    deadline = time.monotonic() + SHOWN_SECONDS
    while time.monotonic() < deadline:
        try:
            sent = call(port, "GET", f"/session/{session}/message", timeout=patient) or []
        except OSError:  # no answer yet: the message is looked for again until the deadline
            sent = []
        if any((message.get("info") or {}).get("role") == "user" for message in sent):
            break
        time.sleep(0.2)
    shown = show(port, session)
    for pause in SHOW_AGAIN if waited else ():
        time.sleep(pause)
        shown = show(port, session) or shown
    return {"session": session, "shown": shown}


def show_waiting(port: int, session: str, wait: float = 0.0) -> dict[str, Any]:
    """Show a session that runs already in the terminal interface on `port` (`clank flow attach` to a planning already
    talking, design 0013 §15): a window still starting waited for up to `wait` seconds, and the session shown again
    after `SHOW_AGAIN`'s pauses when it was; no session is started."""
    waited = not listening(port)
    deadline = time.monotonic() + wait
    while not listening(port):
        if time.monotonic() >= deadline:
            raise ValueError(f"no OpenCode window answered on port {port} within {wait:g} seconds")
        time.sleep(WINDOW_STEP)
    shown = show(port, session)
    for pause in SHOW_AGAIN if waited else ():
        time.sleep(pause)
        shown = show(port, session) or shown
    return {"session": session, "shown": shown}


def show(port: int, session: str) -> bool:
    """Show a session in the terminal interface on `port`; False when it would not (the session stands all the same:
    the owner picks it from the window's list of sessions)."""
    try:
        return bool(call(port, "POST", "/tui/select-session", {"sessionID": session}))
    except (OSError, ValueError):  # an HTTP error, a server that went, an answer that is no JSON
        return False


def servers() -> dict[str, Any]:
    """Each OpenCode server on the ports: its root sessions with their status, the permissions and questions waiting,
    and whether it runs a terminal interface; its subagents' sessions beside the root ones (design 0012 §3)."""
    found = []
    terminals = terminal_ports()
    for port in range(FIRST, LAST + 1):
        if not listening(port):
            continue
        try:
            sessions = call(port, "GET", "/session") or []
            status = call(port, "GET", "/session/status") or {}
            permissions = call(port, "GET", "/permission") or []
            questions = call(port, "GET", "/question") or []
        except (OSError, ValueError, urllib.error.URLError):
            continue  # not an OpenCode server, or not ready yet
        listed = [
            {
                "id": session["id"], "title": session.get("title") or "", "parent": session.get("parentID"),
                "created": (session.get("time") or {}).get("created"),
                "updated": (session.get("time") or {}).get("updated"),
                "status": (status.get(session["id"]) or {}).get("type", "idle"),
            }
            for session in sessions
        ]  # fmt: skip
        found.append({
            "port": port,
            "terminal": port in terminals,
            "sessions": [session for session in listed if not session["parent"]],
            "children": [session for session in listed if session["parent"]],  # subagents' (design 0012 §3)
            "permissions": [
                {
                    "id": item["id"], "session": item.get("sessionID"), "permission": item.get("permission"),
                    "patterns": item.get("patterns") or [],
                    "metadata": {key: cut(value, DIFF) for key, value in (item.get("metadata") or {}).items()},
                }
                for item in permissions
            ],
            "questions": [
                {"id": item["id"], "session": item.get("sessionID"), "questions": item.get("questions") or []}
                for item in questions
            ],
        })  # fmt: skip
    return {"servers": found}


def part_brief(part: dict[str, Any]) -> dict[str, Any] | None:
    """A part of a message, briefly; None for a part a reader does not need (steps, snapshots)."""
    kind = part.get("type")
    if kind == "text" and not part.get("synthetic"):
        return {"type": "text", "text": cut(part.get("text") or "", TEXT)}
    if kind == "tool":
        state = part.get("state") or {}
        brief = {"type": "tool", "tool": part.get("tool"), "status": state.get("status"), "title": state.get("title")}
        if state.get("input") is not None:
            brief["input"] = cut(state["input"], INPUT)
        if state.get("status") == "completed":
            brief["output"] = cut(state.get("output") or "", OUTPUT)
        if state.get("status") == "error":
            brief["error"] = cut(state.get("error") or "", OUTPUT)
        return brief
    if kind == "file":
        url = part.get("url") or ""
        return {"type": "file", "mime": part.get("mime"), "filename": part.get("filename"),
                "url": url if not url.startswith("data:") else ""}  # fmt: skip
    if kind == "reasoning":
        return {"type": "reasoning", "length": len(part.get("text") or "")}
    if kind in ("patch", "compaction"):
        return {"type": kind, "files": part.get("files") or []}
    return None


def said_error(error: Any) -> str:
    """What an error OpenCode keeps says (its message, else its name), cut; "" for none."""
    if not error:
        return ""
    if isinstance(error, dict):
        return cut((error.get("data") or {}).get("message") or error.get("name") or error, OUTPUT)
    return cut(error, OUTPUT)


def messages(port: int, session: str, limit: int) -> dict[str, Any]:
    """A session's last `limit` messages, briefly, and how many it has."""
    found = call(port, "GET", f"/session/{session}/message") or []
    shown = []
    for message in found[-limit:]:
        info = message.get("info") or {}
        parts = [brief for part in message.get("parts") or [] if (brief := part_brief(part)) is not None]
        shown.append({
            "id": info.get("id"), "role": info.get("role"), "created": (info.get("time") or {}).get("created"),
            "completed": (info.get("time") or {}).get("completed"), "parts": parts,
            "error": said_error(info.get("error")),
        })  # fmt: skip
    return {"messages": shown, "count": len(found)}


def seen_message(info: dict[str, Any]) -> dict[str, Any]:
    """A message as the Monitor reads it (design 0012 §6.1), from the event stream or the history alike: who sent it,
    with which agent and model; for a step (an answer), what it answers, its tokens, its cost, how it finished, and its
    error with its name (`MessageAbortedError` for a step the owner stopped, which tells it apart from one that
    failed)."""
    time = info.get("time") or {}
    seen: dict[str, Any] = {
        "id": info.get("id"), "session": info.get("sessionID"), "role": info.get("role"), "agent": info.get("agent"),
        "created": time.get("created"), "completed": time.get("completed"),
    }  # fmt: skip
    if info.get("role") == "user":
        seen["model"] = dict(info.get("model") or {})  # its providerID, its modelID, and its variant when it has one
        return seen
    seen.update({
        "parent": info.get("parentID"), "model": {"providerID": info.get("providerID"), "modelID": info.get("modelID")},
        "tokens": info.get("tokens") or {}, "cost": info.get("cost"), "finish": info.get("finish"),
        "summary": bool(info.get("summary")), "error": said_error(info.get("error")),
        "error_name": str((info.get("error") or {}).get("name") or "") if isinstance(info.get("error"), dict) else "",
    })  # fmt: skip
    return seen


def seen_part(part: dict[str, Any]) -> dict[str, Any]:
    """A part of a message as the Monitor reads it (design 0012 §6.1), from the event stream or the history alike: its
    ids and type and, by type, its text (cut, with its length); a tool call's id, state, title, input and output (cut,
    with the output's length), times (`compacted` once its result was cleared), the subagent it started and its exit
    status, and a `todowrite` call's todo list whole (`todos`); a step's finish with its tokens; a patch's files."""
    kind = part.get("type")
    seen: dict[str, Any] = {"id": part.get("id"), "message": part.get("messageID"), "type": kind}
    if kind in ("text", "reasoning"):
        text = str(part.get("text") or "")
        seen.update({"text": cut(text, TEXT), "length": len(text)})
        if part.get("synthetic"):
            seen["synthetic"] = True
    elif kind == "tool":
        state = part.get("state") or {}
        metadata = state.get("metadata") or part.get("metadata") or {}
        seen.update({
            "tool": part.get("tool"), "call": part.get("callID"), "status": state.get("status"),
            "title": state.get("title") or "", "input": cut(state.get("input") or {}, INPUT),
            "time": state.get("time") or {},
        })  # fmt: skip
        if state.get("status") == "completed":
            output = str(state.get("output") or "")
            seen.update({"output": cut(output, OUTPUT), "length": len(output)})
        if state.get("status") == "error":
            seen["error"] = cut(state.get("error") or "", OUTPUT)
        if metadata.get("sessionId"):
            seen["subagent"] = metadata["sessionId"]
        listed = (state.get("input") or {}).get("todos") if isinstance(state.get("input"), dict) else None
        if part.get("tool") == "todowrite" and isinstance(listed, list):  # whole, though its input and output are cut
            seen["todos"] = [
                {key: cut(each[key], TEXT) if key == "content" else each[key]
                 for key in ("id", "content", "status", "priority") if key in each}
                for each in listed[:TODOS] if isinstance(each, dict)
            ]  # fmt: skip
        if isinstance(metadata.get("exit"), int):
            seen["exit"] = metadata["exit"]
    elif kind == "step-finish":
        seen.update({"tokens": part.get("tokens") or {}, "cost": part.get("cost"), "reason": part.get("reason")})
    elif kind == "patch":
        seen["files"] = part.get("files") or []
    elif kind == "compaction":
        seen["auto"] = bool(part.get("auto"))
    elif kind == "file":
        url = str(part.get("url") or "")
        seen.update({"mime": part.get("mime"), "filename": part.get("filename"),
                     "url": url if not url.startswith("data:") else ""})  # fmt: skip
    elif kind in ("subtask", "agent"):
        seen.update({"agent": part.get("agent") or part.get("name"), "description": part.get("description") or ""})
    elif kind == "retry":
        seen.update({"attempt": part.get("attempt"), "error": said_error(part.get("error"))})
    return seen


def last_said(port: int, session: str) -> dict[str, Any]:
    """The agent and the model (with its variant) of the session's last message of the owner, found a page at a time
    from the newest; {} for a session without one."""
    before = ""
    for _ in range(SAID_PAGES):
        query = urllib.parse.urlencode({"limit": str(SAID_PAGE), **({"before": before} if before else {})})
        found, said = fetch(port, "GET", f"/session/{urllib.parse.quote(session)}/message?{query}")
        users = [
            message["info"]
            for message in found or []
            if isinstance(message, dict) and (message.get("info") or {}).get("role") == "user"
        ]
        if users:
            info = max(users, key=lambda each: ((each.get("time") or {}).get("created") or 0, str(each.get("id"))))
            model = info.get("model") or {}
            chosen: dict[str, Any] = {"agent": str(info["agent"])} if info.get("agent") else {}
            if model.get("providerID") and model.get("modelID"):
                chosen["model"] = {"providerID": str(model["providerID"]), "modelID": str(model["modelID"])}
                if model.get("variant"):
                    chosen["variant"] = str(model["variant"])
            return chosen
        before = str(said.get("X-Next-Cursor") or "")
        if not before:
            break
    return {}


def prompt(port: int, session: str, asked: dict[str, Any]) -> dict[str, Any]:
    """Send a message without waiting for the answer: its text and files, with the agent and the model given, else
    those of the session's last message of the owner."""
    text = str(asked.get("text") or "").strip()
    if not text:
        raise ValueError("an empty message is not sent")
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for file in asked.get("files") or []:
        part = {"type": "file", "mime": str(file["mime"]), "url": str(file["url"])}
        if file.get("filename"):
            part["filename"] = str(file["filename"])
        parts.append(part)
    chosen = last_said(port, session)
    if asked.get("agent"):
        chosen["agent"] = str(asked["agent"])
    model = asked.get("model")
    if isinstance(model, dict) and model.get("providerID") and model.get("modelID"):
        chosen["model"] = {"providerID": str(model["providerID"]), "modelID": str(model["modelID"])}
        chosen.pop("variant", None)  # the session's variant is its model's
    call(port, "POST", f"/session/{urllib.parse.quote(session)}/prompt_async", {**chosen, "parts": parts})
    return {"sent": True, "agent": chosen.get("agent", ""), "model": chosen.get("model") or {}}


def family(port: int, session: str) -> list[str]:
    """The session and its subagents' sessions, theirs too, as OpenCode lists each session's children."""
    found: list[str] = []
    waiting = [session]
    while waiting and len(found) < FAMILY:
        each = waiting.pop(0)
        if each in found:
            continue
        found.append(each)
        children = call(port, "GET", f"/session/{urllib.parse.quote(each)}/children") or []
        waiting += [str(child["id"]) for child in children if isinstance(child, dict) and child.get("id")]
    return found


def reject(port: int, session: str) -> dict[str, Any]:
    """Reject what waits in a session and its subagents (Stop, design 0012 §9.2), so no later "once" can approve it:
    their asks, one at a time until none is left (OpenCode rejects a session's other asks with the first), then their
    questions."""
    sessions = set(family(port, session))
    rejected: list[str] = []
    tried: set[str] = set()
    for _ in range(ROUNDS):
        left = [
            str(ask["id"])
            for ask in call(port, "GET", "/permission") or []
            if ask.get("sessionID") in sessions and ask.get("id") and str(ask["id"]) not in tried
        ]
        if not left:
            break
        tried.add(left[0])
        try:
            call(port, "POST", f"/permission/{urllib.parse.quote(left[0])}/reply", {"reply": "reject"})
            rejected.append(left[0])
        except urllib.error.HTTPError as error:
            if error.code != 404:  # gone meanwhile: rejected with another, or answered
                raise
    questions = []
    for asked in call(port, "GET", "/question") or []:
        if asked.get("sessionID") in sessions and asked.get("id"):
            try:
                call(port, "POST", f"/question/{urllib.parse.quote(str(asked['id']))}/reject")
                questions.append(str(asked["id"]))
            except urllib.error.HTTPError as error:
                if error.code != 404:  # answered meanwhile
                    raise
    return {"rejected": rejected, "questions": questions}


def clear(port: int, session: str, message: str, part: str) -> dict[str, Any]:
    """Clear a finished tool call's result as OpenCode's own compaction does (design 0012 §9.7): the whole part written
    back with `state.time.compacted` set, so from the next step the model reads that the result was cleared and the
    call stays; once is enough. Refused for the step in progress, and for anything but a finished tool call."""
    path = f"/session/{urllib.parse.quote(session)}/message/{urllib.parse.quote(message)}"
    found = call(port, "GET", path) or {}
    info = found.get("info") or {}
    if info.get("role") != "assistant":
        raise ValueError(f"{message} is not a step of the model: only a tool call's result is cleared")
    if not (info.get("time") or {}).get("completed"):
        raise ValueError(f"{message} is the step in progress: it is not changed while it runs")
    kept = next((each for each in found.get("parts") or [] if each.get("id") == part), None)
    if kept is None:
        raise ValueError(f"{message} has no part {part}")
    state = kept.get("state") or {}
    if kept.get("type") != "tool" or state.get("status") != "completed":
        raise ValueError(f"{part} is not a finished tool call: only a finished call's result is cleared")
    length = len(str(state.get("output") or ""))
    times = dict(state.get("time") or {})
    if not times.get("compacted"):
        times["compacted"] = int(time.time() * 1000)
        call(port, "PATCH", f"{path}/part/{urllib.parse.quote(part)}", {**kept, "state": {**state, "time": times}})
    return {"cleared": True, "compacted": times["compacted"], "length": length}


def revert(port: int, session: str, message: str, part: str) -> dict[str, Any]:
    """Take back the session from a message (a part of it) on (design 0012 §9.5); what OpenCode keeps of the revert."""
    body = {"messageID": message, **({"partID": part} if part else {})}
    info = call(port, "POST", f"/session/{urllib.parse.quote(session)}/revert", body) or {}
    return {"reverted": True, "revert": info.get("revert") or {}}


def summarize(port: int, session: str, given: dict[str, Any]) -> dict[str, Any]:
    """Ask OpenCode to compact the session at its next step (design 0012 §9.6), with the model given, else the
    session's own, without waiting for it."""
    model = given if given.get("providerID") and given.get("modelID") else last_said(port, session).get("model")
    if not model:
        raise ValueError(f"{session} has no message of the owner to take its model from: name the model")
    body = {"providerID": str(model["providerID"]), "modelID": str(model["modelID"]), "auto": True}
    return hold(port, f"/session/{urllib.parse.quote(session)}/summarize", body)


def hold(port: int, path: str, body: Any) -> dict[str, Any]:
    """Send a request OpenCode answers only once the session's run ends, and return as soon as OpenCode has it:
    `held`, a process of the bridge's own in a session of its own (as `serve` starts OpenCode, so the exec's end leaves
    it), keeps the connection open until the answer, so OpenCode never sees its client leave."""
    holder = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "held", str(port), path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no window where the tests run it, on Windows
    )  # fmt: skip
    if holder.stdin is None or holder.stdout is None:
        raise RuntimeError("the request could not be handed over")
    holder.stdin.write(json.dumps(body).encode())
    holder.stdin.close()
    said: list[bytes] = []
    reader = threading.Thread(target=lambda out=holder.stdout: said.append(out.readline()), daemon=True)
    reader.start()
    reader.join(TIMEOUT)
    try:
        answer = json.loads(said[0]) if said and said[0].strip() else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):  # ended, so it cannot send what the service is told failed
        holder.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            holder.wait(TIMEOUT)
        reader.join(TIMEOUT)
        holder.stdout.close()
        raise RuntimeError(f"the request to OpenCode was not confirmed within {TIMEOUT:g} seconds")
    if not answer.get("ok"):
        raise RuntimeError(str(answer.get("error") or "OpenCode refused it"))
    return {"asked": True, "answered": bool(answer.get("answered"))}


def held(port: int, path: str, body: Any) -> None:
    """`held`: send the request; say, in one line, whether OpenCode answered within `WAIT_SECONDS` (and its error) or
    holds it; then keep the connection until OpenCode answers."""
    answer: dict[str, Any] = {}

    def send() -> None:
        try:
            call(port, "POST", path, body, timeout=HELD_SECONDS)
            answer["ok"] = True
        except urllib.error.HTTPError as error:
            answer["error"] = f"OpenCode answered {error.code}: {cut(error.read().decode(errors='replace'), 500)}"
        except (OSError, ValueError, urllib.error.URLError) as error:
            answer["error"] = str(error) or type(error).__name__

    sending = threading.Thread(target=send, daemon=True)
    sending.start()
    sending.join(WAIT_SECONDS)
    said = {"ok": False, "error": answer["error"]} if "error" in answer else {"ok": True, "answered": "ok" in answer}
    sys.stdout.write(json.dumps(said, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    sys.stdout.close()
    sending.join()


def page(port: int, session: str, limit: int, before: str) -> dict[str, Any]:
    """A page of a session's messages, oldest first, each in the Monitor's shape, and the cursor of the page before
    it ("" at the session's first message): OpenCode's own paging (`limit`, then `before` the cursor it gave)."""
    if not 1 <= limit <= PAGES:
        raise ValueError(f"a page holds 1 to {PAGES} messages, not {limit}")
    query = urllib.parse.urlencode({"limit": str(limit), **({"before": before} if before else {})})
    found, said = fetch(port, "GET", f"/session/{urllib.parse.quote(session)}/message?{query}")
    listed = [message for message in found or [] if isinstance(message, dict)]
    listed.sort(key=lambda message: (((message.get("info") or {}).get("time") or {}).get("created") or 0,
                                     str((message.get("info") or {}).get("id") or "")))  # fmt: skip
    return {
        "messages": [
            {
                "info": seen_message(each.get("info") or {}),
                "parts": [seen_part(part) for part in each.get("parts") or []],
            }
            for each in listed
        ],
        "next": str(said.get("X-Next-Cursor") or ""),
    }


def part(port: int, session: str, message: str, part_id: str, limit: int = WHOLE) -> dict[str, Any]:
    """One tool call whole (design 0012 §7: the watch cuts a call's input and output): its ids, state and title, its
    input as JSON and its output (a running call's so far, as OpenCode keeps it), each with its length, and cut past
    `limit` characters only, an input to its start and an output to its end, where a command says how it ended."""
    if not 1 <= limit <= WHOLE:
        raise ValueError(f"a call is given whole up to 1 to {WHOLE:,} characters, not {limit:,}")
    found = call(port, "GET", f"/session/{urllib.parse.quote(session)}/message/{urllib.parse.quote(message)}") or {}
    parts = [each for each in found.get("parts") or [] if isinstance(each, dict) and each.get("id") == part_id]
    if not parts:
        raise ValueError(f"{message} has no part {part_id}")
    state = parts[0].get("state") or {}
    given = state.get("input")
    written = given if isinstance(given, str) else json.dumps(given if given is not None else {}, ensure_ascii=False)
    output = state.get("output")
    if output is None:
        output = (state.get("metadata") or {}).get("output") or ""
    output = str(output)
    return {"part": {
        "id": part_id, "message": message, "tool": parts[0].get("tool"), "call": parts[0].get("callID"),
        "status": state.get("status"), "title": state.get("title") or "", "input": written[:limit],
        "output": output[-limit:] if len(output) > limit else output, "error": str(state.get("error") or "")[:limit],
        "length": {"input": len(written), "output": len(output)},
        "cut": {"input": len(written) > limit, "output": len(output) > limit},
    }}  # fmt: skip


def mcp() -> dict[str, Any]:
    """Each OpenCode server's MCP servers on the ports, each with its status, and why when it failed."""
    found = []
    for port in range(FIRST, LAST + 1):
        if not listening(port):
            continue
        try:
            status = call(port, "GET", "/mcp") or {}
        except (OSError, ValueError, urllib.error.URLError):
            continue  # not an OpenCode server, or not ready yet
        found.append({"port": port, "mcp": {
            str(name): {"status": str(each.get("status", "")), "error": str(each.get("error") or "")}
            for name, each in status.items()
        }})  # fmt: skip
    return {"servers": found}


def mcp_start(port: int, name: str, config: Any) -> dict[str, Any]:
    """Connect an MCP server the server knows, or add it with its entry; its status after."""
    known = call(port, "GET", "/mcp") or {}
    if name in known:
        call(port, "POST", f"/mcp/{urllib.parse.quote(name)}/connect", timeout=CONNECT_SECONDS)
    elif isinstance(config, dict) and config:
        call(port, "POST", "/mcp", {"name": name, "config": config}, timeout=CONNECT_SECONDS)
    else:
        raise ValueError(f"{name} is not one of this agent's MCP servers, and no entry came to add it")
    return {"status": (call(port, "GET", "/mcp") or {}).get(name, {})}


def free_port() -> int:
    """The first port of the range no server listens on."""
    for port in range(FIRST, LAST + 1):
        if not listening(port):
            return port
    raise RuntimeError(f"every port from {FIRST} to {LAST} is taken: close an OpenCode first")


def serve(env: dict[str, str]) -> dict[str, Any]:
    """Start OpenCode without a terminal on the first free port, in the folder, with `env`; its port once it answers."""
    port = free_port()
    logs = os.path.expanduser("~/.local/state/clank")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, f"serve-{port}.log"), "ab") as log:
        subprocess.Popen(
            ["opencode", "serve", "--port", str(port), "--hostname", "127.0.0.1"],
            cwd="/workspace", env={**os.environ, **env}, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )  # fmt: skip
    deadline = time.monotonic() + SERVE_SECONDS
    while time.monotonic() < deadline:
        if listening(port):
            return {"port": port}
        time.sleep(0.25)
    raise RuntimeError(f"OpenCode did not answer on port {port} within {SERVE_SECONDS:g} seconds")


class Watch:
    """`watch`: every OpenCode server's events, as the service needs them, one JSON line each, until standard input
    closes (the service stopped, or ended the exec).

    The review's lines (`asked`, `replied`, `edited`, `agent`, `question`, `answered`, `gone`, `disposed`, `synced`)
    are said at once. The Monitor's (design 0012 §6.1) are held in a table keyed by what each says (a part, a message,
    a session's status), a new value replacing the old one and moving to the table's end, and the table is written
    once the stream has been quiet for `BURST_QUIET` seconds, or `BURST_MOST` after its first line, and before any line
    said at once: a part updated a hundred times in a burst is said once, with its last state, and a status that went
    busy, then idle, after the step's parts. The text as it is written (`delta`) is joined per part and field, and
    only for the sessions the service says are shown (a line `{"shown": [...]}` on the input)."""

    def __init__(self) -> None:
        self.lock = threading.RLock()  # what is written, and what is held
        self.stopped = threading.Event()
        self.followed: dict[int, threading.Thread] = {}
        self.terminals: dict[int, bool] = {}  # each port followed: whether it runs a terminal interface
        self.messages: set[str] = set()  # the messages whose agent was said
        self.held: dict[tuple[Any, ...], dict[str, Any]] = {}  # the Monitor's lines of this burst, by what they say
        self.first = self.last = 0.0  # when the burst's first and last lines were held
        self.holding = threading.Event()
        self.shown: set[str] = set()  # the sessions whose text is said as it is written
        self.running: dict[int, set[str]] = {}  # each port's sessions last said busy or retrying

    def run(self) -> None:
        """Follow the servers running now and say `synced` once each was read; then look for new ones every
        `SCAN_SECONDS`, saying `alive` every `ALIVE_SECONDS`, until the input closes."""
        replace_older()
        threading.Thread(target=self._until_input_closes, daemon=True).start()
        threading.Thread(target=self._writer, daemon=True).start()
        for ready in [self._follow(port) for port in self._new_ports()]:
            ready.wait(TIMEOUT)
        self.say({"type": "synced", "ports": sorted(self.followed)})
        said = time.monotonic()
        while not self.stopped.wait(SCAN_SECONDS):
            for port in self._new_ports():
                self._follow(port)
            if time.monotonic() - said >= ALIVE_SECONDS:
                self.say({"type": "alive"})
                said = time.monotonic()

    def say(self, line: dict[str, Any]) -> None:
        """One line for the service, after what is held; when nobody reads them any more, the watch ends."""
        with self.lock:
            self._write_held()
            self._write(line)

    def hold(self, key: tuple[Any, ...], line: dict[str, Any]) -> None:
        """A line of the Monitor's, said with the burst: the last of its key, at the place of its last change."""
        with self.lock:
            self._held_now()
            self.held.pop(key, None)
            self.held[key] = line

    def join(self, key: tuple[Any, ...], line: dict[str, Any], text: str) -> None:
        """Text as it is written, joined to what the burst holds of it."""
        with self.lock:
            self._held_now()
            kept = self.held.get(key)
            if kept is None:
                self.held[key] = {**line, "text": text}
            else:
                kept["text"] += text

    def _held_now(self) -> None:
        now = time.monotonic()
        if not self.held:
            self.first = now
        self.last = now
        self.holding.set()

    def _write(self, line: dict[str, Any]) -> None:
        try:
            sys.stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            self.stopped.set()

    def _write_held(self) -> None:
        with self.lock:
            held, self.held = self.held, {}
            for line in held.values():
                self._write(line)

    def _writer(self) -> None:
        """Write what is held once the burst is over: quiet for `BURST_QUIET`, or `BURST_MOST` after it began."""
        while not self.stopped.is_set():
            if not self.holding.wait(1.0):
                continue
            with self.lock:
                due = min(self.last + BURST_QUIET, self.first + BURST_MOST)
                if not self.held or time.monotonic() >= due:
                    self._write_held()
                    self.holding.clear()
                    continue
            self.stopped.wait(max(due - time.monotonic(), 0.005))
        self._write_held()

    def _until_input_closes(self) -> None:
        """Read the service's lines (the sessions shown) until the input closes, then end the watch."""
        while True:
            raw = sys.stdin.readline()
            if not raw:
                break
            try:
                told = json.loads(raw)
            except ValueError:
                continue
            if isinstance(told, dict) and isinstance(told.get("shown"), list):
                with self.lock:
                    self.shown = {str(session) for session in told["shown"]}
                    self.say({"type": "shown", "sessions": sorted(self.shown)})
        self.stopped.set()

    def _new_ports(self) -> list[int]:
        return [
            port
            for port in range(FIRST, LAST + 1)
            if not (port in self.followed and self.followed[port].is_alive()) and listening(port)
        ]

    def _follow(self, port: int) -> threading.Event:
        ready = threading.Event()
        self.terminals[port] = port in terminal_ports()
        self.followed[port] = threading.Thread(target=self._server, args=(port, ready), daemon=True)
        self.followed[port].start()
        return ready

    def _server(self, port: int, ready: threading.Event) -> None:
        """One server's event stream: once it is open, the permissions and questions waiting and the sessions it runs
        (busy, or retrying), then each event as it comes; followed again when it ends while the server still listens,
        or when its instance ended (OpenCode 1.19 keeps that stream open but sends nothing more on it), `gone` when the
        server no longer listens."""
        while not self.stopped.is_set():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/event", timeout=None) as stream:
                    for request in call(port, "GET", "/permission") or []:
                        self.say(self._asked(port, request))
                    for request in read(port, "/question", []):
                        self.say({"type": "question", "port": port, "request": seen_question(request)})
                    listed = read(port, "/session/status", {})
                    for session in sorted(self.running.get(port, set()) - set(listed)):
                        self._status(port, session, {"type": "idle"})  # its run ended while the stream was closed
                    for session, status in listed.items():
                        self._status(port, session, status)
                    ready.set()
                    for raw in stream:
                        if self._heard(port, raw) == "disposed":
                            break  # its instance ended: this stream hears nothing more, a new one does
            except (OSError, ValueError, AttributeError, urllib.error.URLError):
                pass
            ready.set()
            if not listening(port):
                with self.lock:
                    self.running.pop(port, None)
                    self.say({"type": "gone", "port": port})
                return
            time.sleep(1.0)

    def _heard(self, port: int, raw: bytes) -> str:
        """One line of a server's stream said as the service needs it; the event's type when it was one."""
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            return ""
        try:
            event = json.loads(line[5:])
        except ValueError:
            return ""
        if not isinstance(event, dict):
            return ""
        kind, properties = event.get("type"), event.get("properties") or {}
        session = properties.get("sessionID")
        if kind == "permission.asked":
            self.say(self._asked(port, properties))
        elif kind == "permission.replied":
            self.say({
                "type": "replied", "port": port, "request": properties.get("requestID"),
                "session": properties.get("sessionID"), "reply": properties.get("reply"),
            })  # fmt: skip
        elif kind == "file.edited":
            self.say({"type": "edited", "port": port, "file": properties.get("file")})
        elif kind == "message.updated":
            self._message(port, properties)
        elif kind == "message.part.updated":
            part = properties.get("part") or {}
            self.hold(("part", port, part.get("id")), {
                "type": "part", "port": port, "session": part.get("sessionID") or session, "part": seen_part(part),
            })  # fmt: skip
        elif kind == "message.part.delta":
            if session in self.shown:
                key = ("delta", port, properties.get("partID"), properties.get("field"))
                self.join(key, {
                    "type": "delta", "port": port, "session": session, "message": properties.get("messageID"),
                    "part": properties.get("partID"), "field": properties.get("field"),
                }, str(properties.get("delta") or ""))  # fmt: skip
        elif kind in ("message.removed", "message.part.removed"):
            removed = {"type": "removed", "port": port, "session": session, "message": properties.get("messageID")}
            if properties.get("partID"):
                removed["part"] = properties["partID"]
            self.hold(("removed", port, properties.get("messageID"), properties.get("partID")), removed)
        elif kind == "session.status":
            self._status(port, session, properties.get("status") or {})
        elif kind in ("session.created", "session.updated", "session.deleted"):
            info = properties.get("info") or {}
            self.hold(("session", port, info.get("id") or session), {
                "type": "session", "port": port, "session": seen_session(info), "deleted": kind == "session.deleted",
            })  # fmt: skip
        elif kind == "todo.updated":
            todos = [
                {"content": str(each.get("content") or ""), "status": each.get("status"),
                 "priority": each.get("priority")}
                for each in properties.get("todos") or []
                if isinstance(each, dict)
            ]  # fmt: skip
            self.hold(("todo", port, session), {"type": "todo", "port": port, "session": session, "todos": todos})
        elif kind == "session.compacted":
            self.hold(("compacted", port, session), {"type": "compacted", "port": port, "session": session})
        elif kind == "session.error":
            said = said_error(properties.get("error"))
            self.hold(("error", port, session), {"type": "error", "port": port, "session": session, "error": said})
        elif kind == "question.asked":
            self.say({"type": "question", "port": port, "request": seen_question(properties)})
        elif kind in ("question.replied", "question.rejected"):
            self.say({
                "type": "answered", "port": port, "request": properties.get("requestID"), "session": session,
                "reply": "replied" if kind == "question.replied" else "rejected",
            })  # fmt: skip
        elif kind == "server.instance.disposed":
            self.say({"type": "disposed", "port": port})
            return "disposed"
        return str(kind or "")

    def _status(self, port: int, session: Any, status: dict[str, Any]) -> None:
        """A session's status, held for the burst; the sessions said running on each port are kept, so a stream opened
        again (OpenCode's instance started again) says idle for those it no longer lists."""
        with self.lock:
            running = self.running.setdefault(port, set())
            if str(status.get("type") or "idle") == "idle":
                running.discard(str(session))
            else:
                running.add(str(session))
            self.hold(("status", port, session), seen_status(port, session, status))

    def _message(self, port: int, properties: dict[str, Any]) -> None:
        """A message: held for the Monitor; and, the first time a message of the owner names its agent, said at once
        (design 0009 §7)."""
        info = properties.get("info") or {}
        id = str(info.get("id") or "")
        session = info.get("sessionID") or properties.get("sessionID")
        self.hold(("message", port, id), {"type": "message", "port": port, "session": session,
                                          "message": seen_message(info)})  # fmt: skip
        if info.get("role") != "user" or not info.get("agent") or not id or id in self.messages:
            return
        self.messages.add(id)
        self.say({
            "type": "agent", "port": port, "session": session, "agent": info["agent"],
            "terminal": self.terminals.get(port, False),
        })  # fmt: skip

    def _asked(self, port: int, request: dict[str, Any]) -> dict[str, Any]:
        """An ask as the service needs it: a change with its tool call's input (its old and new text, or its
        content), which OpenCode's diff alone cannot give exactly (design 0007 §2)."""
        tool = request.get("tool") or {}
        found = None
        if request.get("permission") == "edit" and tool.get("messageID"):
            path = f"/session/{request.get('sessionID')}/message/{tool['messageID']}"
            try:
                parts = (call(port, "GET", path) or {}).get("parts") or []
                part: dict[str, Any] = next((each for each in parts if each.get("callID") == tool.get("callID")), {})
                found = (part.get("state") or {}).get("input")
            except (OSError, ValueError, AttributeError, urllib.error.URLError):
                found = None
        given = found if isinstance(found, dict) and len(json.dumps(found)) <= CHANGE_INPUT else None
        return {"type": "asked", "port": port, "request": request, "input": given}


def read(port: int, path: str, empty: Any) -> Any:
    """What a server lists at `path`, or `empty` when it cannot say (an OpenCode without that route): the watch goes
    on without it."""
    try:
        found = call(port, "GET", path)
    except (OSError, ValueError, urllib.error.URLError):
        return empty
    return found if isinstance(found, type(empty)) else empty


def seen_status(port: int, session: Any, status: dict[str, Any]) -> dict[str, Any]:
    """A session's status as the watch says it: idle, busy, or retry with its attempt, OpenCode's words and when the
    next attempt is due (design 0012 §5.1)."""
    kind = str(status.get("type") or "idle")
    seen: dict[str, Any] = {"type": "status", "port": port, "session": session, "status": kind}
    if kind == "retry":
        seen.update({"attempt": status.get("attempt"), "message": cut(status.get("message") or "", OUTPUT),
                     "next": status.get("next")})  # fmt: skip
    return seen


def seen_session(info: dict[str, Any]) -> dict[str, Any]:
    """A session as the watch says it: its id, its parent when it is a subagent's, its title and times, what a revert
    took back, and whether it is being compacted."""
    time = info.get("time") or {}
    return {
        "id": info.get("id"), "parent": info.get("parentID"), "title": info.get("title") or "",
        "created": time.get("created"), "updated": time.get("updated"), "revert": info.get("revert") or {},
        "compacting": bool(time.get("compacting")),
    }  # fmt: skip


def seen_question(request: dict[str, Any]) -> dict[str, Any]:
    """A question the agent asks, as the watch says it."""
    return {"id": request.get("id"), "session": request.get("sessionID"), "questions": request.get("questions") or []}


def replace_older() -> None:
    """End a watcher left in the container by a service that stopped without closing it; this one takes its place."""
    try:
        with open(WATCHER) as kept:
            older = int(kept.read().strip())
        with open(f"/proc/{older}/cmdline", "rb") as running:
            argv = running.read().split(b"\0")
        if older != os.getpid() and b"watch" in argv and any(part.endswith(b"bridge.py") for part in argv):
            os.kill(older, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    try:
        with open(WATCHER, "w") as kept:
            kept.write(str(os.getpid()))
    except OSError:
        pass


def given() -> dict[str, Any]:
    """The JSON object on standard input (empty when there is none)."""
    raw = sys.stdin.read()
    value = json.loads(raw) if raw.strip() else {}
    return value if isinstance(value, dict) else {}


def act(argv: list[str]) -> dict[str, Any]:
    """Do the action the arguments name; what it found or did."""
    action, *rest = argv or [""]
    if action == "servers":
        return servers()
    if action == "messages":
        return messages(int(rest[0]), rest[1], int(rest[2]) if len(rest) > 2 else 40)
    if action == "part":
        return part(int(rest[0]), rest[1], rest[2], rest[3], int(rest[4]) if len(rest) > 4 else WHOLE)
    if action == "page":
        return page(int(rest[0]), rest[1], int(rest[2]) if len(rest) > 2 else PAGE, rest[3] if len(rest) > 3 else "")
    if action == "prompt":
        return prompt(int(rest[0]), rest[1], given())
    if action == "new":
        title = str(given().get("title") or "")
        session = call(int(rest[0]), "POST", "/session", {"title": title} if title else {})
        return {"session": session["id"]}
    if action == "abort":
        return {"stopped": bool(call(int(rest[0]), "POST", f"/session/{rest[1]}/abort"))}
    if action == "reject":
        return reject(int(rest[0]), rest[1])
    if action == "clear":
        return clear(int(rest[0]), rest[1], rest[2], rest[3])
    if action == "revert":
        return revert(int(rest[0]), rest[1], rest[2], rest[3] if len(rest) > 3 else "")
    if action == "unrevert":
        info = call(int(rest[0]), "POST", f"/session/{urllib.parse.quote(rest[1])}/unrevert") or {}
        return {"unreverted": True, "revert": info.get("revert") or {}}
    if action == "summarize":
        return summarize(int(rest[0]), rest[1], given())
    if action == "permission":
        if rest[2] not in ("once", "always", "reject"):
            raise ValueError(f"a permission's reply is once, always or reject, not {rest[2]!r}")
        reply = {"reply": rest[2]}
        note = str(given().get("message") or "").strip()
        if note and rest[2] == "reject":
            reply["message"] = note
        return {"replied": bool(call(int(rest[0]), "POST", f"/permission/{rest[1]}/reply", reply))}
    if action == "question":
        answers = given().get("answers") or []
        return {"replied": bool(call(int(rest[0]), "POST", f"/question/{rest[1]}/reply", {"answers": answers}))}
    if action == "free-port":
        return {"port": free_port()}
    if action == "serve":
        return serve({str(key): str(value) for key, value in (given().get("env") or {}).items()})
    if action == "mcp":
        return mcp()
    if action == "mcp-start":
        return mcp_start(int(rest[0]), rest[1], given().get("config"))
    if action == "mcp-stop":
        return {"stopped": bool(call(int(rest[0]), "POST", f"/mcp/{urllib.parse.quote(rest[1])}/disconnect"))}
    if action == "agents":
        return {"agents": agents(int(rest[0]))}
    if action == "cycle":
        count = int(rest[1])
        if not 0 <= count <= 8:
            raise ValueError(f"Tab is pressed 0 to 8 times, not {count}")
        for _ in range(count):  # the command's old name: OpenCode 1.19 maps it to agent.cycle (measured)
            call(int(rest[0]), "POST", "/tui/execute-command", {"command": "agent_cycle"})
        return {"cycled": count}
    if action == "show":
        asked = given()
        return show_waiting(int(rest[0]), str(rest[1]), float(asked.get("wait") or 0))
    if action == "implement":
        asked = given()
        agent, wait = str(asked.get("agent") or BUILD), float(asked.get("wait") or 0)
        return implement(int(rest[0]), str(asked.get("text") or ""), str(asked.get("title") or ""), agent, wait)
    raise ValueError(f"no action {action!r}")


def main() -> int:
    """Act, and print the result as one line of JSON, an error included; or watch, a line at a time. What it prints is
    UTF-8 whatever the locale says, as the service reads it (a text cut with "…", on Windows in the tests)."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:2] == ["watch"]:
        Watch().run()
        return 0
    if sys.argv[1:2] == ["held"]:  # started by `hold`, never by the service
        held(int(sys.argv[2]), sys.argv[3], json.loads(sys.stdin.read() or "null"))
        return 0
    try:
        result = {"ok": True, **act(sys.argv[1:])}
    except urllib.error.HTTPError as error:
        said = cut(error.read().decode(errors="replace"), 500)
        result = {"ok": False, "error": f"OpenCode answered {error.code}: {said}"}
    except (OSError, ValueError, RuntimeError, IndexError, KeyError, urllib.error.URLError) as error:
        result = {"ok": False, "error": str(error) or type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
