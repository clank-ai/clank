"""Design 0011 §13 (decision 0126): `clank console --record FOLDER` keeps what the console draws, as the terminal gets
it, in asciicast files: a header with the terminal's size, then each write with its time, a resize kept as one; each
part begins on a clear screen with the whole screen drawn, and a new part begins once one has run its time. A view the
console does not have (`--view flow.`) is refused, never opened as another."""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from clank.cli import console as console_command
from clank.cli.main import main
from clank.client import Client
from clank.console import app as console_app
from clank.console import recording as recording_module
from clank.console.app import ClankConsole
from clank.kernel.home import Home
from tests.console.frames import FOLDER, frame_when, settle

pytestmark = pytest.mark.anyio


def make(client: Client, home: Home, folder: Path) -> ClankConsole:
    app = ClankConsole(client, home=home, record=folder)
    app.folder = FOLDER
    return app


def read(path: Path) -> tuple[dict[str, Any], list[list[Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


async def test_the_console_keeps_each_write_to_the_terminal_and_each_resize(
    client: Client, home: Home, tmp_path: Path
) -> None:
    """What the console's driver writes is kept, as the terminal gets it (a test's console draws nothing to a terminal,
    so the driver is written to here as the console writes to it)."""
    folder = tmp_path / "recordings"
    app = make(client, home, folder)
    async with app.run_test(size=(100, 30)) as pilot:
        await frame_when(pilot, app, "CLANK")
        await settle(pilot, lambda: app.recording is not None)
        assert app._driver is not None
        app._driver.write("\x1b[1;1H◆ CLANK  drawn")
        await pilot.resize_terminal(120, 40)
        await pilot.pause(0.3)
    [part] = sorted(folder.glob("*_console-part01.cast"))
    header, events = read(part)
    assert (header["version"], header["width"], header["height"]) == (2, 100, 30)
    assert events[0][1:] == ["o", recording_module.CLEAR], "a part begins on a clear screen"
    assert ["o", "\x1b[1;1H◆ CLANK  drawn"] in [event[1:] for event in events]
    assert ["r", "120x40"] in [event[1:] for event in events]
    times = [event[0] for event in events]
    assert times == sorted(times)


def test_a_recording_is_kept_in_parts_each_beginning_on_a_clear_screen(tmp_path: Path) -> None:
    kept = recording_module.Recording(tmp_path, "console", 100, 30)
    kept.output("one")
    assert not kept.due()
    kept.next_part(120, 40)
    kept.output("two")
    kept.close()
    kept.output("after it closed")
    first, second = sorted(tmp_path.glob("*_console-part*.cast"))
    head, events = read(first)
    assert (head["part"], head["width"]) == (1, 100)
    assert [event[1:] for event in events] == [["o", recording_module.CLEAR], ["o", "one"]]
    head, events = read(second)
    assert (head["part"], head["width"], head["height"]) == (2, 120, 40)
    assert [event[1:] for event in events] == [["o", recording_module.CLEAR], ["o", "two"]]


def test_a_view_the_console_does_not_have_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[dict[str, Any]] = []

    class Recorded:
        def __init__(self, client: Any, **kwargs: Any) -> None:
            opened.append(kwargs)

        def run(self, **kwargs: Any) -> None:
            return None

    class Unused:
        def close(self) -> None:
            return None

    monkeypatch.setattr(console_app, "ClankConsole", Recorded)
    monkeypatch.setattr(console_command, "connect", lambda home, start: Unused())
    refused = CliRunner().invoke(main, ["console", "--page", "monitor", "--view", "flow."])
    assert refused.exit_code == 2
    assert "'flow.' is no view: one of flow, session, context" in refused.output
    assert opened == []
    taken = CliRunner().invoke(main, ["console", "--view", "flow", "--record", "recordings"])
    assert taken.exit_code == 0, taken.output
    assert (opened[-1]["view"], opened[-1]["record"]) == ("flow", Path("recordings"))
