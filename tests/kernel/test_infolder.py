"""Design 0004 §3: Clank reads and writes a workspace's folder only below the folder and never through a link the
agent could have made there, even one it makes while Clank is at work: a name that is absolute or climbs out with ..,
or a link on the way (a symbolic link, a Windows junction), is refused; a file is written whole under a name of its own
and then put in place, so a link in its name is replaced, never written through; a folder swapped for a link while
Clank reads and writes never takes it outside (decisions 0159 and 0164)."""

import contextlib
import os
import shutil
import sys
import threading
from pathlib import Path

import pytest

from clank.kernel import infolder
from clank.kernel.infolder import Outside, place

ROUNDS = 250


def _link_folder(link: Path, target: Path) -> None:
    """A link to a folder: a junction on Windows (any user may make one), else a symbolic link."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _link_file(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("this machine makes no symbolic links for its user")


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path]:
    """A workspace's folder, and a folder beside it that holds the owner's own file."""
    folder, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    (folder / ".clank").mkdir(parents=True)
    elsewhere.mkdir()
    (elsewhere / "secret").write_text("the owner's", encoding="utf-8")
    return folder, elsewhere


def test_a_place_below_the_folder_is_read_and_written_there_its_folders_made(tmp_path: Path) -> None:
    kept = place(tmp_path, ".clank/artifacts/plot/v1/index.html")
    assert kept.relative == ".clank/artifacts/plot/v1/index.html"
    assert kept.path == tmp_path / ".clank" / "artifacts" / "plot" / "v1" / "index.html"
    assert not kept.is_file()
    assert kept.stat() is None
    kept.write_text("<p>plot</p>")
    assert (tmp_path / ".clank/artifacts/plot/v1/index.html").read_text(encoding="utf-8") == "<p>plot</p>"
    assert kept.read_text() == "<p>plot</p>"
    assert kept.read_bytes(most=3) == b"<p>"
    assert kept.is_file()
    assert not kept.is_folder()
    assert kept.parent.is_folder()
    kept.write_text("<p>again</p>")
    assert kept.read_text() == "<p>again</p>", "written whole, in place of the old"
    assert [name for name, _ in kept.parent.entries()] == ["index.html"], "no part file is left behind"
    assert place(tmp_path, r".clank\jobs\3\log") == place(tmp_path, ".clank/jobs/3/log")
    assert place(tmp_path, "./a/./b").relative == "a/b"
    assert (place(tmp_path, ".clank") / "jobs" / "3").relative == ".clank/jobs/3"


def test_a_new_file_is_written_only_when_nothing_has_its_name(tmp_path: Path) -> None:
    copy = place(tmp_path, ".clank/annotations/plot-1.png")
    copy.write_bytes(b"first", new=True)
    with pytest.raises(FileExistsError):
        copy.write_bytes(b"second", new=True)
    assert copy.read_bytes() == b"first"


@pytest.mark.parametrize(
    "named", ["/etc/passwd", r"D:\outside\notes.txt", "../outside", "a/../../b", "notes.txt:hidden", "a/\0b"]
)
def test_a_name_that_is_absolute_or_climbs_out_is_refused(tmp_path: Path, named: str) -> None:
    with pytest.raises(Outside):
        place(tmp_path, named)


@pytest.mark.skipif(sys.platform != "win32", reason="device names and trailing dots are Windows' own")
@pytest.mark.parametrize("named", ["NUL", "logs/con.txt", "COM1", "conout$", "folder./file", "file "])
def test_on_windows_a_device_or_a_name_windows_would_change_is_refused(tmp_path: Path, named: str) -> None:
    with pytest.raises(Outside):
        place(tmp_path, named)


def test_a_link_to_a_folder_anywhere_on_the_way_is_refused_for_every_use(project: tuple[Path, Path]) -> None:
    folder, elsewhere = project
    _link_folder(folder / ".clank" / "artifacts", elsewhere)
    secret = place(folder, ".clank/artifacts/secret")
    with pytest.raises(Outside, match="is a link"):
        secret.read_text()
    with pytest.raises(Outside):
        place(folder, ".clank/artifacts/new-file").write_text("written")
    with pytest.raises(Outside):
        place(folder, ".clank/artifacts/deeper/still").make()
    with pytest.raises(Outside):
        secret.remove()
    assert not secret.is_file()
    assert secret.stat() is None
    assert place(folder, ".clank/artifacts").entries() == []
    assert place(folder, ".clank/artifacts").files() == []
    assert [name for name, _ in place(folder, ".clank").entries()] == [], "the link is left out of its folder's list"
    assert sorted(each.name for each in elsewhere.iterdir()) == ["secret"], "nothing written outside"
    assert (elsewhere / "secret").read_text(encoding="utf-8") == "the owner's"


def test_a_link_in_a_files_own_name_is_never_read_and_is_replaced_when_written(project: tuple[Path, Path]) -> None:
    folder, elsewhere = project
    _link_file(folder / ".clank" / "log", elsewhere / "secret")
    log = place(folder, ".clank/log")
    with pytest.raises(Outside):
        log.read_text()
    assert not log.is_file()
    with pytest.raises(FileExistsError):
        log.write_text("new", new=True)
    log.write_text("Clank's own")
    assert not (folder / ".clank" / "log").is_symlink(), "the link itself was replaced"
    assert log.read_text() == "Clank's own"
    assert (elsewhere / "secret").read_text(encoding="utf-8") == "the owner's", "never written through"


def test_a_folders_files_are_listed_below_it_without_links_and_without_the_folders_skipped(
    project: tuple[Path, Path],
) -> None:
    folder, elsewhere = project
    root = place(folder, "")
    place(folder, "results/sweep.json").write_text("{}")
    place(folder, "results/plots/a.png").write_bytes(b"png")
    place(folder, "node_modules/x.js").write_text("x")
    _link_folder(folder / "results" / "out", elsewhere)
    listed = dict(place(folder, "results").entries())
    assert listed == {"sweep.json": "file", "plots": "folder"}
    below = [name for name, _ in root.files(skip={"node_modules", ".clank"})]
    assert sorted(below) == ["results/plots/a.png", "results/sweep.json"]
    assert all(info.st_size >= 1 for _, info in root.files(skip={"node_modules"}))
    assert len(root.files(most=1)) == 1, "at most the entries asked for are looked at"


def test_a_file_is_removed_and_a_missing_one_says_so(tmp_path: Path) -> None:
    gone = place(tmp_path, ".clank/boards/b/history/1.board")
    gone.write_text("{}")
    assert gone.remove() is True
    assert gone.remove() is False
    assert not gone.is_file()


def test_a_folder_swapped_for_a_link_while_clank_works_never_takes_it_outside(project: tuple[Path, Path]) -> None:
    folder, elsewhere = project
    real, aside = folder / ".clank" / "jobs", folder / ".clank" / "jobs-aside"
    real.mkdir()
    stop = threading.Event()
    swaps = 0

    def swap() -> None:  # the agent's side: the folder, then a link in its place, then the folder again
        nonlocal swaps
        while not stop.is_set():
            try:
                os.rename(real, aside)
                _link_folder(real, elsewhere)
                if sys.platform == "win32":
                    os.rmdir(real)  # a junction goes as a folder does, its target untouched
                else:
                    os.unlink(real)
                os.rename(aside, real)
                swaps += 1
            except OSError:  # Clank holds the folder, or made it again meanwhile: the agent tries again
                if aside.is_dir() and not os.path.lexists(real):
                    os.rename(aside, real)
                elif aside.is_dir():
                    shutil.rmtree(aside, ignore_errors=True)

    agent = threading.Thread(target=swap, daemon=True)
    agent.start()
    read: list[str] = []
    try:
        for round_ in range(ROUNDS):
            with contextlib.suppress(Outside, OSError):
                place(folder, ".clank/jobs/out.txt").write_text(f"round {round_}")
            with contextlib.suppress(Outside, OSError):
                read.append(place(folder, ".clank/jobs/secret").read_text())
    finally:
        stop.set()
        agent.join(timeout=10)
    assert sorted(each.name for each in elsewhere.iterdir()) == ["secret"], "nothing written outside, ever"
    assert "the owner's" not in read, "nothing read from outside, ever"
    assert swaps > 0 or sys.platform == "win32", "the agent's side did swap the folder"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows holds each folder on the way; POSIX opens from it")
def test_on_windows_a_folder_on_the_way_cannot_be_renamed_while_clank_holds_it(project: tuple[Path, Path]) -> None:
    folder, _ = project
    place(folder, ".clank/jobs/1/log").write_text("started")
    with infolder.held(folder, (".clank", "jobs", "1")):
        with pytest.raises(PermissionError):
            os.rename(folder / ".clank" / "jobs", folder / ".clank" / "moved")
        with pytest.raises(PermissionError):
            os.rename(folder / ".clank" / "jobs" / "1", folder / ".clank" / "jobs" / "2")
    os.rename(folder / ".clank" / "jobs", folder / ".clank" / "moved")  # let go: the agent may move it again
