"""Records: everything Clank manages is a record of a kind (design 0002 §2.2).

A kind is one Pydantic class, declared once (decision 0015): its fields, each with a label (`title`) and help
(`description`) that the explain key shows, and class constants saying what the kind is. Settings kinds are files the
user decides (`clank.kernel.settings` reads and writes them); state kinds are what Clank records about what happens,
kept in the state database by the part that owns them. The JSON Schemas of the settings files, the API's description
and the clients' types all come from these classes.
"""

from collections.abc import Callable, Iterator
from typing import Any, ClassVar, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

Migration = Callable[[dict[str, Any]], dict[str, Any]]


class Kind(BaseModel):
    """The base of every kind of record: `KIND` names it, `LABEL` and `HELP` describe it to the user."""

    model_config = ConfigDict(extra="forbid")

    KIND: ClassVar[str]
    LABEL: ClassVar[str]
    HELP: ClassVar[str]


class Settings(Kind):
    """A kind the user decides, kept as readable JSON files in `CLANK_HOME/config/` (decision 0007).

    `SINGLE` kinds have one record (`config/<kind>.json`); the others have a folder (`config/<folder>/<id>.json`).
    `GROUPED_BY` names what a kind's records are grouped by, one folder each, when they are: a flow is
    `config/flows/<workspace>/<name>.json`, its id `<workspace>/<name>` (design 0013 §11).
    `VERSION` is the schema version files are written in; `MIGRATIONS[n]` turns a version-n file into version n + 1.
    `ON_CHANGE` says what a change does to a record in use: it applies now, at the next start, or is refused;
    `NEXT_START` says whose start that is, as the clients say it (`applies`).
    """

    VERSION: ClassVar[int] = 1
    SINGLE: ClassVar[bool] = False
    FOLDER: ClassVar[str] = ""
    GROUPED_BY: ClassVar[str] = ""
    ON_CHANGE: ClassVar[Literal["now", "next start", "refused"]] = "now"
    NEXT_START: ClassVar[str] = "the service's next start"
    MIGRATIONS: ClassVar[dict[int, Migration]] = {}

    title: str = Field(
        "", title="Title", description="The name clients show for this record; the file's own name when empty."
    )

    @classmethod
    def folder(cls) -> str:
        """The folder of this kind's files under `config/` (for a kind with more than one record)."""
        return cls.FOLDER or f"{cls.KIND}s"

    @classmethod
    def applies(cls) -> str:
        """When a change to one of its records applies, in words."""
        return {
            "now": "at once",
            "next start": f"at {cls.NEXT_START}",
            "refused": "never while it is in use: Clank refuses the change",
        }[cls.ON_CHANGE]


class StateKind(Kind):
    """A kind Clank records about what happens, kept in the state database (decision 0014)."""


class RegistryError(Exception):
    """A kind that cannot be registered: declared twice, or missing what every kind declares."""


class Registry:
    """The kinds of record known to Clank, by name."""

    def __init__(self) -> None:
        self._kinds: dict[str, type[Kind]] = {}

    def add(self, kind: type[Kind]) -> None:
        """Register a kind; refuses one declared twice or missing `KIND`, `LABEL` or `HELP`."""
        for constant in ("KIND", "LABEL", "HELP"):
            value = getattr(kind, constant, None)
            if not isinstance(value, str) or not value:
                raise RegistryError(f"{kind.__name__} does not declare {constant}")
        if kind.KIND in self._kinds:
            raise RegistryError(f"the kind {kind.KIND!r} is declared twice")
        self._kinds[kind.KIND] = kind

    def get(self, name: str) -> type[Kind]:
        """The kind of that name."""
        if name not in self._kinds:
            raise RegistryError(f"there is no kind of record named {name!r}")
        return self._kinds[name]

    def all(self) -> list[type[Kind]]:
        """Every kind, in the order they were registered."""
        return list(self._kinds.values())

    def settings(self) -> list[type[Settings]]:
        """The settings kinds."""
        return [kind for kind in self._kinds.values() if issubclass(kind, Settings)]


def undocumented_fields(model: type[BaseModel], prefix: str = "") -> list[str]:
    """Every field of `model`, nested models included, that lacks a label or help, as "path: what is missing"."""
    missing: list[str] = []
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        if not info.title:
            missing.append(f"{path}: no label")
        if not info.description:
            missing.append(f"{path}: no help")
        for nested in _models_in(info.annotation):
            missing += undocumented_fields(nested, f"{path}.")
    return missing


def _models_in(annotation: Any) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for argument in get_args(annotation):
        yield from _models_in(argument)
