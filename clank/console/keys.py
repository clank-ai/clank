"""The console's keys (design 0011 §4 and §7, decision 0046): each page declares its own once, as named actions with
their words (`Page.KEYS`, a tuple of `PageKey`), and the keys bar, Help and `?` read that one declaration, so they
cannot disagree. A key's action is its name, which M2's `keys.json` (design 0001 §5.5) will map another key to; until
then a page acts on its keys in its `press`.

The keys bar (`keysbar.KeysBar`, in place of Textual's footer) is one row on `bars`: the page's own keys first, then the
keys that act anywhere (`ANYWHERE`: `?` explain and `f1` help, which always stay, `esc` back to the menu, decision
0129, then `f5`, `q` and `^b`, the menu shown or hidden, decision 0125), and `PALETTE`'s `^p palette` at the right,
each key in `key` and its words in `quiet`. A page with a step back declares Esc as its own (`esc back`, decision
0151), and then the bar shows that in place of `esc menu`. When the row is too narrow (`fit_keys`), the palette, `^b`,
`q`, `f5` and `esc` go first, then the page's own keys from the right. `MOVES` says what the keys that move do (the
digits, Esc, Backspace, the arrows, Tab, Enter and Space), which are Textual's, the shell's and the groups of buttons',
for Help. Backspace erases in a field you type in and is never a page's key (decision 0151).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rich.cells import cell_len

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
    PageKey("escape", "to_menu", "menu",
            "back: a step back inside a page when it has one (its keys bar says esc back), else to the menu on the "
            "left, the page staying as it was; a window open closes first, and a field you type in is left first"),
    PageKey("f5", "machine", "machine column",
            "show or hide the machine column on the right (it shows by itself from 130 columns)"),
    PageKey("q", "quit", "quit", "quit; the service and what it runs go on"),
    PageKey("ctrl+b", "menu", "menu",
            "show or hide the menu on the left (the Monitor hides it, so the flow has the whole width); every page's "
            "key still opens it"),
)  # fmt: skip
ALWAYS = ANYWHERE[:2]  # on every keys bar, however narrow: `?` and `f1`, which lists every key; `esc` goes last of
# the others, before the page's own keys
PALETTE = PageKey("ctrl+p", "command_palette", "palette",
                  "the commands: every page and action, found by name; Change style picks the style")  # fmt: skip
MOVES = (
    ("0 to 9", "open a page (the menu shows each page's key beside its name)"),
    ("esc", "back: one step inside a page (the Monitor's view before, the Flow view's flow, Add a model's step "
            "before), else to the menu; a window open closes first, a field you type in is left first"),
    ("backspace", "erase the character before the cursor in a field you type in; it never moves you"),
    ("up, down", "move in the menu (the page under the highlight opens), or in the page's list; a page without one "
                 "scrolls; in a column of buttons, the next one; from a row of buttons, the group above or below"),
    ("right, left", "from the menu into the page and back; in a page, from one of its lists to the next and back; in "
                    "a row of buttons (the keys bar too), the next one, stopping at its ends"),
    ("tab", "the next group: the menu, the page's lists and rows of buttons, the keys bar (shift+tab: back)"),
    ("enter, space", "press the button that has the focus, as its key or a click does; Enter on the menu goes into "
                     "the page"),
    ("home, end", "a row of buttons' first or last"),
)  # fmt: skip
SHOWN = {
    "question_mark": "?",
    "slash": "/",
    "full_stop": ".",
    "escape": "esc",
    "backspace": "bksp",
    "plus": "+",
    "minus": "-",
    "ctrl+p": "^p",
    "ctrl+b": "^b",
}


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
    `^b`, `q`, `f5` and `esc` go first, then the page's own from the right; `?` and `f1` always stay."""
    own, palette = list(page), True
    others = [key for key in ANYWHERE[len(ALWAYS) :] if key.key not in {mine.key for mine in own}]  # esc back
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
