"""The machine's meters (the owner's request, 2026-10-14: the console shows the CPU, the GPU, the memory, the disks and
the network all the time): read once a second by the service while it runs, the last `KEPT` readings kept in memory
(so a console that opens shows the last minutes at once), each new one sent to the clients as the live event
`machine.meters`, and the kept ones at `GET /machine/meters`.

A reading: the CPU's use, as a whole and per logical processor (since the last reading); the memory and the page file
in use; the disks' reads and writes and the network's traffic, in bytes a second since the last reading; each fixed
drive's space (read again every `DRIVES_SECONDS`, which is slower); and each NVIDIA GPU's use, memory, temperature,
power, clocks and fan, from NVIDIA's management library (NVML, which comes with the driver: `nvml.dll`,
`libnvidia-ml.so.1`), read through ctypes, so no program is started each second and nothing is added to Clank's
dependencies. Without an NVIDIA driver there are no GPUs; a GPU value its driver does not give is None. A reading costs
about a millisecond. From 2026-10-15 (the owner: the panel did not say enough) a reading also has the busiest and the
largest processes (`Processes`, read every few seconds) and the CPU and memory of Clank's containers (`Containers`,
`docker stats` on a thread of its own every ten seconds, so a reading never waits for Docker).
"""

import contextlib
import ctypes
import json
import re
import shutil
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

import psutil

from clank.kernel.processes import run_answer

SECONDS = 1.0
KEPT = 300  # five minutes of readings
DRIVES_SECONDS = 60.0
PROCESS_SECONDS = 3.0  # the processes are read every few seconds: going through them all costs some tens of ms
TOP = 6  # the busiest and the largest processes, each
CONTAINER_SECONDS = 10.0
CONTAINER_TIMEOUT = 20.0
NVML_NAMES = ("nvml.dll",) if sys.platform == "win32" else ("libnvidia-ml.so.1", "libnvidia-ml.so")


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class Nvml:
    """NVIDIA's management library: each GPU's use, memory, temperature and power; no GPUs when it cannot be loaded."""

    def __init__(self, load: Callable[[str], Any] = ctypes.CDLL) -> None:
        self._library: Any = None
        self._handles: list[ctypes.c_void_p] = []
        self._names: list[str] = []
        for name in NVML_NAMES:
            with contextlib.suppress(OSError, AttributeError):
                library = load(name)
                if library.nvmlInit_v2() == 0:
                    self._library = library
                    break
        if self._library is None:
            return
        count = ctypes.c_uint()
        if self._library.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0:
            return
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if self._library.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(handle)) != 0:
                continue
            buffer = ctypes.create_string_buffer(96)
            self._library.nvmlDeviceGetName(handle, buffer, 96)
            self._handles.append(handle)
            self._names.append(buffer.value.decode("utf-8", errors="replace"))

    def gpus(self) -> list[dict[str, Any]]:
        """Each GPU now: its name, its use (percent), its memory (bytes), its temperature (°C) and its power (W)."""
        return [self._gpu(handle, name) for handle, name in zip(self._handles, self._names, strict=True)]

    def _gpu(self, handle: ctypes.c_void_p, name: str) -> dict[str, Any]:
        library = self._library
        use, memory = _Utilization(), _Memory()
        temperature, power, limit = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        clock, memory_clock, fan = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        used = library.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(use)) == 0
        known = library.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) == 0
        hot = library.nvmlDeviceGetTemperature(handle, 0, ctypes.byref(temperature)) == 0  # 0: the GPU's own sensor
        drawn = library.nvmlDeviceGetPowerUsage(handle, ctypes.byref(power)) == 0
        capped = library.nvmlDeviceGetEnforcedPowerLimit(handle, ctypes.byref(limit)) == 0
        clocked = library.nvmlDeviceGetClockInfo(handle, 0, ctypes.byref(clock)) == 0  # 0: graphics
        memory_clocked = library.nvmlDeviceGetClockInfo(handle, 2, ctypes.byref(memory_clock)) == 0  # 2: memory
        fanned = library.nvmlDeviceGetFanSpeed(handle, ctypes.byref(fan)) == 0
        return {
            "name": name,
            "use": float(use.gpu) if used else None,
            "memory_used": int(memory.used) if known else None,
            "memory_total": int(memory.total) if known else None,
            "temperature": int(temperature.value) if hot else None,
            "power": round(power.value / 1000, 1) if drawn else None,
            "power_limit": round(limit.value / 1000, 1) if capped else None,
            "clock": int(clock.value) if clocked else None,
            "memory_clock": int(memory_clock.value) if memory_clocked else None,
            "fan": int(fan.value) if fanned else None,
        }


