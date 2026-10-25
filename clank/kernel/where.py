"""Where the owner is (design 0013 §15, decision 0099): what a client's own environment says of the terminal it runs in,
so the console and the `clank` command open a planning session where the owner sits.

Over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set, as OpenSSH sets them, Windows' own server too) the owner sits
at another computer: everything opens in that terminal, never on this PC's own screen (a VS Code window there would be
seen by no one), except in a terminal of VS Code's Remote-SSH (design 0018 §8): VS Code's remote command on the path
(`code` under a `remote-cli` folder of VS Code's server, `remote_code`) with `VSCODE_IPC_HOOK_CLI` set, which opens VS
Code on the other computer, connected to this one (`vscode_place`: `remote`; `vscode_request` sends the service the
command and its window's pipe). From any other SSH terminal VS Code opens nowhere, and `ssh_command` says what to run
on the other computer. In VS Code's integrated terminal (`TERM_PROGRAM` is `vscode`) the owner sits in VS Code. Only
the client knows its own environment, so the choice is the client's, and the service opens where it is told. It lives
in the kernel because the console's pages and the commands both use it, and neither may import the other.

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
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

which = shutil.which
SPLIT_SECONDS = 10.0  # how long `wt` may take to hand the split to Windows Terminal
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

SSH = ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")
HERE, VSCODE = "here", "vscode"
REMOTE, OVER_SSH = "remote", "ssh"  # where VS Code opens: on the other computer, or nowhere (design 0018 §8)
PLACEHOLDER = "THIS-PC"  # the PC's name in the other computer's SSH configuration, when none is known
Look = Callable[[str], str | None]


def over_ssh(env: Mapping[str, str]) -> bool:
    """Whether the terminal is reached over SSH."""
    return any(env.get(name) for name in SSH)


def in_vscode(env: Mapping[str, str]) -> bool:
    """Whether the terminal is VS Code's own."""
    return env.get("TERM_PROGRAM") == "vscode"


def remote_code(env: Mapping[str, str], look: Look | None = None) -> str | None:
    """VS Code's remote command, when this terminal is one of VS Code's Remote-SSH on this machine: `code` found under a
    `remote-cli` folder, with `VSCODE_IPC_HOOK_CLI` set (the window it talks back to); else None."""
    if not env.get("VSCODE_IPC_HOOK_CLI"):
        return None
    found = (look or which)("code")
    if not found:
        return None
    folders = {*PureWindowsPath(found).parts, *PurePosixPath(found).parts}
    return found if "remote-cli" in folders else None


def vscode_place(env: Mapping[str, str], look: Look | None = None) -> str:
    """Where VS Code opens for the owner (design 0018 §8.1): `remote` from a VS Code Remote-SSH terminal (on the other
    computer), `ssh` from any other SSH terminal (nowhere: the command to run there is said), else `here` (on the
    PC)."""
    if remote_code(env, look):
        return REMOTE
    return OVER_SSH if over_ssh(env) else HERE


def vscode_request(folder: str, env: Mapping[str, str], file: str = "", look: Look | None = None) -> dict[str, Any]:
    """What a client asks of `POST /agents/vscode` from this terminal: the folder, a file of it when one is named, and
    from a VS Code Remote-SSH terminal VS Code's remote command with the pipe of its window (design 0018 §8.1), which
    only this terminal has."""
    body: dict[str, Any] = {"folder": folder, **({"file": file} if file else {})}
    code = remote_code(env, look)
    if code:
        body["remote"] = {"code": code, "hook": env["VSCODE_IPC_HOOK_CLI"]}
    return body


def folder_uri(folder: str, host: str) -> str:
    """A folder of this PC as VS Code's Remote-SSH names it: `vscode-remote://ssh-remote+HOST/c:/path` (a Windows
    drive in lowercase, as VS Code writes it), its parts quoted."""
    windows = PureWindowsPath(folder)
    if windows.drive.endswith(":") and windows.root:
        path = "/" + windows.drive.lower() + "/" + "/".join(windows.parts[1:])
    else:
        path = PurePosixPath(folder).as_posix()
    return f"vscode-remote://ssh-remote+{host}{quote(path, safe='/:')}"


def ssh_command(folder: str, env: Mapping[str, str], host: str) -> str:
    """What to run on the other computer to open a folder of this PC in its VS Code over Remote-SSH (design 0018 §8.1):
    `code --folder-uri`, on the host named (the setting `ssh_host`), else the address this SSH session came in on
    (`SSH_CONNECTION`'s third field), else a placeholder to replace."""
    address = (env.get("SSH_CONNECTION") or "").split()
    name = host or (address[2] if len(address) > 2 else "") or PLACEHOLDER
    return f'code --folder-uri "{folder_uri(folder, name)}"'


def ssh_said(folder: str, env: Mapping[str, str], host: str, file: str = "") -> str:
    """What a client says over SSH, outside VS Code's Remote-SSH, in place of opening VS Code on the PC's own screen
    (design 0018 §8.1): the command to run on the other computer."""
    then = f", then open {file} in it" if file else ""
    return (
        "over SSH, VS Code would open on the PC's own screen, which no one sees: on your computer, run "
        f"{ssh_command(folder, env, host)}{then} (it needs VS Code's Remote-SSH)"
    )


def console_opening(env: Mapping[str, str], look: Look | None = None) -> str:
    """Where OpenCode opens when the console starts a planning (decision 0100): `vscode` in a terminal of VS Code's
    Remote-SSH (design 0018 §8) or of VS Code itself; `message` over any other SSH (nothing on this PC's screen);
    `split` in Windows Terminal; else `message`."""
    if remote_code(env, look):
        return VSCODE
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


def where_to_open(asked: str, env: Mapping[str, str], look: Look | None = None) -> tuple[str, str]:
    """Where to open what the owner talks to: `here` (this terminal) or `vscode` (Clank's VS Code window, or the other
    computer's from a Remote-SSH terminal, design 0018 §8), and what to say when it is not where `asked` ("" for where
    the owner is): over any other SSH always here; else as asked; else in VS Code when this terminal is VS Code's, else
    here."""
    if over_ssh(env) and not remote_code(env, look):
        said = (
            "over SSH, the planning opens here, in this terminal: a VS Code window would open on the PC's own screen"
            if asked == VSCODE
            else ""
        )
        return HERE, said
    if asked in (HERE, VSCODE):
        return asked, ""
    return (VSCODE if in_vscode(env) else HERE), ""
