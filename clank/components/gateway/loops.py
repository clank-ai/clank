"""The loop guard (design 0004 §2, decision 0040): whether a streamed answer repeats itself.

A model that loses its way may write the same few lines again and again until its answer's limit (2026-10-18: a `bash`
call repeated closing tags for 16,384 tokens). The gateway feeds each streamed answer here as it comes, each part apart:
its thinking, its text, and each tool call's arguments (`tool <index>`: a new call starts afresh). A part repeats itself
when its newest stretch compresses (zlib) to under `ratio` of its size: the same few lines compress to almost nothing,
while code, prose and data keep most of their size (1,566 real answers, none under 0.188 over 2,000 characters:
docs/measurements/2026-10-18-repetition-in-answers.md). The thinking and the text are read over two stretches, a short
one that finds a short repeat soon and a long one that finds a paragraph said again (prose repeated every 600 to 800
characters; a longer or reworded repeat runs on); a tool call's arguments over the short one only, since a file written
from a template (records that differ by an id, rows of a table) compresses over the long stretch as far as a loop. A
part is read once it is as long as a stretch, then every `EVERY` characters, and only its newest characters (the longest
stretch) are kept. Each part's newest reading is kept too, its lowest share and over which stretch (`newest`, which
lists every part fed, one not yet as long as its shortest stretch without a share), so the Monitor shows how near each
part is to the ratio (design 0012 §5.4). Pure: no I/O.
"""

import zlib
from collections.abc import Sequence
from typing import Any

EVERY = 128  # characters of a part between two readings
LEVEL = 6  # zlib's level, the one measured


class LoopGuard:
    """One answer's watch: each piece of it is fed as it streams; once something repeated, `tripped` says what, over
    which stretch and how far it compressed, and `brief` says only what, in words without numbers (an agent may retry
    an error by the numbers in its words: OpenCode 1.19 retries one that holds 500, for instance)."""

    def __init__(
        self, windows: Sequence[int] = (2000, 8000), ratio: float = 0.06, tool_windows: Sequence[int] = (2000,)
    ) -> None:
        self.windows = sorted(windows)
        self.tool_windows = sorted(tool_windows)
        self.ratio = ratio
        self.tripped: str | None = None
        self.brief: str | None = None
        self._newest: dict[str, str] = {}  # each part's newest characters
        self._length: dict[str, int] = {}  # each part's length so far
        self._read: dict[str, int] = {}  # each part's length when it was read last
        self._names: dict[str, str] = {}  # each tool call's name
        self._shares: dict[str, tuple[float, int]] = {}  # each part's newest reading: its lowest share, its stretch

    def feed(self, part: str, text: str, name: str = "") -> str | None:
        """A piece of one part (`thinking`, `answer`, or `tool <index>`, a tool call's name with any of its pieces):
        what repeated, in words, the first time this piece makes its part repeat itself; else None."""
        if name:
            self._names[part] = name
        if self.tripped is not None or not text:
            return None
        windows = self.tool_windows if part.startswith("tool") else self.windows
        length = self._length.get(part, 0) + len(text)
        self._length[part] = length
        self._newest[part] = (self._newest.get(part, "") + text)[-windows[-1] :]
        if length - self._read.get(part, 0) < EVERY:
            return None
        self._read[part] = length
        lowest: tuple[float, int] | None = None
        for window in windows:
            if length < window:
                break
            share = share_of(self._newest[part][-window:])
            if lowest is None or share < lowest[0]:
                lowest = (share, window)
            if share < self.ratio:
                self._shares[part] = (share, window)
                self.brief = f"{self._what(part)} repeated itself"
                self.tripped = f"{self.brief} (its newest {window:,} characters compress to {share:.1%} of their size)"
                return self.tripped
        if lowest is not None:
            self._shares[part] = lowest
        return None

    def newest(self) -> list[dict[str, Any]]:
        """Each part fed so far, in the order it was first fed: its name (`thinking`, `answer`, `tool <index>`), a
        tool call's name, and its newest reading's lowest share (to three places) and the stretch it was read over;
        both None while the part is not yet as long as its shortest stretch (the Monitor says "watching")."""
        found: list[dict[str, Any]] = []
        for part in self._length:
            reading = self._shares.get(part)
            share, window = (round(reading[0], 3), reading[1]) if reading is not None else (None, None)
            found.append({"part": part, "name": self._names.get(part, ""), "share": share, "stretch": window})
        return found

    def _what(self, part: str) -> str:
        if part.startswith("tool"):
            name = self._names.get(part)
            return f"its tool call {name}" if name else "its tool call"
        return f"its {part}"


def share_of(text: str) -> float:
    """The share of its size a text compresses to."""
    raw = text.encode("utf-8")
    return len(zlib.compress(raw, LEVEL)) / max(1, len(raw))
