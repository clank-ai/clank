"""Design 0008 §5: a figure the owner marked up goes to the workspace's agent, run against a fake OpenCode server: each
mark in the figure's own terms (from the geometry Matplotlib's save left in the folder), the owner's words, and the
marked-up copy as an image when the agent's model reads images, else what the vision model read in it (design 0008
§7); it is kept in the folder's `.clank/annotations/` (out
of git) and recorded. It goes to the session most recently active; nothing is sent while no agent runs, for a figure
outside the folder, or with neither a mark nor a word."""

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from clank.components.agents.annotations import AnnotationError
from clank.components.workspaces.sandbox import names
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.processes import Answer, background_flags
from tests.components.agents.test_sessions import BRIDGE, OpenCode, kernel, opencode  # noqa: F401 (fixtures)
from tests.components.workspaces.test_figure_geometry import pixel, run
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="vscode")


def workspace(kernel: Kernel, folder: Path, port: int, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Workspace paper on `folder`, its container running, its bridge (run here) reaching the fake OpenCode."""
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    monkeypatch.setenv("CLANK_BRIDGE_PORTS", f"{port}-{port}")

    def inside(argv: list[str], given: bytes | None) -> Answer:
        done = subprocess.run([sys.executable, str(BRIDGE), *argv[2:]], input=given or b"", capture_output=True,
                              timeout=60, creationflags=background_flags())  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(), done.stderr.decode())

    platform.inside = inside


@pytest.fixture
def figure(tmp_path: Path) -> Path:
    """A figure Matplotlib saved in the folder, with its geometry beside the folder's notes."""
    folder = tmp_path / "paper"
    (folder / "figs").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    done = run(folder, str(tmp_path / "elsewhere"))
    assert done.returncode == 0, done.stderr
    return folder / "figs" / "plot.png"


def test_a_marked_up_figure_reaches_the_agent_with_its_marks_in_words_and_the_copy_attached(
    kernel: Kernel,  # noqa: F811
    opencode: int,  # noqa: F811
    figure: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = figure.parents[1]
    workspace(kernel, folder, opencode, monkeypatch)
    geometry = json.loads((folder / ".clank" / "figures" / "figs" / "plot.png.json").read_text(encoding="utf-8"))
    x, y = pixel(geometry, 0, 2.5, 3.0)
    box = {"n": 1, "kind": "box", "color": "#e5484d", "points": [[x - 15, y - 15], [x + 15, y + 15]]}
    copy = "data:image/png;base64," + base64.b64encode(figure.read_bytes()).decode()
    annotations = kernel.parts["agents"].annotations
    annotations.reads_images = lambda: True
    sent = annotations.send(str(folder), str(figure), [box], "Make the dot bigger.", copy, actor=YOU)
    assert (sent["workspace"], sent["port"], sent["session"]) == ("paper", opencode, "ses_1")
    assert (sent["annotation"], sent["attached"]) == (".clank/annotations/plot-1.png", True)
    path, body = OpenCode.sent[-1]
    assert path == "/session/ses_1/prompt_async"
    text, image = body["parts"]
    assert text["text"].startswith("About the figure `figs/plot.png`: my marked-up copy is ")
    assert 'Mark 1 (red box) on "MSD vs time" (left plot): time 2.' in text["text"]
    assert text["text"].endswith("\n\nMake the dot bigger.")
    assert image == {"type": "file", "mime": "image/png", "url": "file:///workspace/.clank/annotations/plot-1.png",
                     "filename": "plot-1.png"}  # fmt: skip
    kept = folder / ".clank" / "annotations"
    assert (kept / ".gitignore").read_text(encoding="utf-8") == "*\n"
    record = json.loads((kept / "plot-1.json").read_text(encoding="utf-8"))
    assert (record["figure"], record["geometry"], record["message"]) == ("figs/plot.png", True, "Make the dot bigger.")
    [event] = kernel.events.after(0, types=["agents.annotated"])
    assert event.data["marks"] == 1
    annotations.reads_images = lambda: False
    read: list[bytes] = []

    def reading(image: bytes, question: str) -> str:
        read.append(image)
        return "1. circles the red dot near (2.5, 3)."

    annotations.read_image = reading
    again = annotations.send(str(folder), str(figure), [box], "Now a log scale, please.", copy, actor=YOU)
    assert (again["annotation"], again["attached"]) == (".clank/annotations/plot-2.png", False)
    assert [part["type"] for part in OpenCode.sent[-1][1]["parts"]] == ["text"], "no image for a model without sight"
    assert "What the vision model sees at my marks:\n1. circles the red dot near (2.5, 3)." in again["text"]
    assert read == [figure.read_bytes()], "the vision model read the marked-up copy"


def test_an_annotation_is_refused_with_the_reason_when_it_cannot_be_sent(
    kernel: Kernel,  # noqa: F811
    opencode: int,  # noqa: F811
    figure: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = figure.parents[1]
    workspace(kernel, folder, opencode, monkeypatch)
    annotations = kernel.parts["agents"].annotations
    copy = "data:image/png;base64," + base64.b64encode(figure.read_bytes()).decode()
    mark = {"n": 1, "kind": "pen", "color": "#e5484d", "points": [[10, 10], [20, 20]]}
    with pytest.raises(AnnotationError, match="is not in the folder of paper"):
        annotations.send(str(folder), str(tmp_path / "elsewhere" / "outside.png"), [mark], "", copy, actor=YOU)
    with pytest.raises(AnnotationError, match="mark something on the figure or write what to do"):
        annotations.send(str(folder), str(figure), [], "  ", copy, actor=YOU)
    with pytest.raises(AnnotationError, match="has no Clank workspace"):
        annotations.send(str(tmp_path), str(figure), [mark], "", copy, actor=YOU)
    monkeypatch.setattr(kernel.parts["agents"].sessions, "servers", lambda workspace: [])
    with pytest.raises(AnnotationError, match=r"no agent runs in paper: start it"):
        annotations.send(str(folder), str(figure), [mark], "", copy, actor=YOU)
    assert not (folder / ".clank" / "annotations").exists(), "nothing kept for what was not sent"
