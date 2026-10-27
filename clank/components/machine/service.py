"""The machine component's part in the service: the profile, the doctor as an operation (design 0002 §2.4), and the
machine's meters (`meters.py`), read every second while the service runs, the last ones kept and each new one sent to
the clients as the live event `machine.meters`.

The doctor operation has two steps, both safe to run again: detect (the machine profile, written to
`config/machine.json` through the settings files, so the change is recorded) and check (the checks of `clank doctor`).
Its result is the checks; the last one is what clients show as "doctor: 9 of 10 passed".
"""

import json
import logging
import threading
from collections import deque
from dataclasses import asdict
from typing import Any

import anyio
import anyio.to_thread

from clank.components.machine.checks import MARKS as MARKS  # the doctor's marks, which the phone's checkup shows too
from clank.components.machine.checks import Facts, free_gb, hags_mode, run_checks
from clank.components.machine.detect import detect
from clank.components.machine.kinds import MachineProfile
from clank.components.machine.meters import KEPT, SECONDS, Containers, Meters
from clank.kernel.clock import to_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor, EventType
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.processes import run_command

log = logging.getLogger(__name__)
DOCTOR = Actor(kind="clank", via="machine.doctor")
METERS = Actor(kind="clank", via="machine.meters")
EVENT_TYPES = [
    EventType(
        "machine.meters",
        "The machine's meters, read once a second: never kept (the last minutes are at GET /machine/meters).",
        {
            "cpu": "The CPU's use, percent, as a whole; cores: per logical processor.",
            "memory_used": "Memory in use, bytes (memory_total, swap_used, swap_total likewise).",
            "disk_read": "Bytes read from the disks a second (disk_write, net_down, net_up likewise).",
            "drives": "Each fixed drive: mount, used, total (bytes).",
            "gpus": "Each NVIDIA GPU: name, use, memory_used, memory_total, temperature, power, power_limit.",
        },
        live=True,
        owner="machine",
    )
]


def service_port(kernel: Kernel) -> int:
    """The port the service's settings name."""
    return int(kernel.settings.get("service", "service").record.model_dump()["port"])


class Machine:
    """The machine component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self._meters: Meters | None = None  # made when first read: loading NVIDIA's library takes a moment
        self._kept: deque[dict[str, Any]] = deque(maxlen=KEPT)
        self._lock = threading.Lock()

    def read_meters(self) -> dict[str, Any]:
        """The machine's meters now."""
        if self._meters is None:
            self._meters = Meters(containers=Containers(f"clank-{self.kernel.home.id}-"))
        return self._meters.read(to_text(self.kernel.clock.now()))

    def keep_reading(self) -> dict[str, Any]:
        """Read the meters and keep the reading with the last ones; the reading."""
        reading = self.read_meters()
        with self._lock:
            self._kept.append(reading)
        return reading

    def meters(self) -> list[dict[str, Any]]:
        """The last readings kept, oldest first."""
        with self._lock:
            return list(self._kept)

    async def run(self) -> None:
        """While the service runs: read the meters every second, keep each reading and tell the clients."""
        while True:
            try:
                reading = await anyio.to_thread.run_sync(self.keep_reading)
                self.kernel.events.publish_live(
                    "machine.meters", summary="the machine's meters", actor=METERS, data=reading
                )
            except Exception:
                log.exception("reading the machine's meters failed")
            await anyio.sleep(SECONDS)

    def profile(self) -> MachineProfile:
        """The machine profile as last detected (or corrected by the user)."""
        return MachineProfile.model_validate(self.kernel.settings.get("machine", "machine").record.model_dump())

    def last_doctor(self) -> dict[str, Any] | None:
        """The checks of the last doctor run that finished, if any."""
        for operation in self.kernel.operations.find("done", limit=20):
            if operation.type == "machine.doctor" and operation.result:
                return operation.result
        return None

    def operation_types(self) -> list[OperationType]:
        """The doctor."""
        return [
            OperationType(
                "machine.doctor",
                "Check this machine",
                (StepSpec("detect"), StepSpec("check")),
                self._doctor,
                owner="machine",
            )
        ]

    def router(self) -> Any:
        """The machine's routes."""
        from clank.components.machine.api import router

        return router(self)

    async def _doctor(self, context: OperationContext) -> dict[str, Any]:
        async with context.step("detect"):
            profile = await context.run_blocking(detect, run_command)
            current = self.kernel.settings.get("machine", "machine")
            values = json.loads(profile.model_dump_json())
            self.kernel.settings.write("machine", "machine", values, base=current.revision, actor=DOCTOR)
        async with context.step("check"):
            facts = Facts(
                home=self.kernel.home,
                profile=profile,
                run=run_command,
                port=service_port(self.kernel),
                hags_mode=hags_mode(),
                free_gb=free_gb(self.kernel.home),
                more=tuple(each.checks for each in self.kernel.components if each.checks is not None),
            )
            results = await context.run_blocking(run_checks, facts)
        passed = sum(1 for result in results if result.status == "passed")
        return {"checks": [asdict(result) for result in results], "passed": passed, "of": len(results)}
