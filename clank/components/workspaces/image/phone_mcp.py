"""Clank's own MCP server for the agent (design 0005 §3): `send_to_phone(path, caption)` sends a file of the folder to
the owner's phone. It copies the file into the folder's `.clank/outbox/` with a `.json` beside it (its caption, when,
where it came from); the Clank service, which sees the folder on the machine, finds it there and shows it on the
phone. `.clank/` gets a `.gitignore` of its own, so git ignores it.

`look_at_figure(path, question)` (design 0008 §7) lets the agent check a figure it made: the vision model (the gateway's
role `vision`, at `CLANK_GATEWAY`, loaded on demand) answers the question about the image, and the figure's geometry
(written when Matplotlib saved it, `.clank/figures/`) is given beside it: its plots, their axes and their lines. A
reading that takes longer than a tool call may (OpenCode stops one after a while; design 0021 §9) answers within
`ANSWER_SECONDS` that the vision model is still reading, and goes on in the background: the same figure and question
asked again are given its reading, without asking the vision model twice.

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
service checks and writes, or refuses naming each field to fix. `flow_decide(choice, why, ...)` (§16) is an
orchestrator's checkpoint's one decision, which the service checks, keeps and applies when the checkpoint ends. None
writes anything in the folder, so the planner may use them, but `flow_job(command, title, minutes)` (§17): a box's
long computation, which Clank runs detached in the container while the box's turn ends and waits for it.

`find_figures(query, limit)` (design 0018 §7.4) finds the folder's figures that best match words, from their names,
what Matplotlib recorded of them, the LaTeX captions that include them and the scripts that name them (its neighbor
`find_figures.py`, in the container too); it reads only, and asks nothing of the gateway.

`show_files(paths, why)` (design 0018 §7) opens files of the folder in the owner's VS Code window, on the left beside
OpenCode, through the gateway's `/agents/show` route: the owner looks at them themselves, so the model, asked to open
something, opens it and stops. It writes nothing in the folder, so the planner may use it.

`run_job(command, title, minutes)`, `job_status(job)` and `job_stop(job)` (design 0021 §6) are the agent's jobs,
through the gateway's `/agents/jobs` routes: a long computation run detached in the container at the lowest CPU
priority, followed and stopped; the session is told when it ends. `job_status` reads only, so the planner may use it.

`make_artifact(name, title, kind, files, note)` (design 0021 §5) makes a page for the owner from files the agent wrote
in the folder, through the gateway's `/agents/artifacts`: Clank keeps it as a version and opens it in VS Code.

It speaks MCP (revision 2025-06-18) over its standard input and output, one JSON message a line, with Python's standard
library only, so it runs in any workspace's container.
"""

import base64
import concurrent.futures
import hashlib
import importlib
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
ANSWER_SECONDS = float(os.environ.get("CLANK_LOOK_ANSWER_SECONDS") or 45)  # within OpenCode's time limit for a call
STILL_READING = (
    "(the vision model is still reading it: call look_at_figure again in a minute with the same path and question, "
    "and its reading is given then)"
)
READINGS: dict[tuple[str, str], "concurrent.futures.Future[str]"] = {}  # by the image's hash and the question
READERS = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="clank-look")
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
        "what it should, whether labels, legends and scales read well, what a part of it shows. Your own model reads "
        "no images: this tool is how you see one. Clank's vision model reads the image (loaded when needed, so it is "
        "always there); the figure's geometry (its plots, axis ranges and scales, lines and their labels), known when "
        "Matplotlib saved it here, is given too. Use it after making or changing a figure, before saying it is done. "
        "Returns the vision model's answer and the geometry; when it says the vision model is still reading, call it "
        "again in a minute with the same path and question."
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
SHOW = {
    "name": "show_files",
    "description": (
        "Open files of the workspace's folder in the user's VS Code window, beside you, for the user to look at "
        "themselves (the only way to: this container has no `code` command): figures (they open in the user's "
        "annotator), PDFs, LaTeX, code, notes, any file, up to 12 at once. When the user asks to see, open, show or "
        "pull up something, find the files (find_figures, or search the folder with ls, find or rg), call this, say in "
        "one line what you opened, and stop: do not read, describe or check what you opened (no look_at_figure) unless "
        "the user asks for that too. Returns what was opened, and each path that is not a file of the folder."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "The files, relative to the folder or under /workspace."},
            "why": {"type": "string", "description": "What they are, in a few words: the user sees it."},
        },
        "required": ["paths"],
    },
    "annotations": {"readOnlyHint": True},
}  # fmt: skip
FIND = {
    "name": "find_figures",
    "description": (
        "Find the figures of the workspace's folder (images and PDFs) that best match words: their names and folders, "
        "the titles, axis labels and legends Matplotlib recorded when it saved them and the script that did, the LaTeX "
        "captions and labels of the figure environments that include them, the scripts that name them, and when they "
        "were made (today, yesterday, this week, last week, a weekday, latest). Use it when the user asks for a figure "
        "by what it shows; then open the ones they want with show_files. Returns the best figures, each with what is "
        "known of it and the words it matched, or the newest figures when none matches."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What the figure shows, or when it was made, in words."},
            "limit": {"type": "integer", "description": "How many figures at most (5 by default)."},
        },
        "required": ["query"],
    },
    "annotations": {"readOnlyHint": True},
}


