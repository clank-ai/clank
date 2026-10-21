"""The kernel assembled: every part of the kernel, wired together, with each component's declarations and parts.

`open_kernel` is what the service (and a test) calls: it creates CLANK_HOME's folders, opens the state database and
applies the kernel's and the components' migrations, reads the settings, and builds each component's part, whose
operation types join the kernel's. The kernel takes the components it is given and imports none of them (decision
0019): the list comes from `clank.registry`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from clank.kernel import kinds as kernel_kinds
from clank.kernel.clock import Clock
from clank.kernel.components import Component
from clank.kernel.events import EventLog, EventTypes
from clank.kernel.home import Home
from clank.kernel.operations import Operations
from clank.kernel.questions import Questions
from clank.kernel.records import Registry
from clank.kernel.secrets import Secrets
from clank.kernel.settings import SettingsFiles
from clank.kernel.store import Store, kernel_migrations, migrations_in


@dataclass
class Kernel:
    """The kernel's parts, and the parts the components built on them."""

    home: Home
    clock: Clock
    store: Store
    events: EventLog
    settings: SettingsFiles
    questions: Questions
    operations: Operations
    kinds: Registry
    components: tuple[Component, ...]
    secrets: Secrets
    parts: dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        """Close the state database."""
        self.store.close()


def declared_kinds(components: Sequence[Component]) -> Registry:
    """The kernel's kinds of record and every component's."""
    found = Registry()
    for kind in [*kernel_kinds.KINDS, *(kind for component in components for kind in component.kinds)]:
        found.add(kind)
    return found


def declared_event_types(components: Sequence[Component]) -> EventTypes:
    """The kernel's event types and every component's."""
    return EventTypes([*kernel_kinds.EVENT_TYPES, *(t for component in components for t in component.event_types)])


def open_kernel(home: Home, clock: Clock, components: Sequence[Component]) -> Kernel:
    """Open the kernel in a CLANK_HOME, with the given components built on it."""
    home.ensure()
    kinds = declared_kinds(components)
    store = Store(home.database)
    migrations = kernel_migrations()
    for component in components:
        if component.migrations:
            migrations += migrations_in(component.migrations, component.name)
    store.migrate(migrations)
    events = EventLog(store, clock, declared_event_types(components))
    settings = SettingsFiles(home, kinds.settings(), events=events, clock=clock)
    settings.load()
    questions = Questions(store, events, clock)
    operations = Operations(store, events, questions, clock, [])
    secrets = Secrets(home, events, clock)
    kernel = Kernel(home, clock, store, events, settings, questions, operations, kinds, tuple(components), secrets)
    for component in components:
        if component.build is None:
            continue
        part = component.build(kernel)
        kernel.parts[component.name] = part
        for operation_type in getattr(part, "operation_types", list)():
            operations.add_type(operation_type)
    return kernel
