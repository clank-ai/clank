"""A model per box (design 0013 §7; decisions 0062 and 0063): the preset each box runs on, and a run's switches.

`named` says which preset a box runs on, and `switches` the switches of the main slot a run of a flow makes.

A box's model is a preset: its own, else the flow's `defaults.model`. A VERIFY that names none runs on the preset of the
box it checks (that box's own, else the flow's): no switch, its independence coming from what its first message hands
it (decision 0063). A box that names none, the flow naming none either, runs on what the main slot runs when it starts:
nothing is loaded for it. YOU boxes and gates are the owner's, with no model.

`switches` walks the boxes in the order they run (`runs.order`) from what the slot runs at the start: each box whose
preset is not the one loaded by then switches the slot to it. A preset is named by its id or its title, as everywhere,
so the function is given the runtime's way to tell them apart (`resolve`: a name to its preset's id).
"""

from collections.abc import Callable

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.runs import order

OWNERS = ("you", "gate")  # the boxes the owner does: no model


def named(flow: Flow, box: Box) -> str:
    """The preset `box` runs on, as the flow names it (an id or a title); "" when it names none, or is the owner's."""
    if box.type in OWNERS:
        return ""
    if box.model:
        return box.model
    if box.type == "verify":
        checked = next((each for each in flow.boxes if each.id == box.checks), None)
        if checked is not None and checked.model:
            return checked.model
    return flow.defaults.model


def switches(flow: Flow, running: str, resolve: Callable[[str], str]) -> list[tuple[str, str]]:
    """The switches of the main slot a run of the flow makes, from `running` (the preset the slot runs, by its id; ""
    for none), in the order its boxes run: each box that needs another preset than the one loaded by then, with that
    preset's id."""
    by_id = {box.id: box for box in flow.boxes}
    found: list[tuple[str, str]] = []
    loaded = running
    for name in order(flow):
        wanted = named(flow, by_id[name])
        if not wanted:
            continue
        preset = resolve(wanted)
        if preset != loaded:
            found.append((name, preset))
            loaded = preset
    return found
