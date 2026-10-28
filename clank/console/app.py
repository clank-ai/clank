"""The console's shell: the header, the menu, the pages, the machine column and the keys bar (design 0001 §5, design
0002 §2.15).

The console is a client of the API and holds nothing of its own (design 0001 §5.1). A follower thread loads what it
shows and follows the event stream (`data.py`); the shell takes the updates off their queue at most `REDRAWS_PER_SECOND`
times a second and draws the header and the page on screen, so a burst of events costs a few redraws, and animations are
off (§5.7); on each of those ticks the page on screen draws what its own readings brought (`Page.tick`), so a page that
reads on its own keeps that rhythm too. Every call to the API runs in a thread, never on the screen's. The header is a
row of pills, one for each part that runs (`header.py`); the machine column on the right (`machine.py`) shows the
machine's meters, read by the service every second, and what Clank is doing; it shows when the terminal is at least
`MACHINE_FROM` columns wide (the screen's `-wide` class), but beside a page that hides it (`Page.MACHINE_COLUMN`, the
Monitor's: the screen's `-no-machine-column` class), and F5 shows or hides it at any width, on every page; hidden, it
draws nothing, and it is drawn whole when it shows again. The gateway's activity (its requests in flight) is read every
`ACTIVITY_SECONDS` for the header, the column and the pages. While something runs (an operation, a model request, a
page's own steps), a spinner turns `1 / SPIN_SECONDS` times a second in the header, the column and the page; nothing is
redrawn for it when nothing runs. The menu lists every page with its key, then, in red, the pages later milestones bring
(`menu.PLANNED`); arrowing through it opens each. Right moves the focus into the page on screen (to its first list, or
to the page itself, which Up and Down then scroll), Right and Left move it between the page's lists, and Left from the
first goes back to the menu; they come after the focused widget's own keys, so an input keeps its arrows. The keys bar
(`keysbar.KeysBar`) shows the keys of the page on screen, wherever the focus is, then the keys that act anywhere (`?`,
F1, F5, `q`, Ctrl+P), as each page declares them (`Page.KEYS`, design 0011 §7); a page's digit is beside it in the
menu, its key in the style's `key`. A digit opens the page with that key, unless the focus is in the page and the page
acts on it (a numbered option of a question); other keys go to the page on screen. Every key the console shows is also
a button (design 0011 §12, `buttons.py`): a button pressed and its key typed go through one door (`press_key`,
`press_page_key`), so they cannot differ; a key the page says cannot act now (`Page.unable`) says why instead of acting,
and a key acted on shows pressed on every group that shows it. A key pressed tells the service the user is here, at
most once a minute (design 0002 §2.7). What an action did, or why it failed, shows on the message line above
the keys. `?` explains what has the focus and says the page's keys (§5.4), and Ctrl+P finds every page and action by
name (`commands.py`). The console knows the folder it was opened in (`folder`, the working folder unless another is
given), for the pages that work in it (design 0004 §1), and hands its terminal to a program those pages start
(`terminal`, `clank.console.terminal`). The look is in `clank.tcss`; `CLANK_HOME/config/console.tcss`, when it exists,
is loaded after it and watched, so a saved change shows at once (§5.5). The colors and marks are the console's style
(design 0011, `style.py`): read from the settings files before the first frame and loaded into a Textual theme of the
style's name, every element a variable the style sheet and the pages name; when the style asked for cannot be read,
Clank's own is used and the message line says why. Ctrl+P's "Change style" writes the one picked through the service,
and the console draws in a style as soon as the service reports a change of its settings or of a style's file
(`restyle`, which draws every widget again); Textual's own theme command is left out of the palette. With `snapshot`,
the console renders one frame once everything is loaded and returns it as text (§5.8). Opened with no page named
(`guide`, a bare `clank` or `clank console`), it opens Setup in place of This folder or Home once it has read that
anything the setup needs is missing that This folder does not put right on its way to the agent (the checklist's
`opens`: design 0028 §4, decision 0148), else Add a model when no model is usable (design 0016 §14, decision 0105). A
page without a key of its own (Setup) is reached from the menu and Ctrl+P.
"""

import os
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, tzinfo
from pathlib import Path, PurePath
from typing import Any, ClassVar

from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.content import Content
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Label, ListItem, ListView

