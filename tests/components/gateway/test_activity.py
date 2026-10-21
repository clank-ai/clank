"""Design 0004 §2: the gateway says what it does now: each request in flight with its phase (waiting for its slot,
reading the prompt, answering), its time, its tokens (counted by kind: design 0012 §5.2) and its speed; and how the last
request that ended went: its tokens, its time and its speed (the engine's own figures when it gives them), or why it was
refused. A request the gateway answers itself (OpenCode's titles) is not shown, and one whose answer never started
streaming is forgotten. Design 0012 §5.4: a request in flight shows its loop guard's newest share of each part against
its ratio, and the last says what repeated when the guard stopped it. Design 0012 §5.1 and §5.3: a request in flight
says its time to the first token, the kind of text it wrote last, and the call being written, its name and its
arguments' newest characters. Design 0012 §3 and §7: the activity and the live
text of one session give its own requests and its own last, its subagents' too only when they are asked for, never
another session's; each of the newest sessions keeps its last request and its text after another session's ended, and
a session's subagents never push its own last out. Design 0012 §6.1: a session's requests that ended, with the ids of
the calls each answer made, are given when asked for, so the service pairs them with the session's steps. Design
0012 §8: a request whose engine broke off its answer says so once it ended, for the Watch for rule that marks it.
Design 0012 §4: that same word keeps it from being taken for a finished step; each slot's newest request is the one
that reached its engine (never one the gateway refused), and it is marked gone once its engine stopped, started again
or was switched, so the Monitor never says an engine holds a conversation it lost. Design 0012 §9.1: a request that
ended keeps its time to the first token, the measure of the engine's reading speed that the Guide's costs are read
at. Design 0012 §9.4: a held request a note released, answered by the gateway itself, is never counted nor its
session's last, and stays among its session's requests that ended, so its step's flow shows the hold. Design 0012
§4.2: a request's census is kept only among its session's requests that ended, whole from the newest that ended well
on, its parts' numbers alone before it."""

from typing import Any

from clank.components.gateway.activity import ENDED_KEPT, SESSIONS_KEPT, WRITING, Activity
from clank.components.gateway.loops import LoopGuard
from clank.components.gateway.routing import Routes

TIME = "2026-10-14T05:00:00.000000Z"


def asked(id: str, **fields: Any) -> dict[str, Any]:
    """A request's record as the gateway starts it."""
    return {"id": id, "time": TIME, "client": "172.18.0.2", "role": "agent", **fields}


def test_a_request_in_flight_shows_its_phase_its_time_its_tokens_and_its_speed() -> None:
    clock = [101.0]
    activity = Activity(lambda: clock[0])
    record = asked("r-1")
    activity.begin(record, 100.0)
    assert activity.now()["requests"] == [
        {"id": "r-1", "time": TIME, "role": "agent", "slot": "", "session": "", "parent": "",
         "phase": "waiting for its slot", "seconds": 1.0, "tokens": 0,
         "counts": {"thinking": 0, "answer": 0, "tool": 0}, "per_second": None, "loop_guard": None, "calls": [],
         "held": None, "first_ms": None, "newest": "", "writing": None}
    ]  # fmt: skip
    record["slot"] = "main"
    clock[0] = 103.0
    assert activity.now()["requests"][0]["phase"] == "reading the prompt"
    record["first_token_ms"] = 3000.0
    for _ in range(41):
        activity.token(record, "answer")
    clock[0] = 104.0
    shown = activity.now()["requests"][0]
    assert (shown["phase"], shown["seconds"], shown["tokens"], shown["per_second"]) == ("answering", 4.0, 41, 40.0)


