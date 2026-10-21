"""The Clank service's own declarations: its settings kind and its event types.

They live apart from `clank/kernel/service.py` (the service's life cycle) so that the kernel's list of declarations
(`clank/kernel/kinds.py`) can name them without importing the service, which itself opens the assembled kernel.
The service's settings are one record, `config/service.json`: where its API listens, and how long it keeps its
history; a change applies at the service's next start.
"""

from pydantic import Field

from clank.kernel.events import EventType
from clank.kernel.records import Settings

EVENT_TYPES = [
    EventType(
        "service.started",
        "The Clank service started and its API answers.",
        {"url": "Where its API listens.", "version": "Clank's version.", "pid": "Its process."},
    ),
    EventType("service.stopped", "The Clank service stopped; what runs in the data plane is left running."),
    EventType(
        "service.clients",
        "A client began or stopped following the event stream; every client following it hears who is connected.",
        {"clients": "The clients following the stream, by the names they give (console, vscode, cli)."},
        live=True,
    ),
]


class ServiceSettings(Settings):
    """How the Clank service runs."""

    KIND = "service"
    LABEL = "Service"
    HELP = "How the Clank service runs: where its API listens, and how long it keeps its history."
    SINGLE = True
    ON_CHANGE = "next start"

    host: str = Field(
        "127.0.0.1",
        title="Address",
        description="The address the API listens on; 127.0.0.1 keeps it to this machine (design 0002 §2.7).",
    )
    port: int = Field(7720, ge=1024, le=65535, title="Port", description="The TCP port the API listens on.")
    events_kept_days: int = Field(
        30, ge=1, title="History kept", description="How many days events are kept before they are pruned."
    )
