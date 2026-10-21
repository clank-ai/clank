"""Detect the machine profile: the system, Python, WSL, the processor, memory, NVIDIA GPUs and Docker (design 0001 §2).

Facts come from Python itself, psutil (decision 0025) and the system's own commands (`nvidia-smi`, `wsl.exe`,
`docker`), run through the kernel's `run_command` with a time limit; a command that is missing or fails means the thing
is not there, never an error. The commands are passed in (`run`), so tests give fixed answers.
"""

import platform
import sys
from datetime import UTC, datetime

import psutil

from clank.components.machine.kinds import Gpu, MachineProfile
from clank.kernel.processes import Run, run_command


def parse_gpus(output: str) -> list[Gpu]:
    """The GPUs in `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits` output."""
    gpus = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 3 and parts[0]:
            memory = int(parts[1]) if parts[1].isdigit() else 0
            gpus.append(Gpu(name=parts[0], memory_mib=memory, driver=parts[2]))
    return gpus


def parse_wsl(output: str) -> str:
    """WSL's default distribution and its version, from `wsl.exe --list --verbose`."""
    for line in output.splitlines():
        if line.strip().startswith("*"):
            parts = line.replace("*", " ").split()
            if len(parts) >= 3:
                return f"WSL {parts[-1]}, {parts[0]}"
    return "installed, without a distribution" if output.strip() else "not installed"


def describe_system() -> str:
    """This computer's operating system, as people name it."""
    if sys.platform == "win32":
        version = platform.version()
        build = int(version.split(".")[-1]) if version.split(".")[-1].isdigit() else 0
        return f"Windows {11 if build >= 22000 else 10} ({version})"
    if sys.platform.startswith("linux"):
        try:
            return platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except OSError:
            return "Linux"
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}"
    return platform.platform()


def describe_processor() -> str:
    """This computer's processor, by its model name."""
    if sys.platform == "win32":
        import winreg

        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as info:
                for line in info:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def detect(run: Run = run_command, platform: str = sys.platform) -> MachineProfile:
    """The machine profile of this computer. `platform` says which platform's commands to ask (WSL only on Windows), so
    tests can ask as either; the system and the processor are always this computer's."""
    gpus_output = run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
    wsl = ""
    if platform == "win32":
        listed = run(["wsl.exe", "--list", "--verbose"])
        wsl = parse_wsl(listed) if listed is not None else "not installed"
    docker_output = run(["docker", "--version"])
    docker = "not installed"
    if docker_output and "version" in docker_output:
        docker = docker_output.split("version", 1)[1].split(",")[0].strip()
    return MachineProfile(
        system=describe_system(),
        python=sys.version.split()[0],
        wsl=wsl,
        processor=describe_processor(),
        cores=psutil.cpu_count(logical=False) or psutil.cpu_count() or 0,
        memory_gb=round(psutil.virtual_memory().total / 2**30, 1),
        gpus=parse_gpus(gpus_output) if gpus_output else [],
        docker=docker,
        detected=datetime.now(UTC),
    )
