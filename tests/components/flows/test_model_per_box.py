"""Design 0013 §7 (decisions 0062 and 0063): a box's model is a preset, switched into the main slot before the box
starts when the slot does not run it, by the runtime's own switch: a flow alternating two presets switches exactly
before the boxes that need it, and a VERIFY runs on the preset of the box it checks with no switch. No switch starts
while a request is in flight on the slot, while the gateway does not say what is, while another operation changes the
slot, or while the owner's own session in the workspace works: the run says what it waits for; a switch refused as
the slot was taken a moment ago is started once it is free. A switch that fails returns the slot to the last
configuration that worked and leaves the box failed at a gate. A run stopped, or a box canceled, while its box waits
starts no switch, and a wait the service's stop cut short is not said after the restart; a run stopped while the slot
switches lets the switch end, and the window is still told. After a switch, the owner's window is told, a preset too
small for one of the owner's sessions named, and the window is left as it is. The switches a flow makes say how long
each preset's last whole switch took. Run with the fake engine (two presets of a tiny model, real processes of this
machine's CPU), the fake bridge and a synthetic folder."""

import itertools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.verdicts import AGENT
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.operations import Busy
from tests.components.flows.engines import DAILY, FAST, install, runs, stop, with_engines
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, at_work, make_rig, question, restart, running, until

pytestmark = pytest.mark.anyio
SWITCH = 30  # seconds a test waits for a switch of the fake engine, on a busy machine


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = with_engines(make_rig(home, clock, tmp_path, monkeypatch, None), tmp_path)
    try:
        yield made
    finally:
        stop(made)
        made.kernel.close()


