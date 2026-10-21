"""Test support: board A's model request as OpenCode would send it (design 0012 §4.2), for the Monitor's parts.

`board_a_request()` is the body of the request that answered board A's step 18 (`msg_19`, `ls studies/`), the session's
last finished step (`tests/support/boards.py`): OpenCode's system prompt and its tools' definitions, the owner's
message, and every step before it with its calls and their results, each call's id the flow's (`call_c01`, ...), so the
estimate joins each item to its step. The step the loop guard stopped (`msg_18`) left the context, as OpenCode leaves
out a step that ended in an error. Synthetic: the texts are words in no order, of the sizes board A's calls give back;
one thinking (step 8's) repeats itself past the guard's ratio, a loop kept in the context, and `studies/notes.md` is
read twice, its first result one that could be freed. `board_a_census()` is the gateway's census of it, `PROMPT` its
tokens as an engine would count them (about 3.3 characters a token) and `ANSWER` its answer's.
"""

import json
import random
from typing import Any

from clank.components.gateway.census import census
from tests.support.boards import TODOS, listed

SAID = (
    "the grid of sizes runs from sixteen to sixty four and each run keeps its seed while the estimator reads the "
    "energy gap magnetization and its error bars over every sweep of the lattice before the plot is drawn again "
    "def class return import self value list for in if else with open read write path study notes simulator"
)
TOOLS = {
    "bash": 9_000, "read": 2_400, "write": 1_200, "edit": 2_600, "glob": 900, "grep": 1_300, "list": 700,
    "task": 4_200, "todowrite": 7_800, "todoread": 300, "webfetch": 1_100, "myproject_capabilities": 600,
}  # fmt: skip
ANSWER = 61


def prose(length: int, seed: int) -> str:
    """Words in no order, `length` characters of them."""
    pick, words = random.Random(seed), SAID.split()
    said = ""
    while len(said) < length:
        said += pick.choice(words) + " "
    return said[:length]


def _call(id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"id": f"call_{id}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _step(seed: int, calls: list[tuple[str, str, dict[str, Any], int]], thinking: str = "") -> list[dict[str, Any]]:
    """One step: its answer (its thinking, its calls) and each call's result, of the size given."""
    answer = {"role": "assistant", "content": "", "reasoning_content": thinking or prose(300 + 40 * seed, seed),
              "tool_calls": [_call(id, name, arguments) for id, name, arguments, _ in calls]}  # fmt: skip
    results = [{"role": "tool", "tool_call_id": f"call_{id}", "content": prose(size, seed + index + 1)}
               for index, (id, _, _, size) in enumerate(calls)]  # fmt: skip
    return [answer, *results]


def _read(id: str, path: str, size: int) -> tuple[str, str, dict[str, Any], int]:
    return id, "read", {"filePath": f"/workspace/{path}"}, size


def _bash(id: str, command: str, size: int = 200) -> tuple[str, str, dict[str, Any], int]:
    return id, "bash", {"command": command}, size


def board_a_request() -> dict[str, Any]:
    """The body of the request that answered board A's step 18 (module docstring)."""
    tools = [{"type": "function", "function": {"name": name, "description": prose(size, index),
                                               "parameters": {"type": "object", "properties": {}}}}
             for index, (name, size) in enumerate(TOOLS.items())]  # fmt: skip
    loop = "the energy gap is 0.0 and " * 260  # 6,760 characters of the same few
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prose(11_000, 100)},
        {"role": "user", "content": "Plan a new simulation study for myproject: which observables, which sizes, how "
                                    "long."},
        *_step(1, [("c01", "todowrite", {"todos": listed(0)}, 420)]),
        *_step(2, [("c02", "glob", {"pattern": "**/*.py"}, 900)]),
        *_step(3, [_read("c03", "src/simulator.py", 18_600), _read("c04", "README.md", 2_100),
                   _read("c05", "studies/notes.md", 4_000)]),
        *_step(4, [("c06", "myproject_capabilities", {}, 6_400)]),
        *_step(5, [("c07", "todowrite", {"todos": listed(1)}, 420)]),
        *_step(6, [_bash("c08", "python -m myproject observables --list")]),
        *_step(7, [_bash("c09", "python -m myproject describe magnetization")]),
        *_step(8, [_bash("c10", "python -m myproject describe energy")], thinking=loop),
        *_step(9, [_bash("c11", "python -m myproject describe gap")]),
        *_step(10, [("c12", "task", {"description": "find observables", "prompt": "find observables"}, 1_200)]),
        *[message for n, path in enumerate(["docs/observables.md", "docs/estimators.md", "src/measure.py",
                                            "src/grid.py"])
          for message in _step(11 + n, [_read(f"c{13 + n}", path, 3_000)])],
        *_step(15, [("c17", "todowrite", {"todos": listed(2)}, 420)]),
        *_step(16, [_read("c18", "studies/notes.md", 14_200)]),
    ]  # fmt: skip
    assert len(TODOS) == 5
    return {"model": "agent", "stream": True, "messages": messages, "tools": tools}


def board_a_census() -> dict[str, Any]:
    """The gateway's census of board A's request, measured with the loop guard's defaults."""
    return census(board_a_request(), 0.06, 2000)


PROMPT = round(sum(board_a_census()["chars"].values()) / 3.3)
