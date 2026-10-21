"""What passes between this computer and the paired devices (design 0005 §4, transparency): every exchange of the
phone's listener, kept so the owner can see everything a phone asked and everything it was sent, from the console (F9: a
device, Enter) or from the phone itself (its log tab).

An exchange is one request and its answer: when, which device (when the request named a paired one), the method, the
path and the query, the status, how long it took, the bytes each way, and both bodies: JSON as it was, text as text, and
for anything else (a picture sent) its type and size. Nothing secret is kept: the device's token never (it travels in
a cookie, and no header is kept), and a pairing code is masked. An answer the same as the last one to the same request
from the same device (the page asks every few seconds) is kept as `same_as` that one's id, so a page left open costs
little. Each exchange is written as a line of `logs/phone/<day>.jsonl`, the last `KEPT` are also kept in memory, and
files older than `KEEP_DAYS` are removed. A view of the log itself is kept without its answer (it is the log).
"""

import hashlib
import json
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from clank.kernel.clock import to_text

KEPT = 2000
KEEP_DAYS = 7
BODY = 64 * 1024  # the most of a body kept, in characters
MASKED = "••••••••"
LOG_PATH = "/api/traffic"


class Traffic:
    """The exchanges with the paired devices: written to the day's file and kept in memory."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._kept: deque[dict[str, Any]] = deque(maxlen=KEPT)
        self._last: dict[tuple[str, str], tuple[str, str]] = {}  # (device, request) -> (answer's digest, its id)
        self._lock = threading.Lock()
        self._loaded = False

    def record(
        self,
        *,
        when: datetime,
        device: tuple[str, str] | None,
        method: str,
        path: str,
        query: str,
        status: int,
        ms: float,
        request: bytes,
        request_type: str,
        response: bytes,
        response_type: str,
    ) -> dict[str, Any]:
        """Keep one exchange; it, as kept."""
        exchange: dict[str, Any] = {
            "id": f"x-{secrets.token_hex(5)}", "time": to_text(when), "device": device[0] if device else "",
            "device_name": device[1] if device else "", "method": method, "path": path, "query": query,
            "status": status, "ms": round(ms, 1), "bytes_in": len(request), "bytes_out": len(response),
            "request": _body(request, request_type, path), "response_type": response_type,
        }  # fmt: skip
        if path.startswith(LOG_PATH):
            exchange["response"] = "(the log itself, not kept again)"
        else:
            digest = hashlib.sha256(response).hexdigest()
            key = (exchange["device"], f"{method} {path}?{query}")
            with self._lock:
                same = self._last.get(key)
                self._last[key] = (digest, exchange["id"]) if same is None or same[0] != digest else same
            if same is not None and same[0] == digest:
                exchange["same_as"] = same[1]
            else:
                exchange["response"] = _body(response, response_type, path)
        with self._lock:
            self._kept.append(exchange)
            self._write(exchange, when)
        return exchange

    def recent(self, device: str = "", limit: int = 200) -> list[dict[str, Any]]:
        """The newest exchanges (of one device, when named), newest first, each without its bodies."""
        self._load()
        with self._lock:
            found = [each for each in reversed(self._kept) if not device or each["device"] == device]
        bodies = ("request", "response")
        return [{key: value for key, value in each.items() if key not in bodies} for each in found[:limit]]

    def exchange(self, id: str) -> dict[str, Any] | None:
        """One exchange whole, its bodies included (an answer kept as the same as an earlier one, that one's)."""
        self._load()
        with self._lock:
            kept = {each["id"]: each for each in self._kept}
        found = kept.get(id)
        if found is None:
            return None
        if "same_as" in found and found["same_as"] in kept:
            return {**found, "response": kept[found["same_as"]].get("response")}
        return dict(found)

    def _write(self, exchange: dict[str, Any], when: datetime) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        day = self.folder / f"{when:%Y-%m-%d}.jsonl"
        with day.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(exchange, ensure_ascii=False) + "\n")
        if not day.exists() or day.stat().st_size < 4096:  # a new day: the old files go
            for old in self.folder.glob("*.jsonl"):
                if old.stem < f"{when - timedelta(days=KEEP_DAYS):%Y-%m-%d}":
                    old.unlink(missing_ok=True)

    def _load(self) -> None:
        """At the first look, the exchanges of the last days, from their files (the service started since)."""
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not self.folder.is_dir():
                return
            lines: list[dict[str, Any]] = []
            for file in sorted(self.folder.glob("*.jsonl"))[-2:]:
                for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        lines.append(json.loads(line))
                    except ValueError:
                        continue
            if lines:  # every exchange kept since the start is in the files too
                self._kept = deque(lines[-KEPT:], maxlen=KEPT)


def _body(raw: bytes, kind: str, path: str) -> Any:
    """A body as kept: JSON as it was, text as text, anything else by its type and size; a pairing code masked."""
    if not raw:
        return None
    if "json" in kind or (not kind and raw[:1] in (b"{", b"[")):
        try:
            value = json.loads(raw)
        except ValueError:
            value = None
        if value is not None:
            if path == "/api/pair" and isinstance(value, dict) and "code" in value:
                value = {**value, "code": MASKED}
            text = json.dumps(value, ensure_ascii=False)
            return value if len(text) <= BODY else text[:BODY] + f" … [{len(text):,} characters]"
    if kind.startswith("text/") or kind.endswith("javascript"):
        text = raw.decode("utf-8", errors="replace")
        return text if len(text) <= BODY else text[:BODY] + f" … [{len(text):,} characters]"
    return f"[{kind or 'bytes'}, {len(raw):,} bytes]"
