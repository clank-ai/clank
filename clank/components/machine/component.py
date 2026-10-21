"""The machine component's declaration (design 0002 §1, §2.1).

It owns the machine profile (`config/machine.json`), the checks of `clank doctor` and the machine's meters (the CPU,
the GPU, the memory, the disks and the network, read every second); it uses no other component.
"""

from typing import Any

from clank.components.machine.kinds import MachineProfile
from clank.components.machine.service import EVENT_TYPES, Machine
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank doctor`."""
    from clank.components.machine.cli import doctor

    return [doctor]


def pages() -> list[Any]:
    """The machine's page in the console."""
    from clank.components.machine.console.machine import MachinePage

    return [MachinePage]


COMPONENT = Component(
    name="machine",
    summary="What Clank detected about this computer, and the checks of clank doctor.",
    kinds=(MachineProfile,),
    event_types=tuple(EVENT_TYPES),
    build=Machine,
    commands=commands,
    console=pages,
)
