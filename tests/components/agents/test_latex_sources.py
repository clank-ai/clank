"""Design 0020 §7: a paragraph a change adds or alters that states a value carries `% source:` within it, naming a file
of the folder, a key of the bibliography, a DOI or an arXiv id, or `% UNVERIFIED:` with what is not checked. A value is
a decimal, a percentage, a number in scientific notation, or an integer of three digits or more that is not a year;
small integers, lengths (`0.8\\linewidth`, `2em`), labels, references, citation keys, optional arguments, the preamble
and comments are not. Paragraphs the file had before are not the change's. Each refusal names the paragraph's line and
the values found, or the source that is not one."""

from pathlib import Path

from clank.components.agents.latex.sources import source_problems, unverified, values

BODY = r"""\documentclass{article}
\setlength{\parskip}{0.5em}
\begin{document}
\section{Results}
The figure \ref{fig:2025} shows it; see \cite{a2004} and Sec.~2.

The ground state energy is $E_0 = -1.2732(4)$.
% source: runs/vmc-l16/summary.json

\end{document}
"""


def test_values_are_decimals_percentages_scientific_notation_and_large_integers_not_years() -> None:
    assert values(r"The energy is $E_0 = -1.2732(4)$ and 95\% of runs end.") == ["-1.2732", "95\\%"]
    assert values(r"A rate of $3.2\times 10^{-4}$, or 1e-3 per step, over 1000 seeds.") == [
        "3.2\\times 10^{-4}", "1e-3", "1000",
    ]  # fmt: skip
    assert values(r"In 2024 we used $N = 16$, $x^2$, Section 2 and \cite{smith2019} with \ref{eq:12}.") == []
    assert values(r"\includegraphics[width=0.8\linewidth]{fig} \vspace{2.5em} \hspace{1.5cm}") == []


def test_a_new_paragraph_with_a_value_and_no_source_is_refused_naming_its_line_and_values(tmp_path: Path) -> None:
    after = BODY.replace("% source: runs/vmc-l16/summary.json\n", "")
    [problem] = source_problems(None, after, folder=tmp_path, here="", keys=set())
    assert problem.startswith("the paragraph on line 7 states -1.2732 with no source")
    assert "% source: <a file of the folder, a key of the bibliography, a DOI or an arXiv id>" in problem
    assert "% UNVERIFIED: <what is not checked>" in problem


def test_a_source_must_be_a_file_a_key_a_doi_or_an_arxiv_id(tmp_path: Path) -> None:
    (tmp_path / "runs" / "vmc-l16").mkdir(parents=True)
    (tmp_path / "runs" / "vmc-l16" / "summary.json").write_text("{}", encoding="utf-8")
    assert source_problems(None, BODY, folder=tmp_path, here="", keys=set()) == []
    for named in ("a2004", "10.1103/PhysRevA.70.052328", "arXiv:quant-ph/9807006", "2501.01234v2"):
        after = BODY.replace("runs/vmc-l16/summary.json", named)
        assert source_problems(None, after, folder=tmp_path, here="", keys={"a2004"}) == [], named
    wrong = BODY.replace("runs/vmc-l16/summary.json", "runs/vmc-l32/summary.json, my notes")
    [problem] = source_problems(None, wrong, folder=tmp_path, here="", keys=set())
    assert problem.startswith("the paragraph on line 7 names as its source runs/vmc-l32/summary.json, my notes")
    assert "not a file of the folder, a key of the bibliography, a DOI or an arXiv id" in problem


def test_a_file_named_from_the_documents_own_folder_counts(tmp_path: Path) -> None:
    (tmp_path / "paper" / "data").mkdir(parents=True)
    (tmp_path / "paper" / "data" / "fit.csv").write_text("x\n", encoding="utf-8")
    after = BODY.replace("runs/vmc-l16/summary.json", "data/fit.csv")
    assert source_problems(None, after, folder=tmp_path, here="paper", keys=set()) == []


def test_unverified_needs_its_words_and_is_counted(tmp_path: Path) -> None:
    marked = BODY.replace("% source: runs/vmc-l16/summary.json", "% UNVERIFIED: from a run not kept")
    assert source_problems(None, marked, folder=tmp_path, here="", keys=set()) == []
    assert unverified(marked) == [(8, "from a run not kept")]
    bare = BODY.replace("% source: runs/vmc-l16/summary.json", "% UNVERIFIED:")
    [problem] = source_problems(None, bare, folder=tmp_path, here="", keys=set())
    assert "% UNVERIFIED: says what is not checked" in problem


def test_paragraphs_the_file_had_before_are_not_the_changes(tmp_path: Path) -> None:
    before = BODY.replace("% source: runs/vmc-l16/summary.json\n", "")
    after = before.replace("\\section{Results}", "\\section{Main results}")
    assert source_problems(before, after, folder=tmp_path, here="", keys=set()) == []
    changed = before.replace("-1.2732(4)", "-1.2741(3)")
    [problem] = source_problems(before, changed, folder=tmp_path, here="", keys=set())
    assert "states -1.2741 with no source" in problem
