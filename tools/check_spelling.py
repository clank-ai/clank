"""Refuse British spellings anywhere in the repository: Clank is written in American English, in code, comments,
messages and documents alike (AGENTS.md).

The list holds the British forms most likely to slip in, each with the American form that the finding suggests. A
line that must keep a British form, such as a quotation or a name someone else owns, carries the marker
`spelling: keep` and says why. Code blocks in Markdown are skipped, because they copy code and screens whose own files
are checked; this file is skipped, because it holds the list; and so are the artifact libraries other authors wrote
(decision 0135).
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.files import read_text, repository_files
from tools.markdown import prose_lines

SELF = "tools/check_spelling.py"
VENDORED = "clank/components/artifacts/lib/"  # other authors' libraries, kept as they are (decision 0135)
KEEP = "spelling: keep"
AMERICAN = {
    "aeroplane": "airplane",
    "ageing": "aging",
    "amongst": "among",
    "analogue": "analog",
    "analyse": "analyze",
    "analysed": "analyzed",
    "analysing": "analyzing",
    "apologise": "apologize",
    "artefact": "artifact",
    "artefacts": "artifacts",
    "authorisation": "authorization",
    "authorise": "authorize",
    "authorised": "authorized",
    "behaviour": "behavior",
    "behavioural": "behavioral",
    "behaviours": "behaviors",
    "cancelled": "canceled",
    "cancelling": "canceling",
    "catalogue": "catalog",
    "catalogued": "cataloged",
    "catalogues": "catalogs",
    "categorise": "categorize",
    "categorised": "categorized",
    "centre": "center",
    "centred": "centered",
    "centres": "centers",
    "cheque": "check",
    "colour": "color",
    "coloured": "colored",
    "colourful": "colorful",
    "colouring": "coloring",
    "colours": "colors",
    "customise": "customize",
    "customised": "customized",
    "defence": "defense",
    "emphasise": "emphasize",
    "enrolment": "enrollment",
    "favour": "favor",
    "favoured": "favored",
    "favourite": "favorite",
    "favourites": "favorites",
    "favours": "favors",
    "fibre": "fiber",
    "finalise": "finalize",
    "finalised": "finalized",
    "fulfil": "fulfill",
    "grey": "gray",
    "honour": "honor",
    "initialise": "initialize",
    "initialised": "initialized",
    "judgement": "judgment",
    "labelled": "labeled",
    "labelling": "labeling",
    "labour": "labor",
    "learnt": "learned",
    "licence": "license",
    "licences": "licenses",
    "litre": "liter",
    "manoeuvre": "maneuver",
    "maximise": "maximize",
    "maximised": "maximized",
    "metre": "meter",
    "metres": "meters",
    "minimise": "minimize",
    "minimised": "minimized",
    "modelled": "modeled",
    "modelling": "modeling",
    "mould": "mold",
    "neighbour": "neighbor",
    "neighbouring": "neighboring",
    "neighbours": "neighbors",
    "normalise": "normalize",
    "normalised": "normalized",
    "offence": "offense",
    "optimisation": "optimization",
    "optimise": "optimize",
    "optimised": "optimized",
    "optimising": "optimizing",
    "organisation": "organization",
    "organisations": "organizations",
    "organise": "organize",
    "organised": "organized",
    "organises": "organizes",
    "organising": "organizing",
    "practise": "practice",
    "prioritise": "prioritize",
    "prioritised": "prioritized",
    "programme": "program",
    "programmes": "programs",
    "realise": "realize",
    "realised": "realized",
    "realises": "realizes",
    "recognise": "recognize",
    "recognised": "recognized",
    "recognises": "recognizes",
    "rumour": "rumor",
    "sceptical": "skeptical",
    "serialise": "serialize",
    "serialised": "serialized",
    "signalled": "signaled",
    "skilful": "skillful",
    "standardise": "standardize",
    "summarise": "summarize",
    "summarised": "summarized",
    "synchronise": "synchronize",
    "synchronised": "synchronized",
    "theatre": "theater",
    "towards": "toward",
    "travelled": "traveled",
    "travelling": "traveling",
    "tyre": "tire",
    "utilise": "utilize",
    "visualise": "visualize",
    "visualised": "visualized",
    "whilst": "while",
}
# A British form standing alone: letters on neither side, so `_`, digits and punctuation still mark its edges.
WORD = re.compile(
    r"(?<![A-Za-z])(" + "|".join(sorted(AMERICAN, key=len, reverse=True)) + r")(?![A-Za-z])", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    """A British spelling: where it is, the word as written, and its American form."""

    path: str
    line: int
    word: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.word} -> {AMERICAN[self.word.lower()]}"


def scan_text(path: str, text: str) -> list[Finding]:
    """The British spellings in one file's text; Markdown code blocks and lines marked `spelling: keep` are skipped."""
    lines = prose_lines(text) if path.endswith(".md") else list(enumerate(text.splitlines(), start=1))
    return [
        Finding(path, number, match.group(1))
        for number, line in lines
        if KEEP not in line
        for match in WORD.finditer(line)
    ]


def scan(root: Path, files: list[Path]) -> list[Finding]:
    """The British spellings in every text file of the list, except this one and the vendored libraries (decision
    0135: their words are their authors')."""
    findings: list[Finding] = []
    for file in files:
        if file.as_posix() == SELF or file.as_posix().startswith(VENDORED):
            continue
        text = read_text(root / file)
        if text is not None:
            findings.extend(scan_text(file.as_posix(), text))
    return findings


def main() -> int:
    """Print every British spelling in the repository; returns 1 when there is any."""
    root = Path(__file__).resolve().parents[1]
    findings = scan(root, repository_files(root))
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
