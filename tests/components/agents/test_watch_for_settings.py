"""Design 0012 §8 and §11 step 8 (decision 0053): what each Watch for rule does is the owner's to set, in a readable
settings file, `config/monitor.json`, a settings kind with its schema: mark it, pause the session, tell the phone, or
tell the model and go on, telling the model at most twice in a row. Its defaults are §8's table."""

import json
from collections.abc import Iterator

import pytest

from clank import registry
from clank.components.agents.kinds import MonitorSettings
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home


@pytest.fixture
def kernel(home: Home, clock: FakeClock) -> Iterator[Kernel]:
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def test_the_rules_defaults_are_the_designs_table(kernel: Kernel) -> None:
    loaded = kernel.settings.get("monitor", "monitor")
    assert loaded.source == "built-in"
    settings = MonitorSettings.model_validate(loaded.record.model_dump())
    table = {
        "waiting_for_you": ["mark", "tell the phone"],
        "engine_broke_off": ["mark"],
        "loop_guard_stopped": ["mark", "tell the model"],
        "asks_about_a_repeat": ["mark", "tell the phone"],
        "same_call_again": ["mark"],
        "failing_again": ["mark"],
        "one_file_again": ["mark"],
        "call_then_step_failed": ["mark"],
        "stopped_with_an_ask_waiting": ["mark"],
        "note_not_read": ["mark"],
        "retrying": ["mark"],
        "compaction_near": ["mark"],
        "budget_near": ["mark"],
        "engine_taken": ["mark"],
    }
    assert tuple(table) == MonitorSettings.RULES, "every rule, in §8's order"
    assert {name: settings.rule(name).do for name in MonitorSettings.RULES} == table
    assert settings.notes_in_a_row == 2
    assert settings.rule("loop_guard_stopped").note == (
        "Clank's loop guard stopped your last answer because it repeated itself, and that answer is not in your "
        "context. Go on from where you were, without writing it the same way again."
    ), "decision 0053's words"
    assert all(settings.rule(name).note for name in MonitorSettings.RULES), "every rule has words for its note"


def test_a_rule_changed_in_its_file_is_read_and_an_unknown_action_is_refused(kernel: Kernel, home: Home) -> None:
    path = home.config / "monitor.json"
    path.write_text(json.dumps({"schema": "monitor/1", "same_call_again": {"do": ["mark", "tell the phone"]},
                                "retrying": {"do": []}, "notes_in_a_row": 1}), encoding="utf-8")  # fmt: skip
    assert kernel.settings.load() == []
    settings = MonitorSettings.model_validate(kernel.settings.get("monitor", "monitor").record.model_dump())
    assert settings.rule("same_call_again").do == ["mark", "tell the phone"]
    assert settings.rule("retrying").do == [], "an empty list turns the rule off"
    assert settings.rule("failing_again").do == ["mark"], "the others keep their defaults"
    assert settings.notes_in_a_row == 1
    path.write_text(json.dumps({"schema": "monitor/1", "failing_again": {"do": ["shout"]}}), encoding="utf-8")
    [problem] = kernel.settings.load()
    assert "failing_again" in str(problem)
    kept = MonitorSettings.model_validate(kernel.settings.get("monitor", "monitor").record.model_dump())
    assert kept.rule("same_call_again").do == ["mark", "tell the phone"], "the last good values stay in force"


def test_a_rule_given_in_part_keeps_its_own_defaults_for_the_rest(kernel: Kernel, home: Home) -> None:
    built_in = MonitorSettings()
    path = home.config / "monitor.json"
    path.write_text(json.dumps({"schema": "monitor/1", "loop_guard_stopped": {"do": ["mark", "tell the phone"]},
                                "waiting_for_you": {"note": "The owner will answer."}}), encoding="utf-8")  # fmt: skip
    assert kernel.settings.load() == []
    settings = MonitorSettings.model_validate(kernel.settings.get("monitor", "monitor").record.model_dump())
    assert settings.rule("loop_guard_stopped").do == ["mark", "tell the phone"]
    assert settings.rule("loop_guard_stopped").note == built_in.rule("loop_guard_stopped").note, "its own words kept"
    assert settings.rule("waiting_for_you").note == "The owner will answer."
    assert settings.rule("waiting_for_you").do == ["mark", "tell the phone"], "its own actions kept"


def test_the_schema_shows_each_rules_own_defaults() -> None:
    schema = MonitorSettings.model_json_schema()
    for name in MonitorSettings.RULES:
        default = MonitorSettings().rule(name)
        assert schema["properties"][name]["default"] == {"do": default.do, "note": default.note}, name
    assert "default" not in schema["$defs"]["RuleSettings"]["properties"]["note"], "no empty note offered"
