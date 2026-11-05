"""Files in a workspace's folder that Clank reads or writes as the owner (decisions 0159 and 0164).

The agent writes the folder (it is mounted into the agent's container), so it can put a link anywhere in it, and swap
a folder for a link of the same name at any moment. Clank follows no link there, and nothing on the way can change
while it reads or writes: a path below the folder is a `Place`, taken a folder at a time from the workspace's folder,
each folder opened without following it and held (`held`) until the file is read, written or listed:

- on Linux and macOS each folder is opened from the one before it (`dir_fd`, `O_NOFOLLOW`), and the file too: a link
  anywhere on the way is refused by the system itself, and a name changed meanwhile changes nothing already open;
- on Windows, where Python opens nothing from a folder's handle, each folder on the way is opened without following it
  (a junction, a symbolic link, or any other reparse point that names another place, is refused) and held so that
  nothing can rename or remove it (no `FILE_SHARE_DELETE`); the file itself is opened without following it.

A file is written whole under a name of its own, then put in place (`os.replace`), so a link standing in its name is
replaced, never written through; `new` writes only a name nothing has yet. A name that leaves the folder (absolute,
`..`, a drive, `:`, and on Windows a device's name or a name Windows would change) or passes through a link is
`Outside`, a `ValueError`, whose words name the path. The workspace's folder itself is the owner's choice, taken as it
is. `inside` and `linked`, which only check a path before it is used, go once every caller uses a `Place`.
"""

import contextlib
import errno
import os
import secrets
import stat
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Literal

NAME_SURROGATE = 0x20000000  # a reparse point that stands for another name: a symbolic link, a junction, WSL's links
DEVICES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"{port}{digit}" for port in ("com", "lpt") for digit in [*"0123456789", "¹", "²", "³"]}
)
Kind = Literal["file", "folder"]


class Outside(ValueError):
    """A path of the folder that leaves it, or passes through a link."""


def _parts(relative: str | PurePath) -> tuple[str, ...]:
    """A name below the folder as its parts (either slash parts them); `Outside` for one that leaves it."""
    text = str(relative).replace("\\", "/")
    parts = tuple(part for part in text.split("/") if part not in ("", "."))
    leaves = text.startswith("/") or bool(PureWindowsPath(text).drive)
    odd = any(part == ".." or ":" in part or "\0" in part for part in parts)
    if leaves or odd or (sys.platform == "win32" and any(_changed_by_windows(part) for part in parts)):
        raise Outside(f"{relative} is not a path inside the folder")
    return parts


def _changed_by_windows(part: str) -> bool:
    """A name Windows reads as something else: a device (`NUL`, `com1.txt`), or one it drops dots or spaces from."""
    return part != part.rstrip(". ") or part.split(".")[0].rstrip(" ").lower() in DEVICES


def _joined(where: str, name: str) -> str:
    return f"{where}/{name}" if where else name


def _link_words(where: str) -> str:
    return f"{where} is a link: Clank follows no link in the folder"


def _take(file: BinaryIO, most: int | None, last: int | None) -> bytes:
    """An open file's bytes: its last `last` only when given, at most `most`."""
    if last is not None:
        file.seek(max(0, os.fstat(file.fileno()).st_size - last))
    return file.read() if most is None else file.read(most)


def _part_name() -> str:
    """The name a file is written under before it is put in place."""
    return f".clank-{secrets.token_hex(6)}.part"


def _surrogate_stat(info: os.stat_result) -> bool:
    """Whether a stat (not followed) is of a Windows reparse point that names another place."""
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse) and bool(getattr(info, "st_reparse_tag", 0) & NAME_SURROGATE)


def _kind(info: os.stat_result) -> Kind | None:
    """A file or a folder, by its own stat (not followed); None for a link or anything else."""
    if stat.S_ISLNK(info.st_mode) or _surrogate_stat(info):
        return None
    if stat.S_ISDIR(info.st_mode):
        return "folder"
    return "file" if stat.S_ISREG(info.st_mode) else None


