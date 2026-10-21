"""Design 0010 §7: the owner comments on a batch, on a proposal, on a property of it or on a block of its page (never
the agent), and takes back a comment not sent yet; sending the batch back marks it returned and tells the agent, in
one message to the session that submitted it, each comment with what it is about, and what to do. The agent revises
the returned batch with the same tools: a proposal for the same entry (or a new entry of the same title) replaces the
one in the batch, keeping its number and what it was (one that is written in part is never replaced); it answers
each comment (`reply`), and submitting makes the batch's next revision. No comment's words are in an event."""

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
from clank.components.notion.service import NotAllowed, Notion, NotionRefused
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, FakeNotion

YOU = Actor(kind="user", via="vscode")
AGENT = Actor(kind="session", via="the agent")


class FakeAgent:
    """The workspace's agent, as the notion component reaches it: the session that runs, and what it was sent."""

    def __init__(self) -> None:
        self.running: dict[str, Any] | None = {"port": 4096, "session": "ses_1"}
        self.sent: list[dict[str, Any]] = []

    def session(self, workspace: str) -> dict[str, Any] | None:
        return self.running

    def send(
        self, workspace: str, text: str, session: dict[str, Any] | None, *, title: str, actor: Actor
    ) -> dict[str, Any]:
        self.sent.append({"workspace": workspace, "text": text, "session": session, "title": title})
        return {"port": 4096, "session": (session or {}).get("session") or "ses_new", "new": session is None}


@pytest.fixture
def notion() -> FakeNotion:
    return FakeNotion()


@pytest.fixture
def kernel(home: Home, notion: FakeNotion) -> Iterator[Kernel]:
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 17, 20, 0, tzinfo=UTC)), registry.components())
    part: Notion = kernel.parts["notion"]
    part.transport = notion.transport
    part.sleep = notion.wait
    part.agent = FakeAgent()
    part.connect(SECRET, actor=YOU)
    yield kernel
    kernel.close()


@pytest.fixture
def part(kernel: Kernel) -> Notion:
    found: Notion = kernel.parts["notion"]
    return found


def submitted(part: Notion) -> str:
    part.propose_entry("paper", "Papers (test)", {"Title": "A third made-up paper", "Authors": "Who, Ever"},
                       markdown="## Summary\n\nWhat it shows.", why="a test")  # fmt: skip
    part.propose_change("paper", "lit-1", properties={"Year": 2002}, why="the published year", sources=["plan.md"])
    part.propose_removal("paper", "lit-2", why="a duplicate")
    return str(part.submit("paper", "Three things.")["id"])


def test_the_owner_comments_on_the_batch_a_proposal_a_property_and_a_block_and_the_agent_cannot(part: Notion) -> None:
    batch = submitted(part)
    part.comment(batch, "Fewer at a time, please.", actor=YOU)
    part.comment(batch, "Is 2002 the journal's year?", proposal="p2", field="Year", actor=YOU)
    part.comment(batch, "Say what it shows in numbers.", proposal="p1", block=1, actor=YOU)
    part.comment(batch, "Keep this one.", proposal="p3", actor=YOU)
    comments = part.batch(batch)["comments"]
    assert [(each["id"], each["proposal"], each["field"], each["block"]) for each in comments] == [
        ("c1", None, None, None),
        ("c2", "p2", "Year", None),
        ("c3", "p1", None, 1),
        ("c4", "p3", None, None),
    ]
    assert comments[2]["block_text"] == "What it shows."
    assert (comments[1]["state"], comments[1]["sent"], comments[1]["revision"]) == ("open", False, 1)
    assert part.batches()[0]["comment_counts"] == {"all": 4, "open": 4, "unsent": 4}
    for wrong, said in (
        ({"proposal": "p9"}, "no proposal p9"),
        ({"proposal": "p3", "block": 0}, "no block 0"),
        ({"proposal": "p1", "block": 5}, "no block 5"),
        ({"field": "Year"}, "a proposal"),
    ):
        with pytest.raises(NotionRefused, match=said):
            part.comment(batch, "x", actor=YOU, **wrong)
    with pytest.raises(NotionRefused, match="says nothing"):
        part.comment(batch, "  ", actor=YOU)
    with pytest.raises(NotAllowed):
        part.comment(batch, "I approve of myself.", actor=AGENT)
    part.uncomment(batch, "c4", actor=YOU)
    assert [each["id"] for each in part.batch(batch)["comments"]] == ["c1", "c2", "c3"]


