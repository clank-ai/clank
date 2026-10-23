"""Design 0013 §17 (decision 0132): the Flow view shows a box's job and the run's side work. A box waiting on its job
says so on its tag line (`job 1`); Selected says the job (its title, how long it has run of its minutes, or how it
ended), its command and its log; the Side work panel lists each side task with its state, its time and tokens, its
note and why it failed or was dropped; and the session the view follows (Thinking, Tool calls, the context window) is a
side task's while one works, else the box's."""

from datetime import UTC, datetime
from typing import Any

from clank.components.agents.console.boxchart import state_mark
from clank.components.agents.console.flowpanels import selected, sides
from clank.components.agents.console.flowview import running_session

NOW = datetime(2026, 10, 23, 3, 12, tzinfo=UTC)
JOB = {"number": 1, "title": "The annealing seeds", "command": "python3 anneal.py --seeds 8", "minutes": 45,
       "folder": ".clank/jobs/study/1/T1-1", "started": "2026-10-23T03:00:00Z", "ended": None, "status": None,
       "said": ""}  # fmt: skip
SESSION = {"workspace": "myproject", "port": 4096, "session": "ses_box"}


def grid(**job: Any) -> dict[str, Any]:
    """T1 running, its try's job as given."""
    attempt = {"number": 1, "started": "2026-10-23T02:50:00Z", "ended": None, "outcome": None, "reason": "",
               "tokens": 1200, "session": SESSION, "written": [], "verdict": None, "command": None,
               "jobs": [{**JOB, **job}], "waited": 0}  # fmt: skip
    return {"id": "T1", "type": "task", "title": "The grid", "state": "running", "tries": [attempt], "writes": [],
            "sees": [], "model": "", "mode": ""}  # fmt: skip


def view(box: dict[str, Any], side: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"flow": "myproject/study", "boxes": [box], "run": {"number": 1, "status": "running", "at": "T1"},
            "orchestrator": {"on": True, "sides": side or [], "side_minutes": 12, "side_budget": 180}}  # fmt: skip


def shown(lines: list[Any]) -> str:
    return "\n".join(line.plain for line in lines)


def test_a_box_waiting_on_its_job_says_so_on_its_tag_line_and_selected_says_the_job() -> None:
    assert "job 1" in state_mark(grid(), {"step": 7})[0]
    said = shown(selected(view(grid()), "T1", 100, UTC, NOW))
    assert "The annealing seeds · 12 of 45 min" in said
    assert "python3 anneal.py --seeds 8" in said
    assert ".clank/jobs/study/1/T1-1/log" in said
    ended = shown(selected(view(grid(ended="2026-10-23T03:10:00Z", status=0, said="exited 0")), "T1", 100, UTC, NOW))
    assert "The annealing seeds · exited 0" in ended
    assert "step 7" in state_mark(grid(ended="2026-10-23T03:10:00Z", status=0), {"step": 7})[0], "working again"


def test_the_side_work_panel_lists_each_task_with_its_state_time_tokens_note_and_why() -> None:
    side = [
        {"number": 1, "job": "T1-1", "title": "Prior bounds", "state": "done", "note": "corpus/1-1-prior-bounds.md",
         "started": "2026-10-23T03:01:00Z", "ended": "2026-10-23T03:07:00Z", "tokens": 8200, "reason": "",
         "session": None},
        {"number": 2, "job": "T1-1", "title": "The next fit", "state": "running", "note": "corpus/1-2-the-next-fit.md",
         "started": "2026-10-23T03:07:00Z", "ended": None, "tokens": 0, "reason": "",
         "session": {**SESSION, "session": "ses_side"}},
        {"number": 3, "job": "T1-1", "title": "A figure", "state": "dropped", "note": "corpus/1-3-a-figure.md",
         "started": None, "ended": None, "tokens": 0, "reason": "its job ended first", "session": None},
    ]  # fmt: skip
    said = shown(sides(view(grid(), side), 100, UTC, NOW))
    assert "12 of 180 min of side work used" in said
    assert "Prior bounds" in said
    assert "6 min" in said
    assert "8,200 tokens" in said
    assert "corpus/1-1-prior-bounds.md" in said
    assert "The next fit" in said
    assert "5 min" in said
    assert "its job ended first" in said
    assert "No side work in this run." in shown(sides(view(grid()), 100, UTC, NOW))


def test_the_view_follows_a_side_tasks_session_while_one_works_else_the_boxs() -> None:
    working = [{"number": 2, "job": "T1-1", "title": "The next fit", "state": "running", "note": "",
                "session": {**SESSION, "session": "ses_side"}}]  # fmt: skip
    assert running_session(view(grid(), working)) == ("myproject", "ses_side", 4096)
    done = [{**working[0], "state": "done"}]
    assert running_session(view(grid(), done)) == ("myproject", "ses_box", 4096)
