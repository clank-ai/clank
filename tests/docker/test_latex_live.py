"""Design 0020 §3, §5, §6, §7, §8, §9 and §10, end to end, on this machine's Docker when asked (`-m docker`): a
workspace opened with the TeX layer (its image built when missing), then, through the service's own parts and the
workspace's real container: the checks on
real changes to a document (a clean change passes and its build is as clean as before; an invented citation, a value
without a source, an undefined reference and a change that breaks the build are refused, each with its reason; a new
bibliography entry is checked against Crossref's record, a wrong year refused), the change's PDF marked by latexdiff,
the document's pages rendered with their words and a mark said with its source line, and LaTeX Workshop's build
keeping the PDF beside the document."""

import json
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.agents.latex.checks import LatexChecks
from clank.kernel.core import Kernel
from clank.kernel.events import Actor

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
YOU = Actor(kind="user", via="console")
OPEN_SECONDS = 2400  # the first open builds the images
MAIN = r"""\documentclass{article}
\usepackage{natbib}
\begin{document}
\section{Introduction}\label{sec:intro}
Stabilizer rank bounds are reviewed by \citet{a2004}.

\input{results}
\bibliographystyle{plainnat}
\bibliography{refs}
\end{document}
"""
RESULTS = r"""\section{Results}\label{sec:results}
The method converges quickly, as Section~\ref{sec:intro} explains.
"""
BIB = """@article{a2004,
  title = {Improved simulation of stabilizer circuits},
  author = {Aaronson, Scott and Gottesman, Daniel},
  journal = {Phys. Rev. A}, volume = {70}, pages = {052328}, year = {2004},
  doi = {10.1103/PhysRevA.70.052328},
}
"""


async def opened(kernel: Kernel, folder: Path) -> dict[str, Any]:
    params = {"folder": str(folder), "yes": True, "layers": ["tex"]}
    started = await kernel.operations.start("workspaces.open", params, actor=YOU)
    with anyio.fail_after(OPEN_SECONDS):
        done = await kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    return dict(done.result or {})


def change(folder: Path, relative: str, after: str, id: str) -> dict[str, Any]:
    path = folder.joinpath(*relative.split("/"))
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    return {"id": id, "workspace": "paper", "relative": relative, "folder": str(folder), "before": before,
            "after": after, "created": before is None}  # fmt: skip


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    folder.mkdir()
    for name, text in (("main.tex", MAIN), ("results.tex", RESULTS), ("refs.bib", BIB)):
        (folder / name).write_bytes(text.encode())
    (folder / "runs").mkdir()
    (folder / "runs" / "fit.json").write_text("{}", encoding="utf-8")
    return folder


async def test_the_latex_checks_marked_pdf_pages_and_build_run_for_real(machine: Kernel, paper: Path) -> None:
    async with machine.operations.running():
        result = await opened(machine, paper)
    assert result["image"].startswith("clank-sandbox-tex:")
    latex: LatexChecks = machine.parts["agents"].review.latex

    def check(relative: str, after: str, id: str) -> Any:
        return latex.check(change(paper, relative, after, id))

    clean = await anyio.to_thread.run_sync(lambda: check("results.tex", RESULTS + "It holds for every size.\n", "c1"))
    assert clean.refusals == [], clean
    assert clean.unchecked == [], clean
    assert any(each.startswith("the build (as clean as before") for each in clean.passed), clean.passed
    invented = await anyio.to_thread.run_sync(
        lambda: check("results.tex", RESULTS + "See \\citet{nobody2025}.\n", "c2")
    )
    assert invented.refusals[0].startswith("\\cite{nobody2025} on line 3: no bibliography of the document has an entry")
    unsourced = await anyio.to_thread.run_sync(
        lambda: check("results.tex", RESULTS + "\nThe energy is $E_0 = -1.2732$.\n", "c3")
    )
    assert "states -1.2732 with no source" in unsourced.refusals[0]
    sourced = await anyio.to_thread.run_sync(
        lambda: check("results.tex", RESULTS + "\nThe energy is $E_0 = -1.2732$. % source: runs/fit.json\n", "c4")
    )
    assert sourced.refusals == [], sourced
    dangling = await anyio.to_thread.run_sync(
        lambda: check("results.tex", RESULTS + "As in Section~\\ref{sec:missing}.\n", "c5")
    )
    assert dangling.refusals == ["its build has an undefined reference: sec:missing (a \\ref to no \\label)"]
    broken = await anyio.to_thread.run_sync(lambda: check("results.tex", RESULTS + "\\undefinedthing\n", "c6"))
    assert broken.refusals[0].startswith("the document no longer builds: results.tex line 3: Undefined control")
    entry = (
        "@article{b2004, title={Improved simulation of stabilizer circuits}, author={Aaronson, Scott}, "
        "year={2004}, doi={10.1103/PhysRevA.70.052328}}\n"
    )
    good = await anyio.to_thread.run_sync(lambda: check("refs.bib", BIB + entry, "c7"))
    assert good.refusals == [], good
    wrong = await anyio.to_thread.run_sync(lambda: check("refs.bib", BIB + entry.replace("2004}", "2009}"), "c8"))
    assert "year 2009" in wrong.refusals[0], wrong

    marked = change(paper, "results.tex", RESULTS.replace("quickly", "slowly"), "c9")
    marked["checks"] = latex.check(marked).view()
    await anyio.to_thread.run_sync(lambda: latex.marked(marked))
    [event] = machine.events.after(0, types=["agents.latex_diff"])
    assert event.data["pdf"] == ".clank/latex/c9/diff.pdf"
    assert (paper / ".clank" / "latex" / "c9" / "diff.pdf").read_bytes().startswith(b"%PDF")

    built = await anyio.to_thread.run_sync(lambda: latex.build_file(str(paper / "results.tex")))
    assert (built["built"], built["root"], built["warnings"]) == (True, "main.tex", [])
    assert (paper / "main.pdf").read_bytes().startswith(b"%PDF")
    assert (paper / "main.synctex.gz").is_file()

    pages = machine.parts["agents"].pages
    shown = await anyio.to_thread.run_sync(lambda: pages.render("paper", paper, "main.pdf"))
    assert shown["built"] is True
    [page] = shown["pages"]
    meta = json.loads((paper / ".clank" / "latex" / "pages" / "main" / "pages.json").read_text(encoding="utf-8"))
    words = json.loads((paper / ".clank" / "latex" / "pages" / "main" / "words.json").read_text(encoding="utf-8"))
    quickly = next(word for word in words[0]["words"] if word[4] == "quickly,")
    scale = meta["dpi"] / 72.0
    middle = (quickly[1] + quickly[3]) / 2 * scale
    strike = {"n": 1, "kind": "strike", "color": "#e5484d",
              "points": [[quickly[0] * scale - 2, middle], [quickly[2] * scale + 2, middle]]}  # fmt: skip
    said = await anyio.to_thread.run_sync(lambda: pages.describe("paper", paper, page["image"], [strike]))
    assert said == ["Mark 1 (red strike) on page 1, from results.tex line 2: through 'quickly,'."]
