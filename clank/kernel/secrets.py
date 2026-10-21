"""Secrets: keys and tokens the user gives Clank, each a file of its own (design 0002 §2.8, built with its first use,
the values of an MCP server's environment and headers).

A secret belongs to a record (`scope`, such as `mcp-server/myproject`) and has a name there (`env.API_KEY`); it is
kept in `CLANK_HOME/secrets/<scope>/<name>`, a folder only the user can read, and nowhere else. Clients see its name,
when it was set and its last four characters (`shown`). A component gets its value through `value`, which records who
used it and why; setting and removing one are recorded too, and no event ever holds a value. Scopes and names are
plain words (letters, digits, `.`, `_`, `-`; a scope has one `/`), so none can lead outside the folder. Removing the
values from whatever else is written (design 0002 §2.8's last rule) comes with the first writer that could see them:
so far the components that hold secrets never pass their values to a record, an event or a log.
"""

import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from clank.kernel.clock import Clock, to_text
from clank.kernel.events import Actor, EventLog, EventType, Subject
from clank.kernel.home import Home

WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
CLANK = Actor(kind="clank")

EVENT_TYPES = [
    EventType(
        "secret.set",
        "A secret was set: a key or token the user gave, kept in CLANK_HOME/secrets (its value is never recorded).",
        {"scope": "The record it belongs to.", "name": "Its name there.", "ends": "Its last four characters."},
    ),
    EventType(
        "secret.removed",
        "The secrets of a record, or one of them, were removed.",
        {"scope": "The record they belonged to.", "names": "The names removed."},
    ),
    EventType(
        "secret.used",
        "A component read a secret's value, and why (the value is never recorded).",
        {"scope": "The record it belongs to.", "name": "Its name there.", "user": "The component.", "why": "Why."},
    ),
]


class SecretsError(Exception):
    """A secret that does not exist, or a scope or name that cannot be one."""


@dataclass(frozen=True)
class Shown:
    """What a client may see of a secret."""

    name: str
    set: str
    ends: str


class Secrets:
    """The secrets of one CLANK_HOME."""

    def __init__(self, home: Home, events: EventLog, clock: Clock) -> None:
        self.folder = home.secrets
        self.events = events
        self.clock = clock

    def put(self, scope: str, name: str, value: str, *, actor: Actor) -> None:
        """Keep a secret, replacing one of the same name."""
        path = self._path(scope, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.part")
        with partial.open("w", encoding="utf-8", newline="") as file:
            file.write(value)
        if sys.platform != "win32":
            partial.chmod(0o600)
        now = self.clock.now().timestamp()
        os.utime(partial, (now, now))  # when it was set, by Clank's clock
        os.replace(partial, path)
        self.events.record(
            "secret.set",
            summary=f"{actor.describe()} set the secret {name} of {scope}",
            actor=actor,
            subject=_subject(scope),
            data={"scope": scope, "name": name, "ends": value[-4:]},
        )

    def value(self, scope: str, name: str, *, user: str, why: str) -> str:
        """A secret's value, for a component that needs it; recorded with who and why."""
        path = self._path(scope, name)
        if not path.is_file():
            raise SecretsError(f"no secret {name} for {scope}")
        found = path.read_text(encoding="utf-8")
        self.events.record(
            "secret.used",
            summary=f"{user} used the secret {name} of {scope}: {why}",
            actor=CLANK,
            subject=_subject(scope),
            data={"scope": scope, "name": name, "user": user, "why": why},
        )
        return found

    def shown(self, scope: str) -> list[Shown]:
        """The secrets of a record, as a client may see them."""
        folder = self._folder(scope)
        if not folder.is_dir():
            return []
        found = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                set_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                ends = path.read_text(encoding="utf-8")[-4:]
                found.append(Shown(path.name, to_text(set_at), ends))
        return found

    def remove(self, scope: str, name: str | None = None, *, actor: Actor) -> None:
        """Remove one secret of a record, or all of them."""
        folder = self._folder(scope)
        paths = [self._path(scope, name)] if name else (sorted(folder.iterdir()) if folder.is_dir() else [])
        names = [path.name for path in paths if path.is_file()]
        for path in paths:
            path.unlink(missing_ok=True)
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
        if names:
            self.events.record(
                "secret.removed",
                summary=f"{actor.describe()} removed {', '.join(names)} of {scope}",
                actor=actor,
                subject=_subject(scope),
                data={"scope": scope, "names": names},
            )

    def _folder(self, scope: str) -> Path:
        kind, _, record = scope.partition("/")
        if not (WORD.fullmatch(kind) and WORD.fullmatch(record)) or ".." in scope:
            raise SecretsError(f"{scope!r} cannot be a secret's scope: a kind and a record, such as mcp-server/name")
        return self.folder / kind / record

    def _path(self, scope: str, name: str) -> Path:
        if not WORD.fullmatch(name) or ".." in name:
            raise SecretsError(f"{name!r} cannot be a secret's name: letters, digits, '.', '_' and '-' only")
        return self._folder(scope) / name


def _subject(scope: str) -> Subject:
    kind, _, record = scope.partition("/")
    return Subject(kind=kind, id=record)
