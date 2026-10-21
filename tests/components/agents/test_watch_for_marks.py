"""Design 0012 §8 and §11 step 8 (decision 0053): the marks the Watch for rules leave, kept in the service, each taken
once; what each rule then does follows its setting in `config/monitor.json`: the mark alone, pause, tell the phone, tell
the model and go on, telling the model at most `notes_in_a_row` times in a row for one rule in a session, after which
the rule marks, pauses and tells the phone; the count starts again at the owner's own message, and at a step that
finished cleanly after the rule's last note (decision 0083). An action that cannot run (the pause, step 11's; the note
when no Guide is given) tells the phone instead and says why (decision 0082). A mark on a step, or on a note, from
before Clank watched does nothing more. Marks seen leave the count of those not seen; a mark of an ask no longer waiting
leaves the phone's list. Design 0012 §3: a subagent's mark never notes the subagent (the Guide acts on the root
session), and tells the phone instead; a mark dropped to keep the newest is never made, nor acted on, again; a session
whose flow the service no longer keeps is forgotten."""

from collections.abc import Collection, Iterator
from typing import Any

import pytest

from clank import registry
from clank.components.agents.kinds import MonitorSettings
from clank.components.agents.sessionflow.flow import Flow
from clank.components.agents.watchfor import marks as marks_module
from clank.components.agents.watchfor.marks import Marks, Unavailable
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.agents.test_watch_for_rules import (
    APART,
    BEGUN,
    LIMITS,
    flow_of,
    one_file_again,
    request,
    said,
    same_call_again,
    waiting_for_you,
)
from tests.support.flowlines import SESSION, lines, page, status, step, text, updated, user

YOU = Actor(kind="user", via="console")
LOOP_ERROR = {"name": "APIError", "data": {"message": "Clank's loop guard stopped the answer: the thinking repeated"}}


class Acting:
    """What a rule asks of the Guide, recorded; refused with `refusing` when set."""

    def __init__(self, refusing: str = "") -> None:
        self.notes: list[tuple[str, int | None, str, str]] = []
        self.pauses: list[tuple[str, str]] = []
        self.refusing = refusing

    def note(self, workspace: str, port: int | None, session: str, text: str) -> None:
        if self.refusing:
            raise Unavailable(self.refusing)
        self.notes.append((workspace, port, session, text))

    def pause(self, workspace: str, session: str) -> None:
        if self.refusing:
            raise Unavailable(self.refusing)
        self.pauses.append((workspace, session))


@pytest.fixture
def kernel(home: Home, clock: FakeClock) -> Iterator[Kernel]:
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def settings(**rules: list[str]) -> MonitorSettings:
    """Clank's settings, with these rules doing these actions (each keeps its own note's words)."""
    return MonitorSettings.model_validate({name: {"do": do} for name, do in rules.items()})


def marks_of(kernel: Kernel, chosen: MonitorSettings, acting: Any = None) -> Marks:
    if acting is None:
        return Marks(lambda: chosen, kernel.clock, kernel.events)
    return Marks(lambda: chosen, kernel.clock, kernel.events, acting)


def events(kernel: Kernel, type: str) -> list[Any]:
    return kernel.events.after(0, types=[type])


def looped(count: int, *, saying: dict[int, str] | None = None, clean: Collection[int] = ()) -> Flow:
    """A session whose `count` steps each ended in the loop guard's stop, but those numbered in `clean`, which finished
    cleanly; `saying` puts a message of the owner's (or a note Clank sent) before the step of that number."""
    made = [said()]
    for n in range(1, count + 1):
        created = BEGUN + n * APART
        if saying and n in saying:
            made.append(user(f"msg_s{n}", created - 1000, saying[n]))
        if n in clean:
            made.append(step(f"msg_{n:02}", "msg_u0", created, [text(f"p{n}", "Done.")], completed=created + 4000))
            continue
        made.append(step(f"msg_{n:02}", "msg_u0", created, [text(f"p{n}", "again", "reasoning")],
                         completed=created + 4000, error=LOOP_ERROR))  # fmt: skip
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(made))
    flow.heard({"type": "status", "session": SESSION, "status": "idle", "port": 4096})
    return flow


