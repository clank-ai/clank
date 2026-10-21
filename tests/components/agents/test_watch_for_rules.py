"""Design 0012 §8 and §11 step 8 (decision 0053): each Watch for rule is a pure function over a session's flow, and of
the facts of the slot its requests reach; it fires on a synthetic flow made for it and stays quiet on a clean one, and
each mark it leaves says why, naming what it rests on. A rule over a stretch of calls marks the call where a streak
reached its count, and again only after the streak ended; a rule whose fact is not known stays quiet. The flows are
made from OpenCode's shapes by the bridge's own functions (plan s15's `tests/support/flowlines.py`)."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from clank.components.agents.sessionflow.flow import Flow
from clank.components.agents.watchfor.rules import LOOP_WORDS, RULES, Facts, Found, find
from clank.components.gateway.server import LOOPED
from tests.support.flowlines import SESSION, lines, page, status, step, text, tool, user

BEGUN = 1_760_900_000_000  # ms, OpenCode's clock
LIMITS = Facts(context=262_144, output=16_384, thinking=4096)
APART = 10_000


def at(ms: int) -> str:
    """A time as the gateway writes it in a request's record."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def flow_of(messages: list[dict[str, Any]], *events: dict[str, Any], requests: Sequence[dict[str, Any]] = ()) -> Flow:
    """A flow read from these messages, then told these events and the gateway's requests."""
    flow = Flow(SESSION, workspace="paper")
    flow.history(page(messages))
    for line in lines(list(events)):
        flow.heard(line)
    if requests:
        flow.requests(list(requests))
    return flow


def request(id: str, began: int, **more: Any) -> dict[str, Any]:
    return {"id": id, "time": at(began), "calls": [], "session": SESSION, **more}


def said(n: int = 0) -> dict[str, Any]:
    return user(f"msg_u{n}", BEGUN + n, "Plot tau against p.")


def steps_with(calls: list[dict[str, Any]], *, per_step: int = 1) -> list[dict[str, Any]]:
    """The owner's message, then steps of `per_step` calls each, finished, one after another."""
    made = [said()]
    for index in range(0, len(calls), per_step):
        n = index // per_step + 1
        created = BEGUN + n * APART
        made.append(step(f"msg_{n:02}", "msg_u0", created, calls[index : index + per_step], completed=created + 5000))
    return made


def ask(id: str, call: str, permission: str, message: str = "msg_01") -> dict[str, Any]:
    properties = {"id": id, "sessionID": SESSION, "permission": permission, "patterns": ["*"],
                  "tool": {"messageID": message, "callID": call}}  # fmt: skip
    return {"type": "permission.asked", "properties": properties}


def bash(id: str, command: str, *, exit: int = 0, status: str = "completed") -> dict[str, Any]:
    return tool(
        id, "bash", status, input={"command": command}, metadata={"exit": exit} if status == "completed" else {}
    )


def edit(id: str, file: str) -> dict[str, Any]:
    return tool(id, "edit", input={"filePath": file, "oldString": f"a{id}", "newString": f"b{id}"}, title=file)


def with_tokens(made: dict[str, Any], total: int) -> dict[str, Any]:
    made["info"]["tokens"] = {"total": total, "input": total - 500, "output": 500, "reasoning": 0,
                              "cache": {"read": 0, "write": 0}}  # fmt: skip
    return made


def waiting_for_you() -> tuple[Flow, Facts]:
    working = step("msg_01", "msg_u0", BEGUN + APART, [
        tool("c1", "bash", "running", call="call_9", input={"command": "rm -r runs"}, title="rm -r runs"),
        tool("c2", "question", "running", call="call_10", input={"questions": [{"question": "Which axis?"}]}),
    ])  # fmt: skip
    return flow_of([said(), working], status("busy"), ask("per_1", "call_9", "bash")), LIMITS


def engine_broke_off() -> tuple[Flow, Facts]:
    words = "the engine broke off its answer after answering part of it (the connection closed); ask again"
    broken = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "Reading")], completed=BEGUN + APART + 4000,
                  error={"name": "APIError", "data": {"message": words}})  # fmt: skip
    found = [request("r-1", BEGUN + APART + 300, broken="the engine broke off its answer: the connection closed")]
    return flow_of([said(), broken], requests=found), LIMITS


def loop_guard_stopped() -> tuple[Flow, Facts]:
    words = f"{LOOPED}: the thinking repeated itself. Ask again; to let such an answer through, set loop_guard to false"
    looped = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "again and again", "reasoning")],
                  completed=BEGUN + APART + 4000, error={"name": "APIError", "data": {"message": words}})  # fmt: skip
    tripped = "the thinking repeated itself (its newest 2,000 characters compress to 4.1% of their size)"
    found = [request("r-1", BEGUN + APART + 300, error=words, looped=tripped)]
    return flow_of([said(), looped], requests=found), LIMITS


