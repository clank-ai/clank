"""Adapters: how Clank uses programs it does not own, one module per program (design 0002 §2.10).

Each kind of adapter (container platform, engine, endpoint, dialect, agent program, channel, registry) has an
interface, the list of its adapters, one contract test file run against every adapter of the kind
(`tests/contract/test_<kind>.py`), and fixtures recorded from the real program at its pinned version
(`tests/fixtures/<adapter>/<version>/program.json`); a test fails when one of these is missing. A component declares
the kinds of adapter it owns (`Component.adapter_kinds`); one module, its fixtures and a line in its kind's list add an
adapter. An adapter whose program is the running system itself (the local host of engines) has nothing to record: it
says `RECORDED = False`, and its contract runs live. What an adapter supports is read from the program in use (its
version, its options), never assumed for the program: `capabilities()` asks.
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar


class AdapterError(Exception):
    """An adapter that is not what its kind requires, or one that does not exist."""


@dataclass(frozen=True)
class Capability:
    """One thing an adapter can or cannot do with the program in use, and how (or why not)."""

    name: str
    supported: bool
    how: str


class Adapter(ABC):
    """What every adapter is: a name, a label, the platforms it works on, and what it supports."""

    NAME: ClassVar[str] = ""
    LABEL: ClassVar[str] = ""
    PLATFORMS: ClassVar[tuple[str, ...]] = ()
    RECORDED: ClassVar[bool] = True

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """What it supports, read from the program in use."""


class AdapterKind[A: Adapter]:
    """A kind of adapter: its interface (an abstract class), and the list of its adapters, each checked against it."""

    def __init__(self, name: str, summary: str, interface: type, adapters: Sequence[type[A]]) -> None:
        self.name = name
        self.summary = summary
        self.interface = interface
        names: set[str] = set()
        for adapter in adapters:
            _check(adapter, interface)
            if adapter.NAME in names:
                raise AdapterError(f"two adapters of the kind {name} are named {adapter.NAME}")
            names.add(adapter.NAME)
        self._adapters = list(adapters)

    def all(self) -> list[type[A]]:
        """Every adapter of the kind, in the order its list gives."""
        return list(self._adapters)

    def get(self, name: str) -> type[A]:
        """The adapter of this name."""
        for adapter in self._adapters:
            if name == adapter.NAME:
                return adapter
        known = ", ".join(adapter.NAME for adapter in self._adapters)
        raise AdapterError(f"there is no {self.name} adapter named {name!r}; the known ones: {known}")

    def for_platform(self, platform: str) -> list[type[A]]:
        """The adapters that work on a platform (`sys.platform`'s names)."""
        return [adapter for adapter in self._adapters if platform in adapter.PLATFORMS]


def _check(adapter: type, interface: type) -> None:
    if not (inspect.isclass(adapter) and issubclass(adapter, interface)):
        raise AdapterError(f"{adapter!r} does not implement {interface.__name__}")
    declared = {attribute: getattr(adapter, attribute, None) for attribute in ("NAME", "LABEL", "PLATFORMS")}
    for attribute, value in declared.items():
        if not value:
            raise AdapterError(f"the adapter {adapter.__name__} has no {attribute}")
    missing = sorted(getattr(adapter, "__abstractmethods__", ()))
    if missing:
        raise AdapterError(f"the adapter {declared['NAME']} does not implement {', '.join(missing)}")
