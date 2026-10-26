"""Run every check that continuous integration runs, in one command: formatting, lint, types, the VS Code extension
and the tests.

`uv run python -m tools.check` runs them all and names each one that fails, so one run shows every problem. With
`--fix` it first rewrites what can be rewritten safely: the formatting, Ruff's safe fixes, and the generated files (the
settings schemas, the extension's TypeScript types, the events page, the API page, the code map, the tests page). The
extension is compiled and tested before the tests, which run its client against a real service. Continuous integration
runs this same module (`.github/workflows/checks.yml`), so passing here means passing there. The types are checked
twice, as on Windows and as on Linux (each with its own cache), because the type checker skips code under the other
platform's `if sys.platform` and CI checks Windows only for pull requests and tags. The tests include the repository's
own checks (`tests/test_repository.py`): links, indexes, secrets, spelling, and the colors and marks written in the
console's code.
"""

import subprocess
import sys
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], int]

FIXES: list[tuple[str, list[str]]] = [
    ("formatting", [sys.executable, "-m", "ruff", "format", "."]),
    ("safe lint fixes", [sys.executable, "-m", "ruff", "check", "--fix", "."]),
    ("schemas", [sys.executable, "-m", "tools.schemas"]),
    ("TypeScript types", [sys.executable, "-m", "tools.tstypes"]),
    ("events page", [sys.executable, "-m", "tools.eventsdoc"]),
    ("API page", [sys.executable, "-m", "tools.apidoc"]),
    ("code map", [sys.executable, "-m", "tools.codemap"]),
    ("tests page", [sys.executable, "-m", "tools.testspage"]),
]
CHECKS: list[tuple[str, list[str]]] = [
    ("formatting", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("types as on Windows", [sys.executable, "-m", "mypy", "--platform", "win32", "--cache-dir", ".mypy_cache/win32"]),
    ("types as on Linux", [sys.executable, "-m", "mypy", "--platform", "linux", "--cache-dir", ".mypy_cache/linux"]),
    ("VS Code extension", [sys.executable, "-m", "tools.extension"]),
    (
        "phone app tests",
        ["node", "--test", "tests/phone/model.test.mjs", "tests/phone/flows.test.mjs", "tests/phone/talk.test.mjs"],
    ),
    ("tests", [sys.executable, "-m", "pytest", "-q"]),
]


def run(command: Sequence[str]) -> int:
    """Run one command, its output going straight to the terminal; returns its exit status."""
    return subprocess.run(list(command), check=False).returncode


def main(argv: Sequence[str] | None = None, runner: Runner = run) -> int:
    """Run the fixes (with `--fix`), then every check; returns 1 when any of them failed."""
    args = list(sys.argv[1:] if argv is None else argv)
    steps = (FIXES if "--fix" in args else []) + CHECKS
    failed: list[str] = []
    for name, command in steps:
        print(f"== {name}", flush=True)
        if runner(command) != 0:
            failed.append(name)
    print(f"== failed: {', '.join(failed)}" if failed else "== every check passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
