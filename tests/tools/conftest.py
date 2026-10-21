"""Shared fixtures for the development tools' tests: a temporary folder holding the files a test describes."""

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_files(tmp_path: Path) -> Callable[[dict[str, str]], Path]:
    """A function that writes files (relative path to text, LF endings) under a temporary folder, and returns it."""

    def write(files: dict[str, str]) -> Path:
        for name, text in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        return tmp_path

    return write
