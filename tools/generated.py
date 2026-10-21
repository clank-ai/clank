"""Write a generated document, or check that the copy in the repository is up to date.

Generated documents (the code map, the tests page) are committed, so they can be read on GitHub, and by a model,
without running anything. They are written with LF line endings on every platform, so a document generated on Windows
and one generated on Linux are the same file.
"""

import sys
from pathlib import Path


def write_or_check(target: Path, text: str, *, check: bool, command: str) -> int:
    """Write `text` to `target`, or with `check` only compare them; returns the exit status for the command line."""
    if check:
        current = target.read_bytes().decode("utf-8") if target.exists() else None
        if current != text:
            print(f"{target.name} is out of date: run `{command}`", file=sys.stderr)
            return 1
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    print(f"wrote {target.name}")
    return 0
