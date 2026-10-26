"""Design 0022 §6: a LaTeX item in compiled mode (TikZ, pgfplots, a table) is built in the folder's container with the
TeX layer: a `standalone` document with the board's preamble, pdfLaTeX, then `pdftocairo -svg`; the SVG's glyphs are
flattened into paths (no ids left to collide), and it is kept by its source's and preamble's hash in
`.clank/boards/<board>/latex/`, so the same source is built once. A build that fails says LaTeX's error line; a
container without TeX says how to add it; a math item, or an item that is not on the board, is refused."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.boardlatex import flatten, snippet
from clank.components.agents.boards import BoardError
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
CAIRO = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
 width="72pt" height="20pt" viewBox="0 0 72 20">
<defs>
<g>
<g id="glyph-0-0">
<path d="M 1 1 L 2 2 Z"/>
</g>
</g>
<clipPath id="clip-0"><path d="M 0 0 L 72 0 L 72 20 Z"/></clipPath>
</defs>
<g fill="rgb(0%, 0%, 0%)" fill-opacity="1">
<use xlink:href="#glyph-0-0" x="3" y="10"/>
</g>
<path fill="none" stroke-width="0.4" stroke="rgb(0%, 0%, 100%)" clip-path="url(#clip-0)" d="M 0 5 L 72 5"/>
</svg>
"""


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(kernel: Kernel, tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    board = {"board": 1, "title": "t", "settings": {"grid": 20, "preamble": "\\usepackage{pgfplots}"}, "items": [
        {"id": "latex-1", "kind": "latex", "x": 0, "y": 0, "w": 300, "h": 200, "mode": "compiled",
         "source": "\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}"},
        {"id": "latex-2", "kind": "latex", "x": 0, "y": 0, "w": 300, "h": 80, "source": "x^2", "mode": "math"},
    ]}  # fmt: skip
    (folder / "fig.board").write_text(json.dumps(board), encoding="utf-8")
    return folder


def test_a_snippet_is_a_standalone_document_with_the_boards_preamble() -> None:
    made = snippet("\\begin{tikzpicture}\\end{tikzpicture}", "\\usepackage{siunitx}")
    assert made.startswith("\\documentclass[border=2pt]{standalone}\n")
    assert "\\usepackage{amsmath}" in made
    assert "\\usepackage{pgfplots}\n" in made, "plots need no preamble"
    assert "\\pgfplotsset{compat=1.18}\n" in made
    assert "\\usepackage{siunitx}" in made
    assert made.rstrip().endswith("\\end{document}")


def test_cairos_svg_is_flattened_glyphs_into_paths_with_ids_of_its_own() -> None:
    flat = flatten(CAIRO, "k1")
    assert "<use" not in flat
    assert "glyph-0-0" not in flat
    assert '<g transform="translate(3 10)"><path d="M 1 1 L 2 2 Z"></path></g>' in flat
    assert 'id="k1-clip-0"' in flat
    assert 'clip-path="url(#k1-clip-0)"' in flat
    assert 'viewBox="0 0 72 20"' in flat
    assert 'width="96"' in flat, "72pt is 96 pixels"
    assert 'fill="currentColor"' in flat, "black takes the text's color"
    assert 'stroke="rgb(0%, 0%, 100%)"' in flat, "other colors stay"
    unitless = flatten(CAIRO.replace('width="72pt" height="20pt"', 'width="72" height="20"'), "k1")
    assert 'width="96"' in unitless, "cairo's units are points, said or not"


def test_a_compiled_item_is_built_once_in_the_container_and_kept_by_its_source(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[list[str], bytes]] = []

    def run(workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30.0) -> Answer:
        asked.append((argv, input or b""))
        return Answer(0, CAIRO, "")

    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", run)
    boards = kernel.parts["agents"].boards
    made: dict[str, Any] = boards.compile_latex("paper", "fig", "latex-1")
    assert made["file"].startswith(".clank/boards/fig/latex/")
    assert made["file"].endswith(".svg")
    assert (folder / made["file"]).read_text(encoding="utf-8").startswith("<svg")
    assert b"\\usepackage{pgfplots}" in asked[0][1], "the board's preamble"
    assert boards.compile_latex("paper", "fig", "latex-1")["file"] == made["file"]
    assert len(asked) == 1, "built once"
    with pytest.raises(BoardError, match="math"):
        boards.compile_latex("paper", "fig", "latex-2")


def test_a_failed_build_says_latexs_error_and_no_tex_says_how_to_add_it(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([
        Answer(3, "", "! Undefined control sequence.\nl.4 \\drw\n"),
        Answer(127, "", ""),
    ])  # fmt: skip
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", lambda *args, **kwargs: next(answers))
    boards = kernel.parts["agents"].boards
    assert boards.compile_latex("paper", "fig", "latex-1") == {"error": "Undefined control sequence. (l.4 \\drw)"}
    board = json.loads((folder / "fig.board").read_text(encoding="utf-8"))
    board["items"][0]["source"] = "another"
    (folder / "fig.board").write_text(json.dumps(board), encoding="utf-8")
    assert "clank latex setup" in boards.compile_latex("paper", "fig", "latex-1")["error"]


def test_the_owners_window_asks_the_service_for_a_drawing(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", lambda *args, **kwargs: Answer(0, CAIRO, ""))
    headers = {"Authorization": "Bearer t"}
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:
        asked = {"workspace": "paper", "board": "fig", "id": "latex-1"}
        drawn = client.post("/api/v1/agents/boards/latex", json=asked, headers=headers).json()
        refused = client.post("/api/v1/agents/boards/latex", json={**asked, "id": "latex-2"}, headers=headers)
    assert drawn["file"].endswith(".svg")
    assert refused.status_code == 409


def test_the_agent_hears_at_once_whether_its_compiled_latex_builds_and_a_drawing_is_placed_at_its_size(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([Answer(0, CAIRO, ""), Answer(3, "", "! Missing $ inserted.\nl.5 x_\n")])
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", lambda *args, **kwargs: next(answers))
    boards = kernel.parts["agents"].boards
    added = boards.add("paper", "fig", "latex", {"source": "\\tikz\\draw (0,0)--(2,0);", "mode": "compiled"})
    assert "It builds" in added["said"]
    item = next(each for each in boards.read("paper", "fig")["items"] if each["id"] == added["id"])
    assert (item["w"], item["h"]) == (96, 27), "the drawing's own size"
    changed = boards.update("paper", "fig", added["id"], {"source": "x_"})
    assert "does not build: Missing $ inserted. (l.5 x_)" in changed["said"]
