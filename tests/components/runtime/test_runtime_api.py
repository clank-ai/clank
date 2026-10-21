"""Design 0003 §8 and the M1.5 plan's task 1: what clients read of the runtime: the newest launches; the GPU's memory
now; a preset's plan, with its command line, its memory estimate and fit now, and each option with its value, where
the value comes from (design 0001 §3.5), what the engine receives for it or why nothing, and what it does; for a preset
that cannot be planned, its options and why it cannot; and a host is made once, so a WSL host's home is asked once."""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import anyio
import pytest
from fastapi.testclient import TestClient

from clank.components.runtime.gpu import GpuMemory
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def get(http: TestClient, path: str) -> Any:
    answer = http.get(f"/api/v1/{path}", headers=AUTH)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_presets_plan_says_its_command_line_memory_and_fit_and_where_each_value_comes_from(
    rig: Rig, http: TestClient
) -> None:
    rig.gpu[:] = [GpuMemory(16303, 2041)]
    plan = get(http, f"runtime/presets/{quote('fake KVMem')}/plan")
    assert (plan["preset"], plan["title"], plan["problem"]) == ("fake-kvmem", "fake KVMem", None)
    assert " -c 8192 " in plan["command_line"]
    assert plan["memory"]["total_mib"] == 1105
    assert (plan["fit"]["verdict"], plan["fit"]["lines"][-1]) == ("fits", "FITS: 13,157 MiB to spare")
    options = {option["key"]: option for option in plan["options"]}
    assert (options["context"]["value"], options["context"]["source"], options["context"]["gives"]) == (
        8192, "preset", ["-c", "8192"]
    )  # fmt: skip
    assert (options["thinking"]["source"], options["thinking"]["gives"]) == ("Clank's default", ["--enable-thinking"])
    assert (options["batch"]["gives"], options["batch"]["left_out"]) == ([], "the engine's own default")
    assert options["vision.max_tokens"]["value"] is None
    assert options["context"]["help"]
    assert options["context"]["maps_to"] == "-c {value}"


def test_a_preset_that_cannot_be_planned_still_shows_its_options_and_says_why(rig: Rig, http: TestClient) -> None:
    rig.preset("elsewhere", {"title": "elsewhere", "engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1",
                             "model": "tiny", "host": "nowhere", "options": {"context": 4096}})  # fmt: skip
    plan = get(http, "runtime/presets/elsewhere/plan")
    assert plan["problem"] == "KVMem/llama.cpp v0.16.0-rc1 is not installed on nowhere: " + (
        "`clank engine install kvmem-llamacpp --version v0.16.0-rc1`"
    )
    assert (plan["command_line"], plan["memory"], plan["fit"]) == (None, None, None)
    assert {option["key"] for option in plan["options"]} >= {"context", "kvmem.budget", "vision"}
    assert http.get("/api/v1/runtime/presets/nothing/plan", headers=AUTH).status_code == 404


@pytest.mark.anyio
async def test_the_launches_come_newest_first_and_the_gpu_as_it_is_now(rig: Rig, http: TestClient) -> None:
    rig.gpu[:] = [GpuMemory(16303, 2041)]
    async with rig.kernel.operations.running():
        for preset in ("fake KVMem", "fake KVMem small"):
            started = await rig.kernel.operations.start(
                "runtime.switch" if preset == "fake KVMem small" else "runtime.load", {"preset": preset}, actor=YOU
            )
            with anyio.fail_after(60):
                done = await rig.kernel.operations.wait(started.id)
            assert done.status == "done", done.error
        stopping = await rig.kernel.operations.start("runtime.unload", {}, actor=YOU)
        unloaded = await rig.kernel.operations.wait(stopping.id)
        assert unloaded.status == "done", unloaded.error
    launches = get(http, "runtime/launches?limit=1")
    assert [(launch["id"], launch["preset"]) for launch in launches] == [(2, "fake-kvmem-small")]
    assert [launch["id"] for launch in get(http, "runtime/launches")] == [2, 1]
    assert get(http, "runtime/gpu") == {"total_mib": 16303, "used_mib": 2041, "free_mib": 14262}
    rig.gpu[:] = [None]
    assert get(http, "runtime/gpu") is None


def test_a_host_is_made_once_and_again_when_its_record_changes(rig: Rig) -> None:
    folder = rig.kernel.home.config / "hosts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ubuntu.json").write_text(json.dumps({"schema": "host/1", "adapter": "wsl", "distro": "Ubuntu"}) + "\n")
    rig.kernel.settings.reload_changed()
    assert rig.runtime.host("ubuntu") is rig.runtime.host("ubuntu")
    first = rig.runtime.host("ubuntu")
    (folder / "ubuntu.json").write_text(json.dumps({"schema": "host/1", "adapter": "wsl", "distro": "Debian"}) + "\n")
    rig.kernel.settings.reload_changed()
    assert rig.runtime.host("ubuntu") is not first


def test_the_models_say_where_each_file_is_on_each_host_whose_engine_reads_it(rig: Rig, http: TestClient) -> None:
    [tiny] = get(http, "runtime/models")
    assert (tiny["id"], tiny["name"]) == ("tiny", "Tiny")
    files = {(file["format"], file["role"]): file for file in tiny["files"]}
    weights = files[("gguf", "weights")]
    assert (weights["path"], weights["size"], weights["repository"]) == ("tiny.gguf", 12, "tests/tiny")
    [where] = weights["hosts"]
    assert (where["host"], where["how"], where["present"]) == ("local", "adopted", True)
    assert where["path"] == str(rig.models / "tiny.gguf")
    assert [where["host"] for where in files[("gguf", "projector")]["hosts"]] == ["local"]


def test_a_preset_says_what_it_needs_on_its_host_and_whether_each_is_there(rig: Rig) -> None:
    """Design 0006 §6: the Completion page's l installs and downloads what this says is missing."""
    ready = rig.runtime.needs("fake-kvmem")
    assert (ready["host"], ready["engine"]["installed"], ready["model"]["downloaded"]) == ("local", True, True)
    rig.preset("fake-llamacpp", {"title": "fake llama.cpp", "engine": "llamacpp", "engine_version": "b11588",
                                 "model": "tiny", "slot": "fast", "options": {}})  # fmt: skip
    missing = rig.runtime.needs("fake-llamacpp")
    assert missing["host"] == "local", "the host of an installed engine that reads the same format"
    assert (missing["engine"]["installed"], missing["engine"]["recipe"]) == (False, True)
    assert (missing["model"]["format"], missing["model"]["downloaded"]) == ("gguf", True), "the file adopted there"
