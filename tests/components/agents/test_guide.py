"""Design 0012 §9.1, §9.2, §9.3 and §9.6 (§11 step 9): what the Guide offers for the session the Monitor follows, a
pure function of its flow, the server that runs it, its context totals and the gateway's figures of its requests.

Each action (Stop now, a note, Compact now) says its key, whether it can run now and, when not, why; what it does, in
words and as the exact call to OpenCode; what it costs, the tokens read again (estimates until measured) and the time
that takes at the engine's reading speed measured from the gateway's records, or that the time is not known; whether it
asks first (all but Stop); and the state of its last run, read from the flow: a stop stopping, then stopped once the
session is idle; a note written, waiting, read by step n, answered, or not read; a compaction asked, compacting, done.
"""

from typing import Any

from clank.components.agents.guide import READ_LEAST, offer, reading_speed
from clank.components.agents.sessionflow.flow import Flow
from tests.support.flowlines import SESSION, compacting, lines, page, status, step, text, tool, updated, user

BEGUN = 1_760_900_000_000  # ms, OpenCode's clock
KVMEM = {"prompt": "usage.prompt_tokens", "output": "usage.completion_tokens",
         "cached": "usage.prompt_cache_hit_tokens"}  # fmt: skip
TOTALS = {"used": 21_000, "keeps": 15_000, "facts": {"engine": {"fields": KVMEM}}}


def ended(prompt: int, cached: int, first_ms: float | None, **more: Any) -> dict[str, Any]:
    """A request of the session that ended well, as the gateway's activity gives it."""
    usage = {"prompt_tokens": prompt, "completion_tokens": 1_000, "prompt_cache_hit_tokens": cached}
    return {"id": f"r-{prompt}", "status": 200, "error": "", "looped": "", "broken": "", "left": False,
            "usage": usage, "timings": None, "first_ms": first_ms, "prompt_tokens": prompt, **more}  # fmt: skip


ENDED = [ended(12_000, 11_000, 900.0), ended(20_000, 16_000, 2_000.0)]  # the newest read 4,000 anew in 2 s


