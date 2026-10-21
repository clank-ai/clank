"""Design 0010 §8: an approved batch is written to Notion in order: new entries first (so a relation to one proposed in
the same batch points to it once written), then changes (their properties, then their page: a block changed in place,
removed, or added where it belongs), then removals (to Notion's trash). An entry edited in Notion since it was staged
is not written, and said so. Each proposal's result is kept: a batch stopped halfway shows what was written, and
approving it again writes the rest, never a proposal twice. Some proposals may be approved and the rest left staged; a
batch may be rejected with a reason. Only a submitted batch is approved, never by the agent itself. Writing is recorded
without content. `clank notion batches|show|approve|reject` do the same from a terminal."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.notion.markdown import blocks_markdown
from clank.components.notion.service import Notion, NotionRefused
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, FakeNotion, title_of

YOU = Actor(kind="user", via="cli")
LIT_1_PAGE = (
    "## Summary\n\nA made-up result about [Made-up quantity](notion:obs-1).\n\n- ▸ Details\n  Hidden detail.\n\n"
    "$$\nP(m) = m / n\n$$"
)


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


def page_text(notion: FakeNotion, page: str) -> str:
    """An entry's page in the fake, as Clank reads it."""

    def read(id: str) -> list[dict[str, Any]]:
        return [{**each, "children": read(each["id"])} for each in notion.blocks.get(id, [])]

    return blocks_markdown(read(page))


def staged_batch(part: Notion) -> str:
    """A batch of three: a new concept, a new paper related to it, a change to lit-1, and lit-2's removal."""
    part.propose_entry("paper", "Concepts (test)", {"Name": "A new concept", "Status": "Draft"}, why="a test")
    part.propose_entry(
        "paper", "Papers (test)", {"Title": "A third made-up paper", "Concepts": ["A new concept"],
                                       "Keywords": ["walks", "lattices"]},
        markdown="## Summary\n\nWhat it shows.\n\n- a point\n  - an inner point", why="a test",
    )  # fmt: skip
    changed = LIT_1_PAGE.replace("A made-up result about", "A corrected result about") + "\n\nA new closing line."
    part.propose_change("paper", "lit-1", properties={"Year": 2002}, markdown=changed, why="a test", sources=["x"])
    part.propose_removal("paper", "lit-2", why="a duplicate")
    return str(part.submit("paper", "Four things.")["id"])


def test_an_approved_batch_is_written_in_order_new_entries_first_and_relations_point_to_them(
    part: Notion, notion: FakeNotion
) -> None:
    batch = staged_batch(part)
    asked = len(notion.requests)
    written = part.approve(batch, actor=YOU)
    assert written["state"] == "written"
    new_concept, new_paper = (next(id for id, page in notion.pages.items() if title_of(page) == title)
                                 for title in ("A new concept", "A third made-up paper"))  # fmt: skip
    paper = notion.pages[new_paper]
    assert paper["properties"]["Concepts"]["relation"] == [{"id": new_concept}]
    assert [each["name"] for each in paper["properties"]["Keywords"]["multi_select"]] == ["walks", "lattices"]
    assert page_text(notion, new_paper) == "## Summary\n\nWhat it shows.\n\n- a point\n  - an inner point"
    assert notion.pages["lit-1"]["properties"]["Year"]["number"] == 2002
    assert (
        page_text(notion, "lit-1")
        == LIT_1_PAGE.replace("A made-up result about", "A corrected result about") + "\n\nA new closing line."
    )
    assert [each["id"] for each in notion.blocks["lit-1"]][:4] == ["b1", "b2", "b3", "b4"], "kept blocks keep their ids"
    assert notion.pages["lit-2"]["in_trash"] is True
    writes = [f"{sent.method} {sent.path}" for sent in notion.requests[asked:] if sent.method != "GET"
              and not sent.path.endswith(("/query", "/search"))]  # fmt: skip
    assert writes[:2] == ["POST /v1/pages", "POST /v1/pages"], "new entries first"
    assert writes[-1] == "PATCH /v1/pages/lit-2", "removals last"
    proposals = part.batch(batch)["proposals"]
    assert [each["result"]["written"] for each in proposals] == [True, True, True, True]
    assert proposals[1]["result"]["url"] == f"https://www.notion.so/{new_paper}"


def test_an_entry_edited_in_notion_since_it_was_staged_is_not_written_and_said_so(
    part: Notion, notion: FakeNotion
) -> None:
    batch = staged_batch(part)
    notion.edit("lit-1")
    written = part.approve(batch, actor=YOU)
    assert written["state"] == "partly written"
    change = part.batch(batch)["proposals"][2]
    assert change["result"]["written"] is False
    assert "edited in Notion since it was staged" in change["result"]["error"]
    assert notion.pages["lit-1"]["properties"]["Year"]["number"] == 2001, "left as the owner made it"
    assert part.approve(batch, actor=YOU)["state"] == "partly written", "approving again does not overwrite it"


