"""Design 0020 §6: the citations of a LaTeX file are read in every form natbib and biblatex give them (`\\cite`,
`\\citep`, `\\citet`, `\\parencite`, `\\textcite`, `\\autocite`, `\\citeauthor`, `\\citeyear`, `\\nocite`, starred, with
optional arguments, several keys), comments left out, each with its line; the bibliographies a document loads
(`\\bibliography`, `\\addbibresource`) and the entries of a `.bib` file are read. A change is refused for each citation
it adds whose key is no entry, or when it cites with no bibliography loaded; a key the file cited before is not its.
A new or changed `.bib` entry must have a DOI or an arXiv id that resolves and matches its title, first author and year
(Crossref and arXiv, from recorded answers); an entry with neither, one whose identifier does not resolve, or one that
does not match is refused, saying what the record says; a lookup that cannot be made leaves the entry for the owner."""

import json
from typing import Any

import pytest

from clank.components.agents.latex.citations import (
    Lookup,
    bib_entries,
    bibliographies,
    cite_keys,
    entry_problems,
    missing_citations,
)

PAPER = r"""\documentclass{article}
\usepackage{natbib}
\begin{document}
Known results \citep[see][ch.~2]{gottesman1998, aaronson2004}. As \citet*{bravyi2016} show,
% \cite{commented2020} is not a citation
the rank grows \parencite{qassim2021}\textcite{kocia2017}\autocite[p. 3]{bravyi2019}.
\citeauthor{gottesman1998} and \citeyear{aaronson2004}; \nocite{*}
\bibliographystyle{plainnat}
\bibliography{refs,extra/more}
\end{document}
"""
BIB = r"""@article{gottesman1998,
  title = {The {Heisenberg} Representation of Quantum Computers},
  author = {Gottesman, Daniel},
  year = {1998},
  eprint = {quant-ph/9807006},
  archivePrefix = {arXiv},
}
@comment{ignored}
@article{aaronson2004, title="Improved simulation of stabilizer circuits",
  author="Aaronson, Scott and Gottesman, Daniel",
  year=2004, doi={10.1103/PhysRevA.70.052328}}
@string{prl = "Physical Review Letters"}
"""
CROSSREF = {
    "message": {
        "title": ["Improved simulation of stabilizer circuits"],
        "author": [{"family": "Aaronson", "given": "Scott"}, {"family": "Gottesman", "given": "Daniel"}],
        "issued": {"date-parts": [[2004, 11, 30]]},
    }
}
ARXIV = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/quant-ph/9807006v1</id>
<published>1998-07-01T19:15:54Z</published><title>The Heisenberg Representation of
  Quantum Computers</title><author><name>Daniel Gottesman</name></author></entry></feed>"""
EMPTY_ARXIV = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def test_every_citation_form_is_read_with_its_line_and_comments_are_left_out() -> None:
    found = [(each.key, each.line) for each in cite_keys(PAPER)]
    assert found == [
        ("gottesman1998", 4), ("aaronson2004", 4), ("bravyi2016", 4), ("qassim2021", 6), ("kocia2017", 6),
        ("bravyi2019", 6), ("gottesman1998", 7), ("aaronson2004", 7),
    ]  # fmt: skip
    assert "commented2020" not in {each.key for each in cite_keys(PAPER)}
    assert bibliographies(PAPER) == ["refs.bib", "extra/more.bib"]
    assert bibliographies(r"\addbibresource[location=local]{lit/refs.bib}") == ["lit/refs.bib"]


def test_a_bib_files_entries_are_read_with_their_fields() -> None:
    entries = bib_entries(BIB)
    assert set(entries) == {"gottesman1998", "aaronson2004"}
    assert entries["gottesman1998"].fields["title"] == "The {Heisenberg} Representation of Quantum Computers"
    assert entries["gottesman1998"].fields["archiveprefix"] == "arXiv"
    assert entries["aaronson2004"].fields["year"] == "2004"
    assert entries["aaronson2004"].fields["doi"] == "10.1103/PhysRevA.70.052328"
    assert entries["aaronson2004"].line == 9
    assert entries["aaronson2004"].fields["author"] == "Aaronson, Scott and Gottesman, Daniel"


def test_a_change_is_refused_for_each_key_it_adds_that_is_no_entry() -> None:
    known = set(bib_entries(BIB))
    before = "As shown \\cite{missing1999}.\n"
    after = before + "And \\citep{gottesman1998, invented2025}.\n\\cite{missing1999}\n"
    [problem] = missing_citations(before, after, known, loaded=True)
    assert problem.startswith(
        "\\cite{invented2025} on line 2: no bibliography of the document has an entry invented2025"
    )
    assert "propose the entry with its DOI or arXiv id" in problem
    assert missing_citations(None, "\\cite{gottesman1998}\n", known, loaded=True) == []
    [none] = missing_citations(None, "\\cite{gottesman1998}\n", set(), loaded=False)
    assert "the document loads no bibliography" in none


class Recorded:
    """Crossref's and arXiv's answers as they were recorded; what was asked."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        for part, answer in self.answers.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer.encode() if isinstance(answer, str) else json.dumps(answer).encode()
        raise LookupError(f"404 for {url}")


@pytest.fixture
def lookup() -> Lookup:
    return Lookup(Recorded({"api.crossref.org/works/10.1103": CROSSREF, "id_list=quant-ph/9807006": ARXIV,
                            "id_list=2501.99999": EMPTY_ARXIV}))  # fmt: skip


def test_new_entries_that_match_their_records_pass_and_are_looked_up_once(lookup: Lookup) -> None:
    assert entry_problems(None, BIB, lookup) == ([], [])
    entry_problems(None, BIB, lookup)
    assert len(lookup.fetch.asked) == 2, "each record once"  # type: ignore[attr-defined]
    assert entry_problems(BIB, BIB, lookup) == ([], []), "entries the file had are not looked up again"


def test_an_entry_without_an_identifier_or_that_does_not_match_or_resolve_is_refused(lookup: Lookup) -> None:
    bare = "@book{knuth1984, title={The TeXbook}, author={Knuth, Donald}, year={1984}}\n"
    [refused], [] = entry_problems(None, bare, lookup)
    assert refused.startswith("@book{knuth1984} on line 1: it has no DOI and no arXiv id")
    assert "ask the user to add it" in refused
    wrong = BIB.replace("year = {1998}", "year = {2003}").replace(
        "Gottesman, Daniel},\n  year", "Preskill, John},\n  year"
    )
    problems, _ = entry_problems(None, wrong, lookup)
    assert len(problems) == 1
    assert (
        "arXiv quant-ph/9807006 says: 'The Heisenberg Representation of Quantum Computers', Gottesman, 1998"
        in problems[0]
    )
    assert "first author Preskill" in problems[0]
    assert "year 2003" in problems[0]
    ghost = (
        "@article{ghost2025, title={A result}, author={Doe, Jane}, year={2025}, eprint={2501.99999}, "
        "archiveprefix={arXiv}}\n"
    )
    [unresolved], [] = entry_problems(None, ghost, lookup)
    assert "arXiv 2501.99999 has no such paper" in unresolved


def test_a_lookup_that_cannot_be_made_leaves_the_entry_for_the_owner() -> None:
    offline = Lookup(Recorded({"api.crossref.org": OSError("no network")}))
    entry = "@article{a2004, title={T}, author={A, B}, year={2004}, doi={10.1/x}}\n"
    problems, unchecked = entry_problems(None, entry, offline)
    assert problems == []
    assert unchecked == ["@article{a2004}: DOI 10.1/x could not be looked up (no network): the user checks it"]
