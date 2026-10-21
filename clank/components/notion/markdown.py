"""An entry's page as Markdown, for the agent (design 0010 §4): Notion's blocks and rich text to the Markdown a local
model reads best, the same way every time, so the page the agent sends back can be compared with the page now block by
block (design 0010 §5).

A block Clank knows becomes its Markdown: headings (`#`, `##`, `###`), paragraphs, lists (each item's children indented
by two spaces; items of a kind in a row are one list), to-dos (`- [x]`), toggles (`- ▸ `, their contents indented),
quotes, callouts (`> **Callout:** `), code (fenced, with its language), block equations (`$$` lines), dividers
(`---`), images (`![caption](notion:<block id>)`), child pages and databases (`[title](notion:<id>)`) and links
(`<url>`). Any other block is said, never dropped. Rich text keeps bold, italic, strikethrough, inline code, links,
inline equations (`$...$`) and mentions of pages (`[title](notion:<id>)`).
"""

from typing import Any

LISTS = {"bulleted_list_item": "- ", "numbered_list_item": "1. ", "to_do": None, "toggle": "- ▸ "}
LINKS = ("bookmark", "embed", "link_preview", "video", "pdf", "file", "audio")


def rich_markdown(rich: list[dict[str, Any]]) -> str:
    """Rich text as inline Markdown."""
    return "".join(_run(run) for run in rich or [])


def blocks_markdown(blocks: list[dict[str, Any]]) -> str:
    """Blocks (each with its `children`, read already) as Markdown: blocks apart by a blank line, a list's items by one
    line."""
    parts: list[str] = []
    previous = ""
    for each in blocks:
        kind = each.get("type", "")
        shown = _block(each)
        if not shown:
            previous = ""
            continue
        if kind in LISTS and kind == previous and parts:
            parts[-1] += "\n" + shown
        else:
            parts.append(shown)
        previous = kind
    return "\n\n".join(parts)


def _block(each: dict[str, Any]) -> str:
    kind = each.get("type", "")
    content = each.get(kind) or {}
    words = rich_markdown(content.get("rich_text") or [])
    children = each.get("children") or []
    if kind in LISTS:
        marker = LISTS[kind] or ("- [x] " if content.get("checked") else "- [ ] ")
        inner = blocks_markdown(children)
        return marker + words + ("\n" + _indent(inner) if inner else "")
    if kind.startswith("heading_") and kind[-1] in "123":
        return "#" * int(kind[-1]) + " " + words
    if kind == "paragraph":
        inner = blocks_markdown(children)
        return words + ("\n" + _indent(inner) if inner else "")
    if kind == "quote":
        return _quoted(words)
    if kind == "callout":
        return _quoted("**Callout:** " + words)
    if kind == "code":
        language = str(content.get("language") or "")
        language = "" if language == "plain text" else language
        return f"```{language}\n{_plain(content.get('rich_text') or [])}\n```"
    if kind == "equation":
        return f"$$\n{content.get('expression', '')}\n$$"
    if kind == "divider":
        return "---"
    if kind == "image":
        return f"![{_plain(content.get('caption') or [])}](notion:{each.get('id', '')})"
    if kind in ("child_page", "child_database"):
        return f"[{content.get('title', '')}](notion:{each.get('id', '')})"
    if kind in LINKS:
        url = content.get("url") or (content.get("external") or {}).get("url") or ""
        return f"<{url}>" if url else f"[a {kind} block]"
    return f"[a {kind} block, which Clank cannot show yet]"


def _run(run: dict[str, Any]) -> str:
    kind = run.get("type")
    plain = str(run.get("plain_text", ""))
    if kind == "equation":
        return f"${(run.get('equation') or {}).get('expression', plain)}$"
    if kind == "mention":
        mentioned = run.get("mention") or {}
        target = mentioned.get(mentioned.get("type", ""), {})
        if mentioned.get("type") in ("page", "database") and isinstance(target, dict) and target.get("id"):
            return f"[{plain}](notion:{target['id']})"
        return plain
    marks = run.get("annotations") or {}
    link = ((run.get("text") or {}).get("link") or {}).get("url") or run.get("href")
    shown = f"`{plain}`" if marks.get("code") else _marked(plain, marks)
    return f"[{shown}]({link})" if link else shown


def _marked(plain: str, marks: dict[str, Any]) -> str:
    """Bold, italic and strikethrough around the words, the spaces at either end kept outside the marks."""
    core = plain.strip()
    if not core:
        return plain
    lead, trail = plain[: len(plain) - len(plain.lstrip())], plain[len(plain.rstrip()) :]
    for mark, wrap in (("strikethrough", "~~"), ("italic", "*"), ("bold", "**")):
        if marks.get(mark):
            core = f"{wrap}{core}{wrap}"
    return lead + core + trail


def _plain(rich: list[dict[str, Any]]) -> str:
    return "".join(str(run.get("plain_text", "")) for run in rich)


def _indent(text: str) -> str:
    return "\n".join(("  " + line) if line else "" for line in text.split("\n"))


def _quoted(text: str) -> str:
    return "\n".join("> " + line for line in text.split("\n"))
