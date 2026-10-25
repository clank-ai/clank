"""The model's readout (design 0021 §3): what VS Code shows under OpenCode's terminal, and in its status bar, of the
model at work in a folder, composed in one answer so the extension draws it without asking five routes a second.

For the folder's workspace (none for a folder Clank has no workspace for), its session: the one named, else the newest
the service keeps the flow of (the one the window's OpenCode is working in). For that session its `now` (design 0012
§5: the phase, the speed as it writes and each step's, the prompt's reading) and its context totals (§4: used of the
window, its parts, the exact window and the compaction line, the cache's share, whose conversation the engine holds),
as their own routes give them. Then the machine, whatever the folder: the main slot (its state, its preset and title,
and the options that change its speed, `SPEED_OPTIONS`), the GPU's newest meter (its use and memory), and the tokens
the engine last said it drafted and had accepted (`Runtime.drafts`). A part that cannot be read is None.
"""

from collections.abc import Mapping
from typing import Any

SPEED_OPTIONS = ("spec.draft_tokens", "cuda_graphs")  # the preset options the readout names beside its speed
GPU_FIELDS = ("name", "use", "memory_used", "memory_total")


def slot_view(slot: Any, title: str, options: Mapping[str, Any] | None) -> dict[str, Any]:
    """The main slot as the readout shows it: its state, preset, title and the options that change its speed."""
    chosen = {key: options[key] for key in SPEED_OPTIONS if options and key in options}
    return {"status": slot.status, "preset": slot.preset, "title": title, "speed_options": chosen}


def gpu_view(readings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first GPU of the newest meter reading that has one, its use and memory; None when no reading has a GPU."""
    for reading in reversed(readings):
        gpus = reading.get("gpus") or []
        if gpus:
            return {key: gpus[0].get(key) for key in GPU_FIELDS}
    return None
