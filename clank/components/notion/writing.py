"""What the agent proposes, made Notion's (design 0010 §5): its Markdown as blocks and rich text, the reverse of
`markdown.py`, so a page read back reads as the same Markdown and a page the agent did not change compares equal; its
values for properties as Notion's own, each checked against the property and refused with the reason when it does not
fit; and a page proposed against the page now as a list of block changes.

Rich text: `**bold**`, `*italic*`, `~~strikethrough~~`, `` `code` ``, `[words](url)`, `[title](notion:<id>)` (a
mention of that entry) and `$equation$`, each run at most `RUN` characters (Notion's limit). Blocks: what `markdown.py`
writes, read back, with a list item's children indented by two spaces. A line Clank wrote for a block it cannot show,
an image or a child page stands for that block: kept when the page around it is, never made anew (§5's checks refuse
that).

A page's changes (`page_changes`) compare the page now (its blocks, with their ids) and the page proposed, block by
block, by their Markdown: a block kept; removed; added after a block (none: at the start), those added in a row going
there in order; or changed in place, when blocks replaced one for one keep their kind and their children (Notion keeps
such a block, and any comment on it; an update changes a block's own text only).
"""

import difflib
import re
from collections.abc import Callable
from typing import Any

from clank.components.notion.client import NotionRefused
from clank.components.notion.markdown import blocks_markdown

