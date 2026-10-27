"""The checks of `clank doctor`: what Clank needs from this computer, each with what to do about it (design 0001 §4.7,
§7.3).

Each check reads facts (`Facts`: CLANK_HOME, the machine profile, a way to run commands, the platform, the API's port,
Windows' GPU scheduling setting, the free disk space) and answers passed, warning, failed or skipped, with a detail
and, when it is not passed, what to do. A warning means Clank can run but something will be missing or slow; failed
means Clank cannot work as it is. Checks never change anything (design 0001 §4.7: Clank explains and offers, the
user decides). After the machine's own, the checks other components declare run (`more`, design 0002 §2.1: the phone's
way in, design 0025 §2); one that fails to run is said as a failed check.
"""

import shutil
import socket
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Literal

from clank.components.machine.kinds import MachineProfile
from clank.kernel.home import Home
from clank.kernel.processes import Run

Status = Literal["passed", "warning", "failed", "skipped"]
MARKS: dict[str, str] = {"passed": "ok  ", "warning": "warn", "failed": "FAIL", "skipped": "skip"}
GIB = 2**30


@dataclass(frozen=True)
class CheckResult:
    """A check's answer."""

    id: str
    title: str
    status: Status
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class Facts:
    """What the checks read."""

    home: Home
    profile: MachineProfile
    run: Run
    platform: str = sys.platform
    port: int = 7720
    hags_mode: int | None = None
    free_gb: float | None = None
    more: tuple[Callable[[Home], list[dict[str, Any]]], ...] = ()  # the checks the components declare


def free_gb(home: Home) -> float | None:
    """The free space, in GB, on the disk that holds CLANK_HOME (or its parent before it exists); None when it cannot
    be measured."""
    folder = home.root if home.root.exists() else home.root.parent
    try:
        return shutil.disk_usage(folder).free / GIB
    except OSError:
        return None


def hags_mode() -> int | None:
    """Windows' hardware-accelerated GPU scheduling setting: 2 on, 1 off, None when it cannot be read."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers")
        return int(winreg.QueryValueEx(key, "HwSchMode")[0])
    except OSError:
        return None


def _python(facts: Facts) -> tuple[Status, str, str]:
    version = facts.profile.python or sys.version.split()[0]
    major, minor = (int(part) for part in version.split(".")[:2])
    if (major, minor) >= (3, 12):
        return "passed", version, ""
    return "failed", version, "install Python 3.12 or newer; `uv sync` installs it for Clank"


def _clank_home(facts: Facts) -> tuple[Status, str, str]:
    probe = facts.home.root / ".doctor-probe"
    try:
        facts.home.root.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    except (OSError, ValueError) as error:
        return "failed", f"{facts.home.root} cannot be written: {error}", "set CLANK_HOME to a folder you can write"
    return "passed", str(facts.home.root), ""


def _state_database(facts: Facts) -> tuple[Status, str, str]:
    path = facts.home.database
    if not path.exists():
        return "skipped", "not created yet: the service creates it when it first starts", ""
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as database:
            answer = database.execute("PRAGMA quick_check").fetchone()[0]
    except sqlite3.Error as error:
        return "failed", f"cannot be read: {error}", f"stop the service and move {path} aside; it is recreated"
    if answer != "ok":
        return "failed", f"damaged: {answer}", f"stop the service and move {path} aside; it is recreated"
    return "passed", "intact", ""


def _disk(facts: Facts) -> tuple[Status, str, str]:
    free = facts.free_gb
    if free is None:
        return "warning", "cannot be measured", ""
    if free >= 50:
        return "passed", f"{free:.0f} GB free", ""
    return "warning", f"{free:.0f} GB free", "a model takes 10 to 20 GB: free some room, or keep models on another disk"


def _gpu(facts: Facts) -> tuple[Status, str, str]:
    if facts.profile.gpus:
        gpu = facts.profile.gpus[0]
        return "passed", f"{gpu.name}, {gpu.memory_mib / 1024:.0f} GB, driver {gpu.driver}", ""
    return (
        "warning",
        "no NVIDIA GPU found (nvidia-smi)",
        "local models need one; a model through an API key or on another computer does not",
    )


def _wsl(facts: Facts) -> tuple[Status, str, str]:
    if facts.platform != "win32":
        return "skipped", "only on Windows", ""
    if facts.profile.wsl.startswith("WSL 2"):
        return "passed", facts.profile.wsl, ""
    return "warning", facts.profile.wsl or "not installed", "install WSL 2 (`wsl --install`): the engines run in it"


def _hags(facts: Facts) -> tuple[Status, str, str]:
    if facts.platform != "win32":
        return "skipped", "only on Windows", ""
    if facts.hags_mode == 2:
        return (
            "warning",
            "on: it froze the desktop while long prompts were read (design 0001 §4.7)",
            "turn off Hardware-accelerated GPU scheduling in Settings > System > Display > Graphics, then restart",
        )
    return "passed", "off" if facts.hags_mode == 1 else "not set (off)", ""


def _docker_installed(facts: Facts) -> tuple[Status, str, str]:
    if facts.profile.docker and facts.profile.docker != "not installed":
        return "passed", f"Docker {facts.profile.docker}", ""
    return "warning", "not installed", "install Docker Desktop: agents work in its containers (from M4)"


def _docker_running(facts: Facts) -> tuple[Status, str, str]:
    answer = facts.run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if answer and answer.strip():
        return "passed", f"its engine answers ({answer.strip()})", ""
    return "warning", "not running", "start it with `clank docker start` (or open Docker Desktop)"


def _port(facts: Facts) -> tuple[Status, str, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", facts.port))
        except OSError:
            return "passed", f"{facts.port} is taken (by the Clank service, if it runs; `clank status` says)", ""
    return "passed", f"{facts.port} is free for the service", ""


CHECKS: list[tuple[str, str, Callable[[Facts], tuple[Status, str, str]]]] = [
    ("python", "Python 3.12 or newer", _python),
    ("clank_home", "CLANK_HOME can be written", _clank_home),
    ("state_database", "The state database is intact", _state_database),
    ("disk", "Room for models", _disk),
    ("gpu", "An NVIDIA GPU", _gpu),
    ("wsl", "WSL 2", _wsl),
    ("hags", "Hardware-accelerated GPU scheduling off", _hags),
    ("docker_installed", "Docker installed", _docker_installed),
    ("docker_running", "Docker running", _docker_running),
    ("port", "The API's port", _port),
]


def run_checks(facts: Facts) -> list[CheckResult]:
    """Every check's answer, in order."""
    results = []
    for id, title, check in CHECKS:
        try:
            status, detail, fix = check(facts)
        except Exception as error:
            status, detail, fix = "failed", f"the check itself failed: {error}", ""
        results.append(CheckResult(id, title, status, detail, fix))
    for declared in facts.more:
        try:
            results += [CheckResult(**found) for found in declared(facts.home)]
        except Exception as error:
            where = getattr(declared, "__module__", "a component")
            results.append(CheckResult(where, f"The checks of {where}", "failed", f"the check itself failed: {error}"))
    return results
