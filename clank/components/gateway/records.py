"""The gateway's records (design 0001 §6.5): one JSON line per request, in one file per day.

Files are `logs/traffic/<day>.jsonl`, the day the owner's (local) date. A record holds who asked, the role, the slot,
the preset and the engine, the model name sent, what the engine's fields changed, the timings, the token counts, the
status and the error (with what repeated, when the loop guard stopped the answer: `looped`), the ids of the calls the
answer made (`calls`), and (unless turned off) the request and the answer. Any text longer than the limit is cut,
saying how long it was; a header that carries a credential is never kept (its name is, its value is not). A day's file
older than the days kept is removed when the first record of a day is written. Writes are serialized, so records from
requests that end together never interleave. `recent` reads the newest records back, each summed up (who asked, in
which session, how it went, its tokens and its speed), from the files' ends; `find` reads one with what was asked and
answered (the console's Requests page), and the sampling it sent of its own (`sampling`: none when it sent none, `None`
when its request was not kept; design 0003 §4.1).
"""

import json
import threading
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from clank.components.gateway.sessions import session_of

CREDENTIALS = {"authorization", "proxy-authorization", "x-api-key", "api-key", "cookie", "set-cookie"}


class TrafficLog:
    """The daily files of the gateway's records."""

    def __init__(self, folder: Path, limit_kib: int, keep_days: int) -> None:
        self.folder = folder
        self.limit = limit_kib * 1024
        self.keep_days = keep_days
        self._lock = threading.Lock()
        self._pruned: str | None = None

    def write(self, record: dict[str, Any]) -> None:
        """Keep one request's record."""
        values = dict(record)
        day = str(values.pop("day", "") or date.today().isoformat())
        if isinstance(values.get("headers"), dict):
            values["headers"] = {
                name: "(not kept)" if name.lower() in CREDENTIALS else value
                for name, value in values["headers"].items()
            }
        line = json.dumps(self._cut(values), ensure_ascii=False) + "\n"
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            if self._pruned != day:
                self._prune()
                self._pruned = day
            with (self.folder / f"{day}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
                file.write(line)

    def _cut(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > self.limit:
            return value[: self.limit] + f" … [cut: {len(value):,} characters in all]"
        if isinstance(value, dict):
            return {key: self._cut(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._cut(item) for item in value]
        return value

    def _prune(self) -> None:
        oldest = time.time() - self.keep_days * 86400
        for file in self.folder.glob("*.jsonl"):
            if file.stat().st_mtime < oldest:
                file.unlink(missing_ok=True)


def recent(folder: Path, limit: int) -> list[dict[str, Any]]:
    """The newest records first, each summed up (`summary`): read from the files' ends, so a long day costs little."""
    found = []
    for line in _newest_first(folder):
        record = _parsed(line)
        if record is not None:
            found.append(summary(record))
            if len(found) >= limit:
                break
    return found


def find(folder: Path, id: str) -> dict[str, Any] | None:
    """One record by its id, with what was asked and what was answered (each cut at `SHOWN` characters)."""
    for line in _newest_first(folder):
        if f'"{id}"' not in line:
            continue
        record = _parsed(line)
        if record is not None and record.get("id") == id:
            kept = record.get("request")
            request = kept or {}
            return {
                **summary(record),
                "asked": _last_user(request.get("messages") or [])[:SHOWN],
                "answer": str(record.get("answer") or "")[:SHOWN],
                "model_sent": record.get("model_sent"),
                "engine": record.get("engine"),
                "slot": record.get("slot"),
                "wait_ms": record.get("wait_ms"),
                "max_tokens": request.get("max_tokens"),
                "sampling": {name: request[name] for name in SAMPLING if name in request} if kept else None,
            }
    return None


def summary(record: dict[str, Any]) -> dict[str, Any]:
    """A record in brief: who asked (and in which session, `sessions.py`), how it went, its tokens and its speed, and
    the start of what was asked."""
    usage = record.get("usage") or {}
    request = record.get("request") or {}
    messages = request.get("messages") or []
    first, total, out = record.get("first_token_ms"), record.get("total_ms"), usage.get("completion_tokens")
    speed = None
    if out and first is not None and total and total > first:
        speed = round(out / ((total - first) / 1000), 1)
    agent = str((record.get("headers") or {}).get("user-agent") or "")
    session, parent = session_of(record.get("headers"))
    return {
        "id": record.get("id"),
        "time": record.get("time"),
        "role": record.get("role"),
        "client": agent.split("/")[0] or str(record.get("client") or ""),
        "session": session,
        "parent": parent,
        "status": record.get("status"),
        "stream": bool(record.get("stream")),
        "preset": record.get("preset"),
        "error": _said(record.get("error")),
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": usage.get("prompt_cache_hit_tokens"),
        "completion_tokens": out,
        "first_token_ms": first,
        "total_ms": total,
        "per_second": speed,
        "messages": len(messages),
        "tools": len(request.get("tools") or []),
        "notes": str(record.get("notes") or ""),
        "again": bool(record.get("again")),
        "broken": bool(record.get("broken")),
        "looped": bool(record.get("looped")),
        "full": bool(record.get("full")),
        "held_seconds": (record.get("held") or {}).get("seconds") if isinstance(record.get("held"), dict) else None,
        "asked_start": " ".join(_last_user(messages).split())[:BRIEF],
    }


def _said(error: Any) -> str:
    """A record's error in words: its message when it has one (a refusal's own, or an engine's in OpenAI's shape)."""
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or "")


SHOWN = 6000  # characters of a request's question and answer a client is given
# The sampling fields a request may send of its own, which win over its engine's (design 0003 §4.1).
SAMPLING = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty", "repeat_penalty",
            "repetition_penalty", "seed")  # fmt: skip
BRIEF = 160
CHUNK = 1 << 20


def _last_user(messages: list[Any]) -> str:
    """The text of the last message the user (not a tool) wrote."""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def _parsed(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None  # a line being written as it is read
    return value if isinstance(value, dict) else None


def _newest_first(folder: Path) -> Iterator[str]:
    """Every line of every day's file, the newest day first and each day's newest line first."""
    for file in sorted(folder.glob("*.jsonl"), reverse=True):
        with file.open("rb") as stream:
            end = stream.seek(0, 2)
            rest = b""
            while end > 0:
                start = max(0, end - CHUNK)
                stream.seek(start)
                piece = stream.read(end - start) + rest
                end = start
                lines = piece.split(b"\n")
                rest = lines.pop(0) if start > 0 else b""
                for line in reversed(lines):
                    if line.strip():
                        yield line.decode("utf-8", errors="replace")
            if rest.strip():
                yield rest.decode("utf-8", errors="replace")
