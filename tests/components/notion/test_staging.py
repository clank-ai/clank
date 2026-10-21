"""Design 0010 §5: the agent proposes a new entry, a change or a removal; each proposal is checked against its
database's properties when staged and refused with the reason the agent can fix (a property that is not there, a value
that does not fit, a relation to an entry that cannot be found, numbers without their sources, an image or a block
Clank cannot make yet); it is kept with the entry as it was (its properties, its page and when it was edited), a change
with its fields and its page compared block by block, in the workspace's open batch, which `submit` makes ready for
review. A relation may point to an entry proposed in the same batch. Nothing is written to Notion. Batches are files in
Clank's state, read again after a restart; staging is recorded without content."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.notion.service import Notion, NotionRefused
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, FakeNotion

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
YOU = Actor(kind="user", via="cli")
PAPER = {
    "Title": "A third made-up paper",
    "Authors": "Who, Ever",
    "Year": 2005,
    "Keywords": ["walks", "lattices"],
    "Reading": "To read",
    "Concepts": ["Made-up quantity"],
}
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


def writes(notion: FakeNotion) -> list[str]:
    """The requests that would change Notion."""
    return [f"{sent.method} {sent.path}" for sent in notion.requests
            if sent.method in ("PATCH", "DELETE") or (sent.method == "POST" and sent.path == "/v1/pages")]  # fmt: skip


def test_a_new_entry_is_staged_in_the_workspaces_open_batch_checked_against_its_database(
    kernel: Kernel, part: Notion, notion: FakeNotion
) -> None:
    staged = part.propose_entry(
        "paper", "Papers (test)", PAPER, markdown="## Summary\n\nA made-up summary.",
        why="the plan cites it", sources=["studies/x/plan.md"],
    )  # fmt: skip
    assert staged["proposal"] == "p1"
    assert staged["notes"] == ["Keywords gains a new option: lattices"]
    batch = part.batch(staged["batch"])
    assert (batch["workspace"], batch["state"], batch["revision"]) == ("paper", "open", 1)
    [proposal] = batch["proposals"]
    assert (proposal["kind"], proposal["database"], proposal["title"]) == ("entry", "ds-lit", "A third made-up paper")
    assert proposal["fields"][:3] == [
        {"name": "Title", "was": "", "now": "A third made-up paper"},
        {"name": "Authors", "was": "", "now": "Who, Ever"},
        {"name": "Year", "was": "", "now": "2005"},
    ]
    assert {"name": "Concepts", "was": "", "now": "Made-up quantity"} in proposal["fields"]
    assert proposal["payload"]["Concepts"] == {"relation": [{"id": "obs-1"}]}
    assert proposal["markdown"] == "## Summary\n\nA made-up summary."
    assert (proposal["why"], proposal["sources"], proposal["base"]) == (
        "the plan cites it",
        ["studies/x/plan.md"],
        None,
    )
    assert (kernel.home.state / "notion" / "batches" / f"{staged['batch']}.json").is_file()
    assert writes(notion) == [], "nothing is written to Notion while staging"


@pytest.mark.parametrize(
    ("properties", "markdown", "sources", "said"),
    [
        ({**PAPER, "Pages": "12"}, "", ["x"], "Pages is not a property of Papers (test): its properties are Title"),
        ({"Authors": "Who, Ever"}, "", [], "a new entry needs its Title"),
        ({**PAPER, "Reading": "Skimmed"}, "", ["x"], "Reading's status must be one of: To read, Notes written"),
        ({**PAPER, "Concepts": ["Nothing like it"]}, "", ["x"],
         "no entry of Concepts (test) is titled Nothing like it"),
        (PAPER, "", [], "this proposal states numbers: give their sources"),
        ({"Title": "Plain"}, "![a figure](figures/x.png)", [], "an image from a file is not built yet"),
        ({"Title": "Plain"}, "[a table block, which Clank cannot show yet]", [], "only Notion has that block"),
        ({"Title": "Plain"}, "- a\n  - b\n    - c\n      - d", [], "nested more than three levels deep"),
    ],
)  # fmt: skip
def test_a_proposal_that_does_not_fit_is_refused_with_the_reason(
    part: Notion, properties: dict[str, Any], markdown: str, sources: list[str], said: str
) -> None:
    with pytest.raises(NotionRefused, match=said.replace("(", r"\(").replace(")", r"\)")):
        part.propose_entry("paper", "Papers (test)", properties, markdown=markdown, why="a test", sources=sources)
    assert part.batches(workspace="paper") == [], "nothing was staged"


def test_a_change_keeps_the_entry_as_it_was_with_its_fields_and_its_page_compared(part: Notion) -> None:
    page = LIT_1_PAGE.replace("A made-up result about", "A made-up, corrected result about") + "\n\nA new closing line."
    staged = part.propose_change(
        "paper", "lit-1", properties={"Year": 2002, "Reading": "Notes written"}, markdown=page,
        why="the year was wrong", sources=["the paper's first page"],
    )  # fmt: skip
    [proposal] = part.batch(staged["batch"])["proposals"]
    assert (proposal["kind"], proposal["page"], proposal["title"]) == (
        "change",
        "lit-1",
        "A made-up paper on sampling",
    )
    assert proposal["fields"] == [{"name": "Year", "was": "2001", "now": "2002"}], "an unchanged field is left out"
    assert proposal["base"]["edited"] == "2026-10-17T12:00:00.000Z"
    assert proposal["base"]["markdown"] == LIT_1_PAGE
    assert [(each["op"], each.get("id")) for each in proposal["changes"]] == [
        ("keep", "b1"), ("update", "b2"), ("keep", "b3"), ("keep", "b4"), ("add", None),
    ]  # fmt: skip
    with pytest.raises(NotionRefused, match="changes nothing"):
        part.propose_change("paper", "lit-1", properties={"Year": 2001}, markdown=LIT_1_PAGE, why="a test",
                            sources=["x"])  # fmt: skip
    with pytest.raises(NotionRefused, match="not shared with Clank's integration"):
        part.propose_change("paper", "nothing-here", properties={"Year": 2001}, why="a test", sources=["x"])


def test_a_relation_may_point_to_an_entry_proposed_in_the_same_batch(part: Notion) -> None:
    concept = part.propose_entry("paper", "Concepts (test)", {"Name": "A new concept"}, why="a test")
    paper = part.propose_entry("paper", "Papers (test)", {"Title": "Plain", "Concepts": ["A new concept"]},
                               why="a test")  # fmt: skip
    assert concept["batch"] == paper["batch"]
    proposal = part.batch(paper["batch"])["proposals"][1]
    assert proposal["payload"]["Concepts"] == {"relation": [{"id": "proposal:p1"}]}
    assert {"name": "Concepts", "was": "", "now": "A new concept"} in proposal["fields"]


def test_a_removal_names_a_shared_entry_and_why(part: Notion) -> None:
    staged = part.propose_removal("paper", "lit-2", why="a duplicate of lit-1")
    [proposal] = part.batch(staged["batch"])["proposals"]
    assert (proposal["kind"], proposal["page"], proposal["why"]) == ("removal", "lit-2", "a duplicate of lit-1")
    assert proposal["base"]["properties"]["Authors"] == "Nobody, In Particular"
    with pytest.raises(NotionRefused, match="say why"):
        part.propose_removal("paper", "lit-1", why=" ")


def test_submitting_makes_the_batch_ready_and_the_next_proposal_opens_another(part: Notion) -> None:
    with pytest.raises(NotionRefused, match="nothing is staged"):
        part.submit("paper", "nothing yet")
    first = part.propose_removal("paper", "lit-2", why="a duplicate")["batch"]
    ready = part.submit("paper", "One duplicate removed.")
    assert (ready["id"], ready["state"], ready["summary"]) == (first, "ready", "One duplicate removed.")
    second = part.propose_removal("paper", "lit-1", why="a test")["batch"]
    assert second != first
    other = part.propose_removal("other", "lit-1", why="a test")["batch"]
    assert other not in (first, second), "each workspace has its own batch"
    listed = part.batches(workspace="paper")
    assert [(each["id"], each["state"], each["counts"]) for each in listed] == [
        (second, "open", {"new": 0, "changed": 0, "removed": 1}),
        (first, "ready", {"new": 0, "changed": 0, "removed": 1}),
    ]


def test_batches_are_read_again_after_a_restart_and_staging_is_recorded_without_content(
    kernel: Kernel, part: Notion
) -> None:
    staged = part.propose_entry("paper", "Papers (test)", PAPER, why="a test", sources=["plan.md"])
    again = Notion(kernel)
    assert again.batch(staged["batch"])["proposals"][0]["title"] == "A third made-up paper"
    [event] = kernel.events.after(0, types=["notion.staged"])
    assert event.data == {"batch": staged["batch"], "proposal": "p1", "kind": "entry", "database": "ds-lit"}
    kept = json.dumps([each.data for each in kernel.events.after(0)]) + " ".join(
        each.summary for each in kernel.events.after(0)
    )
    assert "A third made-up paper" not in kept
    assert "Who, Ever" not in kept


def test_the_routes_stage_submit_and_list(kernel: Kernel) -> None:
    with TestClient(create_app(kernel, token="t", port=7733), base_url="http://127.0.0.1:7733") as http:

        def call(method: str, path: str, status: int = 200, **body: Any) -> Any:
            answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=body or None)
            assert answer.status_code == status, answer.text
            return answer.json()

        staged = call("POST", "notion/propose/entry", workspace="paper", database="Papers (test)",
                      properties={"Title": "Plain"}, why="a test")  # fmt: skip
        call("POST", "notion/propose/change", workspace="paper", page="lit-1", properties={"Reading": "To read"},
             why="a test")  # fmt: skip
        call("POST", "notion/propose/removal", workspace="paper", page="lit-2", why="a test")
        refused = call("POST", "notion/propose/removal", 409, workspace="paper", page="nothing-here", why="a test")
        assert "not shared" in refused["error"]["message"]
        assert call("POST", "notion/submit", workspace="paper", summary="Three things.")["state"] == "ready"
        [batch] = call("GET", "notion/batches?workspace=paper")["batches"]
        assert (batch["id"], batch["counts"]) == (staged["batch"], {"new": 1, "changed": 1, "removed": 1})
        assert len(call("GET", f"notion/batches/{staged['batch']}")["proposals"]) == 3
