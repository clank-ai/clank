"""Design 0012 §6.1 and §11 step 5 (decision 0049): a session's steps are joined to the gateway's requests by session,
and pair with them in order, one model call at a time. An answer's call ids, equal to OpenCode's, confirm a pairing
and win over time; without them a request pairs in order by time, another request for the same step is a try of it,
the last its answer; steps whose requests the gateway no longer keeps, and steps from before Clank watched, stay
unpaired; the clocks of the container and of this machine may differ by a second or so. Design 0012 §8: a step's
request carries its tokens by kind and whether its engine broke off, which the Watch for rules read. Design 0012 §9.4
(§11 step 11): and the hold the gateway kept of it, while its session was paused; a request a note released pairs
only with an empty step of its own, never in place of the answer of the step before it.
"""

from datetime import UTC, datetime
from typing import Any

from clank.components.agents.sessionflow.flow import Flow
from clank.components.agents.sessionflow.pairing import pair
from tests.support.flowlines import SESSION, page, step, tool, user

BEGUN = 1_760_900_000_000  # ms, OpenCode's clock


def at(ms: int) -> str:
    """A time as the gateway writes it in a request's record."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def steps(count: int, *, apart: int = 10_000, calls: bool = False) -> list[dict[str, Any]]:
    return [{"id": f"msg_{n}", "created": BEGUN + n * apart, "calls": [f"call_{n}"] if calls else []}
            for n in range(1, count + 1)]  # fmt: skip


def request(id: str, began: int, calls: list[str] | None = None, **more: Any) -> dict[str, Any]:
    return {"id": id, "time": at(began), "calls": calls or [], **more}


def answers(paired: dict[str, Any]) -> dict[str, str]:
    return {step: found.request for step, found in paired.items()}


def test_n_requests_pair_with_n_steps_in_order() -> None:
    made = steps(5)
    requests = [request(f"r-{n}", BEGUN + n * 10_000 + 300) for n in range(1, 6)]
    paired = pair(made, list(reversed(requests)))
    assert answers(paired) == {f"msg_{n}": f"r-{n}" for n in range(1, 6)}
    assert all(not found.confirmed and not found.tries for found in paired.values())
    assert "by time" in paired["msg_1"].why
    flow = Flow(SESSION)  # the same, through a flow: each step carries its request's numbers
    flow.history(page([user("msg_0", BEGUN, "Plot tau."),
                       *[step(each["id"], "msg_0", each["created"], [], completed=each["created"] + 5_000)
                         for each in made]]))  # fmt: skip
    flow.requests([{**each, "seconds": 4.2, "per_second": 61.0, "prompt_tokens": 9120, "looped": "", "left": False}
                   for each in requests])  # fmt: skip
    shown = {node["id"]: node["request"] for node in flow.view()["nodes"] if node["kind"] == "step"}
    assert [shown[f"msg_{n}"]["id"] for n in range(1, 6)] == [f"r-{n}" for n in range(1, 6)]
    assert (shown["msg_1"]["seconds"], shown["msg_1"]["per_second"], shown["msg_1"]["prompt_tokens"]) == (
        4.2, 61.0, 9120
    )  # fmt: skip


def test_call_ids_confirm_a_pairing_and_win_over_time() -> None:
    made = steps(3, calls=True)
    skewed = 30_000  # far beyond what time alone would allow
    requests = [request(f"r-{n}", BEGUN + n * 10_000 + skewed, [f"call_{n}"]) for n in range(1, 4)]
    paired = pair(made, requests)
    assert answers(paired) == {"msg_1": "r-1", "msg_2": "r-2", "msg_3": "r-3"}
    assert all(found.confirmed for found in paired.values())
    assert "call" in paired["msg_2"].why
    crossed = [request("r-1", BEGUN + 10_300, ["call_2"]), request("r-2", BEGUN + 20_300, ["call_1"])]
    assert answers(pair(steps(2, calls=True), crossed)) == {"msg_1": "r-2", "msg_2": "r-1"}, "ids win over order"


def test_a_request_again_for_one_step_is_a_try_and_the_last_its_answer() -> None:
    made = steps(2)
    requests = [request("r-1", BEGUN + 10_300), request("r-2", BEGUN + 15_000), request("r-3", BEGUN + 20_300)]
    paired = pair(made, requests)
    assert answers(paired) == {"msg_1": "r-2", "msg_2": "r-3"}
    assert (paired["msg_1"].tries, paired["msg_2"].tries) == (["r-1"], [])


def test_steps_whose_requests_the_gateway_no_longer_keeps_stay_unpaired() -> None:
    made = steps(4)
    requests = [request("r-3", BEGUN + 30_300), request("r-4", BEGUN + 40_300)]
    assert answers(pair(made, requests)) == {"msg_3": "r-3", "msg_4": "r-4"}
    assert answers(pair(made, [request("r-0", BEGUN - 50_000)])) == {}, "a request before every step pairs with none"
    flow = Flow(SESSION)  # steps read from the history when Clank first saw the session are never paired
    first = page([
        user("msg_0", BEGUN, "Plot tau."), step("msg_1", "msg_0", BEGUN + 10_000, [], completed=BEGUN + 15_000),
        step("msg_2", "msg_0", BEGUN + 20_000, [tool("c1", "bash", "running")]),
    ])  # fmt: skip
    flow.history(first, joined=True)
    flow.requests([request("r-1", BEGUN + 10_300), request("r-2", BEGUN + 20_300)])
    shown = {node["id"]: node for node in flow.view()["nodes"] if node["kind"] == "step"}
    assert (shown["msg_1"]["before"], shown["msg_1"]["request"]) == (True, None), "finished before Clank watched"
    assert (shown["msg_2"]["before"], shown["msg_2"]["request"]["id"]) == (False, "r-2"), "still under way: watched"
    assert flow.view()["head"]["before"] == 1


def test_a_clock_a_second_apart_still_pairs_in_order() -> None:
    made = steps(4, apart=3_000)  # quick steps, three seconds apart
    behind = [request(f"r-{n}", BEGUN + n * 3_000 - 1_200) for n in range(1, 5)]  # this machine's clock behind
    ahead = [request(f"r-{n}", BEGUN + n * 3_000 + 800) for n in range(1, 5)]  # or ahead
    expected = {f"msg_{n}": f"r-{n}" for n in range(1, 5)}
    assert answers(pair(made, behind)) == expected
    assert answers(pair(made, ahead)) == expected


def test_a_steps_request_carries_its_counts_by_kind_and_whether_its_engine_broke_off() -> None:
    flow = Flow(SESSION)
    flow.history(page([user("msg_0", BEGUN, "Plot tau."),
                       step("msg_1", "msg_0", BEGUN + 10_000, [], completed=BEGUN + 15_000),
                       step("msg_2", "msg_0", BEGUN + 20_000, [])]))  # fmt: skip
    counts = {"thinking": 3700, "answer": 12, "tool": 0}
    flow.requests([
        request("r-1", BEGUN + 10_300, counts={"thinking": 40, "answer": 9, "tool": 0}, tokens=49,
                broken="the engine broke off its answer: the connection closed"),
        request("r-2", BEGUN + 20_300, counts=counts, tokens=3712, phase="answering"),
    ])  # fmt: skip
    shown = {node["id"]: node["request"] for node in flow.view()["nodes"] if node["kind"] == "step"}
    assert shown["msg_1"]["broken"] == "the engine broke off its answer: the connection closed"
    assert (shown["msg_2"]["counts"], shown["msg_2"]["flying"], shown["msg_2"]["broken"]) == (counts, True, None)


def test_a_step_whose_request_the_gateway_held_carries_its_hold() -> None:
    flow = Flow(SESSION)
    flow.history(page([user("msg_0", BEGUN, "Plot tau."),
                       step("msg_1", "msg_0", BEGUN + 10_000, [], completed=BEGUN + 200_000),
                       step("msg_2", "msg_0", BEGUN + 210_000, [])]))  # fmt: skip
    resumed = {"session": SESSION, "by": "you (console)", "since": at(BEGUN + 10_100), "until": at(BEGUN + 190_100),
               "how": "resumed", "seconds": 180.0}  # fmt: skip
    holding = {"session": SESSION, "by": "Clank (watch for)", "since": at(BEGUN + 210_100)}
    flow.requests([
        request("r-1", BEGUN + 10_050, held=resumed),
        request("r-2", BEGUN + 210_050, held=holding, phase="held: its session is paused"),
    ])  # fmt: skip
    shown = {node["id"]: node["request"] for node in flow.view()["nodes"] if node["kind"] == "step"}
    assert (shown["msg_1"]["id"], shown["msg_1"]["held"]) == ("r-1", resumed)
    assert (shown["msg_2"]["held"], shown["msg_2"]["phase"], shown["msg_2"]["flying"]) == (
        holding, "held: its session is paused", True
    )  # fmt: skip


def test_a_request_a_note_released_pairs_with_its_own_empty_step_and_never_takes_the_step_befores_place() -> None:
    released = {"session": SESSION, "by": "you (console)", "since": at(BEGUN + 60_000), "until": at(BEGUN + 63_000),
                "how": "released", "seconds": 3.0}  # fmt: skip
    made = [{"id": "msg_1", "created": BEGUN + 10_000, "calls": ["call_1"]},
            {"id": "msg_2", "created": BEGUN + 200_000, "calls": []}]  # fmt: skip
    requests = [request("r-1", BEGUN + 10_050, ["call_1"]), request("r-2", BEGUN + 60_000, held=released),
                request("r-3", BEGUN + 200_050)]  # fmt: skip
    paired = pair(made, requests)  # OpenCode kept no step of the empty answer
    assert (paired["msg_1"].request, paired["msg_1"].tries) == ("r-1", []), "the step before keeps its answer"
    assert paired["msg_2"].request == "r-3"
    empty = {"id": "msg_e", "created": BEGUN + 59_900, "calls": []}
    paired = pair([made[0], empty, made[1]], requests)  # OpenCode kept the empty step
    assert answers(paired) == {"msg_1": "r-1", "msg_e": "r-2", "msg_2": "r-3"}
