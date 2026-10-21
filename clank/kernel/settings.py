"""Settings files: the records the user decides, kept as readable JSON files (decision 0007, design 0002 §2.2).

Each settings kind keeps its files under `CLANK_HOME/config/`: one file for a kind with a single record
(`config/service.json`), else one per record in the kind's folder (`config/presets/daily-262k.json`), or one folder
deeper for a kind grouped by something (`config/flows/myproject/new-study.json`, the record `myproject/new-study`); an
id is plain names, so no record reaches outside its kind's folder. Clank ships its own in `clank/defaults/`, in the
same format; a user file of the same name replaces Clank's whole. A single-record kind with no file at all has its
built-in values. Every file names its schema and version first (`"schema": "service/1"`):
an older file is migrated, its original kept beside it as `<name>.v<N>.json`; a newer one is refused. A file that
cannot be read (bad JSON, a wrong type, an unknown field) is reported with its file, line and field, and the last good
values stay in force. A component may also check a kind's records against other records (a flow's presets), which the
kind's own validation cannot see: a record that check finds wrong is refused when written and reported when read, the
same way. Clank writes a file in one fixed format (two-space indents, "schema" first, then the fields in the
kind's order, only the values that differ from the defaults), atomically, and only over the version the change was
based on (its revision), so a file edited in the meantime is never overwritten. Every change, by a client or by an edit
of the file itself, is recorded with each field's old and new value, once the files' lock is released: a listener may
wait for another thread that reads the settings (the event stream waits for the service's event loop, where the flows'
driver reads them), so none is told while the lock is held.
"""

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from clank.kernel.clock import Clock
from clank.kernel.events import Actor, Event, EventLog, EventType, Subject
from clank.kernel.home import Home
from clank.kernel.records import Settings

DEFAULTS = Path(__file__).resolve().parents[1] / "defaults"
BUILT_IN = "built-in"
KEPT_ORIGINAL = re.compile(r"\.v\d+$")
NOT_IN_A_NAME = set('\\:*?"<>|')  # what Windows refuses in a file's name, and the separator it takes besides "/"
FILE_EDIT = Actor(kind="user", via="file")
Source = Literal["built-in", "default", "user"]
InUse = Callable[[str, str], str | None]
Place = tuple[str | int, ...]
Check = Callable[[str, Settings], list[tuple[Place, str]]]

EVENT_TYPES = [
    EventType(
        "settings.changed",
        "A settings record was created, changed or removed, by a client or by an edit of its file.",
        {
            "kind": "The kind of record.",
            "id": "The record.",
            "file": "Its file, relative to CLANK_HOME.",
            "changes": "Each field that changed, with its old and new value.",
            "applies": "When the change takes effect: now, or at the next start.",
        },
    ),
    EventType(
        "settings.invalid",
        "A settings file could not be read; the last good values stay in force until it is fixed.",
        {
            "file": "The file.",
            "line": "The line of the problem, when known.",
            "field": "The field, when known.",
            "message": "What is wrong.",
        },
    ),
    EventType(
        "settings.migrated",
        "A settings file written by an older Clank was brought to the current version; its original is kept.",
        {
            "kind": "The kind of record.",
            "id": "The record.",
            "file": "The file.",
            "from": "The version it was written in.",
            "to": "The version it is now.",
            "original": "Where the original was kept.",
        },
    ),
]


@dataclass(frozen=True)
class Loaded:
    """A settings record as read: its values, where they come from, the revision a change must be based on, and where
    the user's file of it is, or would be."""

    kind: str
    id: str
    record: Settings
    source: Source
    path: Path | None
    revision: str
    user_file: Path


@dataclass(frozen=True)
class SettingsProblem:
    """Why a settings file could not be read: the file, the line and the field when known, and what is wrong."""

    path: Path
    line: int | None
    field: str | None
    message: str

    def __str__(self) -> str:
        where = (
            str(self.path) + (f", line {self.line}" if self.line else "") + (f", {self.field}" if self.field else "")
        )
        return f"{where}: {self.message}"


class SettingsError(Exception):
    """A change that was refused; `current` is the record as it is now, for the client to show beside its own."""

    def __init__(self, message: str, current: Loaded | None = None) -> None:
        super().__init__(message)
        self.current = current


