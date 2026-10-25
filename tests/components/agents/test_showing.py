"""Design 0018 §7.1: the service opens files the agent names in the owner's VS Code window. Each path is named from the
workspace's folder or under `/workspace`; the files of the folder are opened (the event `agents.shown`, with the
workspace, its folder, the files and why, which the window follows), and the answer names each path that is not a file
of the folder (outside it, or missing), and tells the model the owner looks at the files themselves. With no file of
the folder, too many, no workspace of that name, or no VS Code window following the service, nothing is opened and the
answer says why. Through the API, `POST /agents/show` is the agent's: its event's actor is the agent's session."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clank.components.agents.showing import AGENT, MOST, ShowError
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents.test_sessions import kernel  # noqa: F401 (fixture)

YOU = Actor(kind="user", via="vscode")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}


@pytest.fixture
def folder(kernel: Kernel, tmp_path: Path) -> Path:  # noqa: F811
    """Workspace paper on a folder with a figure, a PDF and notes; a file beside the folder."""
    root = tmp_path / "paper"
    (root / "plots").mkdir(parents=True)
    (root / "plots" / "residual.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "paper.pdf").write_bytes(b"%PDF-1.7\n")
    (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not the folder's\n", encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(root)}, base=None, actor=YOU)
    return root


def test_the_files_named_are_opened_as_an_event_the_window_follows(kernel: Kernel, folder: Path) -> None:  # noqa: F811
    showing = kernel.parts["agents"].showing
    shown = showing.show(
        "paper", ["plots/residual.png", "/workspace/paper.pdf", "notes.md"], "The plots you asked for.", windows=True
    )
    assert shown["files"] == ["plots/residual.png", "paper.pdf", "notes.md"]
    assert shown["missing"] == []
    said = shown["said"]
    assert said.startswith("Opened plots/residual.png, paper.pdf and notes.md in the owner's VS Code window")
    assert "The owner looks at them themselves" in said
    assert "do not read, describe or check them unless the owner asks" in said
    [event] = kernel.events.after(0, types=["agents.shown"])
    assert event.actor == AGENT
    assert event.data == {
        "workspace": "paper",
        "folder": str(folder),
        "files": ["plots/residual.png", "paper.pdf", "notes.md"],
        "why": "The plots you asked for.",
    }


def test_paths_outside_the_folder_or_missing_are_named_and_the_rest_are_opened(
    kernel: Kernel,  # noqa: F811
    folder: Path,
) -> None:
    showing = kernel.parts["agents"].showing
    shown = showing.show(
        "paper", ["../secret.txt", "plots/residual.png", "plots/old.png", "C:/x.png"], "", windows=True
    )
    assert shown["files"] == ["plots/residual.png"]
    assert shown["missing"] == ["../secret.txt", "plots/old.png", "C:/x.png"]
    assert "Not opened, not files of the folder: ../secret.txt, plots/old.png, C:/x.png." in shown["said"]
    [event] = kernel.events.after(0, types=["agents.shown"])
    assert event.data["files"] == ["plots/residual.png"]


def test_nothing_is_opened_with_no_file_too_many_no_workspace_or_no_window(
    kernel: Kernel,  # noqa: F811
    folder: Path,
) -> None:
    showing = kernel.parts["agents"].showing
    with pytest.raises(ShowError, match="name the files to open"):
        showing.show("paper", [], "", windows=True)
    with pytest.raises(ShowError, match=r"none of these is a file of the folder: plots/old\.png"):
        showing.show("paper", ["plots/old.png"], "", windows=True)
    with pytest.raises(ShowError, match=f"at most {MOST} files at once"):
        showing.show("paper", ["notes.md"] * (MOST + 1), "", windows=True)
    with pytest.raises(ShowError, match="there is no workspace 'thesis'"):
        showing.show("thesis", ["notes.md"], "", windows=True)
    with pytest.raises(ShowError) as refused:
        showing.show("paper", ["notes.md"], "", windows=False)
    assert str(refused.value) == (
        "No VS Code window follows Clank now, so nothing was opened: tell the owner where the files are (notes.md)."
    )
    assert kernel.events.after(0, types=["agents.shown"]) == []


def test_the_route_is_the_agents_and_knows_whether_a_vs_code_window_follows(
    kernel: Kernel,  # noqa: F811
    folder: Path,
) -> None:
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        body = {"workspace": "paper", "paths": ["notes.md"], "why": "asked for"}
        alone = service.post("/api/v1/agents/show", headers=AUTH, json=body)
        assert alone.status_code == 409
        assert alone.json()["error"]["message"].startswith("No VS Code window follows Clank now")
        app.state.streams[1] = "vscode"
        opened = service.post("/api/v1/agents/show", headers=AUTH, json=body)
        assert opened.status_code == 200, opened.text
        assert opened.json()["files"] == ["notes.md"]
    [event] = kernel.events.after(0, types=["agents.shown"])
    assert event.actor == AGENT
