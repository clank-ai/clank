"""A fake of VS Code's command line (`code`), for the tests of Clank's VS Code window: a program of its own, so it is
run as Clank runs the real one. Its first argument names a JSON file that keeps what it was asked: every command line,
the extensions installed (with their versions), the folders opened, and the extensions it refuses to install (a test
writes those first). `--list-extensions --show-versions` prints the installed ones as `id@version`;
`--install-extension` installs an id (at 1.0.0) or a `.vsix` (Clank's, at the version its name says) unless refused;
anything else opens its last argument, a folder.
"""

import json
import re
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """Do what VS Code's command line would, as far as the tests need."""
    state_file, arguments = Path(argv[0]), argv[1:]
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    state.setdefault("calls", []).append(arguments)
    installed: dict[str, str] = state.setdefault("installed", {})
    status = 0
    if "--list-extensions" in arguments:
        print("\n".join(f"{name}@{version}" for name, version in sorted(installed.items())))
    elif "--install-extension" in arguments:
        wanted = arguments[arguments.index("--install-extension") + 1]
        found = re.fullmatch(r".*clank-(\d+\.\d+\.\d+)\.vsix", wanted)
        name, version = ("clank.clank", found.group(1)) if found else (wanted.lower(), "1.0.0")
        if wanted in state.get("refuse", []):
            print(f"Failed Installing Extensions: {wanted}", file=sys.stderr)
            status = 1
        else:
            installed[name] = version
            print(f"Extension '{wanted}' was successfully installed.")
    else:
        state.setdefault("opened", []).append(arguments[-1])
    state_file.write_text(json.dumps(state), encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
