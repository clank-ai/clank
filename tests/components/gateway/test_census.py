"""Design 0012 §4.2, §4.3, §4.6 and §11 step 12 (decisions 0051 and 0052): the census of a model request, made in the
gateway from the body it parsed: each part's characters (the system prompt, the tool definitions, the owner's
messages, the model's text, the thinking sent back, the calls, the results and loop text), the thinking before the last
real user message counted apart, so the template's rule can be applied where the model's facts are read; each item
with its call id (a tool result's `tool_call_id`, OpenCode's call id; a message's own calls' ids), its tool and what it
is; loop text found by the loop guard's measure over whole items (zlib's share under the guard's ratio, an item at least
as long as its shortest stretch), the result that echoes a call that looped, and the third and later identical call in
the last twelve, each taken out of the part it came from; the earlier results of a call made again with the same
arguments, which could be freed; only the biggest items kept, and each part's; and a body of odd shapes counted without
failing. The requests are synthetic."""

import json
import random
import time
from typing import Any

from clank.components.gateway.census import KEPT, PARTS, PER_PART, census

RATIO, SHORTEST = 0.06, 2000  # the loop guard's defaults (config/gateway.json)
SAID = (
    "the grid of sizes runs from sixteen to sixty four and each run keeps its seed while the estimator reads the "
    "energy gap magnetization and its error bars over every sweep of the lattice before the plot is drawn again"
)


def prose(length: int, seed: int = 1) -> str:
    """Ordinary text of `length` characters: words in no order, which compress as prose does, never as a loop."""
    pick, words = random.Random(seed), SAID.split()
    said = ""
    while len(said) < length:
        said += pick.choice(words) + " "
    return said[:length]


def call(id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def tool(name: str, description: str) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": {}}}}  # fmt: skip


def body(*messages: dict[str, Any], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"model": "agent", "stream": True, "messages": list(messages), "tools": tools or []}


def asking(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    """A session's messages after the owner's first."""
    return [{"role": "user", "content": "Go on."}, *messages]


def taken(found: dict[str, Any], **wanted: Any) -> dict[str, Any]:
    """The item kept whose fields are these."""
    return next(item for item in found["items"] if all(item.get(key) == value for key, value in wanted.items()))


def test_a_requests_characters_are_counted_part_by_part() -> None:
    tools = [tool("read", prose(400, 2)), tool("bash", prose(900, 3))]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prose(3000, 4)},
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": prose(500, 5), "reasoning_content": prose(300, 6),
         "tool_calls": [call("call_c01", "read", {"filePath": "/workspace/src/sim.py"})]},
        {"role": "tool", "tool_call_id": "call_c01", "content": prose(5000, 7)},
    ]  # fmt: skip
    found = census(body(*messages, tools=tools), RATIO, SHORTEST)
    definitions = sum(len(json.dumps(each, ensure_ascii=False)) for each in tools)
    arguments = len("read") + len(json.dumps({"filePath": "/workspace/src/sim.py"}))
    assert found["chars"] == {"system": 3000, "tools": definitions, "yours": 15, "text": 500, "thinking": 300,
                              "calls": arguments, "results": 5000, "loop": 0}  # fmt: skip
    assert list(found["chars"]) == list(PARTS)
    assert found["counts"] == {"system": 1, "tools": 2, "yours": 1, "text": 1, "thinking": 1, "calls": 1, "results": 1,
                               "loop": 0}  # fmt: skip
    assert found["messages"] == 4
    assert found["from_last_user"] == 15 + 500 + 300 + arguments + 5000, "from the last user message on"
    assert taken(found, part="tools", tool="bash")["what"] == "the definition of bash"
    assert taken(found, part="yours")["what"] == "your message: Plan the study."
    assert taken(found, part="results")["after"] == 0, "the last item: nothing after it"
    assert taken(found, part="yours")["after"] == 300 + 500 + arguments + 5000


def test_thinking_before_the_last_user_message_is_counted_apart() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": "Done.", "reasoning_content": prose(700, 1)},
        {"role": "user", "content": "Keep the grid to 3 sizes."},
        {"role": "assistant", "content": "", "reasoning": prose(200, 2),
         "tool_calls": [call("call_c02", "bash", {"command": "ls studies/"})]},
        {"role": "tool", "tool_call_id": "call_c02", "content": "notes.md"},
    ]  # fmt: skip
    found = census(body(*messages), RATIO, SHORTEST)
    assert found["chars"]["thinking"] == 200, "only after the last real user message (a tool's is not one)"
    assert (found["earlier"], found["earlier_items"]) == (700, 1)
    assert taken(found, part="thinking", earlier=True)["chars"] == 700
    assert taken(found, part="thinking", earlier=False)["calls"] == ["call_c02"]