def test_a_rule_marks_once_and_each_action_follows_its_setting(kernel: Kernel) -> None:
    acting = Acting()
    chosen = settings(same_call_again=["mark", "tell the phone"], one_file_again=["mark", "pause"],
                      loop_guard_stopped=["tell the model"])  # fmt: skip
    marks = marks_of(kernel, chosen, acting)
    flow, _ = same_call_again()
    [made] = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert (made["rule"], made["name"], made["node"], made["workspace"], made["session"]) == (
        "same_call_again", "The same call again", "c4", "paper", SESSION
    )  # fmt: skip
    assert "3 times in the last 12" in made["why"]
    assert made["fires"] == "the same call three times or more in the last 12"
    assert (made["phone"], made["seen"], made["before"]) == (True, False, False)
    assert [(each["action"], each["done"]) for each in made["did"]] == [("mark", True), ("tell the phone", True)]
    assert marks.check("paper", SESSION, flow.view(), LIMITS) == [], "the same mark is taken once"
    assert [each["id"] for each in marks.marks()] == [made["id"]]
    [marked] = events(kernel, "agents.marked")
    assert marked.data["rule"] == "same_call_again"
    assert marked.data["did"] == ["mark", "tell the phone"]
    assert marked.actor.describe() == "Clank (watch for)"

    flow, _ = one_file_again()
    [paused] = marks.check("paper", "ses_files", flow.view(), LIMITS)
    assert acting.pauses == [("paper", "ses_files")]
    assert ([(each["action"], each["done"]) for each in paused["did"]], paused["phone"]) == (
        [("mark", True), ("pause", True)], False
    )  # fmt: skip

    [told] = marks.check("paper", SESSION, looped(1).view(), LIMITS)
    assert [(each["action"], each["done"]) for each in told["did"]] == [("mark", True), ("tell the model", True)]
    assert acting.notes == [("paper", 4096, SESSION, chosen.rule("loop_guard_stopped").note)]
    assert told["phone"] is False


def test_a_rule_turned_off_marks_nothing(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings(same_call_again=[]))
    flow, _ = same_call_again()
    assert marks.check("paper", SESSION, flow.view(), LIMITS) == []
    assert marks.marks() == []
    assert events(kernel, "agents.marked") == []


def test_tell_the_model_stops_at_its_cap_then_marks_pauses_and_tells_the_phone(kernel: Kernel) -> None:
    acting = Acting()
    marks = marks_of(kernel, settings(), acting)
    for count in (1, 2):
        [made] = marks.check("paper", SESSION, looped(count).view(), LIMITS)
        assert ("tell the model", True) in [(each["action"], each["done"]) for each in made["did"]]
    assert len(acting.notes) == 2
    [capped] = marks.check("paper", SESSION, looped(3).view(), LIMITS)
    assert len(acting.notes) == 2, "no third note in a row"
    did = {each["action"]: each for each in capped["did"]}
    assert did["tell the model"]["done"] is False
    assert "2 notes in a row" in did["tell the model"]["why"]
    assert did["pause"]["done"] is True
    assert did["tell the phone"]["done"] is True
    assert acting.pauses == [("paper", SESSION)]
    assert capped["phone"] is True


def test_the_cap_starts_again_after_the_owners_own_message(kernel: Kernel) -> None:
    acting = Acting()
    chosen = settings()
    marks = marks_of(kernel, chosen, acting)
    note = chosen.rule("loop_guard_stopped").note
    marks.check("paper", SESSION, looped(1).view(), LIMITS)
    marks.check("paper", SESSION, looped(2, saying={2: note}).view(), LIMITS)
    [capped] = marks.check("paper", SESSION, looped(3, saying={2: note, 3: note}).view(), LIMITS)
    assert len(acting.notes) == 2, "the notes Clank sent are not the owner's own"
    assert capped["phone"] is True
    owner = {2: note, 3: note, 4: "Go on with the plot, please."}
    [again] = marks.check("paper", SESSION, looped(4, saying=owner).view(), LIMITS)
    assert len(acting.notes) == 3, "the owner's own message starts the count again"
    assert again["phone"] is False


