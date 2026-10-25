"""Claims and their sources (design 0020 §7): a value the agent writes into a LaTeX document says where it comes from.

A paragraph (lines between blank lines; the preamble, before `\\begin{document}`, is none) that a change adds or alters
and that states a value carries, within it, `% source:` naming what the value comes from: a file of the folder (from
the folder, or from the document's own folder), a key of the bibliography, a DOI or an arXiv id, several separated by
commas or semicolons; or `% UNVERIFIED:` with what is not checked, so an unchecked claim is never mistaken for a
checked one (design 0018 §4).

A value (`values`) is a decimal, a percentage (`95\\%`), a number in scientific notation (`1e-3`, `3.2\\times 10^{-4}`),
or an integer of three digits or more that is not a year (1900 to 2099); small integers are not (`$N = 16$`, `$x^2$`,
"Section 2"), nor a length (`0.8\\linewidth`, `2.5em`), nor what a label, a reference, a citation, a file's name or an
optional argument holds, nor a comment.
"""

import re
from pathlib import Path, PurePosixPath

from clank.components.agents.latex.citations import uncommented

ARGUMENTS = re.compile(
    r"\\(?:label|ref|eqref|cref|Cref|autoref|pageref|nameref|includegraphics|input|include|subfile|url|href|"
    r"usepackage|documentclass|bibliography|bibliographystyle|addbibresource|begin|end|[Cc]ite[a-z]*|[Pp]arencite|"
    r"[Tt]extcite|[Aa]utocite|nocite|graphicspath)\*?\s*(?:\[[^\]]*\]\s*)*(?:\{[^}]*\})?"
)
OPTIONAL = re.compile(r"(\\[a-zA-Z]+\*?)\s*\[[^\]]*\]")
LENGTH = re.compile(
    r"-?\d*\.?\d+\s*(?:pt|em|ex|cm|mm|in|bp|pc|sp|mu|dd|cc|\\(?:line|text|column|paper)width|\\textheight|\\hsize)\b"
)
VALUE = re.compile(
    r"(?<![\w.\\])(?:"
    r"(?P<times>-?\d+(?:\.\d+)?\s*\\times\s*10\^\{?-?\d+\}?)"
    r"|(?P<sci>-?\d+(?:\.\d+)?[eE][+-]?\d+)"
    r"|(?P<percent>\d+(?:\.\d+)?\s*\\%)"
    r"|(?P<decimal>-?\d+\.\d+)"
    r"|(?P<integer>\d{3,})"
    r")(?![\w.])"
)
SOURCE = re.compile(r"%\s*source\s*:(.*)", re.I)
UNVERIFIED = re.compile(r"%\s*UNVERIFIED\s*:?(.*)")
DOI = re.compile(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+$", re.I)
ARXIV = re.compile(r"^(?:arxiv:)?(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I)
WHAT = "a file of the folder, a key of the bibliography, a DOI or an arXiv id"


def values(text: str) -> list[str]:
    """The values a piece of LaTeX states, in order."""
    plain = uncommented(text)
    plain = ARGUMENTS.sub(" ", plain)
    plain = OPTIONAL.sub(r"\1", plain)
    plain = LENGTH.sub(" ", plain)
    found = []
    for match in VALUE.finditer(plain):
        if match.group("integer") and len(match.group()) == 4 and 1900 <= int(match.group()) <= 2099:
            continue
        found.append(match.group())
    return found


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Each paragraph of the document's body with its first line: lines between blank lines, after
    `\\begin{document}` when the file has one."""
    lines = text.split("\n")
    start = next((n + 1 for n, line in enumerate(lines) if "\\begin{document}" in uncommented(line)), 0)
    found: list[tuple[int, str]] = []
    current: list[str] = []
    first = 0
    for number in range(start, len(lines)):
        if lines[number].strip():
            if not current:
                first = number + 1
            current.append(lines[number])
        elif current:
            found.append((first, "\n".join(current)))
            current = []
    if current:
        found.append((first, "\n".join(current)))
    return found


def unverified(text: str) -> list[tuple[int, str]]:
    """Each `% UNVERIFIED:` mark of the text: its line and what it says is not checked."""
    found = []
    for number, line in enumerate(text.split("\n"), start=1):
        mark = UNVERIFIED.search(line)
        if mark and not line[: mark.start()].endswith("\\"):
            found.append((number, mark.group(1).strip()))
    return found


def source_problems(before: str | None, after: str, *, folder: Path, here: str, keys: set[str]) -> list[str]:
    """A refusal for each paragraph the change adds or alters that states a value without a source, or that names as
    its source something that is none; `here` is the document's folder, from the folder."""
    had = {" ".join(text.split()) for _, text in paragraphs(before or "")}
    problems = []
    for line, text in paragraphs(after):
        if " ".join(text.split()) in had:
            continue
        stated = values(text)
        if not stated:
            continue
        named = [part.strip() for match in SOURCE.finditer(text) for part in re.split(r"[,;]", match.group(1))]
        named = [part for part in named if part]
        marks = [mark for mark in (UNVERIFIED.search(each) for each in text.split("\n")) if mark is not None]
        if marks and not all(mark.group(1).strip() for mark in marks):
            problems.append(
                f"the paragraph on line {line}: % UNVERIFIED: says what is not checked (% UNVERIFIED: <what>)"
            )
            continue
        if not named and not marks:
            problems.append(
                f"the paragraph on line {line} states {', '.join(stated)} with no source: add, within it, "
                f"% source: <{WHAT}>, or % UNVERIFIED: <what is not checked>"
            )
            continue
        wrong = [part for part in named if not _is_source(part, folder, here, keys)]
        if wrong:
            listed = ", ".join(named)
            problems.append(
                f"the paragraph on line {line} names as its source {listed}: {' and '.join(wrong)} "
                f"{'is' if len(wrong) == 1 else 'are'} not {WHAT}"
            )
    return problems


def _is_source(named: str, folder: Path, here: str, keys: set[str]) -> bool:
    if named in keys or DOI.match(named) or ARXIV.match(named):
        return True
    pure = PurePosixPath(named.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        return False
    for base in (folder, folder.joinpath(*here.split("/")) if here else folder):
        if base.joinpath(*pure.parts).is_file():
            return True
    return False
