"""Design 0001 §7.2: CLANK_HOME's secrets/ and state/ can be opened only by the user Clank runs as, whatever the folder
above them allows (decision 0167). On Windows `Home.ensure` gives each an access list of its own, inheritance from the
folder above turned off, with full control for the user and SYSTEM alone, inherited by everything made inside; it reads
the list first and writes nothing when it is already so. On Linux and macOS each is mode 0700.

The Windows tests read the lists with Windows' own `icacls /save` (SDDL) and the user's SID with `whoami`, apart from
Clank's code, and always on a temporary home."""

import csv
import ctypes
import io
import re
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from clank.kernel import private
from clank.kernel.home import Home

windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows' access lists")
posix = pytest.mark.skipif(sys.platform == "win32", reason="a mode means nothing on Windows")


def user_sid() -> str:
    """The user the tests run as, as SDDL writes it in a list: their SID, as Windows' own `whoami` says it, put in a
    list of one entry that Windows itself writes back as SDDL (advapi32, as `icacls /save` writes it). A well-known
    account is written by its two letters (the computer's own Administrator, as GitHub's Windows runner runs, is `LA`),
    any other by its SID."""
    found = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True)
    sid = next(csv.reader(io.StringIO(found.stdout.strip())))[1]
    if sys.platform != "win32":
        return sid
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    parse = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    parse.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    parse.restype = wintypes.BOOL
    write = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
    write.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p)
    write.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor, text = ctypes.c_void_p(), wintypes.LPWSTR()
    if not parse(f"D:(A;;FA;;;{sid})", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not write(descriptor, 1, 4, ctypes.byref(text), None):  # 4: the DACL alone
            raise ctypes.WinError(ctypes.get_last_error())
        written = str(text.value)
    finally:
        kernel32.LocalFree(descriptor)
        kernel32.LocalFree(text)
    return written.removeprefix("D:(").removesuffix(")").rsplit(";", 1)[1]


def listed(path: Path, saved: Path) -> tuple[str, set[str]]:
    """A path's access list as `icacls /save` writes it: its flags (`P`: protected from the folder above; `AI`: its
    entries reach what is made inside) and its entries, each as SDDL writes it (`A;OICI;FA;;;SY`)."""
    subprocess.run(["icacls", str(path), "/save", str(saved)], check=True, capture_output=True)
    dacl = saved.read_text(encoding="utf-16-le").splitlines()[1]  # icacls writes it without a byte order mark
    assert dacl.startswith("D:"), dacl
    flags = dacl[2 : dacl.index("(")] if "(" in dacl else dacl[2:]
    return flags, set(re.findall(r"\(([^()]*)\)", dacl))


def alone(rights: str, user: str) -> set[str]:
    """The two entries Clank keeps, as SDDL writes them: the user's and SYSTEM's, full control."""
    return {f"A;{rights};FA;;;{user}", f"A;{rights};FA;;;SY"}


@windows
def test_ensure_gives_secrets_and_state_a_list_of_their_user_and_system_alone_with_inheritance_off(
    tmp_path: Path,
) -> None:
    home = Home(tmp_path / "home")
    home.ensure()
    user = user_sid()
    for folder in (home.secrets, home.state):
        flags, entries = listed(folder, tmp_path / "acl.txt")
        assert flags.startswith("P"), f"{folder.name}: inheritance from the folder above is off"
        assert entries == alone("OICI", user), folder.name


@windows
def test_what_is_made_inside_them_has_those_two_entries_alone_made_before_or_after(tmp_path: Path) -> None:
    home = Home(tmp_path / "home")
    home.secrets.mkdir(parents=True)
    before = home.secrets / "older.txt"
    before.write_text("made before Clank set the list", encoding="utf-8")
    home.ensure()
    after = home.state / "inner" / "newer.txt"
    after.parent.mkdir()
    after.write_text("made after", encoding="utf-8")
    user = user_sid()
    for path in (before, after):
        flags, entries = listed(path, tmp_path / "acl.txt")
        assert not flags.startswith("P"), f"{path.name} takes its list from its folder"
        assert entries == alone("ID", user), path.name
    assert listed(after.parent, tmp_path / "acl.txt")[1] == alone("OICIID", user)


@windows
def test_a_second_ensure_reads_the_lists_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = Home(tmp_path / "home")
    home.ensure()
    first = [listed(folder, tmp_path / "acl.txt") for folder in (home.secrets, home.state)]

    def refused(folder: Path, user: str) -> None:
        raise AssertionError(f"{folder} was written again")

    monkeypatch.setattr(private, "_write", refused)
    home.ensure()
    assert [listed(folder, tmp_path / "acl.txt") for folder in (home.secrets, home.state)] == first


@windows
def test_ensure_puts_a_list_changed_since_right_again(tmp_path: Path) -> None:
    home = Home(tmp_path / "home")
    home.ensure()
    subprocess.run(["icacls", str(home.secrets), "/grant", "*S-1-5-32-545:(OI)(CI)R"], check=True, capture_output=True)
    assert "A;OICI;FR;;;BU" in listed(home.secrets, tmp_path / "acl.txt")[1]
    home.ensure()
    assert listed(home.secrets, tmp_path / "acl.txt") == ("PAI", alone("OICI", user_sid()))


@windows
def test_the_other_folders_keep_what_they_inherit(tmp_path: Path) -> None:
    home = Home(tmp_path / "home")
    home.ensure()
    for folder in (home.config, home.logs, home.library, home.artifacts):
        assert not listed(folder, tmp_path / "acl.txt")[0].startswith("P"), folder.name


@posix
def test_on_linux_and_macos_secrets_and_state_are_mode_0700(tmp_path: Path) -> None:
    home = Home(tmp_path / "home")
    home.ensure()
    for folder in (home.secrets, home.state):
        assert folder.stat().st_mode & 0o777 == 0o700, folder.name
    home.state.chmod(0o755)
    home.ensure()
    assert home.state.stat().st_mode & 0o777 == 0o700