def test_a_request_in_flight_says_its_time_to_the_first_token_what_it_writes_now_and_the_call_being_written() -> None:
    activity = Activity(lambda: 2.0)
    record = asked("r-1", slot="main")
    activity.begin(record, 0.0)
    shown = activity.now()["requests"][0]
    assert (shown["first_ms"], shown["newest"], shown["writing"]) == (None, "", None), "nothing written yet"
    record["first_token_ms"] = 1250.0
    activity.heard(record, "thinking", "Let me run the tests.")
    shown = activity.now()["requests"][0]
    assert (shown["first_ms"], shown["newest"], shown["writing"]) == (1250.0, "thinking", None)
    activity.heard(record, "tool", "\n→ bash ")
    activity.heard(record, "tool", '{"command": "python -m pytest -q tests/')
    shown = activity.now()["requests"][0]
    assert shown["newest"] == "tool"
    assert shown["writing"] == {"tool": "bash", "arguments": '{"command": "python -m pytest -q tests/'}
    activity.heard(record, "tool", "x" * (WRITING + 50))
    assert activity.now()["requests"][0]["writing"]["arguments"] == "x" * WRITING, "its newest characters"
    activity.heard(record, "tool", '"}\n→ read {"filePath": "src/a.py"')
    assert activity.now()["requests"][0]["writing"] == {"tool": "read", "arguments": '{"filePath": "src/a.py"'}, (
        "the call written last"
    )
    activity.heard(record, "answer", "Done.")
    shown = activity.now()["requests"][0]
    assert (shown["newest"], shown["writing"]) == ("answer", None)
    assert activity.live()["meta"]["newest"] == "answer", "the live view's numbers say it too"


def test_the_last_request_keeps_its_tokens_its_time_and_its_speed_and_the_engines_own_figures_win() -> None:
    activity = Activity(lambda: 0.0)
    record = asked("r-1", slot="main", status=200, first_token_ms=1000.0, total_ms=5000.0)
    activity.begin(record, 0.0)
    for _ in range(101):
        activity.token(record, "answer")
    activity.end(record)
    now = activity.now()
    assert (now["requests"], now["served"]) == ([], 1)
    assert now["last"] == {
        "id": "r-1", "time": TIME, "role": "agent", "slot": "main", "session": "", "parent": "", "status": 200,
        "seconds": 5.0, "tokens": 101, "counts": {"thinking": 0, "answer": 101, "tool": 0}, "per_second": 25.0,
        "prompt_tokens": None, "first_ms": 1000.0, "error": "", "looped": "", "broken": "", "full": "", "left": False,
        "calls": [],
        "preset": None, "usage": None, "timings": None, "held": None,
    }  # fmt: skip
    timed = asked("r-2", slot="main", status=200, first_token_ms=900.0, total_ms=3000.0)
    timed["timings"] = {"predicted_n": 120, "predicted_per_second": 61.234, "prompt_n": 9120}
    activity.begin(timed, 0.0)
    activity.end(timed)
    last = activity.now()["last"]
    assert (last["id"], last["tokens"], last["per_second"], last["prompt_tokens"]) == ("r-2", 120, 61.2, 9120)
    assert activity.now()["served"] == 2


def test_the_tokens_of_a_request_in_flight_are_counted_by_kind_and_add_up() -> None:
    activity = Activity(lambda: 1.0)
    record = asked("r-1", slot="main", first_token_ms=100.0)
    activity.begin(record, 0.0)
    for kind in ("thinking", "thinking", "thinking", "answer", "answer", "tool"):
        activity.token(record, kind)
    [flying] = activity.now()["requests"]
    assert (flying["counts"], flying["tokens"]) == ({"thinking": 3, "answer": 2, "tool": 1}, 6)
    record.update(status=200, total_ms=1000.0, usage={"completion_tokens": 9})
    activity.end(record)
    last = activity.now()["last"]
    assert last["counts"] == {"thinking": 3, "answer": 2, "tool": 1}, "as counted while it streamed"
    assert last["tokens"] == 9, "the engine's own count wins once it ended"


def test_a_request_in_flight_shows_its_loop_guards_shares_against_its_ratio() -> None:
    activity = Activity(lambda: 1.0)
    record = asked("r-1", slot="main", first_token_ms=100.0)
    activity.begin(record, 0.0)
    assert activity.now()["requests"][0]["loop_guard"] is None, "no guard reads it: off, or its answer is not streamed"
    guard = LoopGuard()
    activity.guard(record, guard)
    assert activity.now()["requests"][0]["loop_guard"] == {"ratio": 0.06, "parts": []}
    guard.feed("answer", "</f>\n</invoke>\n</functions>\n" * 100)
    [part] = activity.now()["requests"][0]["loop_guard"]["parts"]
    assert (part["part"], part["stretch"]) == ("answer", 2000)
    assert part["share"] < 0.06
    record.update(status=200, total_ms=1000.0, looped=guard.tripped)
    activity.end(record)
    assert activity.now()["last"]["looped"] == guard.tripped


