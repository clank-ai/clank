"""Design 0012 §9.4 and §11 step 11 (decision 0055): the gateway's holds. A paused session's requests are held, and its
subagents' at any depth (a request names only its direct parent, so the gateway keeps the parents it heard); a held
request is told so at once and then kept alive with a comment line within every keep-alive, well under the 300 s
OpenCode waits without bytes, until the owner resumes; a note's release closes only the session's own requests held
before the note was sent, never the one that carries it, and the pause stays; and the pauses outlive the gateway's
restart, in their file. The clock and the wait are fakes; the sessions are synthetic."""

from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from clank.components.gateway.holds import KEEP_SECONDS, Holds, Released
from clank.kernel.clock import FakeClock, to_text

ROOT = "ses_0c2e9ffe1Qk2Lr8xYb3Zd7a1f0"
CHILD = "ses_0d4c3ffe0Hn5Tq1wVc6Ma7a1f1"
GRANDCHILD = "ses_0d5a1ffe2Pq7Rs3tUv9Wx1y2z3"
OTHER = "ses_0e7b2ffe3Ab4Cd5eFg6Hi7Jk8L9"
OPENCODE_GIVES_UP = 300.0  # seconds without headers or bytes (OpenCode's provider/provider.ts)


def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 20, 12, 22, tzinfo=UTC))


def test_a_paused_session_holds_its_own_requests_and_its_subagents_at_any_depth() -> None:
    holds = Holds(clock=clock())
    holds.pause(ROOT, "you (console)")
    holds.seen(CHILD, ROOT)
    assert holds.holding(ROOT, "") == ROOT
    assert holds.holding(CHILD, ROOT) == ROOT
    assert holds.holding(GRANDCHILD, CHILD) == ROOT  # its parent's parent, as the requests named it
    assert holds.holding(OTHER, "") == ""
    assert holds.holding("", "") == "", "a request that names no session is never held"
    holds.pause(CHILD, "Clank (watch for)")
    assert holds.holding(GRANDCHILD, CHILD) == CHILD, "the nearest pause holds it"


def test_a_held_request_gets_a_comment_line_at_once_and_one_within_every_keep_alive_until_resumed() -> None:
    asked: list[float] = []
    time = clock()

    async def wait(event: anyio.Event, seconds: float) -> bool:
        asked.append(seconds)
        time.advance(seconds)
        if len(asked) == 4:
            holds.resume(ROOT)
        return event.is_set()

    holds = Holds(wait=wait, clock=time)
    holds.pause(ROOT, "you (console)")
    held = holds.take("r-1", ROOT, "")
    assert held is not None
    [shown] = holds.view()
    assert [each["id"] for each in shown["held"]] == ["r-1"]

    async def lines() -> list[bytes]:
        return [line async for line in holds.keep(held)]

    said = anyio.run(lines)
    assert said[0].startswith(b": held by Clank: session "), "told at once why it waits"
    assert b"paused by you (console)" in said[0]
    assert all(line.startswith(b":") and line.endswith(b"\n\n") for line in said), "comment lines only"
    assert len(said) == 4, "one at once, then one each time a keep-alive passed while held"
    assert asked == [KEEP_SECONDS] * 4
    assert KEEP_SECONDS < OPENCODE_GIVES_UP / 10, "well within OpenCode's limit"
    assert (held.how, held.seconds) == ("resumed", 4 * KEEP_SECONDS)
    assert holds.view() == [], "resumed: no pause, nothing held"


def test_a_release_closes_only_the_requests_of_the_session_itself_and_the_pause_stays() -> None:
    holds = Holds(clock=clock())
    holds.pause(ROOT, "you (console)")
    own = holds.take("r-1", ROOT, "")
    child = holds.take("r-2", CHILD, ROOT)
    assert own is not None
    assert child is not None
    assert holds.release(ROOT) == 1

    async def kept() -> None:
        async for _ in holds.keep(own):
            pass

    with pytest.raises(Released):
        anyio.run(kept)
    assert own.how == "released"
    assert not child.event.is_set(), "a subagent's held request stays held"
    [pause] = holds.view()
    assert (pause["session"], [each["id"] for each in pause["held"]]) == (ROOT, ["r-2"])
    assert holds.take("r-3", ROOT, "") is not None, "the pause stays: the next request is held again"


def test_a_release_never_closes_a_request_held_after_the_message_was_sent() -> None:
    time = clock()
    holds = Holds(clock=time)
    holds.pause(ROOT, "you (console)")
    earlier = holds.take("r-1", ROOT, "")
    time.advance(5)
    sent = to_text(time.now())  # the service read its clock, then the bridge sent the message
    at_once = holds.take("r-2", ROOT, "")
    time.advance(0.2)
    carrying = holds.take("r-3", ROOT, "")  # OpenCode's next request, which carries the message
    assert earlier is not None
    assert at_once is not None
    assert carrying is not None
    assert holds.release(ROOT, before=sent) == 1
    assert earlier.how == "released"
    assert not carrying.event.is_set(), "the request that carries the message stays held until the owner resumes"
    assert not at_once.event.is_set(), "one held at that very moment may carry it too: it stays held"
    assert holds.release(ROOT) == 2, "named no time, every request of the session held now is closed"


def test_pausing_twice_keeps_the_first_pause_and_resuming_one_not_paused_says_so() -> None:
    time = clock()
    holds = Holds(clock=time)
    first = holds.pause(ROOT, "you (console)")
    time.advance(60)
    again = holds.pause(ROOT, "you (phone)")
    assert (again["since"], again["by"]) == (first["since"], "you (console)")
    assert (first["already"], again["already"]) == (False, True)
    assert holds.resume(OTHER) is None
    ended = holds.resume(ROOT)
    assert ended is not None
    assert (ended["session"], ended["held"]) == (ROOT, 0)


def test_a_request_resumed_under_another_pause_stays_held_by_it() -> None:
    holds = Holds(clock=clock())
    holds.pause(ROOT, "you (console)")
    holds.pause(CHILD, "Clank (watch for)")
    held = holds.take("r-1", GRANDCHILD, CHILD)
    holds.seen(CHILD, ROOT)
    assert held is not None
    assert held.holder == CHILD
    holds.resume(CHILD)
    assert (held.event.is_set(), held.holder) == (False, ROOT), "its root is still paused"


def test_pauses_are_kept_in_their_file_and_read_again_at_the_next_start(tmp_path: Path) -> None:
    file = tmp_path / "state" / "holds.json"
    holds = Holds(clock=clock(), file=file)
    holds.pause(ROOT, "you (console)")
    holds.pause(OTHER, "you (phone)")
    holds.resume(OTHER)
    again = Holds(clock=clock(), file=file)
    assert [(each["session"], each["by"]) for each in again.view()] == [(ROOT, "you (console)")]
    assert again.holding(ROOT, "") == ROOT
    file.write_text("not json", encoding="utf-8")
    assert Holds(clock=clock(), file=file).view() == [], "a file that cannot be read holds nothing"
