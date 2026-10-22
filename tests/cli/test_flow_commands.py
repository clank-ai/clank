"""Design 0013 §3, §5, §6, §7, §8, §9, §11 and §16: the `clank flow` commands (list, show, check, prepare, run, pause,
stop, diff, proposals, accept, reject, next and orchestrator), clients of the API, for scripts and as the Flow view's
backup: `orchestrator` says a flow's orchestrator's settings and turns it on or off in the flow's file; `list` shows
each flow with its workspace, title and boxes, and where flows are kept and Clank's template when there are none; `show`
names each box with its type, title, files and what comes after it, the workspace being the current folder's, and the
switches of the main slot a run makes (each preset with how long its last whole switch took, else its engine's last
start), `check` how many; `check` says a good flow keeps every rule, and prints each problem of a broken one with its
file, line and field, ending with a failure; `run`, `pause` and `stop` say what they did and where the run is, each box
with its state; `diff` compares two tries of a box, saying how many lines changed, then the diff; `proposals` lists the
run's proposals with their states (`--full`: each whole), `accept` (with `--prompt`, an edit first) and `reject` decide
them by their ids or all, saying what they did; `prepare` lists each box's first message size against its model's
window, saying how each was counted, or shows one box's message whole; `next` shows the flow made after this one, or why
there is none, and makes (`--make`) or runs (`--run`) it; `--json` prints what the API answers.

Design 0013 §15: `new` opens a planning, a flow built with the model: here, OpenCode runs in this terminal on its
session and, once it ends, the command says whether the flow was built and how to look at it and run it; `--vscode`
opens Clank's VS Code window, as does a command run in VS Code's terminal; over SSH it opens here whatever asked,
saying why; a planning open in the workspace is set aside only with `--set-aside`, else refused saying so. `attach`
runs OpenCode in this terminal on the workspace's open planning, saying what the one-window rule closed and naming
the session, and once OpenCode ends whether the flow was built, through the service's own answer too; with none open
it says how to open one; `--home` names Clank's home."""

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.flows import cli as flow_cli
from clank.components.flows.first import instructions
from clank.components.flows.kinds import Box, Flow
from clank.components.flows.proposals import Batch, Batches, Proposal
from clank.components.flows.runs import BoxRun, Kept, Run, Runs, Try
from clank.components.flows.verdicts import AGENT
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

D1 = Path(__file__).resolve().parents[1] / "components" / "flows" / "d1-flow.json"


