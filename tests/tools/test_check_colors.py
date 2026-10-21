"""Design 0011 §6: the colors check refuses a color or a state's mark written in the console's code, where only the
style's elements may be named: a hex color, an `rgb()` or `hsl()` value, a color's name in a style rule (a `.tcss` file
or a widget's `DEFAULT_CSS`), a style string or markup that names a color, a `$` variable that is not the style's, and
the marks ● ○ ✓ ✗ ◆ ✎ in a string; each finding names its file and line. Prose passes: a docstring, or a sentence shown
to the owner, may name a color; ?, · and … are punctuation too. The repository itself passes
(`tests/test_repository.py`).
"""

from collections.abc import Callable
from pathlib import Path

from tools.check_colors import problems

NAMES = {"clank-good", "clank-quiet", "clank-border"}
Write = Callable[[dict[str, str]], Path]


def found(write: Write, files: dict[str, str]) -> list[str]:
    root = write(files)
    return [problem.removeprefix(root.as_posix() + "/") for problem in problems([root], NAMES)]


def test_a_hex_color_in_a_rule_or_a_style_string_is_refused(write_files: Write) -> None:
    shown = found(write_files, {
        "look.tcss": "#menu {\n    color: #ff0000;\n}\n",
        "page.py": 'STYLE = ("busy", "bold #00ff00")\n',
    })  # fmt: skip
    assert shown == [
        "look.tcss:2: the color #ff0000 is written: name the style's element for it ($clank-...)",
        "page.py:1: the color #00ff00 is written: name the style's element for it ($clank-...)",
    ]


def test_an_rgb_or_hsl_value_is_refused(write_files: Write) -> None:
    shown = found(
        write_files, {"look.tcss": "Label {\n    background: rgb(10, 20, 30);\n    color: hsl(0, 50%, 50%);\n}\n"}
    )
    assert [line.split(": ", 1)[0] for line in shown] == ["look.tcss:2", "look.tcss:3"]
    assert "rgb(" in shown[0]
    assert "hsl(" in shown[1]


def test_a_colors_name_in_a_rule_is_refused(write_files: Write) -> None:
    shown = found(write_files, {"look.tcss": "/* red in a comment passes */\n.planned {\n    border: solid red;\n}\n"})
    assert shown == ["look.tcss:3: the color red is written in a rule: name the style's element for it ($clank-...)"]


def test_a_colors_name_in_a_widgets_default_css_is_refused(write_files: Write) -> None:
    widget = 'class Rows:\n    DEFAULT_CSS = """\n    Rows .name { color: green; }\n    """\n'
    assert found(write_files, {"rows.py": widget}) == [
        "rows.py:3: the color green is written in a rule: name the style's element for it ($clank-...)"
    ]


def test_a_style_string_or_markup_that_names_a_color_is_refused(write_files: Write) -> None:
    page = 'A = ("failed", "bold red")\nB = "[green]ready[/]"\nC = ("waits", "on bright_blue")\n'
    shown = found(write_files, {"page.py": page})
    assert shown == [
        "page.py:1: the style 'bold red' names a color: name the style's element for it ($clank-...)",
        "page.py:2: the markup [green] names a color: name the style's element for it ($clank-...)",
        "page.py:3: the style 'on bright_blue' names a color: name the style's element for it ($clank-...)",
    ]


def test_a_variable_that_is_not_the_styles_is_refused(write_files: Write) -> None:
    files = {"look.tcss": "#message {\n    color: $warning;\n}\n", "page.py": 'DOT = ("●", "$success")\n'}
    shown = found(write_files, files)
    assert "look.tcss:2: the variable $warning is not one of the style's elements" in shown
    assert "page.py:1: the variable $success is not one of the style's elements" in shown


def test_a_states_mark_written_in_a_page_is_refused_naming_the_style_mark_to_draw(write_files: Write) -> None:
    shown = found(write_files, {"page.py": 'def badge():\n    return "✓ done"\n'})
    assert shown == ['page.py:2: the mark ✓ is written: draw the style\'s, mark("done")']


def test_prose_and_punctuation_and_the_styles_own_names_pass(write_files: Write) -> None:
    page = (
        '"""A page that shows the planned entries in red, and a ✓ when all is done."""\n'
        'SAID = "Pages in red come with a later milestone"\n'
        'WAITS = ("? asks you · queued …", "$clank-quiet")\n'
        'MARKUP = "[bold $clank-good]ready[/]"\n'
    )
    look = "#menu {\n    border-right: solid $clank-border;\n    color: $clank-quiet 50%;\n}\n"
    assert found(write_files, {"page.py": page, "look.tcss": look}) == []
