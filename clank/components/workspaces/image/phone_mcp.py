"""Clank's own MCP server for the agent (design 0005 §3): `send_to_phone(path, caption)` sends a file of the folder to
the owner's phone. It copies the file into the folder's `.clank/outbox/` with a `.json` beside it (its caption, when,
where it came from); the Clank service, which sees the folder on the machine, finds it there and shows it on the
phone. `.clank/` gets a `.gitignore` of its own, so git ignores it.

`look_at_figure(path, question)` (design 0008 §7) lets the agent check a figure it made: the vision model (the gateway's
role `vision`, at `CLANK_GATEWAY`, loaded on demand) answers the question about the image, and the figure's geometry
(written when Matplotlib saved it, `.clank/figures/`) is given beside it: its plots, their axes and their lines.

The Notion tools (design 0010 §4-§5) ask the gateway's `/notion/` routes, which forward them to Clank's service: the
reading ones (`notion_databases`, `notion_query`, `notion_page`, `notion_search`, marked read-only, so the planner may
use them) and the proposing ones (`notion_propose_entry`, `notion_propose_change`, `notion_propose_removal`,
`notion_submit`), which stage proposals for the owner's review and write nothing, and `notion_reply`, the agent's
answer to a comment of the owner's on a batch sent back to it; each names the workspace this server serves
(`CLANK_WORKSPACE_NAME`, given by Clank). A refusal comes back as the tool's error, in the service's words.

A box's tools of its flow (design 0013 §9) ask the gateway's `/flows/` routes, naming the workspace, and the service
gives each to the box at work there: `flow_read(flow?)`, the flow (marked read-only); `flow_propose_box(after, type,
title, prompt, deliverable, ...)`, a box proposed after a box of the flow, its arguments sent as the model gave them so
the service's refusal names the one to fix; `flow_submit(summary)`, the proposals ready for the owner; and
`flow_verdict(result, findings, criteria)`, a VERIFY box's verdict on the deliverable it checks: pass, or fail with
numbered findings, and each line of the brief and of what done means that it checked, met or not, with its evidence.
`flow_draft(flow)` (design 0013 §15) is a planning session's: the whole flow it drafted with the owner, which the
service checks and writes, or refuses naming each field to fix. None writes anything in the folder, so the planner may
use them.

It speaks MCP (revision 2025-06-18) over its standard input and output, one JSON message a line, with Python's standard
library only, so it runs in any workspace's container.
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

WORKSPACE = os.environ.get("CLANK_WORKSPACE", "/workspace")
OUTBOX = os.path.join(WORKSPACE, ".clank", "outbox")
LARGEST = 50 << 20
PROTOCOL = "2025-06-18"
GATEWAY = os.environ.get("CLANK_GATEWAY", "")
LOOK_SECONDS = 300.0  # the vision model may be loaded first
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
ROOT = GATEWAY[: -len("/v1")] if GATEWAY.endswith("/v1") else GATEWAY  # its /notion/ and /flows/ routes are here
WORKSPACE_NAME = os.environ.get("CLANK_WORKSPACE_NAME", "")
KEY = os.environ.get("CLANK_GATEWAY_KEY", "")  # the workspace's own key at the gateway (design 0016 §9)
NOTION_OFF = os.environ.get("CLANK_NOTION", "") == "off"  # a workspace allowed the cloud reads no Notion (§10)
NOTION_SECONDS = 120.0
TOOL = {
    "name": "send_to_phone",
    "description": (
        "Send a file of the workspace's folder (a figure, a table, a PDF, a short text) to the user's phone, where it "
        "shows at once, an image inline. Use it whenever the user asks for something to be sent to them or to their "
        "phone. Find the file, or make it first (save a figure as PNG), then send it with a caption that says what it "
        "is and how it was made (the parameters you chose). Returns where it was put for the phone."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The file, relative to the folder or under /workspace."},
            "caption": {"type": "string", "description": "What it is, in a sentence or two."},
        },
        "required": ["path"],
    },
}
LOOK = {
    "name": "look_at_figure",
    "description": (
        "Look at a figure of the workspace's folder (PNG or JPEG) and answer a question about it: whether it shows "
        "what it should, whether labels, legends and scales read well, what a part of it shows. A vision model reads "
        "the image; the figure's geometry (its plots, axis ranges and scales, lines and their labels), known when "
        "Matplotlib saved it here, is given too. Use it after making or changing a figure, before saying it is done. "
        "Returns the vision model's answer and the geometry."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The figure, relative to the folder or under /workspace."},
            "question": {"type": "string", "description": "What to look for or check, in a sentence or two."},
        },
        "required": ["path"],
    },
}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str], reads: bool) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
        "annotations": {"readOnlyHint": reads},
    }


TEXT = {"type": "string"}
WHY = {"type": "string", "description": "Why, in a sentence: the owner reads it before approving."}
SOURCES = {
    "type": "array",
    "items": {"type": "string"},
    "description": "The files, sections or scripts its content comes from (needed whenever it states a number).",
}
NOTION_TOOLS = [
    _tool(
        "notion_databases",
        "List the Notion databases the owner shared with Clank: each one's name and id, and its properties (their "
        "names and types, a select's options, the database a relation points to). Use it before querying or proposing. "
        "Returns JSON.",
        {}, [], True,
    ),
    _tool(
        "notion_query",
        "Entries of a shared Notion database as rows: each one's id, title and other properties as text (a relation as "
        "the titles it points to). Filter by words of the title (text) or with Notion's own filter object; limit is "
        "1 to 100 (25 by default); give the cursor of an answer to get the next entries. Returns JSON: the rows and "
        "the cursor of the next ones (null at the end).",
        {"database": {"type": "string", "description": "The database's name, or its id."},
         "text": {"type": "string", "description": "Words of the title."},
         "filter": {"type": "object", "description": "Notion's own filter of a data source's query."},
         "limit": {"type": "integer"}, "cursor": TEXT},
        ["database"], True,
    ),
    _tool(
        "notion_page",
        "One Notion entry: its properties, and its page as Markdown, where a link to another entry reads "
        "[title](notion:<id>). Read an entry before proposing a change to it. Returns its title, database, address, "
        "last edit, properties and page.",
        {"page": {"type": "string", "description": "The entry's id, or its notion: link."}},
        ["page"], True,
    ),
    _tool(
        "notion_search",
        "Find Notion entries and databases whose title holds these words. Returns JSON: each one's kind, id, title and "
        "database.",
        {"text": TEXT}, ["text"], True,
    ),
    _tool(
        "notion_propose_entry",
        "Propose a new entry in a shared Notion database. Nothing is written: the owner reviews it in VS Code and "
        "approves it, rejects it or sends it back with comments. properties: values by property name (text, a number, "
        "an option's name, a list of options, a date as YYYY-MM-DD, yes or no, related entries by their titles or "
        "ids); page_markdown: its page, in Markdown. Call notion_submit after your last proposal. Returns where it was "
        "staged, and notes for the owner.",
        {"database": {"type": "string", "description": "The database's name, or its id."},
         "properties": {"type": "object", "description": "Values by property name; the title is required."},
         "page_markdown": {"type": "string", "description": "Its page, in Markdown."},
         "why": WHY, "sources": SOURCES},
        ["database", "properties", "why"], False,
    ),
    _tool(
        "notion_propose_change",
        "Propose a change to a Notion entry: new values for some of its properties, its page as it should be after the "
        "change (read it with notion_page first, then give the whole page, edited), or both. Nothing is written: the "
        "owner reviews it in VS Code. Returns where it was staged.",
        {"page": {"type": "string", "description": "The entry's id, or its notion: link."},
         "properties": {"type": "object", "description": "Only the properties it changes, by name."},
         "page_markdown": {"type": "string", "description": "The whole page after the change, in Markdown."},
         "why": WHY, "sources": SOURCES},
        ["page", "why"], False,
    ),
    _tool(
        "notion_propose_removal",
        "Propose moving a Notion entry to the trash (the owner can restore it). Nothing is written: the owner reviews "
        "it in VS Code. Returns where it was staged.",
        {"page": {"type": "string", "description": "The entry's id, or its notion: link."}, "why": WHY},
        ["page", "why"], False,
    ),
    _tool(
        "notion_submit",
        "Submit the proposals staged so far as one batch for the owner's review in VS Code, with a summary of what the "
        "batch does. Call it once, after your last proposal. Returns the batch.",
        {"summary": {"type": "string", "description": "What the batch does, in a sentence or two."}},
        ["summary"], False,
    ),
    _tool(
        "notion_reply",
        "Answer a comment the owner made on a batch they sent back to you (its id, as c1, is in their message): what "
        "you did about it, or why you did not. Answer every comment, then submit the revised batch with notion_submit. "
        "Returns the comment, answered.",
        {"comment": {"type": "string", "description": "The comment's id, as c1."},
         "text": {"type": "string", "description": "What you did, or why not, in a sentence or two."}},
        ["comment", "text"], False,
    ),
]  # fmt: skip
PROPOSING = {"notion_propose_entry", "notion_propose_change", "notion_propose_removal", "notion_submit", "notion_reply"}
FILES = {"type": "array", "items": {"type": "string"}}
PROPOSING_FLOW = (  # the arguments of flow_propose_box, sent as the model gave them
    "after", "type", "title", "prompt", "deliverable", "accept_when", "model", "mode", "sees", "why", "flow",
)  # fmt: skip
FLOW_TOOLS = [
    _tool(
        "flow_read",
        "Read the flow you are a box of: its boxes in the order they run, each with its type, title, state in this "
        "run, the files it sees and writes and the boxes after it, and the boxes proposed in this run. It is "
        "read-only: you change the flow only by proposing boxes (flow_propose_box, then flow_submit). Returns the flow "
        "as JSON.",
        {"flow": {"type": "string",
                  "description": "Another flow of this workspace, by its name, when no box of a flow works now; "
                                 "empty: your own."}},
        [], True,
    ),
    _tool(
        "flow_propose_box",
        "Propose a box for your flow, after a box of it; nothing changes until the user accepts it. A DECOMPOSE "
        "proposes each task after its own box, one call per task, in the order they should run. Give its type (task, "
        "plan, verify, integrate or gate), its title, its prompt (everything its model must know: it starts afresh, "
        "without this session), its deliverable (the files it writes in the folder) and what makes that right. "
        "Returns its id (T1) and that it waits for the user, or why it was refused, to fix and propose again.",
        {"after": {"type": "string", "description": "The box of the flow it comes after (a DECOMPOSE: its own)."},
         "type": {"type": "string", "description": "task, plan, verify, decompose, integrate or gate."},
         "title": {"type": "string", "description": "What it does, in a few words."},
         "prompt": {"type": "string", "description": "Everything its model must know, in its own words."},
         "deliverable": {**FILES, "description": "The files it writes, from the folder (runs/estimates.md)."},
         "accept_when": {**FILES, "description": "What makes its deliverable right, one thing each."},
         "model": {"type": "string", "description": "The preset it runs on; empty: the flow's."},
         "mode": {"type": "string", "description": "plan, review or auto; empty: the box's own."},
         "sees": {**FILES, "description": "The files its first message hands it (one written by a box before it)."},
         "why": {"type": "string", "description": "Why it is needed, in a sentence: the user reads it."},
         "flow": {"type": "string", "description": "Your flow's name; empty: the flow of the box you are."}},
        ["after", "type", "title", "prompt", "deliverable"], False,
    ),
    _tool(
        "flow_submit",
        "Submit your proposed boxes to the user, once every one is proposed; then stop. Returns which of them wait "
        "for the user.",
        {"summary": {"type": "string", "description": "What you propose, and why, in a sentence or two."},
         "flow": {"type": "string", "description": "Your flow's name; empty: the flow of the box you are."}},
        ["summary"], False,
    ),
    _tool(
        "flow_verdict",
        "Give your verdict as a VERIFY box of a flow, on the deliverable you check: pass, or fail with findings, each "
        "one thing to fix. List in criteria each line of the brief's limits and of what the deliverable is accepted "
        "when that you checked, quoted, whether it is met, and your evidence (a figure, a line, a file). Call it once, "
        "at the end of your check, then stop. Returns that your verdict is kept, and on which try.",
        {"result": {"type": "string", "enum": ["pass", "fail"], "description": "pass, or fail."},
         "findings": {"type": "array", "items": {"type": "string"},
                      "description": "A fail's findings, each one thing to fix, in order; empty for a pass."},
         "criteria": {"type": "array", "description": "The lines you checked.", "items": {
             "type": "object", "required": ["line", "met"],
             "properties": {"line": {"type": "string", "description": "The line of the brief or accept when, quoted."},
                            "met": {"type": "boolean", "description": "Whether the deliverable meets it."},
                            "evidence": {"type": "string", "description": "What shows it."}}}}},
        ["result", "findings"], False,
    ),
    _tool(
        "flow_draft",
        "Only in a planning session Clank opened to build a flow with the user: send the whole flow you drafted, "
        "once BRIEF.md is written with them. Clank checks it; while it breaks a rule, nothing is written and you get "
        "each problem with the field it is in, and the check's warnings: fix them and call it again. Once it keeps "
        "every rule, Clank writes the flow and asks the user to look, then run it. Returns what Clank did, in words.",
        {"flow": {"type": "object",
                  "description": "The flow, as its file holds it: title, defaults, boxes and lines.",
                  "properties": {"title": {"type": "string"}, "defaults": {"type": "object"},
                                 "boxes": {"type": "array", "items": {"type": "object"}},
                                 "lines": {"type": "array", "items": {"type": "object"}}}}},
        ["flow"], False,
    ),
]  # fmt: skip


def flow(name: str, arguments: dict[str, Any]) -> str:
    """One tool of a box's flow: its request to the gateway, and the service's answer as text."""
    if not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    if name == "flow_read":
        named = str(arguments.get("flow") or "").strip()
        query = {"workspace": WORKSPACE_NAME, **({"flow": named} if named else {})}
        return _json(_gateway("GET", "flows/read?" + urllib.parse.urlencode(query), None, "a flow"))
    if name == "flow_propose_box":  # as the model gave them: the service names the argument to fix
        body = {"workspace": WORKSPACE_NAME, **{key: arguments[key] for key in PROPOSING_FLOW if key in arguments}}
        found = _gateway("POST", "flows/propose", body, "a flow")
    elif name == "flow_submit":
        body = {"workspace": WORKSPACE_NAME, "summary": str(arguments.get("summary") or "")}
        body |= {"flow": str(arguments["flow"])} if arguments.get("flow") else {}
        found = _gateway("POST", "flows/submit", body, "a flow")
    elif name == "flow_draft":  # as the model gave it: the service names each field to fix
        found = _gateway("POST", "flows/draft", {"workspace": WORKSPACE_NAME, "flow": arguments.get("flow")}, "a flow")
    else:
        criteria = arguments.get("criteria") or []
        body = {
            "workspace": WORKSPACE_NAME,
            "result": str(arguments.get("result") or ""),
            "findings": [str(each) for each in arguments.get("findings") or []],
            "criteria": criteria if isinstance(criteria, list) else [criteria],  # as given: the service names the fix
        }
        found = _gateway("POST", "flows/verdict", body, "a flow")
    return str(found.get("said") or "") if isinstance(found, dict) and found.get("said") else _json(found)


def notion(name: str, arguments: dict[str, Any]) -> str:
    """One Notion tool: its request to the gateway, and the answer as text."""
    if name in PROPOSING and not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    given = {key: value for key, value in arguments.items() if value not in (None, "")}
    page = str(given.get("page") or "").strip().removeprefix("notion:")
    if name == "notion_databases":
        return _json(_notion("GET", "databases"))
    if name == "notion_query":
        return _json(_notion("POST", "query", {key: given[key] for key in ("database", "text", "filter", "limit",
                                                                         "cursor") if key in given}))  # fmt: skip
    if name == "notion_page":
        return _page(_notion("GET", f"page/{urllib.parse.quote(page, safe='')}"))
    if name == "notion_search":
        return _json(_notion("GET", "search?" + urllib.parse.urlencode({"text": given.get("text", "")})))
    common = {"workspace": WORKSPACE_NAME}
    if name == "notion_propose_entry":
        body = {**common, "database": given.get("database", ""), "properties": given.get("properties") or {},
                "markdown": given.get("page_markdown", ""), "why": given.get("why", ""),
                "sources": given.get("sources") or []}  # fmt: skip
        return _json(_notion("POST", "propose/entry", body))
    if name == "notion_propose_change":
        body = {**common, "page": page, "properties": given.get("properties") or {},
                "markdown": given.get("page_markdown", ""), "why": given.get("why", ""),
                "sources": given.get("sources") or []}  # fmt: skip
        return _json(_notion("POST", "propose/change", body))
    if name == "notion_propose_removal":
        return _json(_notion("POST", "propose/removal", {**common, "page": page, "why": given.get("why", "")}))
    if name == "notion_reply":
        body = {**common, "comment": str(given.get("comment", "")).strip(), "text": given.get("text", "")}
        return _json(_notion("POST", "reply", body))
    return _json(_notion("POST", "submit", {**common, "summary": given.get("summary", "")}))


def _notion(method: str, path: str, body: Any = None) -> Any:
    return _gateway(method, f"notion/{path}", body, "Notion")


def _gateway(method: str, path: str, body: Any, what: str) -> Any:
    """One request to the gateway's routes at its root (`notion/...`, `flows/...`); its answer, or its refusal as an
    error in the service's words."""
    if not ROOT:
        raise ValueError(f"Clank gave this server no gateway, so it cannot reach {what}")
    data = json.dumps(body).encode() if method == "POST" else None
    request = urllib.request.Request(f"{ROOT}/{path}", data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=NOTION_SECONDS) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as error:
        try:
            said = json.loads(error.read()).get("error", {}).get("message", "")
        except ValueError:
            said = ""
        raise ValueError(said or f"the gateway answered {error.code}") from error
    except (urllib.error.URLError, OSError) as error:
        raise ValueError(f"the gateway did not answer: {error}") from error


