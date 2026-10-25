"""Design 0020 §10: a PDF of the folder is annotated page by page. Its pages are rendered in the container with each
page's words in boxes (a PDF beside the `.tex` of its name is built by Clank first, so SyncTeX can say where each mark
comes from), kept under `.clank/latex/pages/`. A mark on a page goes to the agent in words: its kind and color, its
page, the source file and line SyncTeX gives for it, and the words under it (a highlight, a box, a drawing), through it
(a strike), after it (an insertion, with what to insert), at it (a note) or pointed at (an arrow); a box with no words
under it is a figure or an equation's image."""

import json
from pathlib import Path
from typing import Any

import pytest

from clank.components.agents.latex.pages import PageMarks, page_image
from clank.kernel.processes import Answer

DPI = 144  # two pixels a point
WORDS = [{"width": 612.0, "height": 792.0, "words": [
    [72.0, 100.0, 110.0, 112.0, "which"], [113.0, 100.0, 120.0, 112.0, "is"],
    [123.0, 100.0, 160.0, 112.0, "clearly"], [163.0, 100.0, 205.0, 112.0, "optimal."],
    [72.0, 130.0, 100.0, 142.0, "Main"], [103.0, 130.0, 140.0, 142.0, "result"],
]}]  # fmt: skip


class Helper:
    """The TeX layer's helper as the pages ask it: what it was asked, and its answers."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.asked: list[dict[str, Any]] = []

    def __call__(self, workspace: str, argv: list[str], given: bytes, timeout: float) -> Answer:
        asked = json.loads(given)
        self.asked.append(asked)
        if asked["mode"] == "build":
            return Answer(0, json.dumps({"built": True, "log": "", "kept": {"pdf": f"{asked['keep']}/main.pdf"}}), "")
        if asked["mode"] == "pages":
            out = self.folder.joinpath(*asked["keep"].split("/"))
            out.mkdir(parents=True, exist_ok=True)
            (out / "page-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            (out / "words.json").write_text(json.dumps(WORDS), encoding="utf-8")
            pages = [{"image": f"{asked['keep']}/page-1.png", "width": 612.0, "height": 792.0}]
            words = f"{asked['keep']}/words.json"
            return Answer(0, json.dumps({"pages": pages, "dpi": asked["dpi"], "words": words}), "")
        places = [
            {"input": "/workspace/paper/intro.tex", "line": 12 + number} for number in range(len(asked["points"]))
        ]
        return Answer(0, json.dumps({"places": places}), "")


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    (tmp_path / "paper" / "main.pdf").write_bytes(b"%PDF-1.7\n")
    (tmp_path / "other.pdf").write_bytes(b"%PDF-1.7\n")
    return tmp_path


def test_a_pdf_beside_its_tex_is_built_first_then_its_pages_are_rendered_and_kept(folder: Path) -> None:
    helper = Helper(folder)
    pages = PageMarks(helper, dpi=DPI)
    shown = pages.render("paper", folder, "paper/main.pdf")
    build, render = helper.asked
    assert (build["mode"], build["root"], build["keep"]) == ("build", "paper/main.tex", ".clank/latex/build/paper-main")
    assert (render["mode"], render["pdf"], render["dpi"]) == ("pages", ".clank/latex/build/paper-main/main.pdf", DPI)
    assert render["keep"] == ".clank/latex/pages/paper-main"
    assert shown == {"pdf": "paper/main.pdf", "built": True,
                     "pages": [{"number": 1, "image": ".clank/latex/pages/paper-main/page-1.png"}]}  # fmt: skip
    pages_json = folder / ".clank" / "latex" / "pages" / "paper-main" / "pages.json"
    kept = json.loads(pages_json.read_text(encoding="utf-8"))
    assert (kept["pdf"], kept["dpi"]) == ("paper/main.pdf", DPI)
    assert kept["words"] == ".clank/latex/pages/paper-main/words.json"
    assert page_image(folder, ".clank/latex/pages/paper-main/page-1.png") == (kept, 1)
    assert page_image(folder, "figs/plot.png") is None


def test_a_pdf_with_no_tex_beside_it_is_rendered_as_it_is(folder: Path) -> None:
    helper = Helper(folder)
    shown = PageMarks(helper, dpi=DPI).render("paper", folder, "other.pdf")
    [render] = helper.asked
    assert (render["mode"], render["pdf"]) == ("pages", "other.pdf")
    assert shown["built"] is False


def test_each_mark_on_a_page_is_said_with_its_line_and_the_words_under_it(folder: Path) -> None:
    helper = Helper(folder)
    pages = PageMarks(helper, dpi=DPI)
    pages.render("paper", folder, "paper/main.pdf")
    marks = [
        {"n": 1, "kind": "highlight", "color": "#f5a524", "points": [[140, 196], [420, 228]]},
        {"n": 2, "kind": "strike", "color": "#e5484d", "points": [[240, 212], [420, 212]]},
        {"n": 3, "kind": "insert", "color": "#e5484d", "points": [[204, 270]], "text": "a comma"},
        {"n": 4, "kind": "box", "color": "#3e63dd", "points": [[400, 600], [600, 800]]},
        {"n": 5, "kind": "text", "color": "#3e63dd", "points": [[280, 210]], "text": "say why"},
        {"n": 6, "kind": "arrow", "color": "#30a46c", "points": [[100, 400], [215, 272]]},
    ]
    said = pages.describe("paper", folder, ".clank/latex/pages/paper-main/page-1.png", marks)
    assert said == [
        "Mark 1 (amber highlight) on page 1, from paper/intro.tex line 12: over 'which is clearly optimal.'.",
        "Mark 2 (red strike) on page 1, from paper/intro.tex line 13: through 'clearly optimal.'.",
        "Mark 3 (red insertion) \"a comma\" on page 1, from paper/intro.tex line 14: after 'Main'.",
        "Mark 4 (blue box) on page 1, from paper/intro.tex line 15: around no text (a figure, or an equation's image).",
        "Mark 5 (blue note) \"say why\" on page 1, from paper/intro.tex line 16: at 'clearly'.",
        "Mark 6 (green arrow) on page 1, from paper/intro.tex line 17: pointing at 'result'.",
    ]
    where = helper.asked[-1]
    assert where["mode"] == "where"
    assert where["pdf"] == ".clank/latex/build/paper-main/main.pdf", "SyncTeX reads the PDF Clank built"
    assert where["points"][0] == {"page": 1, "x": 140.0, "y": 106.0}, "a mark's middle, in points"