class SettingsFiles:
    """Every settings record of the given kinds: read from their files, written back, and every change recorded."""

    def __init__(
        self,
        home: Home,
        kinds: Iterable[type[Settings]],
        *,
        events: EventLog,
        clock: Clock,
        defaults: Path = DEFAULTS,
        in_use: InUse | None = None,
    ) -> None:
        self._home = home
        self._kinds = {kind.KIND: kind for kind in kinds}
        self._events = events
        self._clock = clock
        self._defaults = defaults
        self._in_use = in_use
        self._records: dict[tuple[str, str], Loaded] = {}
        self._problems: set[SettingsProblem] = set()
        self._checks: dict[str, Check] = {}
        self._lock = threading.RLock()

    def load(self) -> list[SettingsProblem]:
        """Read every file again; returns the problems found. A file that no longer reads keeps its last good values."""
        with self._lock:
            problems, new = self._load()
        self._report(new)
        return problems

    def check_with(self, kind: str, check: Check) -> None:
        """Check every record of a kind against other records too (a flow's presets): `check(id, record)` names each
        place that is wrong and why. A record it finds wrong is refused when written, and its file is reported when
        read, the last good values staying in force. The files are read again, and the records read before were never
        checked, so none of them stays in force when found wrong."""
        self._kind(kind)
        with self._lock:
            self._checks[kind] = check
            self._records = {key: loaded for key, loaded in self._records.items() if key[0] != kind}
            _, new = self._load()
        self._report(new)

    def records(self, kind: str) -> list[Loaded]:
        """Every record of a kind, by id."""
        self._kind(kind)
        with self._lock:
            return sorted((loaded for loaded in self._records.values() if loaded.kind == kind), key=lambda r: r.id)

    def get(self, kind: str, id: str) -> Loaded:
        """One record."""
        self._kind(kind)
        with self._lock:
            if (kind, id) not in self._records:
                raise SettingsError(f"there is no {kind} named {id!r}")
            return self._records[(kind, id)]

    def write(self, kind: str, id: str, values: dict[str, Any], *, base: str | None, actor: Actor) -> Loaded:
        """Write a record from its values, if `base` is the revision it is at now; returns the record as written."""
        settings_kind = self._kind(kind)
        with self._lock:
            _check_id(settings_kind, id)
            current = self._check(settings_kind, id, base)
            try:
                record = settings_kind.model_validate(values)
            except ValidationError as error:
                problems = "; ".join(f"{_path(e['loc'])}: {_message(e, kind)}" for e in error.errors())
                raise SettingsError(f"the values were refused: {problems}", current) from error
            wrong = self._checks[kind](id, record) if kind in self._checks else []
            if wrong:
                problems = "; ".join(f"{_path(place)}: {message}" if place else message for place, message in wrong)
                raise SettingsError(f"the values were refused: {problems}", current)
            path = self._user_path(settings_kind, id)
            text = render(record)
            _write_atomically(path, text)
            loaded = Loaded(kind, id, record, "user", path, _revision(text.encode("utf-8")), path)
            self._records[(kind, id)] = loaded
        self._announce(current, loaded, actor)
        return loaded

    def delete(self, kind: str, id: str, *, base: str, actor: Actor) -> None:
        """Remove the user's file of a record; Clank's default of the same name, if any, comes back."""
        settings_kind = self._kind(kind)
        with self._lock:
            _check_id(settings_kind, id)
            current = self._check(settings_kind, id, base)
            if current is None or current.source != "user" or current.path is None:
                raise SettingsError(f"{_name(settings_kind, id)} is Clank's own; change it instead", current)
            current.path.unlink()
            records, _ = self._collect()
            after = records.get((kind, id))
            if after is None:
                self._records.pop((kind, id), None)
            else:
                self._records[(kind, id)] = after
        self._announce(current, after, actor)

    def reload_changed(self) -> list[Event]:
        """Read the files again and record every change made to them by hand; returns those events."""
        with self._lock:
            before = dict(self._records)
            _, problems = self._load()
            changed = [
                (before.get(key), self._records.get(key))
                for key in sorted(set(before) | set(self._records))
                if before.get(key) is None
                or self._records.get(key) is None
                or before[key].revision != self._records[key].revision
            ]
        self._report(problems)
        announced = []
        for old, new in changed:
            event = self._announce(old, new, FILE_EDIT)
            if event is not None:
                announced.append(event)
        return announced

    def problems(self) -> list[SettingsProblem]:
        """The files that could not be read at the last load."""
        with self._lock:
            return sorted(self._problems, key=lambda problem: (str(problem.path), problem.line or 0))

    def _load(self) -> tuple[list[SettingsProblem], list[SettingsProblem]]:
        """Read every file again, under the lock: the problems found, and those of them not found before (reported
        once the lock is released)."""
        before = self._records
        records, problems = self._collect()
        self._records = records
        problems += self._checked(before)
        new = [problem for problem in problems if problem not in self._problems]
        self._problems = set(problems)
        return problems, new

    def _report(self, problems: list[SettingsProblem]) -> None:
        """Record each problem newly found in a file (never while the lock is held)."""
        for problem in problems:
            self._events.record(
                "settings.invalid",
                summary=f"{self._shown(problem.path)} could not be read: {problem.message}",
                actor=FILE_EDIT,
                data={
                    "file": self._shown(problem.path),
                    "line": problem.line,
                    "field": problem.field,
                    "message": problem.message,
                },
            )

    def _kind(self, kind: str) -> type[Settings]:
        if kind not in self._kinds:
            raise SettingsError(f"there is no settings kind named {kind!r}")
        return self._kinds[kind]

    def _check(self, kind: type[Settings], id: str, base: str | None) -> Loaded | None:
        current = self._records.get((kind.KIND, id))
        path = self._user_path(kind, id)
        if path.exists():
            actual: str | None = _revision(path.read_bytes())
            if current is None or current.revision != actual:
                current = self._reread(kind, id, path) or current
        else:
            actual = current.revision if current is not None else None
        if base != actual:
            raise SettingsError(f"{self._shown(path)} changed since it was read; here is its current version", current)
        reason = self._in_use(kind.KIND, id) if self._in_use is not None else None
        if kind.ON_CHANGE == "refused" and reason:
            raise SettingsError(f"{_name(kind, id)} is in use ({reason}); it cannot be changed now", current)
        return current

    def _reread(self, kind: type[Settings], id: str, path: Path) -> Loaded | None:
        result = self._read(kind, id, path, "user")
        if isinstance(result, Loaded) and not self._wrong(result):
            self._records[(kind.KIND, id)] = result
            return result
        return None

    def _checked(self, before: dict[tuple[str, str], Loaded]) -> list[SettingsProblem]:
        """The problems of each record its component's check finds wrong; such a record gives way to its last good
        values from the same file, or to none."""
        found: list[SettingsProblem] = []
        for key, loaded in list(self._records.items()):
            wrong = self._wrong(loaded)
            if not wrong:
                continue
            found += wrong
            previous = before.get(key)
            if previous is not None and previous.path == loaded.path:
                self._records[key] = previous
            else:
                del self._records[key]
        return found

    def _wrong(self, loaded: Loaded) -> list[SettingsProblem]:
        """What its component's check finds wrong with a record read from a file, each with its line and field."""
        check = self._checks.get(loaded.kind)
        if check is None or loaded.path is None:
            return []
        wrong = check(loaded.id, loaded.record)
        if not wrong:
            return []
        try:
            text = loaded.path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            text = ""
        return [
            SettingsProblem(loaded.path, line_of(text, place) if text and place else None, _path(place) or None, why)
            for place, why in wrong
        ]

    def _announce(self, old: Loaded | None, new: Loaded | None, actor: Actor) -> Event | None:
        target = new or old
        if target is None:
            return None
        kind = self._kinds[target.kind]
        changes = _changes(old.record if old else None, new.record if new else None)
        if old is not None and new is not None and not changes:
            return None
        if new is None:
            verb = "removed"
        elif old is None:
            verb = "created"
        else:
            verb = "changed"
        fields = ", ".join(change["field"] for change in changes)
        summary = f"{actor.describe()} {verb} {_name(kind, target.id)}" + (f": {fields}" if verb == "changed" else "")
        path = target.path or self._user_path(kind, target.id)
        return self._events.record(
            "settings.changed",
            summary=summary,
            actor=actor,
            subject=Subject(kind=target.kind, id=target.id),
            data={
                "kind": target.kind,
                "id": target.id,
                "file": self._shown(path),
                "changes": changes,
                "applies": "at the next start" if kind.ON_CHANGE == "next start" else "now",
            },
        )

    def _collect(self) -> tuple[dict[tuple[str, str], Loaded], list[SettingsProblem]]:
        records: dict[tuple[str, str], Loaded] = {}
        problems: list[SettingsProblem] = []
        for kind in self._kinds.values():
            for source, folder in (("default", self._defaults), ("user", self._home.config)):
                problems += self._ungrouped(kind, folder)
                for id, path in self._files(kind, folder):
                    result = self._read(kind, id, path, source)  # type: ignore[arg-type]
                    if isinstance(result, Loaded):
                        records[(kind.KIND, id)] = result
                        continue
                    problems += result
                    previous = self._records.get((kind.KIND, id))
                    if previous is not None and previous.path == path:
                        records[(kind.KIND, id)] = previous
            if kind.SINGLE and (kind.KIND, kind.KIND) not in records:
                records[(kind.KIND, kind.KIND)] = Loaded(
                    kind.KIND, kind.KIND, kind(), "built-in", None, BUILT_IN, self._user_path(kind, kind.KIND)
                )
        return records, problems

    def _files(self, kind: type[Settings], folder: Path) -> list[tuple[str, Path]]:
        if kind.SINGLE:
            path = folder / f"{kind.KIND}.json"
            return [(kind.KIND, path)] if path.is_file() else []
        directory = folder / kind.folder()
        if not directory.is_dir():
            return []
        if kind.GROUPED_BY:
            return [
                (f"{path.parent.name}/{path.stem}", path)
                for path in sorted(directory.glob("*/*.json"))
                if not KEPT_ORIGINAL.search(path.stem)
            ]
        return [(path.stem, path) for path in sorted(directory.glob("*.json")) if not KEPT_ORIGINAL.search(path.stem)]

    def _ungrouped(self, kind: type[Settings], folder: Path) -> list[SettingsProblem]:
        """The files directly in a grouped kind's folder, which belong to no group and so are no record."""
        directory = folder / kind.folder()
        if not kind.GROUPED_BY or not directory.is_dir():
            return []
        where = f"{kind.folder()}/<{kind.GROUPED_BY}>/<name>.json"
        return [
            SettingsProblem(
                path, None, None, f"belongs to no {kind.GROUPED_BY}: a {kind.LABEL.lower()} is kept as {where}"
            )
            for path in sorted(directory.glob("*.json"))
        ]

    def _user_path(self, kind: type[Settings], id: str) -> Path:
        if kind.SINGLE:
            return self._home.config / f"{kind.KIND}.json"
        return self._home.config / kind.folder() / f"{id}.json"

    def _read(self, kind: type[Settings], id: str, path: Path, source: Source) -> "Loaded | list[SettingsProblem]":
        found = read_record(kind, path)
        if isinstance(found, list):
            return found
        record, version, raw = found
        if version < kind.VERSION and source == "user":
            raw = self._migrate(kind, id, path, raw, record, version)
        return Loaded(kind.KIND, id, record, source, path, _revision(raw), self._user_path(kind, id))

    def _migrate(self, kind: type[Settings], id: str, path: Path, raw: bytes, record: Settings, version: int) -> bytes:
        original = path.with_name(f"{path.stem}.v{version}.json")
        if not original.exists():
            original.write_bytes(raw)
        text = render(record)
        _write_atomically(path, text)
        self._events.record(
            "settings.migrated",
            summary=f"{self._shown(path)} was brought from version {version} to {kind.VERSION}",
            actor=Actor(kind="clank"),
            subject=Subject(kind=kind.KIND, id=id),
            data={
                "kind": kind.KIND,
                "id": id,
                "file": self._shown(path),
                "from": version,
                "to": kind.VERSION,
                "original": self._shown(original),
            },
        )
        return text.encode("utf-8")

    def _shown(self, path: Path) -> str:
        for base, prefix in ((self._home.root, ""), (self._defaults.parent, "clank/")):
            try:
                return prefix + path.relative_to(base).as_posix()
            except ValueError:
                continue
        return path.as_posix()