def d1() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(D1.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "myproject"
    (folder / "runs").mkdir(parents=True)
    monkeypatch.chdir(folder / "runs")
    return folder


def open_on(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 19, 1, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


@pytest.fixture
def kernel(home: Home, project: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    workspace = home.config / "workspaces" / "myproject.json"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.write_text(json.dumps({"schema": "workspace/1", "path": str(project)}), encoding="utf-8")
    flow = home.config / "flows" / "myproject" / "new-study.json"
    flow.parent.mkdir(parents=True)
    flow.write_bytes(D1.read_bytes())
    yield from open_on(home, monkeypatch)


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, ["flow", *arguments])


def test_orchestrator_says_its_settings_and_turns_it_on_and_off_in_the_flows_file(kernel: Kernel, home: Home) -> None:
    shown = run("orchestrator", "new-study")
    assert shown.exit_code == 0, shown.output
    assert "The orchestrator of A new simulation study (myproject/new-study) is off" in shown.output
    on = run("orchestrator", "new-study", "on", "--final", "owner")
    assert on.exit_code == 0, on.output
    assert "is on: the last gate is yours; 12 changes a run, 2 extra tries a box, stall at 3" in on.output
    saved = json.loads((home.config / "flows" / "myproject" / "new-study.json").read_text(encoding="utf-8"))
    assert (saved["orchestrator"]["on"], saved["orchestrator"]["final_review"]) == (True, "owner")
    off = run("orchestrator", "new-study", "off")
    assert off.exit_code == 0, off.output
    assert "is off" in off.output


def test_list_shows_each_flow_with_its_workspace_title_and_boxes(kernel: Kernel) -> None:
    listed = run("list")
    assert listed.exit_code == 0, listed.output
    assert "myproject/new-study" in listed.output
    assert "A new simulation study" in listed.output
    assert "11 boxes" in listed.output


def test_list_says_where_flows_are_kept_and_where_the_template_is_when_there_are_none(
    home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in open_on(home, monkeypatch):
        listed = run("list")
        assert listed.exit_code == 0, listed.output
        assert "No flows yet" in listed.output
        assert str(home.config / "flows") in listed.output
        assert "flow.json" in listed.output


def test_show_names_each_box_with_its_type_title_files_and_what_comes_after_it(kernel: Kernel) -> None:
    shown = run("show", "new-study")
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert lines[0].startswith("A new simulation study (myproject/new-study")
    check = next(line for line in lines if line.lstrip().startswith("check "))
    assert "VERIFY" in check
    assert "Check the plan" in check
    assert "checks plan" in check
    assert "pass: approve" in check
    assert "fail: back to plan" in check
    split = next(line for line in lines if line.lstrip().startswith("split "))
    assert "then T1, T2, T3, T4, one after another" in split
    t2 = next(line for line in lines if line.lstrip().startswith("T2 "))
    assert "writes runs/estimates.md" in t2
    assert "mode auto" in t2
    assert t2.endswith("then T3"), "DECOMPOSE's tasks run one after another"
    assert next(line for line in lines if line.lstrip().startswith("T4 ")).endswith("then join")
    assert "daily 262K" in shown.output


def test_show_and_check_say_the_switches_a_run_makes_before_it_runs(kernel: Kernel, home: Home) -> None:
    """Design 0013 §7 and decision 0063: the switches' cost shown before the flow runs."""
    flow = d1()
    next(box for box in flow["boxes"] if box["id"] == "T3")["model"] = "frontier-96k"
    (home.config / "flows" / "myproject" / "new-study.json").write_text(json.dumps(flow, indent=2), encoding="utf-8")
    kernel.settings.reload_changed()
    state = kernel.parts["runtime"].state
    launch = state.add_launch(slot="main", preset="daily-262k", options={}, engine="kvmem-llamacpp",
                              engine_version="v0.16.0-rc1", host="local", command_line="kvmem", log="")  # fmt: skip
    state.finish_launch(launch, "ready", seconds=21.4)

    shown = run("show", "new-study")
    assert shown.exit_code == 0, shown.output
    assert (
        "A run switches the main slot 3 times, from what it runs now (nothing): before plan, to daily 262K (its "
        "engine last started here in 21 s); before T3, to frontier 96K (not loaded here yet); before T4, to daily "
        "262K (its engine last started here in 21 s)."
    ) in " ".join(shown.output.split()), "no whole switch of it kept: its engine's start to ready"
    checked = run("check", "myproject/new-study")
    assert "the flow keeps every rule; a run switches the main slot 3 times (clank flow show says where)." in (
        " ".join(checked.output.split())
    )
    found = json.loads(run("show", "new-study", "--json").output)
    assert [(each["box"], each["preset"]) for each in found["switches"]] == [
        ("plan", "daily-262k"), ("T3", "frontier-96k"), ("T4", "daily-262k"),
    ]  # fmt: skip


def test_show_says_how_long_a_presets_last_whole_switch_took_when_one_is_kept(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0013 §7: the whole switch, from the operation's start to its end, is what a switch costs."""
    planned = [{"box": "plan", "preset": "daily-262k", "title": "daily 262K", "seconds": 24.6, "whole": True}]
    switches = {"running": "", "running_title": "", "switches": planned}
    monkeypatch.setattr(kernel.parts["flows"], "switches", lambda flow: switches)
    shown = run("show", "new-study")
    assert "before plan, to daily 262K (its last switch here took 25 s)." in " ".join(shown.output.split())


def test_check_of_a_good_flow_says_it_keeps_every_rule(kernel: Kernel) -> None:
    checked = run("check", "myproject/new-study")
    assert checked.exit_code == 0, checked.output
    assert "keeps every rule" in checked.output


def test_check_warns_of_a_file_a_box_sees_that_nothing_gives_it_and_does_not_fail(
    kernel: Kernel, project: Path
) -> None:
    warned = d1()
    warned["boxes"][5]["sees"] = ["PLAN.md", "notes/missing.md"]
    draft = project / "draft.json"
    draft.write_text(json.dumps(warned, indent=2), encoding="utf-8")
    checked = run("check", str(draft))
    assert checked.exit_code == 0, checked.output
    lines = checked.output.splitlines()
    assert lines[0] == (
        f"{draft}: the flow keeps every rule; a run switches the main slot 1 time (clank flow show says where)."
    )
    assert lines[1].startswith(f"warning: {draft}, line ")
    assert lines[1].endswith(
        ", boxes.5.sees.1: T1 sees notes/missing.md, which is not in the folder, and neither T1 nor a box before it "
        "writes it"
    )


def test_check_of_a_broken_file_prints_each_problem_with_its_file_line_and_field_and_fails(
    kernel: Kernel, project: Path
) -> None:
    broken = d1()
    broken["boxes"][6]["model"] = "fast 8K"
    broken["lines"].append({"from": "approve", "to": "plan"})
    draft = project / "draft.json"
    draft.write_text(json.dumps(broken, indent=2), encoding="utf-8")
    checked = run("check", str(draft))
    assert checked.exit_code == 1, checked.output
    assert f"{draft}, line 227, lines.14.to: leads back to plan" in checked.output
    broken["lines"].pop()
    draft.write_text(json.dumps(broken, indent=2), encoding="utf-8")
    checked = run("check", str(draft))
    assert checked.exit_code == 1, checked.output
    assert "boxes.6.model: names the preset 'fast 8K'" in checked.output


def test_json_prints_what_the_api_answers(kernel: Kernel) -> None:
    listed = json.loads(run("list", "--json").output)
    assert [flow["id"] for flow in listed["flows"]] == ["myproject/new-study"]
    shown = json.loads(run("show", "new-study", "--json").output)
    assert shown["values"]["boxes"][0]["id"] == "brief"
    checked = json.loads(run("check", "new-study", "--json").output)
    assert checked == {"file": shown["file"], "flow": "myproject/new-study", "problems": [], "warnings": [],
                       "running": "", "running_title": "", "switches": shown["switches"]}  # fmt: skip


def test_a_flow_named_outside_a_workspaces_folder_needs_its_workspace(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    shown = run("show", "new-study")
    assert shown.exit_code == 1
    assert "--workspace" in shown.output
    assert run("show", "new-study", "--workspace", "myproject").exit_code == 0


def test_run_pause_and_stop_say_what_they_did_and_where_the_run_is(kernel: Kernel) -> None:
    started = run("run", "new-study")
    assert started.exit_code == 0, started.output
    lines = started.output.splitlines()
    assert lines[0] == "Started A new simulation study (myproject/new-study#1)."
    brief = next(line for line in lines if line.lstrip().startswith("brief "))
    assert "YOU" in brief
    assert brief.rstrip().endswith("<- here")
    assert any(line.lstrip().startswith("T4 ") for line in lines), "every box, in the order they run"
    refused = run("run", "new-study")
    assert refused.exit_code == 1
    assert "already runs" in refused.output
    paused = run("pause", "new-study")
    assert paused.exit_code == 0, paused.output
    assert paused.output.startswith("Paused A new simulation study (myproject/new-study#1): no box starts")
    assert run("run", "new-study").output.startswith("Resumed A new simulation study")
    stopped = run("stop", "new-study")
    assert stopped.output.startswith("Stopped A new simulation study (myproject/new-study#1).")
    again = run("run", "new-study", "--from", "plan")
    assert again.exit_code == 0, again.output
    assert again.output.startswith("A new simulation study (myproject/new-study#1) runs again from plan.")
    assert json.loads(run("pause", "myproject/new-study", "--json").output)["run"]["paused"] is True


def two_tries(kernel: Kernel) -> None:
    """A run of the flow in which the plan ran twice, each try's PLAN.md copied into its folder."""
    runs = Runs(kernel.home)
    now = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
    texts = {1: "# The plan\n\n240 points.\nNo budget.\n", 2: "# The plan\n\n64 points.\nNo budget.\nSeeds 1-8.\n"}
    tries = [
        Try(number=number, started=now, outcome="done",
            deliverables=[Kept(path="PLAN.md", sha256=f"{number}" * 64, size=len(text), copied=True)])
        for number, text in texts.items()
    ]  # fmt: skip
    run = Run(
        flow="myproject/new-study", number=1, title="A new simulation study", workspace="myproject", version="r1",
        status="done", at="review", started_by=Actor(kind="user", via="cli"), created=now,
        boxes={"plan": BoxRun(state="done", tries=tries)},
    )  # fmt: skip
    runs.save(run)
    for number, text in texts.items():
        copy = runs.try_folder(run, "plan", number) / "deliverables" / "PLAN.md"
        copy.parent.mkdir(parents=True)
        copy.write_text(text, encoding="utf-8")


def test_diff_compares_two_tries_of_a_box_saying_how_many_lines_changed_then_the_diff(kernel: Kernel) -> None:
    two_tries(kernel)
    shown = run("diff", "new-study", "plan")
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert lines[0] == "PLAN.md of plan, try 2 against try 1 (myproject/new-study#1): changed since try 1: 2 lines."
    assert "--- PLAN.md (try 1)" in lines
    assert "-240 points." in lines
    assert "+Seeds 1-8." in lines
    assert json.loads(run("diff", "new-study", "plan", "--tries", "2", "1", "--json").output)["a"] == 2
    refused = run("diff", "new-study", "brief")
    assert refused.exit_code == 1
    assert "nothing to compare" in refused.output


def proposed(kernel: Kernel) -> None:
    """A run of the flow in which T2, at work, proposed two more tasks after itself and submitted them."""
    runs = Runs(kernel.home)
    now = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
    run = Run(
        flow="myproject/new-study", number=1, title="A new simulation study", workspace="myproject", version="r1",
        status="running", at="T2", started_by=Actor(kind="user", via="cli"), created=now,
        boxes={"T2": BoxRun(state="running", tries=[Try(number=1, started=now)])},
    )  # fmt: skip
    runs.save(run)
    made = [
        Proposal(id=f"T{number}", number=number - 4, after="T2", why="Leftovers of the estimates.", given=now,
                 by=AGENT, box=Box(id=f"T{number}", type="task", title=title, prompt=f"{title}, in out/t{number}.md.",
                                   writes=[f"out/t{number}.md"]))
        for number, title in ((5, "The cleanup"), (6, "The second cleanup"))
    ]  # fmt: skip
    batch = Batch(flow=run.flow, run=1, box="T2", attempt=1, summary="Two more tasks.", submitted=now, proposals=made)
    Batches(runs).save(batch)


def boxes_of(kernel: Kernel) -> list[Box]:
    record = kernel.settings.get("flow", "myproject/new-study").record
    assert isinstance(record, Flow)
    return record.boxes


def test_proposals_lists_each_proposal_with_its_state_and_full_shows_each_whole(kernel: Kernel) -> None:
    empty = run("proposals", "new-study")
    assert empty.exit_code == 0, empty.output
    assert empty.output.strip() == "A new simulation study has not run yet: it has no proposals."
    proposed(kernel)
    shown = run("proposals", "new-study")
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert lines[0] == "Proposals of A new simulation study (myproject/new-study#1):"
    assert "From T2, try 1, submitted: Two more tasks." in lines
    row = next(line for line in lines if line.lstrip().startswith("1  T5"))
    assert row.split() == ["1", "T5", "TASK", "The", "cleanup", "after", "T2", "proposed", "writes", "out/t5.md"]
    assert lines[-1].startswith("Waiting for you: T5, T6.")
    full = run("proposals", "new-study", "--full")
    assert "The cleanup, in out/t5.md." in full.output
    assert "why: Leftovers of the estimates." in full.output
    assert json.loads(run("proposals", "new-study", "--json").output)["waiting"] == ["T5", "T6"]


def test_accept_with_a_prompt_edits_it_first_and_reject_and_accept_say_what_they_did(kernel: Kernel) -> None:
    proposed(kernel)
    unnamed = run("accept", "new-study")
    assert unnamed.exit_code == 1
    assert "Name the proposals to accept (T1 T2), or --all." in unnamed.output
    edited = run("accept", "new-study", "T5", "--prompt", "Clean the runs, keeping the logs.")
    assert edited.exit_code == 0, edited.output
    assert edited.output.strip() == "Accepted T5, edited: it joins A new simulation study's flow."
    ids = [box.id for box in boxes_of(kernel)]
    assert ids[ids.index("T2") + 1] == "T5", "right after the box it was proposed after"
    assert next(box for box in boxes_of(kernel) if box.id == "T5").prompt == "Clean the runs, keeping the logs."
    rejected = run("reject", "new-study", "--all")
    assert rejected.exit_code == 0, rejected.output
    assert rejected.output.strip() == "Rejected T6."
    nothing = run("accept", "new-study", "--all")
    assert nothing.exit_code == 1
    assert "no proposal of A new simulation study's run 1 waits for you" in nothing.output
    both = run("accept", "new-study", "T5", "T6", "--title", "Both")
    assert both.exit_code == 1
    assert "an edit names one proposal" in both.output


def test_prepare_lists_each_boxs_first_message_size_against_its_window_or_shows_one_whole(
    kernel: Kernel, project: Path
) -> None:
    (project / "BRIEF.md").write_bytes(b"About 60 grid points, at most 48 CPU-hours.\n")
    listed = run("prepare", "new-study")
    assert listed.exit_code == 0, listed.output
    lines = listed.output.splitlines()
    assert lines[0] == (
        "A new simulation study (myproject/new-study): each box's first message as it would be sent now, from the "
        "files as they are now."
    )
    rows = [line for line in lines if line.startswith("  ")]
    assert [row.split()[0] for row in rows] == ["plan", "check", "split", "T1", "T2", "T3", "T4", "join"]
    plan = rows[0].split()
    assert plan[1:4] == ["PLAN", "try", "1"]
    assert rows[0].endswith("of 262,144 (daily 262K)")
    assert "tokens, an estimate" in rows[0]
    counted = lines.index("How each was counted:")
    assert lines[counted + 1].startswith(
        "- plan, check, split, T1, T2, T3, T4, join: an estimate: 0.3 tokens per character, Clank's plain default"
    )
    assert "OpenCode adds its own instructions and tool definitions" in listed.output
    assert lines[-1] == "`clank flow prepare new-study <box>` shows a box's first message whole."

    one = run("prepare", "new-study", "T1")
    assert one.exit_code == 0, one.output
    assert one.output.startswith(instructions("task"))
    assert "### BRIEF.md (from brief)" in one.output
    size = next(line for line in one.output.splitlines() if line.startswith("T1 (TASK), try 1: "))
    assert "tokens (an estimate: 0.3 tokens per character" in size
    assert size.endswith("of 262,144 (daily 262K).")
    shown = json.loads(run("prepare", "new-study", "T1", "--json").output)
    assert [each["box"] for each in shown["boxes"]] == ["T1"]
    owners = run("prepare", "new-study", "approve")
    assert owners.exit_code == 1
    assert "approve is a GATE, done by you: it has no first message" in owners.output


def approved(kernel: Kernel, project: Path) -> None:
    """A run of the flow that ended done, its last gate approved, its INTEGRATE's brief in the folder."""
    now = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
    done = [Try(number=1, started=now, outcome="done")]
    run = Run(
        flow="myproject/new-study", number=1, title="A new simulation study", workspace="myproject", version="r1",
        status="done", at="review", started_by=Actor(kind="user", via="cli"), created=now,
        boxes={name: BoxRun(state="done", tries=done) for name in ("brief", "plan", "join", "review")},
    )  # fmt: skip
    Runs(kernel.home).save(run)
    (project / "NEXT.md").write_bytes(b"# Run the study\n\nThe grid's 60 points.\n")


def test_next_shows_the_next_flow_or_why_there_is_none_and_makes_or_runs_it(kernel: Kernel, project: Path) -> None:
    none = run("next", "new-study")
    assert none.exit_code == 0, none.output
    assert none.output.strip() == (
        "A new simulation study (myproject/new-study) has no next flow: its last gate, review, has not been approved "
        "in a run yet."
    )
    approved(kernel, project)
    assert "none was made: `clank flow next myproject/new-study --make` makes it from NEXT.md, which join wrote" in (
        run("next", "new-study").output
    )
    made = run("next", "new-study", "--make")
    assert made.exit_code == 0, made.output
    assert made.output.splitlines() == [
        "A new simulation study (myproject/new-study) is followed by Run the study (myproject/new-study-2), from "
        "NEXT.md, which join wrote in run 1.",
        "It has not run yet; a question asks whether to run it now, or `clank flow next new-study --run`.",
    ]
    again = run("next", "new-study", "--make")
    assert again.exit_code == 1
    assert "myproject/new-study's next flow is myproject/new-study-2 already" in again.output
    started = run("next", "new-study", "--run")
    assert started.exit_code == 0, started.output
    assert started.output.startswith("Started Run the study (myproject/new-study-2)")
    shown = json.loads(run("next", "new-study", "--json").output)
    assert (shown["next"]["id"], shown["next"]["runs"], shown["waiting"]) == ("myproject/new-study-2", 1, "")


@pytest.fixture
def owner_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The terminal the command runs in is neither VS Code's nor reached over SSH, unless a test says so."""
    for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "TERM_PROGRAM"):
        monkeypatch.delenv(name, raising=False)


def planning_opened(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, project: Path) -> list[dict[str, Any]]:
    """The service's planning opened as it would be, the window's command made up (no container runs): each opening's
    arguments, kept."""
    building = kernel.parts["flows"].building
    opened: list[dict[str, Any]] = []

    def opening(workspace: str, name: str, where: str, *, actor: Actor, aside: bool = False) -> dict[str, Any]:
        planning = building.begin(workspace, name, where, actor=actor, aside=aside)
        opened.append({"workspace": workspace, "name": name, "where": where})
        said = {"flow": planning.flow, "name": planning.name, "where": where, "folder": str(project),
                "first_message": "first-message.md", "title": f"{planning.name} · building the flow"}  # fmt: skip
        if where == "here":
            argv = ["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4096"]
            return {**said, "window": "started", "argv": argv, "program": "OpenCode", "port": 4096,
                    "model": "frontier 262K", "notes": []}  # fmt: skip
        return {**said, "window": "waits", "port": None}

    monkeypatch.setattr(building, "open", opening)
    return opened


def test_flow_new_opens_opencode_here_and_says_the_flow_was_built_and_how_to_look_and_run_it(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    opened = planning_opened(kernel, monkeypatch, project)
    ran: list[list[str]] = []

    def talked(argv: list[str]) -> int:
        ran.append(list(argv))
        kernel.parts["flows"].building._change("myproject/study-2", status="built")  # the model's draft, written
        return 0

    monkeypatch.setattr(flow_cli, "terminal", talked)
    result = run("new", "study-2")
    assert result.exit_code == 0, result.output
    assert opened == [{"workspace": "myproject", "name": "study-2", "where": "here"}]
    assert ran == [["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4096"]]
    assert "OpenCode opens here on the planning session" in result.output
    named = result.output.index("“study-2 · building the flow”")
    assert named < result.output.index("flow built: look"), "named before OpenCode opens, to pick it if not shown"
    assert "pick it from OpenCode's session list (/sessions)" in result.output
    assert "flow built: look, then r to run" in result.output
    assert "clank console --page monitor --view flow" in result.output
    assert "clank flow run myproject/study-2" in result.output


def test_flow_new_says_when_the_flow_was_not_built_and_why_its_session_failed(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    planning_opened(kernel, monkeypatch, project)
    monkeypatch.setattr(flow_cli, "terminal", lambda argv: 0)
    result = run("new")
    assert result.exit_code == 0, result.output
    assert "myproject/flow is not built yet" in result.output

    def failed(argv: list[str]) -> int:
        kernel.parts["flows"].building._failed("myproject/flow-2", "no OpenCode window answered on port 4096")
        return 0

    monkeypatch.setattr(flow_cli, "terminal", failed)
    refused = run("new", "flow-2")  # myproject/flow is still open: never overwritten, set aside only when told
    assert refused.exit_code == 1
    assert "a planning is open in myproject: myproject/flow (waiting)" in refused.output
    assert "clank flow new --set-aside" in refused.output
    result = run("new", "flow-2", "--set-aside")
    assert "its planning session did not start: no OpenCode window answered on port 4096" in result.output


def test_flow_new_in_vs_code_opens_clanks_vs_code_window_and_in_vs_codes_terminal_unasked(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    opened = planning_opened(kernel, monkeypatch, project)
    windows: list[str] = []
    monkeypatch.setattr(flow_cli, "open_vscode", lambda client, folder: windows.append(folder))
    monkeypatch.setattr(flow_cli, "terminal", lambda argv: pytest.fail("nothing runs in this terminal"))
    result = run("new", "--vscode")
    assert result.exit_code == 0, result.output
    assert windows == [str(project)]
    assert "Clank's VS Code window" in result.output
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    assert run("new", "other", "--set-aside").exit_code == 0
    assert [each["where"] for each in opened] == ["vscode", "vscode"]


def test_over_ssh_flow_new_opens_in_this_terminal_whatever_asked_and_says_why(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    opened = planning_opened(kernel, monkeypatch, project)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    monkeypatch.setattr(flow_cli, "open_vscode", lambda client, folder: pytest.fail("no window on the PC's screen"))
    ran: list[list[str]] = []

    def here(argv: list[str]) -> int:
        ran.append(list(argv))
        return 0

    monkeypatch.setattr(flow_cli, "terminal", here)
    result = run("new", "--vscode")
    assert result.exit_code == 0, result.output
    assert [each["where"] for each in opened] == ["here"]
    assert len(ran) == 1
    assert "over SSH, the planning opens here" in result.output


def attaching(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, closed: int = 0) -> list[str]:
    """The service's attach as it would answer (no container runs): the workspaces it was asked for, kept."""
    building = kernel.parts["flows"].building
    asked: list[str] = []

    def attach(workspace: str, *, actor: Actor) -> dict[str, Any]:
        asked.append(workspace)
        planning = building.open_in(workspace)
        if planning is None:
            from clank.components.flows.building import BuildError

            raise BuildError(f"no planning is open in {workspace}: n on the console's Flow view, or `clank flow new`")
        notes = [f"closed the OpenCode window open in {workspace} first: one at a time"] if closed else []
        argv = ["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4097"]
        return {"flow": planning.flow, "name": planning.name, "title": f"{planning.name} · building the flow",
                "status": planning.status, "argv": argv, "program": "OpenCode", "port": 4097,
                "model": "frontier 262K", "notes": notes, "closed": closed, "one_window": True}  # fmt: skip

    monkeypatch.setattr(building, "attach", attach)
    return asked


def test_flow_attach_runs_opencode_here_on_the_open_planning_and_says_what_the_one_window_rule_closed(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    kernel.parts["flows"].building.begin("myproject", "", "attach", actor=Actor(kind="user", via="console"))
    asked = attaching(kernel, monkeypatch, closed=1)
    ran: list[list[str]] = []

    def talked(argv: list[str]) -> int:
        ran.append(list(argv))
        kernel.parts["flows"].building._change("myproject/flow", status="built")
        return 0

    monkeypatch.setattr(flow_cli, "terminal", talked)
    result = run("attach")
    assert result.exit_code == 0, result.output
    assert asked == ["myproject"]
    assert ran == [["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4097"]]
    assert "closed the OpenCode window open in myproject first" in result.output
    assert "“flow · building the flow”" in result.output
    assert "flow built: look, then r to run" in result.output


def test_flow_attach_runs_the_command_of_the_services_own_answer(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    kernel.parts["flows"].building.begin("myproject", "", "attach", actor=Actor(kind="user", via="console"))
    argv = ["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4098"]
    prepared = {"workspace": "myproject", "container": "clank-myproject", "program": "OpenCode",
                "model": "frontier 262K", "limits": {}, "servers": [], "port": 4098, "argv": argv,
                "one_window": True, "closed": 0, "notes": []}  # fmt: skip
    monkeypatch.setattr(kernel.parts["agents"], "prepare", lambda workspace: dict(prepared))  # no container runs
    monkeypatch.setattr(kernel.parts["workspaces"], "runs_current_image", lambda workspace: True)
    ran: list[list[str]] = []

    def talked(given: list[str]) -> int:
        ran.append(list(given))
        return 0

    monkeypatch.setattr(flow_cli, "terminal", talked)
    result = run("attach")
    assert result.exit_code == 0, result.output
    assert ran == [argv]
    assert "“flow · building the flow”" in result.output


def test_flow_attach_with_no_planning_open_says_how_to_open_one(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None
) -> None:
    attaching(kernel, monkeypatch)
    monkeypatch.setattr(flow_cli, "terminal", lambda argv: pytest.fail("nothing to attach to"))
    result = run("attach", "--workspace", "myproject")
    assert result.exit_code == 1
    assert "no planning is open in myproject" in result.output


def test_flow_attach_home_names_clanks_home_as_a_pane_of_windows_terminal_gives_it(
    kernel: Kernel, project: Path, monkeypatch: pytest.MonkeyPatch, owner_terminal: None, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLANK_HOME", "where it was")  # put back as it was once the test ends
    attaching(kernel, monkeypatch)
    result = run("attach", "--home", str(tmp_path / "home"))
    assert os.environ.get("CLANK_HOME") == str(tmp_path / "home"), "set before the service is reached"
    assert "no planning is open" in result.output
