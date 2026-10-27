"""The console's page for the folder clank was started in (design 0004 §1 and §4): getting ready to work there, step by
step, and then working.

"Get ready to work here" is a numbered list: Docker, this folder (refused when its container would see more than it,
saying why), its workspace (its container running), Clank's sandbox image, its software (design 0004 §10: the folder's
own packages, installed into the workspace's home; offered, not required), a model in the main slot, and the gateway.
Each step says what it is now (green when done, red when not, yellow while it changes) and, when it is not done, the key
that does it: `s` starts Docker, `o` opens the workspace (it makes the record, builds the image the first time, asked
first, and starts the container), `e` installs the software (a form with the command, proposed or kept, to change or
take), `l` loads a model picked from the presets (the slot's last that worked first), and `g` does every step that is
not done, in order. A running workspace cut off from the model (the edge not running on its network, design 0004 §3)
says so in the service's words, in yellow: Clank puts it right within seconds, and `o` or the agent's start does at
once, so it does not hold `a` back. The line under the list says what to press next. "Then work" says how to start: `a`
starts OpenCode in this terminal once every required step is done (the console steps aside while it runs and comes back
when it is left: `clank.console.terminal`), with the model it will be given and that model's limits (and, after a flow's
box switched the main slot, that the window's model changed, until OpenCode next starts here: design 0013 §7), and lists
the MCP servers: whether the agent gets each (yours unless taken away, the folder's own once allowed) and its tools once
checked; `m` gives one or takes it away, and checks one given in the workspace's container. `f` builds a flow with the
model (design 0013 §15, decision 0100; `f`, since `n` answers a question here): it brings the console to the Monitor's
Flow view, which opens the planning beside the console as its own `n` does and shows the flow built. `c` does every step
not done, then opens VS Code on the folder: Clank's window on the PC, or over SSH (design 0018 §8) the other computer's
from a terminal of VS Code's Remote-SSH, else nothing opens and the command to run there is said.

A step started here is followed here: the step being worked on has a turning spinner in place of its mark, its
operation's step and last line show under "What runs from here" (with the spinner too), and its end, or why it failed,
on the message line. The first question waiting (an image's build asks one) shows on the page too, under "Waiting for
you", answered with its options' keys (`v` shows it whole). What the page reads besides the console's own data (the
folder's workspace and image, the gateway, the agent's plan) is read off the screen's thread, every few seconds while
the page is on screen and when Docker, the slots, the presets, the operations or the MCP servers change.

With a cloud model (design 0016 §9, §10, §15; decision 0112): the model's step says it runs at OpenRouter; `a` first
asks the service whether this workspace may use it (`POST /workspaces/{name}/cloud/ask`): when it was never answered,
its question opens in a window (`y` allows, `n` keeps it local; a workspace that existed before the cloud was agreed
says so first), and the agent starts once allowed, or the page says why not and how to allow it. "Then work" says the
workspace's bound once a provider is added, `u` changing it (asked first; `c` stays VS Code's), the MCP servers held
back from a workspace allowed the cloud (marked local only), and what its sessions cost today.

Its four panels are board E2's (design 0011 §8): "Get ready to work here"; "Then work" beside "What runs from here", two
fifths of the row, the two stacked when the row is narrower than `STACK_BELOW` columns; and "Waiting for you", which
says nothing waits with the style's done mark.

Its keys are buttons where its panels say what to do (board K2, design 0011 §12): under the steps a row leads with
"Next:" and the key of the first step not done, and `g` when more are, or "Ready:" and the ways to start (`next_keys`);
Then work holds a column of the ways to start working (`WAYS`: `a`, `c`, `f`) above what the agent will be given, and
the row of its settings under it (`SETTINGS`, and `u` once a cloud provider is added); the first question's options are
a row under it. Each is one of the page's declared keys (`KEYS`), pressed through the console's one door. `a` cannot act
until every required step is done, nor the keys that work on the workspace (`WORKSPACE_FIRST`) until it is opened
(`unable`): their buttons are dimmed, and the key, typed or pressed, says why.
"""

import json
import os
import time
from collections.abc import Callable
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.client import ClientError, NotRunning
from clank.components.agents.console.monitor import MonitorPage
from clank.console import terminal
from clank.console.ask import AskScreen
from clank.console.buttons import Buttons, from_keys
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.form import Field, FormScreen
from clank.console.gauges import fit, spinner
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.pages.questions import answer, details, option_buttons, question_lines
from clank.console.panel import Panel, PanelGrid
from clank.console.pick import Choice, PickScreen, preset_choices
from clank.console.rows import Rows
from clank.console.style import mark
from clank.console.text import painted
from clank.kernel import where as places

DEFAULT_PRESET = "daily-262k"
READ_SECONDS = 5.0
POLL_SECONDS = 0.5
FINISHED = ("done", "failed", "canceled", "interrupted")
MODEL_SECONDS = 600.0  # how long a model already starting is waited for
STEPS = ("docker", "workspace", "setup", "model", "gateway")
KEYS = {"docker": "s", "workspace": "o", "setup": "e", "model": "l", "gateway": "g"}
DOING = {
    "s": "start Docker", "o": "open the workspace", "e": "install the folder's software", "l": "load a model",
    "g": "start the gateway",
}  # fmt: skip
OPTIONAL = {"its software"}  # a step the agent can start without (it is offered, not required)
REFRESHED_BY = {"all", "docker", "slots", "presets", "operations", "mcp", "connection", "endpoints"}
ANSWERED = "workspaces.cloud_answered"  # a workspace's bound changed, from any client: read again
NAME = 18
REASON = 60  # a stopped slot's reason, cut: the Models page shows it whole
SERVER = 14  # an MCP server's name, padded
ROWS = {
    "docker": "Docker", "workspace": "Its workspace", "setup": "Its software", "model": "A model",
    "gateway": "The gateway",
}  # fmt: skip
Step = tuple[str, str, bool | None, str]  # its name, what it is now, done (None: not known yet), the key that does it
MENDED = ("cut", "stale")  # a running workspace's way to the model as the service says it, put right by o or by `a`


def slot_text(data: ConsoleData) -> tuple[str, bool]:
    """The main slot: what it runs and whether it is ready."""
    main = next((slot for slot in data.slots if slot["name"] == "main"), None)
    if main is None:
        return "not read yet", False
    titles = {preset["id"]: preset["title"] for preset in data.presets}
    title = titles.get(main["preset"] or "", main["preset"] or "")
    cloud = any(preset["id"] == main["preset"] and preset.get("endpoint") for preset in data.presets)
    if main["status"] == "ready":
        return f"ready: {title} in the main slot" + (" · cloud, at OpenRouter" if cloud else ""), True
    if main["status"] in ("starting", "stopping"):
        return f"{main['status']}: {title} in the main slot", False
    return f"none is loaded ({fit(main['reason'], REASON)})", False


