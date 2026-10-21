"""The console's keys (design 0011 §4 and §7, decision 0046): each page declares its own once, as named actions with
their words (`Page.KEYS`, a tuple of `PageKey`), and the keys bar, Help and `?` read that one declaration, so they
cannot disagree. A key's action is its name, which M2's `keys.json` (design 0001 §5.5) will map another key to; until
then a page acts on its keys in its `press`.

The keys bar (`KeysBar`, in place of Textual's footer) is one row on `bars`: the page's own keys first, then the keys
that act anywhere (`ANYWHERE`: `?` explain and `f1` help, which always stay, then `f5` and `q`), and `PALETTE`'s
`^p palette` at the right, each key in `key` and its words in `quiet`. When the row is too narrow (`fit_keys`), the
palette, `q` and `f5` go first, then the page's own keys from the right. The shell draws it for the page on screen,
wherever the focus is; a click on a key presses it. `MOVES` says what the keys that move do (the digits, Esc, the
arrows, Tab), which are Textual's and the shell's, for Help.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rich.cells import cell_len
from textual import events
from textual.content import Content
from textual.widgets import Label

GAP = "  "  # between two keys of the bar


@dataclass(frozen=True)
class PageKey:
    """A key and what it does: the key as Textual names it ("s", "enter", "slash"; or as the bar writes keys a page
    reads from what it shows, "y n …" for a question's options), the action's name, its words on the keys bar and in
    Help, and what Help says of it instead when the words are too short to say it alone."""

    key: str
    action: str
    words: str
    help: str = ""


ANYWHERE = (
    PageKey("question_mark", "explain", "explain",
            "explain what has the focus: a value, a question, an operation, a menu entry, the page, and its keys"),
    PageKey("f1", "page('help')", "help", "this help"),
    PageKey("f5", "machine", "machine column",
            "show or hide the machine column on the right (it shows by itself from 130 columns)"),
    PageKey("q", "quit", "quit", "quit; the service and what it runs go on"),
)  # fmt: skip
ALWAYS = ANYWHERE[:2]  # on every keys bar, however narrow: `?` and `f1`, which lists every key
PALETTE = PageKey("ctrl+p", "command_palette", "palette",
                  "the commands: every page and action, found by name; Change style picks the style")  # fmt: skip
MOVES = (
    ("0 to 9", "open a page (the menu shows each page's key beside its name)"),
    ("esc", "close a window"),
    ("up, down", "move in the menu (the page under the highlight opens), or in the page's list; a page without one "
                 "scrolls"),
    ("right, left", "from the menu into the page and back; in a page, from one of its lists to the next and back"),
    ("tab", "move between the menu and the page's panels"),
)  # fmt: skip
SHOWN = {"question_mark": "?", "slash": "/", "full_stop": ".", "escape": "esc", "ctrl+p": "^p"}


def shown(key: str) -> str:
    """A key as the keys bar and Help write it."""
    return SHOWN.get(key, key)


def said(key: PageKey) -> str:
    """A key and its words, as the keys bar writes them ("s start or stop Docker")."""
    return f"{shown(key.key)} {key.words}"


def _width(keys: Sequence[PageKey], palette: bool) -> int:
    width = 1 + sum(cell_len(said(key)) for key in keys) + len(GAP) * max(len(keys) - 1, 0)
    return width + (len(GAP) + cell_len(said(PALETTE)) + 1 if palette else 0)


def fit_keys(page: Sequence[PageKey], width: int) -> tuple[list[PageKey], bool]:
    """The keys a bar `width` columns wide shows, in order, and whether the palette's shows at its right: the palette's,
    `q` and `f5` go first, then the page's own from the right; `?` and `f1` always stay."""
    own, others, palette = list(page), list(ANYWHERE[len(ALWAYS) :]), True
    while _width([*own, *ALWAYS, *others], palette) > width:
        if palette:
            palette = False
        elif others:
            others.pop()
        elif own:
            own.pop()
        else:
            break
    return [*own, *ALWAYS, *others], palette


def drawn(keys: Sequence[PageKey], palette: bool, width: int) -> tuple[Content, list[tuple[int, int, PageKey]]]:
    """The bar's row, and where each key stands in it (its first and last column, for a click)."""
    parts: list[Content | tuple[str, str] | str] = [" "]
    places: list[tuple[int, int, PageKey]] = []
    column = 1
    for key in [*keys, *([PALETTE] if palette else [])]:
        if key is PALETTE:
            room = width - column - cell_len(said(PALETTE)) - 1
            parts.append(" " * max(room, len(GAP)))
            column += max(room, len(GAP))
        elif column > 1:
            parts.append(GAP)
            column += len(GAP)
        parts += [(shown(key.key), "$clank-key"), (f" {key.words}", "$clank-quiet")]
        places.append((column, column + cell_len(said(key)), key))
        column += cell_len(said(key))
    return Content.assemble(*parts), places


class KeysBar(Label):
    """The keys bar: the keys of the page on screen, then the keys that act anywhere."""

    DEFAULT_CSS = """
    KeysBar {
        width: 100%;
        height: 1;
        background: $clank-bars;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.keys: tuple[PageKey, ...] = ()
        self._places: list[tuple[int, int, PageKey]] = []
        self._drawn = ""

    def show(self, keys: Sequence[PageKey]) -> None:
        """Show these keys of a page, then the keys that act anywhere, as the bar's width lets it."""
        self.keys = tuple(keys)
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        """Fit the keys to the new width."""
        self._draw()

    def on_click(self, event: events.Click) -> None:
        """A click on a key presses it."""
        pressed = next((key for start, end, key in self._places if start <= event.x < end), None)
        if pressed is not None and " " not in pressed.key:
            self.app.simulate_key(pressed.key)

    def _draw(self) -> None:
        width = self.size.width
        if not width:
            return
        content, self._places = drawn(*fit_keys(self.keys, width), width)
        if content.markup != self._drawn:
            self._drawn = content.markup
            self.update(content)