def test_sending_back_tells_the_agent_each_comment_with_what_it_is_about(part: Notion, kernel: Kernel) -> None:
    batch = submitted(part)
    assert part.batch(batch)["session"] == {"port": 4096, "session": "ses_1"}, "the session that submitted it"
    with pytest.raises(NotionRefused, match="comment"):
        part.send_back(batch, actor=YOU)
    part.comment(batch, "Fewer at a time, please.", actor=YOU)
    part.comment(batch, "Is 2002 the journal's year?", proposal="p2", field="Year", actor=YOU)
    part.comment(batch, "Say what it shows in numbers.", proposal="p1", block=1, actor=YOU)
    returned = part.send_back(batch, actor=YOU)
    assert (returned["state"], returned["sent_to"]) == ("returned", {"port": 4096, "session": "ses_1", "new": False})
    [message] = part.agent.sent
    assert message["session"] == {"port": 4096, "session": "ses_1"}
    text = message["text"]
    assert f"batch {batch}" in text
    assert "revision 1" in text
    assert '- c1, on the whole batch: "Fewer at a time, please."' in text
    assert (
        '- c2, on p2 (a change to "A made-up paper on sampling" in Papers (test)), its property Year '
        '(proposed: 2002; in Notion: 2001): "Is 2002 the journal\'s year?"'
    ) in text
    assert (
        '- c3, on p1 (a new entry "A third made-up paper" in Papers (test)), the block of its page "What it '
        'shows.": "Say what it shows in numbers."'
    ) in text
    assert "notion_reply" in text
    assert "notion_submit" in text
    assert all(each["sent"] for each in part.batch(batch)["comments"])
    with pytest.raises(NotionRefused, match="sent"):
        part.uncomment(batch, "c1", actor=YOU)
    [event] = kernel.events.after(0, types=["notion.returned"])
    assert "Fewer" not in event.summary
    assert "Fewer" not in str(event.data)


def test_a_batch_whose_session_is_gone_goes_to_a_new_session(part: Notion) -> None:
    part.agent.running = None
    batch = submitted(part)
    part.comment(batch, "Fewer.", actor=YOU)
    assert part.send_back(batch, actor=YOU)["sent_to"]["new"] is True


def test_the_agent_revises_a_returned_batch_and_answers_its_comments(part: Notion) -> None:
    batch = submitted(part)
    part.comment(batch, "Is 2002 the journal's year?", proposal="p2", field="Year", actor=YOU)
    part.send_back(batch, actor=YOU)
    revised = part.propose_change("paper", "lit-1", properties={"Year": 2003}, why="the journal's year",
                                  sources=["the journal"])  # fmt: skip
    assert (revised["batch"], revised["proposal"]) == (batch, "p2"), "it replaces the proposal for the same entry"
    added = part.propose_entry("paper", "Papers (test)", {"Title": "A fourth made-up paper"}, why="a test")
    assert (added["batch"], added["proposal"]) == (batch, "p4")
    again = part.propose_entry("paper", "Papers (test)", {"Title": "A third made-up paper", "Authors": "Who, Else"},
                               why="a test")  # fmt: skip
    assert again["proposal"] == "p1", "a new entry of the same title replaces the one proposed"
    with pytest.raises(NotionRefused, match="no comment c9"):
        part.reply("paper", "c9", "Done.")
    part.reply("paper", "c1", "The journal's year is 2003; changed.")
    resubmitted = part.submit("paper", "Three things, revised.")
    assert (resubmitted["id"], resubmitted["state"], resubmitted["revision"]) == (batch, "ready", 2)
    whole = part.batch(batch)
    change = whole["proposals"][1]
    assert (change["fields"][0]["now"], change["revision"], change["previous"]["fields"][0]["now"]) == (
        "2003",
        2,
        "2002",
    )
    assert whole["proposals"][2]["revision"] == 1, "the removal was not revised"
    [comment] = whole["comments"]
    assert (comment["state"], comment["replies"][0]["text"]) == ("answered", "The journal's year is 2003; changed.")
    assert part.batches()[0]["comment_counts"] == {"all": 1, "open": 0, "unsent": 0}


