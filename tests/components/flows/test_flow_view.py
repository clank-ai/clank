"""Design 0013 §12 and §14 step 6 (with §3, §8, §9 and §10): what the Monitor's Flow view shows of a flow, made in the
service from the flow, its latest run, the run's proposals and its events, so the console draws it knowing none of the
runner's rules. Board D1's moment says each box's state, its tries and verdicts, its files and when it last ended; the
lines say which ran, which runs now and which not yet, the fail line its findings; The brief, checked lists the
brief's lines and every *accept when*, the newest verdict on each; Deliverables, Ahead, Models in this flow and Waiting
for you are said; proposals waiting join where they would join, marked proposed; a folder's Monitor shows the flow of
the active run, else the one run last, else the first; the run log (`h`) is the run's events, oldest first. Runs are
written as the runner writes them; nothing runs."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.flows.view import view
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform
from tests.support.flowshapes import (
    FINDINGS,
    FLOW,
    NOW,
    OWNER,
    T2_SESSION,
    WORKSPACE,
    at,
    d1_flow,
    d1_run,
    d1_values,
    install_d1,
    proposed_batch,
    write_flow,
    write_run,
)

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    made = open_kernel(home, clock, registry.components())
    yield made
    made.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "paper"


@pytest.fixture
def d1(kernel: Kernel, clock: FakeClock, folder: Path) -> dict[str, Any]:
    install_d1(kernel, clock, folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=OWNER, preset="daily-262k")
    shown: dict[str, Any] = kernel.parts["flows"].view(str(folder))
    return shown


def box(shown: dict[str, Any], id: str) -> dict[str, Any]:
    return next(each for each in shown["boxes"] if each["id"] == id)


def test_board_d1s_moment_says_each_boxs_state_tries_verdicts_and_files(d1: dict[str, Any]) -> None:
    assert (d1["flow"], d1["workspace"], d1["title"]) == (FLOW, WORKSPACE, "A new simulation study")
    assert d1["run"]["number"] == 1
    assert d1["run"]["status"] == "running"
    assert d1["run"]["at"] == "T2"
    assert d1["run"]["created"] == "2026-10-20T12:02:00.000Z"
    assert [each["id"] for each in d1["boxes"]] == [
        "brief", "plan", "check", "approve", "split", "T1", "T2", "T3", "T4", "join", "review",
    ]  # fmt: skip
    states = {each["id"]: each["state"] for each in d1["boxes"]}
    assert states == {
        "brief": "done", "plan": "done", "check": "done", "approve": "done", "split": "done", "T1": "done",
        "T2": "running", "T3": "waiting", "T4": "waiting", "join": "waiting", "review": "waiting",
    }  # fmt: skip
    plan, check, t2 = box(d1, "plan"), box(d1, "check"), box(d1, "T2")
    assert [each["number"] for each in plan["tries"]] == [1, 2]
    assert plan["cap"] == 3
    assert plan["tries"][1]["written"] == ["PLAN.md"]
    assert plan["tries"][1]["ended"] == "2026-10-20T12:18:00.000Z"
    assert plan["preset"] == "daily-262k"
    assert plan["preset_title"] == "daily 262K"
    assert plan["mode"] == "plan"
    assert check["tries"][0]["verdict"]["result"] == "fail"
    assert check["tries"][0]["verdict"]["findings"] == FINDINGS
    assert check["tries"][1]["verdict"]["result"] == "pass"
    assert check["checks"] == "plan"
    assert t2["tries"][0]["session"] == {"workspace": WORKSPACE, "port": 4097, "session": T2_SESSION}
    assert t2["mode"] == "auto"
    assert t2["proposed"] == {"run": 1, "by": "split", "accepted": "owner"}
    assert t2["edited"] is True, "the owner edited T2's prompt in D4"
    assert box(d1, "T1")["edited"] is False
    assert box(d1, "approve")["ended"] == "2026-10-20T12:30:00.000Z", "a gate's end is its event's"
    assert box(d1, "approve")["ended_by"] == "you (console)"
    assert box(d1, "brief")["preset"] == ""
    assert box(d1, "brief")["writes"] == ["BRIEF.md"]
    assert box(d1, "split")["next"] == ["T1", "T2", "T3", "T4"]
    assert box(d1, "T3")["next"] == ["join"]
    assert box(d1, "T2")["settings"]["prompt"].startswith("Estimate the run time of each grid point")
    assert box(d1, "approve")["shown"] == [{"path": "PLAN.md", "box": "plan"}], "a gate's files and who wrote them"
    assert box(d1, "review")["shown"] == [{"path": "STUDY-PLAN.md", "box": "join"}]
    assert d1["folder"].endswith("paper")
    assert d1["counts"] == {"done": 6, "running": 1, "waiting": 4}


def test_the_lines_say_which_ran_which_runs_now_and_which_not_yet_and_the_fail_line_its_findings(
    d1: dict[str, Any],
) -> None:
    lines = {(each["from"], each["to"]): each for each in d1["lines"]}
    assert lines[("brief", "plan")]["state"] == "ran"
    assert lines[("check", "approve")]["state"] == "ran"
    assert lines[("check", "approve")]["when"] == "pass"
    assert lines[("split", "T2")]["state"] == "now", "the path being run"
    assert lines[("split", "T3")]["state"] == "not yet"
    assert lines[("T2", "join")]["state"] == "not yet"
    fail = lines[("check", "plan")]
    assert fail["when"] == "fail"
    assert fail["state"] == "failed"
    assert (fail["findings"], fail["used"], fail["cap"]) == (3, 2, 3), "3 findings sent back; plan used 2 of 3 tries"


def test_the_brief_checked_lists_its_lines_and_every_accept_when_with_the_newest_verdict_on_each(
    d1: dict[str, Any],
) -> None:
    brief = d1["brief"]
    assert brief["file"] == "BRIEF.md"
    said = {each["line"]: each for each in brief["lines"]}
    assert list(said)[:2] == ["about 60 grid points", "at most 48 CPU-hours"], "the brief's own lines first"
    assert said["at most 48 CPU-hours"]["met"] is True, "the newest verdict, the pass of try 2, not the fail of try 1"
    assert said["at most 48 CPU-hours"]["evidence"] == "about 41, by PLAN.md's estimate"
    assert (said["at most 48 CPU-hours"]["by"], said["at most 48 CPU-hours"]["try"]) == ("check", 2)
    assert said["the seeds are fixed"]["source"] == "plan", "a line of the plan's accept when"
    assert said["every grid point has an estimate"]["met"] is None, "not checked yet"
    assert brief["met"] == 3
    assert brief["of"] == len(brief["lines"]) == 7


def test_deliverables_ahead_models_and_waiting_for_you_are_said(d1: dict[str, Any]) -> None:
    written = [(each["path"], each["box"], each["try"], each["passed"]) for each in d1["deliverables"]]
    assert written == [("BRIEF.md", "brief", None, None), ("PLAN.md", "plan", 2, True), ("grid.json", "T1", 1, None)]
    assert all(each["present"] for each in d1["deliverables"]), "each is in the folder now"
    ahead = {each["box"]: each["costs"] for each in d1["ahead"]}
    assert list(ahead) == ["T3", "T4", "join", "review"]
    assert ahead["T3"] == ["a fresh prompt"]
    assert ahead["review"] == ["asks you"]
    assert d1["models"] == [{"preset": "daily-262k", "title": "daily 262K", "loaded": True, "boxes": 8}]
    assert d1["yours"] == 3
    assert d1["waiting"] == []
    assert d1["next_ask"] == {"box": "review", "title": "You review the whole", "after": "join"}


def test_proposals_waiting_join_where_they_would_join_marked_proposed(
    kernel: Kernel, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    values = d1_values()
    values["boxes"] = [each for each in values["boxes"] if not each["id"].startswith("T")]
    values["lines"] = [
        each for each in values["lines"] if not (each["from"].startswith("T") or each["to"].startswith("T"))
    ]
    values["lines"].insert(4, {"from": "split", "to": "join"})
    write_flow(kernel, values)
    run = d1_run()
    run.at, run.boxes = "split", {name: state for name, state in run.boxes.items() if not name.startswith("T")}
    write_run(kernel.parts["flows"].runner.runs, run, proposed_batch(3))
    shown = kernel.parts["flows"].view(str(folder))
    assert [each["id"] for each in shown["boxes"]][4:9] == ["split", "T1", "T2", "T3", "join"]
    assert [box(shown, id)["state"] for id in ("T1", "T2", "T3")] == ["proposed"] * 3
    assert box(shown, "split")["next"] == ["T1", "T2", "T3"]
    proposals = shown["proposals"]
    assert proposals["box"] == "split"
    assert proposals["waiting"] == ["T1", "T2", "T3"]
    assert [each["id"] for each in proposals["items"]] == ["T1", "T2", "T3"]
    assert proposals["items"][0]["writes"] == ["out/t1.md"]
    assert proposals["items"][0]["state"] == "proposed"
    assert shown["counts"]["proposed"] == 3


def test_a_folders_monitor_shows_the_active_run_else_the_last_run_else_the_first_flow(
    kernel: Kernel, clock: FakeClock, folder: Path
) -> None:
    flows = kernel.parts["flows"]
    assert flows.view(str(folder))["flow"] is None, "a folder with no workspace"
    assert "no workspace" in flows.view(str(folder))["why"]
    install_d1(kernel, clock, folder)
    other = d1_values() | {"title": "Another study"}
    write_flow(kernel, other, name="another")
    assert flows.view(str(folder))["flow"] == FLOW, "the active run's flow"
    run = d1_run()
    run.status, run.ended = "done", at(12, 40)
    write_run(flows.runner.runs, run)
    later = d1_run().model_copy(update={"flow": f"{WORKSPACE}/another", "status": "done", "created": at(12, 39)})
    write_run(flows.runner.runs, later)
    assert flows.view(str(folder))["flow"] == FLOW, "none active: the one run last"
    assert flows.view(str(folder), f"{WORKSPACE}/another")["title"] == "Another study", "the flow named"
    assert flows.view(str(folder), f"{WORKSPACE}/another")["run"]["status"] == "done"


def test_a_flow_not_run_yet_shows_every_box_waiting(kernel: Kernel, clock: FakeClock, folder: Path) -> None:
    folder.mkdir(parents=True)
    kernel.settings.write("workspace", WORKSPACE, {"path": str(folder)}, base=None, actor=OWNER)
    write_flow(kernel, d1_values())
    shown = kernel.parts["flows"].view(str(folder))
    assert shown["run"] is None
    assert {each["state"] for each in shown["boxes"]} == {"waiting"}
    assert {each["state"] for each in shown["lines"]} == {"not yet"}
    assert [each["box"] for each in shown["ahead"]][:2] == ["brief", "plan"]


def test_the_view_is_pure_and_its_version_moves_only_with_what_it_shows(d1: dict[str, Any]) -> None:
    made = d1_flow()
    once = view(FLOW, made, d1_run(), [], running="", titles={}, brief="", present=lambda path: False, ended={})
    again = view(FLOW, made, d1_run(), [], running="", titles={}, brief="", present=lambda path: False, ended={})
    assert once == again
    moved = d1_run()
    moved.boxes["T2"].tries[0].tokens = 9_000
    changed = view(FLOW, made, moved, [], running="", titles={}, brief="", present=lambda path: False, ended={})
    assert changed["version"] != once["version"]


def test_the_routes_give_the_view_and_the_run_log_oldest_first(
    d1: dict[str, Any], kernel: Kernel, folder: Path
) -> None:
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        shown = http.get("/api/v1/flows/view", headers=AUTH, params={"folder": str(folder)}).json()
        assert shown["flow"] == FLOW
        assert shown["version"] == d1["version"]
        log = http.get(f"/api/v1/flows/{WORKSPACE}/study/log", headers=AUTH).json()
    assert log["run"] == 1
    assert log["flow"] == FLOW
    times = [each["time"] for each in log["events"]]
    assert times == sorted(times)
    assert times[0] == "2026-10-20T12:02:00.000Z"
    assert log["events"][-1]["type"] == "flows.box_started"
    assert log["events"][-1]["box"] == "T2"
    assert NOW.isoformat().startswith("2026-10-20T12:41")


def test_the_next_flow_is_said_once_made_else_where_its_brief_will_come_from(
    kernel: Kernel, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    flows = kernel.parts["flows"]
    assert flows.view(str(folder))["next_flow"] == {"id": "", "title": "", "from": "join"}, "made when approved"
    write_flow(kernel, d1_values() | {"title": "Run the study"}, name="study-2")
    write_flow(kernel, d1_values() | {"next": f"{WORKSPACE}/study-2"})
    shown = flows.view(str(folder), FLOW)
    assert shown["next_flow"] == {"id": f"{WORKSPACE}/study-2", "title": "Run the study", "from": ""}
    write_flow(kernel, d1_values() | {"next_flow": "off"})
    assert flows.view(str(folder), FLOW)["next_flow"] is None, "a flow whose next flow is off shows none"


def test_ahead_says_each_switch_of_the_main_slot_and_how_long_its_preset_last_took_to_come_in(
    kernel: Kernel, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_d1(kernel, clock, folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=OWNER, preset="daily-262k")
    values = d1_values()
    for each in values["boxes"]:
        if each["id"] == "T3":
            each["model"] = "frontier 262K"
    write_flow(kernel, values)
    flows = kernel.parts["flows"]
    took = {"frontier-262k": 25.0, "daily-262k": 19.5}
    switches = flows.switches

    def timed(made: Any) -> dict[str, Any]:
        found = switches(made)
        return {**found, "switches": [{**each, "seconds": took.get(each["preset"])} for each in found["switches"]]}

    monkeypatch.setattr(flows, "switches", timed)
    ahead = {each["box"]: each["costs"] for each in flows.view(str(folder))["ahead"]}
    assert ahead["T3"] == ["a switch to frontier 262K, which last took 25 s here", "a fresh prompt"]
    assert ahead["T4"] == ["a switch to daily 262K, which last took 20 s here", "a fresh prompt"]
    assert ahead["join"] == ["a fresh prompt"], "the slot runs daily 262K again by then"


def test_a_brief_that_is_a_link_out_of_the_folder_is_not_read(
    kernel: Kernel, clock: FakeClock, folder: Path, tmp_path: Path
) -> None:
    install_d1(kernel, clock, folder)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("- a line from outside the folder\n", encoding="utf-8")
    (folder / "BRIEF.md").unlink()
    try:
        (folder / "BRIEF.md").symlink_to(elsewhere)
    except OSError:
        pytest.skip("this machine makes no symbolic links for its user")
    lines = [each["line"] for each in kernel.parts["flows"].view(str(folder))["brief"]["lines"]]
    assert "a line from outside the folder" not in lines, "the folder's files only, as the phone reads them"


def test_a_try_that_rewrites_a_file_with_the_same_bytes_is_said_to_have_written_it_as_the_runner_counts_it() -> None:
    from clank.components.flows.runs import Kept

    run = d1_run()
    plan = run.boxes["plan"]
    same = "a" * 64
    plan.tries[1].before = [Kept(path="PLAN.md", sha256=same, size=400, modified=1)]
    plan.tries[1].deliverables = [Kept(path="PLAN.md", sha256=same, size=400, modified=2, copied=True)]
    shown = view(FLOW, d1_flow(), run, [], running="", titles={}, brief="", present=lambda path: True, ended={})
    tries = box(shown, "plan")["tries"]
    assert tries[1]["written"] == ["PLAN.md"], "written again during try 2, though its bytes are the same"
    assert next(each for each in shown["deliverables"] if each["path"] == "PLAN.md")["try"] == 2
    plan.tries[1].deliverables = [Kept(path="PLAN.md", sha256=same, size=400, modified=1, copied=True)]
    untouched = view(FLOW, d1_flow(), run, [], running="", titles={}, brief="", present=lambda path: True, ended={})
    assert box(untouched, "plan")["tries"][1]["written"] == [], "left as it was: not written by try 2"


def test_how_long_each_preset_took_is_read_once_and_again_only_when_an_operation_has_finished(
    d1: dict[str, Any], kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flows = kernel.parts["flows"]
    find = kernel.operations.find
    asked: list[str | None] = []

    def counted(status: str | None = None, limit: int = 50) -> Any:
        asked.append(status)
        return find(status, limit)

    monkeypatch.setattr(kernel.operations, "find", counted)
    flows.view(str(folder))
    flows.view(str(folder))
    flows.view(str(folder))
    assert len(asked) <= 1, "read once a second while the view is on screen, the operations are asked once"
    asked.clear()
    kernel.events.record("operation.finished", summary="a switch ended", actor=OWNER, data={"type": "runtime.switch"})
    flows.view(str(folder))
    assert len(asked) == 1, "an operation finished: what a switch takes is read again"


def test_a_folders_monitor_shows_the_flow_running_before_one_queued_behind_it(
    kernel: Kernel, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    write_flow(kernel, d1_values() | {"title": "A study queued"}, name="another")
    flows = kernel.parts["flows"]
    queued = d1_run().model_copy(update={"flow": f"{WORKSPACE}/another", "status": "queued", "behind": f"{FLOW}#1"})
    write_run(flows.runner.runs, queued)
    assert flows.view(str(folder))["flow"] == FLOW, "the running one, though the queued one's name comes first"


def test_a_flow_named_without_its_workspace_is_refused_saying_how_to_name_it(
    d1: dict[str, Any], kernel: Kernel
) -> None:
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        answer = http.get("/api/v1/flows/view", headers=AUTH, params={"flow": "study"})
        unknown = http.get("/api/v1/flows/view", headers=AUTH, params={"flow": f"{WORKSPACE}/none"})
    assert answer.status_code == 400, answer.text
    assert "myproject/study" in answer.text or "<workspace>/<name>" in answer.text
    assert unknown.status_code == 404


def directory_link(link: Path, target: Path) -> None:
    """A link to a folder: a junction on Windows (which every user may make), a symbolic link elsewhere."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_a_brief_in_a_folder_linked_out_of_the_workspaces_folder_is_not_read(
    kernel: Kernel, clock: FakeClock, folder: Path, tmp_path: Path
) -> None:
    install_d1(kernel, clock, folder)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "BRIEF.md").write_text("- a line from outside the folder\n", encoding="utf-8")
    directory_link(folder / "linked", elsewhere)
    values = d1_values()
    values["boxes"][0]["writes"] = ["linked/BRIEF.md"]
    write_flow(kernel, values)
    lines = [each["line"] for each in kernel.parts["flows"].view(str(folder))["brief"]["lines"]]
    assert "a line from outside the folder" not in lines, "a junction or a link out of the folder is not followed"
