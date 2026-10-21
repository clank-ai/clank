"""Reading Notion for the agent (design 0010 §4), with a client holding the secret: the shared data sources (Notion's
search, `data_source` objects only), a data source found by its name or its id or its database's id, its entries as
compact rows (`POST data_sources/<id>/query`; the title's words as a `contains` filter, joined with Notion's own filter
when both are given), an entry with its page read whole (`blocks/<id>/children`, `PAGE_SIZE` a request, children
followed `DEPTH` deep, `MOST_BLOCKS` in all), and a search by title. A related entry is named by its title, each one
looked up once (`Titles`).
"""

from typing import Any

from clank.components.notion.client import NotionClient, NotionError, NotionRefused
from clank.components.notion.markdown import blocks_markdown
from clank.components.notion.properties import property_schema, property_text

PAGE_SIZE = 100  # Notion's largest page of a list
DEPTH = 4  # how deep a block's children are followed
MOST_BLOCKS = 1500  # the most blocks of one page read
NOT_FOLLOWED = ("child_page", "child_database")  # their contents are entries of their own


def shared_sources(client: NotionClient) -> list[dict[str, Any]]:
    """Every data source shared with the integration, the trash left out."""
    found: list[dict[str, Any]] = []
    cursor = None
    while True:
        body: dict[str, Any] = {"filter": {"property": "object", "value": "data_source"}, "page_size": PAGE_SIZE}
        if cursor:
            body["start_cursor"] = cursor
        answer = client.request("POST", "search", body)
        found += [
            each for each in answer["results"] if each.get("object") == "data_source" and not each.get("in_trash")
        ]
        if not answer.get("has_more"):
            return found
        cursor = answer["next_cursor"]


def describe(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each data source: its name, its id, its database's id, and its properties described."""
    names = {source["id"]: title(source) for source in sources}
    return [
        {
            "name": title(source),
            "id": source["id"],
            "database": (source.get("parent") or {}).get("database_id", ""),
            "properties": [property_schema(name, value, names.get) for name, value in source["properties"].items()],
        }
        for source in sources
    ]


def resolve(sources: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    """The shared data source named, or of the id given (its own, or its database's)."""
    wanted = bare(wanted)
    for source in sources:
        if wanted in (source["id"], (source.get("parent") or {}).get("database_id")):
            return source
    for source in sources:
        if title(source).casefold() == wanted.casefold():
            return source
    names = ", ".join(title(source) for source in sources) or "none is shared yet"
    raise NotionRefused(f"no shared database is named {wanted} (shared: {names})")


def rows(
    client: NotionClient,
    source: dict[str, Any],
    *,
    text: str = "",
    filter: dict[str, Any] | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    """A data source's entries as compact rows, and the cursor of the next ones (None at the end)."""
    title_name = next((name for name, value in source["properties"].items() if value.get("type") == "title"), "")
    wanted = ([{"property": title_name, "title": {"contains": text}}] if text else []) + ([filter] if filter else [])
    body: dict[str, Any] = {"page_size": max(1, min(limit, PAGE_SIZE))}
    if wanted:
        body["filter"] = wanted[0] if len(wanted) == 1 else {"and": wanted}
    if cursor:
        body["start_cursor"] = cursor
    answer = client.request("POST", f"data_sources/{source['id']}/query", body)
    pages = answer["results"]
    titles = Titles(client, pages)
    return {
        "rows": [row(page, titles) for page in pages],
        "cursor": answer.get("next_cursor") if answer.get("has_more") else None,
    }


def row(page: dict[str, Any], titles: "Titles") -> dict[str, Any]:
    """An entry as a compact row: its id, its title, its other properties as text, its address."""
    return {
        "id": page["id"],
        "title": page_title(page),
        "properties": {
            name: property_text(value, titles.get)
            for name, value in page["properties"].items()
            if value.get("type") != "title"
        },
        "url": page.get("url", ""),
    }


def entry(client: NotionClient, page_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """An entry: its row, its database's name, its page as Markdown, and when it was last edited."""
    page = client.request("GET", f"pages/{bare(page_id)}")
    source = (page.get("parent") or {}).get("data_source_id")
    names = {each["id"]: title(each) for each in sources}
    blocks = read_blocks(client, page["id"], 0, [0])
    return {
        **row(page, Titles(client, [page])),
        "database": names.get(source or "", ""),
        "markdown": blocks_markdown(blocks),
        "edited": page.get("last_edited_time", ""),
    }


def read_blocks(client: NotionClient, parent: str, depth: int, count: list[int]) -> list[dict[str, Any]]:
    """A page's or a block's children, every page of them, each with its own children (`count` holds how many were
    read in all)."""
    found: list[dict[str, Any]] = []
    cursor = None
    while count[0] < MOST_BLOCKS:
        params: dict[str, Any] = {"page_size": PAGE_SIZE}
        if cursor:
            params["start_cursor"] = cursor
        answer = client.request("GET", f"blocks/{parent}/children", params=params)
        for each in answer["results"]:
            count[0] += 1
            if each.get("has_children") and depth < DEPTH and each.get("type") not in NOT_FOLLOWED:
                each["children"] = read_blocks(client, each["id"], depth + 1, count)
            found.append(each)
        if not answer.get("has_more"):
            return found
        cursor = answer["next_cursor"]
    if depth == 0:
        found.append(_said(f"[the page goes on: Clank reads the first {MOST_BLOCKS} blocks of a page]"))
    return found


def search(client: NotionClient, text: str, sources: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """Entries and databases whose title holds the words, the trash left out."""
    answer = client.request("POST", "search", {"query": text, "page_size": max(1, min(limit, PAGE_SIZE))})
    names = {each["id"]: title(each) for each in sources}
    found = []
    for each in answer["results"]:
        if each.get("in_trash"):
            continue
        if each.get("object") == "data_source":
            found.append({"kind": "database", "id": each["id"], "title": title(each), "database": title(each)})
        elif each.get("object") == "page":
            source = (each.get("parent") or {}).get("data_source_id") or ""
            kind = "entry" if source else "page"
            found.append({"kind": kind, "id": each["id"], "title": page_title(each), "database": names.get(source, "")})
    return found


class Titles:
    """The titles of entries, by id: those already at hand, then each other one asked of Notion once."""

    def __init__(self, client: NotionClient, pages: list[dict[str, Any]]) -> None:
        self.client = client
        self.known: dict[str, str | None] = {page["id"]: page_title(page) for page in pages}

    def get(self, id: str) -> str | None:
        """An entry's title, None when Notion cannot say (not shared)."""
        if id not in self.known:
            try:
                self.known[id] = page_title(self.client.request("GET", f"pages/{id}"))
            except NotionError:
                self.known[id] = None
        return self.known[id]


def title(source: dict[str, Any]) -> str:
    """A data source's (or a database's) name."""
    return "".join(str(run.get("plain_text", "")) for run in source.get("title") or [])


def page_title(page: dict[str, Any]) -> str:
    """An entry's title."""
    for value in (page.get("properties") or {}).values():
        if value.get("type") == "title":
            return "".join(str(run.get("plain_text", "")) for run in value.get("title") or [])
    return ""


def bare(id: str) -> str:
    """An id as Notion takes it: without a `notion:` link's prefix."""
    id = id.strip()
    return id[len("notion:") :] if id.startswith("notion:") else id


def _said(words: str) -> dict[str, Any]:
    return {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "plain_text": words}]}}
