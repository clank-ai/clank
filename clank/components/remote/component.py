"""The remote component's declaration (design 0002 §1, design 0005, decision 0012).

It owns the phone: its settings (`config/remote.json`: on or off, its ports), the paired devices and their pairing
codes (its tables), the phone's listener and page, publishing it on the tailnet through Tailscale, and the files the
agents sent to the phone. It uses the workspaces (their folders and containers), the agents (the session bridge), the
runtime (the model the phone shows) and the flows (what a question about a flow shows: design 0013 §10).
"""

from typing import Any

from clank.components.remote.kinds import RemoteSettings
from clank.components.remote.service import EVENT_TYPES, Remote
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank remote`."""
    from clank.components.remote.cli import remote

    return [remote]


def pages() -> list[Any]:
    """The Phone page in the console."""
    from clank.components.remote.console.phone import PhonePage

    return [PhonePage]


COMPONENT = Component(
    name="remote",
    summary="The phone: its page over the tailnet, paired devices, and the files the agents send to it.",
    uses=("workspaces", "agents", "runtime", "gateway", "machine", "flows"),
    kinds=(RemoteSettings,),
    event_types=tuple(EVENT_TYPES),
    migrations="clank.components.remote",
    build=Remote,
    commands=commands,
    console=pages,
)
