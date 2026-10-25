"""Design 0020 §8-§10: the TeX layer's build helper (`layers/tex/latex_build.py`, run in the container). A build's
scratch tree holds the folder's files so that a build never writes into the folder: LaTeX's own sources are copied,
what TeX only reads (figures, data) is linked, and what a build writes (a document's `.aux`, `.log`, `.pdf` beside its
`.tex`, SyncTeX's file, latexmk's) is left out, so no build can write through a link. SyncTeX's answer is read into the
file and line a point of a page comes from, and Poppler's word boxes into each page's words; latexmk's argument for each
engine is named. Real builds in the TeX layer's image are in `tests/docker/test_latex_layer.py`."""

import importlib.util
from types import ModuleType

from clank.components.workspaces.sandbox import layer_folder

HELPER = layer_folder("tex") / "latex_build.py"


def helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("latex_build", HELPER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sources_are_copied_inputs_linked_and_build_outputs_left_out() -> None:
    build = helper()
    stems = {"paper": {"main", "intro"}}
    assert build.placed("paper/main.tex", stems) == "copy"
    assert build.placed("paper/refs.bib", stems) == "copy"
    assert build.placed("paper/style.sty", stems) == "copy"
    assert build.placed("paper/figs/plot.pdf", stems) == "link", "a figure's PDF has no .tex of its name beside it"
    assert build.placed("paper/data/fit.csv", stems) == "link"
    for written in ("paper/main.aux", "paper/main.log", "paper/main.pdf", "paper/main.synctex.gz", "paper/intro.aux",
                    "paper/main.fdb_latexmk", "paper/main.bbl", "paper/main.bcf", "paper/main.run.xml"):  # fmt: skip
        assert build.placed(written, stems) == "skip", written
    assert build.engine_argument("pdf") == "-pdf"
    assert build.engine_argument("lualatex") == "-lualatex"
    assert build.engine_argument("xelatex") == "-xelatex"


def test_synctex_says_the_file_and_line_of_a_point() -> None:
    said = (
        "This is SyncTeX command line utility, version 1.5\nSyncTeX result begin\nOutput:/tmp/x/main.pdf\n"
        "Input:/workspace/paper/./intro.tex\nLine:14\nColumn:-1\nOffset:0\nContext:\nSyncTeX result end\n"
    )
    assert helper().synctex_place(said) == {"input": "/workspace/paper/intro.tex", "line": 14}
    assert helper().synctex_place("SyncTeX result begin\nSyncTeX result end\n") is None


def test_poppler_word_boxes_are_read_page_by_page() -> None:
    boxes = (
        '<html><body><doc><page width="612.000000" height="792.000000"><flow><block><line>'
        '<word xMin="72.000" yMin="80.500" xMax="110.250" yMax="92.000">Main</word>'
        '<word xMin="113.0" yMin="80.5" xMax="160.0" yMax="92.0">result&amp;co</word>'
        '</line></block></flow></page><page width="612" height="792"></page></doc></body></html>'
    )
    pages = helper().word_boxes(boxes)
    assert pages == [
        {"width": 612.0, "height": 792.0,
         "words": [[72.0, 80.5, 110.25, 92.0, "Main"], [113.0, 80.5, 160.0, 92.0, "result&co"]]},
        {"width": 612.0, "height": 792.0, "words": []},
    ]  # fmt: skip
