"""Design 0020 §3: the TeX layer's helper is where the mount of Clank's programs (/opt/clank, decision 0142) cannot hide
it, so a workspace with the TeX layer builds its documents; a container whose layer lacks the helper is said to need a
new layer, not to lack TeX."""

import json
from pathlib import Path, PurePosixPath

from clank.components.agents.latex.building import HELPER, NO_HELPER, Builder
from clank.components.workspaces.sandbox import PROGRAMS, image_folder
from clank.kernel.processes import Answer

LAYER = image_folder().parent / "layers" / "tex"


def test_the_helper_is_copied_to_its_own_folder_outside_the_mounted_one() -> None:
    folder = str(PurePosixPath(HELPER).parent)
    assert folder != PROGRAMS, "the mount would hide it"
    assert not folder.startswith(PROGRAMS + "/"), "the mount would hide it"
    dockerfile = (LAYER / "Dockerfile").read_text(encoding="utf-8")
    assert f"COPY latex_build.py {folder}/" in dockerfile
    assert (LAYER / PurePosixPath(HELPER).name).is_file()
    assert not (image_folder() / PurePosixPath(HELPER).name).exists(), "the mounted folder does not carry it either"


def test_a_container_without_the_helper_is_told_its_layer_is_old_not_that_tex_is_missing(tmp_path: Path) -> None:
    gone = Answer(2, "", f"python3: can't open file '{HELPER}': [Errno 2] No such file or directory")
    builder = Builder(lambda *args: gone)
    said = builder._said("paper", {"mode": "build"})
    assert said["unbuilt"] == NO_HELPER.format(workspace="paper")
    builder = Builder(lambda *args: Answer(0, json.dumps({"missing": True}), ""))
    assert "TeX is not in paper's container" in builder._said("paper", {"mode": "build"})["unbuilt"]
