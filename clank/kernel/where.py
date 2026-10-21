"""Where the owner is (design 0013 §15, decision 0099): what a client's own environment says of the terminal it runs in,
so the console and the `clank` command open a planning session where the owner sits.

Over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set, as OpenSSH sets them, Windows' own server too) the owner sits
at another computer: everything opens in that terminal, never on this PC's own screen (a VS Code window there would be
seen by no one). In VS Code's integrated terminal (`TERM_PROGRAM` is `vscode`) the owner sits in VS Code. Only the
client knows its own environment, so the choice is the client's, and the service opens where it is told. It lives in
the kernel because the console's pages and the commands both use it, and neither may import the other.

From the console (decision 0100), a planning never takes the console's terminal (`console_opening`): over SSH nothing
opens and a message says how to attach from another terminal; at the PC in Windows Terminal (`WT_SESSION`), its window
is split and OpenCode runs in the new pane on the right (`split_argv`, Windows Terminal's documented command line: `-w
0` the current window, `split-pane -V` side by side, `-d` the pane's folder, then its command, each `;` escaped since
`wt` reads it as a separator; `--home` when `CLANK_HOME` is set, since the new pane has Windows Terminal's environment,
not the console's), run by `launch_split` without a console window of its own; in VS Code's terminal, VS Code;
elsewhere, the message.
"""

import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence

which = shutil.which
SPLIT_SECONDS = 10.0  # how long `wt` may take to hand the split to Windows Terminal
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

SSH = ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")
HERE, VSCODE = "here", "vscode"


def over_ssh(env: Mapping[str, str]) -> bool:
    """Whether the terminal is reached over SSH."""
    return any(env.get(name) for name in SSH)


def in_vscode(env: Mapping[str, str]) -> bool:
    """Whether the terminal is VS Code's own."""
    return env.get("TERM_PROGRAM") == "vscode"


def console_opening(env: Mapping[str, str]) -> str:
    """Where OpenCode opens when the console starts a planning (decision 0100): `message` over SSH (nothing on this PC's
    screen); `vscode` in VS Code's terminal; `split` in Windows Terminal; else `message`."""
    if over_ssh(env):
        return "message"
    if in_vscode(env):
        return VSCODE
    if env.get("WT_SESSION"):
        return "split"
    return "message"


def split_argv(folder: str, workspace: str, python: str, env: Mapping[str, str]) -> list[str]:
    """Windows Terminal's command that splits its current window, `clank flow attach` in the new pane on the right."""
    home = env.get("CLANK_HOME")
    command = [python, "-m", "clank", "flow", "attach", "--workspace", workspace, *(["--home", home] if home else [])]
    return ["wt", "-w", "0", "split-pane", "-V", "-d", *(part.replace(";", "\\;") for part in [folder, *command])]


def launch_split(argv: Sequence[str]) -> str:
    """Run Windows Terminal's split (no console window of its own): "" once it handed the split over, else why not."""
    program = which(argv[0])
    if program is None:
        return "Windows Terminal's wt is not on the PATH"
    try:
        status = run_wt([program, *argv[1:]])
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"wt did not answer: {error}"
    return "" if status == 0 else f"wt refused the split (exit {status})"


def run_wt(argv: Sequence[str]) -> int:
    """Run `wt` itself, without a console window of its own; its exit status."""
    done = subprocess.run(list(argv), capture_output=True, timeout=SPLIT_SECONDS, creationflags=NO_WINDOW, check=False)
    return done.returncode


def where_to_open(asked: str, env: Mapping[str, str]) -> tuple[str, str]:
    """Where to open what the owner talks to: `here` (this terminal) or `vscode` (Clank's VS Code window), and what to
    say when it is not where `asked` ("" for where the owner is): over SSH always here; else as asked; else in VS Code
    when this terminal is VS Code's, else here."""
    if over_ssh(env):
        said = (
            "over SSH, the planning opens here, in this terminal: a VS Code window would open on the PC's own screen"
            if asked == VSCODE
            else ""
        )
        return HERE, said
    if asked in (HERE, VSCODE):
        return asked, ""
    return (VSCODE if in_vscode(env) else HERE), ""