def test_a_refused_request_is_the_last_with_its_reason() -> None:
    activity = Activity(lambda: 0.0)
    refused = asked("r-1", status=503, error={"code": "no_engine", "message": "no engine runs"}, total_ms=2.0)
    activity.begin(refused, 0.0)
    activity.end(refused)
    last = activity.now()["last"]
    assert (last["status"], last["error"], last["tokens"], last["per_second"]) == (503, "no engine runs", 0, None)


def test_a_request_whose_engine_broke_off_says_so_once_it_ended() -> None:
    activity = Activity(lambda: 0.0)
    broken = asked("r-1", slot="main", status=200, total_ms=900.0,
                   broken="the engine broke off its answer: the connection closed")  # fmt: skip
    activity.begin(broken, 0.0)
    activity.token(broken, "answer")
    activity.end(broken)
    last = activity.now()["last"]
    assert (last["broken"], last["error"]) == ("the engine broke off its answer: the connection closed", "")
    whole = asked("r-2", slot="main", status=200, total_ms=900.0)
    activity.begin(whole, 0.0)
    activity.token(whole, "answer")
    activity.end(whole)
    assert activity.now()["last"]["broken"] == "", "an answer that ended whole"


def test_a_request_that_ended_keeps_its_time_to_the_first_token() -> None:
    activity = Activity(lambda: 0.0)
    read = asked("r-1", slot="main", status=200, total_ms=9000.0, first_token_ms=2500.0)
    activity.begin(read, 0.0)
    activity.token(read, "answer")
    activity.end(read)
    assert activity.now()["last"]["first_ms"] == 2500.0, "the measure of the engine's reading speed"
    refused = asked("r-2", slot="main", status=502, total_ms=10.0, error="the engine did not answer")
    activity.begin(refused, 0.0)
    activity.token(refused, "answer")
    activity.end(refused)
    assert activity.now()["last"]["first_ms"] is None, "no token came"


def test_a_title_answered_here_is_not_shown_and_a_stream_that_never_started_is_forgotten() -> None:
    activity = Activity(lambda: 0.0)
    title = asked("r-1")
    activity.begin(title, 0.0)
    title.update(local="title", status=200)
    assert activity.now()["requests"] == []
    activity.end(title)
    never = asked("r-2", slot="main")
    activity.begin(never, 0.0)
    activity.drop(never)
    assert activity.now() == {"requests": [], "served": 0, "last": None, "slots": {}}


def test_the_live_view_gives_a_requests_thinking_answer_and_tool_calls_from_an_offset_and_keeps_the_last() -> None:
    clock = [101.0]
    activity = Activity(lambda: clock[0])
    record = asked("r-1", slot="main", request={"messages": [{"role": "user", "content": "plot  tau\nvs p"}]})
    activity.begin(record, 100.0)
    for kind, text in (("thinking", "Let me "), ("thinking", "look."), ("answer", "Done"), ("tool", "\n→ bash "),
                       ("tool", '{"cmd": "ls"}')):  # fmt: skip
        activity.heard(record, kind, text)
    whole = activity.live()
    assert (whole["id"], whole["flying"], whole["asked"]) == ("r-1", True, "plot tau vs p")
    assert whole["parts"] == [["thinking", "Let me look."], ["answer", "Done"], ["tool", '\n→ bash {"cmd": "ls"}']]
    assert whole["length"] == len("Let me look.Done") + len('\n→ bash {"cmd": "ls"}')
    assert activity.live(after=9)["parts"] == [
        ["thinking", "ok."],
        ["answer", "Done"],
        ["tool", '\n→ bash {"cmd": "ls"}'],
    ]
    assert activity.live(after=whole["length"])["parts"] == [], "nothing new"
    record.update(status=200, total_ms=2000.0)
    activity.end(record)
    after = activity.live()
    assert (after["id"], after["flying"], after["parts"][1]) == ("r-1", False, ["answer", "Done"]), "the last is kept"


NOTHING = {"id": "", "flying": False, "meta": None, "asked": "", "length": 0, "parts": [], "newest": ""}


def of(session: str, parent: str = "") -> dict[str, str]:
    """The headers OpenCode sends for a session's request (and a subagent's parent)."""
    return {"x-session-id": session, **({"x-parent-session-id": parent} if parent else {})}


def ended(activity: Activity, n: int, session: str, parent: str = "", **fields: Any) -> dict[str, Any]:
    """Request `r-<n>` of a session (of none when ""), begun, heard and ended; its record."""
    headers = of(session, parent) if session else {}
    record = asked(f"r-{n}", slot="main", headers=headers, status=200, total_ms=100.0, **fields)
    activity.begin(record, float(n))
    activity.heard(record, "answer", f"{session or 'no session'} said")
    activity.end(record)
    return record


