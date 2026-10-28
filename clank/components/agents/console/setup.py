"""The console's Setup page (design 0028 §4, §5): `clank setup`'s checklist, as the service gives it (`GET /setup`, the
console's `setup` topic), and the key that does the next step.

Each item is a row: its number and title, then a mark and what it is now (green when done; red when it is required and
not done; dim while it waits for an item before it, is not known, or is offered rather than required; yellow while it
is being done), and under an item not done, what to do and the key that does it here: `s` starts Docker Desktop
through its own command (the service's `docker.start`); `t` runs the command shown, one that needs administrator
rights (`sudo systemctl start docker`, `sudo systemctl enable docker`, `sudo usermod -aG docker <account>`, the
installer's Docker step), in this terminal, asked first: the console steps aside while it runs, sudo asks for the
password itself, and nothing it says reaches Clank (`clank.console.terminal`); what the person does after it (log out
and in) is said when it ends. `m` opens Add a model (in the cloud through OpenRouter, on this computer's GPU, or both),
`f` opens This folder, where `o` opens the folder as a workspace. Under the rows, "Next:" and the key of the first
required item a key can do, or what to do when none can (log out and in); once everything required is done, "Ready:",
what was set up and what each thing is for, and `f`. `r` reads the checklist again now (the service is asked again
whenever Docker, the slots or an operation change, and every few seconds while the page is on screen).

The page has no key of its own in the menu: the one F-key left, F11, is the terminal's full screen on most terminals.
It is the last page of the menu, Ctrl+P finds it, and the console opens on it while anything required is missing
(decision 0148).
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.client import ClientError, NotRunning
from clank.console import terminal
from clank.console.buttons import Buttons, from_keys
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.rows import Rows
from clank.console.style import mark

TITLES = 36  # an item's number and title, the column its words wrap beside
READ_SECONDS = 5.0
REFRESHED_BY = {"all", "setup"}
KEY_OF = {"docker": "s", "terminal": "t", "model": "m", "folder": "f"}  # what a fix does, and the key here
DOING = {"s": "start Docker", "t": "run it in this terminal", "m": "add a model", "f": "open This folder"}
INTRO = (
    "What Clank needs on this computer, in order: each says what it is now and, while it is not done, what to do. "
    "`clank setup` in a terminal says the same."
)
STEPS_ASIDE = (
    "The console steps aside while it runs in this terminal: sudo asks for your password there itself, and Clank never "
    "sees it. The console comes back when it ends."
)


def sign(item: dict[str, Any]) -> tuple[str, str]:
    """An item's mark, and the element of the style it is drawn in."""
    state, required = item["state"], item["required"]
    if state == "done":
        return mark("done"), "$clank-good"
    if state == "doing":
        return mark("cut"), "$clank-attention"
    if state == "to do" and required:
        return mark("failed"), "$clank-failed"
    if state == "unknown":
        return mark("asks"), "$clank-quiet"
    return mark("off"), "$clank-quiet"


def item_rows(found: dict[str, Any]) -> list[tuple[str, Content]]:
    """The checklist's items as rows: number and title; mark, what it is now, and what to do with its key here."""
    rows = []
    for number, item in enumerate(found["items"], 1):
        glyph, style = sign(item)
        offered = "optional: " if not item["required"] and item["state"] != "done" else ""
        value = Content.assemble((glyph, style), f" {offered}{item['said']}")
        fix = item.get("fix")
        if fix and item["state"] != "done":
            key = KEY_OF.get(fix["does"], "")
            press = f" · press {key}" + (" to run it in this terminal" if key == "t" else "") if key else ""
            value = Content.assemble(value, "\n", ("→ ", "$clank-quiet"), fix["said"], (press, "$clank-key"))
        rows.append((f" {number}  {item['title']}", value))
    return rows


def first_fix(found: dict[str, Any] | None, does: str) -> dict[str, Any] | None:
    """The first item not done whose fix does this, required or offered."""
    for item in (found or {}).get("items", []):
        fix = item.get("fix")
        if item["state"] != "done" and fix and fix["does"] == does:
            return dict(item)
    return None


def next_step(found: dict[str, Any]) -> tuple[str, list[str | tuple[str, str]], Content]:
    """The row of buttons under the items, and the line above it: "Ready:" and This folder once everything required
    is done; else "Next:" and the key of the first required item a key here can do; else what to do, in words."""
    if found["ready"]:
        said = [found["said"], *(f"· {line}" for line in found.get("ready_said") or [])]
        return "Ready:", [("f", "open This folder")], Content("\n".join(said))
    for item in found["items"]:
        if not item["required"] or item["state"] == "done":
            continue
        fix = item.get("fix")
        key = KEY_OF.get(fix["does"], "") if fix else ""
        if key == "t" and fix:
            return "Next:", [("t", f"run `{fix['shown']}` in this terminal")], Content(found["said"])
        if key:
            return "Next:", [(key, DOING[key])], Content(found["said"])
        if item["state"] in ("to do", "unknown") and fix:
            return "", [], Content(f"{found['said']} Next: {item['title']}: {fix['said']}.")
        if item["state"] == "to do":
            return "", [], Content(f"{found['said']} Next: {item['title']}: {item['said']}.")
    return "", [], Content(found["said"])


