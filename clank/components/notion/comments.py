"""The owner's comments on a batch (design 0010 §7), and the message that sends the batch back to its agent.

A comment is on the whole batch, on a proposal, on a property of it (any of its database's, changed or not), or on a
block of its page: for a change, the block of its page's changes at that place (`changes`, as the review shows them),
for a new entry, the paragraph of its page at that place (blocks apart by a blank line); the block's Markdown is kept
with the comment, so the agent reads what it was about even after a revision. The message says, for each comment not
sent yet (and each sent earlier and still unanswered), its number and what it is about in words, then what to do:
revise with the same tools, answer each comment with `notion_reply`, submit once.
"""

from typing import Any

from clank.components.notion.client import NotionRefused

KINDS = {"entry": "a new entry", "change": "a change to", "removal": "the removal of"}


def blocks_of(proposal: dict[str, Any]) -> list[str]:
    """The blocks of a proposal's page a comment can be on, as Markdown."""
    if proposal["kind"] == "change":
        return [str(each["markdown"]) for each in proposal["changes"] or []]
    if proposal["kind"] == "entry" and proposal.get("markdown"):
        return [each.strip() for each in str(proposal["markdown"]).split("\n\n") if each.strip()]
    return []


def made(
    batch: dict[str, Any], text: str, proposal: str | None, field: str | None, block: int | None, by: str, at: str
) -> dict[str, Any]:
    """A new comment of the batch, checked: what it is on exists."""
    if not text.strip():
        raise NotionRefused("the comment says nothing: write what the agent should do")
    if (field is not None or block is not None) and proposal is None:
        raise NotionRefused("a comment on a property or a block names a proposal too")
    block_text = None
    if proposal is not None:
        found = next((each for each in batch["proposals"] if each["id"] == proposal), None)
        if found is None:
            ids = ", ".join(each["id"] for each in batch["proposals"])
            raise NotionRefused(f"batch {batch['id']} has no proposal {proposal} (it has {ids})")
        if block is not None:
            blocks = blocks_of(found)
            if not 0 <= block < len(blocks):
                raise NotionRefused(f"{proposal}'s page has no block {block} (it has {len(blocks)})")
            block_text = blocks[block]
    numbers = [int(each["id"][1:]) for each in batch.get("comments") or []]
    return {
        "id": f"c{max(numbers, default=0) + 1}",
        "proposal": proposal,
        "field": field.strip() if field else None,
        "block": block,
        "block_text": block_text,
        "text": text.strip(),
        "by": by,
        "at": at,
        "revision": batch["revision"],
        "sent": False,
        "state": "open",
        "replies": [],
    }


def place(batch: dict[str, Any], comment: dict[str, Any]) -> str:
    """What a comment is about, in words."""
    if comment["proposal"] is None:
        return "the whole batch"
    proposal = next((each for each in batch["proposals"] if each["id"] == comment["proposal"]), None)
    if proposal is None:
        return f"{comment['proposal']}, no longer in the batch"
    where = "in" if proposal["kind"] != "removal" else "from"
    said = f'{proposal["id"]} ({KINDS[proposal["kind"]]} "{proposal["title"]}" {where} {proposal["database_name"]})'
    if comment["field"]:
        field = next((each for each in proposal["fields"] if each["name"] == comment["field"]), None)
        now = ((proposal.get("base") or {}).get("properties") or {}).get(comment["field"])
        values = []
        if field is not None:
            values.append(f"proposed: {field['now']}")
        if field is not None and field["was"]:
            values.append(f"in Notion: {field['was']}")
        elif field is None and now:
            values.append(f"in Notion: {now}")
        return f"{said}, its property {comment['field']}" + (f" ({'; '.join(values)})" if values else "")
    if comment["block"] is not None:
        return f'{said}, the block of its page "{comment["block_text"]}"'
    return said


def message(batch: dict[str, Any]) -> str:
    """The message that sends a batch back to its agent."""
    sent = [each for each in batch["comments"] if not each["sent"]]
    earlier = [each for each in batch["comments"] if each["sent"] and each["state"] == "open"]
    lines = [
        f'The owner sent your Notion batch {batch["id"]} ("{batch["summary"]}", revision {batch["revision"]}) back '
        "with comments. Revise it with the same tools: propose again what should change (a proposal for the same "
        "entry, or a new entry with the same title in the same database, replaces the one in the batch), answer every "
        "comment with notion_reply (its id, and what you did or why not), then call notion_submit once with a summary "
        "of this revision. Nothing is written to Notion until the owner approves it.",
        "",
        "Comments:",
        *(f'- {each["id"]}, on {place(batch, each)}: "{each["text"]}"' for each in sent),
    ]
    if earlier:
        lines += ["", "Still unanswered from earlier revisions:"]
        lines += [f'- {each["id"]}, on {place(batch, each)}: "{each["text"]}"' for each in earlier]
    written = [f"{each['id']} ({', '.join(each['done']['parts'])})" for each in batch["proposals"] if each.get("done")]
    if written:
        lines += ["", f"Written to Notion already (do not propose these parts again): {'; '.join(written)}."]
    return "\n".join(lines)
