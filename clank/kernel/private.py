"""Folders only the user Clank runs as can open: CLANK_HOME's secrets/ and state/ (design 0001 §7.2, decision 0167).

secrets/ holds the keys and tokens the user gave Clank, state/ the local token that opens Clank's API and the state
database. Whatever the folder above them allows, `keep` makes each one the user's alone:

- on Linux and macOS its mode is 0700;
- on Windows, where a mode means nothing, its access list is protected from the folder above (inheritance off) and
  names two entries alone, full control for the user Clank runs as and for SYSTEM (Windows itself), each inherited by
  every file and folder made inside (object and container inherit). The list is read first and written only when it
  is not exactly that, so a start costs one read. Writing it passes the two entries down to what is already inside,
  in place of what that had inherited from above (Windows does it; an entry given to a file of its own stays). It is
  done through Windows' own security calls (advapi32, through ctypes, as `infolder` reaches kernel32), so no program
  is started and nothing localized is read.

`exposed` says, without changing anything, who else may open such a folder (`clank doctor`, `clank setup`): on Windows
each other entry of its list by the account's name (its SID when Windows knows no name), what it allows or denies, and
whether it comes from the folder above; on Linux and macOS a mode that lets others in. With it come the commands that
take it away, for the owner to run: `icacls ... /remove *SID` for an entry of the folder's own, `icacls ...
/inheritance:r /grant:r` for the user and SYSTEM alone when entries come from the folder above, `chmod 700` elsewhere.
"""

import functools
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SYSTEM = "S-1-5-18"  # NT AUTHORITY\SYSTEM: Windows itself
FILE_ALL_ACCESS = 0x1F01FF
INHERITS = 0x1 | 0x2  # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE: files and folders made inside take the entry
INHERITED = 0x10  # INHERITED_ACE: the entry comes from the folder above
INHERITANCE = 0x1F  # the flags of an entry that say how it is inherited (the rest are an audit's)
ALLOWS = frozenset({0x0, 0x5, 0x9, 0xB})  # the access allowed entries: plain, object, callback, callback object
DENIES = frozenset({0x1, 0x6, 0xA, 0xC})  # and the access denied ones
GENERIC_ALL, GENERIC_EXECUTE, GENERIC_WRITE, GENERIC_READ = 0x10000000, 0x20000000, 0x40000000, 0x80000000
WRITE_DAC, WRITE_OWNER = 0x40000, 0x80000
WRITES = GENERIC_WRITE | 0x2 | 0x4 | 0x40 | 0x10000  # write data, append data, delete what is inside, delete
READS = GENERIC_READ | GENERIC_EXECUTE | 0x1 | 0x20  # read data (list the folder), execute (pass through it)


@dataclass(frozen=True)
class Other:
    """An entry of a private folder's access list for someone other than the user and SYSTEM."""

    who: str  # the account's name, as Windows says it; its SID when Windows knows no name
    sid: str
    allows: bool  # False: it denies
    rights: str  # what it allows or denies, in words
    inherited: bool  # it comes from the folder above

    @property
    def said(self) -> str:
        """`BUILTIN\\Users (read, from the folder above)`."""
        above = ", from the folder above" if self.inherited else ""
        return f"{self.who} ({'' if self.allows else 'denied '}{self.rights}{above})"


@dataclass(frozen=True)
class Exposed:
    """A private folder someone other than the user may open: who, in words, and the commands that take it away, for
    the owner to run."""

    folder: Path
    said: str
    commands: tuple[tuple[str, ...], ...]

    @property
    def shown(self) -> tuple[str, ...]:
        """Each command as the owner types it."""
        return tuple(shown(command) for command in self.commands)


def shown(command: Sequence[str]) -> str:
    """A command as the owner types it: icacls with its folder and each value in double quotes (as both Windows shells
    read them), any other as a POSIX shell reads it."""
    if command and command[0] == "icacls":
        return " ".join(
            part if index == 0 or part.startswith("/") else f'"{part}"' for index, part in enumerate(command)
        )
    return shlex.join(command)


