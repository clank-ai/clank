"""The MCP servers page (F3; the M8.0 plan, design 0004 §10): every MCP server the agent of this folder can use, what
state it is in, and what it offers.

The list has one row per server: its name, where it comes from (built in: Clank's own; yours: added for you everywhere;
project: this folder's `.mcp.json`), its state and its tools. While an agent runs in this folder's workspace the state
is what the agent says (running, stopped, failed); while none runs, on or off (whether it starts with the agent). When
the folder is not a workspace yet, the servers are listed without a state. The highlighted server's details show below:
what starts it (or its address), where it is defined, its secrets by name and last four characters, what its last check
found, and why it is off or failed.

Keys: Enter shows its tools, each with its parameters; `s` starts or stops it (at once in a running agent, and for the
agent's next start); `c` checks it (in the workspace's container when it runs, where the agent runs it; else on this
computer); `a` adds a server in a form; `d` removes one after a question. The page reads the state again every few
seconds while it is on screen, changing only what changed.

Its panels are board E14's (design 0011 §8): "Workspace", "Servers" (the list under its column headings) and
"Details · (the highlighted server)".
"""

import shlex
import time
from collections.abc import Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.components.tools.service import CHECK_SECONDS
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.lists import refill, relabel
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel, WindowPanel
from clank.console.pick import Choice, PickScreen
from clank.console.style import mark
from clank.console.text import time_of

READ_SECONDS = 5.0
FIELDS = [
    Field("name", "Name (letters, digits, - and _)", "myproject"),
    Field("command", "Command line, or the URL of a server that listens", "myproject-mcp --quiet"),
    Field("env", "Environment, KEY=VALUE separated by spaces (or, for a URL, headers: Name: value; ...)", ""),
    Field("scope", "Where: user (yours, everywhere) or project (this folder's .mcp.json)", "user", "user"),
]
SOURCES = {"clank": "built in", "user": "yours", "project": "project"}
COLORS = {"running": "$clank-good", "on": "$clank-now", "failed": "$clank-failed", "needs sign-in": "$clank-attention"}
HEADER = f"  {'NAME':<20} {'SOURCE':<9} {'STATE':<14} TOOLS"
DETAILS = "Details"  # the details' panel's title, and the highlighted server's name after it


def tool_count(server: dict[str, Any]) -> str:
    """How many tools its last check found, or a dash before any check."""
    checked = server.get("checked")
    return str(len(checked["tools"])) if checked else "—"


def server_line(server: dict[str, Any]) -> Content:
    """A server's row: a dot in its state's color, its name, where it comes from, its state, its tools."""
    state = server.get("state") or ""
    color = COLORS.get(state, "dim")
    return Content.assemble(
        (f"{mark('on')} " if state in ("running", "on") else f"{mark('off')} ", color),
        f"{server['name'][:20]:<20} {SOURCES.get(server['scope'], server['scope']):<9} ",
        (f"{state or '—':<14}", color),
        f" {tool_count(server):>5}",
    )


def how(server: dict[str, Any]) -> str:
    """What starts it, or its address."""
    if server.get("transport", "stdio") == "stdio":
        if "command" in server:
            return shlex.join([server["command"], *server.get("args", [])])
        return str(server.get("shown", ""))
    return str(server.get("url") or server.get("shown", ""))


def detail_lines(server: dict[str, Any], zone: Any, with_tools: bool = True) -> list[Content]:
    """The highlighted server, a fact a line: what starts it, where it is defined, its secrets, its last check (and its
    tools, unless `with_tools` is false), and what is wrong."""
    rows: list[tuple[str, str]] = [
        ("Starts with" if server.get("transport", "stdio") == "stdio" else "Address", how(server))
    ]
    if server["scope"] == "clank":
        rows.append(("Defined in", "Clank (send_to_phone: files to your phone)"))
    elif server.get("file"):
        rows.append(("Defined in", server["file"]))
    names = [f"{secret['name'].split('.', 1)[-1]} (ends in {secret['ends']})" for secret in server.get("secrets", [])]
    if names:
        rows.append(("Secrets", ", ".join(names)))
    checked = server.get("checked")
    if checked:
        tools = [tool["name"] for tool in checked["tools"]]
        shown = ", ".join(tools[:4]) + (f", +{len(tools) - 4} more" if len(tools) > 4 else "")
        version = f" {checked['version']}" if checked.get("version") else ""
        when = time_of(checked["time"], zone)
        rows.append(("Server", f"{checked['name'] or server['name']}{version}, checked {when} in {checked['where']}"))
        if with_tools:
            rows.append(("Tools", shown or "none"))
    elif with_tools:
        rows.append(("Tools", "not checked yet: c checks it"))
    lines = [Content.assemble((f"{label:<12}", "dim"), value) for label, value in rows]
    if server.get("problem"):
        lines.append(Content.assemble((f"{'Note':<12}", "dim"), (server["problem"], "$clank-attention")))
    return lines


