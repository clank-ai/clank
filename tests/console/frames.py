"""Test support: the console's frames compared with the snapshots checked in under `tests/console/snapshots/`
(decision 0027). What changes from run to run (the service's port, the ids of questions and operations, Clank's
version) is replaced by a fixed stand-in of the same width first; `CLANK_UPDATE_SNAPSHOTS=1` rewrites the snapshots
instead of comparing.
"""

import difflib
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App
from textual.pilot import Pilot
from textual.widgets import ListView

from clank.console.snapshot import render_text

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
FOLDER = "/work/paper"  # the folder a console in a frame was started in: the same on every machine
STAND_INS: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (re.compile(r"127\.0\.0\.1:\d{5}\b"), "127.0.0.1:47720"),
    (re.compile(r"\bq-[0-9a-f]{6}\b"), "q-000000"),
    (re.compile(r"\bop-[0-9a-f]{8}\b"), "op-00000000"),
    (re.compile(r"\bv\d+\.\d+\.\d+[\w.]*"), lambda found: re.sub(r"\d", "0", found.group(0))),
]  # each keeps its line's width (a version's digits each a 0), so a panel's right border stands where it is drawn


def normalized(frame: str) -> str:
    """A frame with its changing parts replaced and its lines' trailing spaces removed."""
    for pattern, stand_in in STAND_INS:
        frame = pattern.sub(stand_in, frame)
    return "\n".join(line.rstrip() for line in frame.splitlines()).rstrip() + "\n"


def assert_frame(frame: str, name: str) -> None:
    """The frame is the snapshot of this name (or becomes it, with CLANK_UPDATE_SNAPSHOTS=1)."""
    path = SNAPSHOTS / f"{name}.txt"
    shown = normalized(frame)
    if os.environ.get("CLANK_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(shown, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"no snapshot {path.name}: run with CLANK_UPDATE_SNAPSHOTS=1 and read what it wrote"
    expected = path.read_text(encoding="utf-8")
    difference = "".join(difflib.unified_diff(expected.splitlines(True), shown.splitlines(True), path.name, "frame"))
    assert shown == expected, f"the frame differs from {path.name}:\n{difference}"


async def settle(pilot: Pilot[Any], until: Callable[[], bool], seconds: float = 10) -> None:
    """Let the console run until a condition holds (it loads and redraws in its own time)."""
    deadline = time.monotonic() + seconds
    while not until():
        if time.monotonic() > deadline:
            raise AssertionError("the console never got there")
        await pilot.pause(0.05)


async def steady_frame(pilot: Pilot[Any], app: App[Any], seconds: float = 10) -> str:
    """The app's frame once it has stopped changing: the same frame twice, a tenth of a second apart, so no frame is
    taken between a change and the layout that follows it (a row of panels stacks on its first resize, and its panels
    then draw their titles again for their new widths)."""
    deadline = time.monotonic() + seconds
    frame = render_text(app)
    while time.monotonic() < deadline:
        await pilot.pause(0.1)
        again = render_text(app)
        if again == frame:
            return frame
        frame = again
    raise AssertionError("the frame never stopped changing")


async def frame_when(pilot: Pilot[Any], app: App[Any], *words: str, seconds: float = 10) -> str:
    """The console's frame once it shows each of these words and its keys bar (drawn again whenever the focus moves),
    and has stopped changing (`steady_frame`)."""
    await settle(pilot, lambda: all(word in render_text(app) for word in (*words, "f1 help")), seconds)
    return await steady_frame(pilot, app, seconds)


async def focus_on(pilot: Pilot[Any], app: App[Any], listed: ListView, index: int | None = None) -> None:
    """Move the focus to a list, highlight a row, and wait until both took effect, so the next key goes where meant
    (moving the focus is not immediate, and a slower machine shows it)."""
    listed.focus()
    if index is not None:
        listed.index = index
    await settle(pilot, lambda: app.focused is listed and (index is None or listed.index == index))
