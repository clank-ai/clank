"""Write `constraints.txt`: each dependency Clank installs, at the version `uv.lock` names (decision 0170).

`pyproject.toml` gives each dependency a range, and `uv.lock` the versions the checks ran with. A `uv tool install`
from a Git tag reads no lock, so the installers and `clank update` pass this file to uv (`--constraints`), read at the
release's own tag: every install of a release has the versions that release was tested with, whatever came out since.
It is `uv export` of the lock, the development tools and Clank itself left out, so it can never say other than the
lock; it is generated, never edited by hand, and a test fails when it is out of date (`tests/test_repository.py`).
"""

import shutil
import subprocess
import sys
from pathlib import Path

from tools.generated import write_or_check

OUTPUT = Path("constraints.txt")
COMMAND = "uv run python -m tools.constraints"
HEADER = (
    "# Generated from uv.lock by `uv run python -m tools.constraints`; do not edit it by hand (decision 0170).\n"
    "# The version of each dependency Clank was tested with: the installer and `clank update` install these.\n"
)
EXPORT = ("export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--no-header", "--no-annotate",
          "--format", "requirements-txt")  # fmt: skip


def uv() -> str | None:
    """uv's program, as found on the PATH; None when it is not there."""
    return shutil.which("uv")


def render(root: Path) -> str:
    """The file's text: its header, then `uv export` of the lock, one pinned requirement a line."""
    program = uv()
    if program is None:
        raise RuntimeError("uv is not on the PATH: it writes constraints.txt from uv.lock")
    said = subprocess.run([program, *EXPORT], cwd=root, capture_output=True, check=True)
    lines = [line.strip() for line in said.stdout.decode("utf-8").splitlines()]
    return HEADER + "".join(f"{line}\n" for line in lines if line and not line.startswith("#"))


def main(argv: list[str] | None = None) -> int:
    """Write constraints.txt, or with `--check` only report whether it is up to date; returns the exit status."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(__file__).resolve().parents[1]
    return write_or_check(root / OUTPUT, render(root), check="--check" in args, command=COMMAND)


if __name__ == "__main__":
    sys.exit(main())
