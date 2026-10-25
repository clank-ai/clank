"""Design 0020 §4 and §5: the review's rule for LaTeX files and the checks on every LaTeX change, run against a fake
OpenCode server with the bridge's watcher, the builds answered from logs recorded in the TeX layer.

A change to a `.tex` file the owner had is asked about even in auto mode; a `.tex` file the agent created follows the
mode (auto: written once it passes); a `.bib` file is always asked about. Before a LaTeX change is asked about or
answered, it is checked (citations, sources, the build): a change that fails is rejected with its reasons, which the
model hears, and nobody is asked; the third refusal of a file in a row asks the owner, the refusals shown; a check that
cannot run (no TeX in the container) asks the owner, saying so. Each check is an event (`agents.change_checked`).
Design 0020 §9: once a change is asked about, its document marked by latexdiff between before and after is built in
the container, and the event `agents.latex_diff` names its PDF, which the window opens beside the diff; a new document
is built as it is instead."""

import json
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from clank.kernel.core import Kernel
from clank.kernel.processes import Answer
from tests.components.agents.test_review import (  # noqa: F401 (fixtures)
    USER,
    OpenCode,
    asked,
    feed,
    kernel,
    plan_ask,
    sent,
    served,
    until,
    watched,
)

RECORDED = Path(__file__).parents[2] / "fixtures" / "latex"
DIFFS: list[dict[str, Any]] = []  # what the helper was asked, in order
PAPER = (
    "\\documentclass{article}\n\\usepackage{natbib}\n\\begin{document}\n\\section{Intro}\\label{sec:intro}\n"
    "Known \\citep{a2004}.\n\n\\bibliographystyle{plainnat}\n\\bibliography{refs}\n\\end{document}\n"
)
BIB = "@article{a2004, title={Improved simulation of stabilizer circuits}, author={Aaronson, Scott}, year={2004},\n" \
      "  doi={10.1103/PhysRevA.70.052328}}\n"  # fmt: skip


def recorded(name: str) -> str:
    return (RECORDED / name).read_text(encoding="utf-8", errors="replace")


def builds(log: Callable[[str | None], tuple[bool, str]] | None = None) -> Callable[..., Answer]:
    """The TeX layer's helper as the checks ask it: each build answered from a recorded log, by the text it builds."""

    def answer(text: str | None) -> tuple[bool, str]:
        if text is not None and "\\undefinedthing" in text:
            return False, recorded("broken2.log")
        return True, recorded("clean.log")

    chosen = log or answer

    def run(workspace: str, argv: list[str], given: bytes, timeout: float) -> Answer:
        asked = json.loads(given)
        DIFFS.append(asked)
        if asked["mode"] == "diff":
            return Answer(
                0, json.dumps({"built": True, "pdf": f"{asked['keep']}/diff.pdf", "log": "", "seconds": 2}), ""
            )
        built, text = chosen(asked.get("text"))
        if asked.get("keep"):
            return Answer(0, json.dumps({"built": True, "log": text, "kept": {"pdf": f"{asked['keep']}/note.pdf"},
                                         "seconds": 1.5}), "")  # fmt: skip
        return Answer(0, json.dumps({"built": built, "status": 0 if built else 12, "log": text, "blg": "",
                                     "seconds": 1.5}), "")  # fmt: skip

    return run


def reply_to(request: str) -> dict[str, Any] | None:
    """What the agent was answered about a change, once it was."""
    found: dict[str, Any] | None = next(
        (body for path, body in OpenCode.sent if path == f"/permission/{request}/reply"), None
    )
    return found


def ask_write(id: str, relative: str, content: str) -> dict[str, Any]:
    return plan_ask(id, relative, "write", {"filePath": f"/workspace/{relative}", "content": content})


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    (tmp_path / "main.tex").write_bytes(PAPER.encode())  # as the agent's container writes it: no carriage returns
    (tmp_path / "refs.bib").write_bytes(BIB.encode())
    return tmp_path


def latex(kernel: Kernel) -> Any:  # noqa: F811
    return kernel.parts["agents"].review.latex


