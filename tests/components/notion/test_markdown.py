"""Design 0010 §4: an entry's page reaches the agent as Markdown: headings, paragraphs with their bold, italic, code,
links and equations, lists with their nesting, to-dos, quotes, callouts, code, block equations, dividers, images as
`notion:` links with their caption, links to other entries as `[title](notion:id)`; a block Clank cannot show is said,
never dropped. A property's value reaches it as plain text."""

from typing import Any

from clank.components.notion.markdown import blocks_markdown, rich_markdown
from clank.components.notion.properties import property_text


def text(content: str, **annotations: Any) -> dict[str, Any]:
    link = annotations.pop("link", None)
    return {
        "type": "text",
        "text": {"content": content, "link": {"url": link} if link else None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False, "underline": False, "code": False,
                        "color": "default", **annotations},
        "plain_text": content,
        "href": link,
    }  # fmt: skip


def block(kind: str, children: list[dict[str, Any]] | None = None, **content: Any) -> dict[str, Any]:
    return {"object": "block", "id": f"b-{kind}", "type": kind, "has_children": bool(children),
            kind: content, "children": children or []}  # fmt: skip


def test_rich_text_keeps_bold_italic_code_strikethrough_links_equations_and_mentions() -> None:
    rich = [
        text("Measured "), text("twice", bold=True), text(", "), text("carefully", italic=True), text(" with "),
        text("ws_sample.py", code=True), text(" "), text("not once", strikethrough=True), text(": see "),
        text("the paper", link="https://arxiv.org/abs/2101.00001"), text(" and "),
        {"type": "equation", "equation": {"expression": "\\epsilon_\\delta"}, "plain_text": "\\epsilon_\\delta"},
        text(" in "),
        {"type": "mention", "mention": {"type": "page", "page": {"id": "obs-1"}}, "plain_text": "Made-up quantity"},
        text("."),
    ]  # fmt: skip
    assert rich_markdown(rich) == (
        "Measured **twice**, *carefully* with `ws_sample.py` ~~not once~~: see "
        "[the paper](https://arxiv.org/abs/2101.00001) and $\\epsilon_\\delta$ in [Made-up quantity](notion:obs-1)."
    )


def test_a_page_reads_as_markdown_with_its_lists_nested_and_every_block_kept() -> None:
    page = [
        block("heading_2", rich_text=[text("Summary")]),
        block("paragraph", rich_text=[text("A made-up result.")]),
        block("bulleted_list_item", [block("bulleted_list_item", rich_text=[text("an inner point")])],
              rich_text=[text("a point")]),
        block("numbered_list_item", rich_text=[text("first")]),
        block("numbered_list_item", rich_text=[text("second")]),
        block("to_do", rich_text=[text("check the seeds")], checked=True),
        block("to_do", rich_text=[text("rerun at n = 256")], checked=False),
        block("quote", rich_text=[text("A quoted line.")]),
        block("callout", rich_text=[text("Read this first.")], icon={"type": "emoji", "emoji": "!"}),
        block("code", rich_text=[text("print(1)")], language="python"),
        block("equation", expression="\\mu = \\sum_m m P(m)"),
        block("divider"),
        block("image", type="external", external={"url": "https://example.test/fig.png"},
              caption=[text("Figure 2")]),
        block("child_page", title="Notes on the derivation"),
        block("synced_block"),
    ]  # fmt: skip
    page[12]["id"] = "img-1"
    page[13]["id"] = "child-1"
    assert blocks_markdown(page) == "\n\n".join([
        "## Summary",
        "A made-up result.",
        "- a point\n  - an inner point",
        "1. first\n1. second",
        "- [x] check the seeds\n- [ ] rerun at n = 256",
        "> A quoted line.",
        "> **Callout:** Read this first.",
        "```python\nprint(1)\n```",
        "$$\n\\mu = \\sum_m m P(m)\n$$",
        "---",
        "![Figure 2](notion:img-1)",
        "[Notes on the derivation](notion:child-1)",
        "[a synced_block block, which Clank cannot show yet]",
    ])  # fmt: skip


def test_a_propertys_value_reads_as_plain_text() -> None:
    titles = {"lit-1": "A made-up paper", "lit-2": "Another made-up paper"}
    cases: list[tuple[dict[str, Any], str]] = [
        ({"type": "title", "title": [text("A made-up paper")]}, "A made-up paper"),
        ({"type": "rich_text", "rich_text": [text("Someone, "), text("Else", bold=True)]}, "Someone, Else"),
        ({"type": "number", "number": 2001.0}, "2001"),
        ({"type": "number", "number": 0.25}, "0.25"),
        ({"type": "number", "number": None}, ""),
        ({"type": "select", "select": {"name": "Draft"}}, "Draft"),
        ({"type": "status", "status": {"name": "Notes written"}}, "Notes written"),
        ({"type": "multi_select", "multi_select": [{"name": "walks"}, {"name": "graphs"}]}, "walks, graphs"),
        ({"type": "date", "date": {"start": "2026-10-17", "end": None}}, "2026-10-17"),
        ({"type": "date", "date": {"start": "2026-10-17", "end": "2026-10-20"}}, "2026-10-17 → 2026-10-20"),
        ({"type": "checkbox", "checkbox": True}, "yes"),
        ({"type": "url", "url": "https://doi.org/10.1103/x"}, "https://doi.org/10.1103/x"),
        ({"type": "relation", "relation": [{"id": "lit-1"}, {"id": "lit-2"}]},
         "A made-up paper; Another made-up paper"),
        ({"type": "people", "people": [{"name": "A. Person"}]}, "A. Person"),
        ({"type": "files", "files": [{"name": "paper.pdf"}]}, "paper.pdf"),
        ({"type": "formula", "formula": {"type": "number", "number": 3}}, "3"),
        ({"type": "unique_id", "unique_id": {"prefix": "LIT", "number": 7}}, "LIT-7"),
        ({"type": "last_edited_time", "last_edited_time": "2026-10-17T18:00:00.000Z"}, "2026-10-17T18:00:00.000Z"),
    ]  # fmt: skip
    for value, expected in cases:
        assert property_text(value, titles.get) == expected, value["type"]
