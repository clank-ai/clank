"""Design 0012 §9.4, design 0016 §10 and §12, and design 0001 §6.5: what the gateway's process keeps in files (the
pauses, the sessions kept from the cloud, the cloud spool, the day's records) is kept though another program holds a
file for good, as Windows then refuses its replace or its delete: said in the gateway's log, kept in memory meanwhile,
and a request never fails for it; the spool never gives a number twice in a run, though its counter could not be
written."""

import json
import logging
import os
import time
from pathlib import Path

import pytest

from clank.components.gateway.holds import Holds
from clank.components.gateway.marks import LocalMarks
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.spool import COUNTER, Spool
from clank.kernel import files


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The names of the files another program holds for good: each replace onto one, and each delete of one, refused
    as Windows refuses them (the waits between tries short)."""
    names: list[str] = []
    real_replace, real_unlink = os.replace, Path.unlink

    def replace(source: str | Path, target: str | Path) -> None:
        if Path(target).name in names:
            raise PermissionError(5, "Access is denied")
        real_replace(source, target)

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name in names:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(files, "WAITS", (0.01,))
    monkeypatch.setattr(files, "MOMENT", (0.01,))
    return names


def test_a_pause_holds_though_its_file_cannot_be_written_and_says_so(
    tmp_path: Path, held: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    held.append("holds.json")
    holds = Holds(file=tmp_path / "holds.json")
    with caplog.at_level(logging.WARNING):
        paused = holds.pause("ses_a", "you (console)")
    assert (paused["session"], [each["session"] for each in holds.view()]) == ("ses_a", ["ses_a"])
    assert holds.take("r-1", "ses_a") is not None, "its requests are held"
    assert "the pauses could not be kept" in caplog.text
    assert sorted(path.name for path in tmp_path.iterdir()) == [], "nothing half written is left"


def test_a_session_kept_from_the_cloud_is_kept_though_its_file_cannot_be_written(
    tmp_path: Path, held: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    held.append("local-only.json")
    marks = LocalMarks(tmp_path / "local-only.json")
    with caplog.at_level(logging.WARNING):
        assert marks.mark("ses_a", "clank_notion_read") is True
    assert marks.marked("ses_a") == "clank_notion_read"
    assert "could not be written" in caplog.text


def test_the_spool_keeps_its_entries_though_its_counter_cannot_be_written_and_never_gives_a_number_twice(
    tmp_path: Path, held: list[str]
) -> None:
    first = Spool(tmp_path)
    first.add({"id": "r-1", "usd": 0.01, "how": "usage"})
    held.append(COUNTER)  # from now on the counter stays at 1
    assert first.add({"id": "r-2", "usd": 0.02, "how": "usage"})["seq"] == 2
    assert json.loads((tmp_path / COUNTER).read_text(encoding="utf-8"))["seq"] == 1
    again = Spool(tmp_path)  # the gateway started again
    assert [entry["seq"] for entry in again.pending()] == [1, 2]
    assert again.add({"id": "r-3", "usd": 0.0, "how": "usage"})["seq"] == 3


def test_a_days_records_are_kept_though_an_old_days_file_to_remove_is_held_open(
    tmp_path: Path, held: list[str]
) -> None:
    old = tmp_path / "2026-09-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    month_ago = time.time() - 40 * 86400
    os.utime(old, (month_ago, month_ago))
    held.append(old.name)
    TrafficLog(tmp_path, limit_kib=1, keep_days=14).write({"id": "r-4", "day": "2026-10-13"})
    assert json.loads((tmp_path / "2026-10-13.jsonl").read_text(encoding="utf-8"))["id"] == "r-4"
    assert old.exists(), "left for the next day's look"
