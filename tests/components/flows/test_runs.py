"""Design 0013 §6 and §8 (decision 0061): a run of a flow is a readable JSON file in the run's folder, beside each try's
folder; runs of a flow are numbered from 1; the boxes run along their lines, a DECOMPOSE's tasks one after another in
the order of the boxes, and what comes after a box is every box later in that order. Design 0013 §10 and §14 step 7:
the phone and VS Code read the runs' files from their own threads while the runner writes them, and a write waits for
a read to end (Windows refuses to replace a file open for reading) rather than failing the box; a read waits for a
replace to end (Windows refuses for a moment to open a file being replaced) rather than taking the run for one that does
not read."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clank.components.flows.kinds import Flow
from clank.components.flows.runs import BoxRun, Run, Runs, Try, after, order
from clank.kernel.events import Actor
from clank.kernel.home import Home

D1 = Path(__file__).with_name("d1-flow.json")
OWNER = Actor(kind="user", via="console")
NOW = datetime(2026, 10, 19, 21, 0, tzinfo=UTC)


def d1() -> Flow:
    values: dict[str, Any] = json.loads(D1.read_text(encoding="utf-8"))
    values.pop("schema")
    return Flow.model_validate(values)


def a_run(number: int = 1) -> Run:
    return Run(
        flow="myproject/new-study",
        number=number,
        title="A new simulation study",
        workspace="myproject",
        version="a1b2c3d4e5f60718",
        status="running",
        at="plan",
        started_by=OWNER,
        created=NOW,
        boxes={
            "brief": BoxRun(state="done"),
            "plan": BoxRun(state="running", tries=[Try(number=1, started=NOW, session="ses_1", port=4097)]),
        },
    )


def test_a_run_is_a_readable_json_file_in_its_folder_read_back_the_same(home: Home) -> None:
    runs = Runs(home)
    run = a_run()
    path = runs.save(run)
    assert path == home.state / "flows" / "myproject" / "new-study" / "run-1" / "run.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["schema"] == "flow-run/1"
    assert (written["flow"], written["number"], written["status"], written["at"]) == (
        "myproject/new-study", 1, "running", "plan"
    )  # fmt: skip
    assert written["boxes"]["plan"]["tries"][0]["session"] == "ses_1"
    assert path.read_text(encoding="utf-8").startswith('{\n  "schema": "flow-run/1"'), "indented, the schema first"
    assert runs.load("myproject/new-study", 1) == run
    assert runs.save(runs.load("myproject/new-study", 1)).read_bytes() == path.read_bytes(), "written back unchanged"


def test_runs_of_a_flow_are_numbered_from_one_and_every_run_is_found(home: Home) -> None:
    runs = Runs(home)
    assert runs.next_number("myproject/new-study") == 1
    runs.save(a_run(1))
    runs.save(a_run(2))
    assert runs.next_number("myproject/new-study") == 3
    assert runs.next_number("myproject/other") == 1
    assert [(run.flow, run.number) for run in runs.all()] == [("myproject/new-study", 1), ("myproject/new-study", 2)]
    assert runs.latest("myproject/new-study") == runs.load("myproject/new-study", 2)
    assert runs.latest("myproject/other") is None


def test_a_file_that_does_not_read_as_a_run_is_left_out_and_said(home: Home) -> None:
    runs = Runs(home)
    runs.save(a_run(1))
    broken = home.state / "flows" / "myproject" / "new-study" / "run-2" / "run.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{not json", encoding="utf-8")
    assert [run.number for run in runs.all()] == [1]
    assert [str(path) for path, _ in runs.problems()] == [str(broken)]


def test_a_try_has_a_folder_of_its_own_under_its_box(home: Home) -> None:
    runs = Runs(home)
    folder = runs.try_folder(a_run(), "plan", 2)
    assert folder == home.state / "flows" / "myproject" / "new-study" / "run-1" / "plan" / "try-2"


def test_the_boxes_run_along_their_lines_and_a_decomposes_tasks_in_the_order_of_the_boxes() -> None:
    flow = d1()
    assert order(flow) == ["brief", "plan", "check", "approve", "split", "T1", "T2", "T3", "T4", "join", "review"]
    assert after(flow, "approve") == ["split", "T1", "T2", "T3", "T4", "join", "review"]
    assert after(flow, "T2") == ["T3", "T4", "join", "review"]
    assert after(flow, "review") == []


def test_a_runs_file_is_written_while_another_thread_reads_it(home: Home) -> None:
    runs = Runs(home)
    run = a_run()
    path = runs.save(run)
    reading = path.open("rb")
    let_go = threading.Timer(0.05, reading.close)
    let_go.start()
    try:
        run.at = "check"
        runs.save(run)
    finally:
        let_go.join()
        reading.close()
    assert runs.load(run.flow, 1).at == "check"


def test_a_runs_file_is_read_while_another_thread_replaces_it(home: Home) -> None:
    runs = Runs(home)
    run = a_run()
    runs.save(run)
    done = threading.Event()

    def write() -> None:
        while not done.is_set():
            run.at = "check" if run.at != "check" else "plan"
            runs.save(run)

    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    try:
        for _ in range(600):  # a read while the file is replaced is refused for a moment on Windows
            assert runs.load(run.flow, 1).at in ("check", "plan")
            assert [each.number for each in runs.all()] == [1]
            assert runs.latest(run.flow) is not None
    finally:
        done.set()
        writer.join()
