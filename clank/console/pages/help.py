"""The help page (design 0001 §5.3's F1; design 0011 §7 and board E13): every key, and what each page shows.

Its four panels are read from the declarations, never written here (decision 0046): the keys that act anywhere and
those that move (`keys.ANYWHERE`, `keys.PALETTE`, `keys.MOVES`), the keys of the page a bare `clank` opens, the keys of
every other page that has some (each page's `KEYS`), and every page with what it shows (each menu entry's summary). A
key Help says more of than its words on the keys bar carries those words itself (`PageKey.help`).
"""

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.widgets import Label

from clank.console.keys import ANYWHERE, MOVES, PALETTE, PageKey, shown
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel


def row(key: str, what: str | Content, classes: str = "help-key") -> Horizontal:
    """One row of a panel: a key (or a page) in its column, what it does wrapping beside it."""
    return Horizontal(Label(key, classes=classes), Label(what, classes="help-what"), classes="help-row")


def keys_said(keys: Sequence[PageKey]) -> Content:
    """A page's keys on one line, each key in `key` and its words after it."""
    parts: list[Content | tuple[str, str] | str] = []
    for key in keys:
        parts += [" · "] if parts else []
        parts += [(shown(key.key), "$clank-key"), f" {key.words}"]
    return Content.assemble(*parts)


class HelpPage(Page):
    """Every key, and what each page shows."""

    ENTRY = MenuEntry("help", "Help", "Every key, and what each page shows.", "design 0001 §5.3", key="F1")
    PANELS = ("help-anywhere", "help-first", "help-others", "help-pages")

    def __init__(
        self, pages: Sequence[type[Page]], planned: Sequence[MenuEntry] = (), *, id: str | None = None
    ) -> None:
        super().__init__(id=id)
        self.pages = list(pages)
        self.planned = list(planned)

    def compose(self) -> ComposeResult:
        """The keys anywhere, the first page's, the other pages', then every page with what it shows."""
        first = next((page for page in self.pages if page.ENTRY.first), self.pages[0])
        with Panel(title="Keys anywhere", id="help-anywhere"):
            for key in (*ANYWHERE, PALETTE):
                yield row(shown(key.key), key.help or key.words)
            for keys, what in MOVES:
                yield row(keys, what)
        with Panel(title=f"Keys on {first.ENTRY.label}", id="help-first"):
            for key in first.KEYS:
                yield row(shown(key.key), key.help or key.words)
        with Panel(title="Keys on the other pages", id="help-others"):
            for page in self.pages:
                if page is not first and page.KEYS:
                    yield row(f"{page.ENTRY.key:<4}{page.ENTRY.label}", keys_said(page.KEYS), "help-page")
        with Panel(title="What each page shows", id="help-pages"):
            for entry in [page.ENTRY for page in self.pages] + self.planned:
                yield row(f"{entry.key or '':<4}{entry.label}", entry.summary, "help-page")
            yield Label("Pages in red come with a later milestone: open one to see what it will do.", classes="planned")