def test_the_live_text_of_one_session_follows_its_own_requests_its_subagents_when_asked_and_never_anothers() -> None:
    activity = Activity(lambda: 10.0)
    root = asked("r-1", slot="main", headers=of("ses_a"))
    other = asked("r-2", slot="main", headers=of("ses_b"))
    child = asked("r-3", slot="main", headers=of("ses_c", "ses_a"))
    activity.begin(root, 1.0)
    activity.heard(root, "answer", "the root's")
    activity.begin(other, 2.0)
    activity.heard(other, "answer", "another's")
    assert activity.live()["id"] == "r-2", "without a session: the newest of all"
    shown = activity.live(session="ses_a")
    assert (shown["id"], shown["newest"], shown["parts"]) == ("r-1", "r-1", [["answer", "the root's"]])
    assert (shown["meta"]["session"], shown["meta"]["parent"]) == ("ses_a", "")
    named = activity.live(session="ses_a", id="r-2")
    assert (named["id"], named["parts"]) == ("r-1", [["answer", "the root's"]]), "never another session's text"
    activity.begin(child, 3.0)
    activity.heard(child, "thinking", "the subagent's")
    shown = activity.live(session="ses_a")
    assert (shown["id"], shown["newest"]) == ("r-1", "r-1"), "its own requests, unless its subagents are asked for"
    shown = activity.live(session="ses_a", subagents=True)
    assert (shown["id"], shown["newest"]) == ("r-3", "r-3")
    assert (shown["meta"]["session"], shown["meta"]["parent"]) == ("ses_c", "ses_a")
    named = activity.live(session="ses_a", id="r-1", subagents=True)
    assert named["parts"] == [["answer", "the root's"]], "one it names"
    assert activity.live(session="ses_c")["id"] == "r-3"
    assert activity.live(session="ses_b")["id"] == "r-2"
    assert activity.live(session="ses_z") == NOTHING


def test_each_of_the_newest_sessions_keeps_its_last_request_after_another_session_ends_one() -> None:
    activity = Activity(lambda: 10.0)
    ended(activity, 1, "ses_a")
    ended(activity, 2, "ses_b")
    ended(activity, 3, "")
    shown = activity.live(session="ses_a")
    assert (shown["id"], shown["flying"], shown["parts"]) == ("r-1", False, [["answer", "ses_a said"]])
    assert activity.live()["id"] == "r-3", "the gateway's last is the newest, whichever session sent it"
    ended(activity, 4, "ses_a")
    assert activity.live(session="ses_a")["id"] == "r-4", "a session's newest last"
    for n in range(5, 5 + SESSIONS_KEPT - 1):
        ended(activity, n, f"ses_{n}")
    assert activity.live(session="ses_b") == NOTHING, "the oldest session's last is no longer kept"
    assert activity.live(session="ses_a")["id"] == "r-4"


def test_a_sessions_subagents_never_push_its_own_last_out() -> None:
    activity = Activity(lambda: 10.0)
    ended(activity, 1, "ses_a")
    newest = 2 + SESSIONS_KEPT
    for n in range(2, newest + 1):  # more subagents than the sessions kept, each ended after it
        ended(activity, n, f"ses_sub{n}", "ses_a")
    assert activity.now("ses_a")["last"]["id"] == "r-1"
    assert activity.now("ses_a", subagents=True)["last"]["id"] == f"r-{newest}"
    assert activity.now("ses_sub2")["last"] is None, "the oldest subagent's last is no longer kept"
    assert activity.now(f"ses_sub{newest}")["last"]["id"] == f"r-{newest}"