def test_a_tool_result_carries_its_call_id_and_its_tool_and_a_message_the_ids_of_its_calls() -> None:
    messages = asking(
        {"role": "assistant", "content": "Reading both.", "tool_calls": [
            call("call_c03", "read", {"filePath": "/workspace/README.md"}),
            call("call_c04", "grep", {"pattern": "def measure_"}),
        ]},
        {"role": "tool", "tool_call_id": "call_c03", "content": prose(2100, 1)},
        {"role": "tool", "tool_call_id": "call_c04", "content": prose(300, 2)},
    )  # fmt: skip
    found = census(body(*messages), RATIO, SHORTEST)
    result = taken(found, part="results", call="call_c03")
    assert (result["tool"], result["what"], result["at"]) == ("read", "the result of read /workspace/README.md", 2)
    assert taken(found, part="calls", call="call_c04")["what"] == "grep def measure_"
    nothing = census(
        body(
            *asking(
                {"role": "assistant", "content": "", "tool_calls": [call("call_c06", "caps", {})]},
                {"role": "tool", "tool_call_id": "call_c06", "content": "x"},
            )
        ),
        RATIO,
        SHORTEST,
    )
    assert taken(nothing, part="results")["what"] == "the result of caps", "a call with nothing to say says its name"
    assert taken(found, part="text")["calls"] == ["call_c03", "call_c04"]
    assert found["tools"] == {"read": [2100, 1], "grep": [300, 1]}


def test_loop_text_is_found_by_the_guards_measure_over_whole_items_and_taken_out_of_its_part() -> None:
    loop = "0.0 " * 1000  # 4,000 characters of the same few
    messages = asking(
        {"role": "assistant", "content": prose(6000, 1), "reasoning_content": loop},
        {"role": "assistant", "content": "0.0 " * 400},  # 1,600: shorter than the guard's shortest stretch
    )
    found = census(body(*messages), RATIO, SHORTEST)
    looped = taken(found, part="loop")
    assert (looped["of"], looped["chars"]) == ("thinking", 4000)
    assert looped["loop"].startswith("it compresses to ")
    assert looped["loop"].endswith("% of its size")
    assert (found["chars"]["loop"], found["chars"]["thinking"]) == (4000, 0), "taken out of the part it came from"
    assert found["chars"]["text"] == 6000 + 1600, "ordinary prose, and a short repeat, are not loop text"


def test_the_result_of_a_call_that_looped_echoes_it_and_is_loop_text_too() -> None:
    tags = "</f>\n</invoke>\n</functions>\n" * 120
    messages = asking(
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_c19", "type": "function", "function": {"name": "bash", "arguments": tags}},
        ]},
        {"role": "tool", "tool_call_id": "call_c19", "content": "Invalid input: " + tags},
    )  # fmt: skip
    found = census(body(*messages), RATIO, SHORTEST)
    assert taken(found, call="call_c19", of="calls")["part"] == "loop"
    echo = taken(found, call="call_c19", of="results")
    assert (echo["part"], echo["loop"]) == ("loop", "the result of a call that repeated itself")
    assert (found["chars"]["results"], found["chars"]["calls"]) == (0, 0)


def test_a_call_made_a_third_time_in_the_last_twelve_is_loop_text_with_its_result() -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Test it."}]
    commands = ["pytest -q", "ls", "pytest -q", "cat setup.cfg", "pytest -q", "pytest -q"]
    for index, command in enumerate(commands):
        id = f"call_r{index}"
        messages += [{"role": "assistant", "content": "", "tool_calls": [call(id, "bash", {"command": command})]},
                     {"role": "tool", "tool_call_id": id, "content": prose(400, index)}]  # fmt: skip
    found = census(body(*messages), RATIO, SHORTEST)
    looped = sorted(item["call"] for item in found["items"] if item["part"] == "loop")
    assert looped == ["call_r4", "call_r4", "call_r5", "call_r5"], "the third and fourth pytest, each call and result"
    assert taken(found, call="call_r4", of="calls")["loop"] == "the same call a third time in the last twelve"
    assert taken(found, call="call_r5", of="results")["loop"] == (
        "the result of a call made a fourth time in the last twelve"
    )
    older: list[dict[str, Any]] = [{"role": "user", "content": "Again."}]
    for index, command in enumerate(["pytest -q", "pytest -q", *[f"ls {n}" for n in range(11)], "pytest -q"]):
        id = f"call_o{index}"
        older += [{"role": "assistant", "content": "", "tool_calls": [call(id, "bash", {"command": command})]},
                  {"role": "tool", "tool_call_id": id, "content": "ok"}]  # fmt: skip
    looping = [item for item in census(body(*older), RATIO, SHORTEST)["items"] if item["part"] == "loop"]
    assert not looping, "the first two are not among the last twelve"