class SetupPage(Page):
    """What Clank needs on this computer, and the key that does the next step."""

    ENTRY = MenuEntry(
        "setup",
        "Setup",
        "What Clank needs on this computer, item by item, and the key that does the next step (s starts Docker "
        "Desktop, t runs a command that needs administrator rights in this terminal, m adds a model, f opens This "
        "folder, r reads it again); the console opens here while anything required is missing.",
        "design 0028 §4",
    )
    PANELS = ("setup-items",)
    KEYS = (
        PageKey("s", "docker", "start Docker", "start Docker Desktop through its own command, and wait for it"),
        PageKey("t", "terminal", "run it here", "run the command shown, which needs administrator rights, in this "
                "terminal: the console steps aside, sudo asks for your password itself, and the console comes back"),
        PageKey("m", "model", "add a model", "Add a model: in the cloud through OpenRouter, on this computer's GPU, "
                "or both"),
        PageKey("f", "folder", "This folder", "This folder: the folder clank was started in, where o opens it as a "
                "workspace and a starts the agent"),
        PageKey("r", "read", "read it again"),
    )  # fmt: skip

    def compose(self) -> ComposeResult:
        """The items, then what to do next."""
        with Panel(title="Clank's setup", id="setup-items"):
            yield Label(INTRO, id="setup-intro")
            yield Rows(TITLES, id="setup-rows")
            yield Label(id="setup-next")
            yield Buttons(id="setup-buttons")

    def on_mount(self) -> None:
        """Draw, and read the checklist again every few seconds while on screen."""
        super().on_mount()
        self.set_interval(READ_SECONDS, self._read)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """The items and what to do next, when the checklist changed."""
        if not changed & REFRESHED_BY:
            return
        found = data.setup
        rows = self.query_one("#setup-rows", Rows)
        group = self.query_one("#setup-buttons", Buttons)
        line = self.query_one("#setup-next", Label)
        if found is None:
            rows.show([])
            line.update("The checklist is not read yet (a service older than this console does not give it).")
            group.display = False
            return
        rows.show(item_rows(found))
        lead, keys, said = next_step(found)
        line.update(said)
        group.show(from_keys(self.KEYS, *keys), lead=lead)
        group.display = bool(keys)

    def unable(self, key: str) -> str:
        """Why `s` or `t` cannot act now: no item waits for it."""
        found = self.console.data.setup
        if key == "s" and first_fix(found, "docker") is None:
            return "Docker needs no start from here"
        if key == "t" and first_fix(found, "terminal") is None:
            return "no command waits to run in this terminal"
        return ""

    def press(self, key: str) -> bool:
        """`s` Docker Desktop started, `t` the command shown run in this terminal (asked first), `m` Add a model, `f`
        This folder, `r` the checklist read again."""
        if self.app.screen is not self.screen:
            return False
        if key == "s":
            self.console.ask_docker(False)
            return True
        if key == "t":
            self._ask_terminal()
            return True
        if key == "m":
            self.console.show_page("addmodel")
            page: Any = self.console.query_one("#page-addmodel")
            page.start()
            return True
        if key == "f":
            self.console.show_page("folder")
            return True
        if key == "r":
            self._read(said=True)
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """What the page shows, and what each key does."""
        return "Setup", [
            "What Clank needs on this computer, in order: Docker installed, running and usable by this account (on "
            "Linux, Docker Engine, which Clank never starts itself; also whether it starts with the computer), "
            "Clank's service, the sandbox image every workspace's container runs, a model that answered a test "
            "request, a folder that is a workspace, and, offered, Clank's VS Code window.",
            "Each item says what it is now and, while it is not done, what to do: s starts Docker Desktop; t runs a "
            "command that needs administrator rights in this terminal, asked first (the console steps aside, sudo "
            "asks for your password itself, and Clank never sees it); m adds a model (in the cloud through OpenRouter "
            "with your key, on this computer's GPU, or both: the cloud first, then local); f opens This folder, where "
            "o opens the folder as a workspace. `clank setup` in a terminal offers the same fixes, one by one.",
            "The console opens here while anything required is missing; once everything is done it says what was set "
            "up and what each thing is for, and f opens This folder. r reads it all again.",
        ]

    def _ask_terminal(self) -> None:
        """`t`: the command shown, asked first in a window, then run in this terminal."""
        item = first_fix(self.console.data.setup, "terminal")
        if item is None:
            return
        fix = item["fix"]
        lines = [f"{item['title']}: {item['said']}.", f"{fix['said'][0].upper()}{fix['said'][1:]}.", STEPS_ASIDE]
        if fix["after"]:
            lines.append(f"Then: {fix['after']}.")

        def answered(yes: bool | None) -> None:
            if yes:
                self._run(item)

        self.console.push_screen(ConfirmScreen(f"Run `{fix['shown']}` in this terminal?", lines), answered)

    def _run(self, item: dict[str, Any]) -> None:
        """Step aside for the command, on the console's thread, and say how it ended once back."""
        fix = item["fix"]
        outcome = terminal.hand_over(self.console, fix["command"], self.console.terminal or terminal.attached)
        if outcome != 0:
            ended = outcome if isinstance(outcome, str) else f"exit {outcome}"
            self.console.say(f"`{fix['shown']}` did not work ({ended}): its words were in the terminal", True)
        elif fix["after"]:
            self.console.say(f"`{fix['shown']}` is done. Next: {fix['after']}")
        else:
            self.console.say(f"`{fix['shown']}` is done")
        self._read(refresh=True)

    def _read(self, said: bool = False, refresh: bool = False) -> None:
        """Read the checklist again, off the screen's thread, while the page is on screen (or when asked, `said`: the
        message line says so); Docker read now when asked, or after a command ran (`refresh`)."""
        if not self.display and not said:
            return
        client, console = self.console.client, self.console

        def work() -> None:
            try:
                found = client.get("setup", refresh=said or refresh)
            except (NotRunning, ClientError) as error:
                if said:
                    console.call_from_thread(console.say, f"the checklist could not be read: {error}", True)
                return
            console.call_from_thread(console.refreshed, "setup", found)
            if said:
                console.call_from_thread(console.say, "read the checklist again")

        self.run_worker(work, thread=True, group="setup-read", exclusive=True, exit_on_error=False)
