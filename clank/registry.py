"""Everything declared, in one place: the components, the kinds of record and event types of the kernel and of every
component, and the kinds of adapter (design 0002 §2.1, §2.10).

The service, the generated documents (the schemas, the events page, the API page) and the tests all read these lists,
so a kind or an event type declared anywhere reaches all of them.
"""

from typing import Any

from clank.components import COMPONENTS
from clank.kernel.adapters import AdapterKind
from clank.kernel.components import Component
from clank.kernel.core import declared_event_types, declared_kinds
from clank.kernel.events import EventTypes
from clank.kernel.records import Registry


def components() -> tuple[Component, ...]:
    """Every component of the service."""
    return COMPONENTS


def kinds() -> Registry:
    """Every kind of record Clank declares."""
    return declared_kinds(COMPONENTS)


def event_types() -> EventTypes:
    """Every event type Clank declares."""
    return declared_event_types(COMPONENTS)


def adapter_kinds() -> list[AdapterKind[Any]]:
    """Every kind of adapter, with its adapters."""
    return [kind for component in COMPONENTS for kind in component.adapter_kinds]