def _drives() -> list[dict[str, Any]]:
    """Each fixed drive: where it is mounted, its space used and its size, in bytes."""
    found = []
    for partition in psutil.disk_partitions(all=False):
        if not partition.fstype or "cdrom" in partition.opts or "removable" in partition.opts:
            continue
        with contextlib.suppress(OSError):
            usage = psutil.disk_usage(partition.mountpoint)
            found.append({"mount": partition.mountpoint, "used": usage.used, "total": usage.total})
    return found


class Processes:
    """The busiest processes (CPU) and the largest (memory), read every `PROCESS_SECONDS`: a process's CPU is its share
    of the whole machine since the last read; the idle process and those Windows does not let a user read are left
    out."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._known: dict[int, psutil.Process] = {}
        self._rows: list[dict[str, Any]] = []
        self._at: float | None = None
        self._cpus = psutil.cpu_count() or 1

    def read(self) -> list[dict[str, Any]]:
        """The top `TOP` by CPU, then the top `TOP` by memory not among them: pid, name, cpu (%) and memory (bytes)."""
        moment = self._clock()
        if self._at is not None and moment - self._at < PROCESS_SECONDS:
            return self._rows
        self._at = moment
        rows: list[dict[str, Any]] = []
        alive: dict[int, psutil.Process] = {}
        for process in psutil.process_iter():
            if process.pid == 0:
                continue
            known = self._known.get(process.pid, process)
            try:
                with known.oneshot():
                    share = known.cpu_percent(None) / self._cpus
                    rows.append({"pid": known.pid, "name": known.name(), "cpu": round(min(share, 100.0), 1),
                                 "memory": known.memory_info().rss})  # fmt: skip
            except (psutil.Error, OSError):
                continue
            alive[process.pid] = known
        self._known = alive
        busiest = sorted(rows, key=lambda row: -row["cpu"])[:TOP]
        taken = {row["pid"] for row in busiest}
        largest = [row for row in sorted(rows, key=lambda row: -row["memory"]) if row["pid"] not in taken][:TOP]
        self._rows = busiest + largest
        return self._rows


class Containers:
    """The CPU and memory of Clank's containers (`docker stats`, which takes a second or two), read on a thread of its
    own every `CONTAINER_SECONDS`, so a reading never waits for Docker; none while Docker does not answer. A container's
    CPU is its share of the machine; the edge, which only forwards, is left out."""

    def __init__(
        self,
        prefix: str,
        run: Callable[[list[str]], str | None] | None = None,
        cpus: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._prefix = prefix
        self._run = run or _docker
        self._cpus = cpus or psutil.cpu_count() or 1
        self._clock = clock
        self._rows: list[dict[str, Any]] = []
        self._at: float | None = None
        self._busy = threading.Lock()

    def latest(self) -> list[dict[str, Any]]:
        """The last rows read; a new read starts on its own thread when one is due and none runs."""
        moment = self._clock()
        if (self._at is None or moment - self._at >= CONTAINER_SECONDS) and self._busy.acquire(blocking=False):
            self._at = moment

            def refresh() -> None:
                try:
                    self._rows = self.read_now()
                finally:
                    self._busy.release()

            threading.Thread(target=refresh, name="clank-container-stats", daemon=True).start()
        return self._rows

    def read_now(self) -> list[dict[str, Any]]:
        """`docker stats` now: each of Clank's containers but the edge, by its workspace's name."""
        answer = self._run(["docker", "stats", "--no-stream", "--format", "{{json .}}"])
        rows = []
        for line in (answer or "").splitlines():
            try:
                found = json.loads(line)
            except ValueError:
                continue
            name = str(found.get("Name", ""))
            if not name.startswith(self._prefix) or name.endswith("-edge"):
                continue
            used, _, total = str(found.get("MemUsage", "")).partition("/")
            cpu = _number(str(found.get("CPUPerc", "0")).rstrip("%")) / self._cpus
            rows.append({"name": name.removeprefix(self._prefix), "cpu": round(cpu, 1),
                         "memory_used": _bytes(used), "memory_total": _bytes(total)})  # fmt: skip
        return rows


def _docker(argv: list[str]) -> str | None:
    """A docker command's output; None when Docker is not there or does not answer (no window opens)."""
    program = shutil.which(argv[0])
    if program is None:
        return None
    answer = run_answer([program, *argv[1:]], timeout=CONTAINER_TIMEOUT)
    return answer.output if answer.ok else None


