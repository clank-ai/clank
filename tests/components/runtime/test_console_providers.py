"""Design 0003 §8.2 and the M1.5 plan's task 4: the console's Providers and models page shows each serving setup with
its versions, where each is installed and how, and which Clank has a recipe for; and each model's files, with where
each is on the hosts whose engine reads it and whether it is there. `i` installs an engine by its recipe on a host
picked from lists (the install asks first, as any install does); `d` downloads a model's file (which asks too); `x`
removes a model's files from a host (asking first) and `u` removes an engine (one Clank did not build is forgotten)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clank.client import Client
from clank.console.app import ClankConsole
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig
from tests.components.runtime.consoles import page_text, pick, serve
from tests.console.frames import settle

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 11, 45, tzinfo=UTC)
YOU = Actor(kind="user", via="console")


@pytest.fixture
def served(bench: Rig) -> Iterator[Client]:
    with serve(bench) as client:
        yield client


async def test_providers_show_installs_and_files_and_i_installs_and_d_downloads_after_asking(
    bench: Rig, served: Client
) -> None:
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=bench.kernel.home, page="providers")
    async with app.run_test(size=(120, 50)) as pilot:
        shows = ("tiny-projector.gguf", "(kvmem-llamacpp), reads gguf")
        await settle(pilot, lambda: all(word in page_text(app, "providers") for word in shows), seconds=30)
        shown = page_text(app, "providers")
        assert "KVMem/llama.cpp (kvmem-llamacpp), reads gguf" in shown
        assert "v0.16.0-rc1  on local (test) · Clank has its recipe" in shown
        assert "gguf weights     tiny.gguf, 12 bytes, from tests/tiny" in shown
        assert f"local: there, adopted at {bench.models / 'tiny.gguf'}" in shown
        await pilot.press("i")
        await pick(pilot, app, "KVMem/llama.cpp v0.16.0-rc1")
        await pick(pilot, app, "bench")
        await settle(pilot, lambda: any(q["title"].startswith("Install KVMem") for q in app.data.questions), seconds=20)
        [asked] = bench.kernel.questions.waiting()
        bench.kernel.questions.answer(asked.id, by=YOU, option="install")
        await settle(pilot, lambda: "on bench (recipe), local (test)" in page_text(app, "providers"), seconds=60)
        await pilot.press("d")
        await pick(pilot, app, "Tiny: tiny-projector.gguf")
        await pick(pilot, app, "bench")
        await settle(
            pilot, lambda: any(q["title"].startswith("Download tiny-projector.gguf") for q in app.data.questions)
        )
        [asked] = bench.kernel.questions.waiting()
        bench.kernel.questions.answer(asked.id, by=YOU, option="cancel")


async def test_x_removes_a_models_files_and_u_an_engine_each_as_its_operation_says(
    bench: Rig, served: Client, tmp_path: Path
) -> None:
    weights = tmp_path / "bench-clank" / "models" / "tests" / "tiny" / "0123456789ab" / "tiny.gguf"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"gguf weights")
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=bench.kernel.home, page="providers")
    async with app.run_test(size=(120, 50)) as pilot:

        def ready() -> bool:
            return "tiny.gguf, 12 bytes" in page_text(app, "providers") and any(
                host["name"] == "bench" for host in app.data.hosts
            )

        await settle(pilot, ready, seconds=30)
        await pilot.press("x")
        await pick(pilot, app, "Tiny (tiny)")
        await pick(pilot, app, "bench")
        await settle(pilot, lambda: any(q["title"].startswith("Remove 1 file of Tiny") for q in app.data.questions))
        [asked] = bench.kernel.questions.waiting()
        bench.kernel.questions.answer(asked.id, by=YOU, option="remove")
        await settle(pilot, lambda: not weights.exists(), seconds=30)
        await pilot.press("u")
        await pick(pilot, app, "KVMem/llama.cpp v0.16.0-rc1 on local")
        await settle(pilot, lambda: "v0.16.0-rc1  not installed" in page_text(app, "providers"), seconds=30)
