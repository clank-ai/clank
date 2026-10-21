"""Design 0010 §5: the page the agent proposes, in Markdown, becomes Notion's blocks; read back it is the same Markdown,
so a page the agent did not change compares equal. Inline Markdown becomes rich text and back. A value the agent gives
for a property becomes Notion's own (a number, an option, a date, related entries), refused with the reason when it
does not fit the property. A page proposed against the page now is a list of block changes: kept, removed, added after
a block, or changed in place when the block keeps its kind."""

import re
from typing import Any

import pytest

from clank.components.notion.client import NotionRefused
from clank.components.notion.markdown import blocks_markdown, rich_markdown
from clank.components.notion.writing import inline_rich, markdown_blocks, page_changes, property_value

PAGE = "\n\n".join([
    "## Summary",
    "A made-up result about [Made-up quantity](notion:obs-1), measured **twice** with `ws_sample.py`.",
    "- a point\n  - an inner point\n- another point",
    "1. first\n1. second",
    "- [x] check the seeds\n- [ ] rerun at n = 256",
    "- ▸ Details\n  Hidden detail.",
    "> A quoted line.",
    "> **Callout:** Read this first.",
    "```python\nprint(1)\n```",
    "$$\n\\mu = \\sum_m m P(m)\n$$",
    "---",
    "<https://arxiv.org/abs/2101.00001>",
    "A last paragraph with $\\epsilon_\\delta$ and a [link](https://example.test/a).",
])  # fmt: skip


def test_markdown_becomes_blocks_that_read_back_as_the_same_markdown() -> None:
    blocks = markdown_blocks(PAGE)
    assert [each["type"] for each in blocks] == [
        "heading_2", "paragraph", "bulleted_list_item", "bulleted_list_item", "numbered_list_item",
        "numbered_list_item", "to_do", "to_do", "toggle", "quote", "callout", "code", "equation", "divider", "bookmark",
        "paragraph",
    ]  # fmt: skip
    assert blocks[2]["children"][0]["type"] == "bulleted_list_item"
    assert blocks[8]["children"][0]["type"] == "paragraph"
    assert blocks[11]["code"]["language"] == "python"
    assert blocks_markdown(blocks) == PAGE


def test_inline_markdown_becomes_rich_text_and_back() -> None:
    for text in (
        "plain words",
        "**bold** and *italic* and ~~gone~~ and `code`",
        "a [link](https://example.test/x) and an entry [Made-up quantity](notion:obs-1)",
        "an equation $P(m) = m / n$ inline",
        "**a** [**bold link**](https://example.test/y) at once",
    ):
        assert rich_markdown(inline_rich(text)) == text, text
    [mention] = [run for run in inline_rich("[Made-up quantity](notion:obs-1)") if run["type"] == "mention"]
    assert mention["mention"] == {"type": "page", "page": {"id": "obs-1"}}
    long = "x" * 4500
    assert [len(run["text"]["content"]) for run in inline_rich(long)] == [2000, 2000, 500], "Notion's 2000 a run"


SCHEMA: dict[str, dict[str, Any]] = {
    "Title": {"type": "title", "title": {}},
    "Authors": {"type": "rich_text", "rich_text": {}},
    "Year": {"type": "number", "number": {}},
    "Keywords": {"type": "multi_select", "multi_select": {"options": [{"name": "walks"}, {"name": "codes"}]}},
    "Kind": {"type": "select", "select": {"options": [{"name": "paper"}]}},
    "Reading": {"type": "status", "status": {"options": [{"name": "To read"}, {"name": "Done"}]}},
    "Published": {"type": "date", "date": {}},
    "Open access": {"type": "checkbox", "checkbox": {}},
    "DOI": {"type": "url", "url": {}},
    "Concepts": {"type": "relation", "relation": {"data_source_id": "ds-obs"}},
    "Added": {"type": "created_time", "created_time": {}},
}


def related(source: str, wanted: str) -> str:
    return {"Made-up quantity": "obs-1", "obs-1": "obs-1"}[wanted]