def test_a_step_finished_cleanly_after_a_note_starts_the_count_again(kernel: Kernel) -> None:
    acting = Acting()
    marks = marks_of(kernel, settings(), acting)
    for count in (1, 3, 5):  # stopped at steps 1, 3 and 5, each time with a clean step after the note before
        [made] = marks.check("paper", SESSION, looped(count, clean=range(2, count, 2)).view(), LIMITS)
        assert made["node"] == f"msg_{count:02}"
        assert made["phone"] is False
    assert len(acting.notes) == 3, "no two notes in a row: the one before worked for a step"
    assert acting.pauses == []
    for count in (6, 7):
        marks.check("paper", SESSION, looped(count, clean=(2, 4)).view(), LIMITS)
    assert len(acting.notes) == 4, "stopped at 5, 6 and 7 in a row: the third waits for you"
    assert acting.pauses == [("paper", SESSION)]


def test_an_action_not_built_yet_tells_the_phone_instead_and_says_why(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings(one_file_again=["mark", "pause"]))
    [told] = marks.check("paper", SESSION, looped(1).view(), LIMITS)
    did = {each["action"]: each for each in told["did"]}
    assert did["tell the model"]["done"] is False
    assert "design 0012 §11 step 9" in did["tell the model"]["why"]
    assert did["tell the phone"]["done"] is True
    assert "instead" in did["tell the phone"]["why"]
    assert told["phone"] is True
    flow, _ = one_file_again()
    [paused] = marks.check("paper", "ses_files", flow.view(), LIMITS)
    pause = {each["action"]: each for each in paused["did"]}["pause"]
    assert (pause["done"], "design 0012 §11 step 11" in pause["why"]) == (False, True)
    assert paused["phone"] is True
    refused = marks_of(kernel, settings(), Acting(refusing="the bridge refused: no such session"))
    [failed] = refused.check("paper", "ses_other", looped(1).view(), LIMITS)
    assert {each["action"]: each for each in failed["did"]}["tell the model"]["why"] == (
        "the bridge refused: no such session"
    )  # fmt: skip
    assert failed["phone"] is True


def test_a_mark_on_a_step_from_before_clank_watched_does_nothing_more(kernel: Kernel) -> None:
    acting = Acting()
    marks = marks_of(kernel, settings(), acting)
    made = [said(), step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "again", "reasoning")],
                         completed=BEGUN + APART + 4000, error=LOOP_ERROR)]  # fmt: skip
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(made), joined=True)
    [kept] = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert (kept["before"], kept["seen"], kept["phone"]) == (True, True, False)
    assert [each["action"] for each in kept["did"]] == ["mark"]
    assert "before Clank watched" in kept["did"][0]["why"]
    assert acting.notes == []
    assert events(kernel, "agents.marked") == []
    assert marks.unseen() == 0


def test_a_note_not_read_from_before_clank_watched_does_nothing_more(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings(note_not_read=["mark", "tell the phone"]))
    answered = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "Done.")], completed=BEGUN + APART + 5000)
    note = user("msg_n1", BEGUN + APART + 2000, "Use a log scale.")
    flow = Flow(SESSION, workspace="paper")
    flow.history(page([said(), answered, note]), joined=True)  # as after a restart of the service
    [kept] = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert (kept["rule"], kept["before"], kept["seen"], kept["phone"]) == ("note_not_read", True, True, False)
    assert events(kernel, "agents.marked") == []
    assert (marks.unseen(), marks.phone()) == (0, [])


def test_a_note_waiting_when_clank_joined_whose_run_ended_after_acts(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings(note_not_read=["mark", "tell the phone"]))
    working = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "Reading")])
    note = user("msg_n1", BEGUN + APART + 2000, "Use a log scale.")
    flow = Flow(SESSION, workspace="paper")
    flow.history(page([said(), working, note]), joined=True)  # step 1 under way: watched from here
    for line in lines([status("busy")]):
        flow.heard(line)
    assert marks.check("paper", SESSION, flow.view(), LIMITS) == [], "the note still waits"
    ended = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "Done.")], completed=BEGUN + APART + 5000)
    for line in lines([*updated(ended), status("idle")]):
        flow.heard(line)
    [made] = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert (made["rule"], made["before"], made["phone"]) == ("note_not_read", False, True)
    assert [each.data["rule"] for each in events(kernel, "agents.marked")] == ["note_not_read"]