def _number(text: str) -> float:
    try:
        return float(text.strip())
    except ValueError:
        return 0.0


UNITS = {"b": 1, "kib": 1 << 10, "mib": 1 << 20, "gib": 1 << 30, "tib": 1 << 40, "kb": 1000, "mb": 1000**2,
         "gb": 1000**3, "tb": 1000**4}  # fmt: skip


def _bytes(text: str) -> int:
    """`3.5GiB` as bytes (0 when it is not a size)."""
    match = re.fullmatch(r"\s*([\d.]+)\s*([A-Za-z]+)\s*", text)
    if match is None:
        return 0
    return int(_number(match.group(1)) * UNITS.get(match.group(2).lower(), 0))


class Meters:
    """The machine's meters, read: each reading's rates are since the one before."""

    def __init__(
        self,
        gpus: Callable[[], list[dict[str, Any]]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        processes: Processes | None = None,
        containers: Containers | None = None,
    ) -> None:
        self._gpus = gpus if gpus is not None else Nvml().gpus
        self._clock = clock
        self._processes = processes or Processes()
        self._containers = containers
        self._last: tuple[float, Any, Any] | None = None
        self._drives: list[dict[str, Any]] = []
        self._drives_at: float | None = None
        psutil.cpu_percent(percpu=True)  # the first reading of the CPU starts its count

    def read(self, now: str) -> dict[str, Any]:
        """A reading now (`now` is its time, as the API writes times)."""
        moment = self._clock()
        cores = psutil.cpu_percent(percpu=True)
        memory, swap = psutil.virtual_memory(), psutil.swap_memory()
        disks, network = psutil.disk_io_counters(), psutil.net_io_counters()
        rates = {"read": 0.0, "write": 0.0, "down": 0.0, "up": 0.0}
        if self._last is not None and moment > self._last[0]:
            seconds, before_disks, before_network = moment - self._last[0], self._last[1], self._last[2]
            if disks is not None and before_disks is not None:
                rates["read"] = max(0.0, (disks.read_bytes - before_disks.read_bytes) / seconds)
                rates["write"] = max(0.0, (disks.write_bytes - before_disks.write_bytes) / seconds)
            if network is not None and before_network is not None:
                rates["down"] = max(0.0, (network.bytes_recv - before_network.bytes_recv) / seconds)
                rates["up"] = max(0.0, (network.bytes_sent - before_network.bytes_sent) / seconds)
        self._last = (moment, disks, network)
        if self._drives_at is None or moment - self._drives_at >= DRIVES_SECONDS:
            self._drives, self._drives_at = _drives(), moment
        reading = {
            "time": now,
            "cpu": round(sum(cores) / len(cores), 1) if cores else 0.0,
            "cores": [round(core, 1) for core in cores],
            "memory_used": memory.total - memory.available,
            "memory_total": memory.total,
            "swap_used": swap.used,
            "swap_total": swap.total,
            "disk_read": round(rates["read"]),
            "disk_write": round(rates["write"]),
            "net_down": round(rates["down"]),
            "net_up": round(rates["up"]),
            "drives": self._drives,
            "gpus": self._gpus(),
            "processes": self._processes.read(),
            "containers": self._containers.latest() if self._containers is not None else [],
        }
        return reading
