"""Design 0002 §2.9: a program Clank starts is the one it means. Clank runs itself again with `python -P -m clank`, so a
folder named clank in the current folder is never imported in place of the installed package; on Windows a program
named without its folder is found on the PATH alone, never in the current folder, which is often a project's, and the
whole process (and every program it starts) is told the same (NoDefaultCurrentDirectoryInExePath)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import clank
from clank.cli import dockergroup
from clank.kernel import processes, where
from clank.kernel.processes import clank_command, found_on_path, resolved, run_answer, search_path_only

WINDOWS = sys.platform == "win32"


def _decoy_package(folder: Path) -> None:
    (folder / "clank").mkdir()
    (folder / "clank" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "clank" / "__main__.py").write_text("print('the decoy ran')\n", encoding="utf-8")


def test_clank_run_again_from_a_folder_holding_a_clank_package_runs_the_installed_one(tmp_path: Path) -> None:
    _decoy_package(tmp_path)
    plain = subprocess.run([sys.executable, "-m", "clank", "--version"], cwd=tmp_path, capture_output=True, text=True)
    assert "the decoy ran" in plain.stdout, "without -P, -m imports the current folder's clank: the test means it"
    done = subprocess.run(clank_command("--version"), cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert done.stdout == f"clank {clank.__version__}\n"


def test_every_way_clank_runs_itself_again_keeps_the_current_folder_off_the_module_path() -> None:
    split = where.split_argv(r"C:\work", "myproject", "python", {})
    assert split[split.index("python") :][:4] == ["python", "-P", "-m", "clank"], "the planning's split pane"
    assert dockergroup.command(["setup"])[3].split()[1:4] == ["-P", "-m", "clank"], "the docker group's run again"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(clank.__file__).parent.rglob("*.py")
        if path.name != "processes.py"
    )
    assert '"-m", "clank"' not in source, "every run of clank again goes through clank_command"


def test_on_windows_a_program_named_alone_is_found_on_the_path_never_in_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    here, listed = tmp_path / "project", tmp_path / "bin"
    here.mkdir()
    listed.mkdir()
    (here / "docker.exe").write_bytes(b"")
    (here / "wt.cmd").write_text("", encoding="utf-8")
    monkeypatch.chdir(here)
    path = os.pathsep.join([os.curdir, "", str(listed)])
    assert found_on_path("docker", path) is None, "the current folder, even named on the PATH as ., is not searched"
    with pytest.raises(FileNotFoundError):
        resolved(["docker", "--version"], platform="win32", path=path)
    (listed / "docker.exe").write_bytes(b"")
    assert resolved(["docker", "--version"], platform="win32", path=path) == [str(listed / "docker.exe"), "--version"]
    assert resolved([str(here / "docker.exe")], platform="win32", path=path) == [str(here / "docker.exe")], "a path"
    assert resolved(["docker"], platform="linux", path=path) == ["docker"], "elsewhere the PATH alone is searched"


def test_the_clank_command_tells_windows_to_keep_the_current_folder_out_of_every_search() -> None:
    environ: dict[str, str] = {}
    search_path_only(environ, platform="win32")
    assert environ == {processes.SEARCH_PATH_ONLY: "1"}
    mine = {processes.SEARCH_PATH_ONLY: "0"}
    search_path_only(mine, platform="win32")
    assert mine[processes.SEARCH_PATH_ONLY] == "0", "the person's own setting is theirs"
    others: dict[str, str] = {}
    search_path_only(others, platform="linux")
    assert others == {}


@pytest.mark.skipif(not WINDOWS, reason="Windows looks in the current folder for a program named alone")
def test_on_windows_a_helper_planted_in_the_current_folder_never_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    shutil.copyfile(system / "hostname.exe", tmp_path / "clank-planted-helper.exe")
    monkeypatch.chdir(tmp_path)
    answer = run_answer(["clank-planted-helper"])
    assert answer.status is None, f"the program in the current folder ran: {answer.output!r}"
    assert "not on the PATH" in answer.errors
    assert (run_answer(["hostname"]).output or "").strip(), "one on the PATH still runs"


def test_the_update_helper_runs_windows_powershell_from_the_systems_folder() -> None:
    assert (
        processes.windows_powershell({"SYSTEMROOT": r"D:\Win"}).lower().startswith(r"d:\win\system32\windowspowershell")
    )
