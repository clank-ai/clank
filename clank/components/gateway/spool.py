"""The gateway's spool of cloud requests (design 0016 §12, decision 0108): each cloud request that ends is appended,
with its cost and how that is known, to `state/cloud-spool.jsonl`, so a restart of the gateway loses none; the service
takes them every two seconds (`GET /spend?after=<n>`, behind its local token), and each take forgets the entries up to
the last the service took. Each entry is named by the spool's run and its sequence number, both kept with the spool
(`state/cloud-spool.json`), so the service, which keeps them by run and sequence, never counts one twice.
"""

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

ENTRIES = "cloud-spool.jsonl"
COUNTER = "cloud-spool.json"


class Spool:
    """The cloud requests that ended and are not yet taken by the service."""

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder
        self._lock = threading.Lock()
        self.run = "run-" + secrets.token_hex(4)
        self._seq = 0
        self._entries: list[dict[str, Any]] = []
        if folder is not None:
            self._load(folder)

    def add(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Append a request's entry; it as kept, with its sequence number."""
        with self._lock:
            self._seq += 1
            kept = {**entry, "seq": self._seq}
            self._entries.append(kept)
            if self._folder is not None:
                self._folder.mkdir(parents=True, exist_ok=True)
                with (self._folder / ENTRIES).open("a", encoding="utf-8", newline="\n") as file:
                    file.write(json.dumps(kept, ensure_ascii=False) + "\n")
                self._save_counter()
            return kept

    def after(self, taken: int) -> dict[str, Any]:
        """The entries after `taken`, the last the service took; those up to it are forgotten."""
        with self._lock:
            kept = [entry for entry in self._entries if int(entry["seq"]) > taken]
            if len(kept) != len(self._entries):
                self._entries = kept
                self._rewrite()
            return {"run": self.run, "entries": [dict(entry) for entry in kept], "last": self._seq}

    def pending(self) -> list[dict[str, Any]]:
        """The entries the service has not taken yet (the limit counts them, design 0016 §12)."""
        with self._lock:
            return [dict(entry) for entry in self._entries]

    def _load(self, folder: Path) -> None:
        try:
            counter = json.loads((folder / COUNTER).read_text(encoding="utf-8"))
            self.run, self._seq = str(counter["run"]), int(counter["seq"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        try:
            lines = (folder / ENTRIES).read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue  # a line cut by a crash as it was written
            if isinstance(entry, dict) and isinstance(entry.get("seq"), int):
                self._entries.append(entry)

    def _save_counter(self) -> None:
        assert self._folder is not None
        partial = self._folder / f".{COUNTER}.part"
        partial.write_bytes(json.dumps({"run": self.run, "seq": self._seq}).encode("utf-8"))
        os.replace(partial, self._folder / COUNTER)

    def _rewrite(self) -> None:
        if self._folder is None:
            return
        partial = self._folder / f".{ENTRIES}.part"
        text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in self._entries)
        partial.write_bytes(text.encode("utf-8"))
        os.replace(partial, self._folder / ENTRIES)