def test_a_mark_of_an_ask_no_longer_waiting_leaves_the_phones_list(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings())
    flow, _ = waiting_for_you()
    told = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert sorted(each["key"] for each in told) == ["ask:per_1", "question:c2"]
    assert len(marks.phone()) == 2
    replied = {"sessionID": SESSION, "requestID": "per_1", "reply": "once"}
    for line in lines([{"type": "permission.replied", "properties": replied}]):
        flow.heard(line)
    marks.check("paper", SESSION, flow.view(), LIMITS)
    assert [each["key"] for each in marks.phone()] == ["question:c2"], "the approval was answered"
    [over] = [each for each in marks.marks() if each["key"] == "ask:per_1"]
    assert (over["over"], over["seen"]) == (True, False), "still in the Watch for panel until seen"
    assert marks.unseen() == 2


def test_a_session_whose_flow_is_no_longer_kept_is_forgotten(kernel: Kernel) -> None:
    class Kept:
        """The flows the service keeps, as the rules read them."""

        def __init__(self) -> None:
            self.flows: dict[tuple[str, str], Flow] = {}

        def changed(self, versions: dict[tuple[str, str], int]) -> list[tuple[str, str, int, dict[str, Any]]]:
            return [(*key, flow.version, flow.view()) for key, flow in self.flows.items()
                    if versions.get(key) != flow.version]  # fmt: skip

        def keys(self) -> set[tuple[str, str]]:
            return set(self.flows)

    kept = Kept()
    marks = marks_of(kernel, settings())
    kept.flows[("paper", SESSION)] = looped(1)
    kept.flows[("paper", "ses_other")] = same_call_again()[0]
    assert marks.watch(kept, lambda: LIMITS) == 2
    assert {each["session"] for each in marks.marks()} == {SESSION, "ses_other"}
    del kept.flows[("paper", SESSION)]
    marks.watch(kept, lambda: LIMITS)
    assert {each["session"] for each in marks.marks()} == {"ses_other"}
    for record in (marks._kept, marks._said, marks._sent, marks._made, marks._versions):
        assert ("paper", SESSION) not in record, "nothing of it stays in memory"
    assert not [counted for counted in marks._in_a_row if counted[:2] == ("paper", SESSION)]


def test_marks_seen_leave_the_count_of_those_not_seen(kernel: Kernel) -> None:
    marks = marks_of(kernel, settings(same_call_again=["mark", "tell the phone"]))
    flow, _ = same_call_again()
    [phoned] = marks.check("paper", SESSION, flow.view(), LIMITS)
    working = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "thinking", "reasoning")])
    found = [request("r-1", BEGUN + APART + 300, counts={"thinking": 3700, "answer": 0, "tool": 0}, tokens=3700,
                     phase="answering")]  # fmt: skip
    [near] = marks.check("paper", "ses_b", flow_of([said(), working], requests=found).view(), LIMITS)
    assert marks.unseen() == 2
    assert [each["id"] for each in marks.phone()] == [phoned["id"]]
    assert [each["id"] for each in marks.marks(session="ses_b")] == [near["id"]]
    assert marks.seen([phoned["id"]], actor=YOU) == 1
    assert marks.unseen() == 1
    assert marks.phone() == [], "seen: no longer listed for the phone"
    assert marks.seen(workspace="paper", session="ses_b", actor=YOU) == 1
    assert marks.unseen() == 0
    seen = events(kernel, "agents.marks_seen")
    assert [each.data["marks"] for each in seen] == [[phoned["id"]], [near["id"]]]
    assert all(each.actor == YOU for each in seen)


def test_a_subagents_mark_tells_the_phone_and_never_the_subagent(kernel: Kernel) -> None:
    acting = Acting()
    marks = marks_of(kernel, settings(), acting)
    flow = looped(1)
    flow.heard({"type": "session", "session": {"id": SESSION, "parent": "ses_root", "title": "a subagent"}})
    [made] = marks.check("paper", SESSION, flow.view(), LIMITS)
    assert acting.notes == [], "the Guide acts on the root session (design 0012 §3)"
    did = {each["action"]: each for each in made["did"]}
    assert did["tell the model"]["done"] is False
    assert "subagent" in did["tell the model"]["why"]
    assert made["phone"] is True


def test_a_mark_dropped_to_keep_the_newest_is_never_made_again(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(marks_module, "KEPT", 1)
    marks = marks_of(kernel, settings())
    assert len(marks.check("paper", SESSION, looped(2).view(), LIMITS)) == 2
    assert len(marks.marks()) == 1, "the newest kept"
    assert marks.check("paper", SESSION, looped(2).view(), LIMITS) == [], "the older one is not made again"
    assert len(events(kernel, "agents.marked")) == 2
