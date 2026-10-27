"""Design 0002 §2.16 and design 0001 §7.2: a file of CLANK_HOME that another program may be reading while Clank changes
it (the state folder's above all) is replaced whole and at once, never half written, and replaced or removed though a
reader holds it for a moment, as Windows refuses both while one does (`clank gateway restart` answered 500 on
2026-10-23 when its stop could not delete `state/gateway.json`); one never let through is said, never half done."""

import os
import threading
from pathlib import Path

import pytest

from clank.kernel import files

HELD = PermissionError(32, "The process cannot access the file because it is being used by another process")


@pytest.fixture
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """The waits between tries kept short, so a refusal that never ends ends the test soon."""
    monkeypatch.setattr(files, "WAITS", (0.01, 0.01, 0.01))


def refused(times: int, real: object) -> tuple[list[int], object]:
    """A replacement for `os.replace` or `os.unlink` that refuses the first `times` calls as Windows does while another
    program holds the file, then does the real thing; the calls counted."""
    calls = [0]

    def attempt(*given: object, **named: object) -> object:
        calls[0] += 1
        if calls[0] <= times:
            raise HELD
        return real(*given, **named)  # type: ignore[operator]

    return calls, attempt


def beside(path: Path) -> list[str]:
    """What else lies in the file's folder."""
    return sorted(each.name for each in path.parent.iterdir() if each != path)


def test_a_replace_puts_the_whole_new_content_in_place_and_leaves_nothing_beside_it(tmp_path: Path) -> None:
    path = tmp_path / "state" / "gateway.json"
    files.replace(path, '{"pid": 1}\n')
    files.replace(path, b'{"pid": 2}\n')
    assert path.read_text(encoding="utf-8") == '{"pid": 2}\n'
    assert beside(path) == []


def test_a_replace_waits_while_another_program_holds_the_file_then_puts_it_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "gateway.json"
    path.write_text("old\n", encoding="utf-8")
    calls, attempt = refused(2, os.replace)
    monkeypatch.setattr(os, "replace", attempt)
    files.replace(path, "new\n")
    assert (calls[0], path.read_text(encoding="utf-8"), beside(path)) == (3, "new\n", [])


def test_a_reader_holding_the_file_a_moment_delays_a_replace_and_a_remove_but_never_fails_them(tmp_path: Path) -> None:
    path = tmp_path / "connection.json"
    path.write_text("old\n", encoding="utf-8")
    reader = path.open("rb")  # on Windows, Python's own open lets no one delete or replace the file meanwhile
    threading.Timer(0.05, reader.close).start()
    files.replace(path, "new\n")
    assert path.read_text(encoding="utf-8") == "new\n"
    reader = path.open("rb")
    threading.Timer(0.05, reader.close).start()
    assert files.remove(path) is True
    assert not path.exists()


@pytest.mark.usefixtures("quick")
def test_a_replace_never_let_through_raises_and_leaves_the_file_as_it_was_with_nothing_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "gateway.json"
    path.write_text("old\n", encoding="utf-8")
    calls, attempt = refused(1000, os.replace)
    monkeypatch.setattr(os, "replace", attempt)
    with pytest.raises(PermissionError):
        files.replace(path, "new\n")
    assert (calls[0], path.read_text(encoding="utf-8"), beside(path)) == (4, "old\n", [])


def test_an_error_that_is_not_another_programs_hold_is_raised_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "gateway.json"
    calls = [0]

    def full(*given: object) -> None:
        calls[0] += 1
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    with pytest.raises(OSError, match="No space left"):
        files.replace(path, "new\n")
    assert (calls[0], beside(path)) == (1, [])


def test_a_remove_waits_while_another_program_holds_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "gateway.json"
    path.write_text("{}\n", encoding="utf-8")
    calls, attempt = refused(2, Path.unlink)
    monkeypatch.setattr(Path, "unlink", attempt)
    assert files.remove(path) is True
    assert (calls[0], path.exists()) == (3, False)


@pytest.mark.usefixtures("quick")
def test_a_remove_never_let_through_says_so_and_leaves_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "gateway.json"
    path.write_text("{}\n", encoding="utf-8")
    _, attempt = refused(1000, Path.unlink)
    monkeypatch.setattr(Path, "unlink", attempt)
    assert files.remove(path) is False
    assert path.read_text(encoding="utf-8") == "{}\n"


def test_a_remove_of_a_file_that_is_not_there_is_done(tmp_path: Path) -> None:
    assert files.remove(tmp_path / "never.json") is True
