"""Design 0002 §3.2: the console shows a state in color: green when it is as wanted, yellow while it changes, red when
it is not; text is shown as it is, never read as markup; a state that appears more than once is colored each time, in
order. Design 0016 §11: a cost is shown in US dollars, cents from a dollar up, two significant digits below, an
estimate marked ≈; a model's window in thousands of tokens."""

from textual.content import Content

from clank.console.text import painted, tone
from clank.money import money, tokens


def colored(content: Content) -> list[tuple[str, str]]:
    """Each colored part of a line: its text and its color."""
    return [(content.plain[span.start : span.end], str(span.style)) for span in content.spans]


def test_a_state_is_green_when_as_wanted_yellow_while_it_changes_and_red_when_not() -> None:
    assert [tone(state) for state in ("running", "starting", "stopped", "exited", "answering")] == [
        "$clank-good", "$clank-attention", "$clank-failed", "$clank-failed", ""
    ]  # fmt: skip


def test_each_mark_is_colored_where_it_next_appears_and_the_text_is_never_read_as_markup() -> None:
    line = painted("paper: running · notes: exited · the edge: running [b]x[/b]", "running", "exited", "running")
    assert colored(line) == [("running", "$clank-good"), ("exited", "$clank-failed"), ("running", "$clank-good")]
    assert [span.start for span in line.spans] == [7, 24, 43]
    assert line.plain.endswith("[b]x[/b]")


def test_money_is_cents_from_a_dollar_up_and_two_significant_digits_below_an_estimate_marked() -> None:
    assert [money(usd) for usd in (3.1, 5.02, 0.84, 0.42, 0.0123, 0.03, 0.1, 0.00002, 0.000021, 0.0, 1234.5)] == [
        "$3.10", "$5.02", "$0.84", "$0.42", "$0.012", "$0.03", "$0.10", "$0.00002", "$0.000021", "$0.00", "$1,234.50"
    ]  # fmt: skip
    assert money(0.03, estimated=True) == "≈ $0.03"
    assert money(None) == "—"


def test_a_window_of_tokens_is_said_in_thousands() -> None:
    assert [tokens(count) for count in (262144, 131072, 32768, 900)] == ["262K", "131K", "33K", "900"]
