"""The runtime component's declaration (design 0003, design 0002 §1).

It owns the models Clank runs: presets, hosts, model files, the providers someone else runs (design 0016: OpenRouter)
and its own settings (its kinds), the engine, host and endpoint kinds of adapter (KVMem; this machine and its WSL
distributions; OpenRouter), and, from M1.3, the slots and what runs in them. It uses no other component.
"""

from typing import Any

from clank.components.runtime.adapters import ENDPOINTS, ENGINES
from clank.components.runtime.checking import EVENT_TYPES as CHECK_EVENT_TYPES
from clank.components.runtime.endpoints import EVENT_TYPES as ENDPOINT_EVENT_TYPES
from clank.components.runtime.hosts import HOSTS
from clank.components.runtime.kinds import Endpoint, Host, ModelFile, Preset, RuntimeSettings
from clank.components.runtime.service import Runtime
from clank.components.runtime.state import EVENT_TYPES, InstallRecord, LaunchRecord, SlotRecord
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank model`, `clank preset`, `clank host`, `clank engine`, `clank endpoint`."""
    from clank.components.runtime.cli import COMMANDS
    from clank.components.runtime.cloudcli import endpoint

    return [*COMMANDS, endpoint]


def pages() -> list[Any]:
    """The runtime's pages in the console."""
    from clank.components.runtime.console.addmodel import AddModelPage
    from clank.components.runtime.console.models import ModelsPage
    from clank.components.runtime.console.options import LaunchOptionsPage
    from clank.components.runtime.console.presets import PresetsPage
    from clank.components.runtime.console.providers import ProvidersPage

    return [ModelsPage, PresetsPage, ProvidersPage, LaunchOptionsPage, AddModelPage]


COMPONENT = Component(
    name="runtime",
    summary="The models Clank starts, watches, switches and stops: presets, serving setups, hosts and slots.",
    kinds=(Preset, Host, ModelFile, RuntimeSettings, Endpoint, SlotRecord, LaunchRecord, InstallRecord),
    event_types=(*EVENT_TYPES, *ENDPOINT_EVENT_TYPES, *CHECK_EVENT_TYPES),
    migrations="clank.components.runtime",
    adapter_kinds=(ENGINES, HOSTS, ENDPOINTS),
    build=Runtime,
    commands=commands,
    console=pages,
)
