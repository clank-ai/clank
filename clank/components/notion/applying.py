"""Writing an approved batch to Notion (design 0010 §8), with a client holding the secret.

The proposals chosen, not yet written, go in order: new entries first (`POST pages`, their page's first `CHUNK` blocks
with them and the rest appended after), so that a relation to an entry proposed in the same batch (`proposal:<id>`)
points to it once written; then changes (their properties, then their page: each block changed in place, removed, or
added where it belongs, those added in a row going in one request); then removals (`in_trash`). A change or a removal
of an entry edited in Notion since it was staged (its `last_edited_time` moved on) is not written, and said so.

A proposal is written whole or in parts (design 0010 §6): its properties by name, its page (`page`), or a removal
(`removal`). What has been written is kept on it (`done`: the parts, the entry, and its last edit after Clank's own
write, which the next part is checked against instead of the staged one); a new entry is made with its title and the
parts approved with it, and its other parts are written to it later as a change is. Each attempt's result is kept on
the proposal too: written whole (with the entry's id and address), written in part, or why not; a failure stops only
its own proposal. What Notion only answers (a run's `plain_text` and `href`) is never sent.
"""

from typing import Any

from clank.components.notion.client import NotionClient, NotionError, NotionRefused

CHUNK = 100  # the most blocks Notion takes in one request
ORDER = {"entry": 0, "change": 1, "removal": 2}


def parts(proposal: dict[str, Any]) -> list[str]:
    """A proposal's parts, each approved on its own: its properties by name and its page, or its removal."""
    if proposal["kind"] == "removal":
        return ["removal"]
    page = proposal["blocks"] if proposal["kind"] == "entry" else proposal["changes"]
    return [field["name"] for field in proposal["fields"]] + (["page"] if page else [])


def left(proposal: dict[str, Any]) -> list[str]:
    """The parts of a proposal not written yet."""
    done = (proposal.get("done") or {}).get("parts") or []
    return [part for part in parts(proposal) if part not in done]


def title_name(proposal: dict[str, Any]) -> str:
    """The property a new entry's title is in."""
    return next((name for name, value in proposal["payload"].items() if "title" in value), "")


def write(
    client: NotionClient, batch: dict[str, Any], chosen: list[tuple[dict[str, Any], list[str]]], now: str
) -> None:
    """Write the chosen parts of a batch's proposals, in order, each one's progress and result kept on it."""
    written = {
        f"proposal:{proposal['id']}": proposal["done"]["id"] for proposal in batch["proposals"] if proposal.get("done")
    }
    titles = {f"proposal:{proposal['id']}": proposal["title"] for proposal in batch["proposals"]}
    for proposal, asked in sorted(chosen, key=lambda each: ORDER[each[0]["kind"]]):
        page: dict[str, Any] | None
        try:
            if proposal["kind"] == "entry" and not proposal.get("done"):
                page = _create(client, proposal, asked, written, titles)
                written[f"proposal:{proposal['id']}"] = page["id"]
            elif proposal["kind"] == "removal":
                page = _remove(client, proposal)
            else:
                page = _change(client, proposal, asked, written, titles)
        except NotionError as error:
            proposal["result"] = {"written": False, "error": f"Notion answered: {error}", "at": now}
            continue
        except NotionRefused as refused:
            proposal["result"] = {"written": False, "error": str(refused), "at": now}
            continue
        if page is None:
            proposal["result"] = {**_edited(), "at": now}
            continue
        whole = not left(proposal)
        proposal["result"] = {"written": whole, "id": page["id"], "url": page.get("url", ""), "at": now}
        if not whole:
            proposal["result"]["partly"] = True


def _done(proposal: dict[str, Any], page: dict[str, Any], written: list[str]) -> None:
    """Keep what of a proposal is written now, and its entry's last edit after Clank's write."""
    before = (proposal.get("done") or {}).get("parts") or []
    proposal["done"] = {
        "parts": [part for part in parts(proposal) if part in before or part in written],
        "id": page["id"],
        "url": page.get("url", ""),
        "edited": page.get("last_edited_time", ""),
    }


def _create(
    client: NotionClient,
    proposal: dict[str, Any],
    asked: list[str],
    written: dict[str, str],
    titles: dict[str, str],
) -> dict[str, Any]:
    blocks = [api_block(each) for each in proposal["blocks"] or []] if "page" in asked else []
    payload = {name: value for name, value in proposal["payload"].items() if name in asked}
    page: dict[str, Any] = client.request("POST", "pages", {
        "parent": {"type": "data_source_id", "data_source_id": proposal["database"]},
        "properties": _properties(payload, written, titles),
        "children": blocks[:CHUNK],
    })  # fmt: skip
    _done(proposal, page, list(payload))
    for start in range(CHUNK, len(blocks), CHUNK):
        client.request("PATCH", f"blocks/{page['id']}/children", {"children": blocks[start : start + CHUNK]})
    if blocks:
        page = client.request("GET", f"pages/{page['id']}")
        _done(proposal, page, ["page"])
    return page


