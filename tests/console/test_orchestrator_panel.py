"""Design 0013 §16: the Flow view's Orchestrator panel and its key. The panel says the orchestrator's role (steering or
watching) and the model it runs on, and its last word for the owner; `O` turns it on steering, then watching, then
off, each press saying what it does now. Design 0013 §12 (decision 0131): the Thinking panel says what the running box
does now, a tool at work with its command and output, and the model's text as it writes."""

import json
from typing import Any

from clank.components.agents.console.flowpanels import doing, generating, orchestrator
from clank.components.agents.console.flowview import turned


def view(**orchestrated: Any) -> dict[str, Any]:
    """A Flow view's data with its orchestrator as given."""
    return {"flow": {"boxes": []}, "orchestrator": {"changes": 12, "stall_limit": 3, **orchestrated}}


def shown(lines: list[Any]) -> str:
    return "\n".join(line.plain for line in lines)


def test_the_panel_says_its_role_and_the_model_it_runs_on() -> None:
    steering = shown(orchestrator(view(on=True, role="steer", final_review="orchestrator"), 80))
    assert "on · steering · the flow's model" in steering
    watching = shown(orchestrator(view(on=True, role="watch", model="frontier-262k"), 80))
    assert "on · watching · frontier-262k" in watching
    off = shown(orchestrator(view(on=False), 80))
    assert "checks the run is on track" in off, "off, it says what turning it on does"


def test_the_panel_shows_its_last_word_for_the_owner() -> None:
    last = {"number": 2, "kind": "review", "box": "plan", "choice": "go on", "why": "PLAN.md answers the brief.",
            "applied": "went on", "tell_user": "The search needs 3 hours, all of the brief's time."}  # fmt: skip
    lines = shown(orchestrator(view(on=True, role="steer", last=last), 80))
    assert "told you: The search needs 3 hours" in lines


def test_o_turns_it_on_steering_then_watching_then_off() -> None:
    body, said = turned({"on": False})
    assert body == {"on": True, "role": "steer"}
    assert "steering" in said
    body, said = turned({"on": True, "role": "steer"})
    assert body == {"on": True, "role": "watch"}
    assert "watching" in said
    body, said = turned({"on": True, "role": "watch"})
    assert body == {"on": False}
    assert "off" in said


def test_thinking_says_what_the_box_does_now_a_tool_running_with_its_command_output_and_the_models_last_words() -> None:
    """The owner (2026-10-23): Thinking said "ended" while the box's bash ran its search for minutes, the speed of the
    last request beside it; "I need ... to always know what the model is doing". A tool at work: its time, its
    command, its output so far, and what the model said before it called it."""
    command = "cd /workspace/stabrank\nfor s in 101 102; do\n  python run.py --seed $s\ndone"
    now = {"state": "tool", "phase": "running a tool", "step": 9, "seconds": 130.0, "working": True,
           "call": {"tool": "bash", "input": json.dumps({"command": command})}}  # fmt: skip
    view = {"nodes": [
        {"kind": "step", "n": 9, "text": "Batch 1 plateaued; now batch 2, wave 1:", "thinking": 292},
        {"kind": "call", "tool": "bash", "status": "running", "input": json.dumps({"command": command}),
         "output": "wave1 start 04:47:41"},
    ]}  # fmt: skip
    shown = "\n".join(line.plain for line in doing(now, view, 90))
    assert "running a tool · step 9 · 2 min 10 s" in shown
    assert "for s in 101 102; do" in shown, "the command whole, line by line"
    assert "wave1 start 04:47:41" in shown, "its output so far"
    assert "Batch 1 plateaued; now batch 2, wave 1:" in shown, "what the model said before it"
    assert not generating(now), "nothing is written now: the live text is not shown"


def test_while_the_model_writes_the_live_text_is_shown_and_while_idle_it_says_so() -> None:
    assert generating({"state": "thinking", "phase": "thinking", "working": True})
    assert generating({"state": "reading", "phase": "reading the prompt (or queued)", "working": True})
    idle = "\n".join(line.plain for line in doing({"state": "idle", "phase": "idle", "working": False}, None, 90))
    assert "idle" in idle


def test_a_command_cut_short_by_the_watch_is_still_shown_line_by_line() -> None:
    cut = json.dumps({"command": "cd /workspace\nfor s in 1 2; do\n  run $s\ndone\necho done"})[:40] + "…"
    now = {"state": "tool", "phase": "running a tool", "step": 2, "seconds": 5.0, "working": True,
           "call": {"tool": "bash", "input": cut}}  # fmt: skip
    shown = [line.plain for line in doing(now, None, 90)]
    assert "  cd /workspace" in shown
    assert not any('{"command"' in line for line in shown)