def checklist(data: ConsoleData, view: dict[str, Any] | None, gateway: dict[str, Any] | None) -> list[Step]:
    """Each step of getting ready to work in the folder, in order."""
    docker = data.docker["state"] if data.docker else ""
    steps: list[Step] = [("Docker", docker or "not read yet", (docker == "running") if docker else None, "s")]
    if view is None:
        steps += [("This folder", "being read", None, ""), ("Its workspace", "being read", None, "o")]
    elif view["problem"]:
        steps += [
            ("This folder", f"refused: {view['problem']}", False, ""),
            ("Its workspace", "cannot open", False, ""),
        ]
    else:
        steps.append(("This folder", "ready: it can be a workspace", True, ""))
        if view["workspace"] is None:
            steps.append(("Its workspace", "not opened yet", False, "o"))
        elif view["state"] == "running" and view.get("edge") in MENDED:
            steps.append(("Its workspace", str(view["edge_said"]), None, "o"))  # its agent's start mends it first
        elif view["state"] == "running":
            told = f"; {view['edge_said']}" if view.get("edge_said") else ""
            steps.append(("Its workspace", f"running: {view['workspace']}, its container up{told}", True, "o"))
        else:
            steps.append(("Its workspace", f"stopped: {view['workspace']}, its container {view['state']}", False, "o"))
    image = view["image"] if view is not None else None
    if image is None or image["built"] is None:
        steps.append(("The sandbox image", "not read yet: Docker must run", None, ""))
    elif image["built"] and image.get("current") is False:
        steps.append(
            ("The sandbox image", "built; the workspace moves to it when next opened (F6: x, then o)", True, "")
        )
    elif image["built"]:
        steps.append(("The sandbox image", f"built: {image['tag']}", True, ""))
    elif image.get("current") is False:
        steps.append(("The sandbox image", "a newer one: o builds it (the workspace keeps running)", False, "o"))
    else:
        steps.append(("The sandbox image", "not built yet: opening the workspace builds it (once)", False, "o"))
    steps.append(software_step(view))
    model, ready = slot_text(data)
    steps.append(("A model", model, ready, "l"))
    if gateway is None:
        steps.append(("The gateway", "being read", None, "g"))
    elif gateway["state"] == "running":
        steps.append(("The gateway", f"running on port {gateway['port']}", True, "g"))
    else:
        problem = f": {gateway['problem']}" if gateway.get("problem") else ""
        steps.append(("The gateway", f"stopped{problem}", False, "g"))
    return steps


def software_step(view: dict[str, Any] | None) -> Step:
    """The folder's own software: nothing to install, installed with what, or the command `e` installs it with."""
    setup = view.get("setup") if view is not None else None
    if view is None:
        return ("Its software", "being read", None, "e")
    if setup is None:
        return ("Its software", "cannot install: this folder is refused", False, "")
    if setup["command"] is None:
        return ("Its software", "nothing to install (no pyproject.toml or requirements.txt)", True, "")
    if setup["installed"]:
        return ("Its software", f"installed: {setup['command']}", True, "e")
    return ("Its software", f"not installed: {setup['command']}", False, "e")


def server_lines(servers: list[dict[str, Any]] | None, checked: dict[str, str], workspace: str | None) -> list[Content]:
    """The MCP servers the agent gets or not, each with its tools once checked, or why it is not given; one the service
    holds back from a workspace allowed the cloud says so in its words (design 0016 §10)."""
    if workspace is None:
        return [Content("    MCP servers: open the workspace (o) to choose which its agent gets")]
    if servers is None:
        return [Content("    MCP servers: being read")]
    if not servers:
        return [Content("    MCP servers: none (F3 adds yours; a folder's .mcp.json offers its own)")]
    lines = [Content("    MCP servers (m gives one to the agent or takes it away):")]
    for server in servers:
        sign = mark("done") if server["given"] else mark("failed")
        whose = {"user": "yours", "clank": "Clank's (send_to_phone)"}.get(server["scope"], "this folder's")
        said = checked.get(server["name"], "") if server["given"] else server["why"]
        if server.get("held"):  # the service's word: held back from a workspace allowed the cloud
            sign, said = mark("failed"), str(server.get("held_said") or "held back")
        line = f"      {sign} {server['name']:<{SERVER}} {whose}: {server['shown']}" + (f" · {said}" if said else "")
        lines.append(painted(line, sign))
    return lines


def host_line(view: dict[str, Any] | None) -> Content | None:
    """The hosts the workspace's agent may reach through Clank's proxy (design 0024 §1, §4), and `h`; none without a
    workspace."""
    if view is None or not view.get("workspace"):
        return None
    hosts = sorted(view.get("hosts") or {})
    if not hosts:
        return Content("Hosts its agent reaches: none (h allows a set or a host; one it needs, it may ask you for)")
    return Content(f"Hosts its agent reaches: {', '.join(hosts)} (h allows a set or a host, or takes one back)")


def review_line(review: dict[str, Any]) -> Content:
    """The workspace's mode for the agent's changes, what it means, and why its agent is not followed when it is not
    (design 0007)."""
    if review.get("shown") == "plan":
        said = Content.assemble(("plan", "$clank-box-plan"), ": the Planner writes plans in Markdown, no code, no runs "
                                f"(r: back to {review['mode']}; i hands a plan over)")  # fmt: skip
    elif review["mode"] == "auto":
        said = Content.assemble(("auto", "$clank-attention"), ": the agent changes files without asking; VS Code shows "
                                "each change after (r: review, p: plan)")  # fmt: skip
    else:
        said = Content.assemble(("review", "$clank-good"), ": the agent asks before it changes a file; VS Code shows "
                                "the change to accept or reject (r: auto, p: plan)")  # fmt: skip
    if review.get("waiting"):
        count = review["waiting"]
        said = Content.assemble(said, (f" · {count} waiting" if count > 1 else " · 1 waiting", "$clank-attention"))
    if review.get("problem"):
        said = Content.assemble(said, "\n", (review["problem"], "dim"))
    return said


def window_line(review: dict[str, Any]) -> Content:
    """Whether the workspace has one OpenCode window at a time (design 0004 §5), and what that means."""
    if review.get("one_window", True):
        return Content.assemble(("one OpenCode window", "$clank-good"), ": opening one closes the one open, so p and r "
                                "always reach it (w: several)")  # fmt: skip
    return Content.assemble(("several OpenCode windows", "$clank-attention"), ": opening one adds another; p and r "
                            "reach the one that last answered (w: one)")  # fmt: skip


STEP_WIDTH = NAME + 5  # a step's number and name, the column its state wraps beside
SERVER_INDENT = 4  # the indent `server_lines` writes, which Then work leaves for its own (`WORK_INDENT`)
WORK_INDENT = 3  # what working here gives the agent stands under the words of the buttons above it
WAYS = (  # Then work's column of buttons (board K2): its keys, with the panel's own words
    ("a", "OpenCode in this terminal; the menu comes back when you leave it"),
    ("c", "VS Code on this folder, OpenCode beside your files (it gets every step above done first)"),
    ("f", "a flow built with the model, OpenCode beside this console: the Flow view shows it built"),
)
SETTINGS = ("m", "h", "p", "r", "w", "i")  # the row of Then work's settings under it (board K2)
WORKSPACE_FIRST = {  # the keys that work on the folder's workspace, and what each would do there
    "e": "its software is installed into its home",
    "m": "its agent's MCP servers are chosen for it",
    "h": "the hosts its agent reaches are its own",
    "p": "how the agent works is set for it",
    "r": "how the agent works is set for it",
    "w": "its windows are its own",
    "i": "its plans are handed to its agent",
    "u": "its bound is its own",
}
COLUMNS = "3fr 2fr"  # Then work beside What runs from here, two fifths of the row (board E2: 38%)
STACK_BELOW = 80  # side by side at 120 and 170 columns (88 and 92 for the row), stacked at 130 and 80 (58 and 56)