def _headers() -> dict[str, str]:
    """The headers of a request to the gateway: the workspace's key, when Clank gave one."""
    return {"Content-Type": "application/json", **({"Authorization": f"Bearer {KEY}"} if KEY else {})}


def _json(found: Any) -> str:
    return json.dumps(found, ensure_ascii=False)


def _page(found: dict[str, Any]) -> str:
    """An entry as text: its title, where it is, its properties, then its page."""
    properties = "\n".join(f"- {name}: {value}" for name, value in (found.get("properties") or {}).items())
    return (
        f"# {found.get('title', '')}\n"
        f"id {found.get('id', '')} · {found.get('database', '')} · {found.get('url', '')} · last edited "
        f"{found.get('edited', '')}\n\nProperties:\n{properties or '(none)'}\n\nPage:\n\n{found.get('markdown', '')}"
    )


def send(path: str, caption: str) -> str:
    """Copy the file into the outbox, with its caption beside it; what was done."""
    source = os.path.realpath(os.path.join(WORKSPACE, path))
    if not source.startswith(os.path.realpath(WORKSPACE) + os.sep):
        raise ValueError(f"{path} is not in the folder: only the folder's files can be sent")
    if not os.path.isfile(source):
        raise ValueError(f"{path} is not a file of the folder")
    if os.path.getsize(source) > LARGEST:
        raise ValueError(f"{path} is larger than {LARGEST >> 20} MB: send a smaller one")
    os.makedirs(OUTBOX, exist_ok=True)
    ignore = os.path.join(WORKSPACE, ".clank", ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as file:
            file.write("# Clank's own: what the agent sent to the phone (design 0005 §3)\n*\n")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{os.path.basename(source)}"
    shutil.copyfile(source, os.path.join(OUTBOX, name))
    where = os.path.relpath(source, WORKSPACE).replace(os.sep, "/")
    note = {"file": name, "caption": caption, "from": where, "sent": time.time()}
    with open(os.path.join(OUTBOX, name + ".json"), "w", encoding="utf-8") as file:
        json.dump(note, file)
    return f"Sent {note['from']} to the phone (.clank/outbox/{name})."


def look(path: str, question: str) -> str:
    """The vision model's answer about a figure of the folder, and the figure's geometry when it is known."""
    source = os.path.realpath(os.path.join(WORKSPACE, path))
    if not source.startswith(os.path.realpath(WORKSPACE) + os.sep) or not os.path.isfile(source):
        raise ValueError(f"{path} is not a file of the folder")
    kind = IMAGES.get(os.path.splitext(source)[1].lower())
    if kind is None:
        raise ValueError(f"{path} is not a PNG or a JPEG: save the figure as one to look at it")
    with open(source, "rb") as file:
        data = file.read()
    relative = os.path.relpath(source, WORKSPACE).replace(os.sep, "/")
    said = [f"The vision model on {relative}: {_seen(data, kind, question)}"]
    shape = _geometry(relative, data)
    if shape:
        said += ["", "Its geometry (from Matplotlib's save):", shape]
    return "\n".join(said)


def _seen(data: bytes, kind: str, question: str) -> str:
    if not GATEWAY:
        return "(no vision model: Clank gave this server no gateway)"
    asked = (question.strip() or "Describe this figure: what it plots, and anything that reads badly.") + (
        " Answer briefly and concretely, reading values from the axes."
    )
    body = {
        "model": "vision", "max_tokens": 500, "temperature": 0.2,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{kind};base64,{base64.b64encode(data).decode()}"}},
            {"type": "text", "text": asked},
        ]}],
    }  # fmt: skip
    request = urllib.request.Request(f"{GATEWAY}/chat/completions", data=json.dumps(body).encode(), headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=LOOK_SECONDS) as answer:
            found = json.loads(answer.read())
        return str(found["choices"][0]["message"].get("content") or "").strip() or "(it said nothing)"
    except urllib.error.HTTPError as error:
        try:
            why = json.loads(error.read()).get("error", {}).get("message", "")
        except ValueError:
            why = ""
        return f"(the vision model did not answer: {why or error})"
    except (OSError, ValueError, KeyError, IndexError) as error:
        return f"(the vision model did not answer: {error})"