def tool_lines(server: dict[str, Any]) -> list[Content]:
    """Every tool of its last check: its name, what it does, and its parameters (name, type, required)."""
    checked = server.get("checked")
    if not checked:
        return [Content("Not checked yet: close this and press c to check it.")]
    lines: list[Content] = []
    for tool in checked["tools"]:
        lines.append(Content.assemble((tool["name"], "bold $clank-title")))
        if tool["description"]:
            lines.append(Content("  " + " ".join(tool["description"].split())))
        for parameter in tool.get("parameters", []):
            kind = parameter["type"] or "any"
            need = "required" if parameter["required"] else "optional"
            about = f"  {parameter['description']}" if parameter["description"] else ""
            lines.append(Content.assemble(("    " + f"{parameter['name']:<16}", "bold"),
                                          (f"{kind}, {need}", "dim"), about))  # fmt: skip
        lines.append(Content(""))
    return lines or [Content("It offers no tools.")]


def entry_of(values: dict[str, str]) -> dict[str, Any]:
    """A server's entry from the form: its command line split as a shell would, or its URL."""
    given = values["command"]
    if given.startswith(("http://", "https://")):
        headers = {}
        for pair in filter(None, (part.strip() for part in values["env"].split(";"))):
            name, said, value = pair.partition(":")
            if not said:
                raise ValueError(f"{pair!r} is not a header (Name: value)")
            headers[name.strip()] = value.strip()
        return {"type": "http", "url": given, "headers": headers}
    words = shlex.split(given, posix=True)
    if not words:
        raise ValueError("a server needs its command line, or its URL")
    env = {}
    for pair in shlex.split(values["env"], posix=True):
        key, said, value = pair.partition("=")
        if not said:
            raise ValueError(f"{pair!r} is not KEY=VALUE")
        env[key] = value
    return {"type": "stdio", "command": words[0], "args": words[1:], "env": env}


