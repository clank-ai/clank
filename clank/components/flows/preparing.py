"""Each box prepared (design 0013 §5, decisions 0085-0087): its first message built in one place, and previewed.

`message` reads what the boxes before a box handed on (`handoff.notes_before`) and builds its first message
(`first.py`) from the files as they are now and the run it is sent in, so the message the runner sends and the one a
preview shows are the same text. `preview` builds every box a model runs that way (`clank flow prepare`): as its next
try would be sent now, in the flow's active run when it has one (else as a new run would start), each with its size
counted by the runtime (by the engine when it can, else an estimate said so, decision 0087) against the window of the
preset it runs on, and its share of it. The preset is the box's own, a VERIFY's the box it checks' unless it names one,
else the flow's (`models.named`, as the runner's model step reads it, design 0013 §7); a box naming none runs on what
the main slot runs when it starts: the preset of the last box before it that names one (its switch leaves the slot
there, as `models.switches` walks them), else the preset the main slot runs now, else its window is not known.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.flows import handoff
from clank.components.flows.first import came_from, first_message
from clank.components.flows.kinds import Box, Flow
from clank.components.flows.models import OWNERS, named
from clank.components.flows.runs import BoxRun, Run, Runs, order

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

QUARTER = 0.25  # a first message past this share of its window is warned of (decision 0087)
SAID = (
    "Each count is of the first message alone: OpenCode adds its own instructions and tool definitions to it (their "
    "size is to measure, design 0013 §7).",
    "Files and notes not written yet are not counted: the boxes before a box write them as the flow runs.",
)


class PrepareError(ValueError):
    """A box that has no first message to show, and why; `missing` when the flow has no such box."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


def message(
    runs: Runs, run: Run | None, flow: str, made: Flow, box: Box, folder: Path, *, number: int, told: str = ""
) -> str:
    """A box's first message for its try `number`: `run` the run it is sent in (none: a preview with no run), `flow`
    the flow's id, `made` the flow, `folder` the workspace's folder, `told` what its last try is told."""
    notes = handoff.notes_before(runs, run, flow, made, box)
    name = flow.split("/", 1)[-1]
    return first_message(made, box, folder, number=number, last=told, name=name, run=run, notes=notes)


def preview(
    runs: Runs, run: Run | None, flow: str, made: Flow, folder: Path, runtime: "Runtime", *, only: str = ""
) -> dict[str, Any]:
    """Every box a model runs (or `only` that one), its first message as it would be sent now and its size: `run` the
    flow's active run, if any. `PrepareError` for a box with no first message."""
    from clank.components.flows.runner import _told  # here: the runner builds on this module

    by_id = {box.id: box for box in made.boxes}
    if only and only not in by_id:
        raise PrepareError(f"{flow} has no box {only}", missing=True)
    if only and by_id[only].type in OWNERS:
        raise PrepareError(f"{only} is a {by_id[only].type.upper()}, done by you: it has no first message")
    shown = []
    loaded = ""  # the preset the boxes before this one leave in the main slot, as named; "" for what it runs now
    for name in order(made):
        box = by_id[name]
        if box.type not in OWNERS and (not only or name == only):
            state: BoxRun | None = run.boxes.get(name) if run is not None else None
            number = len(state.tries) + 1 if state is not None else 1
            told = _told(state) if state is not None else ""
            text = message(runs, run, flow, made, box, folder, number=number, told=told)
            shown.append(sized(runtime, made, box, number, text, loaded=loaded))
        loaded = named(made, box) or loaded
    return {"flow": flow, "title": made.title, "run": run.number if run is not None else None, "boxes": shown,
            "said": list(SAID)}  # fmt: skip


def sized(runtime: "Runtime", made: Flow, box: Box, number: int, text: str, *, loaded: str = "") -> dict[str, Any]:
    """A box's first message with its size, counted for the preset it runs on, against that preset's window: for a box
    naming none, `loaded`, the preset the boxes before it leave in the main slot, else the one the slot runs now."""
    wanted = named(made, box)
    preset, why = wanted or loaded, ""
    if not preset:
        slot = runtime.route("main")
        preset = str(slot["preset"] or "") if slot["status"] == "ready" else ""
        why = "" if preset else "its window is not known: it names no preset, and the main slot runs none now"
    facts = runtime.facts(preset) if preset else None
    if preset and facts is None:
        why = f"its window is not known: Clank cannot read the preset {preset}"
    window = int(facts["engine"]["window"]) if facts is not None else None
    counted = runtime.count_tokens(preset, text)
    share = counted["tokens"] / window if window else None
    price, price_said = _priced(runtime, preset, int(counted["tokens"]))
    return {
        "box": box.id, "type": box.type, "title": box.title, "try": number, "text": text,
        "characters": len(text), "bytes": len(text.encode("utf-8")), **counted,
        "named": wanted, "preset": str(facts["preset"]) if facts is not None else "",
        "preset_title": str(facts["title"]) if facts is not None else "", "window": window, "window_said": why,
        "share": share, "over": share is not None and share > QUARTER, "price_usd": price, "price_said": price_said,
    }  # fmt: skip


def _priced(runtime: "Runtime", preset: str, tokens: int) -> tuple[float | None, str]:
    """A cloud preset's first message priced at its model's input price (design 0016 §7): what it costs to send, and
    in words; None and "" for a preset whose model runs here, or whose price is not known."""
    try:
        price = (runtime.preset(preset).get("price") or {}).get("in") if preset else None
    except Exception:  # noqa: BLE001: a preset gone since has no price
        return None, ""
    if price is None:
        return None, ""
    usd = tokens * float(price) / 1_000_000
    shown = f"${usd:.2f}" if usd >= 0.01 else "$" + f"{usd:.6f}".rstrip("0").rstrip(".")
    return usd, f"≈ {shown} to send, at ${float(price):.2f} per million tokens in"


def warnings(shown: dict[str, Any], made: Flow, folder: Path) -> list[tuple[tuple[str | int, ...], str]]:
    """What `clank flow check` warns of, never refuses (decision 0087), each with its place in the flow's file: a box
    whose first message (as `preview` showed it) is over a quarter of its window; a file a box sees or shows that is
    not in the folder and that neither it nor a box before it writes."""
    place = {box.id: index for index, box in enumerate(made.boxes)}
    found: list[tuple[tuple[str | int, ...], str]] = []
    for each in shown["boxes"]:
        if each["over"]:
            how = "counted" if each["exact"] else "an estimate"
            found.append((
                ("boxes", place[each["box"]]),
                f"{each['box']}'s first message is {each['tokens']:,} tokens ({how}), {each['share']:.0%} of the "
                f"{each['window']:,} of {each['preset_title']}: over a quarter of its window; hand it less whole (its "
                "sees, the flow's whole_up_to) or split its work",
            ))  # fmt: skip
    for box in made.boxes:
        for field in ("sees", "shows"):
            for index, path in enumerate(getattr(box, field)):
                if path in box.writes or came_from(made, box, path) or folder.joinpath(*path.split("/")).is_file():
                    continue
                found.append((
                    ("boxes", place[box.id], field, index),
                    f"{box.id} {field} {path}, which is not in the folder, and neither {box.id} nor a box before it "
                    "writes it",
                ))  # fmt: skip
    return sorted(found, key=lambda each: tuple(str(part).zfill(6) for part in each[0]))
