"""The console's Setup page (design 0028 §4): `clank setup`'s checklist, as the service gives it (`GET /setup`, the
console's `setup` topic), and the key that does the next step.

Each item is a row: its number and title, then a mark and what it is now (green when done; red when it is required and
not done; dim while it waits for an item before it, is not known, or is offered rather than required; yellow while it
is being done), and under an item not done, what to do and the key that does it here: `m` opens Add a model (in the
cloud through OpenRouter, on this computer's GPU, or both), `f` opens This folder, where `o` opens the folder as a
workspace. Under the rows, "Next:" and the key of the first required item a key can do, or what to do when none can
(log out and in); once everything required is done, "Ready:", what was set up and what each thing is for, and `f`. `r`
reads the checklist again now (the service is asked again whenever Docker, the slots or an operation change, and every
few seconds while the page is on screen).

The page has no key of its own in the menu: the one F-key left, F11, is the terminal's full screen on most terminals.
It is the last page of the menu, Ctrl+P finds it, and the console opens on it while anything required is missing
(decision 0148).
"""

from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.client import ClientError, NotRunning
from clank.console.buttons import Buttons, from_keys
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
KEY_OF = {"model": "m", "folder": "f"}  # what a fix does, and the page's key that does it
DOING = {"m": "add a model", "f": "open This folder"}
INTRO = (
    "What Clank needs on this computer, in order: each says what it is now and, while it is not done, what to do. "
    "`clank setup` in a terminal says the same."
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
            press = f" · press {key}" if key else ""
            value = Content.assemble(value, "\n", ("→ ", "$clank-quiet"), fix["said"], (press, "$clank-key"))
        rows.append((f" {number}  {item['title']}", value))
    return rows


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
        "What Clank needs on this computer, item by item, and the key that does the next step (m adds a model, f opens "
        "This folder, r reads it again); the console opens here while anything required is missing.",
        "design 0028 §4",
    )
    PANELS = ("setup-items",)
    KEYS = (
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

    def press(self, key: str) -> bool:
        """`m` Add a model, `f` This folder, `r` the checklist read again."""
        if self.app.screen is not self.screen:
            return False
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
            "Each item says what it is now and, while it is not done, what to do: m adds a model (in the cloud through "
            "OpenRouter with your key, on this computer's GPU, or both: the cloud first, then local); f opens This "
            "folder, where o opens the folder as a workspace. A command that needs administrator rights is shown with "
            "what it does. Clank never asks for, reads or keeps a password.",
            "The console opens here while anything required is missing; once everything is done it says what was set "
            "up and what each thing is for, and f opens This folder. r reads it all again.",
        ]

    def _read(self, said: bool = False) -> None:
        """Read the checklist again, off the screen's thread, while the page is on screen (or when asked, `said`: the
        message line says so, and Docker is read now)."""
        if not self.display and not said:
            return
        client, console = self.console.client, self.console

        def work() -> None:
            try:
                found = client.get("setup", refresh=said)
            except (NotRunning, ClientError) as error:
                if said:
                    console.call_from_thread(console.say, f"the checklist could not be read: {error}", True)
                return
            console.call_from_thread(console.refreshed, "setup", found)
            if said:
                console.call_from_thread(console.say, "read the checklist again")

        self.run_worker(work, thread=True, group="setup-read", exclusive=True, exit_on_error=False)
