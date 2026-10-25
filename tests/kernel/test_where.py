"""Design 0013 §15 (decision 0099): where a planning opens is where the owner is, as the console's or the command's own
environment says: over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set), always in that terminal, whatever asked
for VS Code, said so, since VS Code would open on the PC's own screen; else what was asked; else in VS Code when the
console runs in VS Code's terminal (`TERM_PROGRAM`), else here. From the console (decision 0100), a planning never
takes the console's terminal: over SSH nothing opens (a message says how to attach), in Windows Terminal its window is
split with `wt -w 0 split-pane -V -d <folder> <python> -m clank flow attach --workspace <W>` (`--home` when
`CLANK_HOME` is set, `;` escaped), in VS Code's terminal VS Code, elsewhere the message; a split that cannot run says
why.

Design 0018 §8.1: a terminal of VS Code's Remote-SSH on this machine (VS Code's remote command, `code` under a
`remote-cli` folder, on the path, and `VSCODE_IPC_HOOK_CLI` set) is where VS Code opens, on the other computer, the
service sent the command and its window's pipe; any other SSH terminal opens VS Code nowhere, and the command to run on
the other computer is said (`code --folder-uri` with the PC's folder as Remote-SSH names it, on the host the settings
name, else the address the session came in on); elsewhere it opens here, on the PC."""

import pytest

from clank.kernel import where
from clank.kernel.where import (
    console_opening,
    over_ssh,
    remote_code,
    split_argv,
    ssh_command,
    vscode_place,
    vscode_request,
    where_to_open,
)

SSH = {"SSH_CONNECTION": "10.0.0.2 51022 10.0.0.9 22"}


@pytest.mark.parametrize("name", ["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"])
def test_any_of_ssh_s_variables_says_the_terminal_is_over_ssh(name: str) -> None:
    assert over_ssh({name: "set"})
    assert not over_ssh({name: ""})
    assert not over_ssh({"TERM_PROGRAM": "vscode"})


def test_over_ssh_it_opens_in_this_terminal_whatever_asked_for_vs_code_and_says_why() -> None:
    assert where_to_open("", SSH) == ("here", "")
    assert where_to_open("here", SSH) == ("here", "")
    where, said = where_to_open("vscode", {**SSH, "TERM_PROGRAM": "vscode"})
    assert where == "here"
    assert "over SSH" in said
    assert "the PC's own screen" in said
    assert where_to_open("", {**SSH, "TERM_PROGRAM": "vscode"}) == ("here", ""), "VS Code's terminal reached over SSH"


def test_elsewhere_it_opens_where_asked_else_in_vs_code_when_the_console_runs_there_else_here() -> None:
    assert where_to_open("vscode", {}) == ("vscode", "")
    assert where_to_open("here", {"TERM_PROGRAM": "vscode"}) == ("here", "")
    assert where_to_open("", {"TERM_PROGRAM": "vscode"}) == ("vscode", "")
    assert where_to_open("", {"TERM_PROGRAM": "WezTerm"}) == ("here", "")
    assert where_to_open("", {}) == ("here", "")


def test_from_the_console_over_ssh_nothing_opens_whatever_else_is_set() -> None:
    assert console_opening({**SSH, "WT_SESSION": "a", "TERM_PROGRAM": "vscode"}) == "message"


def test_from_the_console_windows_terminal_is_split_vs_codes_terminal_opens_vs_code_elsewhere_the_message() -> None:
    assert console_opening({"WT_SESSION": "0f3a"}) == "split"
    assert console_opening({"TERM_PROGRAM": "vscode"}) == "vscode"
    assert console_opening({"TERM_PROGRAM": "WezTerm"}) == "message"
    assert console_opening({}) == "message"


def test_windows_terminals_split_is_its_documented_command_line_with_clanks_home_and_semicolons_escaped() -> None:
    python = r"C:\work\.venv\Scripts\python.exe"
    argv = split_argv(r"C:\work\study; two", "myproject", python, {})
    assert argv == ["wt", "-w", "0", "split-pane", "-V", "-d", r"C:\work\study\; two",
                    python, "-m", "clank", "flow", "attach", "--workspace", "myproject"]  # fmt: skip
    homed = split_argv(r"C:\work", "myproject", python, {"CLANK_HOME": r"D:\clank"})
    assert homed[-2:] == ["--home", r"D:\clank"], "a new pane does not inherit the console's environment"