def checklist_rows(steps: list[Step], active: str = "", frame: int = 0) -> list[tuple[str, Content]]:
    """The steps as the page shows them, a row each: its number and name; then a mark, what it is now, and the key when
    it is not done (wrapping beside the name, `console/rows.py`). The step named `active`, being worked on, has the
    spinner's glyph for `frame` and says so."""
    rows = []
    for number, (name, now, done, key) in enumerate(steps, 1):
        head = f" {number}  {name}"
        if name == active:
            rows.append((head, Content.assemble((f"{spinner(frame)} working on it…", "$clank-now"))))
            continue
        sign = mark("done") if done else (mark("cut") if done is None else mark("failed"))
        press = f"   press {key} to {DOING[key]}" if done is False and key in DOING else ""
        rows.append((head, painted(f"{sign} {now}{press}", sign, now.split(":")[0])))
    return rows


def missing(data: ConsoleData, view: dict[str, Any] | None, gateway: dict[str, Any] | None) -> list[tuple[str, str]]:
    """What must be done before the agent can start, each with its key ("" when no key can do it)."""
    if not data.connected:
        return [("the Clank service", "")]
    running = view is not None and view.get("state") == "running"  # the agent's start puts its edge right first
    return [
        (name.lower(), key)
        for name, _, done, key in checklist(data, view, gateway)
        if done is not True
        and name != "The sandbox image"  # a running container has its image
        and not (name == "Its workspace" and running)
    ]


