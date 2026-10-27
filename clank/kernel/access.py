"""Callers and access: who may call the Clank API, and how a local client finds it (design 0002 §2.7).

A local client (the console, VS Code, the `clank` command) proves it is the user on this machine by reading the local
token, `CLANK_HOME/state/local.token`, which only the user can read; it finds the service's address in
`state/connection.json`, which the service writes when it starts and removes when it stops, through the kernel's
`files`: clients read it often (the gateway's process every second), and on Windows a reader holding it a moment
refuses a replace or a delete, which is tried again meanwhile. A client names itself in the `X-Clank-Client` header,
and what it does is recorded as "you (<client>)". A request that starts an operation may carry a key in
`X-Clank-Request-Key`; the same key never starts a second one (design 0002 §2.4), so a button pressed twice, or a
request sent again after a lost answer, starts one. Paired devices, data-plane processes and agents' sessions get their
own tokens and access levels in the milestones that bring them.
"""

import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from clank.kernel import files
from clank.kernel.clock import from_text, to_text
from clank.kernel.events import Actor
from clank.kernel.home import Home

TOKEN_FILE = "local.token"
CONNECTION_FILE = "connection.json"
CLIENT_HEADER = "X-Clank-Client"
REQUEST_KEY_HEADER = "X-Clank-Request-Key"
NOT_A_NAME = re.compile(r"[^a-z0-9-]")


def local_token(home: Home) -> str:
    """The local token, created on first use and kept."""
    path = home.state / TOKEN_FILE
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    home.state.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(token + "\n")
    path.chmod(0o600)
    return token


@dataclass(frozen=True)
class Connection:
    """Where the running service listens, its process, when it started, and its version."""

    url: str
    pid: int
    started: datetime
    version: str


def write_connection(home: Home, connection: Connection) -> None:
    """Write the connection file (when the service has started)."""
    text = json.dumps(
        {
            "url": connection.url,
            "pid": connection.pid,
            "started": to_text(connection.started),
            "version": connection.version,
        },
        indent=2,
    )
    files.replace(home.state / CONNECTION_FILE, text + "\n")


def read_connection(home: Home) -> Connection | None:
    """The connection file's content, or None when the service has not written one."""
    path: Path = home.state / CONNECTION_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Connection(str(data["url"]), int(data["pid"]), from_text(data["started"]), str(data["version"]))
    except (OSError, ValueError, KeyError):
        return None


def remove_connection(home: Home) -> bool:
    """Remove the connection file (when the service stops); whether it went (another program may hold it open)."""
    return files.remove(home.state / CONNECTION_FILE)


def client_actor(name: str | None) -> Actor:
    """The actor of what a local client does: the user, through that client."""
    cleaned = NOT_A_NAME.sub("", (name or "").lower())[:40]
    return Actor(kind="user", via=cleaned or "api")
