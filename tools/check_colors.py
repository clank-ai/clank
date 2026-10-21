"""Refuse a color or a state's mark written in the console's code, where only the style's elements may be named
(design 0011 §6): every color the console draws is an element of its style (`$clank-good`), every mark that says a
state is drawn through the style (`mark("done")`), so a style file changes them all and nothing is left behind.

It reads `clank/console/` and each component's `console/` folder: the style sheets (`.tcss`) and the Python files, a
widget's `DEFAULT_CSS` read as a style sheet. It refuses a hex color; an `rgb()` or `hsl()` value; a color's name in a
style rule; a style string (`"bold red"`) or markup (`[green]`) that names a color; a `$` variable that is not one of
the style's elements (Textual's own, `$success`, among them); and the marks ● ○ ✓ ✗ ◆ ✎ written in a string. A color's
name is a word Textual or Rich reads as a color (`red`, `tan`, `bright_blue`); `transparent` is the absence of one.
Prose passes: a docstring, a comment, or a sentence shown to the owner may name a color ("Pages in red come with a
later milestone"), since a style string holds nothing but words of style; ?, · and …, which are punctuation too,
pass. Colors and marks are written only in style files, and in the style kind's defaults outside these folders.
"""

import ast
import io
import re
import sys
from collections.abc import Iterator
from pathlib import Path

from rich.color import ANSI_COLOR_NAMES
from textual.color import Color, ColorParseError

from clank.console.style import CLANK, LoadedStyle, theme_of
from clank.kernel.console_kinds import StyleMarks, StyleSettings

REPOSITORY = Path(__file__).resolve().parents[1]
ADVICE = "name the style's element for it ($clank-...)"
HEX = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b")
SHORT_HEX = re.compile(r"#[0-9a-fA-F]{3}\b")  # a color only in a rule's value: elsewhere `#add` may be a widget's id
FUNCTION = re.compile(r"\b(?:rgba?|hsla?)\(")
VARIABLE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_-]*)")
MARKUP = re.compile(r"\[([^\[\]/][^\[\]]*)\]")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# The words of a style that are not colors (Rich's and Textual's text styles, and their short forms).
STYLE_WORDS = {
    "b", "bold", "d", "dim", "i", "italic", "u", "underline", "uu", "underline2", "s", "strike", "r", "reverse",
    "blink", "blink2", "conceal", "o", "overline", "frame", "encircle", "not", "on",
}  # fmt: skip
MARK_NAMES = {str(glyph): name for name, glyph in StyleMarks().model_dump().items()}
MARKS = {glyph: name for glyph, name in MARK_NAMES.items() if glyph in "●○✓✗◆✎"}


def console_roots(repository: Path) -> list[Path]:
    """The folders of the console's code: Clank's console and each component's."""
    return [repository / "clank" / "console", *sorted((repository / "clank" / "components").glob("*/console"))]


def style_names() -> set[str]:
    """The names of the style's elements, as the console's theme carries them (`clank-good`, `clank-data-1`)."""
    variables = theme_of(LoadedStyle(CLANK, StyleSettings())).variables
    return {name for name in variables if name.startswith("clank-")}


def is_color_name(word: str) -> bool:
    """Whether a word is a color's name that Textual or Rich reads (`red`, `tan`, `bright_blue`)."""
    if word == "transparent" or not re.fullmatch(r"[a-z][a-z0-9_]*", word):
        return False
    if word in ANSI_COLOR_NAMES:
        return True
    try:
        Color.parse(word)
    except ColorParseError:
        return False
    return True


def names_a_color(style: str) -> bool:
    """Whether a string is a style (nothing but words of style) that names a color."""
    words = style.split()
    in_style = all(
        word in STYLE_WORDS or word.startswith("$") or HEX.fullmatch(word) or is_color_name(word) for word in words
    )
    return bool(words) and in_style and any(is_color_name(word) for word in words)


def variables(text: str, names: set[str]) -> Iterator[str]:
    """What is wrong with each `$` variable in a text that is not one of the style's elements."""
    for name in VARIABLE.findall(text):
        if name not in names:
            yield f"the variable ${name} is not one of the style's elements"