def read_record(kind: type[Settings], path: Path) -> "tuple[Settings, int, bytes] | list[SettingsProblem]":
    """One settings file read and checked by its kind, migrated in memory when it is older: its record, the version it
    was written in and its bytes; or why it cannot be read, with its line and field. Writes nothing (the console reads
    its own settings this way, before the service answers)."""
    raw = path.read_bytes()

    def problem(message: str, line: int | None = None, field: str | None = None) -> list[SettingsProblem]:
        return [SettingsProblem(path, line, field, message)]

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return problem("is not UTF-8 text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return problem(f"is not valid JSON: {error.msg}", error.lineno)
    if not isinstance(data, dict):
        return problem("must hold one JSON object")
    schema = data.pop("schema", None)
    expected = f"{kind.KIND}/{kind.VERSION}"
    if not isinstance(schema, str):
        return problem(f'names no schema: its first field must be "schema": "{expected}"', 1, "schema")
    name, _, written = schema.partition("/")
    line = line_of(text, ("schema",))
    if name != kind.KIND or not written.isdigit():
        return problem(f"names the schema {schema}, not {expected}", line, "schema")
    version = int(written)
    if version > kind.VERSION:
        return problem(f"was written by a newer Clank ({schema}); this one reads up to {expected}", line, "schema")
    for step in range(version, kind.VERSION):
        if step not in kind.MIGRATIONS:
            return problem(f"cannot be migrated from version {step}", line, "schema")
        data = kind.MIGRATIONS[step](data)
    try:
        record = kind.model_validate(data)
    except ValidationError as error:
        return [
            SettingsProblem(path, line_of(text, e["loc"]), _path(e["loc"]), _message(e, kind.KIND))
            for e in error.errors()
        ]
    return record, version, raw


def render(record: Settings) -> str:
    """A record in the fixed format: "schema" first, then the fields in the kind's order, defaults left out."""
    kind = type(record)
    values = record.model_dump(mode="json", exclude_defaults=True)
    ordered: dict[str, Any] = {"schema": f"{kind.KIND}/{kind.VERSION}"}
    ordered.update((name, values[name]) for name in kind.model_fields if name in values)
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def _changes(old: Settings | None, new: Settings | None) -> list[dict[str, Any]]:
    before = old.model_dump(mode="json") if old is not None else {}
    after = new.model_dump(mode="json") if new is not None else {}
    names = list(after) + [name for name in before if name not in after]
    return [
        {"field": name, "old": before.get(name), "new": after.get(name)}
        for name in names
        if before.get(name) != after.get(name)
    ]


def _name(kind: type[Settings], id: str) -> str:
    return kind.LABEL if kind.SINGLE else f"{kind.LABEL} {id}"


def _check_id(kind: type[Settings], id: str) -> None:
    """Refuse an id that is not plain names (one, or a group and a name for a grouped kind): it would reach a file
    outside the kind's folder."""
    parts = id.split("/")
    wanted = 2 if kind.GROUPED_BY else 1
    plain = all(part and not part.startswith(".") and not set(part) & NOT_IN_A_NAME for part in parts)
    if kind.SINGLE or (len(parts) == wanted and plain):
        return
    shape = f"<{kind.GROUPED_BY}>/<name>" if kind.GROUPED_BY else "a plain name"
    raise SettingsError(f"{id!r} cannot name a {kind.LABEL.lower()}: its id is {shape}, without '..', '\\' or ':'")


def _revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.writing")
    temporary.write_bytes(text.encode("utf-8"))
    os.replace(temporary, path)


def _path(location: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in location)


def line_of(text: str, location: tuple[Any, ...]) -> int | None:
    """The line of the field at `location` (its keys and list positions), or of the nearest enclosing one that is in
    the text (a missing field's parent); a component's own checks of a file name their lines with it."""
    lines = _key_lines(text)
    for end in range(len(location), 0, -1):
        if (line := lines.get(tuple(location[:end]))) is not None:
            return line
    return None


def _key_lines(text: str) -> dict[tuple[str | int, ...], int]:
    """The line of each key and list item in a valid JSON text, by its path; a repeated key counts where JSON takes it
    from, its last occurrence."""
    found: dict[tuple[str | int, ...], int] = {}
    at = 0

    def skip() -> None:
        nonlocal at
        while at < len(text) and text[at] in " \t\r\n﻿":
            at += 1

    def string() -> str:
        nonlocal at
        start, at = at, at + 1
        while text[at] != '"':
            at += 2 if text[at] == "\\" else 1
        at += 1
        return str(json.loads(text[start:at]))

    def value(path: tuple[str | int, ...]) -> None:
        nonlocal at
        skip()
        opening = text[at]
        if opening in "{[":
            at += 1
            index = 0
            skip()
            while text[at] not in "}]":
                skip()
                line = text.count("\n", 0, at) + 1
                if opening == "{":
                    key: str | int = string()
                    skip()
                    at += 1  # the colon
                else:
                    key, index = index, index + 1
                found[(*path, key)] = line
                value((*path, key))
                skip()
                if text[at] == ",":
                    at += 1
            at += 1
        elif opening == '"':
            string()
        else:
            while at < len(text) and text[at] not in ",]} \t\r\n":
                at += 1

    try:
        value(())
    except (IndexError, ValueError):
        return {}
    return found


def _message(error: Any, kind: str) -> str:
    if error["type"] == "extra_forbidden":
        return f"is not a field of {kind}"
    return str(error["msg"])
