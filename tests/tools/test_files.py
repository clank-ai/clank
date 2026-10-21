"""Design 0001 §8.4: the checks see exactly the files a commit would hold (tracked, or new and not ignored), and read
as text every file that is text."""

import subprocess
from pathlib import Path

from tools.files import read_text, repository_files


def test_tracked_and_new_files_are_seen_and_ignored_ones_are_not(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "tracked.md").write_text("a\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("b\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "new.md").write_text("c\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.md"], cwd=tmp_path, check=True)
    assert repository_files(tmp_path) == [Path(".gitignore"), Path("docs/new.md"), Path("tracked.md")]


def test_a_file_with_a_nul_byte_is_not_text(tmp_path: Path) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00\x01")
    assert read_text(tmp_path / "image.png") is None


def test_text_that_is_not_utf8_is_still_read(tmp_path: Path) -> None:
    (tmp_path / "old.txt").write_bytes(b"caf\xe9\n")
    assert read_text(tmp_path / "old.txt") == "caf�\n"


def test_a_folder_outside_git_is_listed_whole_but_for_caches(tmp_path: Path) -> None:
    (tmp_path / "clank" / "__pycache__").mkdir(parents=True)
    (tmp_path / "clank" / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "clank" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    assert repository_files(tmp_path) == [Path("clank/a.py")]
