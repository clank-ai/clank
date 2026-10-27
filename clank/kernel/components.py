"""A component: one part of the Clank service, with a fixed shape and a public interface (design 0002 §2.1).

A component is one package, `clank/components/<name>/`, always with the same files (`component.py`, `kinds.py`,
`service.py`, `api.py`, `cli.py`, then `console/` and `adapters/` when it has them), so that a reader of one finds their
way in any other. `component.py` holds its declaration, a `Component`: what it owns, the components it uses, its kinds
of record and event types (read without building anything, for the generated documents), the package of its database
migrations, the kinds of adapter it owns (design 0002 §2.10), how to build its part from the kernel, its commands (a
function returning its click commands), its console pages (a function returning its page classes, imported only by
the console, so the service never loads the console's library) and its own checks for `clank doctor` (a function of
CLANK_HOME returning each check's `id`, `title`, `status`, `detail` and `fix`, run without the service, after the
machine's: the phone's way in is the remote component's). The part a component builds may offer
`operation_types()`, `router()` (its API routes) and `run()` (what it does in the background while the service runs).
A component uses another only through that one's `service.py`, and only if its `uses` names it (decision 0019).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from clank.kernel.adapters import AdapterKind
from clank.kernel.events import EventType
from clank.kernel.home import Home
from clank.kernel.records import Kind


@dataclass(frozen=True)
class Component:
    """What a component declares."""

    name: str
    summary: str
    uses: tuple[str, ...] = ()
    kinds: tuple[type[Kind], ...] = ()
    event_types: tuple[EventType, ...] = ()
    migrations: str | None = None
    adapter_kinds: tuple[AdapterKind[Any], ...] = ()
    build: Callable[[Any], Any] | None = None
    commands: Callable[[], Any] | None = None
    console: Callable[[], list[Any]] | None = None
    checks: Callable[[Home], list[dict[str, Any]]] | None = None
