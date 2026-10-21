"""Design 0013 §4 and §5 (decision 0060): the flow's own OpenCode server is started with the box's context and output
limits, those of the model the main slot runs for it (Clank's configuration, as written when the server started), and
started again only when a box's limits differ (whether its model reads images among them): the old server is ended
once no session at work on it is left, and the run log says so; the run keeps the limits the slot has once that wait
is over. Each box gets its own MCP servers on the flow's server alone, the window's untouched; a box naming a server
the workspace's agent does not get fails at a gate, saying why, while one that fails to connect is said in its log.
Run against the fake bridge and a synthetic folder, the main slot's model given as the gateway's routes say it."""

import itertools
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.gateway.service import Gateway
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, at_work, make_rig, question, running, until

pytestmark = pytest.mark.anyio
FAST = {"status": "ready", "busy": False, "preset": "fast-4k", "title": "fast 4K", "context": 4096, "output": 1024,
        "images": False}  # fmt: skip
DAILY = {**FAST, "preset": "daily-8k", "title": "daily 8K", "context": 8192, "output": 2048}
# OpenCode is told each window less a margin, a quarter of a window this small (decision 0089): 4,096 is told 3,072


def flow(*boxes: dict[str, Any]) -> dict[str, Any]:
    chain = [{"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]}, *boxes]
    lines = [{"from": before["id"], "to": then["id"]} for before, then in itertools.pairwise(chain)]
    return {"schema": "flow/1", "title": "Study", "boxes": chain, "lines": lines}


def task(id: str, **values: Any) -> dict[str, Any]:
    return {"id": id, "type": "task", "title": f"Task {id}", "writes": [f"{id}.md"], "prompt": f"Write {id}.md.",
            **values}  # fmt: skip


@pytest.fixture
def slot(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What the main slot runs, as the gateway's routes say it: the test changes it."""
    now: dict[str, Any] = dict(FAST)
    routes = lambda self: {"slots": {"main": now}, "roles": {"agent": "main"}, "default_slot": "main", "demand": {}}  # noqa: E731
    monkeypatch.setattr(Gateway, "routes", routes)
    return now


@pytest.fixture
def rig(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slot: dict[str, Any]
) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, None)
    yield made
    made.kernel.close()


async def brief_done(rig: Rig) -> None:
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")


def limits(rig: Rig, port: int) -> dict[str, int]:
    """The model's limits in the configuration the server on `port` was started with."""
    config = json.loads(rig.bridge.servers[port].config or "{}")
    [model] = config["provider"]["clank"]["models"].values()
    return dict(model["limit"])


def servers(rig: Rig) -> list[tuple[str, str, Any]]:
    """Each `flows.server` event: its box, what it did, and the server it replaced."""
    return [
        (str(each.data["box"]), str(each.data["action"]), each.data["replaced"]) for each in rig.events("flows.server")
    ]


async def test_the_server_is_started_with_the_boxs_limits_and_again_only_when_they_differ(
    rig: Rig, slot: dict[str, Any]
) -> None:
    rig.write_flow(flow(task("T1"), task("T2"), task("T3")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        assert limits(rig, first.port) == {"context": 3072, "output": 1024}, "the limits of what the slot runs"
        slot.update(DAILY)  # the slot runs another model by the next box (its preset, or the owner's switch)
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})

        second = await at_work(rig, "T2")
        assert len(rig.bridge.done("serve")) == 2, "started again for other limits (on the first free port)"
        assert list(rig.bridge.servers) == [second.port], "the old server ended"
        assert limits(rig, second.port) == {"context": 6144, "output": 2048}
        rig.bridge.finish(second.session, {"T2.md": "# T2\n"})

        third = await at_work(rig, "T3")
        assert (third.port, len(rig.bridge.done("serve"))) == (second.port, 2), "the same limits: the same server"
        rig.bridge.finish(third.session, {"T3.md": "# T3\n"})
        await until(lambda: rig.run().status == "done")

    assert servers(rig) == [("T1", "started", None), ("T2", "started again", first.port)]
    [again] = [each for each in rig.events("flows.server") if each.data["action"] == "started again"]
    assert again.summary == (
        f"the OpenCode server of Study started again on port {second.port} for T2, whose model has other limits "
        f"(6,144 tokens of context, 2,048 out; the server had 3,072 and 1,024): the server on port {first.port} ended, "
        "and what its MCP servers ran in the background with it"
    )
    run = rig.run()
    assert (run.server, run.server_limits.model_dump() if run.server_limits else None) == (
        second.port, {"context": 6144, "output": 2048, "images": False}
    )  # fmt: skip
    pattern = f"(^|/)opencode serve --port {first.port}( |$)"
    assert [argv for argv in rig.bridge.commanded if argv[0] == "pkill"] == [["pkill", "-TERM", "-f", pattern]]


async def test_a_server_to_start_again_waits_for_a_session_at_work_on_it(rig: Rig, slot: dict[str, Any]) -> None:
    rig.write_flow(flow(task("T1"), task("T2")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        rig.bridge.servers[first.port].sessions["ses_phone"] = {"title": "From the phone", "status": "busy"}
        rig.bridge.say(
            {"type": "session", "port": first.port, "session": {"id": "ses_phone", "title": "From the phone"}}
        )
        rig.bridge.say({"type": "status", "port": first.port, "session": "ses_phone", "status": "busy"})
        slot.update(DAILY)
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})

        said = await until(lambda: rig.run().waits_for)
        assert said == (
            "waiting for your session From the phone on the flow's OpenCode server to be idle, to start it again "
            "with T2's limits"
        )
        assert first.port in rig.bridge.servers, "not ended while a session works on it"
        assert [argv for argv in rig.bridge.commanded if argv[0] == "pkill"] == []
        rig.bridge.status("ses_phone", "idle")
        await at_work(rig, "T2")
        assert len(rig.bridge.done("serve")) == 2, "started again once the session was idle"
        assert rig.run().waits_for == ""
    assert [action for _, action, _ in servers(rig)] == ["started", "waits", "started again"]


async def test_a_server_started_again_after_a_wait_keeps_the_limits_the_slot_has_once_it_is_free(
    rig: Rig, slot: dict[str, Any]
) -> None:
    """The slot changed again while the server's session was waited for: the server is started with the limits the
    slot has then, and the run keeps those, so the next box compares with what the server really has."""
    rig.write_flow(flow(task("T1"), task("T2")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        rig.bridge.servers[first.port].sessions["ses_phone"] = {"title": "From the phone", "status": "busy"}
        rig.bridge.say({"type": "status", "port": first.port, "session": "ses_phone", "status": "busy"})
        slot.update(DAILY)
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})
        await until(lambda: rig.run().waits_for)
        slot.update({**DAILY, "preset": "daily-16k", "title": "daily 16K", "context": 16384, "output": 4096})
        rig.bridge.status("ses_phone", "idle")
        second = await at_work(rig, "T2")
        assert limits(rig, second.port) == {"context": 12288, "output": 4096}
        kept = rig.run().server_limits
        assert kept is not None
        assert kept.model_dump() == {"context": 12288, "output": 4096, "images": False}, "what the server has"


async def test_a_box_whose_model_reads_images_where_the_servers_did_not_gets_the_server_started_again(
    rig: Rig, slot: dict[str, Any]
) -> None:
    """The configuration says whether the model reads images, so a model with the same context and output that reads
    them (or not) gets the server started again, as other limits do."""
    rig.write_flow(flow(task("T1"), task("T2")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        slot.update(images=True)
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})
        second = await at_work(rig, "T2")
        assert len(rig.bridge.done("serve")) == 2, "started again"
        config = json.loads(rig.bridge.servers[second.port].config or "{}")
        [model] = config["provider"]["clank"]["models"].values()
        assert model["attachment"] is True, "its configuration says it reads images"
        kept = rig.run().server_limits
        assert kept is not None
        assert kept.images is True
    [again] = [each for each in rig.events("flows.server") if each.data["action"] == "started again"]
    assert again.data["images"] is True
    assert (
        "whose model has other limits (3,072 tokens of context, 1,024 out, reading images; the server had 3,072 and "
        "1,024, reading none)"
    ) in again.summary


async def test_each_box_gets_its_mcp_servers_on_the_flows_server_the_windows_untouched(rig: Rig) -> None:
    tools = rig.kernel.parts["tools"]
    tools.add("notes", {"command": "notes-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    tools.add("sim", {"command": "sim-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    window = rig.bridge.window()
    rig.bridge.servers[window].mcp = dict.fromkeys(("clank", "notes", "sim"), "connected")
    rig.write_flow(flow(task("T1", mcp_servers=["sim"]), task("T2")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        assert rig.bridge.servers[first.port].mcp == {"clank": "connected", "notes": "disabled", "sim": "connected"}
        assert rig.run().box("T1").tries[-1].tools == ["clank", "sim"], "the try says the MCP servers it had"
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})
        second = await at_work(rig, "T2")
        assert rig.bridge.servers[second.port].mcp == dict.fromkeys(("clank", "notes", "sim"), "connected")
        assert rig.run().box("T2").tries[-1].tools == ["clank", "notes", "sim"]
    assert rig.bridge.servers[window].mcp == dict.fromkeys(("clank", "notes", "sim"), "connected"), "untouched"
    assert {rest[0] for rest in [*rig.bridge.done("mcp-start"), *rig.bridge.done("mcp-stop")]} == {str(first.port)}


async def test_a_box_naming_an_mcp_server_the_workspaces_agent_does_not_get_fails_at_a_gate(rig: Rig) -> None:
    rig.write_flow(flow(task("T1", mcp_servers=["nowhere"])))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        gate = await until(lambda: question(rig, "Task T1 failed"))
        assert gate.title == (
            "Study: Task T1 failed: it names the MCP server nowhere, which myproject's agent does not get: it is no "
            "MCP server of yours or of the folder"
        )
        assert rig.bridge.prompted("T1") is None, "no session started"


async def test_an_mcp_server_that_fails_to_connect_is_said_in_the_boxs_log_and_the_box_still_starts(rig: Rig) -> None:
    """Plan s27 call 10: a server that fails to connect is said in the operation's log and left out of the try's tools;
    only one the workspace's agent does not get fails the box."""
    tools = rig.kernel.parts["tools"]
    for name in ("notes", "sim"):
        tools.add(name, {"command": f"{name}-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    rig.write_flow(flow(task("T1", mcp_servers=["sim"]), task("T2")))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        first = await at_work(rig, "T1")
        rig.bridge.refuse["mcp-start"] = "notes did not connect within 90 seconds"
        rig.bridge.finish(first.session, {"T1.md": "# T1\n"})
        second = await at_work(rig, "T2")
        attempt = rig.run().box("T2").tries[-1]
        assert attempt.tools == ["clank", "sim"], "left out of the try's tools"
        said = [line.text for line in rig.kernel.operations.log_lines(attempt.operation)]
        assert "its MCP server notes did not connect: notes did not connect within 90 seconds" in said
        rig.bridge.finish(second.session, {"T2.md": "# T2\n"})
        await until(lambda: rig.run().status == "done")
