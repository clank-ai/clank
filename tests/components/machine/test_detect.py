"""Design 0001 §2 and §7.3: Clank detects the machine it runs on (system, Python, WSL, processor, memory, GPUs, Docker)
from the system's own commands, and says plainly when there is no GPU, no WSL or no Docker."""

from collections.abc import Sequence

from clank.components.machine.detect import detect, parse_gpus, parse_wsl

NVIDIA = "NVIDIA GeForce RTX 5080, 16303, 615.71\n"
WSL = (
    "  NAME            STATE           VERSION\n"
    "* Ubuntu-22.04    Running         2\n"
    "  docker-desktop  Stopped         2\n"
)


def answers(table: dict[str, str]) -> "object":
    def run(arguments: Sequence[str]) -> str | None:
        return table.get(arguments[0])

    return run


def test_gpus_are_read_from_nvidia_smi() -> None:
    [gpu] = parse_gpus(NVIDIA)
    assert (gpu.name, gpu.memory_mib, gpu.driver) == ("NVIDIA GeForce RTX 5080", 16303, "615.71")


def test_the_default_wsl_distribution_and_its_version_are_read() -> None:
    assert parse_wsl(WSL) == "WSL 2, Ubuntu-22.04"


def test_detection_gathers_every_fact_from_the_commands() -> None:
    run = answers({"nvidia-smi": NVIDIA, "wsl.exe": WSL, "docker": "Docker version 28.4.0, build abc1234\n"})
    profile = detect(run, platform="win32")  # type: ignore[arg-type]
    assert profile.python
    assert profile.cores > 0
    assert profile.memory_gb > 0
    assert [gpu.name for gpu in profile.gpus] == ["NVIDIA GeForce RTX 5080"]
    assert profile.wsl == "WSL 2, Ubuntu-22.04"
    assert profile.docker == "28.4.0"
    assert profile.detected is not None


def test_without_a_gpu_wsl_or_docker_detection_says_so() -> None:
    profile = detect(answers({}), platform="win32")  # type: ignore[arg-type]
    assert profile.gpus == []
    assert profile.wsl == "not installed"
    assert profile.docker == "not installed"


def test_wsl_is_not_asked_about_outside_windows() -> None:
    profile = detect(answers({"wsl.exe": WSL}), platform="linux")  # type: ignore[arg-type]
    assert profile.wsl == ""
