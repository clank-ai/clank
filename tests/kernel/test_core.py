"""Design 0002 §2.1 and decision 0013: the kernel is assembled from its own parts and every component's declarations;
each component's part is built with the kernel, and its operation types join the kernel's."""

from typing import Any

import pytest
from pydantic import Field

from clank.kernel.clock import FakeClock
from clank.kernel.components import Component
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK, Actor, EventType
from clank.kernel.home import Home
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.records import Settings

YOU = Actor(kind="user", via="console")


class Gadget(Settings):
    KIND = "gadget"
    LABEL = "Gadget"
    HELP = "A kind a test component declares."
    SINGLE = True

    size: int = Field(1, title="Size", description="How big.")


async def poke(context: OperationContext) -> dict[str, Any]:
    async with context.step("poke"):
        pass
    return {"poked": True}


class Gadgets:
    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def operation_types(self) -> list[OperationType]:
        return [OperationType("gadget.poke", "Poke the gadget", (StepSpec("poke"),), poke, owner="gadgets")]


GADGETS = Component(
    name="gadgets",
    summary="A component for these tests.",
    kinds=(Gadget,),
    event_types=(EventType("gadget.poked", "The gadget was poked.", owner="gadgets"),),
    build=Gadgets,
)


def test_opening_a_kernel_creates_the_database_loads_the_settings_and_builds_every_part(
    home: Home, clock: FakeClock
) -> None:
    kernel = open_kernel(home, clock, [GADGETS])
    try:
        assert home.database.exists()
        assert kernel.settings.get("service", "service").source == "built-in"
        assert kernel.settings.get("gadget", "gadget").record.model_dump()["size"] == 1
        assert isinstance(kernel.parts["gadgets"], Gadgets)
        assert kernel.kinds.get("gadget") is Gadget
        kernel.events.record("gadget.poked", summary="poked", actor=CLANK)
    finally:
        kernel.close()


@pytest.mark.anyio
async def test_a_components_operation_types_join_the_kernels(home: Home, clock: FakeClock) -> None:
    kernel = open_kernel(home, clock, [GADGETS])
    try:
        async with kernel.operations.running():
            started = await kernel.operations.start("gadget.poke", actor=YOU)
            done = await kernel.operations.wait(started.id)
        assert (done.status, done.result) == ("done", {"poked": True})
    finally:
        kernel.close()
