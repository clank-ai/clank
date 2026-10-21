"""The Monitor's Watch for panel (design 0012 §2, §8): the newest marks the Watch for rules left, one line each: a mark
not seen yet in the attention color (the style's `on`), one seen in the quiet color (its `event`), then the rule, the
session and why, cut with "…" at the panel's width (the page's `?` says each whole).

The marks come with the console's data (`marks`, read again when a mark is made or seen). Until the page follows a
session (design 0012 §3), the panel lists the marks of every session, each naming its own; with none, the panel's
`Empty` label says what it waits for, and this list is hidden.
"""

from typing import Any

from textual.content import Content
from textual.widgets import Label

from clank.console.style import mark

SHOWN = 5  # the newest marks the panel lists


class MarksList(Label):
    """The newest marks, one line each; it takes the focus, so Enter on the panel marks them seen."""

    can_focus = True

    DEFAULT_CSS = """
    MarksList {
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """


def shown(marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The marks the panel lists: the newest `SHOWN`."""
    return marks[:SHOWN]


def line(found: dict[str, Any]) -> Content:
    """One mark on one line: its sign, its rule, its session and why."""
    sign = (mark("event"), "$clank-quiet") if found.get("seen") else (mark("on"), "$clank-attention")
    session = str(found.get("title") or found.get("session") or "")
    return Content.assemble(
        sign, " ", (str(found.get("name") or found.get("rule") or ""), "bold"), (f" · {session}", "$clank-quiet"),
        f" · {found.get('why') or ''}",
    )  # fmt: skip


def lines(marks: list[dict[str, Any]]) -> Content:
    """The lines of the marks the panel lists."""
    return Content("\n").join(line(found) for found in shown(marks))


def whole(marks: list[dict[str, Any]]) -> list[str]:
    """What `?` says of the marks listed: each whole, with when its rule fires and what it did."""
    said = []
    for found in shown(marks):
        did = "; ".join(
            each["action"] + ("" if each["done"] else f" (not done: {each['why']})") for each in found.get("did") or []
        )
        said.append(f"{found.get('name')} · {found.get('title') or found.get('session')}: {found.get('why')}. "
                    f"It fires when {found.get('fires')}; it did: {did}.")  # fmt: skip
    return said
