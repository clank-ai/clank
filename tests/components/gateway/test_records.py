"""Design 0001 §6.5: the gateway keeps one JSON line per request, in one file per day under `logs/traffic/`; a field
longer than the limit is cut, saying how long it was; a request's credentials never reach the file; a day's file older
than the days kept is removed."""

import json
import os
import time
from pathlib import Path

from clank.components.gateway.records import TrafficLog


def test_one_line_per_request_in_a_file_per_day(tmp_path: Path) -> None:
    log = TrafficLog(tmp_path, limit_kib=1, keep_days=14)
    log.write({"id": "r-1", "time": "2026-10-13T22:00:00.000Z", "day": "2026-10-13", "role": "agent"})
    log.write({"id": "r-2", "time": "2026-10-13T22:01:00.000Z", "day": "2026-10-13", "role": "agent"})
    lines = (tmp_path / "2026-10-13.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["r-1", "r-2"]


def test_a_long_field_is_cut_saying_how_long_it_was_and_credentials_never_reach_the_file(tmp_path: Path) -> None:
    log = TrafficLog(tmp_path, limit_kib=1, keep_days=14)
    headers = {"authorization": "Bearer secret-token", "x-api-key": "secret-key", "user-agent": "opencode"}
    log.write({"id": "r-3", "day": "2026-10-13", "answer": "x" * 5000, "headers": headers})
    text = (tmp_path / "2026-10-13.jsonl").read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["answer"].startswith("x" * 1000)
    assert record["answer"].endswith("[cut: 5,000 characters in all]")
    assert "secret" not in text
    assert record["headers"] == {"authorization": "(not kept)", "x-api-key": "(not kept)", "user-agent": "opencode"}


def test_a_days_file_older_than_the_days_kept_is_removed(tmp_path: Path) -> None:
    old = tmp_path / "2026-09-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    month_ago = time.time() - 40 * 86400
    os.utime(old, (month_ago, month_ago))
    TrafficLog(tmp_path, limit_kib=1, keep_days=14).write({"id": "r-4", "day": "2026-10-13"})
    assert not old.exists()
    assert (tmp_path / "2026-10-13.jsonl").exists()
