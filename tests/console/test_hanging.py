"""Design 0011 §5: a name and its value, written as one line of text, wraps under its value, never back under its name;
a line with no name wraps under its own start; a heading wraps at the panel's edge, as prose does."""

from textual.content import Content
from textual.css.styles import RulesMap
from textual.style import Style
from textual.visual import RenderOptions

from clank.console.hanging import Hanging, hanging

ACCOUNT = (
    '  account   key "made-up key label" (ends …-key): its own limit $20.00, $18.71 left; OpenRouter counts $0.12 today'
)


def lines_of(text: str | Content, width: int) -> list[str]:
    """What a panel this wide shows of the text, line by line."""
    return hanging(Content(text) if isinstance(text, str) else text, width).plain.split("\n")


def test_a_value_that_wraps_goes_on_under_its_value_never_under_its_name() -> None:
    lines = lines_of(ACCOUNT, 48)
    assert lines[0].startswith("  account   key ")
    assert len(lines) > 2
    for line in lines[1:]:
        assert line.startswith(" " * 12), line
        assert line[12] != " ", line
    assert all(len(line) <= 48 for line in lines)
    assert " ".join(" ".join(lines).split()) == " ".join(ACCOUNT.split())


def test_a_name_of_two_words_keeps_its_value_column() -> None:
    line = "  gguf weights     qwen2.5-coder-0.5b-q8_0.gguf, 531 MB, from ggml-org, at its pinned revision, checked"
    lines = lines_of(line, 60)
    assert lines[1].startswith(" " * 19)
    assert lines[1][19] != " "


def test_a_line_with_no_name_wraps_under_its_own_start() -> None:
    line = "  2 containers that Clank did not start are running: another-model-relay, toolbox-sandbox-017."
    lines = lines_of(line, 50)
    assert lines[1].startswith("  ")
    assert lines[1][2] != " "


def test_a_heading_wraps_at_the_panel_edge_as_prose_does() -> None:
    line = "OpenRouter (openrouter) · agreed 2026-10-11 11:40 · its key set the same day"
    lines = lines_of(line, 50)
    assert len(lines) == 2
    assert lines[1][0] != " "


def test_a_line_that_fits_is_left_as_it_is() -> None:
    text = "Cloud\n  key       set, ends …-key\n\n  policy    data_collection deny"
    assert hanging(Content(text), 80).plain == text


def test_in_a_narrow_panel_a_value_wraps_under_the_line_start_rather_than_in_a_sliver() -> None:
    lines = lines_of(ACCOUNT, 20)
    assert all(len(line) <= 20 for line in lines)
    assert all(line.startswith("  ") and line[2] != " " for line in lines[1:])


def test_a_word_longer_than_the_line_is_cut_and_goes_on_under_its_value() -> None:
    line = "  presets   " + "x" * 50
    lines = lines_of(line, 30)
    assert lines[0] == "  presets   " + "x" * 18
    assert lines[1] == " " * 12 + "x" * 18
    assert lines[2] == " " * 12 + "x" * 14


def test_each_word_keeps_its_color_when_its_line_wraps() -> None:
    text = Content.assemble(
        "  state     ", ("stopped", "$clank-failed"), " and then a long explanation of why it stopped"
    )
    shown = hanging(text, 30)
    painted = [shown.plain[span.start : span.end] for span in shown.spans]
    assert painted == ["stopped"]


def test_the_panel_is_as_tall_as_the_lines_it_shows() -> None:
    visual = Hanging(ACCOUNT)
    rules: RulesMap = {}
    height = visual.get_height(rules, 48)
    assert height == len(lines_of(ACCOUNT, 48))
    strips = visual.render_strips(48, None, Style(), RenderOptions(lambda _: Style(), rules))
    assert len(strips) == height


def test_a_label_showing_it_reads_as_its_words() -> None:
    assert str(Hanging(ACCOUNT)) == ACCOUNT


def test_a_word_too_long_for_the_value_column_but_not_the_panel_goes_on_whole_under_the_line_start() -> None:
    line = (
        "  gguf weights     qwen2.5-coder-0.5b-q8_0.gguf, 531 MB, "
        + "from ggml-org/Qwen2.5-Coder-0.5B-Q8_0-GGUF@5788aee90e72"
    )
    lines = lines_of(line, 60)
    assert lines[1] == "  from ggml-org/Qwen2.5-Coder-0.5B-Q8_0-GGUF@5788aee90e72"
