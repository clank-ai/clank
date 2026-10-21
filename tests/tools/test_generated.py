"""Design 0002 §3.2 (M0.1): a generated document is written with LF line endings on every platform, and `--check`
reports, without writing anything, whether the copy in the repository is up to date."""

from pathlib import Path

import pytest

from tools.generated import write_or_check


def test_writing_uses_lf_line_endings_on_every_platform(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "MAP.md"
    assert write_or_check(target, "a\nb\n", check=False, command="make it") == 0
    assert target.read_bytes() == b"a\nb\n"


def test_check_passes_when_the_copy_matches(tmp_path: Path) -> None:
    target = tmp_path / "MAP.md"
    target.write_bytes(b"same\n")
    assert write_or_check(target, "same\n", check=True, command="make it") == 0


def test_check_fails_names_the_command_and_writes_nothing_when_the_copy_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "MAP.md"
    target.write_bytes(b"old\r\n")
    assert write_or_check(target, "old\n", check=True, command="make it") == 1
    assert "make it" in capsys.readouterr().err
    assert target.read_bytes() == b"old\r\n"


def test_check_fails_when_the_document_is_missing(tmp_path: Path) -> None:
    assert write_or_check(tmp_path / "MAP.md", "text\n", check=True, command="make it") == 1
