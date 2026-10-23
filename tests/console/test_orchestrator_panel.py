"""Design 0013 §16: the Flow view's Orchestrator panel and its key. The panel says the orchestrator's role (steering or
watching) and the model it runs on, and its last word for the owner; `O` turns it on steering, then watching, then
off, each press saying what it does now."""

from typing import Any

from clank.components.agents.console.flowpanels import orchestrator
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
