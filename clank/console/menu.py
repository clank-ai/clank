"""The console's menu: every page it has, then every page a later milestone brings (design 0002 §3.2, §3.3).

Each page declares its own entry (`Page.ENTRY`). The planned entries are listed here, each with its milestone, what
it will do and where it is designed, so the menu shows the whole of Clank as it will be, and their red says they are
not built yet (the owner's request, 2026-10-11). An entry leaves this list in the commit that builds its page.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuEntry:
    """One entry of the menu: a page, its key, what it shows, and, for a planned page, the milestone that builds it."""

    id: str
    label: str
    summary: str
    designed_in: str
    key: str = ""
    milestone: str = ""
    first: bool = False  # shown at the top of the menu: the page a bare `clank` opens

    @property
    def planned(self) -> bool:
        """Whether a later milestone builds it."""
        return bool(self.milestone)

    def explanation(self) -> tuple[str, list[str]]:
        """What the entry is, as `?` explains it: its title, then its lines."""
        if self.planned:
            where = f"Designed in {self.designed_in}; docs/ROADMAP.md says where each milestone stands."
            return f"{self.label} · coming in {self.milestone}", [self.summary, where]
        key = [f"Its key: {self.key}."] if self.key else []
        return self.label, [self.summary, *key, f"Designed in {self.designed_in}."]


def place(entry: MenuEntry) -> tuple[int, int | str]:
    """Where an entry stands in the menu: the page a bare `clank` opens first, then the digits (0 after 9, as on the
    keyboard), then the F-keys by their number (F10 after F9, design 0012 §2), then any other key."""
    key = entry.key
    if entry.first:
        return (-1, key)
    if key.isdigit():
        return (0, int(key) or 10)
    if key[:1] == "F" and key[1:].isdigit():
        return (1, int(key[1:]))
    return (2, key)


PLANNED = [
    MenuEntry(
        "sampling",
        "Sampling",
        "The roles and their sampling for each model; a change applies from the next request.",
        "design 0001 §3.3, §5.3",
        milestone="M3",
    ),
    MenuEntry(
        "layout",
        "Layout",
        "Which panels show, in what order and size, and the file each one is defined in; which key does what.",
        "design 0001 §5.5",
        milestone="M2",
    ),
    MenuEntry(
        "trials",
        "Tests and trials",
        "Check and trial results for each preset; start a suite, and compare serving setups by measured speed and "
        "useful work.",
        "design 0001 §3.8",
        milestone="M2",
    ),
    MenuEntry(
        "skills",
        "Skills",
        "The skills library: each skill's text shown before it is turned on.",
        "design 0002 §2.11",
        milestone="M8",
    ),
]