RUN = 2000  # the most characters of one rich text run
INLINE = [
    ("code", re.compile(r"`([^`\n]+)`")),
    ("equation", re.compile(r"\$([^$\n]+)\$")),
    ("link", re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")),
    ("bold", re.compile(r"\*\*(.+?)\*\*")),
    ("strikethrough", re.compile(r"~~(.+?)~~")),
    ("italic", re.compile(r"\*([^*\n]+?)\*")),
]
HEADING = re.compile(r"^(#{1,3}) (.*)$")
TO_DO = re.compile(r"^- \[([ xX])\] (.*)$")
NUMBERED = re.compile(r"^\d+\. (.*)$")
IMAGE = re.compile(r"^!\[(.*)\]\((\S+)\)$")
BOOKMARK = re.compile(r"^<(https?://\S+)>$")
PLACEHOLDER = re.compile(r"^\[a [a-z_]+ block(, which Clank cannot show yet)?\]$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T[0-9:.]+(Z|[+-]\d{2}:\d{2})?)?$")
YES, NO = ("yes", "true", "1"), ("no", "false", "0")


def inline_rich(text: str) -> list[dict[str, Any]]:
    """Inline Markdown as rich text runs."""
    return _inline(text, {}, None)


def text_run(content: str, marks: dict[str, bool] | None = None, link: str | None = None) -> list[dict[str, Any]]:
    """Plain words as rich text runs (more than one when longer than `RUN`)."""
    return [
        {
            "type": "text",
            "text": {"content": content[start : start + RUN], "link": {"url": link} if link else None},
            "annotations": dict(marks or {}),
            "plain_text": content[start : start + RUN],
            "href": link,
        }
        for start in range(0, len(content), RUN)
    ]


def _inline(text: str, marks: dict[str, bool], link: str | None) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    plain = ""
    at = 0
    while at < len(text):
        found = next(((kind, match) for kind, pattern in INLINE if (match := pattern.match(text, at))), None)
        if found is None:
            plain += text[at]
            at += 1
            continue
        if plain:
            runs += text_run(plain, marks, link)
            plain = ""
        kind, match = found
        if kind == "code":
            runs += text_run(match.group(1), marks | {"code": True}, link)
        elif kind == "equation":
            runs.append({"type": "equation", "equation": {"expression": match.group(1)}, "plain_text": match.group(1)})
        elif kind == "link" and match.group(2).startswith("notion:"):
            page = match.group(2)[len("notion:") :]
            runs.append({"type": "mention", "mention": {"type": "page", "page": {"id": page}},
                         "plain_text": match.group(1)})  # fmt: skip
        elif kind == "link":
            runs += _inline(match.group(1), marks, match.group(2))
        else:
            runs += _inline(match.group(1), marks | {kind: True}, link)
        at = match.end()
    if plain:
        runs += text_run(plain, marks, link)
    return runs


def markdown_blocks(markdown: str) -> list[dict[str, Any]]:
    """Markdown as blocks (each with its `children`), as `markdown.py` writes them."""
    return _blocks(markdown.split("\n"))


def _blocks(lines: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    at = 0
    while at < len(lines):
        line = lines[at]
        if not line.strip():
            at += 1
            continue
        if line.startswith("```"):
            end = _until(lines, at + 1, "```")
            body = "\n".join(lines[at + 1 : end])
            language = line[3:].strip() or "plain text"
            found.append(_block("code", rich_text=text_run(body) if body else [], language=language))
            at = end + 1
            continue
        if line == "$$":
            end = _until(lines, at + 1, "$$")
            found.append(_block("equation", expression="\n".join(lines[at + 1 : end])))
            at = end + 1
            continue
        if line == "---":
            found.append(_block("divider"))
            at += 1
            continue
        if heading := HEADING.match(line):
            found.append(_block(f"heading_{len(heading.group(1))}", rich_text=inline_rich(heading.group(2))))
            at += 1
            continue
        if line.startswith(">"):
            end = at
            while end < len(lines) and lines[end].startswith(">"):
                end += 1
            words = "\n".join(each[2:] if each.startswith("> ") else each[1:] for each in lines[at:end])
            if words.startswith("**Callout:** "):
                found.append(_block("callout", rich_text=inline_rich(words[len("**Callout:** ") :])))
            else:
                found.append(_block("quote", rich_text=inline_rich(words)))
            at = end
            continue
        item = _item(line)
        if item is not None:
            children, at = _children(lines, at + 1)
            kind, content = item
            found.append(_block(kind, children, **content))
            continue
        if image := IMAGE.match(line):
            target = image.group(2)
            made = _block("image", caption=inline_rich(image.group(1)))
            if target.startswith("notion:"):
                made["id"] = target[len("notion:") :]
            else:
                made["file"] = target
            found.append(made)
            at += 1
            continue
        if bookmark := BOOKMARK.match(line):
            found.append(_block("bookmark", url=bookmark.group(1), caption=[]))
            at += 1
            continue
        if PLACEHOLDER.match(line):
            found.append({"type": "_shown", "_shown": {"markdown": line}, "children": []})
            at += 1
            continue
        end = at
        while end < len(lines) and lines[end].strip() and not lines[end].startswith("  ") and (
            end == at or not _starts_block(lines[end])
        ):  # fmt: skip
            end += 1
        children, after = _children(lines, end)
        found.append(_block("paragraph", children, rich_text=inline_rich("\n".join(lines[at:end]))))
        at = after
    return found


def _item(line: str) -> tuple[str, dict[str, Any]] | None:
    if to_do := TO_DO.match(line):
        return "to_do", {"rich_text": inline_rich(to_do.group(2)), "checked": to_do.group(1) != " "}
    if line.startswith("- ▸ "):
        return "toggle", {"rich_text": inline_rich(line[len("- ▸ ") :])}
    if line.startswith("- "):
        return "bulleted_list_item", {"rich_text": inline_rich(line[2:])}
    if numbered := NUMBERED.match(line):
        return "numbered_list_item", {"rich_text": inline_rich(numbered.group(1))}
    return None


def _starts_block(line: str) -> bool:
    return bool(
        line.startswith(("```", ">", "- "))
        or line in ("$$", "---")
        or HEADING.match(line)
        or NUMBERED.match(line)
        or IMAGE.match(line)
        or BOOKMARK.match(line)
    )


def _children(lines: list[str], at: int) -> tuple[list[dict[str, Any]], int]:
    """The blocks indented under the line before `at` (blank lines inside them kept), and where they end."""
    end = at
    while end < len(lines):
        indented = lines[end].startswith("  ")
        if not (indented or (not lines[end].strip() and end + 1 < len(lines) and lines[end + 1].startswith("  "))):
            break
        end += 1
    inner = [line[2:] if line.startswith("  ") else line for line in lines[at:end]]
    return _blocks(inner), end


def _until(lines: list[str], at: int, fence: str) -> int:
    while at < len(lines) and lines[at] != fence:
        at += 1
    return at


def _block(kind: str, children: list[dict[str, Any]] | None = None, **content: Any) -> dict[str, Any]:
    return {"type": kind, kind: content, "children": children or []}


def property_value(
    name: str, schema: dict[str, Any], given: Any, related: Callable[[str, str], str]
) -> tuple[dict[str, Any], list[str]]:
    """A value the agent gives for a property, as Notion's own, and what the owner should know (a new option);
    `related` finds an entry of a data source by its id or title (refusing when it cannot). Refused when it does not
    fit."""
    kind = schema.get("type", "")
    config = schema.get(kind) or {}
    if kind == "title":
        words = str(given or "").strip()
        if not words:
            raise NotionRefused(f"{name} cannot be empty: it is the entry's title")
        return {"title": inline_rich(words)}, []
    if kind == "rich_text":
        return {"rich_text": inline_rich(str(given or ""))}, []
    if kind == "number":
        return {"number": _number(name, given)}, []
    if kind in ("select", "status", "multi_select"):
        return _options(name, kind, config, given)
    if kind == "date":
        return {"date": _date(name, given)}, []
    if kind == "checkbox":
        return {"checkbox": _yes(name, given)}, []
    if kind in ("url", "email", "phone_number"):
        return {kind: str(given).strip() or None}, []
    if kind == "relation":
        wanted = given if isinstance(given, list) else [part.strip() for part in str(given or "").split(";")]
        target = str(config.get("data_source_id") or "")
        return {"relation": [{"id": related(target, str(each))} for each in wanted if str(each).strip()]}, []
    raise NotionRefused(f"Clank cannot set {name} ({kind}): Notion fills it, or it is not built yet")


def _number(name: str, given: Any) -> int | float | None:
    if given is None or given == "":
        return None
    if isinstance(given, bool):
        raise NotionRefused(f"{name} is a number, not yes or no")
    try:
        value = float(str(given).replace(",", "").strip())
    except ValueError:
        raise NotionRefused(f"{name} is a number: {given!r} is not one") from None
    return int(value) if value.is_integer() else value


def _options(name: str, kind: str, config: dict[str, Any], given: Any) -> tuple[dict[str, Any], list[str]]:
    known = [str(option.get("name", "")) for option in config.get("options") or []]
    if kind == "multi_select":
        names = given if isinstance(given, list) else [part.strip() for part in str(given or "").split(",")]
        names = [str(each).strip() for each in names if str(each).strip()]
        new = [each for each in names if each not in known]
        notes = [f"{name} gains a new option{'s' if len(new) > 1 else ''}: {', '.join(new)}"] if new else []
        return {"multi_select": [{"name": each} for each in names]}, notes
    chosen = str(given or "").strip()
    if not chosen:
        return {kind: None}, []
    if chosen in known:
        return {kind: {"name": chosen}}, []
    if kind == "status":
        raise NotionRefused(f"{name}'s status must be one of: {', '.join(known)} (only the owner adds a status)")
    return {kind: {"name": chosen}}, [f"{name} gains a new option: {chosen}"]


def _date(name: str, given: Any) -> dict[str, Any] | None:
    if given in (None, ""):
        return None
    start, end = (given.get("start"), given.get("end")) if isinstance(given, dict) else (given, None)
    for each in (start, end):
        if each is not None and not DATE.match(str(each)):
            raise NotionRefused(f'{name} is a date (YYYY-MM-DD, or {{"start", "end"}}): {each!r} is not one')
    return {"start": str(start)} | ({"end": str(end)} if end else {})


def _yes(name: str, given: Any) -> bool:
    if isinstance(given, bool):
        return given
    said = str(given).strip().lower()
    if said in YES:
        return True
    if said in NO:
        return False
    raise NotionRefused(f"{name} is yes or no: {given!r} is neither")


def page_changes(now: list[dict[str, Any]], proposed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The page proposed against the page now, block by block: keep, remove, add (after a block's id, None at the
    start) or update (in place, the kind kept), each with its Markdown (and what an update was)."""
    old = [blocks_markdown([each]) for each in now]
    new = [blocks_markdown([each]) for each in proposed]
    changes: list[dict[str, Any]] = []
    last: str | None = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                last = now[i1 + k]["id"]
                changes.append({"op": "keep", "id": last, "markdown": old[i1 + k]})
            continue
        in_place = (
            tag == "replace"
            and i2 - i1 == j2 - j1
            and all(_in_place(now[i1 + k], proposed[j1 + k]) for k in range(i2 - i1))
        )
        if in_place:
            for k in range(i2 - i1):
                last = now[i1 + k]["id"]
                changes.append({"op": "update", "id": last, "was": old[i1 + k], "markdown": new[j1 + k],
                                "block": proposed[j1 + k]})  # fmt: skip
            continue
        changes += [{"op": "remove", "id": now[k]["id"], "markdown": old[k]} for k in range(i1, i2)]
        changes += [{"op": "add", "after": last, "markdown": new[k], "block": proposed[k]} for k in range(j1, j2)]
    return changes


def _in_place(now: dict[str, Any], proposed: dict[str, Any]) -> bool:
    """Whether a block can become the proposed one in place: the same kind, and the same children (an update changes
    a block's own content only)."""
    return bool(now["type"] == proposed["type"]) and blocks_markdown(now.get("children") or []) == blocks_markdown(
        proposed.get("children") or []
    )
