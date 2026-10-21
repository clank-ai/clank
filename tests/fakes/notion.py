"""A fake Notion (design 0010 §10): an `httpx2` mock transport that answers Notion's API at version 2025-09-03 over a
made-up workspace, so Clank's Notion component is tested without anyone's real Notion.

It checks what Notion checks: the secret as a bearer token (`401 unauthorized` otherwise) and the `Notion-Version`
header (`400 missing_version` without it). It keeps every request it was sent (`requests`), and can answer the next ones
with `429 rate_limited` and a `Retry-After` (`limit`), as Notion does when a connection asks too fast.

The workspace (`made_up`): two databases shared with the integration, Papers (test) and Concepts (test), each
with one data source; made-up entries with pages of blocks (a toggle with children of its own) and one entry in the
trash; what is not in it stands for what is not shared. Search, a data source's query (title and text `contains`, select
`equals`, multi-select `contains`, `and`/`or`; pages of `page_size` with a cursor), pages and block children are
answered as Notion's reference describes; anything unknown is `404 object_not_found`.

It is written to as Notion is (`POST pages`, `PATCH pages/<id>`, `PATCH blocks/<id>/children` with a `position`,
`PATCH blocks/<id>`, `DELETE blocks/<id>`), as strictly: a property the data source lacks, a status that is not one of
its options, a relation to an entry that does not exist, children nested more than two deep in one request and more
than 100 blocks at once are `400 validation_error`; a new select option is added, as Notion adds one. It is stricter in
one way: text sent with the fields Notion only answers (`plain_text`, `href`) is refused, so Clank sends exactly what
Notion's writes take. Each write moves the entry's `last_edited_time` on; `edit` does so as if the owner edited it in
Notion, and `fail` makes the next request to a path fail once.
"""

import copy
import json
from dataclasses import dataclass, field
from typing import Any

import httpx2

VERSION = "2025-09-03"
SECRET = "ntn_fake_secret_for_tests_7f3a"
LIT_DB, LIT_DS, OBS_DB, OBS_DS = "db-lit", "ds-lit", "db-obs", "ds-obs"
EDITED = "2026-10-17T12:00:00.000Z"


def text(content: str, **annotations: Any) -> dict[str, Any]:
    """A rich text run, as Notion gives one."""
    link = annotations.pop("link", None)
    return {
        "type": "text",
        "text": {"content": content, "link": {"url": link} if link else None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False, "underline": False, "code": False,
                        "color": "default", **annotations},
        "plain_text": content,
        "href": link,
    }  # fmt: skip


def mention(page: str, title: str) -> dict[str, Any]:
    """A mention of a page, as Notion gives one."""
    return {"type": "mention", "mention": {"type": "page", "page": {"id": page}}, "plain_text": title, "href": None}


def block(id: str, kind: str, children: list[dict[str, Any]] | None = None, **content: Any) -> dict[str, Any]:
    """A block (its children kept beside it, given by `blocks/<id>/children`)."""
    return {"object": "block", "id": id, "type": kind, "has_children": bool(children), kind: content,
            "_children": children or []}  # fmt: skip


@dataclass
class Sent:
    """A request the fake was sent."""

    method: str
    path: str
    headers: dict[str, str]
    body: Any