def _geometry(relative: str, data: bytes) -> str:
    """The figure's plots in brief, when Matplotlib saved it here and it is still this figure."""
    kept = os.path.join(WORKSPACE, ".clank", "figures", *f"{relative}.json".split("/"))
    try:
        with open(kept, encoding="utf-8") as file:
            shape = json.load(file)
    except (OSError, ValueError):
        return ""
    if shape.get("sha256") != hashlib.sha256(data).hexdigest():
        return ""
    lines = [f"- figure: {shape['size'][0]} x {shape['size'][1]} pixels" + (f", titled {shape['title']!r}"
             if shape.get("title") else "")]  # fmt: skip
    for plot in shape.get("axes") or []:
        series = [line.get("label") or "(unlabeled)" for line in [*plot.get("lines", []), *plot.get("scatters", [])]]
        lines.append(
            f"- plot {plot['index'] + 1} {plot.get('title')!r}: x {plot.get('xlabel')!r} {plot['xlim'][0]:.4g} to "
            f"{plot['xlim'][1]:.4g} ({plot['xscale']}), y {plot.get('ylabel')!r} {plot['ylim'][0]:.4g} to "
            f"{plot['ylim'][1]:.4g} ({plot['yscale']}); lines: {', '.join(series) or 'none'}"
            + (f"; legend: {', '.join(plot['legend']['entries'])}" if plot.get("legend") else "")
        )
    return "\n".join(lines)


