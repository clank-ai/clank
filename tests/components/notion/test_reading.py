"""Design 0010 §4: the agent reads the databases shared with Clank's integration: each with its properties and their
types (a select's options, the database a relation points to); a database's entries as compact rows (a relation as the
titles it points to, the trash left out), filtered by a title's words or by Notion's own filter, a page at a time with a
cursor; an entry's properties and its page as Markdown, read whole however many requests it takes; a search by title.
What is not shared, or unknown, is said so, and so is a Clank not connected. A read is recorded with what was asked,
never with what Notion answered."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.notion import reading
from clank.components.notion.service import Notion, NotionRefused
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, FakeNotion

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
YOU = Actor(kind="user", via="cli")


@pytest.fixture
def notion() -> FakeNotion:
    return FakeNotion()


@pytest.fixture
def kernel(home: Home, notion: FakeNotion) -> Iterator[Kernel]:
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 17, 18, 0, tzinfo=UTC)), registry.components())
    part: Notion = kernel.parts["notion"]
    part.transport = notion.transport
    part.sleep = notion.wait
    part.connect(SECRET, actor=YOU)
    yield kernel
    kernel.close()


@pytest.fixture
def part(kernel: Kernel) -> Notion:
    found: Notion = kernel.parts["notion"]
    return found


def test_the_shared_databases_are_listed_with_their_properties_types_options_and_what_a_relation_points_to(
    part: Notion,
) -> None:
    found = part.databases()
    assert [(each["name"], each["id"], each["database"]) for each in found] == [
        ("Papers (test)", "ds-lit", "db-lit"),
        ("Concepts (test)", "ds-obs", "db-obs"),
    ]
    assert found[0]["properties"] == [
        {"name": "Title", "type": "title"},
        {"name": "Authors", "type": "rich_text"},
        {"name": "Year", "type": "number"},
        {"name": "Keywords", "type": "multi_select", "options": ["walks", "sampling", "codes", "graphs"]},
        {"name": "Reading", "type": "status", "options": ["To read", "Notes written"]},
        {"name": "Concepts", "type": "relation", "points_to": "Concepts (test)"},
    ]


def test_a_databases_entries_are_compact_rows_with_relations_as_titles_and_the_trash_left_out(part: Notion) -> None:
    found = part.query("Papers (test)")
    assert [row["title"] for row in found["rows"]] == ["A made-up paper on sampling", "Another made-up paper"]
    assert found["rows"][0] == {
        "id": "lit-1",
        "title": "A made-up paper on sampling",
        "properties": {"Authors": "Someone, Else", "Year": "2001", "Keywords": "sampling, codes",
                       "Reading": "Notes written", "Concepts": "Made-up quantity"},
        "url": "https://www.notion.so/lit-1",
    }  # fmt: skip
    assert found["cursor"] is None
    assert part.query("ds-lit")["rows"] == found["rows"], "by its data source's id"
    assert part.query("db-lit")["rows"] == found["rows"], "by its database's id"


def test_entries_are_filtered_by_a_titles_words_or_by_notions_own_filter_a_page_at_a_time(part: Notion) -> None:
    assert [row["id"] for row in part.query("Papers (test)", text="another")["rows"]] == ["lit-2"]
    walks = {"property": "Keywords", "multi_select": {"contains": "walks"}}
    assert [row["id"] for row in part.query("Papers (test)", filter=walks)["rows"]] == ["lit-2"]
    first = part.query("Papers (test)", limit=1)
    assert ([row["id"] for row in first["rows"]], first["cursor"]) == (["lit-1"], "1")
    rest = part.query("Papers (test)", limit=1, cursor=first["cursor"])
    assert ([row["id"] for row in rest["rows"]], rest["cursor"]) == (["lit-2"], None)


def test_an_entrys_page_reads_as_markdown_with_its_properties(part: Notion) -> None:
    found = part.page("lit-1")
    assert (found["id"], found["title"], found["database"]) == ("lit-1", "A made-up paper on sampling",
                                                                "Papers (test)")  # fmt: skip
    assert found["properties"]["Concepts"] == "Made-up quantity"
    assert found["markdown"] == (
        "## Summary\n\n"
        "A made-up result about [Made-up quantity](notion:obs-1).\n\n"
        "- ▸ Details\n  Hidden detail.\n\n"
        "$$\nP(m) = m / n\n$$"
    )
    assert found["edited"] == "2026-10-17T12:00:00.000Z"
    assert part.page("notion:lit-1")["markdown"] == found["markdown"], "a notion: link names the entry too"


def test_a_long_page_is_read_whole_however_many_requests_it_takes(
    part: Notion, notion: FakeNotion, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "PAGE_SIZE", 1)
    asked = len(notion.requests)
    assert part.page("lit-1")["markdown"].endswith("$$\nP(m) = m / n\n$$")
    children = [sent for sent in notion.requests[asked:] if sent.path.endswith("/children")]
    assert len(children) >= 5, "the page's four blocks a request each, then the toggle's child"


def test_a_search_finds_entries_and_databases_by_title_and_never_the_trash(part: Notion) -> None:
    found = part.search("made-up")
    assert [(each["kind"], each["id"], each["title"]) for each in found] == [
        ("entry", "lit-1", "A made-up paper on sampling"),
        ("entry", "lit-2", "Another made-up paper"),
        ("entry", "obs-1", "Made-up quantity"),
    ]
    assert part.search("concepts") == [
        {"kind": "database", "id": "ds-obs", "title": "Concepts (test)", "database": "Concepts (test)"}
    ]


def test_what_is_not_shared_and_a_clank_not_connected_are_said_so(part: Notion) -> None:
    with pytest.raises(NotionRefused, match="not shared with Clank's integration, or does not exist"):
        part.page("nothing-here")
    with pytest.raises(NotionRefused, match="no shared database is named Nothing"):
        part.query("Nothing")
    part.disconnect(actor=YOU)
    with pytest.raises(NotionRefused, match="not connected"):
        part.databases()


def test_a_read_is_recorded_with_what_was_asked_and_never_what_notion_answered(kernel: Kernel, part: Notion) -> None:
    part.query("Papers (test)", text="another")
    part.page("lit-1")
    reads = kernel.events.after(0, types=["notion.read"])
    assert [event.data["what"] for event in reads] == ["query", "page"]
    assert reads[1].data["ids"] == ["lit-1"]
    kept = json.dumps([event.data for event in kernel.events.after(0)]) + " ".join(
        event.summary for event in kernel.events.after(0)
    )
    for content in ("Someone, Else", "A made-up result", "Hidden detail", "A made-up paper on sampling"):
        assert content not in kept


def test_clank_notion_databases_lists_what_clank_can_see_for_the_owner_to_check_their_sharing(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from clank.cli import common
    from clank.cli.main import main
    from clank.client import Client

    with TestClient(create_app(kernel, token="t", port=7737), base_url="http://127.0.0.1:7737") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7737", "t", name="cli", http=http))
        listed = CliRunner().invoke(main, ["notion", "databases"])
    assert listed.exit_code == 0, listed.output
    assert "Papers (test): Title (title), Authors (rich_text), Year (number), Keywords (multi_select)" in listed.output
    assert "Concepts (relation → Concepts (test))" in listed.output
    assert "Concepts (test): Name (title)" in listed.output


def test_the_routes_answer_what_the_agent_reads(kernel: Kernel) -> None:
    with TestClient(create_app(kernel, token="t", port=7732), base_url="http://127.0.0.1:7732") as http:

        def call(method: str, path: str, **body: Any) -> Any:
            answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=body or None)
            assert answer.status_code == 200, answer.text
            return answer.json()

        assert call("GET", "notion/databases")["databases"][0]["name"] == "Papers (test)"
        assert call("POST", "notion/query", database="Papers (test)", text="another")["rows"][0]["id"] == "lit-2"
        assert call("GET", "notion/page/lit-1")["title"] == "A made-up paper on sampling"
        assert call("GET", "notion/search?text=quantity")["results"][0]["id"] == "obs-1"
        missing = http.get("/api/v1/notion/page/nothing-here", headers=AUTH)
        assert missing.status_code == 409
        assert "not shared with Clank's integration" in missing.json()["error"]["message"]