def words(found: Sequence[Exposed]) -> tuple[str, str]:
    """What the doctor and the setup say of folders others may open: who, and how to put it right."""
    said = "; ".join(exposed.said for exposed in found)
    commands = ", then ".join(f"`{each}`" for exposed in found for each in exposed.shown)
    again = "Clank also sets them itself each time its service starts (`clank stop`, then `clank`)"
    return said, f"put them right: {commands}. {again}"


def keep(folder: Path) -> None:
    """Make the folder the user's alone (the module's docstring): on Windows its list is read, and written only when it
    is not the user's and SYSTEM's alone."""
    if sys.platform == "win32":
        user = _user()
        protected, entries = _listing(folder)
        if not (protected and entries is not None and sorted(entries) == _wanted(user)):
            _write(folder, user)
    else:
        folder.chmod(0o700)


def exposed(folder: Path) -> Exposed | None:
    """Who else may open the folder and how to take it away; None when only the user (and SYSTEM, on Windows) may.
    Nothing is changed."""
    if sys.platform == "win32":
        return _exposed_windows(folder)
    mode = folder.stat().st_mode & 0o777
    if not mode & 0o077:
        return None
    return Exposed(
        folder, f"{folder.name}/ has mode {mode:03o}, so others may open it", (("chmod", "700", str(folder)),)
    )


def rights(mask: int) -> str:
    """What an entry's access mask gives, in words."""
    if mask & (GENERIC_ALL | WRITE_DAC | WRITE_OWNER) or mask & FILE_ALL_ACCESS == FILE_ALL_ACCESS:
        return "full control"  # one who may change the list may give itself the rest
    reads, writes = bool(mask & READS), bool(mask & WRITES)
    if reads and writes:
        return "read and write"
    if writes:
        return "write"
    if reads:
        return "read"
    return f"access {mask:#x}"


