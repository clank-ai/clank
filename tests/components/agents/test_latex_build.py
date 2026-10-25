"""Design 0020 §3: LaTeX Workshop builds in the container. `POST /agents/latex/build` builds the document a `.tex` file
of a workspace belongs to (its root) in the workspace's container, and keeps its PDF, its log and its SyncTeX file
beside the root's `.tex`, SyncTeX's paths made this machine's (so LaTeX Workshop goes from the PDF to the source and
back); it answers whether it built, where the PDF is, its errors and its undefined references, citations and labels
defined twice. A file in no workspace, or no `.tex`, is refused. Clank's VS Code window gets a LaTeX Workshop recipe
that runs `clank latex build` on the root, first, unless the owner has recipes of their own."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.vscode import settings_text
from clank.components.workspaces.sandbox import layer_folder
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.processes import Answer
from tests.components.agents.test_sessions import kernel  # noqa: F401 (fixture)

YOU = Actor(kind="user", via="cli")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
RECORDED = Path(__file__).parents[2] / "fixtures" / "latex"


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    folder = tmp_path / "work"
    (folder / "paper" / "sections").mkdir(parents=True)
    (folder / "paper" / "main.tex").write_text("\\documentclass{article}\n\\input{sections/intro}\n", encoding="utf-8")
    (folder / "paper" / "sections" / "intro.tex").write_text("Hello.\n", encoding="utf-8")
    return folder


def test_a_tex_file_builds_its_document_in_the_container_kept_beside_it(kernel: Kernel, paper: Path) -> None:  # noqa: F811
    kernel.settings.write("workspace", "work", {"path": str(paper)}, base=None, actor=YOU)
    asked: list[dict[str, Any]] = []

    def helper(workspace: str, argv: list[str], given: bytes, timeout: float) -> Answer:
        asked.append(json.loads(given))
        log = (RECORDED / "warn.log").read_text(encoding="utf-8", errors="replace")
        return Answer(0, json.dumps({"built": True, "log": log, "seconds": 2.5, "kept": {"pdf": "paper/main.pdf"}}), "")

    kernel.parts["agents"].review.latex.builder.run = helper
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        intro = paper / "paper" / "sections" / "intro.tex"
        built = service.post("/api/v1/agents/latex/build", headers=AUTH, json={"file": str(intro)})
        assert built.status_code == 200, built.text
        answer = built.json()
        assert (answer["built"], answer["root"], answer["pdf"]) == (
            True,
            "paper/main.tex",
            str(paper / "paper" / "main.pdf"),
        )
        assert answer["warnings"] == ["undefined reference sec:missing", "undefined citation invented2025",
                                      "label defined twice sec:intro"]  # fmt: skip
        outside = service.post("/api/v1/agents/latex/build", headers=AUTH, json={"file": str(paper.parent / "x.tex")})
        assert outside.status_code == 409
        assert "is in no Clank workspace" in outside.json()["error"]["message"]
    [request] = asked
    assert (request["mode"], request["root"], request["file"], request["text"]) == ("build", "paper/main.tex",
                                                                                   "paper/main.tex", None)  # fmt: skip
    assert request["keep"] == "paper"
    assert request["synctex_root"] == paper.as_posix()
    assert request["log"] is True


def test_the_helper_makes_synctexs_paths_this_machines() -> None:
    spec = importlib.util.spec_from_file_location("latex_build", layer_folder("tex") / "latex_build.py")
    assert spec is not None
    assert spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    text = "SyncTeX Version:1\nInput:1:/tmp/clank-latex-ab12/paper/./main.tex\nInput:2:/tmp/clank-latex-ab12/x.tex\n"
    assert helper.rewritten(text, "/tmp/clank-latex-ab12", "D:/research/work") == (
        "SyncTeX Version:1\nInput:1:D:/research/work/paper/./main.tex\nInput:2:D:/research/work/x.tex\n"
    )


def test_the_window_builds_latex_with_clank_unless_the_owner_has_recipes_of_their_own() -> None:
    written = json.loads(settings_text(None, clank="C:/tools/clank.exe") or "")
    [tool] = written["latex-workshop.latex.tools"]
    assert tool == {
        "name": "clank",
        "command": "C:/tools/clank.exe",
        "args": ["latex", "build", "%DOC_EXT%"],
        "env": {},
    }
    assert written["latex-workshop.latex.recipes"][0] == {"name": "Clank: in the container", "tools": ["clank"]}
    owners = json.loads(settings_text(json.dumps({"latex-workshop.latex.recipes": []}), clank="clank") or "")
    assert owners["latex-workshop.latex.recipes"] == [], "the owner's own recipes are kept"
