"""VS Code on another computer (design 0018 §8): from a terminal of VS Code's Remote-SSH on this PC, a folder opens in
a new window of the other computer's VS Code, connected to this PC. VS Code's remote command in that terminal (`code`
under the `remote-cli` folder of VS Code's server) does it, talking back to its window through the pipe that
`VSCODE_IPC_HOOK_CLI` names. Only the client's terminal has both, so the client sends them (`POST /agents/vscode`,
`remote`), and the service runs the command in the operation `agents.vscode` (`vscode.py`), followed and logged as on
the PC.

- The command is run as its `code.cmd` runs it on Windows (`remote_argv`): the Node of VS Code's server with its
  `server-cli.js` and the version the script names, so no folder's name goes through cmd.exe, which would read `&` or
  `%` in it; elsewhere the command itself.
- The request names a program, so the service runs only VS Code's remote command of its own user's VS Code server
  (`~/.vscode-server`, or the Insiders' one) and refuses any other (`remote_command`).
- The server's machine settings (`data/Machine/settings.json` in that folder, `machine_settings`) get Clank's, as the
  window's user settings do on the PC.
"""

import re
from pathlib import Path

SERVERS = (".vscode-server", ".vscode-server-insiders")  # VS Code's server folders, in the user's home
NAMES = ("code", "code.cmd")
ROOT_DIR = re.compile(r"^set ROOT_DIR=%~dp0(.*?)\s*$", re.MULTILINE)  # the server's folder, from the script's own
CALL = re.compile(r'^call\s+((?:"[^"]*"\s+)+)%\*', re.MULTILINE)  # what the script runs, with its arguments
QUOTED = re.compile(r'"([^"]*)"')
ROOT = "%ROOT_DIR%\\"


def server_root(code: str) -> Path | None:
    """VS Code's server folder that a remote command belongs to (`.vscode-server`); None when it is in none."""
    return next((folder for folder in Path(code).parents if folder.name in SERVERS), None)


def remote_argv(code: str) -> list[str]:
    """How VS Code's remote command is run: on Windows what its `code.cmd` runs (the server's Node, its server-cli.js,
    and the arguments the script gives before the caller's), else, or when the script is not as VS Code writes it, the
    command itself."""
    script = Path(code)
    if script.suffix.lower() != ".cmd":
        return [code]
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [code]
    root, call = ROOT_DIR.search(text), CALL.search(text)
    if root is None or call is None:
        return [code]
    folder = script.parent
    for part in root.group(1).split("\\"):
        folder = folder.parent if part == ".." else folder / part if part else folder
    argv = [
        str(folder.joinpath(*argument[len(ROOT) :].split("\\"))) if argument.startswith(ROOT) else argument
        for argument in QUOTED.findall(call.group(1))
    ]
    return [code] if any("%" in argument for argument in argv) else argv


def remote_command(code: str, home: Path) -> list[str] | None:
    """How to run the remote command a client named, when it is VS Code's remote command of the server in `home` (the
    service's user's): `code` or `code.cmd` in a `remote-cli` folder of `~/.vscode-server`, named whole, without `..`;
    None for any other program."""
    path = Path(code)
    root = server_root(code)
    if not path.is_absolute() or ".." in path.parts or root is None or root.parent != home:
        return None
    if path.name.lower() not in NAMES or path.parent.name != "remote-cli":
        return None
    return remote_argv(code)


def machine_settings(code: str) -> Path | None:
    """The machine settings of the VS Code server a remote command belongs to; None when it is in no server folder."""
    root = server_root(code)
    return root / "data" / "Machine" / "settings.json" if root is not None else None