def test_a_value_becomes_notions_own_and_a_new_option_is_said() -> None:
    def value(name: str, given: Any) -> tuple[dict[str, Any], list[str]]:
        return property_value(name, SCHEMA[name], given, related)

    assert value("Title", "A made-up paper")[0] == {"title": [inline_rich("A made-up paper")[0]]}
    assert value("Authors", "Someone, Else")[0]["rich_text"][0]["text"]["content"] == "Someone, Else"
    assert value("Year", 2001)[0] == {"number": 2001}
    assert value("Year", "2001")[0] == {"number": 2001}
    assert value("Year", 0.25)[0] == {"number": 0.25}
    assert value("Keywords", ["walks", "codes"]) == ({"multi_select": [{"name": "walks"}, {"name": "codes"}]}, [])
    assert value("Keywords", "walks, graphs") == (
        {"multi_select": [{"name": "walks"}, {"name": "graphs"}]},
        ["Keywords gains a new option: graphs"],
    )
    assert value("Kind", "paper") == ({"select": {"name": "paper"}}, [])
    assert value("Reading", "Done") == ({"status": {"name": "Done"}}, [])
    assert value("Published", "2020-11-05")[0] == {"date": {"start": "2020-11-05"}}
    assert value("Published", {"start": "2020-11-05", "end": "2020-11-06"})[0] == {
        "date": {"start": "2020-11-05", "end": "2020-11-06"}
    }
    assert value("Open access", "yes")[0] == {"checkbox": True}
    assert value("DOI", "https://doi.org/10.1103/x")[0] == {"url": "https://doi.org/10.1103/x"}
    assert value("Concepts", ["Made-up quantity"])[0] == {"relation": [{"id": "obs-1"}]}
    assert value("Concepts", [])[0] == {"relation": []}


@pytest.mark.parametrize(
    ("name", "given", "said"),
    [
        ("Year", "two thousand", "Year is a number"),
        ("Reading", "Skimmed", "Reading's status must be one of: To read, Done"),
        ("Published", "last year", "Published is a date"),
        ("Open access", "maybe", "Open access is yes or no"),
        ("Added", "2026-10-17", "Clank cannot set Added (created_time)"),
        ("Title", "", "Title cannot be empty"),
    ],
)
def test_a_value_that_does_not_fit_its_property_is_refused_with_the_reason(name: str, given: Any, said: str) -> None:
    with pytest.raises(NotionRefused, match=re.escape(said)):
        property_value(name, SCHEMA[name], given, related)


def block(id: str, markdown: str) -> dict[str, Any]:
    [parsed] = markdown_blocks(markdown)
    return {**parsed, "id": id}


def test_a_proposed_page_is_compared_with_the_page_now_block_by_block() -> None:
    now = [block("b1", "## Summary"), block("b2", "First words."), block("b3", "- a point"), block("b4", "Old end.")]
    proposed = "## Summary\n\nFirst words, changed.\n\n- a point\n\nA new paragraph.\n\nOld end."
    changes = page_changes(now, markdown_blocks(proposed))
    assert [(each["op"], each.get("id"), each.get("after")) for each in changes] == [
        ("keep", "b1", None),
        ("update", "b2", None),
        ("keep", "b3", None),
        ("add", None, "b3"),
        ("keep", "b4", None),
    ]
    assert (changes[1]["was"], changes[1]["markdown"]) == ("First words.", "First words, changed.")
    removed = page_changes(now, markdown_blocks("## Summary\n\n# A heading now\n\nOld end."))
    assert [(each["op"], each.get("id")) for each in removed] == [
        ("keep", "b1"), ("remove", "b2"), ("remove", "b3"), ("add", None), ("keep", "b4"),
    ], "a block that changes its kind is removed and added"  # fmt: skip
    first = page_changes(now, markdown_blocks("A first line.\n\n## Summary\n\nFirst words.\n\n- a point\n\nOld end."))
    assert (first[0]["op"], first[0]["after"]) == ("add", None), "added at the start: after no block"
    nested = [block("n1", "- a point\n  - an inner point")]
    moved = page_changes(nested, markdown_blocks("- a point\n  - another inner point"))
    assert [each["op"] for each in moved] == ["remove", "add"], "children changed: an update would keep the old ones"