def _job_tools() -> list[dict[str, Any]]:
    """The agent's jobs (design 0021 §6)."""
    job = {"type": "integer", "description": "The job's number, as run_job gave it."}
    return [
        _tool(
            "run_job",
            "Start a long computation as a job: any command you expect to run more than two minutes (a simulation, a "
            "sweep, a build, a batch of seeds), in place of running it with bash, which stops a command after a few "
            "minutes. Clank runs it in the folder, detached, at the lowest CPU priority (so the model keeps its "
            "speed), its output in a log, for at most minutes (240 by default). Then go on with other work, or end "
            "your turn saying what you expect it to give: you are told when it ends (how, after how long, its log's "
            "last lines, the files it wrote). Returns its number and where its log is, or why it did not start.",
            {
                "command": {
                    "type": "string",
                    "description": "The command, as you would run it in bash, in the folder.",
                },
                "title": {"type": "string", "description": "What it computes, in a few words."},
                "minutes": {"type": "integer", "description": "How long it may run before Clank ends it (240)."},
            },
            ["command", "title"],
            False,
        ),
        _tool(
            "job_status",
            "A job of this workspace: its state, how long it has run, its log's last lines and the files it wrote; "
            "with no number, every job in a line each, newest first.",
            {"job": job},
            [],
            True,
        ),
        _tool(
            "job_stop", "Stop a job and everything it started. Returns what Clank did.", {"job": job}, ["job"], False
        ),
    ]


ARTIFACT = {
    "name": "make_artifact",
    "description": (
        "Make a page for the user from files you wrote in the folder: an interactive plot of results, a parameter "
        "explorer, an explainer, a report, a diagram. Clank keeps it as a version under .clank/artifacts/<name>/ and "
        "opens it in the user's VS Code window beside you. Its page (the first file) uses only its own files and "
        "Clank's libraries, with no network: clank-lib/plotly.min.js (charts), clank-lib/katex.min.js with "
        "clank-lib/katex.min.css and clank-lib/auto-render.min.js (math), clank-lib/marked.min.js (Markdown), "
        "clank-lib/mermaid.min.js (diagrams). Name its data files after it: they are copied with it, keeping their "
        "paths. A markdown kind is a .md file (math in $...$ and $$...$$), drawn by Clank's page; an svg kind is a "
        ".svg file. To change it, write its files again and call make_artifact with the same name: that makes the "
        "next version. Returns its version, or why it was refused."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Lowercase letters, digits and dashes, as in sweep-results."},
            "title": {"type": "string", "description": "What the user sees as its title."},
            "kind": {"type": "string", "enum": ["html", "markdown", "svg"], "description": "Its page's kind (html)."},
            "files": {"type": "array", "items": {"type": "string"},
                      "description": "Its page first, then every file it reads, from the folder."},
            "note": {"type": "string", "description": "What changed in this version, in a line."},
        },
        "required": ["name", "title", "files"],
    },
    "annotations": {"readOnlyHint": False},
}  # fmt: skip