def flow(*boxes: dict[str, Any]) -> dict[str, Any]:
    """The owner's brief, then the boxes, a chain; a VERIFY's fail line back to the box it checks."""
    chain = [{"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]}, *boxes]
    lines: list[dict[str, Any]] = []
    for before, then in itertools.pairwise(chain):
        when = {"when": "pass"} if before["type"] == "verify" else {}
        lines.append({"from": before["id"], "to": then["id"], **when})
    lines += [{"from": each["id"], "to": each["checks"], "when": "fail"} for each in chain if each["type"] == "verify"]
    return {"schema": "flow/1", "title": "Study", "boxes": chain, "lines": lines}


def task(id: str, model: str = "") -> dict[str, Any]:
    return {"id": id, "type": "task", "title": f"Task {id}", "writes": [f"{id}.md"], "prompt": f"Write {id}.md.",
            **({"model": model} if model else {})}  # fmt: skip


async def brief_done(rig: Rig) -> None:
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")


def switches(rig: Rig) -> list[str]:
    """The presets of the main slot's switches, oldest first."""
    found = [each for each in rig.kernel.operations.find(limit=200) if each.type == "runtime.switch"]
    return [str(each.params["preset"]) for each in reversed(found)]


def models(rig: Rig) -> list[tuple[str, str]]:
    """Each `flows.model` event: its box and what it said."""
    return [(str(each.data["box"]), str(each.data["action"])) for each in rig.events("flows.model")]


async def test_a_flow_alternating_two_presets_switches_exactly_before_the_boxes_that_need_it(rig: Rig) -> None:
    plan = {"id": "plan", "type": "plan", "title": "Write the plan", "writes": ["PLAN.md"], "prompt": "Plan it.",
            "model": "daily 8K"}  # fmt: skip
    check = {"id": "check", "type": "verify", "title": "Check the plan", "checks": "plan", "sees": ["PLAN.md"]}
    rig.write_flow(flow(plan, check, task("T1", "fast 4K"), task("T2", "fast-4k"), task("T3", "daily 8K")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        for box, preset, made in (("plan", DAILY, "PLAN.md"), ("check", DAILY, ""), ("T1", FAST, "T1.md"),
                                  ("T2", FAST, "T2.md"), ("T3", DAILY, "T3.md")):  # fmt: skip
            prompt = await at_work(rig, box) if box != "plan" else None
            if prompt is None:
                await until(lambda: rig.bridge.prompted("Study · plan · try 1"), SWITCH)
                prompt = await at_work(rig, "plan")
            assert runs(rig) == preset, f"{box} works on {preset}"
            assert rig.run().box(box).tries[-1].preset == preset, "its try names the preset it ran on"
            if box == "check":
                rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
            rig.bridge.finish(prompt.session, {made: f"# {box}\n"} if made else None)
            if box == "T2":
                await until(lambda: rig.bridge.prompted("Study · T3 · try 1"), SWITCH)
        await until(lambda: rig.run().status == "done", SWITCH)

    assert switches(rig) == [DAILY, FAST, DAILY], "before plan, T1 and T3 only: the check and T2 keep what runs"
    assert models(rig) == [
        ("plan", "switching"), ("plan", "switched"), ("T1", "switching"), ("T1", "switched"), ("T3", "switching"),
        ("T3", "switched"),
    ]  # fmt: skip
    started = [
        (event.type, event.data.get("box"))
        for event in rig.events("flows.model", "flows.box_started")
        if event.type == "flows.box_started" or event.data.get("action") == "switched"
    ]
    assert started[1:] == [
        ("flows.model", "plan"), ("flows.box_started", "plan"), ("flows.box_started", "check"),
        ("flows.model", "T1"), ("flows.box_started", "T1"), ("flows.box_started", "T2"), ("flows.model", "T3"),
        ("flows.box_started", "T3"),
    ], "each switch done before its box's session starts"  # fmt: skip
    told = [event.data["title"] for event in rig.events("agents.model_changed")]
    assert told == ["daily 8K", "fast 4K", "daily 8K"], "the owner's window told after each switch"


async def test_after_a_switch_the_owners_window_is_told_naming_a_preset_too_small_and_left_as_it_is(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    window = rig.bridge.window()
    rig.bridge.servers[window].sessions["ses_mine"] = {"title": "My analysis", "status": "idle"}
    rig.bridge.say({"type": "session", "port": window, "session": {"id": "ses_mine", "title": "My analysis"}})
    rig.bridge.say({"type": "status", "port": window, "session": "ses_mine", "status": "idle"})
    agents = rig.kernel.parts["agents"]
    held = {"ses_mine": 6000}
    monkeypatch.setattr(agents, "context", lambda workspace, id: {"used": held.get(id, 9000)})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        prompt = await at_work(rig, "T1")
        [told] = rig.events("agents.model_changed")
        assert told.summary == (
            "The flow Study, for its box T1, switched the main slot to fast 4K (4,096 tokens of context, 1,024 out): "
            "your OpenCode window in myproject talks to it from its next step, with the limits it started with until "
            "it next starts; fast 4K is too small for your session My analysis, which holds 6,000 tokens"
        ), "the box's own session, which holds more, is not named"
        assert agents.model_notice(WORKSPACE)["said"] == told.summary, "This folder shows it"
        assert window in rig.bridge.servers, "the window goes on"
        acted = [rest for _, rest in rig.bridge.actions if rest[:1] == [str(window)]]
        assert acted == [], "nothing is asked of the window"
        rig.bridge.finish(prompt.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().status == "done")


async def test_no_switch_starts_while_a_request_is_in_flight_on_the_slot_and_the_run_says_so(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    flying = [{"id": "r-1", "role": "agent", "slot": "main", "session": "ses_elsewhere", "phase": "answering"}]
    gateway = rig.kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "activity", lambda *args, **kwargs: {"state": "running", "requests": list(flying)})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        said = await until(lambda: rig.run().waits_for)
        assert said == "waiting for 1 request in flight on the main slot to end, to load fast 4K"
        assert switches(rig) == [], "no switch while a request is in flight"
        assert models(rig) == [("T1", "waits")]
        flying.clear()
        prompt = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"), SWITCH)
        assert runs(rig) == FAST
        assert rig.run().waits_for == "", "it waits no more"
        rig.bridge.finish(prompt.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().status == "done")
    [waited] = [each for each in rig.events("flows.model") if each.data["action"] == "waits"]
    assert waited.summary == "T1 of Study is waiting for 1 request in flight on the main slot to end, to load fast 4K"


async def test_no_switch_starts_while_the_owners_own_session_in_the_workspace_works(rig: Rig) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    window = rig.bridge.window()
    rig.bridge.servers[window].sessions["ses_mine"] = {"title": "My analysis", "status": "busy"}
    rig.bridge.say({"type": "session", "port": window, "session": {"id": "ses_mine", "title": "My analysis"}})
    rig.bridge.say({"type": "status", "port": window, "session": "ses_mine", "status": "busy"})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        said = await until(lambda: rig.run().waits_for)
        assert said == "waiting for your session My analysis to be idle, to load fast 4K"
        assert switches(rig) == []
        rig.bridge.status("ses_mine", "idle")
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"), SWITCH)
        assert switches(rig) == [FAST]


async def test_a_failed_switch_returns_the_slot_and_leaves_the_box_failed_at_a_gate(rig: Rig, tmp_path: Path) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    async with running(rig.kernel):
        loaded = await rig.kernel.operations.start("runtime.load", {"slot": "main", "preset": DAILY}, actor=OWNER)
        assert (await rig.kernel.operations.wait(loaded.id)).status == "done"
        install(rig, tmp_path, "--fake-fail-start", "oom", "--fake-only-context", "4096")
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        gate = await until(lambda: question(rig, "Task T1"), SWITCH)
        assert runs(rig) == DAILY, "the slot went back to the last configuration that worked"
        assert rig.bridge.prompted("T1") is None, "no session started"
        state = rig.run().box("T1")
        assert state.state == "failed"
        assert "the main slot did not switch to fast 4K: fast 4K ended while it started" in state.why
        assert "out of memory" in state.why, "in the engine's own words"
        assert "back to daily 8K, which runs again" in state.why
        assert gate.status == "waiting"
    assert switches(rig) == [FAST]
    assert models(rig) == [("T1", "switching"), ("T1", "failed")]
    [box] = [each for each in rig.kernel.operations.find(limit=50) if each.type == "flows.box"]
    assert (box.status, box.steps[-1].name) == ("failed", "model")


async def test_a_run_stopped_while_its_box_waits_starts_no_switch(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    flying = [{"id": "r-1", "role": "agent", "slot": "main", "session": "", "phase": "reading the prompt"}]
    gateway = rig.kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "activity", lambda *args, **kwargs: {"state": "running", "requests": list(flying)})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        await until(lambda: rig.run().waits_for)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().box("T1").tries and rig.run().box("T1").tries[-1].outcome == "stopped")
        flying.clear()
    assert switches(rig) == []
    assert rig.run().status == "stopped"
    assert rig.run().waits_for == ""


async def test_a_wait_cut_short_by_the_service_stopping_is_not_said_after_the_restart(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service killed while a box waits leaves the wait in the run's file: after the restart its box fails at a
    gate, and the run no longer says it waits."""
    rig.write_flow(flow(task("T1", "fast 4K")))
    flying = [{"id": "r-1", "role": "agent", "slot": "main", "session": "", "phase": "answering"}]
    monkeypatch.setattr(rig.kernel.parts["gateway"], "activity", lambda *args, **kwargs: {"requests": list(flying)})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        said = await until(lambda: rig.run().waits_for)
    killed = rig.run()
    killed.waits_for = said  # as a kill leaves it, before the step's own end could take it back
    rig.runner.runs.save(killed)
    again = restart(rig)
    async with running(again.kernel):
        await until(lambda: question(again, "Task T1 failed"))
        assert again.run().waits_for == ""
    assert switches(again) == []


async def test_a_run_stopped_while_the_slot_switches_lets_the_switch_end_and_still_tells_the_window(
    rig: Rig, tmp_path: Path
) -> None:
    """The owner's stop heard while the runner's own switch runs: the switch goes on to its end in the runtime, and
    what follows every switch the runner made still follows it (decision 0062)."""
    rig.write_flow(flow(task("T1", "fast 4K")))
    install(rig, tmp_path, "--fake-start-seconds", "2", "--fake-only-context", "4096")
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        await until(lambda: ("T1", "switching") in models(rig), SWITCH)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().box("T1").tries[-1].outcome == "stopped", SWITCH)
        assert runs(rig) == FAST, "the switch it started went on to its end"
    assert models(rig) == [("T1", "switching"), ("T1", "switched")], "the run log says the switch ended"
    told = [event.data["title"] for event in rig.events("agents.model_changed")]
    assert told == ["fast 4K"], "the owner's window told, as after every switch the runner made"
    attempt = rig.run().box("T1").tries[-1]
    assert attempt.preset == FAST, "its try names the preset loaded for it"
    assert attempt.reason.startswith("stopped by "), attempt.reason
    assert rig.bridge.prompted("T1") is None, "no session started"
    assert rig.run().status == "stopped"


async def test_a_box_waits_for_a_load_that_changes_the_slot_and_says_so_then_switches(rig: Rig, tmp_path: Path) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    install(rig, tmp_path, "--fake-start-seconds", "3", "--fake-only-context", "8192")
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        loaded = await rig.kernel.operations.start("runtime.load", {"slot": "main", "preset": DAILY}, actor=OWNER)
        rig.write("BRIEF.md", "About 60 grid points.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        said = await until(lambda: rig.run().waits_for, SWITCH)
        assert said == f"waiting for {loaded.title} ({loaded.id}) on the main slot to end, to load fast 4K"
        assert switches(rig) == [], "no switch while another operation changes the slot"
        prompt = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"), SWITCH)
        assert rig.kernel.operations.get(loaded.id).status == "done"
        assert (switches(rig), runs(rig)) == ([FAST], FAST), "switched once the load ended"
        rig.bridge.finish(prompt.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().status == "done")
    assert models(rig) == [("T1", "waits"), ("T1", "switching"), ("T1", "switched")]


async def test_a_switch_refused_because_the_slot_was_taken_a_moment_ago_is_started_once_it_is_free(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    operations = rig.kernel.operations
    start = operations.start
    refused: list[str] = []

    async def taken_once(type: str, params: Any = None, **given: Any) -> Any:
        if type == "runtime.switch" and not refused:
            refused.append(type)
            raise Busy("slot:main is in use by Load daily 8K (op-elsewhere), started by you from the console")
        return await start(type, params, **given)

    monkeypatch.setattr(operations, "start", taken_once)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        prompt = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"), SWITCH)
        assert refused == ["runtime.switch"], "refused once"
        assert (switches(rig), runs(rig)) == ([FAST], FAST), "then started once, and waited for"
        rig.bridge.finish(prompt.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().status == "done")
    assert models(rig) == [("T1", "switching"), ("T1", "switched")]


async def test_a_box_canceled_while_it_waits_starts_no_switch_and_its_try_is_stopped(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.write_flow(flow(task("T1", "fast 4K")))
    flying = [{"id": "r-1", "role": "agent", "slot": "main", "session": "", "phase": "answering"}]
    monkeypatch.setattr(rig.kernel.parts["gateway"], "activity", lambda *args, **kwargs: {"requests": list(flying)})
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        await until(lambda: rig.run().waits_for)
        box = rig.run().operation
        await rig.kernel.operations.cancel(box, actor=OWNER)
        await until(lambda: question(rig, "Task T1"))
        attempt = rig.run().box("T1").tries[-1]
        assert (attempt.outcome, attempt.reason) == ("stopped", "canceled from the Operations page")
        assert rig.kernel.operations.get(box).status == "canceled"
        assert rig.run().waits_for == ""
    assert switches(rig) == []
    assert models(rig) == [("T1", "waits")]


async def test_no_switch_starts_while_the_gateway_does_not_say_what_it_has_in_flight(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway runs but its activity did not answer in time: what is in flight on the slot is not known, so the
    switch waits rather than taking no answer for none in flight (design 0013 §7)."""
    rig.write_flow(flow(task("T1", "fast 4K")))
    problem = ["the gateway did not say what it does: timed out"]

    def activity(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"state": "running", "requests": [], "problem": problem[0] if problem else ""}

    monkeypatch.setattr(rig.kernel.parts["gateway"], "activity", activity)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        said = await until(lambda: rig.run().waits_for)
        assert said == "waiting for the gateway to say what is in flight on the main slot, to load fast 4K"
        assert switches(rig) == []
        problem.clear()
        prompt = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"), SWITCH)
        assert runs(rig) == FAST
        rig.bridge.finish(prompt.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().status == "done")


async def test_a_flows_switches_say_how_long_the_last_whole_switch_to_each_preset_took(rig: Rig) -> None:
    """Design 0013 §7: the whole switch is recorded with its duration, and the switches a flow makes say the last one
    recorded for each preset (the clock the operations keep is the test's, moved on while each switch runs)."""
    rig.write_flow(flow(task("T1", "fast 4K"), task("T2", "daily 8K")))

    async def switched_for(box: str, took: int) -> None:
        await until(lambda: (box, "switching") in models(rig), SWITCH)
        rig.clock.advance(took)
        prompt = await until(lambda: rig.bridge.prompted(f"Study · {box} · try 1"), SWITCH)
        rig.bridge.finish(prompt.session, {f"{box}.md": f"# {box}\n"})

    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        await switched_for("T1", 25)
        await switched_for("T2", 40)
        await until(lambda: rig.run().status == "done", SWITCH)
    shown = rig.kernel.parts["flows"].flow(WORKSPACE, "study")
    assert shown["running"] == DAILY
    assert [(each["box"], each["preset"], each["seconds"], each["whole"]) for each in shown["switches"]] == [
        ("T1", FAST, 25.0, True), ("T2", DAILY, 40.0, True),
    ], "each preset's last whole switch, from its start to its end"  # fmt: skip
