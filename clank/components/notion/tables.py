"""Each database of a batch as a table, for the owner's review in VS Code (design 0010 §6), with a client holding the
secret.

A table has its database's columns (the title first, then the other properties in the data source's order) and rows:
the entries as Notion has them now (its query's order, `MOST_ROWS` at most), each marked `changed` or `removed` with
its proposal, or `same`; the entries the batch adds after them, marked `added` (where one is made already, its row in
Notion is marked instead); and a proposal's entry Notion no longer lists (a removal written, an entry trashed since)
after those, from what it was when staged. Each cell is the value as text, and a cell the proposal sets holds what it
was too (`was`, empty for a new entry). Unless every row is asked for, only the marked ones and their neighbors
(`NEAR` on each side) are kept, so a large database reads as the changes in their place.
"""

from typing import Any

from clank.components.notion import reading
from clank.components.notion.client import NotionClient

MOST_ROWS = 1000
NEAR = 1  # the unchanged rows kept on each side of a marked one
MARKS = {"entry": "added", "change": "changed", "removal": "removed"}


def tables(client: NotionClient, batch: dict[str, Any], *, everything: bool = False) -> list[dict[str, Any]]:
    """Each database the batch touches, in the order its proposals do, as a table."""
    shared = {source["id"]: source for source in reading.shared_sources(client)}
    order = list(dict.fromkeys(proposal["database"] for proposal in batch["proposals"]))
    return [
        _table(client, shared.get(database), database,
               [each for each in batch["proposals"] if each["database"] == database], everything)
        for database in order
    ]  # fmt: skip


def _table(
    client: NotionClient,
    source: dict[str, Any] | None,
    database: str,
    proposals: list[dict[str, Any]],
    everything: bool,
) -> dict[str, Any]:
    columns = _columns(source, proposals)
    title_name = columns[0] if columns else ""
    entries = _entries(client, source) if source else []
    by_entry = {_entry_of(each): each for each in proposals if _entry_of(each)}
    rows = []
    for entry in entries:
        proposal = by_entry.pop(entry["id"], None)
        values = {title_name: entry["title"], **entry["properties"]}
        rows.append(_row(entry["id"], entry["title"], entry["url"], proposal, values, columns))
    if not everything:
        marked = [index for index, row in enumerate(rows) if row["proposal"]]
        rows = [row for index, row in enumerate(rows) if any(abs(index - each) <= NEAR for each in marked)]
    unlisted = [each for each in proposals if each["kind"] != "entry" and _entry_of(each) in by_entry]
    added = [each for each in proposals if each["kind"] == "entry" and _entry_of(each) in (None, *by_entry)]
    for proposal in [*unlisted, *added]:
        values = dict((proposal.get("base") or {}).get("properties") or {})
        rows.append(_row(_entry_of(proposal), proposal["title"], (proposal.get("done") or {}).get("url", ""),
                         proposal, values, columns))  # fmt: skip
    name = reading.title(source) if source else proposals[0]["database_name"]
    return {"database": database, "name": name, "columns": columns, "rows": rows, "shared": source is not None}


def _row(
    id: str | None,
    title: str,
    url: str,
    proposal: dict[str, Any] | None,
    values: dict[str, str],
    columns: list[str],
) -> dict[str, Any]:
    fields = {field["name"]: field for field in (proposal or {}).get("fields") or []}
    cells: dict[str, dict[str, str]] = {}
    for column in columns:
        field = fields.get(column)
        cells[column] = {"text": field["now"], "was": field["was"]} if field else {"text": values.get(column, "")}
    return {
        "id": id,
        "title": title,
        "url": url,
        "mark": MARKS[proposal["kind"]] if proposal else "same",
        "proposal": proposal["id"] if proposal else None,
        "cells": cells,
    }


def _entry_of(proposal: dict[str, Any]) -> str | None:
    """The entry a proposal is about: the one it changes or removes, or the one made for it."""
    return proposal["page"] or (proposal.get("done") or {}).get("id")


def _columns(source: dict[str, Any] | None, proposals: list[dict[str, Any]]) -> list[str]:
    if source is None:  # no longer shared: what the proposals say
        return list(dict.fromkeys(field["name"] for each in proposals for field in each["fields"]))
    properties = source["properties"]
    titled = [name for name, value in properties.items() if value.get("type") == "title"]
    return titled + [name for name in properties if name not in titled]


def _entries(client: NotionClient, source: dict[str, Any]) -> list[dict[str, Any]]:
    """The database's entries as rows, every page of them up to `MOST_ROWS`."""
    found: list[dict[str, Any]] = []
    cursor = None
    while len(found) < MOST_ROWS:
        answer = reading.rows(client, source, limit=reading.PAGE_SIZE, cursor=cursor)
        found += answer["rows"]
        cursor = answer["cursor"]
        if cursor is None:
            break
    return found[:MOST_ROWS]