def test_a_change_to_the_owners_tex_is_asked_about_in_auto_mode_once_it_passed_the_checks(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    review = watched(kernel, paper, port, monkeypatch)
    latex(kernel).builder.run = builds()
    review.switch("paper", "auto", actor=USER)
    feed("permission.asked", ask_write("per_1", "main.tex", PAPER.replace("Known", "Well known")))
    question = asked(kernel, "per_1")
    assert question.detail.startswith("Clank's LaTeX checks passed: citations (none added), sources (no value "
                                      "stated), the build (as clean as before, 1.5 s).")  # fmt: skip
    assert review.store.get("per_1")["mode"] == "review", "the owner's file: asked about in auto mode too"  # type: ignore[index]
    [checked] = kernel.events.after(0, types=["agents.change_checked"])
    assert (checked.data["file"], checked.data["passed"], checked.data["refusals"]) == ("main.tex", True, [])
    [marked] = until(lambda: kernel.events.after(0, types=["agents.latex_diff"]))
    assert marked.data == {"workspace": "paper", "folder": str(paper), "change": "per_1", "file": "main.tex",
                           "pdf": ".clank/latex/per_1/diff.pdf", "marked": True}  # fmt: skip
    [diffed] = [asked for asked in DIFFS if asked["mode"] == "diff"]
    assert (diffed["root"], diffed["file"], diffed["before"]) == ("main.tex", "main.tex", PAPER)
    assert diffed["after"] == PAPER.replace("Known", "Well known")


def test_a_change_that_fails_a_check_is_rejected_with_its_reasons_and_nobody_is_asked(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    review = watched(kernel, paper, port, monkeypatch)
    latex(kernel).builder.run = builds()
    feed("permission.asked", ask_write("per_1", "main.tex", PAPER.replace("a2004", "invented2025")))
    until(lambda: any(path == "/permission/per_1/reply" for path, _ in OpenCode.sent))
    [(_, reply)] = [each for each in OpenCode.sent if each[0] == "/permission/per_1/reply"]
    assert reply["reply"] == "reject"
    assert reply["message"].startswith("Clank's LaTeX checks refused this change to main.tex: fix each, then propose")
    assert (
        "\\cite{invented2025} on line 5: no bibliography of the document has an entry invented2025" in reply["message"]
    )
    assert not kernel.questions.waiting()
    change = review.store.get("per_1")
    assert change is not None
    assert (change["state"], change["by"]) == ("rejected", "Clank (LaTeX checks)")
    [checked] = kernel.events.after(0, types=["agents.change_checked"])
    assert checked.data["passed"] is False


def test_the_build_failing_refuses_and_the_third_refusal_in_a_row_asks_the_owner(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    watched(kernel, paper, port, monkeypatch)
    latex(kernel).builder.run = builds()
    broken = PAPER.replace("Known", "Known \\undefinedthing")
    for request in ("per_1", "per_2"):
        feed("permission.asked", ask_write(request, "main.tex", broken))
        assert until(partial(reply_to, request))["reply"] == "reject"
    first = reply_to("per_1")
    assert first is not None
    assert "the document no longer builds: broken2.tex line 5: Undefined control sequence." in first["message"]
    feed("permission.asked", ask_write("per_3", "main.tex", broken))
    question = asked(kernel, "per_3")
    assert question.detail.startswith("Clank's LaTeX checks refused this change 3 times in a row; the last time:")
    assert "the document no longer builds" in question.detail


def test_a_tex_file_the_agent_created_follows_auto_mode(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    review = watched(kernel, paper, port, monkeypatch)
    latex(kernel).builder.run = builds()
    review.switch("paper", "auto", actor=USER)
    note = "\\documentclass{article}\n\\begin{document}\nA note.\n\\end{document}\n"
    feed("permission.asked", ask_write("per_1", "note.tex", note))
    until(lambda: sent({"reply": "once"}))
    (paper / "note.tex").write_text(note, encoding="utf-8")
    feed("file.edited", {"file": "/workspace/note.tex"})
    until(lambda: (review.store.get("per_1") or {}).get("written"))
    feed("permission.asked", ask_write("per_2", "note.tex", note.replace("A note", "A longer note")))
    until(lambda: sent({"reply": "once"}, "per_2"))
    assert not kernel.questions.waiting(), "the agent's own document, in auto mode"


def test_without_tex_in_the_container_the_owner_is_asked_and_told_why(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    review = watched(kernel, paper, port, monkeypatch)
    latex(kernel).builder.run = lambda *args: Answer(2, "", "python3: can't open file '/opt/clank/latex_build.py'")
    review.switch("paper", "auto", actor=USER)
    note = "\\documentclass{article}\n\\begin{document}\nA note.\n\\end{document}\n"
    feed("permission.asked", ask_write("per_1", "note.tex", note))
    question = asked(kernel, "per_1")
    assert not kernel.events.after(0, types=["agents.latex_diff"]), "no TeX: no PDF"
    assert "NOT CHECKED: TeX is not in paper's container, so the document could not be built: `clank latex setup`" \
        in question.detail  # fmt: skip


def test_a_bib_entry_without_a_doi_or_arxiv_id_is_refused(
    kernel: Kernel,  # noqa: F811
    served: Any,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _ = served
    watched(kernel, paper, port, monkeypatch)
    latex(kernel).lookup.fetch = lambda url: (_ for _ in ()).throw(AssertionError("not looked up"))
    added = BIB + "@book{knuth1984, title={The TeXbook}, author={Knuth, Donald}, year={1984}}\n"
    feed("permission.asked", ask_write("per_1", "refs.bib", added))
    until(lambda: any(path == "/permission/per_1/reply" for path, _ in OpenCode.sent))
    [(_, reply)] = [each for each in OpenCode.sent if each[0] == "/permission/per_1/reply"]
    assert "@book{knuth1984} on line 3: it has no DOI and no arXiv id" in reply["message"]
