"""Design 0020 §8: the document a changed file belongs to is found (its `% !TEX root`, the file itself when it has
`\\documentclass`, else the file that includes it with `\\input`, `\\include` or `\\subfile`, from its folder or the
folder's root), and its engine (`% !TEX program`, LuaLaTeX for `fontspec` or `unicode-math`, else pdfLaTeX). A build's
log is read (logs recorded from real builds, `tests/fixtures/latex/`): its errors with their file and line, its
undefined references and citations (LaTeX's, natbib's, BibTeX's), its labels defined twice. A change is refused when
the document no longer builds, or when its build has an undefined reference or citation, or a label defined twice, that
the build before it did not have; warnings the document already had do not refuse it."""

from pathlib import Path

from clank.components.agents.latex.building import BuildLog, compile_problems, engine_of, parse_log, root_of

RECORDED = Path(__file__).parents[2] / "fixtures" / "latex"


def recorded(name: str) -> str:
    return (RECORDED / name).read_text(encoding="utf-8", errors="replace")


def test_the_root_is_the_magic_comment_the_file_itself_or_the_file_that_includes_it() -> None:
    texts = {
        "paper/main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{sections/intro}\n\\include{results}\n"
        "\\end{document}\n",
        "paper/sections/intro.tex": "\\section{Intro}\n",
        "paper/results.tex": "\\section{Results}\n",
        "paper/appendix.tex": "% !TEX root = main.tex\n\\section{Appendix}\n",
        "notes/fragment.tex": "Just a fragment.\n",
        "talk/slides.tex": "\\documentclass{beamer}\n",
    }
    assert root_of("paper/sections/intro.tex", texts) == "paper/main.tex"
    assert root_of("paper/results.tex", texts) == "paper/main.tex"
    assert root_of("paper/appendix.tex", texts) == "paper/main.tex"
    assert root_of("talk/slides.tex", texts) == "talk/slides.tex"
    assert root_of("paper/main.tex", texts) == "paper/main.tex"
    assert root_of("notes/fragment.tex", texts) is None


def test_the_engine_is_the_magic_comment_lualatex_for_its_fonts_or_pdflatex() -> None:
    assert engine_of("% !TEX program = xelatex\n\\documentclass{article}") == "xelatex"
    assert engine_of("\\documentclass{article}\n\\usepackage{fontspec}") == "lualatex"
    assert engine_of("\\documentclass{article}\n% \\usepackage{fontspec}") == "pdf"


def test_a_clean_build_has_nothing_to_say() -> None:
    log = parse_log(recorded("clean.log"))
    assert log == BuildLog(errors=[], references=set(), citations=set(), labels=set())


def test_the_warnings_of_a_build_are_read_from_its_log_and_bibtexs() -> None:
    log = parse_log(recorded("warn.log"), recorded("warn.blg"))
    assert log.references == {"sec:missing"}
    assert log.citations == {"invented2025"}
    assert log.labels == {"sec:intro"}
    assert log.errors == []


def test_a_failed_builds_errors_are_read_with_their_file_and_line() -> None:
    assert parse_log(recorded("broken2.log")).errors == ["broken2.tex line 5: Undefined control sequence."]
    assert parse_log(recorded("broken.log")).errors == ["File ended while scanning use of \\frac ."]


def test_a_change_is_refused_for_a_failed_build_or_what_its_build_adds() -> None:
    clean = parse_log(recorded("clean.log"))
    warned = parse_log(recorded("warn.log"), recorded("warn.blg"))
    [failed] = compile_problems(clean, parse_log(recorded("broken2.log")), built=False)
    assert failed == "the document no longer builds: broken2.tex line 5: Undefined control sequence."
    added = compile_problems(clean, warned, built=True)
    assert added == [
        "its build has an undefined reference: sec:missing (a \\ref to no \\label)",
        "its build has an undefined citation: invented2025",
        "its build has a label defined twice: sec:intro",
    ]
    assert compile_problems(warned, warned, built=True) == [], "what the document had already is not the change's"
    assert compile_problems(None, warned, built=True) == added, "a new document's own warnings are its"
