"""Design 0001 §3.6 and design 0003 §6.5: the GPU's memory is read from `nvidia-smi`, and a machine where it does not
answer is "unknown", never an error; a plan's estimate beside the free memory is *fits*, *tight* (less to spare than
the setting) or *does not fit*, said with its breakdown; an engine that sizes its KV cache itself (as vLLM's does)
fits when its smallest KV cache and the rest do with the headroom it keeps free, and is told how many tokens its KV
cache grows by into what is left, when it can grow."""

from collections.abc import Sequence

from clank.components.runtime.adapters.engine import MemoryEstimate
from clank.components.runtime.gpu import GpuMemory, fit, gpu_memory

ESTIMATE = MemoryEstimate(weights_mib=11160, kv_mib=1768, buffers_mib=537, overhead_mib=632)


def answering(text: str | None) -> object:
    def run(arguments: Sequence[str]) -> str | None:
        assert list(arguments) == [
            "nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits",
        ]  # fmt: skip
        return text

    return run


def test_the_gpus_memory_is_read_from_nvidia_smi_and_unknown_without_it() -> None:
    found = gpu_memory(answering("16303, 2041, 14262\n"))  # type: ignore[arg-type]
    assert found == GpuMemory(total_mib=16303, used_mib=2041)
    assert GpuMemory(16303, 2041).free_mib == 14262
    assert gpu_memory(answering(None)) is None  # type: ignore[arg-type]
    assert gpu_memory(answering("[N/A], [N/A], [N/A]\n")) is None  # type: ignore[arg-type]


def test_what_the_driver_reserves_is_not_free() -> None:
    """The 5080's driver kept 326 MiB that nvidia-smi counts neither as used nor as free (2026-10-18)."""
    found = gpu_memory(answering("16303, 15848, 129\n"))  # type: ignore[arg-type]
    assert found == GpuMemory(total_mib=16303, used_mib=15848, reserved_mib=326)
    assert found is not None
    assert found.free_mib == 129
    assert fit(ESTIMATE, GpuMemory(16303, 1500, 326), 500).lines[1] == (
        "free now 14,477 of 16,303 MiB (1,500 in use: the desktop and other programs; 326 reserved by the driver)"
    )


def test_a_plan_fits_is_tight_or_does_not_fit_with_its_breakdown() -> None:
    assert fit(ESTIMATE, GpuMemory(16303, 1500), 500).verdict == "fits"
    tight = fit(ESTIMATE, GpuMemory(16303, 2041), 500)
    assert (tight.verdict, tight.spare_mib) == ("tight", 165)
    assert tight.lines[0] == "weights 11,160 + KV 1,768 + buffers 537 + overhead 632 = 14,097 MiB"
    assert tight.lines[1] == "free now 14,262 of 16,303 MiB (2,041 in use: the desktop and other programs)"
    assert tight.lines[-1] == "TIGHT: 165 MiB to spare, less than 500"
    short = fit(ESTIMATE, GpuMemory(16303, 3000), 500)
    assert (short.verdict, short.lines[-1]) == ("does not fit", "DOES NOT FIT: 794 MiB short")
    assert fit(ESTIMATE, None, 500).verdict == "unknown"


def test_an_engine_that_sizes_its_kv_itself_needs_its_smallest_kv_and_the_headroom_it_keeps_free() -> None:
    """Such an engine holds at least its smallest KV cache, keeps headroom free beside it, and grows into what is left
    only when it can (the numbers are NInfer v1.4's on this machine, 2026-10-13, while Clank had it: decision 0034)."""
    auto = MemoryEstimate(
        weights_mib=13040, kv_mib=795, buffers_mib=353, overhead_mib=0, kv_auto=True, kv_bytes_per_token=18496,
        kv_headroom_mib=1024,
    )  # fmt: skip
    found = fit(auto, GpuMemory(16303, 1000), 500)
    assert (found.verdict, found.spare_mib) == ("fits", 91)
    assert found.lines[-1] == "FITS: 91 MiB to spare beyond the 1,024 MiB it keeps free"
    short = fit(auto, GpuMemory(16303, 1600), 500)
    assert (short.verdict, short.lines[-1]) == (
        "does not fit", "DOES NOT FIT: 509 MiB short, with the 1,024 MiB it keeps free"
    )  # fmt: skip
    growing = MemoryEstimate(**{**vars(auto), "kv_more_tokens": 45056})
    grown = fit(growing, GpuMemory(16303, 1000), 500)
    assert grown.lines[-1] == (
        "FITS: 91 MiB to spare beyond the 1,024 MiB it keeps free; its KV cache grows into it by about 5,000 tokens"
    )
