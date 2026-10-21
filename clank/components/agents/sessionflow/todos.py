"""The todo list's items across its revisions (design 0012 §6.2, decision 0050), the branches of a session that carries
out no Clank plan.

OpenCode sends the whole list with each `todo.updated`, and writes it with its `todowrite` call (whose output, in the
history, is the list as JSON); its items have no ids. So an item is followed from one revision to the next by its text:
the same text is the same item, wherever the revision lists it; else the most alike text among the items this revision
has not matched yet, when it is alike enough (`LIKE`), is the same item reworded, a match guessed, which the item says
and why; else it is a new item.
An item's state is its last: done, now (in progress), planned or canceled. Each revision comes after the step that
wrote it, so a step joins the item in progress when it began: the one the revisions before it left in progress.
"""

import difflib
import json
from typing import Any

from clank.components.agents.sessionflow.text import brief

LIKE = 0.6  # how alike two texts must be to be one item reworded
STATES = {  # OpenCode's states of an item, as an item shows them
    "completed": "done", "in_progress": "now", "pending": "planned",
    "cancelled": "canceled",  # spelling: keep (OpenCode's own word)
}  # fmt: skip
Revision = tuple[int, list[dict[str, Any]]]  # the index of the step that wrote it (-1 before any), and its todos


def written(tool: str, input: Any, output: Any, listed: Any = None) -> list[dict[str, Any]] | None:
    """The todo list a `todowrite` call wrote: the list the bridge keeps whole (`listed`, its part's `todos`), or else
    from its output or its input (an older bridge said only those); None when none reads whole (the bridge cuts its
    input and output)."""
    if tool != "todowrite":
        return None
    if isinstance(listed, list):
        return [each for each in listed if isinstance(each, dict)]
    for said in (output, input):
        try:
            found = json.loads(str(said or ""))
        except ValueError:
            continue
        listed = found.get("todos") if isinstance(found, dict) else found
        if isinstance(listed, list):
            return [each for each in listed if isinstance(each, dict)]
    return None


def follow(revisions: list[Revision]) -> tuple[list[dict[str, Any]], list[str]]:
    """The items of every revision, in the order they first appeared, and for each revision (in the order given) the
    key of the item it left in progress ("" for none)."""
    items: list[dict[str, Any]] = []
    texts: list[str] = []  # each item's whole text, as last written
    progress: list[str] = []
    for _, todos in revisions:
        said = [str(todo.get("content") or "") for todo in todos]
        free = list(range(len(items)))
        matched: list[int | None] = []
        for text in said:  # the same text first, wherever the revision lists it
            index = next((each for each in free if texts[each] == text), None)
            if index is not None:
                free.remove(index)
            matched.append(index)
        now = ""
        for todo, text, index in zip(todos, said, matched, strict=True):
            if index is None and free:
                alike = max(free, key=lambda each: difflib.SequenceMatcher(None, texts[each], text).ratio())
                ratio = difflib.SequenceMatcher(None, texts[alike], text).ratio()
                if ratio >= LIKE:
                    index = alike
                    free.remove(index)
                    items[index].update(guessed=True, why=f"taken for the item “{brief(texts[index], 80)}” "
                                        f"reworded: the texts are {ratio:.0%} alike")  # fmt: skip
            if index is None:
                items.append({"key": f"todo:{len(items) + 1}", "title": "", "source": "todo", "state": "planned",
                              "guessed": False, "why": "", "steps": []})  # fmt: skip
                texts.append(text)
                index = len(items) - 1
            texts[index] = text
            items[index].update(title=brief(text), state=STATES.get(str(todo.get("status")), "planned"))
            if todo.get("status") == "in_progress" and not now:
                now = items[index]["key"]
        progress.append(now)
    return items, progress