def test_a_batch_stopped_halfway_shows_what_was_written_and_approving_again_writes_the_rest_once(
    part: Notion, notion: FakeNotion
) -> None:
    batch = staged_batch(part)
    notion.fail("PATCH", "/v1/pages/lit-1")
    first = part.approve(batch, actor=YOU)
    assert first["state"] == "partly written"
    results = [each["result"] for each in part.batch(batch)["proposals"]]
    assert [result["written"] for result in results] == [True, True, False, True]
    assert "Notion answered" in results[2]["error"]
    again = part.approve(batch, actor=YOU)
    assert again["state"] == "written"
    created = [sent for sent in notion.requests if (sent.method, sent.path) == ("POST", "/v1/pages")]
    assert len(created) == 2, "the new entries were written once"
    assert notion.pages["lit-1"]["properties"]["Year"]["number"] == 2002


def test_some_proposals_are_approved_and_the_rest_stay_staged(part: Notion, notion: FakeNotion) -> None:
    batch = staged_batch(part)
    assert part.approve(batch, proposals=["p4"], actor=YOU)["state"] == "partly written"
    assert notion.pages["lit-2"]["in_trash"] is True
    assert not any(title_of(page) == "A new concept" for page in notion.pages.values())
    assert [each["result"] is None for each in part.batch(batch)["proposals"]] == [True, True, True, False]
    with pytest.raises(NotionRefused, match="no proposal p9"):
        part.approve(batch, proposals=["p9"], actor=YOU)


def test_a_batch_is_rejected_with_a_reason_and_nothing_is_written(part: Notion, notion: FakeNotion) -> None:
    batch = staged_batch(part)
    asked = len(notion.requests)
    rejected = part.reject(batch, "Not these papers.", actor=YOU)
    assert (rejected["state"], part.batch(batch)["reason"]) == ("rejected", "Not these papers.")
    assert [sent.method for sent in notion.requests[asked:]] == []
    with pytest.raises(NotionRefused, match="rejected"):
        part.approve(batch, actor=YOU)


def test_only_a_submitted_batch_is_approved_and_never_by_the_agent(kernel: Kernel, part: Notion) -> None:
    staged = part.propose_removal("paper", "lit-2", why="a duplicate")
    with pytest.raises(NotionRefused, match="still being staged"):
        part.approve(staged["batch"], actor=YOU)
    part.submit("paper", "One removal.")
    with TestClient(create_app(kernel, token="t", port=7734), base_url="http://127.0.0.1:7734") as http:
        agent = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}
        refused = http.post(f"/api/v1/notion/batches/{staged['batch']}/approve", headers=agent, json={})
        assert refused.status_code == 403
        assert "the agent cannot approve" in refused.json()["error"]["message"]
        you = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
        assert (
            http.post(f"/api/v1/notion/batches/{staged['batch']}/approve", headers=you, json={}).json()["state"]
            == "written"
        )


def test_writing_is_recorded_without_content(kernel: Kernel, part: Notion) -> None:
    batch = staged_batch(part)
    part.approve(batch, actor=YOU)
    [event] = kernel.events.after(0, types=["notion.written"])
    assert event.data == {"batch": batch, "written": 4, "failed": 0, "left": 0}
    assert event.actor == YOU
    assert "A third made-up paper" not in event.summary


def test_clank_notion_lists_shows_approves_and_rejects_batches(
    kernel: Kernel, part: Notion, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = staged_batch(part)
    with TestClient(create_app(kernel, token="t", port=7735), base_url="http://127.0.0.1:7735") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7735", "t", name="cli", http=http))
        listed = CliRunner().invoke(main, ["notion", "batches"])
        assert listed.exit_code == 0, listed.output
        assert f"{batch}  ready  paper: 2 new, 1 changed, 1 removed: Four things." in listed.output
        shown = CliRunner().invoke(main, ["notion", "show", batch])
        assert "p2  new      Papers (test): A third made-up paper" in shown.output
        assert "p3  change   Papers (test): A made-up paper on sampling (Year 2001 → 2002; its page)" in (shown.output)
        assert "Keywords gains a new option: lattices" in shown.output
        approved = CliRunner().invoke(main, ["notion", "approve", batch, "--only", "p4"])
        assert "1 written, 3 left staged" in approved.output
        rejected = CliRunner().invoke(main, ["notion", "reject", batch, "--reason", "Not now."])
        assert f"{batch} is rejected" in rejected.output
