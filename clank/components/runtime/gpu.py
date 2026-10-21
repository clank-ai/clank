"""The GPU's memory, and whether a plan fits in it (design 0001 §3.6, design 0003 §6.5).

`nvidia-smi` reports the GPU's total, used and free memory; on Windows with WSL it is Windows' own program, and the
memory in use includes the desktop's. What is neither used nor free the driver reserves (326 MiB on the owner's RTX
5080), so it is no room for a model: free is read, never computed from total and used. A machine where it does not
answer has an "unknown" fit, never an error. A plan's estimate
beside the memory free now is *fits*, *tight* (less to spare than the runtime's setting, 500 MiB unless changed) or
*does not fit*, with the breakdown the user can read. An engine that sizes its own KV cache (as vLLM and SGLang do;
NInfer did, until decision 0034) fits when everything with its smallest KV cache does, beside the headroom it keeps
free; what is left beyond that is said, and how many tokens its KV cache grows by into it when it can grow. An engine
on the CPU (design 0006) is *on the CPU*: it takes none of the GPU, whatever the GPU holds.
"""

from dataclasses import dataclass
from typing import Literal

from clank.components.runtime.adapters.engine import MemoryEstimate
from clank.kernel.processes import Run, run_command

QUERY = ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"]
MIB = 1024 * 1024
Verdict = Literal["fits", "tight", "does not fit", "unknown", "on the CPU"]


@dataclass(frozen=True)
class GpuMemory:
    """The GPU's memory now, in MiB: its total, what programs use, and what the driver reserves."""

    total_mib: int
    used_mib: int
    reserved_mib: int = 0

    @property
    def free_mib(self) -> int:
        """What is free."""
        return self.total_mib - self.used_mib - self.reserved_mib


@dataclass(frozen=True)
class Fit:
    """Whether a plan fits, by how much, and the lines that say it."""

    verdict: Verdict
    spare_mib: int | None
    lines: tuple[str, ...]


def gpu_memory(run: Run = run_command) -> GpuMemory | None:
    """The first GPU's memory, or None when `nvidia-smi` does not answer."""
    answer = run(QUERY)
    try:
        total, used, free = (int(part.strip()) for part in (answer or "").splitlines()[0].split(","))
    except (IndexError, ValueError):
        return None
    return GpuMemory(total, used, max(total - used - free, 0))


def fit(estimate: MemoryEstimate, gpu: GpuMemory | None, tight_mib: int) -> Fit:
    """Whether the estimate fits in the memory free now."""
    if not estimate.on_gpu:
        taken = (
            f"weights {estimate.weights_mib:,} + KV {estimate.kv_mib:,} + buffers {estimate.buffers_mib:,} = "
            f"{estimate.total_mib:,} MiB of system memory"
        )
        return Fit("on the CPU", None, (taken, "ON THE CPU: it takes none of the GPU's memory"))
    if gpu is None:
        return Fit("unknown", None, ("the GPU's memory could not be read: nvidia-smi did not answer",))
    learned = f" + learned {estimate.learned_mib:,}" if estimate.learned_mib else ""
    parts = (
        f"weights {estimate.weights_mib:,} + KV {estimate.kv_mib:,} + buffers {estimate.buffers_mib:,} + overhead "
        f"{estimate.overhead_mib:,}{learned} = {estimate.total_mib:,} MiB"
    )
    reserved = f"; {gpu.reserved_mib:,} reserved by the driver" if gpu.reserved_mib else ""
    free = (
        f"free now {gpu.free_mib:,} of {gpu.total_mib:,} MiB ({gpu.used_mib:,} in use: the desktop and other "
        f"programs{reserved})"
    )
    if estimate.kv_auto:
        kept = estimate.kv_headroom_mib
        left = gpu.free_mib - estimate.total_mib - kept
        if left < 0:
            return Fit(
                "does not fit",
                left,
                (parts, free, f"DOES NOT FIT: {-left:,} MiB short, with the {kept:,} MiB it keeps free"),
            )
        said = f"FITS: {left:,} MiB to spare beyond the {kept:,} MiB it keeps free"
        if estimate.kv_more_tokens and estimate.kv_bytes_per_token:
            more = min(left * MIB / estimate.kv_bytes_per_token, estimate.kv_more_tokens)
            said += f"; its KV cache grows into it by about {round(more, -3):,.0f} tokens"
        return Fit("fits", left, (parts, free, said))
    spare = gpu.free_mib - estimate.total_mib
    if spare < 0:
        return Fit("does not fit", spare, (parts, free, f"DOES NOT FIT: {-spare:,} MiB short"))
    if spare < tight_mib:
        return Fit("tight", spare, (parts, free, f"TIGHT: {spare:,} MiB to spare, less than {tight_mib:,}"))
    return Fit("fits", spare, (parts, free, f"FITS: {spare:,} MiB to spare"))