def _wanted(user: str) -> list[tuple[int, int, int, str]]:
    """The entries Clank keeps, as `_listing` gives them: the user's and SYSTEM's, full control, inherited inside."""
    return sorted({(0, INHERITS, FILE_ALL_ACCESS, sid) for sid in (user, SYSTEM)})


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _P = ctypes.POINTER
    _VOID = ctypes.c_void_p

    _GetNamedSecurityInfoW = _advapi32.GetNamedSecurityInfoW
    _GetNamedSecurityInfoW.argtypes = (
        wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, _P(_VOID), _P(_VOID), _P(_VOID), _P(_VOID), _P(_VOID)
    )  # fmt: skip
    _GetNamedSecurityInfoW.restype = wintypes.DWORD
    _SetNamedSecurityInfoW = _advapi32.SetNamedSecurityInfoW
    _SetNamedSecurityInfoW.argtypes = (wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, _VOID, _VOID, _VOID, _VOID)
    _SetNamedSecurityInfoW.restype = wintypes.DWORD
    _GetSecurityDescriptorControl = _advapi32.GetSecurityDescriptorControl
    _GetSecurityDescriptorControl.argtypes = (_VOID, _P(wintypes.WORD), _P(wintypes.DWORD))
    _GetSecurityDescriptorControl.restype = wintypes.BOOL
    _GetSecurityDescriptorDacl = _advapi32.GetSecurityDescriptorDacl
    _GetSecurityDescriptorDacl.argtypes = (_VOID, _P(wintypes.BOOL), _P(_VOID), _P(wintypes.BOOL))
    _GetSecurityDescriptorDacl.restype = wintypes.BOOL
    _ConvertStringSecurityDescriptorToSecurityDescriptorW = (
        _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    )
    _ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, _P(_VOID), _P(wintypes.ULONG)
    )  # fmt: skip
    _ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    _GetAce = _advapi32.GetAce
    _GetAce.argtypes = (_VOID, wintypes.DWORD, _P(_VOID))
    _GetAce.restype = wintypes.BOOL
    _ConvertSidToStringSidW = _advapi32.ConvertSidToStringSidW
    _ConvertSidToStringSidW.argtypes = (_VOID, _P(_VOID))
    _ConvertSidToStringSidW.restype = wintypes.BOOL
    _ConvertStringSidToSidW = _advapi32.ConvertStringSidToSidW
    _ConvertStringSidToSidW.argtypes = (wintypes.LPCWSTR, _P(_VOID))
    _ConvertStringSidToSidW.restype = wintypes.BOOL
    _LookupAccountSidW = _advapi32.LookupAccountSidW
    _LookupAccountSidW.argtypes = (
        wintypes.LPCWSTR, _VOID, wintypes.LPWSTR, _P(wintypes.DWORD), wintypes.LPWSTR, _P(wintypes.DWORD),
        _P(ctypes.c_int),
    )  # fmt: skip
    _LookupAccountSidW.restype = wintypes.BOOL
    _OpenProcessToken = _advapi32.OpenProcessToken
    _OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, _P(wintypes.HANDLE))
    _OpenProcessToken.restype = wintypes.BOOL
    _GetTokenInformation = _advapi32.GetTokenInformation
    _GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, _VOID, wintypes.DWORD, _P(wintypes.DWORD))
    _GetTokenInformation.restype = wintypes.BOOL
    _GetCurrentProcess = _kernel32.GetCurrentProcess
    _GetCurrentProcess.argtypes = ()
    _GetCurrentProcess.restype = wintypes.HANDLE
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    _CloseHandle.restype = wintypes.BOOL
    _LocalFree = _kernel32.LocalFree
    _LocalFree.argtypes = (_VOID,)
    _LocalFree.restype = _VOID

    _FILE = 1  # SE_FILE_OBJECT
    _DACL = 0x4  # DACL_SECURITY_INFORMATION
    _PROTECTED_DACL = 0x80000000  # PROTECTED_DACL_SECURITY_INFORMATION: nothing inherited from the folder above
    _DACL_PROTECTED = 0x1000  # SE_DACL_PROTECTED, in a security descriptor's control
    _TOKEN_QUERY = 0x8
    _TOKEN_USER = 1  # TokenUser
    _SDDL_REVISION = 1

    class _Acl(ctypes.Structure):
        _fields_ = (
            ("revision", ctypes.c_ubyte), ("sbz1", ctypes.c_ubyte), ("size", wintypes.WORD), ("count", wintypes.WORD),
            ("sbz2", wintypes.WORD),
        )  # fmt: skip

    class _AceHeader(ctypes.Structure):
        _fields_ = (("type", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("size", wintypes.WORD))

    def _failed(what: str, folder: Path | None = None, code: int | None = None) -> OSError:
        """Windows' error, its words and the folder's path in it."""
        code = ctypes.get_last_error() if code is None else code
        return OSError(
            None, f"{what} ({ctypes.FormatError(code).strip()})", None if folder is None else str(folder), code
        )

    @functools.cache
    def _user() -> str:
        """The SID of the user Clank runs as (its process's token's), as text."""
        token = wintypes.HANDLE()
        if not _OpenProcessToken(_GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
            raise _failed("Clank could not read which user it runs as")
        try:
            size = wintypes.DWORD()
            _GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))  # asks only how big it is
            buffer = ctypes.create_string_buffer(size.value)
            if not _GetTokenInformation(token, _TOKEN_USER, buffer, size, ctypes.byref(size)):
                raise _failed("Clank could not read which user it runs as")
            return _sid_text(ctypes.cast(buffer, _P(_VOID))[0])  # TOKEN_USER begins with its SID's address
        finally:
            _CloseHandle(token)

    def _sid_text(sid: int | None) -> str:
        text = _VOID()
        if not _ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise _failed("Clank could not read a SID")
        try:
            return ctypes.wstring_at(text.value)  # type: ignore[arg-type]
        finally:
            _LocalFree(text)

    def _name(sid: str) -> str:
        """The account a SID names, as Windows says it (`BUILTIN\\Users`); "" when Windows knows no name for it."""
        found = _VOID()
        if not _ConvertStringSidToSidW(sid, ctypes.byref(found)):
            return ""
        try:
            name, domain = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            names, domains, use = wintypes.DWORD(256), wintypes.DWORD(256), ctypes.c_int()
            if not _LookupAccountSidW(None, found, name, names, domain, domains, ctypes.byref(use)):
                return ""
            return f"{domain.value}\\{name.value}" if domain.value else name.value
        finally:
            _LocalFree(found)

    def _entry(address: int) -> tuple[int, int, int, str]:
        """An entry of a list: its type, its inheritance flags, its access mask and its SID ("" for a kind of entry
        that names none)."""
        header = _AceHeader.from_address(address)
        mask = wintypes.DWORD.from_address(address + 4).value
        if header.type in (0x5, 0x6, 0xB, 0xC):  # an object entry: its own flags, then the GUIDs they say it has
            flags = wintypes.DWORD.from_address(address + 8).value
            sid = address + 12 + (16 if flags & 0x1 else 0) + (16 if flags & 0x2 else 0)
        elif header.type in ALLOWS | DENIES:
            sid = address + 8
        else:
            return header.type, header.flags & INHERITANCE, mask, ""
        return header.type, header.flags & INHERITANCE, mask, _sid_text(sid)

    def _listing(folder: Path) -> tuple[bool, list[tuple[int, int, int, str]] | None]:
        """The folder's access list: whether it is protected from the folder above, and its entries (`_entry`); None
        when it has no list at all, which lets everyone in."""
        dacl, descriptor = _VOID(), _VOID()
        code = _GetNamedSecurityInfoW(
            str(folder), _FILE, _DACL, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
        )
        if code:
            raise _failed("Clank could not read the folder's access list", folder, code)
        try:
            control, revision = wintypes.WORD(), wintypes.DWORD()
            if not _GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
                raise _failed("Clank could not read the folder's access list", folder)
            protected = bool(control.value & _DACL_PROTECTED)
            if not dacl.value:
                return protected, None
            entries = []
            for index in range(_Acl.from_address(dacl.value).count):
                found = _VOID()
                if not _GetAce(dacl, index, ctypes.byref(found)):
                    raise _failed("Clank could not read the folder's access list", folder)
                entries.append(_entry(found.value))  # type: ignore[arg-type]
            return protected, entries
        finally:
            _LocalFree(descriptor)

    def _write(folder: Path, user: str) -> None:
        """Give the folder its protected list: the user and SYSTEM alone, full control, inherited inside."""
        sddl = "D:P" + "".join(f"(A;OICI;FA;;;{sid})" for sid in dict.fromkeys((user, SYSTEM)))
        descriptor = _VOID()
        if not _ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, _SDDL_REVISION, ctypes.byref(descriptor), None
        ):
            raise _failed("Clank could not make the folder private to you", folder)
        try:
            present, dacl, defaulted = wintypes.BOOL(), _VOID(), wintypes.BOOL()
            if not _GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
            ):
                raise _failed("Clank could not make the folder private to you", folder)
            code = _SetNamedSecurityInfoW(str(folder), _FILE, _DACL | _PROTECTED_DACL, None, None, dacl, None)
            if code:
                raise _failed("Clank could not make the folder private to you", folder, code)
        finally:
            _LocalFree(descriptor)

    def _exposed_windows(folder: Path) -> Exposed | None:
        user = _user()
        _, entries = _listing(folder)
        grant = [f"*{sid}:(OI)(CI)F" for sid in dict.fromkeys((user, SYSTEM))]
        reset = ("icacls", str(folder), "/inheritance:r", "/grant:r", *grant)
        if entries is None:
            return Exposed(folder, f"{folder.name}/ has no access list, so everyone may open it", (reset,))
        others = [
            Other(_name(sid) or sid, sid, kind in ALLOWS, rights(mask), bool(flags & INHERITED))
            for kind, flags, mask, sid in entries
            if sid and sid not in (user, SYSTEM)
        ]
        if not others:
            return None
        commands = [reset] if any(other.inherited for other in others) else []
        explicit = dict.fromkeys(other.sid for other in others if not other.inherited)
        commands += [("icacls", str(folder), "/remove", f"*{sid}") for sid in explicit]
        said = f"{folder.name}/'s access list also names {', '.join(other.said for other in others)}"
        return Exposed(folder, said, tuple(commands))