def answer(message: dict[str, Any]) -> dict[str, Any] | None:
    """The reply to one message from the client; None for a notification."""
    method, id = message.get("method"), message.get("id")
    if id is None:
        return None  # a notification
    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion") or PROTOCOL
        result: dict[str, Any] = {
            "protocolVersion": asked, "capabilities": {"tools": {}},
            "serverInfo": {"name": "clank", "version": "1"},
        }  # fmt: skip
    elif method == "tools/list":
        result = {"tools": [TOOL, LOOK, *_notion_tools(), *FLOW_TOOLS]}
    elif method == "tools/call":
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        names = {TOOL["name"], LOOK["name"], *(tool["name"] for tool in [*_notion_tools(), *FLOW_TOOLS])}
        if params.get("name") not in names:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32602, "message": "no such tool"}}
        path = str(arguments.get("path") or "")
        try:
            if str(params.get("name")).startswith("notion_"):
                text, failed = notion(str(params["name"]), arguments), False
            elif str(params.get("name")).startswith("flow_"):
                text, failed = flow(str(params["name"]), arguments), False
            elif params.get("name") == LOOK["name"]:
                text, failed = look(path, str(arguments.get("question") or "")), False
            else:
                text, failed = send(path, str(arguments.get("caption") or "")), False
        except (OSError, ValueError) as error:
            text, failed = str(error), True
        result = {"content": [{"type": "text", "text": text}], "isError": failed}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _notion_tools() -> list[dict[str, Any]]:
    """Notion's tools, none for a workspace allowed the cloud (design 0016 §10)."""
    return [] if NOTION_OFF else NOTION_TOOLS


def main() -> int:
    """Answer each message on standard input, one JSON line each, until it closes."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict) and (reply := answer(message)) is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
