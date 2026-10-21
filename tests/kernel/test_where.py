"""Design 0013 §15 (decision 0099): where a planning opens is where the owner is, as the console's or the command's own
environment says: over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set), always in that terminal, whatever asked
for VS Code, said so, since VS Code would open on the PC's own screen; else what was asked; else in VS Code when the
console runs in VS Code's terminal (`TERM_PROGRAM`), else here. From the console (decision 0100), a planning never
takes the console's terminal: over SSH nothing opens (a message says how to attach), in Windows Terminal its window is
split with `wt -w 0 split-pane -V -d <folder> <python> -m clank flow attach --workspace <W>` (`--home` when
`CLANK_HOME` is set, `;` escaped), in VS Code's terminal VS Code, elsewhere the message; a split that cannot run says
why."""

import pytest

from clank.kernel import where
from clank.kernel.where import console_opening, over_ssh, split_argv, where_to_open

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