from clank import registry
from clank.client import Client, ClientError, NotRunning
from clank.console import actions
from clank.console.buttons import Button, Buttons
from clank.console.commands import ClankCommands
from clank.console.data import ConsoleData, Follower, Update, apply
from clank.console.details import DetailsScreen
from clank.console.form import Field, FormScreen
from clank.console.gauges import fit
from clank.console.header import header
from clank.console.keys import ANYWHERE, PALETTE, PageKey, said, shown
from clank.console.keysbar import KeysBar
from clank.console.machine import MachineColumn, Seen, busy
from clank.console.menu import PLANNED, MenuEntry, place
from clank.console.pages import Page
from clank.console.pages.help import HelpPage
from clank.console.pages.history import HistoryPage
from clank.console.pages.home import HomePage
from clank.console.pages.operations import OperationsPage
from clank.console.pages.planned import PlannedPage
from clank.console.pages.questions import QuestionsPage
from clank.console.pages.records import RecordsPage
from clank.console.pick import Choice, PickScreen
from clank.console.recording import Recording
from clank.console.snapshot import render_text
from clank.console.style import forget_theme, load_style, theme_of, use
from clank.console.terminal import Terminal
from clank.console.text import clock
from clank.kernel.home import Home
from clank.money import dollars

CLANK_TCSS = Path(__file__).with_name("clank.tcss")
REDRAWS_PER_SECOND = 4
PRESENCE_SECONDS = 60
SPIN_SECONDS = 0.1
ACTIVITY_SECONDS = 2.0
MACHINE_FROM = 130  # the narrowest terminal the machine column shows in by itself
WIDER_FROM = 170  # from here the column is wider (`-wider` in clank.tcss), so processes' names fit
MENU_NAME = 22  # a menu entry's key and name, before its badge
SMALL_FROM = 100  # narrower than this, the menu narrows (`-small` in clank.tcss): its names shortened, "coming" hidden
SMALL_NAME = 16  # a menu entry's key and name in a small terminal
MACHINE_TOPICS = {"all", "meters", "operations", "connection", "activity"}


def _pages_in_order() -> list[type[Page]]:
    """The shell's pages and every component's, in the menu's order (`menu.place`): the one a bare `clank` opens first,
    then the digits (0 last), then the F-keys by their number (F1 help ... F10)."""
    pages: list[type[Page]] = [HomePage, QuestionsPage, HistoryPage, OperationsPage, RecordsPage, HelpPage]
    pages += [page for component in registry.components() if component.console for page in component.console()]
    return sorted(pages, key=lambda page: place(page.ENTRY))


PAGES = _pages_in_order()
DIGITS = {page.ENTRY.key: page.ENTRY.id for page in PAGES if page.ENTRY.key.isdigit()}
ACT_ANYWHERE = {key.key for key in (*ANYWHERE, PALETTE)}  # pressed by a button, they run their binding's action


def _bindings() -> list[BindingType]:
    """Each page's key, the keys that act anywhere (`keys.ANYWHERE`, the keys bar's words), and the arrows; the keys
    bar draws the keys itself (`KeysBar`), so no binding shows in a footer."""
    keys: list[Binding] = []
    for page in PAGES:
        entry = page.ENTRY
        if not entry.key:
            continue  # a page reached from the menu and Ctrl+P alone (Setup: F11 is the terminal's full screen)
        action = f"key('{entry.key}')" if entry.key in DIGITS else f"page('{entry.id}')"
        keys.append(Binding(entry.key.lower(), action, entry.label.lower(), show=False))
    bound = {binding.key for binding in keys} | {"escape"}  # Esc is `on_key`'s, after a page's field took its own
    keys += [Binding(key.key, key.action, key.words, show=False) for key in ANYWHERE if key.key not in bound]
    return [
        *keys,
        # After the focused widget's own: an input keeps its arrows, and a page scrolls sideways when it can.
        Binding("right", "inward", "into the page", show=False),
        Binding("left", "outward", "back to the menu", show=False),
    ]


