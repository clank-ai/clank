"""The machine component's kind of record: the machine profile (design 0001 §2).

One record, `config/machine.json`, written by the doctor operation in the service and readable like any settings file;
the user can correct a value Clank detected wrongly. It stays in CLANK_HOME: the repository never holds one machine's
specifics (design 0001 §7.7).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from clank.kernel.records import Settings


class Gpu(BaseModel):
    """One NVIDIA GPU, as `nvidia-smi` reports it."""

    name: str = Field(title="Name", description="The GPU's model, such as NVIDIA GeForce RTX 5080.")
    memory_mib: int = Field(0, title="Memory (MiB)", description="Its memory, in mebibytes.")
    driver: str = Field("", title="Driver", description="The version of the NVIDIA driver.")


class MachineProfile(Settings):
    """What Clank detected about this computer."""

    KIND = "machine"
    LABEL = "Machine"
    HELP = "What Clank detected about this computer: its system, Python, WSL, processor, memory, GPUs and Docker."
    SINGLE = True

    system: str = Field("", title="System", description="The operating system and its version.")
    python: str = Field("", title="Python", description="The version of Python that runs Clank.")
    wsl: str = Field(
        "", title="WSL", description="On Windows, WSL's version and default distribution, or not installed."
    )
    processor: str = Field("", title="Processor", description="The processor's model.")
    cores: int = Field(0, title="Cores", description="The processor's physical cores.")
    memory_gb: float = Field(0.0, title="Memory (GB)", description="The computer's memory, in gibibytes.")
    gpus: list[Gpu] = Field(default_factory=list, title="GPUs", description="The NVIDIA GPUs found.")
    docker: str = Field("", title="Docker", description="The version of the Docker command, or not installed.")
    detected: datetime | None = Field(None, title="Detected", description="When Clank last detected all this.")
