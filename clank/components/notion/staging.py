"""Staging the agent's proposals (design 0010 §5), with a client holding the secret: a new entry, a change or a
removal, each checked against its database's properties and refused with the reason the agent can fix, then kept in the
workspace's open batch with what the review shows and what applying needs.

A proposal holds its database (its data source) and its name, the entry (none for a new one) and its title; `fields`,
each property the proposal sets with what it was and what it would be, as text (a change keeps only those it changes);
`payload`, the same values as Notion takes them; `notes` for the owner (a new option); the page proposed in Markdown
(`markdown`), and for a new entry its blocks (`blocks`), for a change the page compared block by block with the page now
(`changes`); `base`, the entry as it was when staged (its properties as text, its page, when it was last edited: the
review compares with it and applying checks it); `why` and `sources`; and `result`, once written. A relation may name an
entry by its id or its title, or an entry proposed earlier in the same batch (`proposal:<id>` until it is written).
Numbers need their sources; an image from a file and a block only Notion has cannot be made (yet).
"""

import re
from typing import Any

from clank.components.notion import reading
from clank.components.notion.batches import Batches
from clank.components.notion.client import NotionClient, NotionError, NotionRefused
from clank.components.notion.markdown import blocks_markdown
from clank.components.notion.properties import property_text
from clank.components.notion.writing import markdown_blocks, page_changes, property_value

DIGIT = re.compile(r"\d")