def test_the_activity_of_one_session_gives_its_own_requests_and_its_own_last_and_its_subagents_when_asked() -> None:
    activity = Activity(lambda: 10.0)
    ended(activity, 1, "ses_a", usage={"prompt_tokens": 30000})
    ended(activity, 2, "ses_b")
    child = asked("r-3", slot="main", headers=of("ses_c", "ses_a"))
    activity.begin(child, 3.0)
    activity.begin(asked("r-4", slot="main", headers=of("ses_b")), 4.0)
    mine = activity.now("ses_a")
    assert mine["requests"] == [], "its subagent's request only when they are asked for"
    assert (mine["last"]["id"], mine["served"]) == ("r-1", 2), "its own last; the gateway's count"
    mine = activity.now("ses_a", subagents=True)
    assert [request["id"] for request in mine["requests"]] == ["r-3"], "its subagent's, not another session's"
    assert mine["last"]["id"] == "r-1"
    assert activity.now()["last"]["id"] == "r-2"
    assert [request["id"] for request in activity.now()["requests"]] == ["r-3", "r-4"]
    other = activity.now("ses_z")
    assert (other["requests"], other["served"], other["last"]) == ([], 2, None)
    assert other["slots"] == activity.now()["slots"], "the slots are the engines', whatever the session"
    child.update(status=200, total_ms=100.0, usage={"prompt_tokens": 900})
    activity.heard(child, "answer", "the subagent's")
    activity.end(child)  # its subagent ends after it
    own = activity.now("ses_a")["last"]
    assert (own["id"], own["session"], own["prompt_tokens"]) == ("r-1", "ses_a", 30000), "still its own last"
    assert activity.live(session="ses_a")["parts"] == [["answer", "ses_a said"]]
    assert activity.now("ses_a", subagents=True)["last"]["id"] == "r-3", "a subagent's, found through its parent"
    assert activity.live(session="ses_a", subagents=True)["parts"] == [["answer", "the subagent's"]]


def test_a_sessions_requests_that_ended_are_given_when_asked_oldest_first_and_bounded() -> None:
    """Design 0012 §6.1 (§11 step 5): the service pairs a session's steps with its requests, so the activity gives a
    session's own requests that ended, numbers only, when asked for them."""
    activity = Activity(lambda: 10.0)
    ended(activity, 1, "ses_a", calls=["call_1", "call_2"])
    ended(activity, 2, "ses_b")
    ended(activity, 3, "ses_c", "ses_a")
    ended(activity, 4, "ses_a")
    assert "ended" not in activity.now("ses_a"), "only when asked for"
    shown = activity.now("ses_a", ended=True)["ended"]
    assert [each["id"] for each in shown] == ["r-1", "r-4"], "its own, oldest first: not another's, not a subagent's"
    assert (shown[0]["calls"], shown[0]["time"], shown[1]["calls"]) == (["call_1", "call_2"], TIME, [])
    assert [each["id"] for each in activity.now("ses_c", ended=True)["ended"]] == ["r-3"]
    assert activity.now("ses_z", ended=True)["ended"] == []
    for n in range(5, 5 + ENDED_KEPT):
        ended(activity, n, "ses_a")
    kept = [each["id"] for each in activity.now("ses_a", ended=True)["ended"]]
    assert (len(kept), kept[-1]) == (ENDED_KEPT, f"r-{4 + ENDED_KEPT}"), "the newest kept"
    for n in range(100, 100 + SESSIONS_KEPT):
        ended(activity, n, f"ses_{n}")
    assert activity.now("ses_a", ended=True)["ended"] == [], "a session no longer kept keeps none"


def test_a_request_that_ended_keeps_its_preset_and_the_engines_own_usage_and_timings() -> None:
    activity = Activity(lambda: 0.0)
    usage = {"prompt_tokens": 40000, "completion_tokens": 120, "prompt_cache_hit_tokens": 39000}
    timings = {"prompt_n": 1000, "cache_n": 39000, "predicted_n": 120}
    record = asked("r-1", slot="main", preset="daily-262k", status=200, total_ms=1000.0, usage=usage,
                   timings=timings, headers={"x-session-id": "ses_a"})  # fmt: skip
    activity.begin(record, 0.0)
    activity.end(record)
    last = activity.now()["last"]
    assert (last["preset"], last["usage"], last["timings"]) == ("daily-262k", usage, timings), "as the engine gave them"
    [ended] = activity.now("ses_a", ended=True)["ended"]
    assert (ended["preset"], ended["usage"], ended["timings"]) == ("daily-262k", usage, timings)
    bare = asked("r-2", slot="main", status=200, total_ms=10.0)
    activity.begin(bare, 0.0)
    activity.end(bare)
    last = activity.now()["last"]
    assert (last["preset"], last["usage"], last["timings"]) == (None, None, None), "none given: none kept"


