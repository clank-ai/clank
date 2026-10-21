"""Design 0013 §8: a deliverable counts only when written during its try, so a file left from before does not; and a
plan's progress (each step's tick, its Log's lines, its header's `status`) is told apart from the rest of the file (the
steps' own words, its other sections and its other header lines)."""

import os
from pathlib import Path

from clank.components.flows.deliverables import fingerprint, split, written

PLAN = """---
kind: plan
status: ready
title: A new simulation study
---
# A new simulation study

## Steps

- [ ] Write the grid (grid.json)
- [x] Write the sweep's script
* [ ] Run the pilot

## Log

## Deliverables

The report.
"""


def ticked(text: str) -> str:
    return text.replace("- [ ] Write the grid", "- [x] Write the grid", 1)


def logged(text: str) -> str:
    return text.replace("## Log\n", "## Log\n\n- 2026-10-19: wrote grid.json, 60 points.\n", 1)


def implementing(text: str) -> str:
    return text.replace("status: ready", "status: implementing", 1)


def test_a_file_written_during_a_try_counts_and_one_left_from_before_does_not(tmp_path: Path) -> None:
    file = tmp_path / "runs" / "estimates.md"
    assert fingerprint(tmp_path, "runs/estimates.md").sha256 == "", "not there yet"
    assert not written(fingerprint(tmp_path, "runs/estimates.md"), fingerprint(tmp_path, "runs/estimates.md"))
    before = fingerprint(tmp_path, "runs/estimates.md")
    file.parent.mkdir()
    file.write_bytes(b"| point | CPU-hours |\n")
    now = fingerprint(tmp_path, "runs/estimates.md")
    assert (now.path, now.size) == ("runs/estimates.md", 22)
    assert written(before, now), "made during the try"
    assert not written(now, fingerprint(tmp_path, "runs/estimates.md")), "left from before, untouched"
    stamp = file.stat().st_mtime_ns
    os.utime(file, ns=(stamp + 5_000_000_000, stamp + 5_000_000_000))
    assert written(now, fingerprint(tmp_path, "runs/estimates.md")), "written again, the same words"
    file.write_bytes(b"| point | CPU-hours | method |\n")
    os.utime(file, ns=(stamp, stamp))
    assert written(now, fingerprint(tmp_path, "runs/estimates.md")), "other words, whatever its time says"


def test_a_plans_ticks_log_and_status_are_its_progress_and_the_rest_its_other_lines() -> None:
    rest, progress = split(PLAN)
    for change in (ticked, logged, implementing):
        changed_rest, changed_progress = split(change(PLAN))
        assert changed_rest == rest, change.__name__
        assert changed_progress != progress, change.__name__
    for change in (
        lambda text: text.replace("Write the grid", "Write the grid of 240 points"),
        lambda text: text.replace("title: A new simulation study", "title: Another study"),
        lambda text: text.replace("The report.", "The report, and the plots."),
        lambda text: text.replace("* [ ] Run the pilot\n", ""),
    ):
        assert split(change(PLAN))[0] != rest


def test_a_plans_fingerprint_keeps_its_progress_apart_and_another_file_has_none(tmp_path: Path) -> None:
    (tmp_path / "PLAN.md").write_text(PLAN, encoding="utf-8", newline="\n")
    (tmp_path / "notes.md").write_text("- [ ] not a plan\n", encoding="utf-8", newline="\n")
    plan = fingerprint(tmp_path, "PLAN.md")
    assert plan.rest
    assert plan.progress
    (tmp_path / "PLAN.md").write_text(logged(ticked(PLAN)), encoding="utf-8", newline="\n")
    after = fingerprint(tmp_path, "PLAN.md")
    assert after.rest == plan.rest, "the rest unchanged"
    assert after.progress != plan.progress
    assert after.sha256 != plan.sha256
    notes = fingerprint(tmp_path, "notes.md")
    assert (notes.rest, notes.progress) == ("", "")