_AT = {
    "type": "object",
    "description": (
        'Where it goes, by where and never pixels: {"right_of": id}, {"left_of": id}, {"below": id}, '
        '{"above": id} (beside an item, aligned with it), {"in": frame id} (inside a frame, which grows to hold '
        'it), {"slot": slot id} (fills the slot the owner drew, which it takes), or {"x": .., "y": ..}. '
        "Left out: a new row under everything."
    ),
}
_BOARD = {"type": "string", "description": "The board: its name (fig3) or its path in the folder (figures/fig3.board)."}
BOARD_FIELDS = ("file", "caption", "source", "mode", "text", "label", "name", "around", "from", "to", "w", "h")
BOARD_TOOLS = [
    {
        "name": "board_new",
        "description": (
            "Make a board: a canvas you share with the user, a .board file in the folder, where you place figures, "
            "LaTeX, notes and frames and the user moves and annotates them. It opens in the user's VS Code window. "
            "Returns its path."
        ),
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Its name (fig3 makes fig3.board)."},
            "folder": {"type": "string", "description": "The folder under the workspace to make it in (figures)."},
            "title": {"type": "string", "description": "Its title."},
        }, "required": ["name"]},
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "board_read",
        "description": (
            "Read a board in words: every item with its id, kind, place and size and what it shows, what each frame "
            "holds, the open slots, and the user's annotations by what they are over (a pen loop, an arrow, a "
            "highlight, a pin with its comment). Read it before you change it, and after the user asks about it."
        ),
        "inputSchema": {"type": "object", "properties": {"board": _BOARD}, "required": ["board"]},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "board_add",
        "description": (
            "Add to a board, placed by where (`at`), never pixels: Clank aligns it with its neighbor and keeps it "
            "clear of the others. A figure is an image file of the folder (PNG, JPEG, SVG ...), sized from it; LaTeX "
            "is math (mode math, drawn at once: an equation, an aligned derivation) or a drawing compiled with TeX "
            "(mode compiled: TikZ, pgfplots, a table); a note is Markdown with $math$; a slot is an empty place for a "
            "figure; a frame goes around items you name (it exports as one figure); an arrow goes from one item to "
            "another. A figure placed in a slot takes it. Returns the new item's id."
        ),
        "inputSchema": {"type": "object", "properties": {
            "board": _BOARD,
            "kind": {"type": "string", "enum": ["figure", "latex", "note", "slot", "frame", "arrow"]},
            "file": {"type": "string", "description": "A figure's image, from the folder."},
            "caption": {"type": "string", "description": "A figure's caption, under it."},
            "source": {"type": "string", "description": "LaTeX's source, without $ for math."},
            "mode": {"type": "string", "enum": ["math", "compiled"], "description": "LaTeX: math (default), compiled."},
            "text": {"type": "string", "description": "A note's Markdown."},
            "label": {"type": "string", "description": "A slot's label: the figure that goes there."},
            "name": {"type": "string", "description": "A frame's name (Figure 3)."},
            "around": {"type": "array", "items": {"type": "string"}, "description": "A frame's items, by id."},
            "from": {"type": "object", "description": "An arrow's start: {\"item\": id}."},
            "to": {"type": "object", "description": "An arrow's end: {\"item\": id}."},
            "w": {"type": "number", "description": "A width in pixels, when the default does not suit."},
            "at": _AT,
        }, "required": ["board", "kind"]},
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "board_update",
        "description": (
            "Change an item of a board: its caption, source, text, label, name, file or size, and move it with `at` "
            "(as board_add takes it). Returns what changed."
        ),
        "inputSchema": {"type": "object", "properties": {
            "board": _BOARD, "id": {"type": "string", "description": "The item, as board_read names it."},
            "file": {"type": "string"}, "caption": {"type": "string"}, "source": {"type": "string"},
            "mode": {"type": "string", "enum": ["math", "compiled"]}, "text": {"type": "string"},
            "label": {"type": "string"}, "name": {"type": "string"}, "w": {"type": "number"}, "at": _AT,
        }, "required": ["board", "id"]},
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "board_remove",
        "description": "Take an item away from a board (its history keeps it). Returns what was taken away.",
        "inputSchema": {"type": "object", "properties": {"board": _BOARD, "id": {"type": "string"}},
                        "required": ["board", "id"]},
        "annotations": {"readOnlyHint": False},
    },
]  # fmt: skip


