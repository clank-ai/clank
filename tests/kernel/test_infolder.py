"""Design 0004 §3: Clank reads and writes the files it keeps in a workspace's folder only below the folder and never
through a link the agent could have made there: a name that is absolute or climbs out with .., or a link on the way
(a symbolic link, a Windows junction), is refused (decision 0159)."""

import os
import sys
from pathlib import Path

import pytest

from clank.kernel.infolder import Outside, inside, linked


def _link_folder(link: Path, target: Path) -> None:
    """A link to a folder: a junction on Windows (any user may make one), else a symbolic link."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_name_below_the_folder_is_its_path_there_even_before_the_file_is_made(tmp_path: Path) -> None:
    assert inside(tmp_path, ".clank/artifacts/plot/v1/index.html") == tmp_path / ".clank/artifacts/plot/v1/index.html"
    assert inside(tmp_path, r".clank\jobs\3\log") == tmp_path / ".clank" / "jobs" / "3" / "log"
    assert inside(tmp_path, "./a/./b") == tmp_path / "a" / "b"


@pytest.mark.parametrize("named", ["/etc/passwd", r"C:\Users\someone\.ssh\id_ed25519", "../outside", "a/../../b", ""])
def test_a_name_that_is_absolute_or_climbs_out_is_refused(tmp_path: Path, named: str) -> None:
    with pytest.raises(Outside):
        inside(tmp_path, named)


def test_a_link_to_a_folder_anywhere_on_the_way_is_refused(tmp_path: Path) -> None:
    folder, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    (folder / ".clank").mkdir(parents=True)
    elsewhere.mkdir()
    (elsewhere / "secret").write_text("the owner's", encoding="utf-8")
    _link_folder(folder / ".clank" / "artifacts", elsewhere)
    assert linked(folder / ".clank" / "artifacts")
    with pytest.raises(Outside, match="is a link"):
        inside(folder, ".clank/artifacts/secret")
    with pytest.raises(Outside):
        inside(folder, ".clank/artifacts/new-file")
    assert not linked(folder / ".clank"), "a plain folder is no link"
    assert not linked(folder / "not-there")


def test_a_link_to_a_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "target").write_text("the owner's", encoding="utf-8")
    try:
        os.symlink(tmp_path / "target", tmp_path / "log")
    except OSError:
        pytest.skip("this machine makes no symbolic links for its user")
    with pytest.raises(Outside):
        inside(tmp_path, "log")
