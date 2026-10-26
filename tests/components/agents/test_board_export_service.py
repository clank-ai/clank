"""Design 0022 §7: a frame exports as a file of the folder, beside its board (named after the frame) or where the
owner or the agent says, as PDF or PNG (made with librsvg in the folder's container, from the export's SVG) or SVG.
The LaTeX and the captions are typeset by TeX there, so the figure's words are the paper's. A frame can be kept
exported: the board then remembers the file. A container without the converter says how to add it; a part that does
not build is left out and said."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.components.agents.test_boards import png
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
HEADERS = {"Authorization": "Bearer t"}
TEX = '<svg xmlns="http://www.w3.org/2000/svg" width="30pt" height="10pt" viewBox="0 0 30 10"><path d="M 0 0"/></svg>'
FIGURE = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="75"><path id="a" d="M 0 0 L 9 9"/></svg>'


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(kernel: Kernel, tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    (folder / "figures").mkdir(parents=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    (folder / "figures" / "a.svg").write_text(FIGURE, encoding="utf-8")
    png(folder / "figures" / "b.png", 40, 30)
    board = {"board": 1, "title": "Fig", "settings": {"grid": 20, "preamble": ""}, "items": [
        {"id": "frame-4", "kind": "frame", "x": 60, "y": 40, "w": 800, "h": 460, "name": "Figure 1"},
        {"id": "fig-1", "kind": "figure", "x": 80, "y": 80, "w": 360, "h": 270, "file": "figures/a.svg"},
        {"id": "fig-2", "kind": "figure", "x": 480, "y": 80, "w": 360, "h": 298, "file": "figures/b.png",
         "caption": "(b) 50%"},
        {"id": "latex-3", "kind": "latex", "x": 80, "y": 400, "w": 200, "h": 80, "source": "T_0", "mode": "math"},
    ]}  # fmt: skip
    (folder / "figures" / "fig.board").write_text(json.dumps(board), encoding="utf-8")
    return folder


def container(folder: Path, asked: list[list[str]], converter: bool = True):  # type: ignore[no-untyped-def]
    """The folder's container: TeX answers with a drawing; librsvg writes the file it is asked for."""

    def run(workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30.0) -> Answer:
        asked.append(argv)
        if argv[0] == "sh":
            return Answer(0, TEX, "")
        if not converter:
            return Answer(127, "", "")
        out = argv[argv.index("-o") + 1]
        (folder / out.removeprefix("/workspace/")).write_bytes(b"%PDF-1.5 made")
        return Answer(0, "", "")

    return run


def test_a_frame_exports_as_a_pdf_beside_its_board_with_its_latex_typeset_by_tex(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", container(folder, asked))
    made = kernel.parts["agents"].boards.export("paper", "figures/fig", frame="frame-4")
    assert made["file"] == "figures/figure-1.pdf"
    assert (folder / "figures" / "figure-1.pdf").read_bytes().startswith(b"%PDF")
    assert made["said"].startswith("Exported frame-4 as figures/figure-1.pdf")
    converted = asked[-1]
    assert converted[:3] == ["rsvg-convert", "-f", "pdf"]
    composed = (folder / converted[-1].removeprefix("/workspace/")).read_text(encoding="utf-8")
    assert composed.count("<svg") == 5, "the export, two figures, the caption and the math"
    assert 'id="f1-a"' in composed
    assert "data:image/png;base64," in composed
    assert sum(1 for each in asked if each[0] == "sh") == 2, "the caption and the math, by TeX"


def test_an_export_can_be_png_or_svg_and_kept_and_without_the_converter_says_how_to_add_it(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", container(folder, asked))
    boards = kernel.parts["agents"].boards
    made = boards.export("paper", "figures/fig", ids=["fig-1"], file="out/one.png", dpi=150)
    assert made["file"] == "out/one.png"
    assert asked[-1][:7] == ["rsvg-convert", "-f", "png", "-d", "150", "-p", "150"]
    kept = boards.export("paper", "figures/fig", frame="frame-4", format="svg", keep=True)
    assert (folder / kept["file"]).read_text(encoding="utf-8").startswith("<svg")
    frame = next(each for each in boards.read("paper", "figures/fig")["items"] if each["id"] == "frame-4")
    assert frame["export"] == {"file": "figures/figure-1.svg", "format": "svg", "dpi": 300}
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", container(folder, [], converter=False))
    with pytest.raises(Exception, match="clank latex setup"):
        boards.export("paper", "figures/fig", frame="frame-4")
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:
        refused = client.post("/api/v1/agents/boards/export", headers=HEADERS,
                              json={"workspace": "paper", "board": "figures/fig", "frame": "frame-9"})  # fmt: skip
    assert refused.status_code == 409


def test_a_kept_export_is_made_again_when_the_agent_changes_what_its_frame_shows(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []
    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", container(folder, asked))
    boards = kernel.parts["agents"].boards
    boards.export("paper", "figures/fig", frame="frame-4", keep=True)
    converted = sum(1 for each in asked if each[0] == "rsvg-convert")
    noted = boards.add("paper", "figures/fig", "note", {"text": "check the fit"}, {"x": 1200, "y": 80})
    assert sum(1 for each in asked if each[0] == "rsvg-convert") == converted, "a note outside: nothing to make again"
    assert "again" not in noted["said"]
    changed = boards.update("paper", "figures/fig", "latex-3", {"source": "T_1"})
    assert sum(1 for each in asked if each[0] == "rsvg-convert") == converted + 1
    assert "Made frame-4's export figures/figure-1.pdf again" in changed["said"]
    once = boards.export("paper", "figures/fig", frame="frame-4", keep=False)
    assert "export" not in next(
        each for each in boards.read("paper", "figures/fig")["items"] if each["id"] == "frame-4"
    )
    assert once["file"] == "figures/figure-1.pdf"