if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE,
    )  # fmt: skip
    _CreateFileW.restype = wintypes.HANDLE
    _GetFileInformationByHandleEx = _kernel32.GetFileInformationByHandleEx
    _GetFileInformationByHandleEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _GetFileInformationByHandleEx.restype = wintypes.BOOL
    _GetFileType = _kernel32.GetFileType
    _GetFileType.argtypes = (wintypes.HANDLE,)
    _GetFileType.restype = wintypes.DWORD
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    _CloseHandle.restype = wintypes.BOOL
    # A folder is held with the right to list it: a handle that may only read attributes takes no part in sharing, so
    # it would hold nothing (Windows checks the sharing of handles that may read, write or delete)
    _HOLD = 0x0001 | 0x0080  # FILE_LIST_DIRECTORY, FILE_READ_ATTRIBUTES
    _GENERIC_READ = 0x80000000
    _HOLD_TRIES, _HOLD_WAIT = 5, 0.02  # a folder someone else has open to rename or remove, for a moment
    _SHARE_READ, _SHARE_WRITE, _SHARE_DELETE = 0x1, 0x2, 0x4
    _OPEN_EXISTING = 3
    _BACKUP_SEMANTICS = 0x02000000  # what lets a folder be opened
    _OPEN_REPARSE_POINT = 0x00200000  # the link itself, never what it names
    _ATTRIBUTE_TAG_INFO = 9
    _FILE_TYPE_DISK = 1
    _INVALID = wintypes.HANDLE(-1).value

    class _TagInfo(ctypes.Structure):
        _fields_ = (("attributes", wintypes.DWORD), ("tag", wintypes.DWORD))

    def _long(path: str) -> str:
        """A path Windows takes as written: no length limit, no name changed (`\\\\?\\`)."""
        absolute = os.path.abspath(path)
        if absolute.startswith("\\\\?\\"):
            return absolute
        if absolute.startswith("\\\\"):
            return "\\\\?\\UNC\\" + absolute[2:]
        return "\\\\?\\" + absolute

    def _handle(path: str, access: int, share: int, flags: int) -> int:
        found = _CreateFileW(path, access, share, None, _OPEN_EXISTING, flags, None)
        if found is None or found == _INVALID:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(found)

    def _tag(handle: int) -> tuple[int, int]:
        """A handle's attributes and reparse tag; the handle closed when they cannot be read."""
        info = _TagInfo()
        if not _GetFileInformationByHandleEx(handle, _ATTRIBUTE_TAG_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            _CloseHandle(handle)
            raise error
        return int(info.attributes), int(info.tag)

    def _surrogate(attributes: int, tag: int) -> bool:
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and bool(tag & NAME_SURROGATE)

    class _Here:
        """A folder on the way, held: nothing can rename or remove it while Clank works below it."""

        def __init__(self, path: str, handle: int | None, where: str) -> None:
            self.path, self.handle, self.where = path, handle, where

        @classmethod
        def top(cls, folder: Path) -> "_Here":
            return cls(_long(str(folder)), None, "")

        def _of(self, name: str) -> str:
            return self.path.rstrip("\\") + "\\" + name

        @staticmethod
        def _hold(path: str) -> int:
            """A folder opened without following it, and held: shared for reading and writing, never for deleting,
            so nothing renames or removes it while the handle is open; tried again a few times while someone else
            has it open that way."""
            for tries_left in range(_HOLD_TRIES - 1, -1, -1):
                try:
                    return _handle(path, _HOLD, _SHARE_READ | _SHARE_WRITE, _BACKUP_SEMANTICS | _OPEN_REPARSE_POINT)
                except PermissionError:
                    if not tries_left:
                        raise
                    time.sleep(_HOLD_WAIT)
            raise AssertionError("unreachable")

        def folder(self, name: str, *, create: bool) -> "_Here":
            path, where = self._of(name), _joined(self.where, name)
            try:
                handle = self._hold(path)
            except FileNotFoundError:
                if not create:
                    raise
                with contextlib.suppress(FileExistsError):
                    os.mkdir(path)
                handle = self._hold(path)
            attributes, tag = _tag(handle)
            if _surrogate(attributes, tag):
                _CloseHandle(handle)
                raise Outside(_link_words(where))
            if not attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
                _CloseHandle(handle)
                raise NotADirectoryError(errno.ENOTDIR, "not a folder", where)
            return _Here(path, handle, where)

        def open(self, name: str) -> BinaryIO:
            """A file of this folder, opened to read without following it."""
            path, share = self._of(name), _SHARE_READ | _SHARE_WRITE | _SHARE_DELETE
            handle = _handle(path, _GENERIC_READ, share, _OPEN_REPARSE_POINT)
            attributes, tag = _tag(handle)
            if _surrogate(attributes, tag):
                _CloseHandle(handle)
                raise Outside(_link_words(_joined(self.where, name)))
            if _GetFileType(handle) != _FILE_TYPE_DISK:
                _CloseHandle(handle)
                raise OSError(errno.EINVAL, "not a plain file", _joined(self.where, name))
            itself = os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY), "rb")
            if not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return itself
            # A reparse point that names no other place (a cloud file not yet on the disk) is read as Windows gives
            # it, when what opens is the very file the first opening found
            with itself:
                given = open(path, "rb")  # noqa: SIM115 (given to the caller, who closes it)
                first, then = os.fstat(itself.fileno()), os.fstat(given.fileno())
                if (first.st_dev, first.st_ino) != (then.st_dev, then.st_ino):
                    given.close()
                    raise Outside(f"{_joined(self.where, name)} changed while it was read")
                return given

        def read(self, name: str, most: int | None, last: int | None = None) -> bytes:
            with self.open(name) as file:
                return _take(file, most, last)

        def write(self, name: str, data: bytes, *, new: bool) -> None:
            target = self._of(name)
            if new:
                with open(target, "xb") as file:  # a name that is taken, even by a link, is refused
                    file.write(data)
                return
            part, made = self._of(_part_name()), False
            try:
                with open(part, "xb") as file:
                    made = True
                    file.write(data)
                os.replace(part, target)  # a link in the name is replaced, never written through
            except BaseException:
                if made:
                    with contextlib.suppress(OSError):
                        os.remove(part)
                raise

        def stat(self, name: str) -> os.stat_result:
            return os.stat(self._of(name), follow_symlinks=False)

        def entries(self) -> list[tuple[str, Kind, os.stat_result]]:
            found: list[tuple[str, Kind, os.stat_result]] = []
            with os.scandir(self.path) as listing:
                for entry in listing:
                    with contextlib.suppress(OSError):
                        info = entry.stat(follow_symlinks=False)
                        if kind := _kind(info):
                            found.append((entry.name, kind, info))
            return sorted(found, key=lambda each: each[0])

        def remove(self, name: str) -> None:
            os.remove(self._of(name))  # a link in the name goes itself; a folder's link is no file

        def close(self) -> None:
            if self.handle is not None:
                _CloseHandle(self.handle)
                self.handle = None