class ClankConsole(App[str]):
    """Clank's console."""

    TITLE = "Clank"
    BINDINGS: ClassVar[list[BindingType]] = _bindings()
    HORIZONTAL_BREAKPOINTS = [(0, "-small"), (SMALL_FROM, "-narrow"), (MACHINE_FROM, "-wide"), (WIDER_FROM, "-wider")]  # noqa: RUF012
    COMMANDS = App.COMMANDS | {ClankCommands}

    def __init__(
        self,
        client: Client,
        *,
        now: Callable[[], datetime] | None = None,
        zone: tzinfo | None = None,
        page: str = "home",
        view: str = "",
        home: Home | None = None,
        snapshot: bool = False,
        folder: str | None = None,
        terminal: Terminal | None = None,
        guide: bool = False,
        record: Path | None = None,
    ) -> None:
        self.home = home or Home.resolve()
        self.folder = str(Path(folder or os.getcwd()).resolve())
        self.terminal = terminal  # None: `clank.console.terminal.attached`, looked up when a program starts
        user = self.home.config / "console.tcss"
        styles: list[str | PurePath] = [CLANK_TCSS, user] if user.is_file() else [CLANK_TCSS]
        super().__init__(css_path=styles, watch_css=user.is_file())
        self.animation_level = "none"
        self.style = load_style(self.home)
        self._forgotten = forget_theme(self.home)
        use(self.style)
        self.register_theme(theme_of(self.style))
        self.theme = self.style.name
        self.client = client
        self.now = now or (lambda: datetime.now(UTC))
        self.zone = zone
        self.data = ConsoleData()
        self.redraws = 0
        self.presence_sent = 0
        self._presence_at: float | None = None
        self._updates: queue.Queue[Update] = queue.Queue()
        self._follower = Follower(client, None, self._updates)
        self._page = page
        self._view = view  # the view a page with views opens on (the Monitor's flow), if any
        self._snapshot = snapshot
        self._guide = guide  # no page named: Add a model in place of This folder or Home while no model is usable
        self._heard = False
        self._loaded = False
        self._finishing = False
        self._shown_header = ("", "")
        self.frame = 0  # the spinner's
        self._menu_shown: dict[str, str] = {}  # each menu entry as last drawn
        self._hinted: Content | None = None  # what the message line says of the focused button, until a message
        self._before_bar: Widget | None = None  # what had the focus before the keys bar
        self._left: dict[str, Widget] = {}  # where the focus was in each page when it was last in it
        self._record_to = record  # the folder a recording of what the console draws goes to (decision 0126), if any
        self._pages_found: dict[str, Page] = {}  # each page by its id, as found (`_page_of`)
        self.recording: Recording | None = None

    def compose(self) -> ComposeResult:
        """The header, the menu beside the pages, and the keys bar."""
        with Horizontal(id="header"):
            yield Label(id="header-left")
            yield Label(id="header-clock")
        with Horizontal(id="body"):
            items = list(self._menu())
            first = next((n for n, item in enumerate(items) if item.id == f"menu-{self._page}"), 0)
            yield ListView(*items, id="menu", initial_index=first)
            with ContentSwitcher(id="pages", initial=f"page-{self._page}"):
                yield from self._pages()
            yield MachineColumn(id="machine")
        yield Label(id="message")
        yield KeysBar(id="keys")

    def on_mount(self) -> None:
        """Start following the service, and draw at most REDRAWS_PER_SECOND times a second. The focus starts on the
        menu (design 0011 §12.5), not on the first group Textual finds, which is the keys bar."""
        self.query_one("#menu", ListView).focus()
        threading.Thread(target=self._follower.run, name="console-follower", daemon=True).start()
        self.set_interval(1 / REDRAWS_PER_SECOND, self._drain)
        self.set_interval(SPIN_SECONDS, self._spin)
        self.set_interval(ACTIVITY_SECONDS, self._read_activity)
        self._draw_header()
        self.show_page(self._page)
        page = self._current()
        if self._view and self._view in getattr(page, "VIEWS", ()) and hasattr(page, "show_view"):
            page.show_view(self._view)
        if self._forgotten:
            self.say(f"the console's colors are now its style's, not Textual's theme {self._forgotten} picked before: "
                     "Ctrl+P, Change style, picks another")  # fmt: skip
        if self.style.problem:
            self.say(self.style.problem, error=True)
        if self._record_to is not None and not self._snapshot:
            self._start_recording(self._record_to)

    def _start_recording(self, folder: Path) -> None:
        """Record every write the console sends the terminal from here on (decision 0126), the whole screen drawn again
        first; kept to disk every second, in parts."""
        driver = self._driver
        if driver is None:
            return
        recording = self.recording = Recording(folder, "console", self.size.width, self.size.height)
        original = driver.write

        def write(data: str) -> None:
            recording.output(data)
            original(data)

        driver.write = write  # type: ignore[method-assign]
        self.set_interval(1.0, self._keep_recording)
        self.refresh(repaint=True, layout=True)

    def _keep_recording(self) -> None:
        recording = self.recording
        if recording is None:
            return
        recording.keep()
        if recording.due():
            recording.next_part(self.size.width, self.size.height)
            self.refresh(repaint=True, layout=True)  # the new part begins with the whole screen

    def on_resize(self, event: events.Resize) -> None:
        """A recording keeps the terminal's new size (the console draws itself whole again for it)."""
        if self.recording is not None:
            self.recording.resized(event.size.width, event.size.height)

    def on_unmount(self) -> None:
        """Stop following the service; close the recording, if one is kept."""
        self._follower.stop()
        if self.recording is not None:
            self.recording.close()

    def raise_limits(self) -> None:
        """The cloud's cost limits in a form, as they are; sent as typed (`PUT /gateway/cost/limits`), the service
        checking them, and the pause lifted once a limit is raised past what was spent."""
        cost = self.data.cost or {}
        limits = cost.get("limits") or {}

        def shown(value: float | None) -> str:
            return "" if value is None else f"{value:g}"

        fields = [
            Field("day", "A day's limit, US dollars (empty: none)", "5", shown(limits.get("day_usd"))),
            Field("month", "A month's limit, US dollars (empty: none)", "50", shown(limits.get("month_usd"))),
        ]
        note = f"{(cost.get('paused') or {}).get('said') or cost.get('said', '')}. Ctrl+S sends these; Esc leaves them."
        client = self.client

        def given(values: dict[str, str] | None) -> None:
            if values is None:
                return
            try:
                body = {"day_usd": dollars(values["day"]), "month_usd": dollars(values["month"])}
            except ValueError as error:
                self.say(str(error), True)
                return
            actions.call(self, lambda: client.put("gateway/cost/limits", body), done="the cost limits are sent")

        self.push_screen(FormScreen("The cloud's cost limits", fields, note), given)

    def show_page(self, id: str) -> None:
        """Bring a page on screen, drawn whole, with its menu entry highlighted."""
        if self._page_of(id) is None:
            return
        self._page = id
        self.query_one("#pages", ContentSwitcher).current = f"page-{id}"
        self._current().show(self.data, {"all"})
        self.query_one("#keys", KeysBar).show_keys(self._current().shown_keys())
        machine = self.query_one("#machine", MachineColumn)
        hidden = not machine.display
        self.screen.set_class(not self._current().MACHINE_COLUMN, "-no-machine-column")
        self.screen.set_class(not self._current().MENU_COLUMN, "-no-menu-column")
        if hidden and machine.display:
            self._draw_machine()  # it drew nothing while hidden
        menu = self.query_one("#menu", ListView)
        if self.focused is menu and self.menu_hidden():
            self.call_after_refresh(self.action_inward)  # a hidden menu keeps no focus: the page takes it
        index = list(menu.children).index(self.query_one(f"#menu-{id}"))
        if menu.index != index:
            menu.index = index

    def entries(self) -> list[MenuEntry]:
        """Every menu entry: the pages the console has, then the planned ones."""
        return [page.ENTRY for page in PAGES] + PLANNED

    def ask_docker(self, stop: bool) -> None:
        """Ask the service to start Docker, or to stop it (which asks first when others' containers run)."""
        client = self.client
        actions.call(
            self,
            lambda: client.post("docker/stop" if stop else "docker/start"),
            done=f"asked Docker to {'stop' if stop else 'start'}",
        )

    @property
    def activity(self) -> dict[str, Any] | None:
        """The gateway's activity, as last read."""
        return self.data.activity

    def seen(self) -> Seen:
        """What the machine column and the spinner go by."""
        return Seen(self.data.meters, self.data.operations, self.activity, self.frame, self.zone)

    def busy(self) -> bool:
        """Whether something runs that a spinner shows: an operation, a model request, or the page's own steps."""
        return busy(self.seen()) or self._current().busy

    def menu_hidden(self) -> bool:
        """Whether the menu is hidden now: by Ctrl+B, or beside a page that takes the whole width (as its classes say,
        before the screen is drawn again)."""
        screen = self.screen
        if screen.has_class("-menu-focus"):
            return False
        if screen.has_class("-menu-off"):
            return True
        return not self._current().MENU_COLUMN and not screen.has_class("-menu-on")

    def action_menu(self) -> None:
        """Ctrl+B: show the menu on the left, or hide it, on any page (decision 0125); a hidden menu's focus goes into
        the page."""
        hiding = not self.menu_hidden()
        self.screen.set_class(hiding, "-menu-off")
        self.screen.set_class(not hiding, "-menu-on")
        if hiding and self.focused is self.query_one("#menu", ListView):
            self.call_after_refresh(self.action_inward)

    def action_to_menu(self) -> None:
        """Esc: back to the menu, from anywhere in a page, the page staying as it was (decision 0129); the menu shows
        while it has the focus, beside a page that hides it too."""
        self._present()
        menu = self.query_one("#menu", ListView)
        self.screen.set_class(True, "-menu-focus")
        menu.focus()

    def action_machine(self) -> None:
        """F5: show the machine column, or hide it, whatever the terminal's width."""
        shown = self.query_one("#machine").display
        self.screen.set_class(shown, "-machine-off")
        self.screen.set_class(not shown, "-machine-on")
        self._draw_machine()

    def run_doctor(self) -> None:
        """Ask the service to run the doctor."""
        client = self.client
        actions.call(self, lambda: client.post("machine/doctor"), done="the doctor runs")

    def action_explain(self) -> None:
        """Explain what has the focus: a menu entry, or what the page on screen says about its own focus."""
        self._present()
        if isinstance(self.screen, DetailsScreen):
            self.screen.dismiss()
            return
        focused = self.focused
        if isinstance(focused, KeysBar) and focused.current is not None and focused.current.key.key == "question_mark":
            focused = self._before_bar  # the keys bar's own `?`: what had the focus before it
        if isinstance(focused, Buttons) and focused.current is not None:
            title, lines = explain_button(focused.current, focused.reason(focused.current))
            self.push_screen(DetailsScreen(title, lines))
            return
        menu = self.query_one("#menu", ListView)
        highlighted = menu.highlighted_child
        if focused is menu and highlighted is not None and highlighted.id:
            entry = next(entry for entry in self.entries() if f"menu-{entry.id}" == highlighted.id)
            title, lines = entry.explanation()
            page = next((page for page in PAGES if page.ENTRY.id == entry.id), None)
        else:
            title, lines = self._current().explain()
            page = type(self._current())
        if page is not None and page.KEYS:
            lines = [*lines, f"Its keys: {' · '.join(said(key) for key in page.KEYS)}."]
        self.push_screen(DetailsScreen(title, [line for line in lines if line]))

    def get_system_commands(self, screen: Screen[Any]) -> Iterable[SystemCommand]:
        """Textual's own commands but its themes: the console's colors are its style's ("Change style")."""
        return [command for command in super().get_system_commands(screen) if command.title != "Theme"]

    def pick_style(self) -> None:
        """Ctrl+P, "Change style": the styles the service has, Clank's and yours; the one picked is written to the
        console's settings through the service, which reports the change, and the console then draws in it."""
        client = self.client

        def picked(name: str | None) -> None:
            if name is None:
                return

            def write() -> Any:
                found = client.get("records/console/console")
                values = {**found["values"], "style": name}
                return client.put("records/console/console", {"values": values, "base": found["revision"]})

            actions.call(self, write, done=f"the console's style is now {name}")

        def listed() -> None:
            try:
                styles = client.get("records/style")
            except (NotRunning, ClientError) as error:
                self.call_from_thread(self.say, f"the styles could not be read: {error}", True)
                return
            choices = [
                Choice(style["id"], style["title"], ("yours" if style["source"] == "user" else "Clank's")
                       + (", in force" if style["id"] == self.style.name else ""))
                for style in styles
            ]  # fmt: skip
            self.call_from_thread(self.push_screen, PickScreen("The console's style", choices), picked)

        self.run_worker(listed, thread=True, group="styles", exclusive=True, exit_on_error=False)

    def restyle(self) -> None:
        """Draw in the style the settings pick now, read again; a file that no longer reads leaves the style in force,
        and the message line says why."""
        loaded = load_style(self.home, self.style)
        if loaded.problem:
            self.say(loaded.problem, error=True)
        unchanged = (loaded.name, loaded.style) == (self.style.name, self.style.style)
        self.style = loaded
        if unchanged:
            return
        use(loaded)
        self.register_theme(theme_of(loaded))
        if self.theme == loaded.name:
            self.refresh_css(animate=False)  # the same name, new values
        else:
            self.theme = loaded.name
        self._menu_shown.clear()  # every mark is drawn again in the style's glyphs
        self._shown_header = ("", "")
        self._draw_header()
        self._draw_menu()
        self._draw_machine()
        self._current().show(self.data, {"all"})
        # Text that names an element (`$clank-key` on the keys bar, in Help's lines) reads its color as it is drawn,
        # but Textual draws a widget again only when its own rules change: every widget is drawn again.
        for screen in self.screen_stack:
            for widget in screen.walk_children(Widget):
                widget.refresh()

    def say(self, text: str, error: bool = False) -> None:
        """Put a message on the message line, above the keys, until the next one."""
        line = self.query_one("#message", Label)
        line.update(f"{clock(self.now(), self.zone)}  {'! ' if error else ''}{text}")
        line.set_class(error, "error")
        self._hinted = None

    def hint(self, pressed: Button, reason: str) -> None:
        """While a group has the focus (design 0011 §12.6): what its focused button does and how it is pressed, in
        `quiet`, or why it cannot act now, in `attention`; cut to the line's one row with the style's mark. Nothing
        while the console is taken down."""
        line = next(iter(self.query("#message").results(Label)), None)
        if line is None:
            return
        if reason:
            text = f"{pressed.label} {pressed.said}: {reason}"
        else:
            typed = "" if pressed.key.key in ("enter", "space") else f", {pressed.label}"
            what = pressed.key.help or pressed.said
            text = f"{pressed.label} {pressed.said}: {what} · Enter, Space{typed} or a click"
        self._hinted = Content(fit(text, max(self.size.width - 2, 1)))  # the line is the screen's width, less padding
        line.update(self._hinted)
        line.set_class(bool(reason), "error")

    def unhint(self) -> None:
        """The focus left the groups: what the message line said of a button goes, unless a message came since."""
        line = next(iter(self.query("#message").results(Label)), None)
        if self._hinted is None or line is None:
            return
        line.update("")
        line.set_class(False, "error")
        self._hinted = None

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Remember what had the focus before the keys bar, for the keys bar's own `?`, and where the focus was in the
        page on screen, for when the focus comes back into it; none while the pages are taken down, as the console
        quits."""
        if not isinstance(event.widget, KeysBar):
            self._before_bar = event.widget
        if not self.screen_stack:
            return  # the console is quitting: its screens are taken down, and a focus still heard has nothing to tidy
        screen = self.screen  # the menu Esc showed hides again once the focus is elsewhere (as it is now)
        if not screen.is_modal and (screen.focused is None or screen.focused.id != "menu"):
            screen.remove_class("-menu-focus")
        page = self._shown_page()
        if page is not None and page in event.widget.ancestors:
            self._left[self._page] = event.widget

    def action_page(self, id: str) -> None:
        """Open a page."""
        self._present()
        self.show_page(id)

    def action_key(self, key: str) -> None:
        """A digit: the page's when the focus is in it and the page acts on it, else the page with that key."""
        self._present()
        window = self._details()
        if self._focus_in_page() and self.press_page_key(key):
            self._close(window)
            return
        self.show_page(DIGITS[key])

    def press_button(self, pressed: Button) -> None:
        """A button pressed by Enter, Space or a click (design 0011 §12.3): the same as its key."""
        self.press_key(pressed.key)

    def press_key(self, key: PageKey) -> None:
        """A key pressed by its button: one that acts anywhere runs its binding's action (`?`, F1, F5, `q`, Ctrl+P);
        a key of several says which keys it stands for; a page's key goes through the page's door."""
        self._present()
        if key.key in ACT_ANYWHERE:
            self._flash(key.key)
            self.call_later(self.run_action, key.action)
            return
        if " " in key.key:
            self.say(f"{key.key} {key.words}: press one of the keys it stands for")
            return
        self.press_page_key(key.key)

    def press_page_key(self, key: str) -> bool:
        """The one door of a page's key, typed or pressed (design 0011 §12.3, §12.7): when the page says the key cannot
        act now, why, on the message line, and the page is not pressed; else the page's `press`. A key acted on shows
        pressed on every group that shows it. True when the key was taken."""
        page = self._current()
        reason = page.unable(key) if self.screen is page.screen else ""
        if reason:
            self.say(f"{shown(key)}: {reason}", True)
            return True
        acted = page.press(key)
        if acted:
            self._flash(key)
        return acted

    def unable_button(self, pressed: Button) -> str:
        """Why a button cannot act now: its page's word for its key ("" when it can, and for a key that acts anywhere
        or stands for several)."""
        page = self._shown_page()
        if pressed.key.key in ACT_ANYWHERE or " " in pressed.key.key or page is None:
            return ""
        return page.unable(pressed.key.key)

    def _flash(self, key: str) -> None:
        """Every group on the screen that shows this key shows it pressed, for a moment; a group in a list's row only
        when it is clicked (another row's `y` is not the one a typed `y` answers)."""
        for group in self.screen.query(Buttons).results(Buttons):
            if group.can_focus:
                group.flash(key)

    def action_inward(self) -> None:
        """Right: from the menu into the page on screen (where the focus was when the page was left, else its main
        list: design 0011 §12.5), and in the page on to its next list."""
        self._present()
        stops = self._stops()
        if self.focused not in stops:
            left = self._left.get(self._page)
            (left if left in stops else self.main()).focus()
            return
        later = stops[stops.index(self.focused) + 1 :]
        if later:
            later[0].focus()

    def action_outward(self) -> None:
        """Left: in the page back to its previous list, and from its first to the menu."""
        self._present()
        if not self._focus_in_page():
            return
        stops = self._stops()
        index = stops.index(self.focused) if self.focused in stops else 0
        if index > 0:
            stops[index - 1].focus()
        else:
            self.action_to_menu()

    def main(self) -> Widget:
        """The page's main list (design 0011 §12.4): the first of its stops that is not a group of buttons, else its
        first stop (its first group, or the page itself)."""
        stops = self._stops()
        return next((widget for widget in stops if not isinstance(widget, Buttons)), stops[0])

    def to_main(self) -> None:
        """Esc on a group of buttons: back to the page's main list."""
        self.main().focus()

    def into_page(self) -> None:
        """↑ on the keys bar: back into the page, to its main list."""
        self.main().focus()

    def on_key(self, event: events.Key) -> None:
        """A key the focused widget did not take goes to the page on screen, through its door (`press_page_key`); a
        digit is left to its binding (`action_key`), which gives it to the page only while the focus is in it; while the
        cloud is paused at its spending limit, `L` anywhere opens the limits (design 0016 §11)."""
        self._present()
        if event.key == "L" and (self.data.cost or {}).get("paused"):
            event.stop()
            self.raise_limits()
            return
        if event.key in DIGITS:
            return
        if event.key == "escape" and not self.screen.is_modal:
            event.stop()  # a page's field takes it first (History's filter, Add a model's search); else the menu
            if not self.press_page_key("escape"):
                self.action_to_menu()
            return
        window = self._details()
        if self.press_page_key(event.key):
            event.stop()
            self._close(window)
        elif event.key == "enter" and self.focused is self.query_one("#menu", ListView):
            event.stop()
            event.prevent_default()  # the list the focus goes to must not take this Enter too
            self.action_inward()  # Enter on the menu goes into the page, as Right does

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Open the page under the menu's highlight; one a newer highlight overtook before it was heard is left, since
        opening its page would take the menu back to it."""
        menu = event.list_view
        if menu.id == "menu" and event.item is not None and event.item.id and event.item is menu.highlighted_child:
            self.show_page(event.item.id.removeprefix("menu-"))

    def _menu(self) -> Iterator[ListItem]:
        for page in PAGES:
            entry = page.ENTRY
            yield ListItem(Label(menu_name(entry, MENU_NAME)), id=f"menu-{entry.id}", classes="page")
        yield ListItem(Label("coming"), id="menu-coming", classes="divider", disabled=True)
        for entry in PLANNED:
            yield ListItem(Label(f"{entry.label:<22}{entry.milestone}"), id=f"menu-{entry.id}", classes="planned")

    def _pages(self) -> Iterator[Page]:
        for page in PAGES:
            if page is HelpPage:
                yield HelpPage(PAGES, PLANNED, id="page-help")
            else:
                yield page(id=f"page-{page.ENTRY.id}")
        for entry in PLANNED:
            yield PlannedPage(entry)

    def _page_of(self, id: str) -> Page | None:
        """A page by its id, from an index kept as pages are found: a search of the whole console takes a while (every
        page's widgets are in it), and the buttons ask for the page on screen many times a frame, the menu for each
        page's badge four times a second. None while the pages are taken down (as the console quits)."""
        found = self._pages_found.get(id)
        if found is not None and found.is_attached:
            return found
        found = next(iter(self.query(f"#page-{id}").results(Page)), None)
        if found is not None:
            self._pages_found[id] = found
        return found

    def _current(self) -> Page:
        found = self._page_of(self._page)
        return found if found is not None else self.query_one(f"#page-{self._page}", Page)

    def _shown_page(self) -> Page | None:
        """The page on screen, or None while the pages are taken down (as the console quits), for what the focus moving
        then asks of it."""
        return self._page_of(self._page) if self._page else None

    def _stops(self) -> list[Widget]:
        """Where Left and Right move the focus in the page on screen: what in it takes the focus, in order, or the page
        itself when nothing in it does (so that Up and Down scroll it)."""
        page = self._current()
        inside = [widget for widget in self.screen.focus_chain if widget is not page and page in widget.ancestors]
        return inside or [page]

    def _focus_in_page(self) -> bool:
        focused = self.focused
        return focused is not None and self._current() in focused.ancestors_with_self

    def _details(self) -> DetailsScreen | None:
        """The details window on screen, if any."""
        return self.screen if isinstance(self.screen, DetailsScreen) else None

    def _close(self, shown: DetailsScreen | None) -> None:
        """Close the details window that was open when a key the page acted on was pressed (an answer given from a
        question's window); a window the key itself opened stays."""
        if shown is not None and self.screen is shown:
            shown.dismiss()

    def _present(self) -> None:
        moment = time.monotonic()
        if self._presence_at is not None and moment - self._presence_at < PRESENCE_SECONDS:
            return
        self._presence_at = moment
        self.presence_sent += 1
        client = self.client
        actions.call(self, lambda: client.post("presence"), quiet=True)

    def _drain(self) -> None:
        if not self.is_running:  # shutting down: the widgets are being removed
            return
        changed: set[str] = set()
        restyled = False
        while True:
            try:
                update = self._updates.get_nowait()
            except queue.Empty:
                break
            changed |= apply(self.data, update)
            restyled = restyled or (update.topic == "event" and restyles(update.data))
            if update.topic in ("all", "connection"):
                self._heard = True
            if update.topic == "all":
                self._loaded = True
        if restyled:
            self.restyle()
        if self._guide and self.data.usable is not None:
            self._open_guide()
        self._current().tick()  # a page that reads on its own draws what came, in this rhythm (the Monitor)
        self._draw_header()  # after it: what the page drew may make it busy, which the header shows
        self._draw_menu()  # a page's own reads change its badge too (This folder's steps)
        if type(self._current()).unable is not Page.unable:  # its keys may come to act, or stop: dimmed or not
            self.query_one("#keys", KeysBar).recheck()
        if not changed:
            return
        self.redraws += 1
        if changed & MACHINE_TOPICS:
            self._draw_machine()
        self._current().show(self.data, changed)
        if self._snapshot and self._loaded and not self._finishing:
            self._finishing = True
            self.call_after_refresh(lambda: self.exit(render_text(self)))

    def _open_guide(self) -> None:
        """Once, at the start, in place of This folder or Home: Setup while anything it needs is missing that This
        folder does not put right itself (decision 0148); else Add a model when no model is usable (decision 0105)."""
        self._guide = False
        if self._page not in ("folder", "home"):
            return
        setup = self.data.setup
        if setup is not None and setup.get("opens", not setup.get("ready", True)) and self.query("#page-setup"):
            self.show_page("setup")
            return
        usable = (self.data.usable or {}).get("usable", True)
        if usable or not self.query("#page-addmodel"):
            return
        self.show_page("addmodel")
        page: Any = self.query_one("#page-addmodel")
        page.start()

    def refreshed(self, topic: str, value: Any) -> None:
        """A topic a page read again itself (Setup's `r`), applied as the follower's readings are, at the next tick."""
        self._updates.put(Update(topic, value))

    def _draw_header(self) -> None:
        frame = self.frame if self._heard and self.busy() else None
        width = self.query_one("#header-left").size.width
        left = header(self.data, self.activity, self.now(), self._heard, frame, self.folder, width)
        shown = (left.plain, clock(self.now(), self.zone))
        if shown != self._shown_header:
            self._shown_header = shown
            self.query_one("#header-left", Label).update(left)
            self.query_one("#header-clock", Label).update(shown[1])

    def _draw_menu(self) -> None:
        """Each menu entry with its page's badge, drawn again only where it changed."""
        room = SMALL_NAME if self.screen.has_class("-small") else MENU_NAME
        for page in PAGES:
            entry = page.ENTRY
            found = self._page_of(entry.id)
            badge = found.badge(self.frame) if found is not None else None
            name = menu_name(entry, room)
            shown = Content.assemble(name, " " * (room - name.cell_length + 1), badge) if badge is not None else name
            if self._menu_shown.get(entry.id) != shown.markup:
                self._menu_shown[entry.id] = shown.markup
                self.query_one(f"#menu-{entry.id} Label", Label).update(shown)

    def _draw_machine(self, machine: bool = True) -> None:
        column = self.query_one("#machine", MachineColumn)
        if column.display:
            column.draw(self.seen(), machine)

    def _spin(self) -> None:
        """Turn the spinner while something runs: the header, the machine column's "Clank now" and the page."""
        if not self.is_running or not self.busy():
            return
        self.frame += 1
        self._draw_header()
        self._draw_machine(machine=False)
        self._current().spin(self.frame)
        self._draw_menu()

    def _read_activity(self) -> None:
        """Read the gateway's activity off the screen's thread."""
        if not self.data.connected:
            return
        client = self.client

        def work() -> None:
            try:
                found = client.get("gateway/activity")
            except Exception:
                found = None
            self.call_from_thread(self._read_done, found)

        self.run_worker(work, thread=True, group="activity", exclusive=True, exit_on_error=False)

    def _read_done(self, found: dict[str, Any] | None) -> None:
        if found == self.data.activity or not self.is_running:
            return
        self.data.activity = found
        self._draw_header()
        self._draw_machine(machine=False)
        self._current().show(self.data, {"activity"})


def explain_button(pressed: Button, reason: str) -> tuple[str, list[str]]:
    """What `?` says of a focused button (design 0011 §12.4): what it does, and the keys that press it or why it
    cannot act now."""
    if reason:
        how = f"It cannot act now: {reason}."
    else:
        ways = ["Enter or Space while it has the focus"]
        if " " in pressed.key.key:
            ways.append(f"one of the keys it stands for ({pressed.label}) from anywhere on this page")
        elif pressed.key.key not in ("enter", "space"):
            ways.append(f"{pressed.label} from anywhere on this page")
        how = f"Pressed by {', by '.join(ways)}, or by a click."
    return f"{pressed.label} {pressed.said}", [pressed.key.help or pressed.said, how]


def menu_name(entry: MenuEntry, room: int) -> Content:
    """A page's menu entry, its key in `key` and its name, cut to `room` columns (its name alone for a page without a
    key of its own)."""
    if not entry.key:
        return Content(fit(entry.label, room))
    name = fit(f"{entry.key} {entry.label}", room)
    return Content.assemble((name[: len(entry.key)], "$clank-key"), name[len(entry.key) :])


def restyles(event: dict[str, Any]) -> bool:
    """Whether an event reports a change of the console's style: of its settings, or of a style's file."""
    data = event.get("data") or {}
    if event["type"] == "settings.changed":
        return data.get("kind") in ("console", "style")
    if event["type"] == "settings.invalid":
        file = str(data.get("file") or "")
        return file == "config/console.json" or file.startswith("config/styles/")
    return False
