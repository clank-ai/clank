"""The gateway's spool of cloud requests (design 0016 §12, decision 0108): each cloud request that ends is appended,
with its cost and how that is known, to `state/cloud-spool.jsonl`, so a restart of the gateway loses none; the service
takes them every two seconds (`GET /spend?after=<n>`, behind its local token), and each take forgets the entries up to
the last the service took. Each entry is named by the spool's run and its sequence number, both kept with the spool
(`state/cloud-spool.json`), so the service, which keeps them by run and sequence, never counts one twice; a number is
never given twice in a run, though its counter could not be written (the entries' own numbers count too). The files are
changed through the kernel's `files`, and one another program holds for good is said in the gateway's log, the
entries kept in memory all the same: a request never fails for it.
"""

import json
import logging
import secrets
import threading
from pathlib import Path
from typing import Any

from clank.kernel import files

log = logging.getLogger(__name__)

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
                try:
                    self._folder.mkdir(parents=True, exist_ok=True)
                    with (self._folder / ENTRIES).open("a", encoding="utf-8", newline="\n") as file:
                        file.write(json.dumps(kept, ensure_ascii=False) + "\n")
                except OSError as error:
                    log.warning("the cloud spool %s could not be written (%s): kept in memory", self._folder, error)
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
                self._seq = max(self._seq, int(entry["seq"]))  # a counter that could not be written is behind

    def _save_counter(self) -> None:
        assert self._folder is not None
        self._replace(COUNTER, json.dumps({"run": self.run, "seq": self._seq}))

    def _rewrite(self) -> None:
        if self._folder is None:
            return
        self._replace(ENTRIES, "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in self._entries))

    def _replace(self, name: str, text: str) -> None:
        """One of the spool's files written whole; one another program holds for good is said, and left as it was."""
        assert self._folder is not None
        try:
            files.replace(self._folder / name, text, files.MOMENT)
        except OSError as error:
            log.warning("the cloud spool's %s could not be written (%s): kept in memory", name, error)
