"""Design 0022 §4: the agent places things on a board by where, never by pixels. `right_of`, `left_of`, `below` and
`above` an item put the new one beside it, aligned with it (tops for beside, left edges for under and over), two grid
steps away, snapped to the grid; one that would overlap another item moves on (down beside, right under) until it
overlaps none. A slot is taken: the new item fills it, its aspect kept, centered in it. `in` a frame is the first
free place inside it, below its name, and a frame too full for it grows downward. `{x, y}` is that place, snapped; no
`at` is a new row under everything, at the board's left edge. An item that is not on the board is refused, saying so."""

from typing import Any

import pytest

from clank.components.agents.boardplace import PlaceError, place


def box(id: str, kind: str, x: int, y: int, w: int, h: int, **more: Any) -> dict[str, Any]:
    return {"id": id, "kind": kind, "x": x, "y": y, "w": w, "h": h, **more}


FIG = box("fig-1", "figure", 80, 80, 360, 240)


def test_beside_and_under_an_item_aligned_with_it_two_grid_steps_away() -> None:
    assert place([FIG], 300, 200, {"right_of": "fig-1"}).box == (480, 80, 300, 200)
    assert place([FIG], 300, 200, {"below": "fig-1"}).box == (80, 360, 300, 200)
    assert place([FIG], 300, 200, {"above": "fig-1"}).box == (80, -160, 300, 200)
    assert place([FIG], 300, 200, {"left_of": "fig-1"}).box == (-260, 80, 300, 200)


def test_a_place_taken_moves_on_until_it_overlaps_nothing() -> None:
    taken = box("note-2", "note", 480, 80, 280, 160)
    assert place([FIG, taken], 300, 200, {"right_of": "fig-1"}).box == (480, 280, 300, 200), "down, under the note"
    under = box("latex-3", "latex", 80, 360, 400, 80)
    assert place([FIG, under], 300, 200, {"below": "fig-1"}).box == (520, 360, 300, 200), "right, beside the equation"


def test_a_slot_is_filled_with_the_aspect_kept_centered_and_taken() -> None:
    slot = box("slot-4", "slot", 480, 80, 280, 200, label="phase")
    placed = place([FIG, slot], 360, 240, {"slot": "slot-4"})
    assert placed.box == (480, 87, 280, 187)
    assert placed.taken == "slot-4"
    tall = place([FIG, slot], 200, 400, {"slot": "slot-4"})
    assert tall.box == (570, 80, 100, 200), "fitted by its height when it is the taller"


def test_inside_a_frame_the_first_free_place_below_its_name_and_the_frame_grows_when_full() -> None:
    frame = box("frame-5", "frame", 60, 60, 760, 300, name="Figure 3")
    inside = box("fig-1", "figure", 80, 100, 360, 240)
    placed = place([frame, inside], 300, 200, {"in": "frame-5"})
    assert placed.box == (480, 100, 300, 200)
    assert placed.grown is None
    full = place([frame, inside, box("fig-6", "figure", 460, 100, 340, 240)], 300, 200, {"in": "frame-5"})
    assert full.box == (80, 380, 300, 200), "a new row in the frame"
    assert full.grown == ("frame-5", 760, 540), "the frame grows to hold it"


def test_a_place_named_is_snapped_and_none_named_is_a_new_row_under_everything() -> None:
    assert place([FIG], 100, 100, {"x": 333, "y": 207}).box == (340, 200, 100, 100)
    assert place([FIG], 100, 100, None).box == (80, 360, 100, 100)
    assert place([], 100, 100, None).box == (80, 80, 100, 100), "an empty board starts near its corner"


def test_an_item_not_on_the_board_is_refused() -> None:
    with pytest.raises(PlaceError, match="no item fig-9"):
        place([FIG], 100, 100, {"below": "fig-9"})
    with pytest.raises(PlaceError, match="not a slot"):
        place([FIG], 100, 100, {"slot": "fig-1"})
    with pytest.raises(PlaceError, match="not a frame"):
        place([FIG], 100, 100, {"in": "fig-1"})


def test_beside_an_item_in_a_frame_is_in_that_frame_which_grows_to_hold_it() -> None:
    frame = box("frame-5", "frame", 60, 60, 420, 300, name="Figure 3")
    inside = box("fig-1", "figure", 80, 100, 360, 240)
    placed = place([frame, inside], 300, 200, {"right_of": "fig-1"})
    assert placed.box == (480, 100, 300, 200), "the frame is not in the way"
    assert placed.grown == ("frame-5", 740, 300)
    assert place([frame, inside], 300, 200, {"below": "frame-5"}).grown is None, "under the frame is outside it"
