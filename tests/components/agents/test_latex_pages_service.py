"""Design 0020 §10, through the service: `POST /agents/latex/pages` renders a PDF of a workspace's folder as pages to
mark up (refused for a folder with no workspace, or a path that is no PDF of it), and a page marked up and sent goes
to the agent as a page of its PDF, each mark with its source line and the words under it."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents.test_annotations import workspace
from tests.components.agents.test_latex_pages import Helper
from tests.components.agents.test_sessions import OpenCode, kernel, opencode  # noqa: F401 (fixtures)

YOU = Actor(kind="user", via="vscode")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    (folder / "main.pdf").write_bytes(b"%PDF-1.7\n")
    return folder


def test_the_route_renders_a_pdfs_pages_and_refuses_what_it_cannot(
    kernel: Kernel,  # noqa: F811
    paper: Path,
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(paper)}, base=None, actor=YOU)
    kernel.parts["agents"].pages.run = Helper(paper)
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        shown = service.post("/api/v1/agents/latex/pages", headers=AUTH, json={"folder": str(paper), "pdf": "main.pdf"})
        assert shown.status_code == 200, shown.text
        assert shown.json()["pages"] == [{"number": 1, "image": ".clank/latex/pages/main/page-1.png"}]
        missing = service.post("/api/v1/agents/latex/pages", headers=AUTH, json={"folder": str(paper), "pdf": "x.pdf"})
        assert missing.status_code == 409
        assert missing.json()["error"]["message"] == "x.pdf is not a file of the folder"
        nowhere = service.post("/api/v1/agents/latex/pages", headers=AUTH, json={"folder": str(paper.parent),
                                                                                "pdf": "main.pdf"})  # fmt: skip
        assert nowhere.status_code == 409
        assert "has no Clank workspace" in nowhere.json()["error"]["message"]


def test_a_marked_up_page_reaches_the_agent_as_a_page_of_its_pdf(
    kernel: Kernel,  # noqa: F811
    opencode: int,  # noqa: F811
    paper: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace(kernel, paper, opencode, monkeypatch)
    agents = kernel.parts["agents"]
    agents.pages.run = Helper(paper)
    agents.pages.dpi = 144
    agents.annotations.reads_images = lambda: False
    agents.pages.render("paper", paper, "main.pdf")
    image = paper / ".clank" / "latex" / "pages" / "main" / "page-1.png"
    data = _tiny_png()
    image.write_bytes(data)
    strike = {"n": 1, "kind": "strike", "color": "#e5484d", "points": [[240, 212], [420, 212]]}
    copy = "data:image/png;base64," + base64.b64encode(data).decode()
    sent = agents.annotations.send(str(paper), str(image), [strike], "Cut this.", copy, actor=YOU)
    assert sent["text"].startswith(
        "About page 1 of `main.pdf`: my marked-up copy is `.clank/annotations/page-1-1.png`."
    )
    assert "- Mark 1 (red strike) on page 1, from paper/intro.tex line 12: through 'clearly optimal.'." in sent["text"]
    assert sent["text"].endswith("\n\nCut this.")


def _tiny_png() -> bytes:
    """A 1 by 1 PNG."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
