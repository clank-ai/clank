"""Design 0020 §3: a workspace's record may name image layers (`tex` so far); its image is then Clank's sandbox image
with each layer built on it, from the layer's folder with the base image's tag as the build argument `BASE`, tagged by
the base's tag and the layers' files (`layered_tag`). Opening it builds the sandbox image and then the layered one,
when missing, asked first with what the layers add; its container is made from the layered image, the edge from the
sandbox image; the next opening does nothing again. Whether a container runs the current image is judged against its
workspace's own. `POST /workspaces/{name}/layers` adds a layer to a workspace's record or takes it away; an unknown
layer is refused."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import LAYERS, image_tag, layer_folder, layered_tag, names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "work" / "paper"
    found.mkdir(parents=True)
    return found


async def run(kernel: Kernel, kind: str, params: dict[str, Any]) -> Operation:
    started = await kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(30):
        while True:
            current = kernel.operations.get(started.id)
            if (current.status == "waiting" and current.waiting_on) or current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.01)


def test_the_layered_tag_is_the_base_with_no_layer_and_names_its_layers_otherwise() -> None:
    assert LAYERS == ("tex",)
    assert layered_tag([]) == image_tag()
    tagged = layered_tag(["tex"])
    assert tagged.startswith("clank-sandbox-tex:")
    assert tagged != image_tag()
    assert layered_tag(["tex", "tex"]) == tagged, "a layer named twice is one layer"
    assert (layer_folder("tex") / "Dockerfile").is_file()
    with pytest.raises(ValueError, match="no image layer 'lean': the layers are tex"):
        layered_tag(["lean"])


def test_the_tex_layer_builds_on_the_base_and_holds_what_the_checks_need() -> None:
    text = (layer_folder("tex") / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG BASE" in text
    assert "FROM ${BASE}" in text
    for needed in ("latexmk", "latexdiff", "biber", "poppler-utils", "texlive-latex-extra", "texlive-science"):
        assert needed in text, needed
    assert text.rstrip().endswith("USER agent"), "the agent runs as itself again"


@pytest.mark.anyio
async def test_opening_a_workspace_with_the_tex_layer_builds_it_on_the_base_and_runs_it(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(folder), "layers": ["tex"]}, base=None, actor=YOU)
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert done.status == "done", done.error
        before = list(platform.calls)
        again = await run(kernel, "workspaces.open", {"folder": str(folder)})
        assert again.status == "done", again.error
    home = names(kernel.home.id)
    base, tex = image_tag(), layered_tag(["tex"])
    assert before[:2] == [f"build {image_tag()}", f"build {tex}"]
    assert platform.build_args[tex] == {"BASE": base}
    assert platform.build_folders[tex] == str(layer_folder("tex"))
    assert platform.specs[home.container("paper")].image == tex
    assert platform.specs[home.edge].image == base, "the edge needs no TeX"
    assert (done.result or {})["image"] == tex
    assert platform.calls == before, "nothing is built twice"
    assert kernel.parts["workspaces"].runs_current_image("paper") is True


@pytest.mark.anyio
async def test_the_layers_build_is_asked_first_saying_what_it_adds(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.images.add(image_tag())
    kernel.settings.write("workspace", "paper", {"path": str(folder), "layers": ["tex"]}, base=None, actor=YOU)
    async with kernel.operations.running():
        waiting = await run(kernel, "workspaces.open", {"folder": str(folder)})
        question = kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Build the TeX layer for paper?"
        assert "TeX Live" in question.detail
        assert "about 2 GB" in question.detail
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        with anyio.fail_after(30):
            canceled = await kernel.operations.wait(waiting.id)
    assert canceled.status == "canceled"
    assert not [call for call in platform.calls if call.startswith(("build", "run"))]


def test_a_layer_is_added_to_a_workspace_and_taken_away_through_the_api(kernel: Kernel, folder: Path) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    app = create_app(kernel, token="t", port=7720)
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        added = service.post("/api/v1/workspaces/paper/layers", headers=AUTH, json={"layer": "tex"})
        assert added.status_code == 200, added.text
        assert added.json()["layers"] == ["tex"]
        assert "open the workspace again" in added.json()["said"]
        assert kernel.settings.get("workspace", "paper").record.model_dump()["layers"] == ["tex"]
        unknown = service.post("/api/v1/workspaces/paper/layers", headers=AUTH, json={"layer": "lean"})
        assert unknown.status_code == 409
        assert "the layers are tex" in unknown.json()["error"]["message"]
        taken = service.post("/api/v1/workspaces/paper/layers", headers=AUTH, json={"layer": "tex", "added": False})
        assert taken.json()["layers"] == []