def blocking(found: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """What the agent cannot start without (the folder's software is offered, not required)."""
    return [(what, key) for what, key in found if what not in OPTIONAL]


def next_line(found: list[tuple[str, str]]) -> Content:
    """What to press next."""
    if not blocking(found):
        first = " · e installs the folder's software first" if found else ""
        return painted(
            f"Ready: press a to start OpenCode here, or c to open VS Code with OpenCode beside your files{first}.",
            "Ready",
        )
    keys = [(what, key) for what, key in found if key]
    if not keys:
        return painted(f"Not ready: {found[0][0]} cannot be done from here (? says why).", "Not ready")
    what, key = keys[0]
    more = " · or g to do every step that is not done" if len(keys) > 1 else ""
    return Content(f"Next: press {key} to {DOING.get(key, what)}{more}.")


def next_keys(found: list[tuple[str, str]]) -> tuple[str, list[str | tuple[str, str]]]:
    """The row of buttons under the steps (board K2): "Next:" and the key of the first step not done (and `g` when more
    are), or "Ready:" and the ways to start working; no keys when what is missing cannot be done from here (the line
    `next_line` says then why)."""
    if not blocking(found):
        software = [("e", "install the folder's software first")] if found else []
        return "Ready:", [("a", "start OpenCode here"), ("c", "open VS Code, OpenCode beside your files"), *software]
    keys = [key for _, key in found if key]
    if not keys:
        return "", []
    first = keys[0]
    more = ["g"] if len(keys) > 1 and first != "g" else []
    return "Next:", [(first, DOING[first]) if first != "g" else "g", *more]


def readiness(found: list[tuple[str, str]]) -> str:
    """One line for the message line: ready, or what is not, with each key."""
    found = blocking(found)
    if not found:
        return "Ready: a starts OpenCode here; leaving it brings you back to this page."
    items = " · ".join(f"{what} ({key})" if key else what for what, key in found)
    return f"Not ready yet: {items}. g does every step that is not done."


class FolderPage(Page):
    """The folder clank was started in: getting ready to work there, and working."""

    DEFAULT_CSS = f"""
    #folder-work {{
        padding-left: {WORK_INDENT};
    }}
    """

    ENTRY = MenuEntry(
        "folder",
        "This folder",
        "Getting ready to work in the folder clank was started in, step by step (s Docker, o the workspace, e its "
        "software, l a model, g every step; m the agent's MCP servers, h the hosts it may reach), then working there: "
        "a starts OpenCode here, "
        "c opens VS Code with OpenCode beside your files; r switches between reviewing the agent's changes and auto.",
        "design 0004 §1",
        key="F4",
        first=True,
    )
    PANELS = ("folder-items", "folder-work-panel", "folder-runs", "folder-waiting-panel")
    KEYS = (
        PageKey("g", "get_ready", "get everything ready", "get everything ready: every step that is not done, in "
                "order"),
        PageKey("a", "opencode", "OpenCode here", "start OpenCode in this terminal"),
        PageKey("c", "vscode", "in VS Code", "open VS Code with OpenCode beside your files"),
        PageKey("f", "flow", "build a flow", "build a flow with the model: OpenCode beside this console, the Monitor's "
                "Flow view showing it built"),
        PageKey("p", "plan", "plan", "plan with the Planner (Markdown only, no code, no runs)"),
        PageKey("e", "software", "its software", "install the folder's software"),
        PageKey("m", "servers", "MCP servers", "give an MCP server to the agent or take it away"),
        PageKey("h", "hosts", "hosts", "allow the agent a named set of hosts, or a host, or take one back"),
        PageKey("r", "review", "review or auto", "review each change the agent asks for (VS Code shows it), or let it "
                "change files (auto)"),
        PageKey("i", "implement", "implement a plan", "hand a plan to the agent"),
        PageKey("w", "windows", "one window or several", "one OpenCode window at a time, or several"),
        PageKey("u", "cloud", "cloud or local", "let this workspace use the cloud model, or keep it on this machine"),
        PageKey("s", "docker", "start Docker"),
        PageKey("o", "workspace", "open the workspace"),
        PageKey("l", "model", "load a model"),
        PageKey("v", "question", "the question whole", "the first question waiting, shown whole"),
        PageKey("y n …", "answer", "answer it with an option's key", "answer the first question waiting with one of "
                "its options' keys"),
    )  # fmt: skip

    def badge(self, frame: int) -> Content | None:
        """A spinner while its steps run; else a check mark when every required step is done, or a cross and how many
        are not (the folder's software is offered, not counted)."""
        if self.running:
            return Content.assemble((spinner(frame), "$clank-now"))
        if self.view is None:
            return None
        left = len(blocking(missing(self.console.data, self.view, self.gateway)))
        return (
            Content.assemble((mark("done"), "$clank-good"))
            if not left
            else Content.assemble((f"{mark('failed')} {left}", "$clank-attention"))
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.view: dict[str, Any] | None = None
        self.gateway: dict[str, Any] | None = None
        self.plan: dict[str, Any] | None = None
        self.servers: list[dict[str, Any]] | None = None
        self.review: dict[str, Any] | None = None  # the workspace's mode for the agent's changes (design 0007)
        self.checked: dict[str, str] = {}  # a given server's last check here: its tools, or that it failed
        self.cost: dict[str, Any] | None = None  # the workspace's cloud cost, as the service says it (design 0016 §11)
        self.heard = 0  # the last event read for a workspace's answer
        self.progress: list[str] = []
        self.running = False
        self.doing = ""  # the step being worked on, while `running`

    def compose(self) -> ComposeResult:
        """Getting ready, working, what runs, what waits for the user, and the keys."""
        with Panel(title="Get ready to work here", id="folder-items"):
            yield Label(id="folder-path")
            yield Rows(STEP_WIDTH, id="folder-rows")
            yield Label(id="folder-ready")
            yield Buttons(id="folder-next")
        yield PanelGrid(
            Panel(
                Buttons(from_keys(self.KEYS, *WAYS), column=True, id="folder-ways"),
                Label(id="folder-work"),
                Buttons(from_keys(self.KEYS, *SETTINGS), id="folder-settings"),
                title="Then work",
                id="folder-work-panel",
            ),
            Panel(Label(id="folder-progress"), title="What runs from here", id="folder-runs"),
            columns=COLUMNS,
            stack_below=STACK_BELOW,
        )
        with Panel(title="Waiting for you", id="folder-waiting-panel"):
            yield Label(id="folder-waiting")
            yield Buttons(id="folder-waiting-options")

    def on_mount(self) -> None:
        """Draw, read what the console's own data lacks, and read it again every few seconds while on screen."""
        super().on_mount()
        self.set_interval(READ_SECONDS, self._read)

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self.draw(self.console.data, {"folder"})

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """The steps, what to press next, how to work, what runs, and the first question waiting."""
        if changed & REFRESHED_BY or ("history" in changed and self._answered(data)):
            self._read()
        if changed & (REFRESHED_BY | {"folder", "questions"}):
            self.query_one("#folder-path", Label).update(Content(f"Folder: {self.console.folder}"))
            self._draw_running(data, self.console.frame)
            found = missing(data, self.view, self.gateway)
            lead, keys = next_keys(found)
            group = self.query_one("#folder-next", Buttons)
            group.show(from_keys(self.KEYS, *keys), lead=lead)
            group.display = bool(keys)
            ready = self.query_one("#folder-ready", Label)
            ready.update(next_line(found))
            ready.display = not keys
            self.query_one("#folder-ways", Buttons).recheck()
            self.query_one("#folder-work", Label).update(self._work_lines(data))
            cloud = ("u",) if self._cloud_lines(data) else ()  # the workspace's bound, once a provider is added
            self.query_one("#folder-settings", Buttons).show(from_keys(self.KEYS, *SETTINGS, *cloud))
            waiting = question_lines(data.questions[0], self.console.zone)[:-1] if data.questions else []
            nothing = Content.assemble((mark("done"), "$clank-good"), " No question waits.")
            self.query_one("#folder-waiting", Label).update(Content("\n".join(waiting)) if waiting else nothing)
            options = self.query_one("#folder-waiting-options", Buttons)
            options.show(option_buttons(data.questions[0], self.KEYS) if data.questions else [])
            options.display = bool(data.questions)

    @property
    def busy(self) -> bool:
        """Whether the page works on its steps."""
        return self.running

    def spin(self, frame: int) -> None:
        """Turn the spinners of the step being worked on and of what runs."""
        self._draw_running(self.console.data, frame)

    def _draw_running(self, data: ConsoleData, frame: int) -> None:
        """The steps, the one being worked on spinning, and what runs."""
        active = ROWS.get(self.doing, "") if self.running else ""
        self.query_one("#folder-rows", Rows).show(
            checklist_rows(checklist(data, self.view, self.gateway), active, frame)
        )
        if self.progress:
            first, *rest = self.progress
            shown = Content.assemble((spinner(frame), "$clank-now"), f" {first}", *(f"\n{line}" for line in rest))
        elif self.running:
            shown = Content.assemble((spinner(frame), "$clank-now"), " checking what is ready")
        else:
            shown = Content("Nothing runs from here.")
        self.query_one("#folder-progress", Label).update(shown)

    def _work_lines(self, data: ConsoleData) -> Content:
        """What working here gives the agent, under the ways to start it (buttons, `WAYS`) and above its settings
        (buttons, `SETTINGS`): how it changes files, its windows, its model and limits, its bound and cost with a cloud
        provider, its MCP servers; drawn under the buttons' words (`WORK_INDENT`), each line wrapping under itself."""
        lines: list[Content] = []
        if self.review is not None and self.review.get("workspace"):
            lines += [review_line(self.review), window_line(self.review)]
        if self.plan is not None:
            limits = self.plan["limits"]
            kept = limits.get("margin") or 0
            whose = f" (the engine's {limits['window']:,} less {kept:,} kept for a step's tool results)" if kept else ""
            sizes = f"{limits['context']:,} tokens of context{whose}, {limits['output']:,} out"
            lines.append(Content(f"OpenCode will use {self.plan['model']}: {sizes}"))
        changed = (self.review or {}).get("model_changed")
        if changed:  # a flow's box switched the main slot (design 0013 §7): said until OpenCode next starts here
            lines.append(Content.assemble(("model changed", "$clank-attention"), f": {changed['said']}"))
        lines += self._cloud_lines(data)
        for line in server_lines(self.servers, self.checked, (self.view or {}).get("workspace")):
            lines.append(line[SERVER_INDENT:] if line.plain.startswith(" " * SERVER_INDENT) else line)
        hosts = host_line(self.view)
        if hosts is not None:
            lines.append(hosts)
        return Content("\n").join(lines)

    def unable(self, key: str) -> str:
        """Why a key cannot act now (design 0011 §12.7): `a` until every required step is done, and the keys that work
        on the workspace until it is opened, in the words they say when pressed."""
        if key == "a":
            found = blocking(missing(self.console.data, self.view, self.gateway))
            return readiness(found) if found else ""
        workspace = (self.review or {}).get("workspace") or (self.view or {}).get("workspace")
        if key in WORKSPACE_FIRST and not workspace:
            return f"open the workspace first (o): {WORKSPACE_FIRST[key]}"
        return ""

    def _cloud_lines(self, data: ConsoleData) -> list[Content]:
        """The workspace's bound and what its sessions cost today, in the service's words, once a provider is added;
        `u`, which changes the bound, is then a button of the settings' row."""
        workspace = (self.view or {}).get("workspace")
        if not data.endpoints or not workspace or self.view is None or not self.view.get("cloud_said"):
            return []
        key = "keeps it here" if self.view.get("models") == "cloud" else "allows it"
        lines = [Content(f"{self.view['cloud_said']} (u {key})")]
        own = (self.cost or {}).get("workspace") or {}
        if (own.get("today") or {}).get("requests"):
            lines.append(Content(f"its sessions: {own['today']['said']} (Requests, F7, shows each)"))
        return lines

    def _answered(self, data: ConsoleData) -> bool:
        """Whether a workspace's answer came since the page last looked."""
        fresh = [event for event in data.history if event["id"] > self.heard]
        if data.history:
            self.heard = data.history[-1]["id"]
        return any(event["type"] == ANSWERED for event in fresh)

    def press(self, key: str) -> bool:
        """The page's keys; then the first question's option keys, and `v` for it whole. None while a window is over
        the page: the window takes its own keys."""
        if self.app.screen is not self.screen:
            return False
        actions: dict[str, Callable[[], None]] = {
            "a": self._start_agent,
            "g": lambda: self._run(list(STEPS)),
            "s": lambda: self._run(["docker"]),
            "o": lambda: self._run(["workspace", "image"]),
            "e": self._setup_form,
            "l": self._pick_model,
            "m": self._pick_server,
            "h": self._pick_hosts,
            "c": lambda: self._run([*STEPS, "vscode"]),
            "r": self._switch_review,
            "w": self._switch_windows,
            "u": self._switch_cloud,
            "p": lambda: self._switch_mode("plan"),
            "i": self._pick_plan,
            "f": self._new_flow,
        }
        if key in actions:
            actions[key]()
            return True
        questions = self.console.data.questions
        if not questions:
            return False
        if key == "v":
            details(self.console, questions[0])
            return True
        return answer(self.console, questions[0], key)

    def explain(self) -> tuple[str, list[str]]:
        """What the page shows, and what each key does."""
        return "This folder", [
            f"The folder clank was started in: {self.console.folder}. Working there needs Docker, the folder's "
            "workspace (a record naming the folder; nothing is written in it) and its container, Clank's sandbox "
            "image, a model in the main slot, and the gateway, which the agent reaches through the container's edge.",
            "Each step shows green when it is done, red when it is not, yellow while it changes, and the key that "
            "does it: s starts Docker; o opens the workspace (it makes the record, builds the sandbox image the "
            "first time, asked first, about a gigabyte, and starts the container); l loads a model picked from the "
            "presets. g does every step that is not done yet, in order.",
            "a starts OpenCode in the folder's container once every step is done: the console steps aside while it "
            "runs in this terminal and comes back when it is left. `clank work` does it all from the command line.",
            "c does every step that is not done, then opens the folder in Clank's VS Code window (a VS Code of its "
            "own: its settings and extensions under Clank's folder, your main VS Code untouched; the first time it "
            "installs its extensions), where OpenCode opens in a terminal beside your files. `clank code` does the "
            "same. Over SSH nothing opens on the PC's own screen: in a terminal of VS Code's Remote-SSH, the folder "
            "opens in your computer's VS Code, connected to this PC (Clank's extension and settings installed on this "
            "PC's side first), and the PC draws no window; in any other, the console says the command to run on your "
            "computer (`ssh_host` in config/vscode.json names this PC there).",
            "e installs the folder's own software (its packages, its command line, its MCP server) into the "
            "workspace's home, where the agent finds it: Clank proposes the command from the folder's pyproject.toml "
            "or requirements.txt, and you may change it; it runs in a container of its own that reaches the internet, "
            "while the agent's never does. The agent can start without it; g and c offer it, asked first.",
            "r switches how the agent changes your files: review (the default) has it ask first, and the change opens "
            "in VS Code beside your files to accept or reject (or answer it here, under waiting for you, or from the "
            "phone); auto lets it change files without asking, and VS Code shows each change after it is made. A "
            "command the agent runs can still change files either way.",
            "f builds a flow with the model: the console goes to the Monitor's Flow view, which opens a planning "
            "(a session of OpenCode's in the folder's workspace, where the model reads the folder, asks you what it "
            "needs, writes BRIEF.md and drafts the flow) and shows it built: over SSH, run `clank flow attach` in "
            "another terminal to talk with the model; in Windows Terminal its window splits for it; in VS Code's "
            "terminal, Clank's VS Code window opens. Once Clank wrote the flow: look, then r runs it.",
            "m gives an MCP server to the agent or takes it away: yours (F3) are given unless you take one away here; "
            "the folder's own (its .mcp.json) only once you allow it, and again after its entry changes. A server "
            "given is checked at once in the workspace's container, where the agent will start it: its tools show "
            "beside it. The agent gets the servers when it next starts (a or c).",
            "A folder is refused when its container would see more than it: a drive's root, your home folder, or a "
            "folder that holds Clank's own folder (its secrets) or lies inside it.",
            "w switches between one OpenCode window (the default) and several: with one, opening OpenCode (a, c, or "
            "VS Code's Start the agent) first closes the window already open in the workspace, so there is only ever "
            "one and p and r always reach it; with several, each opening adds a window. OpenCode without a window (the "
            "phone's) is left alone either way.",
            "A question a step asks (the image's build) shows here, answered with its options' keys; v shows it whole.",
        ]

    def _read(self) -> None:
        """Read the folder's workspace and image, the gateway and the agent's plan, off the screen's thread."""
        if not self.display:
            return
        client, folder, endpoints = self.console.client, self.console.folder, bool(self.console.data.endpoints)

        def work() -> None:
            try:
                view = client.get("workspaces/folder", folder=folder)
                gateway = client.get("gateway")
                plan = client.get("agents/plan")
                servers = client.get("agents/servers", workspace=view["workspace"]) if view["workspace"] else None
                review = client.get("agents/review", workspace=view["workspace"]) if view["workspace"] else None
                cost = _cost(client, view["workspace"]) if view["workspace"] and endpoints else None
            except (NotRunning, ClientError):
                return  # the header says the service does not answer; the next read tries again
            except Exception as error:  # a fault of the page's own: said, not hidden
                self._say(f"this folder's page could not read what it shows: {error!r}", True)
                return
            found = servers["servers"] if servers is not None else None
            self.cost = cost
            self.console.call_from_thread(self._show, view, gateway, plan, found, review)

        self.run_worker(work, thread=True, group="folder-read", exclusive=True, exit_on_error=False)

    def _show(
        self,
        view: dict[str, Any],
        gateway: dict[str, Any],
        plan: dict[str, Any],
        servers: list[dict[str, Any]] | None,
        review: dict[str, Any] | None = None,
    ) -> None:
        self.view, self.gateway, self.plan, self.servers, self.review = view, gateway, plan, servers, review
        self.draw(self.console.data, {"folder"})

    def _new_flow(self) -> None:
        """`f`: a flow built with the model (decision 0100): the console goes to the Monitor's Flow view, whose `n`
        opens the planning beside the console and shows it built."""
        self.console.show_page("monitor")
        monitor = self.console.query_one("#page-monitor", MonitorPage)
        monitor.show_view("flow")
        monitor.flows.new_flow("")

    def _switch_review(self) -> None:
        """Switch between reviewing each change the agent asks for and auto (from plan: back to the change rule kept),
        the window's agent build, in a worker (design 0009 §7)."""
        review = self.review or {}
        if review.get("shown") == "plan":
            self._switch_mode(str(review.get("mode") or "review"))
        else:
            self._switch_mode("review" if review.get("mode") == "auto" else "auto")

    def _switch_windows(self) -> None:
        """Switch between one OpenCode window at a time and several, kept in the workspace's record (design 0004 §5),
        in a worker."""
        review = self.review or {}
        if not review.get("workspace"):
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['w']}", True)
            return
        client, workspace = self.console.client, review["workspace"]

        def work() -> None:
            try:
                loaded = client.get(f"records/workspace/{workspace}")
                one = not loaded["values"].get("one_window", True)
                values = {**loaded["values"], "one_window": one}
                client.put(f"records/workspace/{workspace}", {"values": values, "base": loaded["revision"]})
            except (NotRunning, ClientError) as error:
                self._say(f"the windows were not switched: {error}", True)
                return
            said = ("one OpenCode window: opening one closes the one open" if one
                    else "several OpenCode windows: opening one adds another")  # fmt: skip
            self._say(f"{workspace} now has {said}")
            self.console.call_from_thread(self._read)

        self.run_worker(work, thread=True, group="folder-review", exclusive=True, exit_on_error=False)

    def _switch_mode(self, mode: str) -> None:
        """Plan, review or auto, in a worker: the window's agent switched, the change rule set."""
        review = self.review or {}
        if not review.get("workspace"):
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['p']}", True)
            return
        client, workspace = self.console.client, review["workspace"]

        def work() -> None:
            try:
                now = client.post("agents/mode", {"workspace": workspace, "mode": mode})
            except (NotRunning, ClientError) as error:
                self._say(f"the mode was not switched: {error}", True)
                return
            said = {"plan": "plans with the Planner: Markdown only, no code, no runs",
                    "review": "builds, asking before it changes a file",
                    "auto": "builds, changing files without asking"}[mode]  # fmt: skip
            note = str(now.get("note") or "")
            self._say(f"{workspace}'s agent now {said}" + (f" ({note})" if note else ""), bool(note))
            self.console.call_from_thread(self._reviewed, now)

        self.run_worker(work, thread=True, group="folder-review", exclusive=True, exit_on_error=False)

    def _pick_plan(self) -> None:
        """A plan of the folder to hand to the agent, then review or auto (design 0009 §8)."""
        workspace = (self.review or {}).get("workspace") or (self.view or {}).get("workspace")
        if not workspace:
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['i']}", True)
            return
        client = self.console.client

        def work() -> None:
            try:
                found = client.get("agents/plans", workspace=workspace)["plans"]
            except (NotRunning, ClientError) as error:
                self._say(f"the plans were not read: {error}", True)
                return
            self.console.call_from_thread(self._plans_read, workspace, found)

        self.run_worker(work, thread=True, group="folder-plans", exclusive=True, exit_on_error=False)

    def _plans_read(self, workspace: str, plans: list[dict[str, Any]]) -> None:
        if not plans:
            self.console.say("no plan in this folder yet: Tab in OpenCode to the Planner writes one", True)
            return
        choices = [
            Choice(plan["path"], plan["title"] or plan["path"],
                   f"{plan['status'] or 'no status'} · {plan['done']} of {plan['steps']} steps done · {plan['path']}")
            for plan in plans
        ]  # fmt: skip

        def picked(plan: str | None) -> None:
            if plan is None:
                return
            modes = [
                Choice("review", "Implement with Review", "build asks before each change (the plan's ticks excepted)"),
                Choice("auto", "Implement with Auto", "build changes files without asking"),
            ]
            self.console.push_screen(
                PickScreen(f"Hand {plan} to the agent", modes),
                lambda mode: self._implement(workspace, plan, mode) if mode else None,
            )

        self.console.push_screen(PickScreen("Implement a plan: a new session in OpenCode's window", choices), picked)

    def _implement(self, workspace: str, plan: str, mode: str) -> None:
        """Hand the plan to the agent, in a worker."""
        client = self.console.client

        def work() -> None:
            try:
                client.post("agents/implement", {"workspace": workspace, "plan": plan, "mode": mode})
            except (NotRunning, ClientError) as error:
                self._say(f"{plan} was not handed over: {error}", True)
                return
            self._say(f"{workspace}'s agent implements {plan} ({mode}) in a new session of its window")

        self.run_worker(work, thread=True, group="folder-implement", exclusive=True, exit_on_error=False)

    def _reviewed(self, review: dict[str, Any]) -> None:
        self.review = review
        self.draw(self.console.data, {"folder"})

    def _setup_form(self) -> None:
        """The command that installs the folder's software, to change or take as it is; Enter installs."""
        view = self.view or {}
        if not view.get("workspace"):
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['e']}", True)
            return
        setup = view.get("setup") or {}
        field = Field(
            "command",
            "The command that installs it, run in the folder (/workspace) with the internet",
            "python3 -m venv --system-site-packages ~/.venv && ~/.venv/bin/python -m pip install -r requirements.txt",
            setup.get("command") or "",
        )
        note = (
            "It runs in a container of its own that reaches the internet; the agent's never does. The command is kept "
            "for next time. Enter installs; Esc closes this."
        )

        def given(values: dict[str, str] | None) -> None:
            if values is not None and values["command"]:
                self._run(["setup"], command=values["command"])

        self.console.push_screen(FormScreen("Install this folder's software", [field], note), given)

    def _pick_server(self) -> None:
        """An MCP server to give to the agent, or to take away; one given is checked where the agent will start it."""
        workspace = (self.view or {}).get("workspace")
        if not workspace:
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['m']}", True)
            return
        if not self.servers:
            self.console.say("no MCP server to give: F3 adds yours; a folder's .mcp.json offers its own", True)
            return
        choices = [
            Choice(
                server["name"],
                server["name"],
                ("given: Enter takes it away" if server["given"] else f"not given ({server['why']}): Enter gives it")
                + f" · {server['shown']}",
            )
            for server in self.servers
        ]

        def picked(value: str | None) -> None:
            if value is not None:
                self._toggle(workspace, value)

        self.console.push_screen(PickScreen("Give an MCP server to the agent, or take it away", choices), picked)

    def _toggle(self, workspace: str, name: str) -> None:
        """Give the server or take it away, in a worker; a server given is checked in the workspace's container."""
        if self.running:
            self.console.say("a step runs from this page: it is followed under What runs from here", True)
            return
        row = next(server for server in self.servers or [] if server["name"] == name)
        client, folder = self.console.client, self.console.folder
        running = (self.view or {}).get("state") == "running"
        self.running = True

        def work() -> None:
            try:
                now = client.post("agents/servers", {"workspace": workspace, "name": name, "given": not row["given"]})
                if not now["given"]:
                    self.checked.pop(name, None)
                    self._say(f"{name}: the agent does not get it ({now['why']})")
                elif not running:
                    self._say(f"{name}: the agent gets it; it is checked once the workspace runs (o)")
                else:
                    asked = {"folder": folder, "scope": now["scope"], "workspace": workspace}
                    operation = client.post(f"mcp/servers/{name}/check", asked)
                    if self._follow(operation):
                        result = client.get(f"records/operation/{operation['id']}")["values"]["result"]
                        self.checked[name] = f"{len(result['tools'])} tools"
                        self._say(f"{name}: the agent gets it, with {len(result['tools'])} tools, when it next starts")
                    else:
                        self.checked[name] = "its check failed (the message line says why)"
            except (NotRunning, ClientError) as error:
                self._say(str(error), True)
            except Exception as error:  # a fault of the page's own: said, not hidden
                self._say(f"the server could not be given: an error of Clank's: {error!r}", True)
            finally:
                self.running = False
                self.console.call_from_thread(self._read)

        self.run_worker(work, thread=True, group="folder-steps", exclusive=True, exit_on_error=False)

    def _pick_hosts(self) -> None:
        """A named set of hosts to allow the agent or take back, or a host by name (design 0024 §4, §5)."""
        workspace = (self.view or {}).get("workspace")
        if not workspace:
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['h']}", True)
            return
        client = self.console.client
        hosts = dict((self.view or {}).get("hosts") or {})

        def work() -> None:
            try:
                sets = client.get("workspaces/network-sets")
            except (NotRunning, ClientError) as error:
                self._say(str(error), True)
                return
            self.console.call_from_thread(self._show_hosts, workspace, sets, hosts)

        self.run_worker(work, thread=True, group="folder-hosts", exclusive=True, exit_on_error=False)

    def _show_hosts(self, workspace: str, sets: dict[str, dict[str, Any]], hosts: dict[str, str]) -> None:
        """The picker: each set allowed or not, a host by name, and each host allowed (to take back)."""
        allowed = {name: all(host in hosts for host in each.get("hosts") or []) for name, each in sets.items()}
        choices = [
            Choice(
                f"set:{name}",
                f"{name}: {', '.join(each.get('hosts') or [])}",
                ("allowed: Enter takes it back" if allowed[name] else "not allowed: Enter allows it")
                + (f" · {each['for']}" if each.get("for") else ""),
            )
            for name, each in sets.items()
        ]
        choices.append(
            Choice("host", "a host by name", "Enter asks for it: pypi.org, or .arxiv.org for a site and all under it")
        )
        choices += [Choice(f"host:{host}", host, f"{hosts[host]}: Enter takes it back") for host in sorted(hosts)]

        def picked(value: str | None) -> None:
            if value is None:
                return
            if value == "host":
                self._host_form(workspace)
            elif value.startswith("set:"):
                self._change_hosts(workspace, "sets", {"set": value[4:], "allow": not allowed[value[4:]]})
            else:
                self._change_hosts(workspace, "hosts", {"host": value[5:], "allow": False})

        self.console.push_screen(PickScreen("Allow the agent hosts, or take them back", choices), picked)

    def _host_form(self, workspace: str) -> None:
        field = Field("host", "Host", "pypi.org, or .arxiv.org for a site and everything under it", "")
        note = "The agent reaches it through Clank's proxy; every exchange is logged (clank network log)."

        def given(values: dict[str, str] | None) -> None:
            host = (values or {}).get("host", "").strip()
            if host:
                self._change_hosts(workspace, "hosts", {"host": host, "allow": True})

        self.console.push_screen(FormScreen("Allow the agent a host", [field], note), given)

    def _change_hosts(self, workspace: str, what: str, body: dict[str, Any]) -> None:
        """Allow or take back, in a worker; the page reads the folder again after."""
        client = self.console.client

        def work() -> None:
            try:
                after = client.post(f"workspaces/{workspace}/{what}", body)
                reached = ", ".join(sorted(after.get("hosts") or {}))
                self._say(
                    f"{workspace}: its agent may reach {reached}"
                    if reached
                    else f"{workspace}: its agent reaches no host"
                )
            except (NotRunning, ClientError) as error:
                self._say(str(error), True)
            finally:
                self.console.call_from_thread(self._read)

        self.run_worker(work, thread=True, group="folder-hosts", exclusive=True, exit_on_error=False)

    def _pick_model(self) -> None:
        """A preset to run in the main slot, the slot's last that worked first (else the default)."""
        data = self.console.data
        main = next((slot for slot in data.slots if slot["name"] == "main"), None)
        first = ((main or {}).get("last_good") or {}).get("preset") or DEFAULT_PRESET
        choices = preset_choices(data.presets)
        choices.sort(key=lambda choice: choice.value != first)
        if not choices:
            self.console.say("there is no preset to load: the Presets page (9) shows why", True)
            return

        def picked(value: str | None) -> None:
            if value is not None:
                self._run(["model"], preset=value)

        self.console.push_screen(PickScreen("Run in the main slot", choices), picked)

    def _run(self, steps: list[str], preset: str | None = None, command: str | None = None) -> None:
        """Do the steps in a worker, in order, each only when it is needed; stop at the first that does not end (but
        the folder's software: the agent can start without it)."""
        if self.running:
            self.console.say("a step runs from this page: it is followed under What runs from here", True)
            return
        self.running = True

        def work() -> None:
            try:
                for step in steps:
                    if not self._step(step, preset, command):
                        return
                if "vscode" in steps:
                    on = " on your computer" if places.vscode_place(os.environ) == places.REMOTE else ""
                    self._say(f"VS Code opens this folder{on}: OpenCode opens beside your files")
                elif all(step in steps for step in STEPS):
                    self._say("everything is ready: a starts OpenCode here")
            except (NotRunning, ClientError) as error:
                self._say(str(error), True)
            except Exception as error:  # a fault of the page's own: said, not hidden
                self._say(f"the step stopped on an error of Clank's: {error!r}", True)
            finally:
                self.running = False
                self.console.call_from_thread(self._read)

        self.run_worker(work, thread=True, group="folder-steps", exclusive=True, exit_on_error=False)

    def _step(self, step: str, preset: str | None, command: str | None = None) -> bool:
        """One step, on the worker's thread: True when it is done (or was already)."""
        self.doing = step
        client = self.console.client
        if step == "setup":
            return self._setup(command)
        if step == "docker":
            if client.get("docker", refresh=True)["state"] == "running":
                return True
            return self._follow(client.post("docker/start"))
        if step == "workspace":
            view = client.get("workspaces/folder", folder=self.console.folder)
            if view["problem"]:
                self._say(view["problem"], True)
                return False
            if view["state"] == "running" and view.get("edge") not in MENDED:
                return True
            return self._follow(client.post("workspaces/open", {"folder": self.console.folder, "yes": False}))
        if step == "image":  # o only: a newer image is built while the workspace runs on the one it has
            view = client.get("workspaces/folder", folder=self.console.folder)
            if view["image"]["built"] is not False:
                return True
            return self._follow(client.post("workspaces/open", {"folder": self.console.folder, "yes": False}))
        if step == "model":
            return self._model(preset)
        if step == "vscode":
            return self._vscode()
        gateway = client.get("gateway")
        if gateway["state"] == "running":
            return True
        gateway = client.post("gateway/restart")
        if gateway["state"] != "running":
            self._say(f"the gateway does not run: {gateway.get('problem') or gateway['state']}", True)
            return False
        return True

    def _vscode(self) -> bool:
        """VS Code on the folder where the owner sits (design 0018 §8.1): Clank's window on the PC, or the other
        computer's from a terminal of VS Code's Remote-SSH; over any other SSH nothing opens, and the command to run
        there is said (the step then stops, done)."""
        client, folder = self.console.client, self.console.folder
        if places.vscode_place(os.environ) == places.OVER_SSH:
            host = str(client.get("records/vscode/vscode")["values"].get("ssh_host") or "")
            self._say(f"everything is ready; {places.ssh_said(folder, os.environ, host)}")
            return False
        return self._follow(client.post("agents/vscode", places.vscode_request(folder, os.environ)))

    def _setup(self, command: str | None) -> bool:
        """The folder's software: the command given (the form's, so no question), else the kept or proposed one when it
        is not installed yet (asked first). Among other steps (g, c) a setup not done does not stop the ones after."""
        client = self.console.client
        if command is None:
            setup = client.get("workspaces/folder", folder=self.console.folder).get("setup")
            if setup is None or setup["command"] is None or setup["installed"]:
                return True
        body = {"folder": self.console.folder, "command": command or "", "yes": command is not None}
        done = self._follow(client.post("workspaces/setup", body))
        return done or command is None

    def _model(self, preset: str | None) -> bool:
        """A model in the main slot: the one asked for, else the one that runs, else the slot's last that worked."""
        client = self.console.client
        main = next(slot for slot in client.get("runtime/slots") if slot["name"] == "main")
        if preset is None and main["status"] == "ready":
            return True
        if preset is None and main["status"] in ("starting", "stopping"):
            return self._until_ready()
        chosen = preset or (main.get("last_good") or {}).get("preset") or DEFAULT_PRESET
        verb = "switch" if main["status"] == "ready" else "load"
        return self._follow(client.post(f"runtime/slots/main/{verb}", {"preset": chosen}))

    def _until_ready(self) -> bool:
        """Wait for a model another start is bringing up."""
        client = self.console.client
        deadline = time.monotonic() + MODEL_SECONDS
        while time.monotonic() < deadline:
            main = next(slot for slot in client.get("runtime/slots") if slot["name"] == "main")
            if main["status"] == "ready":
                return True
            if main["status"] in ("stopped", "failed"):
                self._say(f"the model did not start: {main['reason']}", True)
                return False
            self._progress([f"the main slot is {main['status']}: {main['reason']}"])
            time.sleep(POLL_SECONDS)
        self._say("the model is still starting: it is followed on the Models page (8)", True)
        return False

    def _follow(self, operation: dict[str, Any]) -> bool:
        """Follow an operation to its end, its step and last line shown here; True when it is done."""
        client, id = self.console.client, operation["id"]
        last = ""
        number = 0
        current = operation
        while current["status"] not in FINISHED:
            time.sleep(POLL_SECONDS)
            lines = client.get(f"operations/{id}/log", after=number)
            if lines:
                number, last = lines[-1]["number"], lines[-1]["text"]
            current = client.get(f"records/operation/{id}")["values"]
            steps = current["steps"]
            step = f"{steps[-1]['number']} of {current['planned_steps']}: {steps[-1]['name']}" if steps else "starting"
            waiting = "   (it waits for your answer below)" if current["status"] == "waiting" else ""
            self._progress([f"{current['title']}: {step}{waiting}", *([f"  {last}"] if last else [])])
        self._progress([])
        if current["status"] == "done":
            self._say(f"{current['title']}: done")
            return True
        self._say(f"{current['title']}: {current.get('error') or current['status']}", True)
        return False

    def _progress(self, lines: list[str]) -> None:
        def shown() -> None:
            self.progress = lines
            self.draw(self.console.data, {"folder"})

        self.console.call_from_thread(shown)

    def _say(self, text: str, error: bool = False) -> None:
        self.console.call_from_thread(self.console.say, text, error)

    def _start_agent(self) -> None:
        """OpenCode in the folder's container, in this terminal; the console comes back when it ends. With a cloud model
        loaded, the workspace is asked first, once (decision 0112)."""
        found = blocking(missing(self.console.data, self.view, self.gateway))
        if found:
            self.console.say(readiness(found), True)
            return
        client, workspace = self.console.client, (self.view or {}).get("workspace")
        cloud = bool(self.console.data.endpoints)

        def work() -> None:
            try:
                if cloud:
                    asked = client.post(f"workspaces/{workspace}/cloud/ask")
                    if asked["needed"]:
                        question = client.get(f"records/question/{asked['question']}")["values"]
                        self.console.call_from_thread(self._ask_cloud, question)
                        return
                    if not asked.get("start", True):
                        self._say(f"the agent was not started: {asked['why']} (u allows the cloud for it)", True)
                        return
                prepared = client.post("agents/prepare", {"workspace": workspace})
            except (NotRunning, ClientError) as error:
                self._say(str(error), True)
                return
            self.console.call_from_thread(self._hand_over, prepared)

        self.run_worker(work, thread=True, group="folder-agent", exclusive=True, exit_on_error=False)

    def _ask_cloud(self, question: dict[str, Any]) -> None:
        """The workspace's question in a window; allowed, the agent starts; kept local, the service says why not."""
        workspace = (self.view or {}).get("workspace") or ""

        def answered(option: str | None) -> None:
            if option is None:
                self.console.say(f"{workspace}'s question waits (Questions, 2): the agent starts once it is answered")
                return
            client = self.console.client

            def work() -> None:
                try:
                    client.post(f"questions/{question['id']}/answer", {"option": option})
                except (NotRunning, ClientError) as error:
                    self._say(str(error), True)
                    return
                if option == "allow":
                    self._say(f"{workspace} may use the cloud model: starting the agent")
                    self.console.call_from_thread(self._start_agent)
                else:
                    self.console.call_from_thread(self._start_agent)  # the service says why it does not start

            self.run_worker(work, thread=True, group="folder-agent", exclusive=True, exit_on_error=False)

        self.console.push_screen(AskScreen(question), answered)

    def _switch_cloud(self) -> None:
        """`u`: allow this workspace the cloud model, or keep it on this machine, asked first."""
        workspace = (self.view or {}).get("workspace")
        if not workspace:
            self.console.say(f"open the workspace first (o): {WORKSPACE_FIRST['u']}", True)
            return
        if not self.console.data.endpoints:
            self.console.say("no cloud provider is added: Add a model (F12) adds one", True)
            return
        allow = (self.view or {}).get("models") != "cloud"
        lines = [((self.view or {}).get("cloud_confirm") or {}).get("allow" if allow else "local", "")]
        lines.append(f"The call: POST /api/v1/workspaces/{workspace}/cloud {json.dumps({'allow': allow})}")
        title = f"Let {workspace} use the cloud model?" if allow else f"Keep {workspace} on this machine?"

        def answered(yes: bool | None) -> None:
            if not yes:
                return
            client = self.console.client

            def work() -> None:
                try:
                    client.post(f"workspaces/{workspace}/cloud", {"allow": allow})
                except (NotRunning, ClientError) as error:
                    self._say(str(error), True)
                    return
                said = "may use the cloud model" if allow else "is kept on this machine"
                self._say(f"{workspace} {said}")
                self.console.call_from_thread(self._read)

            self.run_worker(work, thread=True, group="folder-cloud", exclusive=True, exit_on_error=False)

        self.console.push_screen(ConfirmScreen(title, lines), answered)

    def _hand_over(self, prepared: dict[str, Any]) -> None:
        """Step aside for the agent, on the console's thread, and say how it ended once back."""
        run = self.console.terminal or terminal.attached
        outcome = terminal.hand_over(self.console, prepared["argv"], run)
        ended = "ended" if outcome == 0 else f"ended: {outcome if isinstance(outcome, str) else f'exit {outcome}'}"
        self.console.say(f"{prepared['program']} {ended}", outcome != 0)
        self._read()


def _cost(client: Any, workspace: str) -> dict[str, Any] | None:
    """The workspace's cloud cost, as the service says it; None from a service without the cost's routes."""
    try:
        found: dict[str, Any] = client.get("gateway/cost", workspace=workspace)
    except ClientError as error:
        if error.status == 404:
            return None
        raise
    return found
