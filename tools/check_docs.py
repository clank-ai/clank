"""Check the documents: every link resolves, every decision, design and plan is in its index, and every design
section has a status (design 0001 §8.4).

Links are checked the way GitHub shows them: a link to a heading uses GitHub's anchor for it (lowercase, punctuation
removed, spaces made hyphens, a number added to a repeated heading), a heading may be underlined (`===` or `---`), a
link starting with `/` starts at the repository's root, and text inside code is not a link. Only links within the
repository are checked; outside links would need the network, which checks never use.
"""

import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

from tools.files import repository_files
from tools.markdown import prose_lines

HEADING = re.compile(r"^ {0,3}#{1,6} +(.+?)(?: +#+)? *$")
UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+) *$")
NOT_A_PARAGRAPH = re.compile(r"^ {0,3}(?:#|[-*+] |\d+[.)] |>|\|)")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"!?\[(?:[^\]\\]|\\.)*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
OUTSIDE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
NUMBERED = re.compile(r"^(\d{4})-.+\.md$")
SECTION = re.compile(r"^## (\d+)\. ")
# Each indexed folder, and whether its documents are numbered.
INDEXES = {
    "docs/decisions": True,
    "docs/design": True,
    "docs/plans": False,
    "docs/measurements": False,
    "docs/models": False,
}


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, only letters, digits, hyphens and underscores kept, spaces made
    hyphens."""
    text = LINK_TEXT.sub(r"\1", CODE_SPAN.sub(r"\2", heading))
    kept = "".join(char for char in text.lower() if char in "-_ " or unicodedata.category(char)[0] in "LNM")
    return kept.replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Every anchor GitHub gives the headings of a Markdown text, a repeated heading numbered as GitHub numbers it."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    previous = ""
    for _, line in prose_lines(text):
        heading = None
        if match := HEADING.match(line):
            heading = match.group(1)
        elif UNDERLINE.match(line) and previous.strip() and not NOT_A_PARAGRAPH.match(previous):
            heading = previous.strip()
        previous = line
        if heading is None:
            continue
        base = slug(heading)
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.add(base if count == 0 else f"{base}-{count}")
    return found


def links(text: str) -> list[str]:
    """Every link target in a Markdown text, outside code."""
    prose = CODE_SPAN.sub("", "\n".join(line for _, line in prose_lines(text)))
    found = [match.group(1) for match in LINK.finditer(prose)]
    found += [match.group(1) for line in prose.splitlines() if (match := DEFINITION.match(line))]
    return found


def broken_links(root: Path, files: list[Path]) -> list[str]:
    """Each link within the repository to a file or a heading that does not exist."""
    problems: list[str] = []
    headings: dict[Path, set[str]] = {}
    top = root.resolve()
    for doc in (file for file in files if file.suffix == ".md"):
        for target in links((root / doc).read_text(encoding="utf-8")):
            if OUTSIDE.match(target):
                continue
            path, _, anchor = target.partition("#")
            dest = _resolve(root, doc, unquote(path)) if path else (root / doc).resolve()
            where = f"{doc.as_posix()}: links to {target}"
            if not dest.is_relative_to(top):
                problems.append(f"{where}, which is outside the repository")
            elif not dest.exists():
                problems.append(f"{where}, which does not exist")
            elif anchor and dest.suffix == ".md":
                if dest not in headings:
                    headings[dest] = anchors(dest.read_text(encoding="utf-8"))
                if unquote(anchor) not in headings[dest]:
                    problems.append(f"{where}, but that heading does not exist")
    return problems


def unindexed(root: Path, files: list[Path]) -> list[str]:
    """Each decision, design or plan missing from its folder's index, and each gap or repeat in the numbers."""
    problems: list[str] = []
    for folder, numbered in INDEXES.items():
        members = [f for f in files if f.parent.as_posix() == folder and f.suffix == ".md" and f.name != "README.md"]
        if not members:
            continue
        index = root / folder / "README.md"
        targets = links(index.read_text(encoding="utf-8")) if index.exists() else []
        index_doc = Path(folder) / "README.md"
        listed = {_resolve(root, index_doc, unquote(path)) for target in targets if (path := target.partition("#")[0])}
        problems += [
            f"{folder}/README.md: does not list {member.name}"
            for member in members
            if (root / member).resolve() not in listed
        ]
        if not numbered:
            continue
        problems += [f"{folder}/{m.name}: is not named NNNN-title.md" for m in members if not NUMBERED.match(m.name)]
        numbers = sorted(int(match.group(1)) for m in members if (match := NUMBERED.match(m.name)))
        missing = sorted(set(range(1, max(numbers, default=0) + 1)) - set(numbers))
        repeated = sorted({n for n in numbers if numbers.count(n) > 1})
        if missing or repeated:
            parts = [f"missing {', '.join(f'{n:04d}' for n in missing)}"] if missing else []
            parts += [f"repeated {', '.join(f'{n:04d}' for n in repeated)}"] if repeated else []
            problems.append(f"{folder}: numbers must run from 0001 without gaps or repeats; {'; '.join(parts)}")
    return problems


def _resolve(root: Path, doc: Path, path: str) -> Path:
    """Where a link in `doc` leads: from the repository's root when it starts with `/`, else from `doc`'s folder."""
    base = root if path.startswith("/") else (root / doc).parent
    return (base / path.lstrip("/")).resolve()


def _sections_table(lines: list[str]) -> dict[str, str]:
    """The rows of the table under the "## Sections" heading: each section's number, and its status."""
    rows: dict[str, str] = {}
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line.strip() == "## Sections"
        elif inside and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].isdigit():
                rows[cells[0]] = cells[-1]
    return rows


def sections_without_status(root: Path, files: list[Path]) -> list[str]:
    """Each design section missing from its document's Sections table, or listed there without a status."""
    problems: list[str] = []
    for doc in files:
        if doc.parent.as_posix() != "docs/design" or not NUMBERED.match(doc.name):
            continue
        lines = [line for _, line in prose_lines((root / doc).read_text(encoding="utf-8"))]
        headings = [match.group(1) for line in lines if (match := SECTION.match(line))]
        table = _sections_table(lines)
        name = doc.as_posix()
        for number in headings:
            if number not in table:
                problems.append(f"{name}: section {number} is missing from its Sections table")
            elif not table[number]:
                problems.append(f"{name}: section {number} has no status in its Sections table")
        problems += [
            f"{name}: its Sections table lists section {n}, which has no heading" for n in table if n not in headings
        ]
    return problems


def problems(root: Path, files: list[Path]) -> list[str]:
    """Every problem in the documents among `files` (paths relative to `root`)."""
    return broken_links(root, files) + unindexed(root, files) + sections_without_status(root, files)


def main() -> int:
    """Print every problem in the repository's documents; returns 1 when there is any."""
    root = Path(__file__).resolve().parents[1]
    found = problems(root, repository_files(root))
    for problem in found:
        print(problem, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
