"""The gateway component's declaration (design 0002 §1, §2.1; design 0001 §6; design 0004 §2).

It owns the gateway: its settings (`config/gateway.json`), its process (supervised, adopted after a restart of the
service) and the routes that process follows, and the console's Requests page (the requests it kept); and completion
in VS Code (design 0006): its settings (`config/completion.json`) and the console's Completion page; from design 0016
each workspace's key at the gateway and its bound, and the cloud's costs, in its own tables (migration `gateway 0001`).
It uses the runtime, whose slots it routes to.
"""

from typing import Any

from clank.components.gateway.kinds import CompletionSettings, CostSettings, GatewaySettings, VisionSettings
from clank.components.gateway.service import EVENT_TYPES, Gateway
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank gateway` and `clank cost`."""
    from clank.components.gateway.cli import gateway
    from clank.components.gateway.costcli import cost

    return [gateway, cost]


def pages() -> list[Any]:
    """The Requests page and the Completion page."""
    from clank.components.gateway.console.completion import CompletionPage
    from clank.components.gateway.console.requests import RequestsPage

    return [RequestsPage, CompletionPage]


COMPONENT = Component(
    name="gateway",
    summary="Every model request, to the engine of its role's slot, in that engine's own fields; recorded.",
    uses=("runtime",),
    kinds=(GatewaySettings, CompletionSettings, VisionSettings, CostSettings),
    migrations="clank.components.gateway",
    event_types=tuple(EVENT_TYPES),
    build=Gateway,
    commands=commands,
    console=pages,
)
