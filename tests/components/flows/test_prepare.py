"""Design 0013 §5, §6 and §7 (decision 0087): `clank flow prepare`'s preview shows each box a model runs with its first
message as it would be sent now, from the files as they are now and the active run's state, so it is the message the
runner then sends; each with its size in tokens, an estimate labeled as one unless the engine counted it, against the
window of the preset the box runs on (for a box naming none, the preset a box before it switches the main slot to, else
the main slot's, else not known) and its share of it; one box shown alone; an owner's box has no first message. Run
against the fake bridge and a synthetic folder."""

import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.first import instructions
from clank.components.flows.service import Flows
from clank.kernel.api import ApiError
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
DAILY = 262_144  # the window of Clank's preset "daily 262K" (KVMem's default context)


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study(defaults={"model": "daily 262K"}))
    yield made
    made.kernel.close()


def flows(rig: Rig) -> Flows:
    found: Flows = rig.kernel.parts["flows"]
    return found


def boxes(said: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {each["box"]: each for each in said["boxes"]}


async def test_the_preview_of_a_box_is_the_message_the_runner_then_sends(rig: Rig) -> None:
    runtime = rig.kernel.parts["runtime"]  # the flow's preset runs already, so its boxes need no switch (§7)
    runtime.state.set_slot("main", "ready", "a test", actor=Actor(kind="user", via="a test"), preset="daily-262k",
                           host="local", port=1)  # fmt: skip
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n", ".clank/handoff/study/plan.md": "Chose 60.\n"})
        gate = await until(lambda: question(rig, "You approve the plan"))
        rig.runner.pause(FLOW, actor=OWNER)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        await until(lambda: rig.run().box("approve").state == "done")

        shown = boxes(flows(rig).prepare(WORKSPACE, "study"))
        assert list(shown) == ["plan", "T1"], "every box a model runs, in the order they run; not the owner's"
        assert shown["T1"]["try"] == 1
        assert shown["plan"]["try"] == 2, "a box done shows its next try"
        rig.runner.resume(FLOW, actor=OWNER)
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    assert task.text == shown["T1"]["text"]
    assert "> Chose 60." in task.text


def test_each_box_says_its_size_an_estimate_labeled_as_one_against_its_presets_window(rig: Rig) -> None:
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    said = flows(rig).prepare(WORKSPACE, "study")
    assert (said["flow"], said["title"], said["run"]) == (FLOW, "Study", None)
    plan = boxes(said)["plan"]
    assert plan["text"].startswith(instructions("plan"))
    assert (plan["type"], plan["title"], plan["try"]) == ("plan", "Write the plan", 1)
    assert plan["characters"] == len(plan["text"])
    assert plan["tokens"] == math.ceil(len(plan["text"]) * 0.3)
    assert plan["exact"] is False
    assert plan["counted"].startswith("an estimate: 0.3 tokens per character, Clank's plain default (")
    assert (plan["preset"], plan["preset_title"], plan["window"]) == ("daily-262k", "daily 262K", DAILY)
    assert plan["share"] == pytest.approx(plan["tokens"] / DAILY)
    assert plan["over"] is False
    assert any("OpenCode adds its own instructions and tool definitions" in line for line in said["said"])
    assert any("not written yet are not counted" in line for line in said["said"])


def test_a_box_naming_no_preset_takes_the_main_slots_else_its_window_is_not_known(rig: Rig) -> None:
    rig.write_flow(study())
    plan = boxes(flows(rig).prepare(WORKSPACE, "study"))["plan"]
    assert (plan["preset"], plan["window"], plan["share"], plan["over"]) == ("", None, None, False)
    assert plan["window_said"] == "its window is not known: it names no preset, and the main slot runs none now"
    runtime = rig.kernel.parts["runtime"]
    runtime.state.set_slot("main", "ready", "a test", actor=Actor(kind="user", via="a test"), preset="daily-262k",
                           host="local", port=1)  # fmt: skip
    plan = boxes(flows(rig).prepare(WORKSPACE, "study"))["plan"]
    assert (plan["preset"], plan["preset_title"], plan["window"]) == ("daily-262k", "daily 262K", DAILY)


def test_a_box_naming_no_preset_after_one_that_switches_the_main_slot_takes_that_ones_window(rig: Rig) -> None:
    small_window(rig)
    flow = study()
    flow["boxes"][1]["model"] = "tiny window"
    rig.write_flow(flow)
    runtime = rig.kernel.parts["runtime"]
    runtime.state.set_slot("main", "ready", "a test", actor=Actor(kind="user", via="a test"), preset="daily-262k",
                           host="local", port=1)  # fmt: skip
    shown = boxes(flows(rig).prepare(WORKSPACE, "study"))
    assert (shown["plan"]["preset"], shown["plan"]["window"]) == ("tiny-window", 4096)
    task = shown["T1"]
    assert (task["named"], task["preset"], task["preset_title"], task["window"]) == ("", "tiny-window", "tiny window",
                                                                                     4096)  # fmt: skip
    assert task["share"] == pytest.approx(task["tokens"] / 4096), "the plan's switch leaves the slot on its preset"
    alone = boxes(flows(rig).prepare(WORKSPACE, "study", box="T1"))["T1"]
    assert (alone["preset"], alone["window"]) == ("tiny-window", 4096), "shown alone, the boxes before it still count"


def test_one_box_is_shown_alone_and_an_owners_box_has_no_first_message(rig: Rig) -> None:
    said = flows(rig).prepare(WORKSPACE, "study", box="T1")
    assert [each["box"] for each in said["boxes"]] == ["T1"]
    with pytest.raises(ApiError) as owners:
        flows(rig).prepare(WORKSPACE, "study", box="approve")
    assert owners.value.status == 409
    assert "approve is a GATE, done by you: it has no first message" in str(owners.value)
    with pytest.raises(ApiError) as missing:
        flows(rig).prepare(WORKSPACE, "study", box="T9")
    assert missing.value.status == 404


def test_the_route_serves_the_preview(rig: Rig) -> None:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    with TestClient(create_app(rig.kernel, token="t", port=7721), base_url="http://127.0.0.1:7721") as http:
        answer = http.get(
            f"/api/v1/flows/{WORKSPACE}/study/prepare", params={"box": "plan"}, headers={"Authorization": "Bearer t"}
        )
    assert answer.status_code == 200, answer.text
    found = json.loads(answer.text)
    assert [each["box"] for each in found["boxes"]] == ["plan"]


def small_window(rig: Rig) -> None:
    """A preset of the main slot whose window is 4,096 tokens: a quarter of it is 1,024."""
    preset = rig.kernel.home.config / "presets" / "tiny-window.json"
    preset.parent.mkdir(parents=True, exist_ok=True)
    preset.write_bytes(json.dumps({
        "schema": "preset/1", "title": "tiny window", "engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1",
        "model": "qwen3.8-27b", "options": {"context": 4096, "kvmem.budget": 0},
    }).encode("utf-8"))  # fmt: skip
    rig.kernel.settings.reload_changed()


def test_a_box_whose_first_message_is_over_a_quarter_of_its_window_is_warned_of(rig: Rig) -> None:
    small_window(rig)
    flow = study(defaults={"model": "daily 262K"})
    flow["boxes"][1]["model"] = "tiny window"
    rig.write_flow(flow)
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours. " * 120)
    checked = flows(rig).check(flow=FLOW)
    assert checked["problems"] == []
    plan = boxes(flows(rig).prepare(WORKSPACE, "study"))["plan"]
    assert plan["over"] is True
    assert [each["message"] for each in checked["warnings"]] == [
        f"plan's first message is {plan['tokens']:,} tokens (an estimate), {plan['share']:.0%} of the 4,096 of tiny "
        "window: over a quarter of its window; hand it less whole (its sees, the flow's whole_up_to) or split its work"
    ]
    assert checked["warnings"][0]["field"] == "boxes.1"
    assert boxes(flows(rig).prepare(WORKSPACE, "study"))["T1"]["over"] is False, "T1 runs on daily 262K"


def test_a_file_a_box_sees_or_shows_that_nothing_gives_it_is_warned_of_and_no_other(rig: Rig) -> None:
    flow = study(defaults={"model": "daily 262K"})
    flow["boxes"][3]["sees"] = ["PLAN.md", "notes/missing.md", "data/given.csv", "grid.json"]
    flow["boxes"][2]["shows"] = ["PLAN.md", "figures/none.png"]
    rig.write_flow(flow)
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.write("data/given.csv", "a,b\n")
    checked = flows(rig).check(flow=FLOW)
    assert checked["problems"] == []
    assert [(each["field"], each["message"]) for each in checked["warnings"]] == [
        ("boxes.2.shows.1", "approve shows figures/none.png, which is not in the folder, and neither approve nor a "
                            "box before it writes it"),
        ("boxes.3.sees.1", "T1 sees notes/missing.md, which is not in the folder, and neither T1 nor a box before it "
                           "writes it"),
    ]  # fmt: skip
    assert all(each["line"] for each in checked["warnings"]), "each with its line in the flow's file"