def test_each_slots_newest_request_is_its_oldest_in_flight_else_its_last_that_ended() -> None:
    activity = Activity(lambda: 5.0)
    assert activity.now()["slots"] == {}
    first = asked("r-1", slot="main", headers={"x-session-id": "ses_a"}, status=200, total_ms=10.0)
    activity.begin(first, 0.0)
    activity.end(first)
    held = {"id": "r-1", "session": "ses_a", "parent": "", "time": TIME, "flying": False, "gone": False}
    assert activity.now()["slots"] == {"main": held}
    waiting = asked("r-2", headers={"x-session-id": "ses_b"})
    activity.begin(waiting, 1.0)
    assert activity.now()["slots"]["main"]["id"] == "r-1", "waiting for its slot: it has not reached the engine"
    waiting["slot"] = "main"
    reading = {"id": "r-2", "session": "ses_b", "parent": "", "time": TIME, "flying": True, "gone": False}
    assert activity.now()["slots"]["main"] == reading, "the engine reads it"
    sub = asked("r-3", slot="main", headers={"x-session-id": "ses_c", "x-parent-session-id": "ses_a"})
    activity.begin(sub, 2.0)
    assert activity.now()["slots"]["main"]["id"] == "r-2", "the engine reads one at a time: the oldest in flight"
    fast = asked("r-4", slot="fast", status=200, total_ms=5.0)
    activity.begin(fast, 3.0)
    activity.end(fast)
    assert activity.now()["slots"]["fast"] == {"id": "r-4", "session": "", "parent": "", "time": TIME, "flying": False,
                                               "gone": False}  # fmt: skip
    waiting.update(status=200, total_ms=10.0)
    activity.end(waiting)
    assert activity.now()["slots"]["main"]["id"] == "r-3", "the next in flight"
    sub.update(status=200, total_ms=10.0)
    activity.end(sub)
    assert activity.now()["slots"]["main"] == {**held, "id": "r-3", "session": "ses_c", "parent": "ses_a"}
    title = asked("r-5", slot="main", local="title", status=200)
    activity.begin(title, 4.0)
    activity.end(title)
    assert activity.now()["slots"]["main"]["id"] == "r-3", "a title the gateway answered itself never reached it"
    for code in ("engine_unreachable", "engine_broke_off"):
        refused = asked(f"r-{code}", slot="main", headers={"x-session-id": "ses_d"}, status=502,
                        error={"code": code, "message": "the engine did not answer"}, total_ms=10.0)  # fmt: skip
        activity.begin(refused, 5.0)
        activity.end(refused)
        assert activity.now()["slots"]["main"]["id"] == "r-3", f"refused after it was routed ({code}): not the engine's"


def test_two_requests_in_flight_that_began_at_the_same_moment_are_both_shown() -> None:
    activity = Activity(lambda: 10.0)
    activity.begin(asked("r-1", slot="main", headers={"x-session-id": "ses_a"}), 5.0)
    activity.begin(asked("r-2", slot="main", headers={"x-session-id": "ses_b"}), 5.0)
    shown = activity.now()
    assert [request["id"] for request in shown["requests"]] == ["r-1", "r-2"]
    assert shown["slots"]["main"]["id"] == "r-1", "the first that came"


def test_a_sessions_requests_that_ended_say_which_one_its_engine_broke_off() -> None:
    activity = Activity(lambda: 0.0)
    record = asked("r-1", slot="main", status=200, total_ms=10.0, headers={"x-session-id": "ses_a"},
                   broken="the engine broke off its answer: its stream stopped without its end")  # fmt: skip
    activity.begin(record, 0.0)
    activity.end(record)
    [ended] = activity.now("ses_a", ended=True)["ended"]
    assert (ended["status"], ended["broken"]) == (
        200,
        "the engine broke off its answer: its stream stopped without its end",
    )


