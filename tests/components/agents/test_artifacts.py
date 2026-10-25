"""Design 0021 §5: artifacts, pages the agent makes for the owner. Making one copies the files the agent named into the
artifact's next version (`.clank/artifacts/<name>/v<n>/`), keeping their layout from their common folder, its entry page
first; `artifact.json` keeps its title, kind and every version (when, its entry, its files, its note, the session that
made it); `agents.artifact_made` is recorded. A Markdown artifact gets Clank's page that renders it with the kept
libraries, math included, and so does an SVG one. A name, a kind, a file not the folder's, too many or too large files,
or an entry page that names the network, are refused, saying why. The owner's comment on a version goes to the session
that made it, in one message naming the artifact and its version, and `agents.artifact_commented` is recorded."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents.artifacts import ArtifactError, Artifacts
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
PAGE = """<!doctype html><html><head><script src="clank-lib/plotly.min.js"></script></head>
<body><div id="plot"></div><script>
fetch("../results/sweep.json").then(r => r.json()).then(d => Plotly.newPlot("plot", d));
</script></body></html>
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
    (folder / "report").mkdir(parents=True)
    (folder / "results").mkdir()
    (folder / "report" / "index.html").write_text(PAGE, encoding="utf-8")
    (folder / "results" / "sweep.json").write_text('[{"x": [1, 2], "y": [3, 4]}]', encoding="utf-8")
    (folder / "notes.md").write_text("# Notes\n\nThe energy is $E = mc^2$.\n", encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    return folder


def artifacts_of(kernel: Kernel) -> Artifacts:
    found: Artifacts = kernel.parts["agents"].artifacts
    return found


def test_making_one_copies_its_files_as_a_version_keeping_their_layout_and_records_it(
    kernel: Kernel, folder: Path
) -> None:
    made = artifacts_of(kernel).make(
        "paper", "sweep", "Sweep results", "html", ["report/index.html", "/workspace/results/sweep.json"],
        note="first look", session="ses_1",
    )  # fmt: skip
    version = folder / ".clank/artifacts/sweep/v1"
    assert (version / "report" / "index.html").read_text(encoding="utf-8") == PAGE
    assert (version / "results" / "sweep.json").is_file(), "its relative path still works"
    kept = json.loads((folder / ".clank/artifacts/sweep/artifact.json").read_text(encoding="utf-8"))
    assert (kept["title"], kept["kind"]) == ("Sweep results", "html")
    [first] = kept["versions"]
    assert (first["version"], first["entry"], first["note"], first["session"]) == (1, "report/index.html", "first look",
                                                                                   "ses_1")  # fmt: skip
    assert made["version"] == 1
    assert made["entry"] == ".clank/artifacts/sweep/v1/report/index.html"
    assert "opens in the owner's VS Code window" in made["said"]
    [event] = kernel.events.latest(5, types=["agents.artifact_made"])
    assert event.data["name"] == "sweep"
    assert event.data["folder"] == str(folder)
    again = artifacts_of(kernel).make("paper", "sweep", "Sweep results", "html", ["report/index.html",
                                                                                  "results/sweep.json"])  # fmt: skip
    assert again["version"] == 2
    assert [each["name"] for each in artifacts_of(kernel).list("paper")] == ["sweep"]
    assert len(artifacts_of(kernel).one("paper", "sweep")["versions"]) == 2


def test_a_markdown_or_svg_artifact_gets_clanks_page_that_renders_it(kernel: Kernel, folder: Path) -> None:
    made = artifacts_of(kernel).make("paper", "notes", "Notes", "markdown", ["notes.md"])
    page = (folder / ".clank/artifacts/notes/v1/index.html").read_text(encoding="utf-8")
    assert "clank-lib/marked.min.js" in page
    assert "clank-lib/katex.min.js" in page
    assert "E = mc^2" in page, "its text is in the page, so it also opens as one exported file"
    assert (folder / ".clank/artifacts/notes/v1/notes.md").is_file(), "and kept as written"
    assert made["entry"] == ".clank/artifacts/notes/v1/index.html"
    (folder / "shape.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    drawn = artifacts_of(kernel).make("paper", "shape", "A shape", "svg", ["shape.svg"])
    assert 'src="shape.svg"' in (folder / ".clank/artifacts/shape/v1/index.html").read_text(encoding="utf-8")
    assert drawn["entry"].endswith("v1/index.html")


@pytest.mark.parametrize(
    ("name", "kind", "files", "said"),
    [
        ("Bad Name!", "html", ["report/index.html"], "a name is lowercase letters"),
        ("sweep", "pdf", ["report/index.html"], "a kind is html, markdown or svg"),
        ("sweep", "html", ["../elsewhere.html"], "is not a file of the folder"),
        ("sweep", "html", ["missing.html"], "is not a file of the folder"),
        ("sweep", "html", [], "names no file"),
        ("sweep", "html", ["results/sweep.json"], "its first file is its page"),
    ],
)
def test_what_cannot_be_an_artifact_is_refused_saying_why(
    kernel: Kernel, folder: Path, name: str, kind: str, files: list[str], said: str
) -> None:
    with pytest.raises(ArtifactError, match=said):
        artifacts_of(kernel).make("paper", name, "A title", kind, files)


def test_a_page_that_names_the_network_is_refused(kernel: Kernel, folder: Path) -> None:
    (folder / "report" / "online.html").write_text(
        '<script src="https://cdn.example.org/lib.js"></script>', encoding="utf-8"
    )
    with pytest.raises(ArtifactError, match="names the network"):
        artifacts_of(kernel).make("paper", "online", "Online", "html", ["report/online.html"])


def test_the_owners_comment_goes_to_the_session_that_made_that_version(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = kernel.parts["agents"].sessions
    sent: list[tuple[str, int, str, str]] = []
    monkeypatch.setattr(sessions, "runs", lambda workspace, session: 4096)

    def send(workspace: str, port: int, session: str, text: str, *, actor: Any) -> dict[str, Any]:
        sent.append((workspace, port, session, text))
        return {}

    monkeypatch.setattr(sessions, "send", send)
    artifacts_of(kernel).make("paper", "sweep", "Sweep results", "html", ["report/index.html"], session="ses_1")
    said = artifacts_of(kernel).comment("paper", "sweep", 1, "Use a log scale on y.", actor=YOU)
    [(workspace, port, session, text)] = sent
    assert (workspace, port, session) == ("paper", 4096, "ses_1")
    assert text.startswith("The owner commented on the artifact Sweep results (sweep, version 1)")
    assert "Use a log scale on y." in text
    assert "make_artifact" in text, "how to answer: a new version"
    assert "sent to the session" in said["said"]
    assert kernel.events.latest(5, types=["agents.artifact_commented"])


def test_the_routes_make_list_and_read_artifacts_and_take_the_owners_comment(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    sessions = kernel.parts["agents"].sessions
    monkeypatch.setattr(sessions, "runs", lambda workspace, session: None)
    headers = {"Authorization": "Bearer t"}
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        body = {"workspace": "paper", "name": "sweep", "title": "Sweep", "files": ["report/index.html"]}
        made = http.post("/api/v1/agents/artifacts", json=body, headers=headers).json()
        assert made["version"] == 1
        listed = http.get("/api/v1/agents/artifacts", params={"workspace": "paper"}, headers=headers).json()
        assert [each["name"] for each in listed["artifacts"]] == ["sweep"]
        one = http.get("/api/v1/agents/artifacts/paper/sweep", headers=headers).json()
        assert one["versions"][0]["entry"] == "index.html"
        refused = http.post("/api/v1/agents/artifacts/paper/sweep/comment", json={"version": 1, "text": "log y"},
                            headers=headers)  # fmt: skip
        assert refused.status_code == 409, "no session of the agent's runs to tell"
        assert "start the agent" in refused.json()["error"]["message"]
        bad = http.post("/api/v1/agents/artifacts", json={**body, "files": ["../x.html"]}, headers=headers)
        assert bad.status_code == 409


def test_an_export_is_one_file_with_its_libraries_and_data_inside_that_needs_nothing_else(
    kernel: Kernel, folder: Path
) -> None:
    artifacts = artifacts_of(kernel)
    artifacts.make("paper", "sweep", "Sweep results", "html", ["report/index.html", "results/sweep.json"])
    exported = Path(artifacts.export("paper", "sweep", 1)["file"])
    assert exported == folder / ".clank/artifacts/sweep/export/sweep-v1.html"
    page = exported.read_text(encoding="utf-8")
    assert "clank-lib/" not in page, "the libraries are inside it"
    assert "Plotly" in page
    assert "results/sweep.json" in page, "its data file is inside it, answered when the page fetches it"
    assert "window.fetch" in page
    with pytest.raises(ArtifactError, match="has no version 4"):
        artifacts.export("paper", "sweep", 4)


def test_clank_artifact_lists_a_folders_artifacts_and_exports_the_newest_version(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner
    from fastapi.testclient import TestClient

    from clank.cli import common
    from clank.cli.main import main
    from clank.client import Client
    from clank.kernel.api import create_app

    artifacts_of(kernel).make("paper", "sweep", "Sweep results", "html", ["report/index.html", "results/sweep.json"])
    artifacts_of(kernel).make("paper", "sweep", "Sweep results", "html", ["report/index.html", "results/sweep.json"])
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7727", "t", name="cli", http=http))
        listed = CliRunner().invoke(main, ["artifact", "list", str(folder)])
        exported = CliRunner().invoke(main, ["artifact", "export", "sweep", str(folder)])
    assert listed.exit_code == 0, listed.output
    assert "sweep  Sweep results  (html, 2 versions" in listed.output
    assert exported.exit_code == 0, exported.output
    assert "sweep version 2 as one page" in exported.output
    assert (folder / ".clank/artifacts/sweep/export/sweep-v2.html").is_file()