def test_a_split_that_cannot_run_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(where, "which", lambda name: None)
    assert "wt is not on the PATH" in where.launch_split(["wt", "-w", "0", "split-pane"])
    monkeypatch.setattr(where, "which", lambda name: "wt.exe")
    monkeypatch.setattr(where, "run_wt", lambda argv: 1)
    assert where.launch_split(["wt", "-w", "0", "split-pane"]) == "wt refused the split (exit 1)"
    monkeypatch.setattr(where, "run_wt", lambda argv: 0)
    assert where.launch_split(["wt", "-w", "0", "split-pane"]) == ""


REMOTE_CODE = r"D:\vscode\.vscode-server\cli\servers\Stable-1\server\bin\remote-cli\code.cmd"
REMOTE = {**SSH, "TERM_PROGRAM": "vscode", "VSCODE_IPC_HOOK_CLI": r"\\.\pipe\vscode-ipc-1.sock"}


def test_a_vs_code_remote_ssh_terminal_opens_vs_code_on_the_other_computer() -> None:
    def remote(name: str) -> str | None:
        return REMOTE_CODE if name == "code" else None

    assert remote_code(REMOTE, remote) == REMOTE_CODE
    assert vscode_place(REMOTE, remote) == "remote"
    assert console_opening(REMOTE, remote) == "vscode", "a planning opens there too"
    assert where_to_open("", REMOTE, remote) == ("vscode", "")
    assert where_to_open("here", REMOTE, remote) == ("here", "")


def test_from_a_remote_ssh_terminal_the_service_is_sent_vs_codes_remote_command_and_its_windows_pipe() -> None:
    def remote(name: str) -> str | None:
        return REMOTE_CODE if name == "code" else None

    assert vscode_request(r"D:\work\paper", REMOTE, look=remote) == {
        "folder": r"D:\work\paper",
        "remote": {"code": REMOTE_CODE, "hook": REMOTE["VSCODE_IPC_HOOK_CLI"]},
    }
    assert vscode_request(r"D:\work\paper", {}, "PLAN.md", look=remote) == {
        "folder": r"D:\work\paper",
        "file": "PLAN.md",
    }


def test_from_any_other_ssh_terminal_the_command_for_the_other_computer_names_the_pcs_folder() -> None:
    assert ssh_command(r"C:\Research\paper", SSH, "") == (
        'code --folder-uri "vscode-remote://ssh-remote+10.0.0.9/c:/Research/paper"'
    ), "the address the SSH session came in on"
    assert ssh_command(r"D:\Research\my paper", SSH, "lab-pc") == (
        'code --folder-uri "vscode-remote://ssh-remote+lab-pc/d:/Research/my%20paper"'
    ), "the host the settings name, the folder's parts quoted"
    assert ssh_command("/srv/research/paper", {"SSH_TTY": "/dev/pts/1"}, "") == (
        'code --folder-uri "vscode-remote://ssh-remote+THIS-PC/srv/research/paper"'
    ), "no address known: a placeholder to replace"


def test_any_other_ssh_terminal_opens_vs_code_nowhere_and_the_pc_opens_it_here() -> None:
    def desktop(name: str) -> str | None:
        return r"C:\Program Files\Microsoft VS Code\bin\code.cmd" if name == "code" else None

    assert vscode_place(SSH, desktop) == "ssh"
    assert vscode_place({**SSH, "TERM_PROGRAM": "vscode"}, desktop) == "ssh", "no remote command: not Remote-SSH's"
    assert remote_code({"VSCODE_IPC_HOOK_CLI": "x"}, desktop) is None, "VS Code's own terminal on the PC"
    assert vscode_place({"TERM_PROGRAM": "vscode", "VSCODE_IPC_HOOK_CLI": "x"}, desktop) == "here"
    assert vscode_place({}, desktop) == "here"
