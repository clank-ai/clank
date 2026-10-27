"""The gateway's way in on Linux (design 0014 §3, decision 0071 (a)): its socket and the proxy's, in a folder of their
own outside CLANK_HOME, which only the edge mounts, on Docker Engine.

The folder is `~/.cache/clank/<home id>` (`$XDG_CACHE_HOME/clank/<home id>` when that names a folder from the root),
unless the setting `socket_folder` in `config/gateway.json` moves it (`socket_folder()`). It holds `gateway.sock` and
`proxy.sock`.
It may not be anywhere (`checked_socket_folder`): never the home folder itself, never inside or holding CLANK_HOME or
the folder Clank itself runs from (`runs_from`), and its socket's path holds 107 bytes at most, as Linux allows.

The folder is made the owner's alone (0700, `prepare_folder`); one that is a link, not a folder, or another user's is
refused. The gateway's process makes its listeners itself before Uvicorn runs, and hands them over (`listeners`): the
TCP socket on 127.0.0.1 at its port, reusing its address as asyncio's own would on Linux, so a restart finds the port
free while old connections close (a port another program holds is an `OSError`, which ends the gateway as Uvicorn
ended it); and each Unix socket, bound in the folder, set to 0600, and only then listening. The process's umask is
never changed, since it is the whole process's; Uvicorn's own way to make a socket would leave it open to every user.
A socket left by a gateway that ended without removing it, where nothing answers, is replaced; any other file is left
as it is, and the gateway runs without that socket, saying why. When the gateway stops, it removes the sockets it made,
and only those still its own (`remove_sockets`). The rest of the gateway reads a socket's connection as any other: such
a connection has no client address, which nothing in the gateway needs.
"""

import contextlib
import logging
import os
import socket
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import clank

log = logging.getLogger(__name__)
LINUX = sys.platform == "linux"  # where the gateway also listens on its sockets (design 0014 §3)
GATEWAY_SOCKET = "gateway.sock"
PROXY_SOCKET = "proxy.sock"
PATH_MOST = 107  # the bytes of a socket's path Linux holds (its `sun_path` is 108, the last a zero)
FOLDER_MODE = 0o700
SOCKET_MODE = 0o600
HOST = "127.0.0.1"
MOVE = "set socket_folder in config/gateway.json to another folder, then clank gateway restart"


class SocketFolderError(Exception):
    """A socket folder, or a socket in it, the gateway may not use, and why."""


def runs_from() -> Path:
    """The folder Clank itself runs from: its package's parent (a clone's root, or the environment's packages)."""
    return Path(clank.__file__).resolve().parents[1]


def default_folder(home_id: str, environ: Mapping[str, str] | None = None, user_home: Path | None = None) -> Path:
    """The socket folder when the settings name none: under `$XDG_CACHE_HOME` when that names a folder from the root
    (a relative one is ignored, as the XDG rules say), else under `~/.cache`; then `clank/<home id>`, so two homes
    never share one."""
    cache = (os.environ if environ is None else environ).get("XDG_CACHE_HOME", "")
    base = Path(cache) if cache and Path(cache).is_absolute() else (user_home or Path.home()) / ".cache"
    return base / "clank" / home_id


def socket_folder(
    setting: str, home_id: str, environ: Mapping[str, str] | None = None, user_home: Path | None = None
) -> Path:
    """Where the gateway's sockets go: the folder `socket_folder` names (`~` for the home folder), else the default."""
    named = setting.strip()
    if named:
        return Path(os.path.expanduser(named))
    return default_folder(home_id, environ, user_home)


def checked_socket_folder(folder: Path, clank_home: Path, runs_from: Path, user_home: Path) -> Path:
    """The folder, from the root, when the gateway may keep its sockets there; `SocketFolderError` saying why not."""
    if not folder.is_absolute():
        raise SocketFolderError(f"the gateway's socket folder {folder} is not a full path: {MOVE}")
    found = folder.resolve()
    if found == user_home.resolve():
        raise SocketFolderError(f"the gateway's socket folder {found} is your home folder itself: {MOVE}")
    for what, other in (("Clank's own folder, CLANK_HOME", clank_home), ("the folder Clank runs from", runs_from)):
        place = other.resolve()
        if found == place or place.is_relative_to(found):
            raise SocketFolderError(f"the gateway's socket folder {found} holds {what} ({place}): {MOVE}")
        if found.is_relative_to(place):
            raise SocketFolderError(f"the gateway's socket folder {found} is inside {what} ({place}): {MOVE}")
    path = found / GATEWAY_SOCKET
    size = len(os.fsencode(str(path)))
    if size > PATH_MOST:
        raise SocketFolderError(
            f"the gateway's socket {path} would be {size} bytes long, and Linux holds a socket's path of {PATH_MOST} "
            f"bytes at most: {MOVE}"
        )
    return found


