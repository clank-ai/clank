"""Design 0010 §6 and §8, what VS Code's review needs of the service: a proposal approved in part (some of its fields,
or its page) writes only those, and the rest stays staged until approved later, written then as a change to the entry
(a new entry needs its title to be made); each database of a batch as a table: its columns, the entries the batch
changes (each changed cell with what it was), removes and adds, and, around them, the entries it leaves as they are
(their neighbors, or all of them when asked)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.notion.service import Notion, NotionRefused
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import LIT_DS, SECRET, FakeNotion, text, title_of

YOU = Actor(kind="user", via="vscode")


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


def batch_of_three(part: Notion) -> str:
    part.propose_entry("paper", "Papers (test)", {"Title": "A third made-up paper", "Authors": "Who, Ever",
                                                      "Keywords": ["walks"]},
                       markdown="## Summary\n\nWhat it shows.", why="a test")  # fmt: skip
    part.propose_change("paper", "lit-1", properties={"Year": 2002, "Reading": "To read"},
                        markdown="## Summary\n\nRewritten.", why="a test", sources=["x"])  # fmt: skip
    part.propose_removal("paper", "lit-2", why="a duplicate")
    return str(part.submit("paper", "Three things.")["id"])


def test_a_change_approved_in_part_writes_those_parts_and_the_rest_later(part: Notion, notion: FakeNotion) -> None:
    batch = batch_of_three(part)
    first = part.approve(batch, parts={"p2": ["Year"]}, actor=YOU)
    assert (first["state"], first["written"], first["left"]) == ("partly written", 1, 3)
    assert notion.pages["lit-1"]["properties"]["Year"]["number"] == 2002
    assert notion.pages["lit-1"]["properties"]["Reading"]["status"]["name"] == "Notes written", "Reading waits"
    assert notion.blocks["lit-1"][0]["heading_2"]["rich_text"][0]["plain_text"] == "Summary", "its page waits too"
    change = part.batch(batch)["proposals"][1]
    assert (change["done"]["parts"], change["result"]["written"], change["result"]["partly"]) == (["Year"], False, True)
    later = part.approve(batch, parts={"p2": ["Reading", "page"]}, actor=YOU)
    assert later["left"] == 2, "the change is written whole now; the entry and the removal wait"
    assert notion.pages["lit-1"]["properties"]["Reading"]["status"]["name"] == "To read"
    assert notion.blocks["lit-1"][1]["paragraph"]["rich_text"][0]["plain_text"] == "Rewritten."
    assert part.batch(batch)["proposals"][1]["result"]["written"] is True
    assert part.batches()[0]["left"] == 2, "a batch in brief says how many of its proposals wait"


def test_a_new_entry_approved_in_part_is_made_with_those_and_the_rest_written_to_it_later(
    part: Notion, notion: FakeNotion
) -> None:
    batch = batch_of_three(part)
    with pytest.raises(NotionRefused, match="needs its title"):
        part.approve(batch, parts={"p1": ["Authors"]}, actor=YOU)
    part.approve(batch, parts={"p1": ["Title", "Keywords"]}, actor=YOU)
    made = next(id for id, page in notion.pages.items() if title_of(page) == "A third made-up paper")
    assert (
        "Authors" not in notion.pages[made]["properties"]
        or not notion.pages[made]["properties"]["Authors"]["rich_text"]
    )
    assert notion.blocks[made] == [], "its page waits"
    part.approve(batch, parts={"p1": ["Authors", "page"]}, actor=YOU)
    assert notion.pages[made]["properties"]["Authors"]["rich_text"][0]["plain_text"] == "Who, Ever"
    assert [each["type"] for each in notion.blocks[made]] == ["heading_2", "paragraph"]
    created = [sent for sent in notion.requests if (sent.method, sent.path) == ("POST", "/v1/pages")]
    assert len(created) == 1, "made once, its other parts written to it"
    assert part.batch(batch)["proposals"][0]["result"]["written"] is True


def test_an_entry_edited_in_notion_between_two_parts_is_not_written_again(part: Notion, notion: FakeNotion) -> None:
    batch = batch_of_three(part)
    part.approve(batch, parts={"p2": ["Year"]}, actor=YOU)
    notion.edit("lit-1")
    part.approve(batch, parts={"p2": ["Reading"]}, actor=YOU)
    change = part.batch(batch)["proposals"][1]
    assert "edited in Notion" in change["result"]["error"]
    assert notion.pages["lit-1"]["properties"]["Reading"]["status"]["name"] == "Notes written"


def test_each_database_of_a_batch_is_a_table_of_its_changes_and_their_neighbors(
    part: Notion, notion: FakeNotion
) -> None:
    for id, title in (("lit-3", "A far paper"), ("lit-4", "A farther paper")):
        notion.add_page(id, LIT_DS, {"Title": {"id": "title", "type": "title", "title": [text(title)]}}, [])
    batch = batch_of_three(part)
    [table] = part.tables(batch)
    assert (table["database"], table["name"]) == ("ds-lit", "Papers (test)")
    assert table["columns"] == ["Title", "Authors", "Year", "Keywords", "Reading", "Concepts"]
    assert [(row["title"], row["mark"], row["proposal"]) for row in table["rows"]] == [
        ("A made-up paper on sampling", "changed", "p2"),
        ("Another made-up paper", "removed", "p3"),
        ("A far paper", "same", None),
        ("A third made-up paper", "added", "p1"),
    ], "lit-4 is no neighbor of a change"
    changed = table["rows"][0]["cells"]
    assert changed["Year"] == {"text": "2002", "was": "2001"}
    assert changed["Authors"] == {"text": "Someone, Else"}, "a cell the change leaves as it is"
    assert table["rows"][3]["cells"]["Authors"] == {"text": "Who, Ever", "was": ""}
    assert table["rows"][1]["cells"]["Authors"] == {"text": "Nobody, In Particular"}
    everything = part.tables(batch, everything=True)[0]["rows"]
    assert [row["title"] for row in everything] == [
        "A made-up paper on sampling", "Another made-up paper", "A far paper", "A farther paper",
        "A third made-up paper",
    ]  # fmt: skip


def test_the_routes_give_the_tables_and_approve_parts(
    kernel: Kernel, part: Notion, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = batch_of_three(part)
    with TestClient(create_app(kernel, token="t", port=7738), base_url="http://127.0.0.1:7738") as http:
        auth = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
        tables = http.get(f"/api/v1/notion/batches/{batch}/tables?everything=true", headers=auth)
        assert tables.status_code == 200, tables.text
        assert tables.json()["tables"][0]["name"] == "Papers (test)"
        approved = http.post(
            f"/api/v1/notion/batches/{batch}/approve", headers=auth, json={"parts": {"p3": ["removal"]}}
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["written"] == 1
        part.approve(batch, parts={"p2": ["Year"]}, actor=YOU)
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7738", "t", name="cli", http=http))
        shown = CliRunner().invoke(main, ["notion", "show", batch])
        assert shown.exit_code == 0, shown.output
        assert "    written in part (Year): https://www.notion.so/lit-1" in shown.output
