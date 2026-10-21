"""Design 0003 §3 and design 0001 §3.4, §3.7: presets are readable files, Clank's own and the user's, each naming its
engine, the engine's version, its model and the options that differ from the defaults; the API lists them and the
engines, and `clank preset list` and `clank preset show` print them, as JSON with `--json`."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.machine import service as machine_service
from clank.components.machine.kinds import MachineProfile
from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.kinds import Preset
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
FAST: dict[str, object] = {
    "schema": "preset/1",
    "title": "fast 64K",
    "engine": "kvmem-llamacpp",
    "engine_version": "v0.16.0-rc1",
    "model": "qwen3.8-27b",
    "options": {"context": 65536, "kvmem.budget": 32768},
    "notes": "Text only, for this desktop.",
}


def write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    write(home.config / "presets" / "fast-64k.json", FAST)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=client))
        yield client


def test_a_preset_file_is_read_with_its_engine_model_and_options(kernel: Kernel) -> None:
    loaded = kernel.settings.get("preset", "fast-64k")
    preset = Preset.model_validate(loaded.record.model_dump())
    assert (preset.title, preset.engine, preset.engine_version, preset.model) == (
        "fast 64K",
        "kvmem-llamacpp",
        "v0.16.0-rc1",
        "qwen3.8-27b",
    )
    assert preset.options == {"context": 65536, "kvmem.budget": 32768}
    assert preset.slot == "main"
    assert loaded.source == "user"


def test_a_preset_with_an_unknown_field_is_refused_naming_its_line(home: Home, clock: FakeClock) -> None:
    write(home.config / "presets" / "odd.json", {**FAST, "engines": "typo"})
    kernel = open_kernel(home, clock, registry.components())
    try:
        problems = [problem for problem in kernel.settings.problems() if problem.path.name == "odd.json"]
    finally:
        kernel.close()
    assert [(problem.field, problem.line) for problem in problems] == [("engines", 12)]


def test_the_api_lists_the_presets_and_the_engines(http: TestClient) -> None:
    presets = http.get("/api/v1/runtime/presets", headers=AUTH).json()
    mine = next(preset for preset in presets if preset["id"] == "fast-64k")
    assert (mine["title"], mine["engine"], mine["source"]) == ("fast 64K", "kvmem-llamacpp", "user")
    assert http.get("/api/v1/runtime/presets/fast-64k", headers=AUTH).json()["options"]["context"] == 65536
    engines = http.get("/api/v1/runtime/engines", headers=AUTH).json()
    assert [engine["name"] for engine in engines] == [adapter.NAME for adapter in ENGINES.all()]


def test_the_preset_commands_print_them_and_json_for_scripts(http: TestClient) -> None:
    listed = CliRunner().invoke(main, ["preset", "list"])
    assert listed.exit_code == 0, listed.output
    assert "fast 64K" in listed.output
    assert "kvmem-llamacpp v0.16.0-rc1" in listed.output
    shown = CliRunner().invoke(main, ["preset", "show", "fast 64K"])
    assert shown.exit_code == 0, shown.output
    assert "kvmem.budget: 32768" in shown.output
    as_json = json.loads(CliRunner().invoke(main, ["preset", "show", "fast-64k", "--json"]).output)
    assert as_json["options"]["context"] == 65536
    missing = CliRunner().invoke(main, ["preset", "show", "nothing like it"])
    assert missing.exit_code == 1
    assert "no preset named" in missing.output


def test_each_listed_preset_says_what_would_stop_it_from_running(home: Home, kernel: Kernel, http: TestClient) -> None:
    write(home.config / "presets" / "typo.json", {**FAST, "title": "typo", "options": {"kv.type": "q2"}})
    kernel.settings.reload_changed()
    presets = {preset["id"]: preset for preset in http.get("/api/v1/runtime/presets", headers=AUTH).json()}
    assert presets["fast-64k"]["problems"] == []
    assert presets["daily-262k"]["problems"] == []
    assert presets["typo"]["problems"] == ["kv.type is one of f16, q8_0, q5_0, q4_0, not 'q2'"]


def test_preset_show_says_what_would_stop_a_preset_from_running(home: Home, kernel: Kernel, http: TestClient) -> None:
    write(home.config / "presets" / "typo.json", {**FAST, "title": "typo", "options": {"kv.type": "q2"}})
    kernel.settings.reload_changed()
    shown = CliRunner().invoke(main, ["preset", "show", "typo"])
    assert "cannot run: kv.type is one of f16, q8_0, q5_0, q4_0, not 'q2'" in shown.output
    listed = CliRunner().invoke(main, ["preset", "list"])
    assert "typo" in listed.output
    assert "1 problem" in listed.output
