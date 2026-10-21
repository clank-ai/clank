"""The repository's files as the checks see them: what git tracks or would track, read as text when they are text.

Asking git for the list means a check sees exactly what a commit would hold (never `.venv/` or caches), including a new
file before it is committed. A folder outside any git repository (a test's sample) is listed whole, but for caches.
"""

import subprocess
from pathlib import Path


def repository_files(root: Path) -> list[Path]:
    """Every file git tracks, or would track, under `root`, relative to it, in a stable order."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
    )
    if listed.returncode != 0:
        found = [path.relative_to(root) for path in root.rglob("*") if path.is_file()]
        return sorted((path for path in found if "__pycache__" not in path.parts), key=lambda path: path.as_posix())
    names = {name for name in listed.stdout.decode("utf-8").split("\0") if name and (root / name).is_file()}
    return sorted((Path(name) for name in names), key=lambda path: path.as_posix())


def read_text(path: Path) -> str | None:
    """The file's text, or None when it is not text (a NUL byte near its start, as in images and archives)."""
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")