def prepare_folder(folder: Path) -> None:
    """The folder made when it is not there, and kept the owner's alone (0700); `SocketFolderError` saying why when it
    cannot be: it is a link or not a folder, or it is another user's."""
    try:
        folder.mkdir(mode=FOLDER_MODE, parents=True, exist_ok=True)
        found = os.lstat(folder)
    except OSError as error:
        raise SocketFolderError(f"the gateway's socket folder {folder} could not be made: {error}") from error
    if stat.S_ISLNK(found.st_mode) or not stat.S_ISDIR(found.st_mode):
        raise SocketFolderError(f"the gateway's socket folder {folder} is not a folder: {MOVE}")
    if sys.platform != "win32" and found.st_uid != os.getuid():
        raise SocketFolderError(f"the gateway's socket folder {folder} is another user's: {MOVE}")
    if stat.S_IMODE(found.st_mode) != FOLDER_MODE:
        os.chmod(folder, FOLDER_MODE)


def is_socket(path: Path) -> bool:
    """Whether a socket is at `path` (a link is not followed)."""
    try:
        return stat.S_ISSOCK(os.lstat(path).st_mode)
    except OSError:
        return False


@dataclass
class Listeners:
    """What the gateway's process listens on (Linux): the TCP socket, its Unix socket and the proxy's (None, each, when
    it could not be made, which its log says), and each socket file it made, as it was then (removed when it stops)."""

    tcp: socket.socket
    gateway: socket.socket | None = None
    proxy: socket.socket | None = None
    made: list[tuple[Path, os.stat_result]] = field(default_factory=list)

    @property
    def served(self) -> list[socket.socket]:
        """What Uvicorn serves: the TCP socket, and the gateway's Unix socket when there is one."""
        return [self.tcp, *([self.gateway] if self.gateway is not None else [])]


def tcp_listener(port: int) -> socket.socket:
    """127.0.0.1 at the port, its address reused as asyncio's own listener reuses it on Linux, listening; an `OSError`
    when it cannot be bound (another program holds the port)."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, port))
        listener.listen()
    except OSError:
        listener.close()
        raise
    return listener


def remove_sockets(made: list[tuple[Path, os.stat_result]]) -> None:
    """Remove each socket file the gateway made that is still its own (the same file, not one made there since)."""
    for path, then in made:
        try:
            now = os.lstat(path)
        except OSError:
            continue
        if stat.S_ISSOCK(now.st_mode) and (now.st_dev, now.st_ino) == (then.st_dev, then.st_ino):
            with contextlib.suppress(OSError):
                path.unlink()


if sys.platform != "win32":  # Unix sockets: the type checker knows `AF_UNIX` only off Windows

    def listeners(port: int, folder: Path) -> Listeners:
        """The TCP socket at the port (an `OSError` when it cannot be bound), then the folder made ready and the two
        Unix sockets in it; a socket that cannot be made is left out, its log saying why."""
        made = Listeners(tcp_listener(port))
        try:
            prepare_folder(folder)
        except SocketFolderError as error:
            log.warning("%s; the gateway listens on no socket", error)
            return made
        for name in (GATEWAY_SOCKET, PROXY_SOCKET):
            path = folder / name
            try:
                listener = unix_listener(path)
            except (OSError, SocketFolderError) as error:
                log.warning("the gateway could not listen on %s: %s", path, error)
                continue
            made.made.append((path, os.lstat(path)))
            if name == GATEWAY_SOCKET:
                made.gateway = listener
            else:
                made.proxy = listener
        return made

    def unix_listener(path: Path) -> socket.socket:
        """A socket at `path`, in a folder made ready: bound, set to 0600, and only then listening (the umask is never
        changed); one left by a gateway that ended is replaced first (`clear`)."""
        clear(path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            os.chmod(path, SOCKET_MODE)
            listener.listen()
        except OSError:
            listener.close()
            raise
        return listener

    def clear(path: Path) -> None:
        """Make way for a socket at `path`: nothing there is fine; a socket where nothing answers (left by a gateway
        that ended) is removed; any other file, or a socket that answers or cannot be reached, is left as it is, and
        `SocketFolderError` says why."""
        try:
            found = os.lstat(path)
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(found.st_mode):
            raise SocketFolderError(f"{path} is there and is not a socket: it is left as it is; remove it, then clank "
                                    "gateway restart")  # fmt: skip
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(2)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            path.unlink(missing_ok=True)  # nothing answers there: a gateway that ended left it
            return
        except FileNotFoundError:
            return
        except OSError as error:
            raise SocketFolderError(f"{path} is a socket Clank cannot reach ({error}): it is left as it is") from error
        finally:
            probe.close()
        raise SocketFolderError(f"another program answers on {path}: it is left as it is")