def _change(
    client: NotionClient,
    proposal: dict[str, Any],
    asked: list[str],
    written: dict[str, str],
    titles: dict[str, str],
) -> dict[str, Any] | None:
    """A change's parts (or a new entry's, written after it was made), the entry as it is after; None when it was
    edited in Notion since it was staged (or since Clank last wrote to it)."""
    page = _unedited(client, proposal)
    if page is None:
        return None
    payload = {name: value for name, value in proposal["payload"].items() if name in asked}
    if payload:
        page = client.request("PATCH", f"pages/{page['id']}", {"properties": _properties(payload, written, titles)})
        _done(proposal, page, list(payload))
    if "page" not in asked:
        return page
    if proposal["kind"] == "entry":
        blocks = [api_block(each) for each in proposal["blocks"] or []]
        for start in range(0, len(blocks), CHUNK):
            client.request("PATCH", f"blocks/{page['id']}/children", {"children": blocks[start : start + CHUNK]})
        return _after_page(client, proposal, page["id"])
    pending: list[dict[str, Any]] = []
    for change in proposal["changes"] or []:
        if change["op"] == "add" and pending and pending[-1]["after"] != change["after"]:
            _add(client, page["id"], pending)
            pending = []
        if change["op"] == "add":
            pending.append(change)
            continue
        if pending:
            _add(client, page["id"], pending)
            pending = []
        if change["op"] == "update":
            kind = change["block"]["type"]
            client.request("PATCH", f"blocks/{change['id']}", {kind: _content(change["block"], children=False)})
        elif change["op"] == "remove":
            client.request("DELETE", f"blocks/{change['id']}")
    if pending:
        _add(client, page["id"], pending)
    return _after_page(client, proposal, page["id"])


def _after_page(client: NotionClient, proposal: dict[str, Any], id: str) -> dict[str, Any]:
    """The entry once its page is written (writing blocks moves its last edit on), its page kept as done."""
    page: dict[str, Any] = client.request("GET", f"pages/{id}")
    _done(proposal, page, ["page"])
    return page


def _remove(client: NotionClient, proposal: dict[str, Any]) -> dict[str, Any] | None:
    page = _unedited(client, proposal)
    if page is None:
        return None
    trashed: dict[str, Any] = client.request("PATCH", f"pages/{page['id']}", {"in_trash": True})
    _done(proposal, trashed, ["removal"])
    return trashed


def _unedited(client: NotionClient, proposal: dict[str, Any]) -> dict[str, Any] | None:
    """The entry now, None when it was edited in Notion since it was staged, or since Clank last wrote part of it."""
    done = proposal.get("done") or {}
    page: dict[str, Any] = client.request("GET", f"pages/{done.get('id') or proposal['page']}")
    expected = done.get("edited") or proposal["base"]["edited"]
    return page if page.get("last_edited_time") == expected else None


def _edited() -> dict[str, Any]:
    return {
        "written": False,
        "edited": True,
        "error": "edited in Notion since it was staged: it is left as it is now (send it back for the agent to "
        "propose again, or reject it)",
    }


def _add(client: NotionClient, page: str, added: list[dict[str, Any]]) -> None:
    """Blocks added in a row, after the same block (or at the start), in requests of `CHUNK`."""
    after = added[0]["after"]
    blocks = [api_block(each["block"]) for each in added]
    for start in range(0, len(blocks), CHUNK):
        position = {"type": "after_block", "after_block": {"id": after}} if after else {"type": "start"}
        answer = client.request(
            "PATCH", f"blocks/{page}/children", {"children": blocks[start : start + CHUNK], "position": position}
        )
        after = answer["results"][-1]["id"] if answer.get("results") else after


def _properties(payload: dict[str, Any], written: dict[str, str], titles: dict[str, str]) -> dict[str, Any]:
    """The payload as Notion takes it: relations to proposals of the batch made the entries they wrote."""
    made: dict[str, Any] = {}
    for name, value in payload.items():
        if "relation" in value:
            ids = []
            for each in value["relation"]:
                id = each["id"]
                if id.startswith("proposal:"):
                    if id not in written:
                        raise NotionRefused(
                            f"{name} points to {titles.get(id, id)} ({id[len('proposal:') :]}), which is not written "
                            "yet: approve it too"
                        )
                    id = written[id]
                ids.append({"id": id})
            made[name] = {"relation": ids}
        elif "title" in value or "rich_text" in value:
            kind = "title" if "title" in value else "rich_text"
            made[name] = {kind: api_rich(value[kind])}
        else:
            made[name] = value
    return made


def api_block(block: dict[str, Any]) -> dict[str, Any]:
    """A block as Notion takes one, its children inside it."""
    kind = block["type"]
    return {"object": "block", "type": kind, kind: _content(block, children=True)}


def _content(block: dict[str, Any], *, children: bool) -> dict[str, Any]:
    kind = block["type"]
    content = {key: value for key, value in (block.get(kind) or {}).items() if key != "children"}
    for key in ("rich_text", "caption"):
        if key in content:
            content[key] = api_rich(content[key])
    if children and block.get("children"):
        content["children"] = [api_block(each) for each in block["children"]]
    return content


def api_rich(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rich text as Notion takes it: without what Notion only answers."""
    made = []
    for run in runs:
        if run["type"] == "text":
            made.append({"type": "text", "text": run["text"], "annotations": run.get("annotations") or {}})
        else:
            made.append({"type": run["type"], run["type"]: run[run["type"]]})
    return made
