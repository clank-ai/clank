"""The Workspaces page (design 0004 §3, §10; built 2026-10-15): every workspace, its container, and what its agent has.

A line a workspace: its name, its container's state, its software (installed or not) and its folder; a workspace whose
running container is cut off from the model (the edge not running on its network, design 0004 §3) says `cut off` in
place of its state, in the failed color. The highlighted workspace shows whole: its folder and container, its limits,
what is wrong with its way to the model and what Clank does about it (the service's words, `edge_said`), its container's
CPU and memory now (the machine's meters read them from Docker every ten seconds), its software and the command that
installs it, and the MCP servers its agent gets. `o` opens it (its container starts; made first when it is not there),
`x` stops its container, `e` installs its software (a form with the command to change or take), `d` removes it (asked
first: its container and home go, its folder stays). The list is read again when Docker or an operation changes, and `r`
reads it now.

Its panels are board E15's (design 0011 §8): "Workspaces", the list, with how many there are and run as its note, and
"The highlighted workspace", with its name as note.
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.form import Field, FormScreen
from clank.console.gauges import size
from clank.console.keys import PageKey
from clank.console.lists import refill
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.text import count, painted

NAME = 18
STATE = 12
REFRESHED_BY = {"all", "docker", "operations", "connection"}
CUT = "cut off"  # a running workspace's state while the edge does not run on its network
NONE = "No workspace yet: clank in a folder (F4, o)."  # the list's panel says it while there is none


def shown_state(row: dict[str, Any]) -> str:
    """A workspace's state as its line shows it: its container's, or `cut off` while it runs cut off from the model."""
    return CUT if row.get("edge") == "cut" else str(row["state"])


def workspace_line(row: dict[str, Any]) -> str:
    """One workspace: its name, its container's state (`cut off` when cut off from the model), its software, its
    folder."""
    setup = row.get("setup") or {}
    if setup.get("command") is None:
        software = "nothing to install"
    else:
        software = "software installed" if setup.get("installed") else "software not installed"
    return f"{row['name']:<{NAME}} {shown_state(row):<{STATE}} {software:<22} {row['path']}"


def workspace_detail(
    row: dict[str, Any], usage: dict[str, Any] | None, servers: list[dict[str, Any]] | None
) -> list[str]:
    """A workspace whole: its folder and container, limits, use now, software and MCP servers."""
    limits = []
    limits.append(f"{row['cpus']:g} CPUs" if row.get("cpus") else "half of Docker's CPUs")
    limits.append(f"{row['memory_mib']:,} MiB" if row.get("memory_mib") else "a quarter of Docker's memory")
    lines = [
        f"{row['name']}: {row['path']} at /workspace",
        f"container {row['container']}: {row['state']} · limits {', '.join(limits)}",
    ]
    if row.get("edge_said"):
        lines.append(str(row["edge_said"]))
    if usage is not None:
        lines.append(
            f"using now: {usage['cpu']:.0f}% of the machine's CPU, {size(usage['memory_used'])} of "
            f"{size(usage['memory_total'])} memory"
        )
    setup = row.get("setup") or {}
    if setup.get("command") is None:
        lines.append("software: nothing to install (no pyproject.toml or requirements.txt; e gives a command)")
    elif setup.get("installed"):
        lines.append(f"software: installed with {setup['command']}")
    else:
        lines.append(f"software: not installed (e installs it with {setup['command']})")
    if servers is None:
        lines.append("MCP servers: being read")
    elif not servers:
        lines.append("MCP servers: none (F3 adds yours; a folder's .mcp.json offers its own)")
    else:
        given = [server["name"] for server in servers if server["given"]]
        held = [f"{server['name']} ({server['why']})" for server in servers if not server["given"]]
        lines.append(f"MCP servers its agent gets: {', '.join(given) or 'none'}")
        if held:
            lines.append(f"not given: {'; '.join(held)}")
    return lines


class WorkspacesPage(Page):
    """Every workspace, its container, and what its agent has."""

    ENTRY = MenuEntry(
        "workspaces",
        "Workspaces",
        "Every workspace: its container's state and use, its software and its agent's MCP servers; o opens, x stops, "
        "e installs the software, d removes.",
        "design 0004 §3, §10",
        key="F6",
    )
    PANELS = ("workspaces-list-panel", "workspaces-highlighted")
    KEYS = (
        PageKey("o", "open", "opens"),
        PageKey("x", "stop", "stops"),
        PageKey("e", "software", "installs its software"),
        PageKey("d", "remove", "removes"),
        PageKey("r", "read", "reads again"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rows: list[dict[str, Any]] = []
        self.servers: dict[str, list[dict[str, Any]]] = {}

    def badge(self, frame: int) -> Content | None:
        """How many workspaces run, in green."""
        running = sum(1 for row in self.rows if row["state"] == "running")
        return Content.assemble((str(running), "$clank-good")) if running else None

    def compose(self) -> ComposeResult:
        """The workspaces, then the highlighted one whole."""
        with Panel(title="Workspaces", id="workspaces-list-panel"):
            none = Label(NONE, id="workspaces-none")
            none.display = False  # until the first read says there is none
            yield none
            yield ListView(id="workspaces-list")
        with Panel(title="The highlighted workspace", id="workspaces-highlighted"):
            yield Label(id="workspace-detail")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read the workspaces again when Docker or an operation changed; the use shown follows the meters."""
        if changed & REFRESHED_BY:
            self._read()
        elif "meters" in changed:
            self._detail()

    def press(self, key: str) -> bool:
        """The page's keys, on the highlighted workspace."""
        selected = self._selected()
        if key == "r":
            self._read()
            return True
        if selected is None or key not in ("o", "x", "e", "d"):
            return False
        client, name, folder = self.console.client, selected["name"], selected["path"]
        if key == "o":
            body = {"folder": folder, "yes": False}
            actions.call(self.console, lambda: client.post("workspaces/open", body), done=f"opening {name}",
                         finished=f"{name} is open")  # fmt: skip
        elif key == "x":
            actions.call(self.console, lambda: client.post(f"workspaces/{name}/stop"), done=f"stopping {name}",
                         finished=f"{name} is stopped")  # fmt: skip
        elif key == "d":
            body = {"yes": False}
            asked = f"removing {name}: it asks first (Questions, 2)"
            actions.call(self.console, lambda: client.post(f"workspaces/{name}/remove", body), done=asked,
                         finished=f"{name} is removed")  # fmt: skip
        else:
            self._setup_form(selected)
        return True

    def explain(self) -> tuple[str, list[str]]:
        """What a workspace is, and what the keys do."""
        return "Workspaces", [
            "A workspace is a folder an agent works in, in a container of its own: the container sees the folder at "
            "/workspace and nothing else of the machine, and reaches nothing but the model (design 0004 §3).",
            "o opens the highlighted workspace (its container starts; it is made first when it is not there); x "
            "stops its container; d removes it, asked first: its container and its home (the agent's settings and "
            "sessions) go, its folder stays as it is.",
            "e installs the folder's own software into the workspace's home (~/.venv), where the agent finds it: the "
            "command is proposed from the folder's pyproject.toml or requirements.txt, and kept once you change it; it "
            "runs in a container of its own that reaches the internet (design 0004 §10).",
            "The highlighted workspace's use (CPU and memory) comes from Docker, read every ten seconds; its MCP "
            "servers are chosen on This folder (F4, m) or with clank mcp allow|hold.",
            "A workspace cut off shows so in place of its state: its container runs, but the edge, its only way to the "
            "model, does not run on its network. Clank puts it back within seconds, and o or starting its agent does "
            "it at once; the highlighted workspace says what is wrong.",
        ]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted workspace whole."""
        if event.list_view.id == "workspaces-list":
            self._detail()

    def _read(self) -> None:
        if not self.display:
            return
        client = self.console.client

        def work() -> None:
            try:
                rows = client.get("workspaces")
                servers = {row["name"]: client.get("agents/servers", workspace=row["name"])["servers"] for row in rows}
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show, rows, servers)

        self.run_worker(work, thread=True, group="workspaces-read", exclusive=True, exit_on_error=False)

    def _show(self, rows: list[dict[str, Any]], servers: dict[str, list[dict[str, Any]]]) -> None:
        listed = self.query_one("#workspaces-list", ListView)
        kept = self._selected()
        self.rows, self.servers = rows, servers
        lines = [painted(workspace_line(row), shown_state(row)) for row in rows]
        refill(listed, lines, [row["name"] for row in rows], kept["name"] if kept else None)
        running = sum(1 for row in rows if row["state"] == "running")
        note = f"{count(len(rows), 'workspace')}, {running} running" if rows else ""
        self.query_one("#workspaces-list-panel", Panel).note = note
        self.query_one("#workspaces-none", Label).display = not rows
        self._detail()

    def _selected(self) -> dict[str, Any] | None:
        index = self.query_one("#workspaces-list", ListView).index
        if index is None or not 0 <= index < len(self.rows):
            return self.rows[0] if self.rows else None
        return self.rows[index]

    def _detail(self) -> None:
        selected = self._selected()
        self.query_one("#workspaces-highlighted", Panel).note = selected["name"] if selected else ""
        if selected is None:
            self.query_one("#workspace-detail", Label).update("")
            return
        readings = self.console.data.meters
        boxes = (readings[-1].get("containers") or []) if readings else []
        usage = next((box for box in boxes if box["name"] == selected["name"]), None)
        lines = workspace_detail(selected, usage, self.servers.get(selected["name"]))
        shown = [Content(lines[0]), painted(lines[1], selected["state"]), *(painted(line, CUT) for line in lines[2:])]
        self.query_one("#workspace-detail", Label).update(Content("\n").join(shown))

    def _setup_form(self, selected: dict[str, Any]) -> None:
        setup = selected.get("setup") or {}
        field = Field(
            "command",
            "The command that installs its software, run in the folder (/workspace) with the internet",
            "python3 -m venv --system-site-packages ~/.venv && ~/.venv/bin/python -m pip install -r requirements.txt",
            setup.get("command") or "",
        )
        client, folder, name = self.console.client, selected["path"], selected["name"]

        def given(values: dict[str, str] | None) -> None:
            if values is None or not values["command"]:
                return
            body = {"folder": folder, "command": values["command"], "yes": True}
            actions.call(self.console, lambda: client.post("workspaces/setup", body),
                         done=f"installing {name}'s software: Operations (6) follows it")  # fmt: skip

        note = "It runs in a container of its own that reaches the internet; the agent's never does. Esc closes this."
        self.console.push_screen(FormScreen(f"Install {name}'s software", [field], note), given)