def declarations(sheet: str) -> Iterator[tuple[int, str]]:
    """Each declaration's value in a style sheet, with its line (from 1); selectors and comments left out."""
    sheet = COMMENT.sub(lambda comment: re.sub(r"[^\n]", " ", comment.group()), sheet)
    depth, line, start, segment = 0, 1, 1, ""
    for character in sheet:
        if character in "{};":
            if depth and character != "{":
                name, colon, value = segment.partition(":")
                if colon and re.fullmatch(r"\s*[a-z-]+\s*", name):
                    yield start, value
            depth += {"{": 1, "}": -1}.get(character, 0)
            segment = ""
        else:
            if not segment.strip() and not character.isspace():
                start = line
            segment += character
        line += character == "\n"


def sheet_problems(sheet: str, names: set[str]) -> Iterator[tuple[int, str]]:
    """What is wrong in a style sheet's declarations, each with its line."""
    for line, value in declarations(sheet):
        for color in [*HEX.findall(value), *SHORT_HEX.findall(value)]:
            yield line, f"the color {color} is written: {ADVICE}"
        for function in FUNCTION.findall(value):
            yield line, f"the color {function}...) is written: {ADVICE}"
        for word in re.split(r"[\s,()]+", value):
            if is_color_name(word):
                yield line, f"the color {word} is written in a rule: {ADVICE}"
        for problem in variables(value, names):
            yield line, problem


def string_problems(text: str, names: set[str]) -> Iterator[str]:
    """What is wrong in a string of the code that is neither a docstring nor a style sheet."""
    for color in HEX.findall(text):
        yield f"the color {color} is written: {ADVICE}"
    for function in FUNCTION.findall(text):
        yield f"the color {function}...) is written: {ADVICE}"
    if names_a_color(text):
        yield f"the style {text!r} names a color: {ADVICE}"
    for inside in MARKUP.findall(text):
        if names_a_color(inside):
            yield f"the markup [{inside}] names a color: {ADVICE}"
    yield from variables(text, names)
    for glyph, name in MARKS.items():
        if glyph in text:
            yield f'the mark {glyph} is written: draw the style\'s, mark("{name}")'


def docstrings(tree: ast.Module) -> set[int]:
    """The nodes of a module's docstrings: its own, its classes' and its functions'."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def style_sheets(tree: ast.Module) -> set[int]:
    """The nodes of the style sheets written in a module: a widget's `DEFAULT_CSS`, an app's `CSS`."""
    found = set()
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        value = getattr(node, "value", None)
        named = any(isinstance(target, ast.Name) and target.id in ("DEFAULT_CSS", "CSS") for target in targets)
        if named and isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.add(id(value))
    return found


def python_problems(source: str, names: set[str]) -> Iterator[tuple[int, str]]:
    """What is wrong in a Python file's strings, each with its line."""
    tree = ast.parse(source)
    skipped, sheets = docstrings(tree), style_sheets(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in skipped:
            continue
        if id(node) in sheets:
            for line, problem in sheet_problems(node.value, names):
                yield node.lineno + line - 1, problem
        else:
            for problem in string_problems(node.value, names):
                yield node.lineno, problem


def problems(roots: list[Path], names: set[str]) -> list[str]:
    """Every color or mark written in the console's code under these folders, as `path:line: what`."""
    found: list[tuple[str, int, str]] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".py", ".tcss") or "__pycache__" in path.parts:
                continue
            text = path.read_bytes().decode("utf-8")
            checked = sheet_problems(text, names) if path.suffix == ".tcss" else python_problems(text, names)
            found += [(path.as_posix(), line, problem) for line, problem in checked]
    return [f"{path}:{line}: {problem}" for path, line, problem in sorted(found)]


def main() -> int:
    """Print every color or mark written in the console's code; returns 1 when there is any."""
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(errors="backslashreplace")  # a mark (✓) in a console that cannot show it: ✓
    found = problems(console_roots(REPOSITORY), style_names())
    for problem in found:
        print(problem, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
