"""Design 0007 §5: a change the agent asks for, worked out as the file it would leave, from what OpenCode 1.19 says
(`tests/fixtures/opencode/1.19.0/changes.json`, recorded) and from made-up asks; its diff and counts; where it is kept.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from clank.components.agents.changes import KEPT, ChangeStore, proposed, unified

RECORDED: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "opencode" / "1.19.0" / "changes.json").read_text(encoding="utf-8")
)
BEFORE = "class A:\n    def f(self):\n        a = 1\n        b = 2\n        c = 3\n        return a\n"


@pytest.mark.parametrize("name", ["edit-once", "edit-after-patch"])
def test_a_recorded_edit_is_worked_out_exactly_from_its_tool_call_and_from_its_diff_alone(name: str) -> None:
    """Design 0007 §2: OpenCode's diff lost the indentation its lines share; the file's lines give it back."""
    change = RECORDED[name]
    diff = change["asked"]["metadata"]["diff"]
    assert "\n value_4 = 4\n" in diff, "the recorded diff has its indentation removed"
    assert proposed(change["before"], change["input"], diff) == (change["after"], True)
    assert proposed(change["before"], None, diff) == (change["after"], False)


def test_a_recorded_write_of_a_new_file_is_its_content() -> None:
    change = RECORDED["write-reject"]
    diff = change["asked"]["metadata"]["diff"]
    assert proposed(None, change["input"], diff) == ("print('new')\n", True)
    assert proposed(None, None, diff) == ("print('new')\n", False)


def test_an_edit_that_is_not_exact_is_worked_out_from_its_diff() -> None:
    ambiguous = {"oldString": "        ", "newString": "    "}
    diff = "@@ -4,1 +4,2 @@\n-b = 2\n+b = 22\n+bb = 0\n"
    assert proposed(BEFORE, ambiguous, diff) == (BEFORE.replace("        b = 2\n", "        b = 22\n        bb = 0\n"),
                                                 False)  # fmt: skip
    every = {"oldString": "= ", "newString": "== ", "replaceAll": True}
    assert proposed(BEFORE, every, "")[0] == BEFORE.replace("= ", "== ")
    assert proposed(BEFORE, {"oldString": "", "newString": "x\n"}, "") == ("x\n", True), "an empty old text: the file"


def test_a_diff_that_no_longer_fits_the_file_cannot_be_worked_out() -> None:
    assert proposed(BEFORE, None, "@@ -4,1 +4,1 @@\n-z = 9\n+z = 10\n") == (None, False)
    assert proposed(BEFORE, None, "") == (None, False), "no hunk"
    assert proposed("x\n", None, "@@ -7,1 +7,1 @@\n-y\n+z\n") == (None, False), "past the file's end"


def test_a_windows_file_keeps_its_line_endings() -> None:
    before = BEFORE.replace("\n", "\r\n")
    after, exact = proposed(before, None, "@@ -3,1 +3,1 @@\n-a = 1\n+a = 10\n")
    assert (after, exact) == (before.replace("a = 1\r\n", "a = 10\r\n"), False)


def test_the_diff_clients_show_is_made_from_the_file_before_and_after_with_its_counts() -> None:
    after = BEFORE.replace("        b = 2\n", "        b = 22\n        bb = 0\n")
    diff, added, removed = unified(BEFORE, after, "pkg/a.py")
    assert diff.startswith("--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ ")
    assert "-        b = 2\n+        b = 22\n+        bb = 0\n" in diff, "with the file's own indentation"
    assert (added, removed) == (2, 1)
    created, added, removed = unified(None, "x\ny\n", "new.py")
    assert created.startswith("--- /dev/null\n+++ b/new.py\n")
    assert (added, removed) == (2, 0)


def test_changes_are_kept_the_newest_first_and_the_oldest_forgotten(tmp_path: Path) -> None:
    store = ChangeStore(tmp_path / "changes")
    for number in range(KEPT + 2):
        store.save(
            {"id": f"per_{number}", "workspace": "paper" if number % 2 else "other", "before": "x", "after": "y"}
        )
        stamp = time.time_ns() + number * 1_000_000
        os.utime(store.folder / f"per_{number}.json", ns=(stamp, stamp))
    assert store.get("per_0") is None, "beyond the newest it keeps"
    assert store.get(f"per_{KEPT + 1}") == {"id": f"per_{KEPT + 1}", "workspace": "paper", "before": "x", "after": "y"}
    assert [each["id"] for each in store.recent("paper", limit=2)] == [f"per_{KEPT + 1}", f"per_{KEPT - 1}"]
    assert "before" not in store.recent(limit=1)[0], "a list leaves the files' contents out"
    assert store.get("../config/secret") is None, "an id that is not a change's reads nothing"