def asks_about_a_repeat() -> tuple[Flow, Facts]:
    working = step("msg_01", "msg_u0", BEGUN + APART, [tool("c1", "read", "running", call="call_9", title="a.py")])
    return flow_of([said(), working], status("busy"), ask("per_1", "call_9", "doom_loop")), LIMITS


def same_call_again() -> tuple[Flow, Facts]:
    calls = [bash("c1", "pytest -q"), bash("c2", "ls"), bash("c3", "pytest -q"), bash("c4", "pytest -q")]
    return flow_of(steps_with(calls)), LIMITS


def failing_again() -> tuple[Flow, Facts]:
    calls = [bash("c1", "a", exit=1), bash("c2", "b"), tool("c3", "read", "error", error="no such file"),
             bash("c4", "c", exit=2), bash("c5", "d"), bash("c6", "e", exit=1)]  # fmt: skip
    return flow_of(steps_with(calls)), LIMITS


def one_file_again() -> tuple[Flow, Facts]:
    calls = [edit(f"c{n}", "src/plot.py") for n in range(1, 7)]
    return flow_of(steps_with(calls)), LIMITS


def call_then_step_failed() -> tuple[Flow, Facts]:
    failed = step("msg_01", "msg_u0", BEGUN + APART, [edit("c1", "src/plot.py")], completed=BEGUN + APART + 4000,
                  error={"name": "APIError", "data": {"message": "the engine broke off"}})  # fmt: skip
    return flow_of([said(), failed]), LIMITS


def stopped_with_an_ask_waiting() -> tuple[Flow, Facts]:
    aborted = {"name": "MessageAbortedError", "data": {"message": "Aborted"}}
    waiting = tool("c1", "bash", "running", call="call_9", input={"command": "rm -r runs"})
    stopped = step("msg_01", "msg_u0", BEGUN + APART, [waiting], completed=BEGUN + APART + 4000, error=aborted)
    return flow_of([said(), stopped], ask("per_1", "call_9", "bash"), status("idle")), LIMITS


def note_not_read() -> tuple[Flow, Facts]:
    answered = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "Done.")], completed=BEGUN + APART + 5000)
    note = user("msg_n1", BEGUN + APART + 2000, "Use a log scale.")
    return flow_of([said(), answered, note]), LIMITS


def retrying() -> tuple[Flow, Facts]:
    working = step("msg_01", "msg_u0", BEGUN + APART, [])
    return flow_of([said(), working], status("retry", attempt=2, message="Rate limited", next=1)), LIMITS


def compaction_near() -> tuple[Flow, Facts]:
    made = [said()]
    for n, total in enumerate((200_000, 220_000, 240_000), start=1):
        created = BEGUN + n * APART
        made.append(with_tokens(step(f"msg_{n:02}", "msg_u0", created, [], completed=created + 5000), total))
    return flow_of(made), LIMITS


def budget_near() -> tuple[Flow, Facts]:
    working = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "thinking", "reasoning")])
    counts = {"thinking": 3700, "answer": 0, "tool": 0}
    found = [request("r-1", BEGUN + APART + 300, counts=counts, tokens=3700, phase="answering")]
    return flow_of([said(), working], status("busy"), requests=found), LIMITS


def engine_taken() -> tuple[Flow, Facts]:
    working = step("msg_01", "msg_u0", BEGUN + APART, [])
    return flow_of([said(), working], status("busy")), Facts(context=262_144, output=16_384, holds="ses_other")


CASES: dict[str, tuple[Callable[[], tuple[Flow, Facts]], str, list[str]]] = {
    "waiting_for_you": (waiting_for_you, "c1", ["bash", "approval", "rm -r runs"]),
    "engine_broke_off": (engine_broke_off, "msg_01", ["step 1", "the connection closed"]),
    "loop_guard_stopped": (loop_guard_stopped, "msg_01", ["step 1", "the thinking repeated itself", "not in"]),
    "asks_about_a_repeat": (asks_about_a_repeat, "c1", ["read", "again"]),
    "same_call_again": (same_call_again, "c4", ["bash", "pytest -q", "3 times in the last 12"]),
    "failing_again": (failing_again, "c6", ["4 of the last 8", "bash", "read"]),
    "one_file_again": (one_file_again, "c6", ["src/plot.py", "6 times in the last 30"]),
    "call_then_step_failed": (call_then_step_failed, "msg_01", ["step 1", "edit", "the engine broke off"]),
    "stopped_with_an_ask_waiting": (stopped_with_an_ask_waiting, "c1", ["bash", "stays"]),
    "note_not_read": (note_not_read, "msg_n1", ["Use a log scale.", "without reading it"]),
    "retrying": (retrying, "msg_01", ["attempt 2", "Rate limited"]),
    "compaction_near": (compaction_near, "msg_03", ["240,000", "245,760", "20,000"]),
    "budget_near": (budget_near, "msg_01", ["3,700", "4,096", "thinking"]),
    "engine_taken": (engine_taken, "msg_01", ["ses_other", "again"]),
}


