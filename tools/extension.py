"""Check the VS Code extension: install its tools from their lock when needed, then compile and test it (decision
0028); with `--host`, also run its suite inside a real VS Code (decision 0029).

`tools.check` runs this, so a working copy checks the extension as continuous integration does. The tools are
installed with `npm ci` (exactly what `vscode/package-lock.json` says) when `vscode/node_modules` is missing or older
than the lock; then `npm run check` compiles the extension and runs its tests. npm comes with Node; without it, this
says what to install and fails. The host suite (`npm run test:host`) opens a VS Code window, so it runs only when asked:
CI asks on Linux, where a machine without a display runs it under a virtual one (`xvfb-run`).
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "vscode"
Runner = Callable[[Sequence[str], Path], int]


def run(command: Sequence[str], folder: Path) -> int:
    """Run a command in a folder, its output going straight to the terminal."""
    return subprocess.run(list(command), cwd=folder, check=False).returncode


def has_display() -> bool:
    """Whether a window can open here: always on Windows and macOS; on Linux, when a display is set."""
    return sys.platform != "linux" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def check(
    folder: Path = FOLDER,
    which: Callable[[str], str | None] = shutil.which,
    runner: Runner = run,
    *,
    host: bool = False,
    display: bool | None = None,
) -> int:
    """Install the extension's tools if need be, then compile and test it (and, with `host`, run its suite inside VS
    Code); 1 when anything failed."""
    npm = which("npm")
    if npm is None:
        print("The VS Code extension needs Node 22 or newer, with npm (nodejs.org), to be compiled and tested.")
        return 1
    lock = folder / "package-lock.json"
    installed = folder / "node_modules" / ".package-lock.json"
    stale = not installed.exists() or installed.stat().st_mtime < lock.stat().st_mtime
    if stale and runner([npm, "ci", "--no-audit", "--no-fund"], folder) != 0:
        return 1
    if runner([npm, "run", "check"], folder) != 0:
        return 1
    if not host:
        return 0
    suite = [npm, "run", "test:host"]
    if not (has_display() if display is None else display):
        suite = ["xvfb-run", "-a", *suite]
    return 1 if runner(suite, folder) != 0 else 0


if __name__ == "__main__":
    sys.exit(check(host="--host" in sys.argv[1:]))
