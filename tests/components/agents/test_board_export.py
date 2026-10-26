"""Design 0022 §7: a frame, or a selection, exports as one figure. What is exported is what a paper's figure shows:
the figures and the LaTeX in the frame (or chosen), and the arrows between them; the working layer (notes, slots, pins,
pen strokes, highlights, the frame itself) is left out. Each figure's SVG is nested in the export with ids of its own,
so it stays vector and two figures never share a clip path; a picture is embedded as it is; the export is cropped to
what it shows, with a small margin. A caption's words are written for TeX, its math kept."""

import pytest

from clank.components.agents.boardexport import Art, ExportError, art_of_picture, art_of_svg, chosen, compose, tex_text

BOARD = {"board": 1, "title": "t", "settings": {"grid": 20, "preamble": ""}, "items": [
    {"id": "frame-4", "kind": "frame", "x": 60, "y": 40, "w": 800, "h": 460, "name": "Figure 1"},
    {"id": "fig-1", "kind": "figure", "x": 80, "y": 80, "w": 360, "h": 270, "file": "figures/a.svg"},
    {"id": "fig-2", "kind": "figure", "x": 480, "y": 80, "w": 360, "h": 298, "file": "figures/b.png", "caption": "(b)"},
    {"id": "latex-3", "kind": "latex", "x": 80, "y": 400, "w": 200, "h": 80, "source": "T_0", "mode": "math"},
    {"id": "note-5", "kind": "note", "x": 300, "y": 400, "w": 200, "h": 80, "text": "check"},
    {"id": "pin-6", "kind": "pin", "x": 100, "y": 100, "text": "why?"},
    {"id": "arrow-7", "kind": "arrow", "from": {"item": "latex-3"}, "to": {"item": "fig-1"}},
    {"id": "fig-8", "kind": "figure", "x": 2000, "y": 80, "w": 360, "h": 270, "file": "figures/c.png"},
]}  # fmt: skip
FIGURE = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="460.8pt" height="345.6pt"
 viewBox="0 0 460.8 345.6"><style>#line1 { stroke-width: 2 }</style><script>alert(1)</script>
<defs><clipPath id="p1"><rect width="10" height="10"/></clipPath><path id="m0" d="M 0 0 L 1 1"/></defs>
<g id="line1" clip-path="url(#p1)" onclick="alert(2)"><use xlink:href="#m0" x="3" y="4"/></g></svg>"""


def test_a_frame_exports_its_figures_latex_and_arrows_and_leaves_the_working_layer_out() -> None:
    assert [each["id"] for each in chosen(BOARD, frame="frame-4")] == ["fig-1", "fig-2", "latex-3", "arrow-7"]
    assert [each["id"] for each in chosen(BOARD, ids=["frame-4", "fig-8"])] == ["fig-1", "fig-2", "latex-3", "arrow-7",
                                                                                 "fig-8"]  # fmt: skip
    with pytest.raises(ExportError, match="nothing to export"):
        chosen(BOARD, ids=["note-5", "pin-6"])
    with pytest.raises(ExportError, match="no frame frame-9"):
        chosen(BOARD, frame="frame-9")


def test_a_figures_svg_is_nested_with_ids_of_its_own_and_nothing_that_runs() -> None:
    art = art_of_svg(FIGURE, "f1")
    assert (art.view, round(art.w, 1), round(art.h, 1)) == ("0 0 460.8 345.6", 614.4, 460.8), "points made pixels"
    assert 'id="f1-p1"' in art.inner
    assert 'clip-path="url(#f1-p1)"' in art.inner
    assert 'href="#f1-m0"' in art.inner
    assert "#f1-line1 {" in art.inner, "its style names its own ids"
    assert "script" not in art.inner
    assert "onclick" not in art.inner


def test_a_picture_is_embedded_as_it_is() -> None:
    art = art_of_picture(b"\x89PNG...", "image/png", 40, 30)
    assert art.view == "0 0 40 30"
    assert art.inner.startswith('<image width="40" height="30" href="data:image/png;base64,')


def test_the_export_is_cropped_to_what_it_shows_each_part_placed_in_its_box() -> None:
    items = chosen(BOARD, frame="frame-4")
    arts = {
        "fig-1": Art("0 0 100 75", "<path d='M 0 0'></path>", 100, 75),
        "fig-2": Art("0 0 40 30", "<image></image>", 40, 30),
        "fig-2:caption": Art("0 0 20 10", "<path></path>", 20, 10),
        "latex-3": Art("0 0 30 10", "<path></path>", 40, 15),
    }
    svg = compose(items, arts)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="776" height="416" viewBox="72 72 776 416"')
    assert (
        '<svg x="80" y="80" width="360" height="270" viewBox="0 0 100 75" preserveAspectRatio="xMidYMid meet">' in svg
    )
    assert '<svg x="480" y="80" width="360" height="270" viewBox="0 0 40 30"' in svg, "the picture above its caption"
    assert '<svg x="650" y="359" width="20" height="10" viewBox="0 0 20 10"' in svg, "the caption centered under it"
    assert '<svg x="140" y="425" width="80" height="30" viewBox="0 0 30 10"' in svg, "math at most twice its size"
    assert '<line x1="194.22" y1="400" x2="212" y2="350" ' in svg, "an arrow from edge to edge"
    assert "frame-4" not in svg


def test_a_captions_words_are_written_for_tex_and_its_math_kept() -> None:
    assert tex_text("(a) 50% & more of $x_1$, #2") == "(a) 50\\% \\& more of $x_1$, \\#2"