else:
    _CLOEXEC = getattr(os, "O_CLOEXEC", 0)
    _NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
    _DIRECTORY = getattr(os, "O_DIRECTORY", 0)
    _NONBLOCK = getattr(os, "O_NONBLOCK", 0)
    _LINK = {errno.ELOOP, errno.EMLINK}  # what opening a link without following it says (EMLINK: the BSDs')

    class _Here:
        """A folder on the way, open: what is in it is opened from it, never following a link."""

        def __init__(self, fd: int, where: str) -> None:
            self.fd: int | None = fd
            self.where = where

        @classmethod
        def top(cls, folder: Path) -> "_Here":
            return cls(os.open(folder, os.O_RDONLY | _DIRECTORY | _CLOEXEC), "")

        def _open(self, name: str, flags: int, mode: int = 0o777) -> int:
            try:
                return os.open(name, flags | _NOFOLLOW | _CLOEXEC, mode, dir_fd=self.fd)
            except OSError as error:
                # Linux says a link opened as a folder is no folder (ENOTDIR), not a link: the open refused it either
                # way, and its own stat says which to tell
                if error.errno in _LINK or (error.errno == errno.ENOTDIR and self._is_link(name)):
                    raise Outside(_link_words(_joined(self.where, name))) from error
                raise

        def _is_link(self, name: str) -> bool:
            try:
                return stat.S_ISLNK(os.stat(name, dir_fd=self.fd, follow_symlinks=False).st_mode)
            except OSError:
                return False

        def folder(self, name: str, *, create: bool) -> "_Here":
            try:
                fd = self._open(name, os.O_RDONLY | _DIRECTORY)
            except FileNotFoundError:
                if not create:
                    raise
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, dir_fd=self.fd)
                fd = self._open(name, os.O_RDONLY | _DIRECTORY)
            return _Here(fd, _joined(self.where, name))

        def open(self, name: str) -> BinaryIO:
            """A file of this folder, opened to read without following it (never waiting on a pipe)."""
            file = os.fdopen(self._open(name, os.O_RDONLY | _NONBLOCK), "rb")
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                file.close()
                raise OSError(errno.EINVAL, "not a plain file", _joined(self.where, name))
            return file

        def read(self, name: str, most: int | None, last: int | None = None) -> bytes:
            with self.open(name) as file:
                return _take(file, most, last)

        def write(self, name: str, data: bytes, *, new: bool) -> None:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if new:
                with os.fdopen(self._open(name, flags, 0o666), "wb") as file:
                    file.write(data)
                return
            part, made = _part_name(), False
            try:
                with os.fdopen(self._open(part, flags, 0o666), "wb") as file:
                    made = True
                    file.write(data)
                os.replace(part, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            except BaseException:
                if made:
                    with contextlib.suppress(OSError):
                        os.unlink(part, dir_fd=self.fd)
                raise

        def stat(self, name: str) -> os.stat_result:
            return os.stat(name, dir_fd=self.fd, follow_symlinks=False)

        def entries(self) -> list[tuple[str, Kind, os.stat_result]]:
            found: list[tuple[str, Kind, os.stat_result]] = []
            if self.fd is None:
                return found
            with os.scandir(self.fd) as listing:
                for entry in listing:
                    with contextlib.suppress(OSError):
                        info = entry.stat(follow_symlinks=False)
                        if kind := _kind(info):
                            found.append((entry.name, kind, info))
            return sorted(found, key=lambda each: each[0])

        def remove(self, name: str) -> None:
            os.unlink(name, dir_fd=self.fd)

        def close(self) -> None:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None


@contextlib.contextmanager
def held(folder: Path, parts: Iterable[str], *, create: bool = False) -> Iterator[_Here]:
    """The folder `parts` names below `folder`, each folder on the way opened without following it and held until the
    block ends (the module's docstring); each one made as it goes when `create`."""
    opened = [_Here.top(folder)]
    try:
        for part in parts:
            opened.append(opened[-1].folder(part, create=create))
        yield opened[-1]
    finally:
        for each in reversed(opened):
            each.close()


@contextlib.contextmanager
def _child(here: _Here, name: str) -> Iterator[_Here]:
    inner = here.folder(name, create=False)
    try:
        yield inner
    finally:
        inner.close()


@dataclass(frozen=True)
class Place:
    """A path below a workspace's folder, by its parts, read and written as the module's docstring says. `path` is for
    words and for programs that take a path; Clank's own reads and writes go through the place's methods."""

    folder: Path
    parts: tuple[str, ...]

    def __truediv__(self, more: str | PurePath) -> "Place":
        return Place(self.folder, self.parts + _parts(more))

    @property
    def relative(self) -> str:
        """Its path from the folder, `/`-separated."""
        return "/".join(self.parts)

    @property
    def path(self) -> Path:
        """Its path on this machine: for words, and for programs that take one."""
        return self.folder.joinpath(*self.parts)

    @property
    def name(self) -> str:
        """Its last part."""
        return self.parts[-1] if self.parts else ""

    @property
    def stem(self) -> str:
        """Its name without its ending."""
        return PurePosixPath(self.name).stem

    @property
    def suffix(self) -> str:
        """Its name's ending, with its dot."""
        return PurePosixPath(self.name).suffix

    @property
    def parent(self) -> "Place":
        """The folder it is in."""
        return Place(self.folder, self.parts[:-1])

    def _last(self) -> str:
        if not self.parts:
            raise IsADirectoryError(errno.EISDIR, "the folder itself is no file", str(self.folder))
        return self.parts[-1]

    def read_bytes(self, most: int | None = None, *, last: int | None = None) -> bytes:
        """The file's bytes, at most `most`; its last `last` only, when given (the end of a log)."""
        with held(self.folder, self.parts[:-1]) as here:
            return here.read(self._last(), most, last)

    def chunks(self, size: int = 1 << 20) -> Iterator[bytes]:
        """The file's bytes in pieces of `size`, the way held while they are read (a file too big to read whole)."""
        with held(self.folder, self.parts[:-1]) as here, here.open(self._last()) as file:
            while piece := file.read(size):
                yield piece

    def read_text(self, errors: str = "strict", most: int | None = None) -> str:
        """The file's text, as UTF-8."""
        return self.read_bytes(most).decode("utf-8", errors=errors)

    def write_bytes(self, data: bytes, *, new: bool = False) -> None:
        """Write the file whole, its folders made; `new`: only when nothing has its name (else `FileExistsError`)."""
        with held(self.folder, self.parts[:-1], create=True) as here:
            here.write(self._last(), data, new=new)

    def write_text(self, text: str, *, new: bool = False) -> None:
        """Write the file whole, as UTF-8 (`write_bytes`)."""
        self.write_bytes(text.encode("utf-8"), new=new)

    def make(self) -> None:
        """Make the folder, and those on the way to it."""
        with held(self.folder, self.parts, create=True):
            pass

    def stat(self) -> os.stat_result | None:
        """Its own stat, never followed; None when it is not there, or it or something on the way is a link."""
        if not self.parts:
            return os.stat(self.folder)
        try:
            with held(self.folder, self.parts[:-1]) as here:
                info = here.stat(self.parts[-1])
        except (OSError, Outside):
            return None
        return info if _kind(info) else None

    def is_file(self) -> bool:
        """Whether it is a file reached through no link."""
        info = self.stat()
        return info is not None and stat.S_ISREG(info.st_mode)

    def is_folder(self) -> bool:
        """Whether it is a folder reached through no link."""
        info = self.stat()
        return info is not None and stat.S_ISDIR(info.st_mode)

    def entries(self) -> list[tuple[str, Kind]]:
        """What the folder holds, by name, files and folders, links left out; none when it is no folder or a link."""
        try:
            with held(self.folder, self.parts) as here:
                return [(name, kind) for name, kind, _ in here.entries()]
        except (OSError, Outside):
            return []

    def files(
        self, *, skip: Iterable[str] = (), most: int | None = None, hidden: bool = True
    ) -> list[tuple[str, os.stat_result]]:
        """Every file below the folder, by its path from it, with its stat: links left out, folders named in `skip` (and
        hidden ones, whose names start with a dot, unless `hidden`) not looked in, at most `most` files."""
        skipped = frozenset(skip)
        found: list[tuple[str, os.stat_result]] = []

        def walk(here: _Here, prefix: str) -> None:
            for name, kind, info in here.entries():
                if most is not None and len(found) >= most:
                    return
                if kind == "file":
                    found.append((prefix + name, info))
                elif name not in skipped and (hidden or not name.startswith(".")):
                    with contextlib.suppress(OSError, Outside), _child(here, name) as inner:
                        walk(inner, f"{prefix}{name}/")

        with contextlib.suppress(OSError, Outside), held(self.folder, self.parts) as top:
            walk(top, "")
        return found

    def remove(self) -> bool:
        """Remove the file (a link in its name goes itself); False when it was not there."""
        try:
            with held(self.folder, self.parts[:-1]) as here:
                here.remove(self._last())
        except FileNotFoundError:
            return False
        return True


def place(folder: Path | str, relative: str | PurePath = "") -> Place:
    """The place `relative` names below `folder` (the folder itself when it names nothing); `Outside` for a name that
    leaves it."""
    return Place(Path(folder), _parts(relative))


def file_of(folder: Path | str, relative: str | PurePath) -> tuple[Place, os.stat_result] | None:
    """A file below `folder` with its own stat, when it is a plain file reached through no link; None otherwise (not
    there, a folder, a link, or a name that leaves the folder)."""
    try:
        found = place(folder, relative)
    except Outside:
        return None
    info = found.stat()
    return (found, info) if info is not None and stat.S_ISREG(info.st_mode) else None


def linked(path: Path) -> bool:
    """Whether `path` is itself a link: a symbolic link, or on Windows a reparse point that names another place. False
    when it is not there."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(found.st_mode) or _surrogate_stat(found)


def inside(folder: Path, relative: str | PurePath) -> Path:
    """`folder` joined with `relative`, when the name stays below the folder and nothing on the way to it is a link (the
    module's docstring); `Outside` otherwise. A check before use only: `Place` holds the way while it is used."""
    parts = _parts(relative)
    if not parts:
        raise Outside(f"{relative} is not a path inside the folder")
    path = folder
    for part in parts:
        path = path / part
        if linked(path):
            raise Outside(f"{path.relative_to(folder).as_posix()} is a link: Clank follows no link in the folder")
    return path
