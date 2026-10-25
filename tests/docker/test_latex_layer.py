"""Design 0020 §8-§10, run in the TeX layer's image on this machine's Docker (`-m docker`; skipped when the image is
not built): a build of a changed document answers its log and changes nothing in the folder, though the folder holds
the owner's own `.aux` and PDF of that document; latexdiff's marked-up PDF is kept under `.clank/`; a PDF's pages become
images with their words in boxes; and SyncTeX gives back the line a point of a page comes from."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clank.components.workspaces.sandbox import layered_tag
from clank.kernel.processes import background_flags

pytestmark = pytest.mark.docker
MAIN = (
    "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\\label{sec:intro}\n"
    "The first result is shown here.\n\n\\input{results}\n\\end{document}\n"
)
RESULTS = "\\section{Results}\nThe energy is low.\n"


def helper(folder: Path, asked: dict[str, Any]) -> dict[str, Any]:
    image = layered_tag(["tex"])
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False).returncode != 0:
        pytest.skip(f"the TeX layer's image {image} is not built here: clank latex setup builds it")
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", "-v", f"{folder}:/workspace", "-w", "/workspace", image,
         "python3", "/opt/clank/latex_build.py"],
        input=json.dumps(asked).encode(), capture_output=True, timeout=600, check=False,
        creationflags=background_flags(),
    )  # fmt: skip
    answered: dict[str, Any] = json.loads(done.stdout or b"{}")
    return answered


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "main.tex").write_text(MAIN, encoding="utf-8")
    (paper / "results.tex").write_text(RESULTS, encoding="utf-8")
    (paper / "main.aux").write_text("% the owner's own\n", encoding="utf-8")
    (paper / "main.pdf").write_bytes(b"%PDF-1.4 the owner's own build\n")
    return paper


def files(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def test_a_build_of_a_change_answers_its_log_and_writes_nothing_in_the_folder(folder: Path) -> None:
    before = files(folder)
    changed = RESULTS + "See Section~\\ref{sec:missing}.\n"
    said = helper(folder, {"mode": "build", "root": "main.tex", "file": "results.tex", "text": changed,
                           "engine": "pdf", "seconds": 120})  # fmt: skip
    assert said["built"] is True, said
    assert "Reference `sec:missing' on page 1 undefined" in said["log"]
    assert files(folder) == before, "nothing in the folder changed"
    broken = helper(folder, {"mode": "build", "root": "main.tex", "file": "results.tex", "text": "\\undefinedthing\n",
                             "engine": "pdf", "seconds": 120})  # fmt: skip
    assert broken["built"] is False
    assert "results.tex:1: Undefined control sequence." in broken["log"]


def test_a_changes_marked_up_pdf_is_kept_under_clank(folder: Path) -> None:
    said = helper(folder, {"mode": "diff", "root": "main.tex", "file": "results.tex", "before": RESULTS,
                           "after": RESULTS.replace("low", "lower than before"), "engine": "pdf", "seconds": 180,
                           "keep": ".clank/latex/change-1"})  # fmt: skip
    assert said.get("built") is True, said
    assert said["pdf"] == ".clank/latex/change-1/diff.pdf"
    assert (folder / ".clank" / "latex" / "change-1" / "diff.pdf").read_bytes().startswith(b"%PDF")
    assert (folder / ".clank" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_a_pdfs_pages_and_words_and_synctex_give_back_the_line_of_a_point(folder: Path) -> None:
    built = helper(folder, {"mode": "build", "root": "main.tex", "file": "main.tex", "text": None, "engine": "pdf",
                            "seconds": 120, "keep": ".clank/latex/build"})  # fmt: skip
    assert built["kept"] == {"pdf": ".clank/latex/build/main.pdf"}, built
    shown = helper(folder, {"mode": "pages", "pdf": ".clank/latex/build/main.pdf", "keep": ".clank/latex/pages/main",
                            "dpi": 72})  # fmt: skip
    [page] = shown["pages"]
    assert page["image"] == ".clank/latex/pages/main/page-1.png"
    assert (page["width"], page["height"]) == (595.276, 841.89), "A4, TeX Live's paper on Ubuntu"
    words = json.loads((folder / ".clank" / "latex" / "pages" / "main" / "words.json").read_text(encoding="utf-8"))
    energy = next(word for word in words[0]["words"] if word[4] == "energy")
    x, y = (energy[0] + energy[2]) / 2, (energy[1] + energy[3]) / 2
    said = helper(
        folder, {"mode": "where", "pdf": ".clank/latex/build/main.pdf", "points": [{"page": 1, "x": x, "y": y}]}
    )
    [place] = said["places"]
    assert place == {"input": "/workspace/results.tex", "line": 2}


def test_latex_workshops_build_keeps_the_pdf_log_and_synctex_beside_the_document_with_this_machines_paths(
    folder: Path,
) -> None:
    asked = {"mode": "build", "root": "main.tex", "file": "main.tex", "text": None, "engine": "pdf", "seconds": 120,
             "keep": "", "synctex_root": "D:/research/paper", "log": True}  # fmt: skip
    said = helper(folder, asked)
    assert said["built"] is True, said
    assert said["kept"] == {"pdf": "main.pdf"}
    assert (folder / "main.pdf").read_bytes().startswith(b"%PDF"), "the owner's own build replaced, as a build does"
    assert (folder / "main.log").is_file()
    import gzip

    with gzip.open(folder / "main.synctex.gz", "rt", encoding="utf-8") as read:
        synctex = read.read()
    assert "D:/research/paper/" in synctex
    assert "/tmp/clank-latex-" not in synctex
