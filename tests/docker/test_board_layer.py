"""Design 0022 §6 and §7, run in the TeX layer's image on this machine's Docker (`-m docker`; skipped when the image
is not built): a pgfplots drawing on a board is compiled by pdfLaTeX and made SVG by `pdftocairo`, its glyphs
flattened and its size its own; and a frame exports as a vector PDF made by librsvg, the figure's lines and the LaTeX
as paths, not pixels."""

import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import layered_tag
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer, background_flags
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.docker
YOU = Actor(kind="user", via="console")
PLOT = (
    "\\begin{tikzpicture}\\begin{axis}[width=6cm,height=4cm,xlabel={$t$}]"
    "\\addplot[blue,domain=0:6,samples=40]{exp(-0.3*x)*cos(deg(2*x))};\\end{axis}\\end{tikzpicture}"
)
FIGURE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" viewBox="0 0 200 150">'
    '<path d="M 10 140 L 100 20 L 190 140" stroke="#c00" fill="none" stroke-width="3"/></svg>'
)


@pytest.fixture
def kernel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Kernel]:
    image = layered_tag(["tex"])
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False).returncode != 0:
        pytest.skip(f"the TeX layer's image {image} is not built here: clank latex setup builds it")
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    home = Home(tmp_path / "clank-home")
    home.ensure()
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 26, 12, 0, tzinfo=UTC)), registry.components())
    folder = tmp_path / "paper"
    (folder / "figures").mkdir(parents=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)

    def run(workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30.0) -> Answer:
        done = subprocess.run(
            ["docker", "run", "--rm", "-i", "--network", "none", "-v", f"{folder}:/workspace", "-w", "/workspace",
             image, *argv],
            input=input or b"", capture_output=True, timeout=timeout + 60, check=False,
            creationflags=background_flags(),
        )  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(errors="replace"), done.stderr.decode(errors="replace"))

    monkeypatch.setattr(kernel.parts["workspaces"], "run_in", run)
    yield kernel
    kernel.close()


def test_a_drawing_is_compiled_and_a_frame_exports_as_a_vector_pdf(kernel: Kernel, tmp_path: Path) -> None:
    folder = tmp_path / "paper"
    (folder / "figures" / "a.svg").write_text(FIGURE, encoding="utf-8")
    boards = kernel.parts["agents"].boards
    boards.new("paper", "fig", folder="figures", title="Fig")
    boards.add("paper", "figures/fig", "figure", {"file": "figures/a.svg", "caption": "(a) 50% of $x_1$"})
    drawn = boards.add("paper", "figures/fig", "latex", {"source": PLOT, "mode": "compiled"}, {"right_of": "fig-1"})
    assert "It builds with TeX" in drawn["said"], drawn["said"]
    boards.add("paper", "figures/fig", "latex", {"source": "T_0 = 2\\pi\\sqrt{L/g}"}, {"below": "fig-1"})
    boards.add("paper", "figures/fig", "frame", {"name": "Figure 1", "around": ["fig-1", "latex-2", "latex-3"]})
    board = json.loads((folder / "figures" / "fig.board").read_text(encoding="utf-8"))
    plot = next(each for each in board["items"] if each["id"] == "latex-2")
    assert 200 < plot["w"] < 320, "a 6 cm plot, at its own size"

    made = boards.export("paper", "figures/fig", frame="frame-4")
    assert made["problems"] == []
    pdf = folder / made["file"]
    assert pdf.read_bytes().startswith(b"%PDF")
    images = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{folder}:/workspace", "-w", "/workspace", layered_tag(["tex"]),
         "pdfimages", "-list", made["file"]],
        capture_output=True, timeout=120, check=False, creationflags=background_flags(),
    ).stdout.decode()  # fmt: skip
    assert len(images.strip().splitlines()) == 2, f"no pictures in it, only paths: {images}"
    png = boards.export("paper", "figures/fig", frame="frame-4", format="png", dpi=150)
    assert (folder / png["file"]).read_bytes().startswith(b"\x89PNG")