def request(id: str, began: int, prompt: int) -> dict[str, Any]:
    from datetime import UTC, datetime

    at = datetime.fromtimestamp(began / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return {"id": id, "time": at, "calls": [], "seconds": 3.0, "per_second": 40.0, "prompt_tokens": prompt,
            "looped": "", "left": False}  # fmt: skip


def working(state: str = "busy") -> Flow:
    """A planner session: the owner's message, three steps, the owner's second message, two steps; each step paired
    with its request's prompt."""
    flow = Flow(SESSION, workspace="paper")
    made = [user("msg_00", BEGUN, "Plot tau.", agent="planner")]
    prompts = {1: 9_000, 2: 12_000, 3: 15_000, 5: 16_000, 6: 20_000}
    for n in (1, 2, 3):
        made.append(step(f"msg_0{n}", "msg_00", BEGUN + n * 10_000, [text(f"p{n}", "Working.")],
                         completed=BEGUN + n * 10_000 + 5_000))  # fmt: skip
    made.append(user("msg_04", BEGUN + 40_000, "Use the log scale.", agent="planner"))
    for n in (5, 6):
        made.append(step(f"msg_0{n}", "msg_04", BEGUN + n * 10_000, [text(f"p{n}", "Working.")],
                         completed=BEGUN + n * 10_000 + 5_000))  # fmt: skip
    flow.history(page(made))
    flow.requests([request(f"r-{n}", BEGUN + n * 10_000 + 300, prompt) for n, prompt in prompts.items()])
    hear(flow, [status(state)])
    return flow


def hear(flow: Flow, events: list[dict[str, Any]]) -> None:
    for line in lines(events):
        flow.heard(line)


def offered(flow: Flow, **given: Any) -> dict[str, dict[str, Any]]:
    chosen: dict[str, Any] = {"port": 4096, "totals": TOTALS, "ended": ENDED, "kept": {}, **given}
    return {each["action"]: each for each in offer(flow.view(), **chosen)}


def test_each_action_says_its_key_what_it_does_its_exact_call_and_its_cost() -> None:
    found = offered(working())
    listed = [(".", "Stop now"), ("m", "Note"), ("k", "Compact now"), ("u", "Undo turn"), ("x", "Drop")]
    assert [(each["key"], each["title"]) for each in found.values()] == listed, (
        "Undo and Drop follow (step 10): each step's text is its last part, so the last goes back to your message"
    )
    stop, note, compact = found["stop"], found["note"], found["compact"]
    assert (stop["can"], stop["why"], stop["confirm"]) == (True, "", False), "Stop must be quick: never asked first"
    assert stop["calls"][0] == "POST /session/ses_plan/abort"
    assert "reject" in stop["calls"][1]
    assert stop["cost"] == {"tokens": 0, "seconds": 0.0, "words": "nothing read again"}
    assert (note["can"], note["confirm"]) == (True, True)
    assert note["calls"] == [
        'POST /session/ses_plan/prompt_async {"agent": "planner", "model": {"providerID": "clank", "modelID": '
        '"agent"}, "parts": [{"type": "text", "text": "<your note>"}]}'
    ]
    assert "planner" in note["does"]
    assert "next step" in note["does"]
    assert (note["cost"]["tokens"], note["cost"]["seconds"]) == (5_000, 2.5), "21,000 used less step 5's 16,000"
    assert "estimate" in note["cost"]["words"]
    assert "to measure" in note["cost"]["words"]
    assert compact["calls"] == [
        'POST /session/ses_plan/summarize {"providerID": "clank", "modelID": "agent", "auto": true}'
    ]
    assert "15,000" in compact["does"]
    assert (compact["cost"]["tokens"], compact["cost"]["seconds"], compact["confirm"]) == (21_000, 10.5, True)


def test_an_action_that_cannot_run_says_why() -> None:
    idle = offered(working("idle"))
    assert (idle["stop"]["can"], idle["note"]["can"], idle["compact"]["can"]) == (False, True, True)
    assert idle["stop"]["why"] == "the session is idle and nothing waits in it: there is nothing to stop"
    assert "starts a run" in idle["note"]["does"]
    nowhere = offered(working(), port=None)
    assert not any(each["can"] for each in nowhere.values())
    assert all("no OpenCode server" in each["why"] for each in nowhere.values())
    asked = offered(working(), kept={"compact": {"state": "asked", "bands": 0, "time": "", "by": "you"}})
    assert asked["compact"]["can"] is False
    assert asked["compact"]["why"] == "a compaction is asked already: OpenCode makes it at the session's next step"
    flow = working("idle")
    rm = tool("c1", "bash", "running", call="call_9", input={"command": "rm -r runs"})
    hear(flow, [*updated(step("msg_07", "msg_04", BEGUN + 70_000, [rm]))])
    ask = {"id": "per_1", "sessionID": SESSION, "permission": "bash", "patterns": ["rm -r runs"],
           "tool": {"messageID": "msg_07", "callID": "call_9"}}  # fmt: skip
    hear(flow, [{"type": "permission.asked", "properties": ask}])
    waiting = offered(flow)
    assert waiting["stop"]["can"] is True, "an ask waits: Stop rejects it"
    assert waiting["stop"]["calls"][1] == 'POST /permission/per_1/reply {"reply": "reject"}'
    assert "reject" in waiting["note"]["does"]
    assert "no message is added" in waiting["note"]["does"]
    assert waiting["note"]["calls"] == ['POST /permission/per_1/reply {"reply": "reject", "message": "<your note>"}']


def test_the_reading_speed_comes_from_the_gateways_records_else_the_time_is_not_known() -> None:
    assert reading_speed(ENDED, KVMEM) == (2_000.0, 4_000), "the newest step that read enough anew"
    timed = [ended(20_000, 0, 9_000.0, timings={"prompt_per_second": 812.5, "prompt_n": 4_000})]
    assert reading_speed(timed, {**KVMEM, "timings": "timings"}) == (812.5, 4_000), "the engine's own figure first"
    small = [ended(20_000, 20_000 - READ_LEAST + 1, 100.0)]
    assert reading_speed(small, KVMEM) is None, "too few tokens read anew to measure by"
    silent = {key: path for key, path in KVMEM.items() if key != "cached"}
    assert reading_speed(ENDED, silent) is None, "what was read anew is not known when the cache is not reported"
    unknown = offered(working(), ended=[])
    assert unknown["compact"]["cost"]["seconds"] is None
    assert "time not known" in unknown["compact"]["cost"]["words"]


def test_each_actions_state_is_read_from_the_flow() -> None:
    flow = working()
    kept = {"state": "stopping", "time": "2026-10-20T04:00:00Z", "by": "you, from the console"}
    assert offered(flow, kept={"stop": kept})["stop"]["state"]["state"] == "stopping"
    hear(flow, [status("idle")])
    assert offered(flow, kept={"stop": kept})["stop"]["state"]["state"] == "stopped"
    flow = working()
    said = "About step 6: use a log scale."
    note = {"state": "written", "text": said, "time": "", "by": "you"}
    assert offered(flow, kept={"note": note})["note"]["state"]["state"] == "written"
    hear(flow, [*updated(user("msg_07", BEGUN + 62_000, said, agent="planner"))])
    assert offered(flow, kept={"note": note})["note"]["state"]["state"] == "waiting"
    hear(flow, [*updated(step("msg_08", "msg_04", BEGUN + 70_000, [text("p8", "Log scale it is.")]))])
    read = offered(flow, kept={"note": note})["note"]["state"]
    assert (read["state"], read["step"]) == ("read", 6)
    hear(flow, [*updated(step("msg_08", "msg_04", BEGUN + 70_000, [text("p8", "Log scale it is.")],
                              completed=BEGUN + 75_000)), status("idle")])  # fmt: skip
    assert offered(flow, kept={"note": note})["note"]["state"]["state"] == "answered"
    late = working()
    hear(late, [status("idle"), *updated(user("msg_07", BEGUN + 62_000, said, agent="planner"))])
    assert offered(late, kept={"note": note})["note"]["state"]["state"] == "not read"
    flow = working()
    asked = {"state": "asked", "bands": 0, "time": "", "by": "you"}
    assert offered(flow, kept={"compact": asked})["compact"]["state"]["state"] == "asked"
    hear(flow, [*updated(compacting("msg_07", "msg_06", BEGUN + 70_000))])
    assert offered(flow, kept={"compact": asked})["compact"]["state"]["state"] == "compacting"
    hear(flow, [{"type": "session.compacted", "properties": {"sessionID": SESSION}}])
    assert offered(flow, kept={"compact": asked})["compact"]["state"]["state"] == "done"
    failed = {"state": "failed", "why": "the bridge refused", "time": "", "by": "you"}
    shown = offered(flow, kept={"stop": failed})["stop"]["state"]
    assert (shown["state"], shown["why"]) == ("failed", "the bridge refused")