def test_a_proposal_written_in_part_is_never_replaced(part: Notion) -> None:
    batch = submitted(part)
    part.approve(batch, parts={"p2": ["Year"]}, actor=YOU)
    part.comment(batch, "And the reading status?", proposal="p2", actor=YOU)
    part.send_back(batch, actor=YOU)
    staged = part.propose_change("paper", "lit-1", properties={"Reading": "To read"}, why="not read yet")
    assert (staged["batch"], staged["proposal"]) == (batch, "p4")
    assert part.submit("paper", "The reading status.")["state"] == "partly written"


def test_the_routes_take_comments_and_a_send_back_from_the_owner_and_replies_from_the_agent(
    kernel: Kernel, part: Notion, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = submitted(part)
    with TestClient(create_app(kernel, token="t", port=7739), base_url="http://127.0.0.1:7739") as http:
        you = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
        agent = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}
        made = http.post(f"/api/v1/notion/batches/{batch}/comments", headers=you,
                         json={"text": "Which year?", "proposal": "p2", "field": "Year"})  # fmt: skip
        assert made.status_code == 200, made.text
        assert made.json()["id"] == "c1"
        refused = http.post(f"/api/v1/notion/batches/{batch}/comments", headers=agent, json={"text": "Mine."})
        assert refused.status_code == 403
        http.post(f"/api/v1/notion/batches/{batch}/comments", headers=you, json={"text": "Gone soon."})
        assert http.delete(f"/api/v1/notion/batches/{batch}/comments/c2", headers=you).status_code == 200
        assert http.post(f"/api/v1/notion/batches/{batch}/return", headers=agent).status_code == 403
        sent = http.post(f"/api/v1/notion/batches/{batch}/return", headers=you)
        assert sent.status_code == 200, sent.text
        assert sent.json()["state"] == "returned"
        replied = http.post("/api/v1/notion/reply", headers=agent,
                            json={"workspace": "paper", "comment": "c1", "text": "It is 2002."})  # fmt: skip
        assert replied.status_code == 200, replied.text
        assert replied.json()["state"] == "answered"
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7739", "t", name="cli", http=http))
        shown = CliRunner().invoke(main, ["notion", "show", batch])
        assert '    c1 on p2, Year (answered): "Which year?"' in shown.output
        assert '        the agent: "It is 2002."' in shown.output


def test_clank_notion_comments_and_sends_a_batch_back(
    kernel: Kernel, part: Notion, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch = submitted(part)
    with TestClient(create_app(kernel, token="t", port=7740), base_url="http://127.0.0.1:7740") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7740", "t", name="cli", http=http))
        made = CliRunner().invoke(main, ["notion", "comment", batch, "Is 2002 right?", "--on", "p2:Year"])
        assert made.exit_code == 0, made.output
        assert f"c1 is kept with {batch}" in made.output
        CliRunner().invoke(main, ["notion", "comment", batch, "Say it in numbers.", "--on", "p1:block:1"])
        sent = CliRunner().invoke(main, ["notion", "send-back", batch])
        assert sent.exit_code == 0, sent.output
        assert f"{batch} is sent back to the agent (session ses_1)" in sent.output
    assert [(each["field"], each["block"]) for each in part.batch(batch)["comments"]] == [("Year", None), (None, 1)]
