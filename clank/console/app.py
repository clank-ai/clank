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
(`keys.KeysBar`) shows the keys of the page on screen, wherever the focus is, then the keys that act anywhere (`?`, F1,
F5, `q`, Ctrl+P), as each page declares them (`Page.KEYS`, design 0011 §7); a page's digit is beside it in the menu, its
key in the style's `key`. A digit opens the page with that key, unless the focus is in the page and the page acts on it
(a numbered option of a question); other keys go to the page on screen. A key pressed tells the service the user is
here, at most once a minute (design 0002 §2.7). What an action did, or why it failed, shows on the message line above
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
(`guide`, a bare `clank` or `clank console`), it opens Add a model in place of This folder or Home once it has read
that no model is usable (design 0016 §14, decision 0105).
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
from clank.console.commands import ClankCommands
from clank.console.data import ConsoleData, Follower, Update, apply
from clank.console.details import DetailsScreen
from clank.console.form import Field, FormScreen
from clank.console.gauges import fit
from clank.console.header import header
from clank.console.keys import ANYWHERE, KeysBar, said
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


def _bindings() -> list[BindingType]:
    """Each page's key, the keys that act anywhere (`keys.ANYWHERE`, the keys bar's words), and the arrows; the keys
    bar draws the keys itself (`KeysBar`), so no binding shows in a footer."""
    keys: list[Binding] = []
    for page in PAGES:
        entry = page.ENTRY
        action = f"key('{entry.key}')" if entry.key in DIGITS else f"page('{entry.id}')"
        keys.append(Binding(entry.key.lower(), action, entry.label.lower(), show=False))
    bound = {binding.key for binding in keys}
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
        """Start following the service, and draw at most REDRAWS_PER_SECOND times a second."""
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

    def on_unmount(self) -> None:
        """Stop following the service."""
        self._follower.stop()

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
        if not self.query(f"#page-{id}"):
            return
        self._page = id
        self.query_one("#pages", ContentSwitcher).current = f"page-{id}"
        self._current().show(self.data, {"all"})
        self.query_one("#keys", KeysBar).show(self._current().shown_keys())
        machine = self.query_one("#machine", MachineColumn)
        hidden = not machine.display
        self.screen.set_class(not self._current().MACHINE_COLUMN, "-no-machine-column")
        if hidden and machine.display:
            self._draw_machine()  # it drew nothing while hidden
        menu = self.query_one("#menu", ListView)
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
        menu = self.query_one("#menu", ListView)
        highlighted = menu.highlighted_child
        if self.focused is menu and highlighted is not None and highlighted.id:
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

    def action_page(self, id: str) -> None:
        """Open a page."""
        self._present()
        self.show_page(id)

    def action_key(self, key: str) -> None:
        """A digit: the page's when the focus is in it and the page acts on it, else the page with that key."""
        self._present()
        shown = self._details()
        if self._focus_in_page() and self._current().press(key):
            self._close(shown)
            return
        self.show_page(DIGITS[key])

    def action_inward(self) -> None:
        """Right: from the menu into the page on screen, and in the page on to its next list."""
        self._present()
        stops = self._stops()
        if self.focused not in stops:
            stops[0].focus()
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
        (stops[index - 1] if index > 0 else self.query_one("#menu", ListView)).focus()

    def on_key(self, event: events.Key) -> None:
        """A key no binding took goes to the page on screen; while the cloud is paused at its spending limit, `L`
        anywhere opens the limits (design 0016 §11)."""
        self._present()
        shown = self._details()
        if event.key == "L" and (self.data.cost or {}).get("paused"):
            event.stop()
            self.raise_limits()
            return
        if self._current().press(event.key):
            event.stop()
            self._close(shown)

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

    def _current(self) -> Page:
        return self.query_one(f"#page-{self._page}", Page)

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
        """Once, at the start: Add a model in place of This folder or Home when no model is usable (decision 0105)."""
        self._guide = False
        usable = (self.data.usable or {}).get("usable", True)
        if usable or self._page not in ("folder", "home") or not self.query("#page-addmodel"):
            return
        self.show_page("addmodel")
        page: Any = self.query_one("#page-addmodel")
        page.start()

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
            badge = self.query_one(f"#page-{entry.id}", Page).badge(self.frame)
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


def menu_name(entry: MenuEntry, room: int) -> Content:
    """A page's menu entry, its key in `key` and its name, cut to `room` columns."""
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