def found_by(rule: str, flow: Flow, facts: Facts) -> list[Found]:
    return [each for each in find(flow.view(), facts) if each.rule == rule]


def test_the_cases_cover_every_rule_and_the_loop_guards_words_are_the_gateways() -> None:
    assert list(CASES) == list(RULES)
    assert LOOP_WORDS == LOOPED


@pytest.mark.parametrize("rule", list(CASES))
def test_each_rule_fires_on_its_synthetic_flow_and_says_why(rule: str) -> None:
    make, node, words = CASES[rule]
    flow, facts = make()
    found = found_by(rule, flow, facts)
    assert found, f"{rule} did not fire"
    first = found[0]
    assert first.node == node
    assert first.key, "a key, stable across evaluations"
    for word in words:
        assert word in first.why, f"{rule}'s mark says why: {first.why!r} lacks {word!r}"
    assert RULES[rule].title
    assert RULES[rule].fires
    assert find(flow.view(), facts) == find(make()[0].view(), facts), "the same flow, the same marks"


def test_the_question_tool_waiting_is_a_mark_of_its_own_and_doom_loop_is_left_to_its_rule() -> None:
    flow, facts = waiting_for_you()
    assert [(each.node, each.key) for each in found_by("waiting_for_you", flow, facts)] == [
        ("c1", "ask:per_1"), ("c2", "question:c2")
    ]  # fmt: skip
    flow, facts = asks_about_a_repeat()
    assert found_by("waiting_for_you", flow, facts) == []
    assert found_by("note_not_read", *note_not_read())[0].offer == "send again"


def test_every_rule_stays_quiet_on_a_clean_flow() -> None:
    made = [said()]
    calls = [bash("c1", "ls"), tool("c2", "read", title="data/tau.csv"), edit("c3", "src/plot.py"),
             bash("c4", "pytest -q"), tool("c5", "read", title="src/plot.py")]  # fmt: skip
    for n, call in enumerate(calls, start=1):
        created = BEGUN + n * APART
        made.append(with_tokens(step(f"msg_{n:02}", "msg_u0", created, [call], completed=created + 5000), 9000 + n))
    found = [request(f"r-{n}", BEGUN + n * APART + 300, counts={"thinking": 300, "answer": 40, "tool": 20},
                     tokens=360, error="", looped="", broken="") for n in range(1, 6)]  # fmt: skip
    flow = flow_of(made, status("idle"), requests=found)
    assert all(node["request"] for node in flow.view()["nodes"] if node["kind"] == "step"), "every step paired"
    assert find(flow.view(), Facts(context=262_144, output=16_384, thinking=4096, holds=SESSION)) == []


def test_a_streak_is_marked_where_it_reached_its_count_and_again_only_after_it_ended() -> None:
    calls = [bash(f"c{n}", "pytest -q") for n in range(1, 6)]  # five in a row: one streak
    calls += [bash(f"o{n}", f"ls {n}") for n in range(1, 13)]  # twelve others: it ended
    calls += [bash(f"d{n}", "pytest -q") for n in range(1, 4)]  # three again: a streak of its own
    flow = flow_of(steps_with(calls, per_step=2))
    assert [each.node for each in found_by("same_call_again", flow, LIMITS)] == ["c3", "d3"]
    assert len({each.key for each in found_by("same_call_again", flow, LIMITS)}) == 2


def test_a_rule_whose_fact_is_not_known_stays_quiet() -> None:
    unknown = Facts()
    assert found_by("compaction_near", compaction_near()[0], unknown) == []
    assert found_by("budget_near", budget_near()[0], unknown) == []
    assert found_by("budget_near", budget_near()[0], Facts(context=262_144, output=16_384, thinking=-1)) == []
    assert found_by("engine_taken", engine_taken()[0], LIMITS) == [], "whose conversation the engine holds: unknown"


def test_an_answer_within_a_tenth_of_the_output_limit_is_marked_naming_the_limit() -> None:
    def answering(tokens: int) -> Flow:
        working = step("msg_01", "msg_u0", BEGUN + APART, [text("p1", "the answer")])
        counts = {"thinking": 0, "answer": tokens, "tool": 0}
        found = [request("r-1", BEGUN + APART + 300, counts=counts, tokens=tokens, phase="answering")]
        return flow_of([said(), working], status("busy"), requests=found)

    [near] = found_by("budget_near", answering(14_800), LIMITS)
    assert (near.node, near.key) == ("msg_01", "answer:r-1")
    for word in ("14,800", "the output limit", "16,384", "within a tenth"):
        assert word in near.why, f"{near.why!r} lacks {word!r}"
    assert found_by("budget_near", answering(14_700), LIMITS) == [], "below nine tenths of 16,384: quiet"
