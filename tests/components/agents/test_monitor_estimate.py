"""Design 0012 §4.2, §4.3, §4.6 and §11 step 12 (decisions 0051, 0052 and 0067): the context's parts, estimated in
the service from the gateway's census of the last finished step: for a synthetic request with known parts, the parts'
tokens add up to the engine's own `prompt_tokens` exactly, each part's share its characters' (weighted by the model's
calibration, each part's tokens per character, when it has one); earlier thinking is left out by the template's rule
(Qwen's reference template drops it before the last user message) and kept by a template that keeps it, and a model
whose template has no thinking has no thinking part; tool results map to their call ids and so to the steps that made
them, a result OpenCode cleared is marked, and so are the items inside the tail a compaction keeps; where the room went
and what could be freed; and the context totals carry the parts of the last finished step and of each step before.
The requests and sessions are synthetic."""

from typing import Any

from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.context import totals
from clank.components.agents.estimate import estimate
from clank.components.agents.sessionflow.flow import Flow
from clank.components.gateway.census import census
from tests.components.agents.test_monitor_context import SESSION, doing, ended, facts_of, route
from tests.components.gateway.test_census import body, call, prose
from tests.support import flowlines

KVMEM = facts_of("daily-262k")


def counted(*messages: dict[str, Any], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The gateway's census of a request of these messages."""
    return census(body(*messages, tools=tools), 0.06, 2000)


def facts(template: dict[str, Any] | None = None, calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    """daily 262K's facts, its model's template or calibration changed."""
    assert KVMEM is not None
    model = {**KVMEM["model"]}
    if template is not None:
        model["template"] = {**model["template"], **template}
    if calibration is not None:
        model["calibration"] = calibration
    return {**KVMEM, "model": model}


def part(found: dict[str, Any], name: str) -> dict[str, Any]:
    return next(each for each in found["parts"] if each["part"] == name)


def study() -> dict[str, Any]:
    return counted(
        {"role": "system", "content": prose(12_000, 1)},
        {"role": "user", "content": "Plan a new simulation study."},
        {"role": "assistant", "content": prose(800, 2), "reasoning_content": prose(2_400, 3),
         "tool_calls": [call("call_c03", "read", {"filePath": "/workspace/src/simulator.py"})]},
        {"role": "tool", "tool_call_id": "call_c03", "content": prose(18_600, 4)},
        tools=[{"type": "function", "function": {"name": "bash", "description": prose(9_000, 5)}}],
    )  # fmt: skip


def test_for_a_synthetic_request_with_known_parts_the_shares_add_up_to_prompt_tokens() -> None:
    found_census = study()
    chars = found_census["chars"]
    total = sum(chars.values())
    for prompt in (1, 7, 999, 12_345, 152_661, 262_144):
        found = estimate(found_census, prompt, KVMEM)
        assert found is not None
        assert sum(each["tokens"] for each in found["parts"]) == prompt, prompt
        for each in found["parts"]:
            assert abs(each["tokens"] - chars[each["part"]] * prompt / total) < 1, (prompt, each["part"])
    found = estimate(found_census, 152_661, KVMEM)
    assert found is not None
    assert [each["part"] for each in found["parts"]] == list(chars), "every part, in the census's order"
    assert part(found, "results")["share"] == part(found, "results")["tokens"] / 152_661
    assert found["calibrated"] is False
    assert found["how"] == (
        "each part's characters, shared out so the parts add up to the engine's own count of 152,661 tokens; "
        "Qwen3.8-27B is not calibrated, so every part counts alike by its characters"
    )
    assert estimate(found_census, 0, KVMEM) is None, "no count to share out"
    assert estimate(None, 1000, KVMEM) is None


def test_earlier_thinking_is_left_out_by_the_templates_rule_and_kept_by_another() -> None:
    found_census = counted(
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": "Planned.", "reasoning_content": prose(7_000, 1)},
        {"role": "user", "content": "Keep the grid to 3 sizes."},
        {"role": "assistant", "content": "", "reasoning_content": prose(1_000, 2),
         "tool_calls": [call("call_c20", "bash", {"command": "ls studies/"})]},
        {"role": "tool", "tool_call_id": "call_c20", "content": prose(500, 3)},
    )  # fmt: skip
    dropped = estimate(found_census, 10_000, KVMEM)
    assert dropped is not None
    assert dropped["thinking"] == "dropped"
    assert part(dropped, "thinking")["items"] == 1
    total = sum(found_census["chars"].values())
    assert abs(part(dropped, "thinking")["tokens"] - 1_000 * 10_000 / total) < 1, "the earlier 7,000 left out"
    assert not [item for item in dropped["items"] if item["earlier"]], "not in the context: not among its items"
    kept = estimate(found_census, 10_000, facts(template={"earlier_thinking": "kept"}))
    assert kept is not None
    assert (kept["thinking"], part(kept, "thinking")["items"]) == ("kept", 2)
    assert abs(part(kept, "thinking")["tokens"] - 8_000 * 10_000 / (total + 7_000)) < 1
    assert [item["chars"] for item in kept["items"] if item["earlier"]] == [7_000]


def test_a_model_whose_template_has_no_thinking_has_no_thinking_part() -> None:
    found = estimate(study(), 50_000, facts(template={"earlier_thinking": "none", "reasoning": []}))
    assert found is not None
    assert "thinking" not in [each["part"] for each in found["parts"]]
    assert sum(each["tokens"] for each in found["parts"]) == 50_000


def test_a_calibrated_model_weighs_each_part_by_its_tokens_per_character() -> None:
    found_census = counted(
        {"role": "system", "content": prose(4_000, 1)},
        {"role": "user", "content": "Go."},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c01", "read", {"filePath": "/a"})]},
        {"role": "tool", "tool_call_id": "call_c01", "content": prose(4_000, 2)},
    )
    measured = {"tokens_per_character": {"system": 0.25, "results": 0.5}, "measured": "2026-10-20, synthetic"}
    found = estimate(found_census, 30_000, facts(calibration=measured))
    assert found is not None
    assert found["calibrated"] is True
    assert abs(part(found, "results")["tokens"] / part(found, "system")["tokens"] - 2) < 0.01
    assert "calibrated (2026-10-20, synthetic)" in found["how"]


def board() -> dict[str, Any]:
    """A session's flow: a read whose result OpenCode cleared, a bash call, then an answer with no call."""
    cleared = flowlines.tool("c03", "read", input={"filePath": "/workspace/src/simulator.py"}, output="r" * 9_000)
    cleared["state"]["time"]["compacted"] = 5
    flow = Flow(SESSION)
    flow.history(flowlines.page([
        flowlines.user("msg_01", 1_000, "Plan the study."),
        flowlines.step("msg_02", "msg_01", 2_000, [cleared], completed=3_000),
        flowlines.step("msg_03", "msg_01", 4_000, [flowlines.tool("c04", "bash", input={"command": "ls"})],
                       completed=5_000),
        flowlines.step("msg_04", "msg_01", 6_000, [flowlines.text("t04", "The plan: three sizes.")],
                       completed=7_000),
    ]))  # fmt: skip
    view = flow.view()
    assert next(node for node in view["nodes"] if node.get("call") == "call_c03")["cleared"] is True
    return view


def test_tool_results_map_to_their_call_ids_and_their_steps_and_a_cleared_one_is_marked() -> None:
    found_census = counted(
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c03", "read", {"filePath": "/a.py"})]},
        {"role": "tool", "tool_call_id": "call_c03", "content": "[Old tool result content cleared]"},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c04", "bash", {"command": "ls"})]},
        {"role": "tool", "tool_call_id": "call_c04", "content": prose(3_000, 1)},
        {"role": "assistant", "content": "The plan: three sizes."},
    )
    found = estimate(found_census, 5_000, KVMEM, board())
    assert found is not None
    items = {(item["of"], item["call"] or item["what"]): item for item in found["items"]}
    assert (items[("results", "call_c03")]["step"], items[("results", "call_c03")]["cleared"]) == (1, True)
    assert (items[("results", "call_c04")]["step"], items[("results", "call_c04")]["cleared"]) == (2, False)
    assert items[("calls", "call_c04")]["step"] == 2
    assert (items[("results", "call_c03")]["node"], items[("calls", "call_c04")]["node"]) == ("c03", "c04"), (
        "the call's part in the flow, which the Guide's Drop names"
    )
    assert items[("text", "the model's text: The plan: three sizes.")]["step"] == 3, "the step after, with no call"
    assert items[("yours", "your message: Plan the study.")]["step"] == 1, "the step that read it"
    unknown = estimate(found_census, 5_000, KVMEM)
    assert unknown is not None
    assert {item["step"] for item in unknown["items"]} == {None}, "no flow: no step claimed"


def test_items_in_the_tail_a_compaction_keeps_are_marked() -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Read them all."}]
    for index in range(20):
        id = f"call_t{index}"
        messages += [{"role": "assistant", "content": "", "tool_calls": [call(id, "read", {"filePath": f"/{index}"})]},
                     {"role": "tool", "tool_call_id": id, "content": prose(4_000, index)}]  # fmt: skip
    found_census = counted(*messages)
    prompt = sum(found_census["chars"].values())  # a token a character
    found = estimate(found_census, prompt, KVMEM, keeps=15_000)
    assert found is not None
    kept = sorted(item["call"] for item in found["items"] if item["kept"] and item["part"] == "results")
    assert kept == ["call_t17", "call_t18", "call_t19"], "the last 15,000 tokens hold the last three results whole"


def test_where_the_room_went_and_what_could_be_freed() -> None:
    notes = {"filePath": "/workspace/studies/notes.md"}
    found_census = counted(
        {"role": "system", "content": prose(6_000, 1)},
        {"role": "user", "content": "Read the notes again and go on."},
        {"role": "assistant", "content": "", "reasoning_content": "0.0 " * 1_500,
         "tool_calls": [call("call_c05", "read", notes)]},
        {"role": "tool", "tool_call_id": "call_c05", "content": prose(4_000, 2)},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c18", "read", notes)]},
        {"role": "tool", "tool_call_id": "call_c18", "content": prose(14_000, 3)},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c20", "bash", {"command": "ls studies/"})]},
        {"role": "tool", "tool_call_id": "call_c20", "content": prose(500, 4)},
        tools=[{"type": "function", "function": {"name": "bash", "description": prose(3_000, 5)}}],
    )  # fmt: skip
    prompt = sum(found_census["chars"].values())
    found = estimate(found_census, prompt, KVMEM, keeps=15_000)
    assert found is not None
    room = [(each["words"], each["tokens"]) for each in found["groups"]]
    assert room[0] == ("read: 2 results", 18_000)
    assert ("loop text: 1 item", 6_000) in room
    assert ("bash: 1 result", 500) in room
    assert room[1][0] == "the system prompt and tool definitions, every step"
    freed = {each["what"]: each for each in found["freed"]}
    assert "loop" not in freed, "a thinking that looped is no call's result: no Drop clears it"
    assert (freed["loop_kept"]["tokens"], freed["loop_kept"]["items"], freed["loop_kept"]["how"]) == (
        6_000,
        1,
        "compact",
    )
    assert (freed["again"]["tokens"], freed["again"]["items"]) == (4_000, 1)
    assert freed["compact"]["tokens"] == prompt - 15_000
    assert [each["what"] for each in found["freed"]] == ["again", "loop_kept", "compact"]


def test_the_totals_carry_the_parts_of_the_last_finished_step_and_of_each_step_before() -> None:
    first = study()
    slim = {key: value for key, value in first.items() if key != "items"}
    looped = ended("r-3", 0, 0, looped="its thinking repeated itself", census=first)
    activity = doing(ended("r-1", 100_000, 2_000, census=slim), ended("r-2", 150_000, 2_661, census=first), looped)
    found = totals(SESSION, activity, route("daily-262k"), facts_of, OpenCode().compaction)
    assert found["parts"] is not None
    assert sum(each["tokens"] for each in found["parts"]["parts"]) == 150_000, "the last finished step's prompt"
    assert [step["request"] for step in found["steps"]] == ["r-1", "r-2"], "each step whose prompt is known"
    assert sum(found["steps"][0]["parts"].values()) == 100_000
    bare = totals(SESSION, doing(ended("r-1", 100_000, 2_000)), route("daily-262k"), facts_of, OpenCode().compaction)
    assert (bare["parts"], bare["steps"]) == (None, []), "a step the gateway made no census of"


def test_a_result_the_guide_cleared_says_by_you_and_what_it_freed_and_is_left_out_of_what_could_be_freed() -> None:
    notes = {"filePath": "/workspace/studies/notes.md"}
    first = flowlines.tool("c05", "read", input=notes, output="n" * 4_000)
    first["state"]["time"]["compacted"] = 5
    flow = Flow(SESSION)
    flow.history(flowlines.page([
        flowlines.user("msg_01", 1_000, "Read the notes again."),
        flowlines.step("msg_02", "msg_01", 2_000, [first], completed=3_000),
        flowlines.step("msg_03", "msg_01", 4_000, [flowlines.tool("c18", "read", input=notes, output="m" * 9_000)],
                       completed=5_000),
    ]))  # fmt: skip
    flow.cleared("c05", 1_212)
    found_census = counted(
        {"role": "user", "content": "Read the notes again."},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c05", "read", notes)]},
        {"role": "tool", "tool_call_id": "call_c05", "content": "[Old tool result content cleared]"},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c18", "read", notes)]},
        {"role": "tool", "tool_call_id": "call_c18", "content": prose(9_000, 1)},
    )
    assert found_census["again"][1] == 1, "the census counts it: it knows nothing of the flow"
    found = estimate(found_census, 3_000, KVMEM, flow.view(), keeps=15_000)
    assert found is not None
    cleared = next(item for item in found["items"] if item["call"] == "call_c05" and item["of"] == "results")
    assert (cleared["cleared"], cleared["cleared_by"], cleared["freed"]) == (True, "you", 1_212)
    assert "again" not in [each["what"] for each in found["freed"]], "nothing left to free there"


def test_two_answers_without_calls_in_a_row_each_get_their_own_step_never_the_one_before() -> None:
    flow = Flow(SESSION)
    flow.history(flowlines.page([
        flowlines.user("msg_01", 1_000, "Plan the study."),
        flowlines.step("msg_02", "msg_01", 2_000, [flowlines.tool("c01", "read", input={"filePath": "/a.md"})],
                       completed=3_000),
        flowlines.step("msg_03", "msg_01", 4_000, [flowlines.text("t03", "The plan: three sizes.")], completed=5_000),
        flowlines.user("msg_04", 6_000, "Why three?"),
        flowlines.step("msg_05", "msg_04", 7_000, [flowlines.text("t05", "Time: each doubles the cost.")],
                       completed=8_000),
    ]))  # fmt: skip
    found_census = counted(
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c01", "read", {"filePath": "/a.md"})]},
        {"role": "tool", "tool_call_id": "call_c01", "content": "a"},
        {"role": "assistant", "content": "The plan: three sizes."},
        {"role": "user", "content": "Why three?"},
        {"role": "assistant", "content": "Time: each doubles the cost."},
    )
    found = estimate(found_census, 2_000, KVMEM, flow.view())
    assert found is not None
    steps = {item["what"]: item["step"] for item in found["items"]}
    assert steps["the model's text: The plan: three sizes."] == 2
    assert steps["the model's text: Time: each doubles the cost."] == 3, "its own step, not the one before"
    assert steps["your message: Why three?"] == 3, "the step that read it, though it made no call"


def test_could_be_freed_offers_drop_only_for_results_and_the_rest_of_the_loop_text_to_compacting() -> None:
    tags = "</f>\n</invoke>\n</functions>\n" * 120
    found_census = counted(
        {"role": "user", "content": "Go on."},
        {"role": "assistant", "content": "", "reasoning_content": "0.0 " * 1_500,
         "tool_calls": [{"id": "call_c19", "type": "function", "function": {"name": "bash", "arguments": tags}}]},
        {"role": "tool", "tool_call_id": "call_c19", "content": "Invalid input: " + tags},
    )  # fmt: skip
    prompt = sum(found_census["chars"].values())
    found = estimate(found_census, prompt, KVMEM, keeps=1_000)
    assert found is not None
    freed = {each["what"]: each for each in found["freed"]}
    echo = len("Invalid input: " + tags)
    assert (freed["loop"]["tokens"], freed["loop"]["items"], freed["loop"]["how"]) == (echo, 1, "drop"), (
        "only the result Drop can clear"
    )
    kept = freed["loop_kept"]
    assert (kept["tokens"], kept["items"], kept["how"]) == (6_000 + len("bash") + len(tags), 2, "compact")
    assert kept["words"] == "the loop text the model wrote, which only compacting clears"
    assert [each["what"] for each in found["freed"]] == ["loop", "loop_kept", "compact"]