def board(name: str, arguments: dict[str, Any]) -> str:
    """A board tool (design 0022 §4): its request to the gateway naming the workspace, and the service's words."""
    if not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    named = str(arguments.get("board") or "")
    fields = {key: arguments[key] for key in BOARD_FIELDS if key in arguments}
    at = arguments.get("at") if isinstance(arguments.get("at"), dict) else None
    body: dict[str, Any]
    if name == "board_new":
        body = {"workspace": WORKSPACE_NAME, "name": str(arguments.get("name") or ""),
                "folder": str(arguments.get("folder") or ""), "title": str(arguments.get("title") or "")}  # fmt: skip
        return str(_gateway("POST", "agents/boards", body, "boards").get("said") or "")
    if name == "board_read":
        query = urllib.parse.urlencode({"workspace": WORKSPACE_NAME, "board": named})
        return str(_gateway("GET", f"agents/boards/read?{query}", None, "boards").get("said") or "")
    if name == "board_add":
        body = {"workspace": WORKSPACE_NAME, "board": named, "kind": str(arguments.get("kind") or ""),
                "fields": fields, "at": at}  # fmt: skip
        return str(_gateway("POST", "agents/boards/add", body, "boards").get("said") or "")
    if name == "board_update":
        body = {"workspace": WORKSPACE_NAME, "board": named, "id": str(arguments.get("id") or ""), "changes": fields,
                "at": at}  # fmt: skip
        return str(_gateway("POST", "agents/boards/update", body, "boards").get("said") or "")
    body = {"workspace": WORKSPACE_NAME, "board": named, "id": str(arguments.get("id") or "")}
    return str(_gateway("POST", "agents/boards/remove", body, "boards").get("said") or "")


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
        "flow_decide",
        "Only as a flow's orchestrator, at a checkpoint Clank opened: give your one decision, then stop. choice is one "
        "of the choices your checkpoint lists (after a box: go on, change, back, pause or stop; at a question: one of "
        "its answers, or leave; while a box waits on its job: wait, side or change). Rewrite the ledger's facts and "
        "plan, judge each line of the brief met or not, say whether the run is progressing or looping, give the next "
        "box a note when it needs one, and tell the user "
        "at once what they should know (tell_user; pause and leave need it). Returns that your decision is kept, or "
        "what to fix and send again.",
        {"choice": {"type": "string", "description": "What you decide: one of the choices your checkpoint lists."},
         "why": {"type": "string", "description": "Why, citing the evidence (a check's output, a figure, a file)."},
         "met": {**FILES, "description": "The brief's lines that are met, quoted."},
         "unmet": {**FILES, "description": "The brief's lines not met yet, quoted."},
         "progressing": {"type": "boolean", "description": "Whether the run made progress since the last checkpoint."},
         "looping": {"type": "boolean", "description": "Whether the same failure came back for the same reason."},
         "facts": {"type": "string", "description": "What is known now, rewritten whole."},
         "plan": {"type": "string", "description": "The plan from here, in a few lines."},
         "note": {"type": "string", "description": "What the next box is told, or your words with an answer."},
         "back_to": {"type": "string", "description": "For back: the box to do again."},
         "tell_user": {"type": "string", "description": "What the user should know now, in a few sentences: it reaches "
                       "them at once, and the run does not wait for it. Needed for pause and leave."},
         "side": {"type": "array", "description": "For side: one to three side tasks, run one after another while "
                  "the job runs, each writing one note into the corpus.",
                  "items": {"type": "object", "required": ["title", "prompt"], "properties": {
                      "title": {"type": "string", "description": "What it is about; its note is named after it."},
                      "prompt": {"type": "string", "description": "Everything its model must know: it starts afresh."},
                      "reads": FILES}}},
         "changes": {"type": "array", "description": "For change: each an edit of a box not run, or a box added.",
                     "items": {"type": "object", "required": ["box"], "properties": {
                         "box": {"type": "string", "description": "The box edited, or the new box's id."},
                         "after": {"type": "string", "description": "A new box: the box it comes after."},
                         "type": {"type": "string", "description": "A new box's type: task or verify."},
                         "title": {"type": "string"}, "prompt": {"type": "string"},
                         "sees": FILES, "writes": FILES, "accept_when": FILES,
                         "accept_command": {"type": "string"}, "model": {"type": "string"},
                         "tries": {"type": "integer"}, "minutes": {"type": "integer"},
                         "tokens": {"type": "integer"}}}}},
        ["choice", "why", "progressing", "looping", "facts", "plan"], False,
    ),
    _tool(
        "flow_job",
        "Start a long computation as a job: any command you expect to run more than two minutes (a search, a sweep, "
        "a batch of seeds), in place of running it with bash. Clank runs it in the folder, detached, its output in a "
        "log, for at most minutes (at most your box's). Then end your turn, saying what you expect it to give: Clank "
        "sends its end to this session (its exit code, its time, the last lines of its log) and you go on from there. "
        "One job at a time. Returns where its log is, or why it did not start.",
        {"command": {"type": "string", "description": "The command, as you would run it in bash, in the folder."},
         "title": {"type": "string", "description": "What it computes, in a few words."},
         "minutes": {"type": "integer", "description": "How long it may run before Clank ends it."}},
        ["command", "title", "minutes"], False,
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
    elif name == "flow_decide":  # as the model gave it: the service says what to fix
        found = _gateway("POST", "flows/decide", {"workspace": WORKSPACE_NAME, **arguments}, "a flow")
    elif name == "flow_job":
        body = {"workspace": WORKSPACE_NAME, "command": str(arguments.get("command") or ""),
                "title": str(arguments.get("title") or ""), "minutes": arguments.get("minutes") or 0}  # fmt: skip
        found = _gateway("POST", "flows/job", body, "a flow")
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


def find(arguments: dict[str, Any]) -> str:
    """The figures of the folder best matching the words, found in the container (`find_figures.py`)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    finder = importlib.import_module("find_figures")  # its neighbor, copied beside it into the container
    limit = arguments.get("limit")
    return str(finder.find(WORKSPACE, str(arguments.get("query") or ""), int(limit) if limit else 5))


def jobs(name: str, arguments: dict[str, Any]) -> str:
    """One of the job tools (design 0021 §6): its request to the gateway, and the answer in words."""
    if not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    number = arguments.get("job")
    named = {"job": int(number)} if number not in (None, "") else {}
    if name == "run_job":
        command, title = str(arguments.get("command") or ""), str(arguments.get("title") or "")
        body = {"workspace": WORKSPACE_NAME, "command": command, "title": title,
                "minutes": int(arguments.get("minutes") or 240)}  # fmt: skip
        return str(_gateway("POST", "agents/jobs", body, "your jobs").get("said") or "")
    if name == "job_stop":
        return str(_gateway("POST", "agents/jobs/stop", {"workspace": WORKSPACE_NAME, **named}, "your jobs")["said"])
    found = _gateway("POST", "agents/jobs/status", {"workspace": WORKSPACE_NAME, **named}, "your jobs")
    if named:
        return _job_whole(found)
    return "\n".join(_job_line(each) for each in found.get("jobs") or []) or "No job of this workspace yet."


def _job_line(job: dict[str, Any]) -> str:
    """A job in a line: its number, title, state and how long."""
    ran = _span(float(job.get("seconds") or 0))
    state = f"ended, {job.get('said')}, after {ran}" if job.get("state") == "ended" else f"{job.get('state')} for {ran}"
    return f"Job {job.get('job')} ({job.get('title')}): {state}. Its log: {job.get('folder')}/log."


def _job_whole(job: dict[str, Any]) -> str:
    """A job whole: its line, its log's last lines and the files it wrote."""
    tail = str(job.get("tail") or "")
    log = f"The last lines of its log:\n```\n{tail}\n```" if tail else "Its log is empty so far."
    files = job.get("written") or []
    wrote = "Files written in the folder since it started: " + ", ".join(files) + "." if files else ""
    return "\n".join(part for part in (_job_line(job), log, wrote) if part)


def _span(seconds: float) -> str:
    """A length of time in words: 40 seconds, 12 minutes, 2 hours 5 minutes."""
    whole = max(0, round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, rest = divmod(rest, 60)

    def unit(count: int, word: str) -> str:
        return f"{count} {word}{'' if count == 1 else 's'}"

    if hours:
        return unit(hours, "hour") + (f" {unit(minutes, 'minute')}" if minutes else "")
    return unit(minutes, "minute") if minutes else unit(rest, "second")


def artifact(arguments: dict[str, Any]) -> str:
    """Make an artifact (design 0021 §5): the request to the gateway, and the service's words."""
    if not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    files = arguments.get("files") or []
    named = [files] if isinstance(files, str) else [str(each) for each in files]
    body = {"workspace": WORKSPACE_NAME, "name": str(arguments.get("name") or ""),
            "title": str(arguments.get("title") or ""), "kind": str(arguments.get("kind") or "html"),
            "files": named, "note": str(arguments.get("note") or "")}  # fmt: skip
    return str(_gateway("POST", "agents/artifacts", body, "artifacts").get("said") or "")


def show(arguments: dict[str, Any]) -> str:
    """Open files in the owner's VS Code window: the request to the gateway, and the service's words."""
    if not WORKSPACE_NAME:
        raise ValueError(
            "this server does not know its workspace (Clank gives it one): start the agent again from Clank"
        )
    paths = arguments.get("paths") or []
    named = [paths] if isinstance(paths, str) else [str(each) for each in paths]
    body = {"workspace": WORKSPACE_NAME, "paths": named, "why": str(arguments.get("why") or "")}
    found = _gateway("POST", "agents/show", body, "the owner's VS Code window")
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
    """The vision model's reading, or, past `ANSWER_SECONDS`, that it is still reading (the reading kept for the same
    image and question asked again)."""
    if not GATEWAY:
        return "(no vision model: Clank gave this server no gateway)"
    key = (hashlib.sha256(data).hexdigest(), question.strip())
    reading = READINGS.get(key)
    if reading is None:
        reading = READINGS[key] = READERS.submit(_read, data, kind, question)
    try:
        said = reading.result(timeout=ANSWER_SECONDS)
    except concurrent.futures.TimeoutError:
        return STILL_READING
    READINGS.pop(key, None)
    return said


def _read(data: bytes, kind: str, question: str) -> str:
    """Ask the vision model about the image; its answer, or why it gave none."""
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
        result = {
            "tools": [TOOL, LOOK, SHOW, FIND, *_notion_tools(), *FLOW_TOOLS, *_job_tools(), ARTIFACT, *BOARD_TOOLS]
        }
    elif method == "tools/call":
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        names = {TOOL["name"], LOOK["name"], SHOW["name"], FIND["name"], ARTIFACT["name"]}
        names |= {tool["name"] for tool in [*_notion_tools(), *FLOW_TOOLS, *_job_tools(), *BOARD_TOOLS]}
        if params.get("name") not in names:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": -32602, "message": "no such tool"}}
        path = str(arguments.get("path") or "")
        try:
            if str(params.get("name")).startswith("notion_"):
                text, failed = notion(str(params["name"]), arguments), False
            elif params.get("name") == ARTIFACT["name"]:
                text, failed = artifact(arguments), False
            elif str(params.get("name")).startswith("board_"):
                text, failed = board(str(params["name"]), arguments), False
            elif str(params.get("name")) in ("run_job", "job_status", "job_stop"):
                text, failed = jobs(str(params["name"]), arguments), False
            elif str(params.get("name")).startswith("flow_"):
                text, failed = flow(str(params["name"]), arguments), False
            elif params.get("name") == FIND["name"]:
                text, failed = find(arguments), False
            elif params.get("name") == SHOW["name"]:
                text, failed = show(arguments), False
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