def test_the_earlier_results_of_a_call_made_again_could_be_freed() -> None:
    read = {"filePath": "/workspace/studies/notes.md"}
    messages = asking(
        {"role": "assistant", "content": "", "tool_calls": [call("call_c05", "read", read)]},
        {"role": "tool", "tool_call_id": "call_c05", "content": prose(4000, 1)},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c06", "read", {"filePath": "/x.md"})]},
        {"role": "tool", "tool_call_id": "call_c06", "content": prose(100, 2)},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c18", "read", read)]},
        {"role": "tool", "tool_call_id": "call_c18", "content": prose(14200, 3)},
    )
    found = census(body(*messages), RATIO, SHORTEST)
    assert taken(found, call="call_c05", part="results")["again"] is True
    assert taken(found, call="call_c18", part="results")["again"] is False, "the newest stays"
    assert found["again"] == [4000, 1]


def test_only_the_biggest_items_are_kept_and_each_parts_biggest() -> None:
    messages: list[dict[str, Any]] = [{"role": "system", "content": "s" * 10}, {"role": "user", "content": "Go."}]
    for index in range(100):
        id = f"call_k{index}"
        messages += [{"role": "assistant", "content": "", "tool_calls": [call(id, "read", {"filePath": f"/{index}"})]},
                     {"role": "tool", "tool_call_id": id, "content": "r" * (100 + index)}]  # fmt: skip
    found = census(body(*messages), RATIO, SHORTEST)
    sizes = [item["chars"] for item in found["items"]]
    assert sizes == sorted(sizes, reverse=True), "biggest first"
    assert sizes[0] == 199
    assert sum(1 for item in found["items"] if item["part"] == "results") == KEPT
    assert taken(found, part="system")["chars"] == 10, "each part's biggest kept, however small"
    assert sum(1 for item in found["items"] if item["part"] == "calls") == PER_PART
    assert (found["counts"]["results"], found["chars"]["results"]) == (100, sum(range(100, 200)))
    assert "text" not in found["items"][0], "what an item wrote is never kept"


def test_a_body_of_odd_shapes_is_counted_without_failing() -> None:
    odd = {
        "messages": [
            "not a message",
            {"role": "user", "content": [{"type": "text", "text": "Look at this."},
                                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_x"}, "nothing"]},
            {"role": "tool", "content": 7},
            {"role": "narrator", "content": "unknown"},
        ],
        "tools": "none",
    }  # fmt: skip
    found = census(odd, RATIO, SHORTEST)
    assert found["chars"]["yours"] == len("Look at this.")
    assert found["images"] == 1
    assert census({}, RATIO, SHORTEST)["messages"] == 0


def test_an_item_without_a_call_names_the_calls_around_it() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Plan the study."},
        {"role": "assistant", "content": "", "tool_calls": [call("call_c01", "read", {"filePath": "/a.md"})]},
        {"role": "tool", "tool_call_id": "call_c01", "content": "a"},
        {"role": "assistant", "content": "The plan: three sizes."},
        {"role": "user", "content": "Keep the grid to 3 sizes."},
        {"role": "assistant", "content": "Done."},
    ]
    found = census(body(*messages), RATIO, SHORTEST)
    assert (taken(found, at=0)["next"], taken(found, at=0)["near"]) == ("call_c01", ""), "the step that read it"
    assert taken(found, at=3)["near"] == "call_c01", "the model's text after the step of that call"
    assert taken(found, at=4)["next"] == "", "the step that read it made no call"
    assert taken(found, at=1, part="calls")["near"] == "", "an item with a call of its own needs none"


def test_a_long_chat_of_answers_without_calls_is_counted_in_time_that_grows_with_its_length() -> None:
    messages: list[dict[str, Any]] = []
    for index in range(10_000):
        messages += [{"role": "user", "content": f"Question {index}?"}, {"role": "assistant", "content": "Yes."}]
    began = time.perf_counter()
    found = census(body(*messages), RATIO, SHORTEST)
    took = time.perf_counter() - began
    assert found["counts"]["text"] == 10_000
    assert took < 1.0, f"{took:.2f} s for 10,000 answers: each item looked through every answer"


def test_with_its_words_off_no_item_carries_any_text_of_the_request() -> None:
    secret = ["Plan the merger quietly", "the board must not know", "/workspace/merger/terms.md", "Signed, the CFO",
              "a summary of the terms"]  # fmt: skip
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are careful."},
        {"role": "user", "content": secret[0]},
        {"role": "assistant", "content": secret[4], "reasoning_content": secret[1],
         "tool_calls": [call("call_c01", "read", {"filePath": secret[2]})]},
        {"role": "tool", "tool_call_id": "call_c01", "content": secret[3]},
    ]  # fmt: skip
    found = census(body(*messages, tools=[tool("read", "Reads a file.")]), RATIO, SHORTEST, words=False)
    said = json.dumps(found)
    assert not any(each in said for each in secret), "counts, kinds and tool names only"
    assert {item["what"] for item in found["items"]} == {
        "the system prompt", "the definition of read", "your message", "the model's text", "thinking", "read",
        "the result of read",
    }  # fmt: skip
    assert found["chars"]["yours"] == len(secret[0]), "the sizes stay"
    worded = census(body(*messages), RATIO, SHORTEST)
    assert taken(worded, part="yours")["what"] == f"your message: {secret[0]}", "with its words on, as the records"