@dataclass
class FakeNotion:
    """A made-up Notion workspace behind Notion's API."""

    secret: str = SECRET
    integration: str = "Clank"
    workspace: str = "A made-up workspace"
    requests: list[Sent] = field(default_factory=list)
    limited: list[float] = field(default_factory=list)  # each next request answered 429 with this Retry-After
    waited: list[float] = field(default_factory=list)  # what a client given `wait` as its sleep waited
    databases: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    blocks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # a page's or a block's children
    failing: dict[str, int] = field(default_factory=dict)  # "METHOD path": the status of its next answer, once
    made: int = 0  # ids given and edits made, to name new blocks and pages and to move edit times on

    def __post_init__(self) -> None:
        made_up(self)

    @property
    def transport(self) -> httpx2.MockTransport:
        """The transport a client sends its requests through."""
        return httpx2.MockTransport(self.handle)

    def wait(self, seconds: float) -> None:
        """A client's sleep: kept, not slept."""
        self.waited.append(seconds)

    def limit(self, *waits: float) -> None:
        """Answer the next requests with `429 rate_limited`, each asking for its wait in seconds."""
        self.limited.extend(waits)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append(Sent(request.method, request.url.path, dict(request.headers), body))
        if request.headers.get("authorization") != f"Bearer {self.secret}":
            return error(401, "unauthorized", "API token is invalid.")
        if request.headers.get("notion-version") != VERSION:
            return error(400, "missing_version", "Notion-Version header failed validation.")
        if self.limited:
            wait = self.limited.pop(0)
            return error(429, "rate_limited", "You have been rate limited.", headers={"Retry-After": f"{wait:g}"})
        failed = self.failing.pop(f"{request.method} {request.url.path}", None)
        if failed is not None:
            return error(failed, "internal_server_error", "Something went wrong (the fake was told to fail).")
        return self.route(request.method, request.url.path, dict(request.url.params), body or {})

    def fail(self, method: str, path: str, status: int = 500) -> None:
        """Answer the next request to this path with an error, once."""
        self.failing[f"{method} {path}"] = status

    def edit(self, page: str) -> None:
        """An edit of an entry in Notion, as if the owner made it: its last edit time moves on."""
        self.pages[page]["last_edited_time"] = self._later()

    def route(self, method: str, path: str, params: dict[str, str], body: Any) -> httpx2.Response:
        parts = path.strip("/").split("/")[1:]  # after v1
        if (method, parts) == ("GET", ["users", "me"]):
            return answer({
                "object": "user", "id": "u-bot", "type": "bot", "name": self.integration,
                "bot": {"workspace_name": self.workspace, "owner": {"type": "workspace", "workspace": True}},
            })  # fmt: skip
        if (method, parts) == ("POST", ["search"]):
            return self.search(body)
        if method == "GET" and len(parts) == 2 and parts[0] == "databases":
            return self.found(self.databases, parts[1])
        if method == "GET" and len(parts) == 2 and parts[0] == "data_sources":
            return self.found(self.sources, parts[1])
        if method == "POST" and len(parts) == 3 and parts[0] == "data_sources" and parts[2] == "query":
            return self.query(parts[1], body)
        if method == "GET" and len(parts) == 2 and parts[0] == "pages":
            return self.found(self.pages, parts[1])
        if method == "GET" and len(parts) == 3 and parts[0] == "blocks" and parts[2] == "children":
            return self.children(parts[1], params)
        try:
            if (method, parts) == ("POST", ["pages"]):
                return self.create_page(body)
            if method == "PATCH" and len(parts) == 2 and parts[0] == "pages":
                return self.update_page(parts[1], body)
            if method == "PATCH" and len(parts) == 3 and parts[0] == "blocks" and parts[2] == "children":
                return self.append(parts[1], body)
            if method == "PATCH" and len(parts) == 2 and parts[0] == "blocks":
                return self.update_block(parts[1], body)
            if method == "DELETE" and len(parts) == 2 and parts[0] == "blocks":
                return self.delete_block(parts[1])
        except Invalid as invalid:
            return error(400, "validation_error", str(invalid))
        return error(400, "invalid_request_url", f"Invalid request URL: {method} {path}.")

    def create_page(self, body: dict[str, Any]) -> httpx2.Response:
        parent = body.get("parent") or {}
        source = parent.get("data_source_id")
        if parent.get("type") != "data_source_id" or source not in self.sources:
            raise Invalid("body.parent should be a data_source_id of a shared data source.")
        properties = self._properties(source, body.get("properties") or {}, {})
        if not any(value["type"] == "title" for value in properties.values()):
            raise Invalid("body.properties should hold the title.")
        id = self._id("page")
        children = self._blocks(body.get("children") or [], 0)
        self.add_page(id, source, properties, children)
        self.pages[id]["last_edited_time"] = self.pages[id]["created_time"] = self._later()
        return answer(copy.deepcopy(self.pages[id]))

    def update_page(self, id: str, body: dict[str, Any]) -> httpx2.Response:
        if id not in self.pages:
            return not_found(id)
        page = self.pages[id]
        if "in_trash" in body:
            page["in_trash"] = bool(body["in_trash"])
        if body.get("properties"):
            source = page["parent"]["data_source_id"]
            page["properties"] = self._properties(source, body["properties"], page["properties"])
        page["last_edited_time"] = self._later()
        return answer(copy.deepcopy(page))

    def append(self, parent: str, body: dict[str, Any]) -> httpx2.Response:
        if parent not in self.blocks:
            return not_found(parent)
        made = self._blocks(body.get("children") or [], 0)
        siblings = self.blocks[parent]
        position = body.get("position") or {"type": "end"}
        if position["type"] == "start":
            at = 0
        elif position["type"] == "after_block":
            after = position["after_block"]["id"]
            at = next((index + 1 for index, each in enumerate(siblings) if each["id"] == after), -1)
            if at < 0:
                raise Invalid(f"body.position.after_block.id {after} is not a child of {parent}.")
        else:
            at = len(siblings)
        siblings[at:at] = made
        for each in made:
            self._keep_children(each)
        self._touch(parent)
        return answer({"object": "list", "results": [_shown(each) for each in made], "has_more": False})

    def update_block(self, id: str, body: dict[str, Any]) -> httpx2.Response:
        found = self._block(id)
        kind = found["type"]
        if kind not in body:
            raise Invalid(f"body.{kind} should be defined: a block keeps its type.")
        content = dict(body[kind])
        _check_rich(content.get("rich_text") or [])
        found[kind] = {**found[kind], **content, "rich_text": self._stored(content.get("rich_text") or [])}
        self._touch_block(id)
        return answer(_shown(found))

    def delete_block(self, id: str) -> httpx2.Response:
        for parent, children in self.blocks.items():
            for index, each in enumerate(children):
                if each["id"] == id:
                    del children[index]
                    self._touch(parent)
                    return answer({**_shown(each), "in_trash": True})
        return not_found(id)

    def _properties(self, source: str, given: dict[str, Any], now: dict[str, Any]) -> dict[str, Any]:
        """Properties written as Notion keeps them, checked against the data source."""
        schema = self.sources[source]["properties"]
        kept = copy.deepcopy(now)
        for name, value in given.items():
            if name not in schema:
                raise Invalid(f"{name} is not a property that exists.")
            kind = schema[name]["type"]
            if set(value) != {kind}:
                raise Invalid(f"body.properties.{name} should be an object with {kind}.")
            written = value[kind]
            if kind in ("title", "rich_text"):
                _check_rich(written)
                written = self._stored(written)
            if kind == "status" and written and written["name"] not in _options(schema[name]):
                raise Invalid(f"Status option {written['name']} does not exist for {name}.")
            if kind in ("select", "multi_select"):
                for each in [written] if kind == "select" else written:
                    if each and each["name"] not in _options(schema[name]):
                        schema[name][kind]["options"].append({"name": each["name"], "color": "default"})
            if kind == "relation":
                for each in written:
                    if each["id"] not in self.pages:
                        raise Invalid(f"Could not find page with ID: {each['id']}.")
            kept[name] = {"id": schema[name]["id"], "type": kind, kind: written}
        return kept

    def _blocks(self, given: list[dict[str, Any]], depth: int) -> list[dict[str, Any]]:
        """Blocks written as Notion keeps them: given ids, their children kept beside them."""
        if len(given) > 100:
            raise Invalid("body.children.length should be at most 100.")
        made = []
        for each in given:
            kind = str(each.get("type") or "")
            if not kind:
                raise Invalid("body.children[].type should be defined.")
            content = dict(each.get(kind) or {})
            children = content.pop("children", [])
            if children and depth >= 2:
                raise Invalid("body.children should be nested at most two levels deep in one request.")
            for key in ("rich_text", "caption"):
                if key in content:
                    _check_rich(content[key])
                    content[key] = self._stored(content[key])
            made.append(block(self._id("block"), kind, self._blocks(children, depth + 1), **content))
        return made

    def _stored(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rich text as Notion answers it: with its plain text."""
        stored = []
        for run in runs:
            kept = copy.deepcopy(run)
            if run["type"] == "text":
                kept["plain_text"] = run["text"]["content"]
                kept["href"] = (run["text"].get("link") or {}).get("url")
            elif run["type"] == "equation":
                kept["plain_text"] = run["equation"]["expression"]
            elif run["type"] == "mention":
                page = self.pages.get(run["mention"]["page"]["id"])
                kept["plain_text"] = title_of(page) if page else "Untitled"
            stored.append(kept)
        return stored

    def _keep_children(self, each: dict[str, Any]) -> None:
        self.blocks[each["id"]] = each["_children"]
        for child in each["_children"]:
            self._keep_children(child)

    def _block(self, id: str) -> dict[str, Any]:
        for children in self.blocks.values():
            for each in children:
                if each["id"] == id:
                    return each
        raise Invalid(f"Could not find block with ID: {id}.")

    def _touch(self, parent: str) -> None:
        if parent in self.pages:
            self.pages[parent]["last_edited_time"] = self._later()
        else:
            self._touch_block(parent)

    def _touch_block(self, id: str) -> None:
        for parent, children in self.blocks.items():
            if any(each["id"] == id for each in children):
                self._touch(parent)
                return

    def _id(self, kind: str) -> str:
        self.made += 1
        return f"new-{kind}-{self.made}"

    def _later(self) -> str:
        self.made += 1
        return f"2026-10-17T13:{self.made // 60:02d}:{self.made % 60:02d}.000Z"

    def found(self, table: dict[str, dict[str, Any]], id: str) -> httpx2.Response:
        if id not in table:
            return not_found(id)
        return answer(copy.deepcopy(table[id]))

    def search(self, body: dict[str, Any]) -> httpx2.Response:
        wanted = str(body.get("query") or "").lower()
        kind = (body.get("filter") or {}).get("value")
        found = []
        if kind in (None, "data_source"):
            found += [source for source in self.sources.values() if wanted in plain(source["title"]).lower()]
        if kind in (None, "page"):
            found += [page for page in self.pages.values() if not page["in_trash"] and wanted in title_of(page).lower()]
        return listed(found, body.get("start_cursor"), int(body.get("page_size") or 100))

    def query(self, source: str, body: dict[str, Any]) -> httpx2.Response:
        if source not in self.sources:
            return not_found(source)
        rows = [
            page for page in self.pages.values()
            if page["parent"].get("data_source_id") == source and not page["in_trash"]
            and matches(page, body.get("filter"))
        ]  # fmt: skip
        return listed(rows, body.get("start_cursor"), int(body.get("page_size") or 100))

    def children(self, id: str, params: dict[str, str]) -> httpx2.Response:
        if id not in self.blocks:
            return not_found(id)
        shown = [{key: value for key, value in each.items() if key != "_children"} for each in self.blocks[id]]
        return listed(shown, params.get("start_cursor"), int(params.get("page_size") or 100))

    def add_page(self, id: str, source: str, properties: dict[str, Any], blocks: list[dict[str, Any]],
                 in_trash: bool = False) -> None:  # fmt: skip
        """An entry of a data source, with its page's blocks (and theirs, kept as their children)."""
        database = self.sources[source]["parent"]["database_id"]
        self.pages[id] = {
            "object": "page", "id": id, "created_time": EDITED, "last_edited_time": EDITED, "in_trash": in_trash,
            "is_archived": False, "url": f"https://www.notion.so/{id}",
            "parent": {"type": "data_source_id", "data_source_id": source, "database_id": database},
            "properties": properties,
        }  # fmt: skip
        self._keep(id, blocks)

    def _keep(self, parent: str, blocks: list[dict[str, Any]]) -> None:
        self.blocks[parent] = blocks
        for each in blocks:
            if each["_children"]:
                self._keep(each["id"], each["_children"])


class Invalid(Exception):
    """A request Notion would refuse: `400 validation_error`, with this message."""


def _check_rich(runs: list[dict[str, Any]]) -> None:
    for run in runs:
        extra = {"plain_text", "href"} & set(run)
        if extra:
            raise Invalid(f"rich text should not hold {', '.join(sorted(extra))}: Notion only answers them.")


def _options(schema: dict[str, Any]) -> list[str]:
    return [option["name"] for option in schema[schema["type"]].get("options") or []]


def _shown(each: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in each.items() if key != "_children"}


def made_up(notion: FakeNotion) -> None:
    """The made-up workspace."""
    notion.databases[LIT_DB] = {
        "object": "database",
        "id": LIT_DB,
        "title": [text("Papers (test)")],
        "data_sources": [{"id": LIT_DS, "name": "Papers (test)"}],
        "in_trash": False,
    }
    notion.databases[OBS_DB] = {
        "object": "database",
        "id": OBS_DB,
        "title": [text("Concepts (test)")],
        "data_sources": [{"id": OBS_DS, "name": "Concepts (test)"}],
        "in_trash": False,
    }
    options = [{"id": f"o{index}", "name": name, "color": "default"}
               for index, name in enumerate(["walks", "sampling", "codes", "graphs"])]  # fmt: skip
    notion.sources[LIT_DS] = source(LIT_DS, LIT_DB, "Papers (test)", {
        "Title": {"type": "title", "title": {}},
        "Authors": {"type": "rich_text", "rich_text": {}},
        "Year": {"type": "number", "number": {"format": "number"}},
        "Keywords": {"type": "multi_select", "multi_select": {"options": options}},
        "Reading": {"type": "status", "status": {"options": [{"name": "To read"}, {"name": "Notes written"}]}},
        "Concepts": {"type": "relation", "relation": {"data_source_id": OBS_DS, "database_id": OBS_DB,
                                                         "type": "dual_property", "dual_property": {}}},
    })  # fmt: skip
    notion.sources[OBS_DS] = source(OBS_DS, OBS_DB, "Concepts (test)", {
        "Name": {"type": "title", "title": {}},
        "Symbol": {"type": "rich_text", "rich_text": {}},
        "Status": {"type": "select", "select": {"options": [{"name": "Draft"}, {"name": "Checked"}]}},
        "Defined in": {"type": "relation", "relation": {"data_source_id": LIT_DS, "database_id": LIT_DB,
                                                        "type": "dual_property", "dual_property": {}}},
    })  # fmt: skip
    notion.add_page("lit-1", LIT_DS, {
        "Title": {"id": "title", "type": "title", "title": [text("A made-up paper on sampling")]},
        "Authors": {"id": "a", "type": "rich_text", "rich_text": [text("Someone, Else")]},
        "Year": {"id": "y", "type": "number", "number": 2001},
        "Keywords": {"id": "k", "type": "multi_select", "multi_select": [{"name": "sampling"}, {"name": "codes"}]},
        "Reading": {"id": "r", "type": "status", "status": {"name": "Notes written"}},
        "Concepts": {"id": "o", "type": "relation", "relation": [{"id": "obs-1"}], "has_more": False},
    }, [
        block("b1", "heading_2", rich_text=[text("Summary")]),
        block("b2", "paragraph", rich_text=[text("A made-up result about "), mention("obs-1", "Made-up quantity"),
                                            text(".")]),
        block("b3", "toggle", [block("b3a", "paragraph", rich_text=[text("Hidden detail.")])],
              rich_text=[text("Details")]),
        block("b4", "equation", expression="P(m) = m / n"),
    ])  # fmt: skip
    notion.add_page("lit-2", LIT_DS, {
        "Title": {"id": "title", "type": "title", "title": [text("Another made-up paper")]},
        "Authors": {"id": "a", "type": "rich_text", "rich_text": [text("Nobody, In Particular")]},
        "Year": {"id": "y", "type": "number", "number": 2003},
        "Keywords": {"id": "k", "type": "multi_select", "multi_select": [{"name": "walks"}, {"name": "graphs"}]},
        "Reading": {"id": "r", "type": "status", "status": {"name": "To read"}},
        "Concepts": {"id": "o", "type": "relation", "relation": [], "has_more": False},
    }, [])  # fmt: skip
    notion.add_page("lit-gone", LIT_DS, {
        "Title": {"id": "title", "type": "title", "title": [text("A paper in the trash")]},
    }, [], in_trash=True)  # fmt: skip
    notion.add_page("obs-1", OBS_DS, {
        "Name": {"id": "title", "type": "title", "title": [text("Made-up quantity")]},
        "Symbol": {"id": "s", "type": "rich_text", "rich_text": [text("ε_x")]},
        "Status": {"id": "st", "type": "select", "select": {"name": "Draft"}},
        "Defined in": {"id": "d", "type": "relation", "relation": [{"id": "lit-1"}], "has_more": False},
    }, [block("c1", "paragraph", rich_text=[text("Defined as a made-up quantity.")])])  # fmt: skip


def source(id: str, database: str, title: str, properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A data source, its properties named and given ids, as Notion gives one."""
    named = {name: {"id": name.lower()[:4], "name": name, **value} for name, value in properties.items()}
    return {"object": "data_source", "id": id, "title": [text(title)], "properties": named, "in_trash": False,
            "parent": {"type": "database_id", "database_id": database}}  # fmt: skip


def plain(rich: list[dict[str, Any]]) -> str:
    return "".join(run.get("plain_text", "") for run in rich)


def title_of(page: dict[str, Any]) -> str:
    return next((plain(value["title"]) for value in page["properties"].values() if value["type"] == "title"), "")


def matches(page: dict[str, Any], wanted: dict[str, Any] | None) -> bool:
    """Whether a page passes a query's filter (the kinds of filter the fake knows)."""
    if not wanted:
        return True
    if "and" in wanted:
        return all(matches(page, each) for each in wanted["and"])
    if "or" in wanted:
        return any(matches(page, each) for each in wanted["or"])
    value = page["properties"].get(wanted["property"])
    if value is None:
        return False
    for kind in ("title", "rich_text"):
        if kind in wanted:
            return bool(wanted[kind]["contains"].lower() in plain(value.get(kind) or []).lower())
    if "select" in wanted:
        return bool((value.get("select") or value.get("status") or {}).get("name") == wanted["select"]["equals"])
    if "multi_select" in wanted:
        return bool(wanted["multi_select"]["contains"] in [each["name"] for each in value.get("multi_select") or []])
    raise AssertionError(f"the fake Notion does not know this filter: {wanted}")


def listed(items: list[dict[str, Any]], cursor: str | None, size: int) -> httpx2.Response:
    """A page of a list, with Notion's cursor."""
    start = int(cursor or 0)
    page = items[start : start + size]
    more = start + size < len(items)
    return answer({"object": "list", "results": copy.deepcopy(page), "has_more": more,
                   "next_cursor": str(start + size) if more else None})  # fmt: skip


def answer(value: Any, status: int = 200) -> httpx2.Response:
    """A JSON answer."""
    return httpx2.Response(status, json=value)


def not_found(id: str) -> httpx2.Response:
    """What Notion answers for anything not shared with the integration, or unknown."""
    return error(404, "object_not_found",
                 f"Could not find block with ID: {id}. Make sure the relevant pages and databases are shared with "
                 "your integration.")  # fmt: skip


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> httpx2.Response:
    """Notion's error shape."""
    return httpx2.Response(
        status, json={"object": "error", "status": status, "code": code, "message": message}, headers=headers or {}
    )