def entry(
    client: NotionClient,
    batches: Batches,
    workspace: str,
    database: str,
    properties: dict[str, Any],
    markdown: str,
    why: str,
    sources: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A new entry of a shared database, staged; its batch and the proposal."""
    _why(why)
    shared = reading.shared_sources(client)
    source = reading.resolve(shared, database)
    _known(source, properties)
    title_name = _title_name(source)
    title = str(properties.get(title_name) or "").strip()
    if not title:
        raise NotionRefused(f"a new entry needs its {title_name} (the property that is its title)")
    pending = _pending(batches, workspace)
    payload, notes, fields = _values(client, shared, source, properties, pending, {})
    blocks = markdown_blocks(markdown) if markdown.strip() else []
    _makeable(blocks)
    words = [field["now"] for field in fields if _kind(source, field["name"]) != "relation"]
    _sourced([*words, markdown], sources)
    return batches.add(workspace, {
        "kind": "entry", "database": source["id"], "database_name": reading.title(source), "page": None,
        "title": title, "fields": fields, "payload": payload, "notes": notes, "markdown": markdown.strip() or None,
        "blocks": blocks, "changes": None, "base": None, "why": why.strip(), "sources": _clean(sources),
        "result": None,
    })  # fmt: skip


def change(
    client: NotionClient,
    batches: Batches,
    workspace: str,
    page_id: str,
    properties: dict[str, Any],
    markdown: str,
    why: str,
    sources: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A change to a shared entry, staged with the entry as it is now; its batch and the proposal."""
    _why(why)
    shared = reading.shared_sources(client)
    page, source, now, base = _entry_now(client, shared, page_id)
    _known(source, properties)
    payload, notes, fields = _values(
        client, shared, source, properties, _pending(batches, workspace), base["properties"]
    )
    changes = None
    if markdown.strip():
        changes = page_changes(now, markdown_blocks(markdown))
        if all(each["op"] == "keep" for each in changes):
            changes = None
        else:
            _makeable([each["block"] for each in changes if each["op"] in ("add", "update")])
    title = reading.page_title(page)
    if not payload and changes is None:
        raise NotionRefused(f"{title} changes nothing: its properties and its page are as they are in Notion")
    words = [field["now"] for field in fields if _kind(source, field["name"]) != "relation"]
    words += [each["markdown"] for each in changes or [] if each["op"] in ("add", "update")]
    _sourced(words, sources)
    return batches.add(workspace, {
        "kind": "change", "database": source["id"], "database_name": reading.title(source), "page": page["id"],
        "title": title, "fields": fields, "payload": payload, "notes": notes,
        "markdown": markdown.strip() or None, "blocks": None, "changes": changes, "base": base, "why": why.strip(),
        "sources": _clean(sources), "result": None,
    })  # fmt: skip


def removal(
    client: NotionClient, batches: Batches, workspace: str, page_id: str, why: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A shared entry to Notion's trash, staged with the entry as it is now; its batch and the proposal."""
    if not why.strip():
        raise NotionRefused("a removal must say why: the owner reads it before anything is removed")
    page, source, _, base = _entry_now(client, reading.shared_sources(client), page_id)
    return batches.add(workspace, {
        "kind": "removal", "database": source["id"], "database_name": reading.title(source), "page": page["id"],
        "title": reading.page_title(page), "fields": [], "payload": {}, "notes": [], "markdown": None,
        "blocks": None, "changes": None, "base": base, "why": why.strip(), "sources": [], "result": None,
    })  # fmt: skip


def _entry_now(
    client: NotionClient, shared: list[dict[str, Any]], page_id: str
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """An entry of a shared database as it is now: the page, its data source, its blocks, and its base."""
    page = client.request("GET", f"pages/{reading.bare(page_id)}")
    source = next((each for each in shared if each["id"] == (page.get("parent") or {}).get("data_source_id")), None)
    if source is None:
        raise NotionRefused(f"{reading.bare(page_id)} is not an entry of a database shared with Clank's integration")
    titles = reading.Titles(client, [page])
    now = reading.read_blocks(client, page["id"], 0, [0])
    base = {
        "properties": {name: property_text(value, titles.get) for name, value in page["properties"].items()},
        "markdown": blocks_markdown(now),
        "edited": page.get("last_edited_time", ""),
    }
    return page, source, now, base


def _values(
    client: NotionClient,
    shared: list[dict[str, Any]],
    source: dict[str, Any],
    given: dict[str, Any],
    pending: list[dict[str, Any]],
    base: dict[str, str],
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    """The values given, as Notion's own, with the owner's notes and the fields (only those that change, against a
    base)."""
    names = {each["id"]: reading.title(each) for each in shared}
    titles = reading.Titles(client, [])
    proposed = {f"proposal:{each['id']}": each["title"] for each in pending}

    def related(target: str, wanted: str) -> str:
        wanted = reading.bare(wanted)
        for each in pending:
            if each["kind"] == "entry" and each["database"] == target and each["title"].casefold() == wanted.casefold():
                return f"proposal:{each['id']}"
        found = next((each for each in shared if each["id"] == target), None)
        if found is None:
            raise NotionRefused(f"a relation points to a database not shared with Clank's integration ({target})")
        exact = [row for row in reading.rows(client, found, text=wanted, limit=25)["rows"]
                 if row["title"].casefold() == wanted.casefold()]  # fmt: skip
        if len(exact) > 1:
            raise NotionRefused(f"several entries of {names[target]} are titled {wanted}: give the one meant by its id")
        if exact:
            titles.known[exact[0]["id"]] = exact[0]["title"]
            return str(exact[0]["id"])
        try:
            page = client.request("GET", f"pages/{wanted}")
        except NotionError:
            page = None
        if page is not None and (page.get("parent") or {}).get("data_source_id") == target:
            titles.known[page["id"]] = reading.page_title(page)
            return str(page["id"])
        raise NotionRefused(f"no entry of {names[target]} is titled {wanted} (and none has that id)")

    def title_of(id: str) -> str | None:
        return proposed.get(id) or titles.get(id)

    payload: dict[str, Any] = {}
    notes: list[str] = []
    fields: list[dict[str, str]] = []
    for name, value in given.items():
        schema = source["properties"][name]
        made, said = property_value(name, schema, value, related)
        now = property_text({"type": schema.get("type", ""), **made}, title_of)
        was = base.get(name, "")
        if base and now == was:
            continue
        payload[name] = made
        notes += said
        fields.append({"name": name, "was": was, "now": now})
    return payload, notes, fields


def _pending(batches: Batches, workspace: str) -> list[dict[str, Any]]:
    """The proposals of the batch the workspace's agent stages into (one being revised, else its open batch), without
    making one."""
    found = batches.staging(workspace)
    return list(found["proposals"]) if found else []


def _known(source: dict[str, Any], given: dict[str, Any]) -> None:
    for name in given:
        if name not in source["properties"]:
            listed = ", ".join(source["properties"])
            raise NotionRefused(f"{name} is not a property of {reading.title(source)}: its properties are {listed}")


def _title_name(source: dict[str, Any]) -> str:
    return next((name for name, value in source["properties"].items() if value.get("type") == "title"), "Name")


def _kind(source: dict[str, Any], name: str) -> str:
    return str((source["properties"].get(name) or {}).get("type", ""))


def _makeable(blocks: list[dict[str, Any]], depth: int = 0) -> None:
    """Refuse a block Clank cannot make: an image (from a file, or one Notion has elsewhere), a line standing for a
    block only Notion has, or blocks nested deeper than one of Notion's requests takes (three levels)."""
    for each in blocks:
        if depth >= 2 and each.get("children"):
            raise NotionRefused(
                "a page nested more than three levels deep (a list in a list in a list) is not built yet"
            )
        if each.get("type") == "image" and each.get("file"):
            raise NotionRefused(
                f"an image from a file is not built yet ({each['file']}): it comes with images (design 0010 §11)"
            )
        if each.get("type") == "image":
            raise NotionRefused("an image already in Notion stays on its own page: it cannot be added to another")
        if each.get("type") == "_shown":
            raise NotionRefused(
                "only Notion has that block: a line Clank writes for a block it cannot show cannot make one"
            )
        _makeable(each.get("children") or [], depth + 1)


def _sourced(words: list[str], sources: list[str]) -> None:
    if any(DIGIT.search(each or "") for each in words) and not _clean(sources):
        raise NotionRefused(
            "this proposal states numbers: give their sources (the files, sections or scripts they come from)"
        )


def _why(why: str) -> None:
    if not why.strip():
        raise NotionRefused("a proposal must say why: the owner reads it in the review")


def _clean(sources: list[str]) -> list[str]:
    return [str(each).strip() for each in sources or [] if str(each).strip()]