class ToolsScreen(ModalScreen[None]):
    """A server's tools, each with its parameters, over the console; it scrolls."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "close")]

    def __init__(self, title: str, info: Sequence[Content], tools: Sequence[Content]) -> None:
        super().__init__()
        self.heading = title
        self.info = list(info)
        self.tools = list(tools)

    def compose(self) -> ComposeResult:
        """The server and its tools in a panel titled with the server (design 0011 §7), and how to close it."""
        info = [Label(line) for line in self.info]
        tools = VerticalScroll(*(Label(line) for line in self.tools), id="tools-scroll")
        yield WindowPanel(*info, tools, Label("Esc closes this.", classes="hint"), title=self.heading, id="tools")


class McpServersPage(Page):
    """Every MCP server this folder's agent can use: its state, its tools, and starting or stopping it."""

    ENTRY = MenuEntry(
        "tools",
        "MCP servers",
        "Every MCP server this folder's agent can use, its state and its tools: Enter lists its tools, s starts or "
        "stops it, c checks it, a adds one, d removes one.",
        "the M8.0 plan; design 0004 §10",
        key="F3",
    )
    PANELS = ("mcp-workspace", "mcp-servers", "mcp-detail-panel")
    KEYS = (
        PageKey("enter", "tools", "tools", "list the highlighted server's tools"),
        PageKey("s", "switch", "start or stop"),
        PageKey("c", "check", "check"),
        PageKey("a", "add", "add"),
        PageKey("d", "remove", "remove"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.workspace: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.agents = False

    def compose(self) -> ComposeResult:
        """Where the servers are for, the list, the highlighted one's details, the keys."""
        with Panel(title="Workspace", id="mcp-workspace"):
            yield Label(id="mcp-head")
        with Panel(title="Servers", id="mcp-servers"):
            yield Label(Content.assemble((HEADER, "$clank-quiet")), id="mcp-columns")
            yield ListView(id="mcp-list")
        with Panel(title=DETAILS, id="mcp-detail-panel"):
            yield Label(id="mcp-detail")

    def on_mount(self) -> None:
        """Read now, and every few seconds while on screen."""
        super().on_mount()
        self.set_interval(READ_SECONDS, self._read)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read again when the servers or the workspaces changed."""
        if changed & {"all", "mcp", "connection", "operations"}:
            self._read()

    def press(self, key: str) -> bool:
        """The page's keys."""
        if key == "a":
            self.console.push_screen(FormScreen("Add an MCP server", FIELDS), self._add)
            return True
        server = self._selected()
        if server is None or key not in ("s", "c", "d"):
            return False
        if key == "s":
            self._switch(server)
        elif key == "c":
            self._check(server)
        elif server["scope"] == "clank":
            self.console.say("Clank's own server cannot be removed: s stops it for this folder's agent", True)
        else:
            choices = [
                Choice("remove", f"Remove {server['name']}", "its secrets go with it"),
                Choice("keep", "Keep it"),
            ]
            self.console.push_screen(
                PickScreen(f"Remove {server['name']}?", choices), lambda answer: self._remove(server, answer)
            )
        return True

    def explain(self) -> tuple[str, list[str]]:
        """What the page shows, and what the keys do."""
        server = self._selected()
        lines = [
            "MCP servers give the agent tools: a server runs beside the agent (in the workspace's container) and "
            "offers tools it can call. Built in is Clank's own (send_to_phone); yours are added for you, in every "
            "folder; project ones are this folder's .mcp.json, used once you allow them (s).",
            "State: running, stopped or failed is what the agent running here says; on or off, while no agent runs, "
            "is whether it starts with the agent. s changes it at once in a running agent, and for its next start.",
            "c checks a server: starts it where the agent would, asks for its tools, and ends it. Enter lists the "
            "tools of its last check, with their parameters.",
            "Your servers' environment and header values are secrets, kept in CLANK_HOME/secrets and shown only by "
            "their last four characters.",
        ]
        return (server["name"] if server else "MCP servers"), lines

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted server's details."""
        if event.list_view.id == "mcp-list":
            self._draw_details()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter on a server: its tools."""
        if event.list_view.id == "mcp-list" and (server := self._selected()) is not None:
            self._show_tools(server)

    def _read(self) -> None:
        if not self.display:
            return
        client, folder = self.console.client, self.console.folder

        def work() -> None:
            try:
                workspace = client.get("workspaces/folder", folder=folder)["workspace"]
                listed = client.get("mcp/servers", folder=folder)["servers"]
                rows = client.get("agents/servers", workspace=workspace, live=True)["servers"] if workspace else listed
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show, workspace, rows, listed)

        self.run_worker(work, thread=True, group="mcp-read", exclusive=True, exit_on_error=False)

    def _show(self, workspace: str | None, rows: list[dict[str, Any]], listed: list[dict[str, Any]]) -> None:
        known = {(each["name"], each["scope"]): each for each in listed}
        self.workspace = workspace
        self.rows = [{**known.get((row["name"], row["scope"]), {}), **row} for row in rows]
        self.agents = any(row.get("agents") for row in self.rows)
        if workspace is None:
            head = Content("This folder is not a workspace yet: open it (F4, then o) to give servers to an agent.")
        elif self.agents:
            head = Content.assemble((workspace, "bold"), "  ·  ", ("agent running", "$clank-good"))
        else:
            head = Content.assemble((workspace, "bold"), "  ·  ", ("no agent running", "dim"),
                                    ": the servers that are on start with it")  # fmt: skip
        relabel(self.query_one("#mcp-head", Label), head)
        listed_view = self.query_one("#mcp-list", ListView)
        kept = self._selected()
        lines = [server_line(row) for row in self.rows] or [Content("No MCP server yet: a adds one.")]
        keys = [f"{row['scope']}:{row['name']}" for row in self.rows]
        refill(listed_view, lines, keys, f"{kept['scope']}:{kept['name']}" if kept else None)
        if listed_view.index is None and self.rows:
            listed_view.index = 0
        self._draw_details()

    def _selected(self) -> dict[str, Any] | None:
        index = self.query_one("#mcp-list", ListView).index
        return self.rows[index] if index is not None and 0 <= index < len(self.rows) else None

    def _draw_details(self) -> None:
        server = self._selected()
        self.query_one("#mcp-detail-panel", Panel).title = f"{DETAILS} · {server['name']}" if server else DETAILS
        shown = Content("\n").join(detail_lines(server, self.console.zone)) if server else Content("")
        relabel(self.query_one("#mcp-detail", Label), shown)

    def _show_tools(self, server: dict[str, Any]) -> None:
        title = f"{server['name']}  ·  {SOURCES.get(server['scope'], server['scope'])}"
        self.console.push_screen(ToolsScreen(title, detail_lines(server, self.console.zone, False), tool_lines(server)))

    def _switch(self, server: dict[str, Any]) -> None:
        if self.workspace is None:
            self.console.say("Servers start with an agent: open this folder as a workspace first (F4, then o)", True)
            return
        on = not server.get("given", False)
        body = {"workspace": self.workspace, "name": server["name"], "given": on}
        client, name = self.console.client, server["name"]

        def work() -> None:
            try:
                found = client.post("agents/servers", body)
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            if found.get("problem") and (on and not found.get("given")):
                said, bad = f"{name} is not started: {found['problem']}", True
            elif found.get("applied") == "now":
                said, bad = f"{name} {'started' if on else 'stopped'}", False
            else:
                said, bad = f"{name} is {'on' if on else 'off'}: it applies when the agent starts", False
            self.console.call_from_thread(self.console.say, said, bad)
            self.console.call_from_thread(self._read)

        self.console.say(f"{'starting' if on else 'stopping'} {name}")
        self.run_worker(work, thread=True, group="mcp-switch", exit_on_error=False)

    def _add(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        try:
            entry = entry_of(values)
        except ValueError as error:
            self.console.say(str(error), True)
            return
        scope = values["scope"] or "user"
        body = {"name": values["name"], "scope": scope, "folder": self.console.folder, "entry": entry}
        actions.call(
            self.console, lambda: self.console.client.post("mcp/servers", body), done=f"added {values['name']}"
        )

    def _remove(self, server: dict[str, Any], answer: str | None) -> None:
        if answer != "remove":
            return
        params = {"folder": self.console.folder, "scope": server["scope"]}
        path = f"mcp/servers/{server['name']}"
        actions.call(self.console, lambda: self.console.client.delete(path, **params), done=f"removed {server['name']}")

    def _check(self, server: dict[str, Any]) -> None:
        name = server["name"]
        body: dict[str, Any] = {"folder": self.console.folder, "scope": server["scope"]}
        if self.workspace and (self.agents or server["scope"] in ("clank", "project")):
            body["workspace"] = self.workspace
        if server["scope"] == "clank" and "workspace" not in body:
            self.console.say("Clank's own server runs in a workspace: open this folder as one first (F4, then o)", True)
            return

        def work() -> None:
            client = self.console.client
            try:
                started = client.post(f"mcp/servers/{name}/check", body)
                done = started
                deadline = time.monotonic() + CHECK_SECONDS + 30
                while done["status"] not in ("done", "failed", "canceled") and time.monotonic() < deadline:
                    time.sleep(0.25)
                    done = client.get(f"records/operation/{started['id']}")["values"]
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            if done["status"] == "done":
                count = len(done["result"]["tools"])
                self.console.call_from_thread(
                    self.console.say, f"{name} answers, with {count} tools (Enter lists them)"
                )
            else:
                self.console.call_from_thread(self.console.say, f"{name}: {done.get('error') or done['status']}", True)
            self.console.call_from_thread(self._read)

        where = f"in {self.workspace}'s container" if "workspace" in body else "on this computer"
        self.console.say(f"checking {name} {where}: starting it and asking for its tools")
        self.console.run_worker(work, thread=True, group="calls", exit_on_error=False)