def test_a_slots_newest_request_is_marked_gone_once_its_engine_stopped_started_again_or_was_switched() -> None:
    def table(status: str = "ready", preset: str = "daily-262k", port: int | None = 18300, busy: bool = False) -> Any:
        slot = {"status": status, "busy": busy, "port": port if status == "ready" else None, "preset": preset}
        return {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main"}

    routes = Routes()
    routes.update(table())
    activity = Activity(lambda: 0.0, routes.generation)

    def answered(id: str) -> None:
        record = asked(id, slot="main", headers={"x-session-id": "ses_a"}, status=200, total_ms=10.0)
        activity.begin(record, 0.0)
        activity.end(record)

    def gone() -> bool:
        return bool(activity.now()["slots"]["main"]["gone"])

    answered("r-1")
    routes.update(table(busy=True))
    routes.update(table())
    assert not gone(), "an operation queued for the slot changed nothing yet"
    routes.update(table("starting"))
    assert gone(), "its engine stopped (it crashed, and the runtime starts it again)"
    routes.update(table())
    assert gone(), "started again: it holds no conversation"
    answered("r-2")
    assert not gone()
    routes.update(table(preset="frontier-96k"))
    assert gone(), "switched to another preset"
    answered("r-3")
    routes.update(table(port=18301))
    assert gone(), "another engine serves it"
    flying = asked("r-4", slot="main", headers={"x-session-id": "ses_a"})
    activity.begin(flying, 1.0)
    reading = {"id": "r-4", "session": "ses_a", "parent": "", "time": TIME, "flying": True, "gone": False}
    assert activity.now()["slots"]["main"] == reading, "in flight: its engine reads it now"


def test_a_request_a_note_released_stays_among_its_sessions_ended_but_is_never_counted_nor_its_last() -> None:
    """Design 0012 §9.4 (§11 step 11): a hold a note closed is answered by the gateway itself, an empty step, never
    counted; it stays among its session's requests that ended, so its step's flow still shows the hold."""
    activity = Activity(lambda: 10.0)
    ended(activity, 1, "ses_a")
    held = {
        "session": "ses_a",
        "by": "you (console)",
        "since": TIME,
        "until": TIME,
        "how": "released",
        "seconds": 180.0,
    }
    record = asked("r-2", headers=of("ses_a"))
    activity.begin(record, 2.0)
    record.update(local="released", status=200, answer="", held=held, total_ms=180_000.0)
    activity.end(record)
    shown = activity.now("ses_a", ended=True)
    assert [(each["id"], each["held"]) for each in shown["ended"]] == [("r-1", None), ("r-2", held)]
    assert (shown["served"], shown["last"]["id"]) == (1, "r-1"), "never counted, never the session's last"
    assert activity.now()["last"]["id"] == "r-1"
    record = asked("r-3", headers=of("ses_alone"))
    activity.begin(record, 3.0)
    record.update(local="released", status=200, answer="", held=held, total_ms=1.0)
    activity.end(record)
    assert [each["id"] for each in activity.now("ses_alone", ended=True)["ended"]] == ["r-3"]
    for n in range(100, 100 + 2 * SESSIONS_KEPT):
        record = asked(f"r-{n}", headers=of(f"ses_{n}"))
        activity.begin(record, float(n))
        record.update(local="released", status=200, answer="", held=held, total_ms=1.0)
        activity.end(record)
    assert activity.now("ses_alone", ended=True)["ended"] == [], "sessions with only such requests are bounded too"
    assert activity.now("ses_a", ended=True)["ended"][0]["id"] == "r-1", "a session kept keeps its own"


def test_a_sessions_requests_that_ended_keep_their_census_whole_only_from_the_newest_that_ended_well() -> None:
    activity = Activity(lambda: 1.0)

    def ends(id: str, **fields: Any) -> None:
        record = asked(id, slot="main", headers=of("ses_a"), status=200, total_ms=10.0, **fields)
        activity.begin(record, 0.0)
        found = {"chars": {"results": 100}, "counts": {"results": 1},
                 "items": [{"part": "results", "chars": 100, "call": f"call_{id}"}]}  # fmt: skip
        activity.census(record, found)
        assert "census" not in activity.now("ses_a")["requests"][0], "never in a request in flight"
        activity.end(record)

    ends("r-1")
    ends("r-2", looped="its text repeated itself", error="Clank's loop guard stopped the answer")
    shown = activity.now("ses_a", ended=True)
    assert [each["census"]["items"][0]["call"] for each in shown["ended"]] == ["call_r-1", "call_r-2"]
    assert "census" not in shown["last"], "only among a session's requests that ended"
    ends("r-3")
    shown = activity.now("ses_a", ended=True)
    assert [("items" in each["census"]) for each in shown["ended"]] == [False, False, True], (
        "whole from the newest that ended well on"
    )
    assert shown["ended"][0]["census"] == {"chars": {"results": 100}, "counts": {"results": 1}}, "the older: numbers"
    record = asked("r-4", slot="main", headers=of("ses_a"), status=200, total_ms=10.0)
    activity.begin(record, 0.0)
    activity.end(record)
    assert activity.now("ses_a", ended=True)["ended"][-1]["census"] is None, "a request with none says so"
