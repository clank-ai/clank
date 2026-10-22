"""The console's pages: one per menu entry, each a widget that draws part of what the console holds (design 0001
§5.6: small modules, each with the data it needs and how it draws itself).

A page declares its menu entry (`ENTRY`), its panels by id, in the order it draws them (`PANELS`, design 0011 §4, so
that M2's Layout page can show and rearrange them), and its keys, once, as named actions with their words (`KEYS`,
design 0011 §7: the keys bar, Help and `?` read them, and M2's `keys.json` will remap them), most used first, since a
narrow keys bar drops them from the right; it draws itself in `draw`. A page whose panels need the room (the Monitor,
design 0012 §2) hides the machine column until F5 shows it (`MACHINE_COLUMN`). The console calls `show` with what
changed, at most four times a second, while the page is on screen (and with everything when it comes on screen); a
page draws nothing until its own widgets are mounted, and then draws everything the console holds. Keys meant for the
page reach its `press`, which says whether it acted on them; every key does, the menu's too, before the shell's own
bindings act on it (so a page may take its own menu key, pressed again on it: the Monitor's next view). The keys bar
shows the keys of the page as it stands (`shown_keys`: its `KEYS`, or a view's).

A page scrolls down, and sideways too when one of its panels is wider than the page: a panel is never narrower than
its title (`Panel`), so with the machine column in a narrow window (F5 at 80 columns leaves the page 20 columns, 18
beside its vertical scroll bar) the page scrolls sideways rather than cut a title or clip a line (design 0011 §9).
Textual's `VerticalScroll` hides what stands beyond its right edge, hence `overflow-x: auto`, and `_refresh_scrollbars`
shows the sideways bar in the one case Textual's own decision misses (its docstring says which).
"""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from textual.containers import VerticalScroll
from textual.content import Content

from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry

if TYPE_CHECKING:
    from clank.console.app import ClankConsole


class Page(VerticalScroll):
    """A page of the console."""

    DEFAULT_CSS = """
    Page {
        overflow-x: auto;
    }
    """

    ENTRY: ClassVar[MenuEntry]
    PANELS: ClassVar[tuple[str, ...]] = ()  # its panels' ids, in order
    KEYS: ClassVar[tuple[PageKey, ...]] = ()  # its own keys, most used first
    MACHINE_COLUMN: ClassVar[bool] = True  # the machine column beside it by the width; False: hidden until F5
    MENU_COLUMN: ClassVar[bool] = True  # the menu beside it; False: hidden until Ctrl+B (decision 0125)
    _ready = False

    @property
    def console(self) -> "ClankConsole":
        """The console this page is in."""
        return cast("ClankConsole", self.app)

    def _refresh_scrollbars(self) -> None:
        """Show the scroll bars Textual decides, and the sideways one where it misses it. Textual (8.2.8,
        `Widget._refresh_scrollbars`) compares the page's content with the page's whole width, then, once the vertical
        bar shows, with that width less the bar's; but a guard against flicker skips that second look when the same
        first look flipped the bars before, and nothing looks again until the page's size changes. A panel wider than
        the page by no more than the vertical bar's two columns then stands partly under that bar, where no scroll
        reaches it. This shows the sideways bar then, which changes no width, so nothing flickers."""
        super()._refresh_scrollbars()
        missed = (
            self.styles.overflow_x == "auto" and self.show_vertical_scrollbar and not self.show_horizontal_scrollbar
        )
        if missed and self.virtual_size.width > self.container_size.width - self.styles.scrollbar_size_vertical:
            self.show_horizontal_scrollbar = True
            self.horizontal_scrollbar.display = True

    def on_mount(self) -> None:
        """Draw everything the console holds, now that the page's widgets are mounted."""
        self._ready = True
        data: Any = getattr(self.app, "data", None)
        if isinstance(data, ConsoleData):
            self.draw(data, {"all"})

    def show(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw what changed, once the page's widgets are mounted."""
        if self._ready:
            self.draw(data, changed)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw what changed; `changed` holds "all" when everything should be drawn."""

    @property
    def busy(self) -> bool:
        """Whether the page runs something of its own a spinner should show (the console's own work it knows)."""
        return False

    def badge(self, frame: int) -> Content | None:
        """What the page says beside its menu entry, briefly (a count, a dot in a state's color, a spinner while its
        work runs), from the console's data; None when it has nothing to say."""
        return None

    def tick(self) -> None:
        """Called on each of the console's redraw ticks (at most four a second) while the page is on screen: a page
        that reads the service on its own draws what its readings brought here, so it redraws no more often than the
        console does (design 0001 §5.7)."""

    def spin(self, frame: int) -> None:
        """Turn the page's spinners to `frame`; called a few times a second while something runs."""

    def press(self, key: str) -> bool:
        """Act on a key meant for this page; False when the page has nothing to do with it."""
        return False

    def unable(self, key: str) -> str:
        """Why one of the page's keys cannot act now, in the words its key would say ("" when it can): its buttons are
        dimmed, and the key, typed or pressed, says why instead of acting (design 0011 §12.7)."""
        return ""

    def shown_keys(self) -> tuple[PageKey, ...]:
        """The keys the keys bar shows for the page as it stands: its own (`KEYS`). A page with views shows its view's
        (the Monitor), and draws the bar again when its view changes."""
        return self.KEYS

    def explain(self) -> tuple[str, list[str]]:
        """What `?` says on this page: a title and its lines (design 0001 §5.4). Pages say more about what has the
        focus; this says what the page shows."""
        return self.ENTRY.explanation()
