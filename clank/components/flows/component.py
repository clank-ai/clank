"""The flows component's declaration (design 0013; decisions 0057-0066).

It owns the flows: the work as a program of boxes, each a big task with a deliverable done by a model in a session of
its own, or a decision the owner makes. A flow is its file, `config/flows/<workspace>/<name>.json`, read and checked
(design 0013 §14, step 1); its runs are state, `state/flows/<workspace>/<name>/run-<n>/` (step 2). It uses the
workspaces (a flow's folder), the runtime (the presets its boxes run on, the main slot switched to each), the agents
(the sessions its boxes run in, a plan's progress, the owner's own sessions) and the gateway (the requests in flight on
the main slot, which a switch waits for).
"""

from typing import Any

from clank.components.flows.kinds import Flow
from clank.components.flows.service import EVENT_TYPES, Flows
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank flow`."""
    from clank.components.flows.cli import flow

    return [flow]


COMPONENT = Component(
    name="flows",
    summary="Flows: the work as a program of boxes, each a fresh session with its own model, run one after another.",
    uses=("workspaces", "runtime", "agents", "gateway"),
    kinds=(Flow,),
    event_types=tuple(EVENT_TYPES),
    build=Flows,
    commands=commands,
)
