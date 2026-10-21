"""Design 0011 §12.2 and §12.8 (one group, one cursor; the look): a button is its key and its words with a blank cell at
each side, drawn in its state's elements of the style (normal, under the mouse, focused, pressed, cannot act now, and
cannot act now while focused), the state's fill covering the blank cells, so that no state changes its width; its words
are `quiet` on the keys bar and `text` in a panel. A group's lines for a width: a row goes on to its next line between
two buttons, never inside one, a column's button wraps its words under themselves, a lead's words come first and are
no button, and each button's cells are where its text is drawn, for a click."""

import pytest
from textual.content import Content

from clank.console.buttons import STATES, Button, button, lay_out
from clank.console.keys import PageKey

GET_READY = PageKey("g", "get_ready", "get everything ready")
OPENCODE = PageKey("a", "opencode", "OpenCode here")
PLAN = PageKey("p", "plan", "plan")


def cells(content: Content) -> list[str]:
    """The style of each cell of a one-line content, as written ("" where none)."""
    found = [""] * content.cell_length
    for span in content.spans:
        for index in range(span.start, span.end):
            found[index] = str(span.style)
    return found


def test_a_button_is_its_key_and_its_words_with_a_blank_cell_at_each_side() -> None:
    assert button("g", "get everything ready").plain == " g get everything ready "
    assert button("enter", "do it").plain == " enter do it "


@pytest.mark.parametrize("place", ["bar", "panel"])
def test_no_state_changes_a_buttons_width_or_its_text(place: str) -> None:
    drawn = [button("a", "OpenCode here", state, place) for state in STATES]  # type: ignore[arg-type]
    assert {content.plain for content in drawn} == {" a OpenCode here "}
    assert {content.cell_length for content in drawn} == {len(" a OpenCode here ")}


def test_a_normal_buttons_key_is_in_key_and_its_words_quiet_on_the_bar_and_text_in_a_panel() -> None:
    bar = cells(button("a", "OpenCode here", "normal", "bar"))
    assert bar[0] == bar[-1] == "", "no fill"
    assert bar[1] == "$clank-key"
    assert set(bar[3:-1]) == {"$clank-quiet"}
    panel = cells(button("a", "OpenCode here", "normal", "panel"))
    assert set(panel[3:-1]) == {"$clank-text"}


@pytest.mark.parametrize(
    ("state", "fill", "key", "words"),
    [
        ("hover", "$clank-button-hover", "$clank-key", "$clank-text"),
        ("focused", "$clank-button-focused", "$clank-button-focused-text", "$clank-button-focused-text"),
        ("pressed", "$clank-button-pressed", "$clank-button-focused-text", "$clank-button-focused-text"),
        ("unable_focused", "$clank-button-unable-focused", "$clank-quiet", "$clank-quiet"),
    ],
)
def test_a_states_fill_covers_the_whole_button_its_blank_cells_too(state: str, fill: str, key: str, words: str) -> None:
    drawn = cells(button("a", "OpenCode here", state, "bar"))  # type: ignore[arg-type]
    assert all(style.endswith(f"on {fill}") for style in drawn), drawn
    assert drawn[1] == f"{key} on {fill}"
    assert set(drawn[3:-1]) == {f"{words} on {fill}"}


def test_a_button_that_cannot_act_now_is_dimmed_without_a_fill() -> None:
    drawn = cells(button("i", "implement a plan", "unable", "panel"))
    assert drawn[0] == drawn[-1] == ""
    assert set(drawn[1:-1]) - {""} == {"$clank-dim"}


def test_a_row_goes_on_to_its_next_line_between_two_buttons_never_inside_one() -> None:
    row = [Button(GET_READY), Button(OPENCODE), Button(PLAN)]
    lines, places = lay_out(row, ["normal"] * 3, 30)
    assert [line.plain for line in lines] == [" g get everything ready ", " a OpenCode here  p plan "]
    assert places == [(0, 0, 0, 24), (1, 1, 0, 17), (2, 1, 17, 25)]
    wide, _ = lay_out(row, ["normal"] * 3, 80)
    assert [line.plain for line in wide] == [" g get everything ready  a OpenCode here  p plan "]


def test_a_rows_lead_comes_first_and_is_no_button() -> None:
    lines, places = lay_out([Button(OPENCODE), Button(PLAN)], ["normal"] * 2, 80, lead="Next:")
    assert lines[0].plain == "Next:  a OpenCode here  p plan "
    assert places[0] == (0, 0, 6, 23)


def test_a_columns_button_wraps_its_words_under_themselves() -> None:
    long = Button(OPENCODE, "OpenCode in this terminal; the menu comes back when you leave it")
    lines, places = lay_out([long, Button(PLAN)], ["normal"] * 2, 30, column=True)
    assert [line.plain for line in lines] == [
        " a OpenCode in this terminal; ",
        "   the menu comes back when   ",
        "   you leave it               ",
        " p plan ",
    ]
    assert places[:3] == [(0, 0, 0, 30), (0, 1, 0, 30), (0, 2, 0, 30)]
    assert places[3] == (1, 3, 0, 8)


def test_a_button_wider_than_its_row_is_cut_with_the_styles_mark() -> None:
    lines, places = lay_out([Button(GET_READY)], ["normal"], 12)
    assert lines[0].plain == " g get eve… "
    assert places == [(0, 0, 0, 12)]
