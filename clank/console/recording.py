"""The console recorded as it draws itself (`clank console --record FOLDER`, decision 0126): every write it sends the
terminal, with its time to the microsecond, in the asciicast format (version 2) that asciinema's player reads, so the
console can be watched again exactly as it was, at its own pace.

It is taken where the console writes (Textual's driver), so it is what the terminal received: no screen is captured,
nothing is encoded, and no second terminal stands between (a recorder that runs the console in a pseudo console of its
own redraws it twice, and lines can shift). It holds only what the console drew: a key typed in a hidden field (a cloud
provider's, design 0016 §4) is drawn as dots, and nothing typed is written. A recording is kept in parts
(`<date>_<name>-part01.cast`, `-part02.cast`, ...), a new one every `PART_MINUTES`, its first write the whole screen
drawn again, so no file grows too large for the player and each part plays on its own.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

PART_MINUTES = 20.0
CLEAR = "\x1b[2J\x1b[H"  # each part begins on a clear screen, then the whole screen drawn


class Recording:
    """A recording in parts, written as the console draws."""

    def __init__(self, folder: Path, name: str, width: int, height: int, command: str = "clank console") -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.base = folder / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{name}"
        self.command = command
        self.lock = threading.Lock()
        self.part = 0
        self.events = 0
        self.closed = False
        self._open(width, height)

    def _open(self, width: int, height: int) -> None:
        self.part += 1
        self.path = self.base.with_name(f"{self.base.name}-part{self.part:02d}.cast")
        self.file = self.path.open("w", encoding="utf-8", newline="\n")
        self.start = time.perf_counter()
        self.began = time.monotonic()
        header = {
            "version": 2, "width": width, "height": height, "timestamp": int(time.time()), "start": time.time(),
            "title": self.path.stem, "command": self.command, "part": self.part,
            "env": {"TERM": "xterm-256color"},
        }  # fmt: skip
        self.file.write(json.dumps(header) + "\n")
        self._add("o", CLEAR)

    def _add(self, kind: str, data: str) -> None:
        self.file.write(json.dumps([round(time.perf_counter() - self.start, 6), kind, data], ensure_ascii=False))
        self.file.write("\n")
        self.events += 1

    def output(self, data: str) -> None:
        """What the console wrote to the terminal."""
        with self.lock:
            if not self.closed and data:
                self._add("o", data)

    def resized(self, width: int, height: int) -> None:
        """The terminal's new size."""
        with self.lock:
            if not self.closed:
                self._add("r", f"{width}x{height}")

    def due(self) -> bool:
        """Whether this part has run its time: the next begins once the console draws its whole screen again."""
        return time.monotonic() - self.began >= PART_MINUTES * 60

    def next_part(self, width: int, height: int) -> None:
        """Close this part and begin the next."""
        with self.lock:
            if self.closed:
                return
            self.file.close()
            self._open(width, height)

    def keep(self) -> None:
        """What was written so far, on disk."""
        with self.lock:
            if not self.closed:
                self.file.flush()

    def close(self) -> None:
        """End the recording: the part on disk, closed; what the console writes later is not kept."""
        with self.lock:
            if not self.closed:
                self.closed = True
                self.file.close()
