"""Design 0003 §9 and the M1.6 plan's task 2: on this machine, when asked (`-m real`), each shipped preset whose engine
is installed here starts through a load, answers a request for its model, is measured (what it took, and what it
needed to start when its engine says), and stops through an unload, its GPU memory freed."""

import anyio
import httpx2
import pytest

from clank.components.runtime.gpu import gpu_memory
from clank.components.runtime.service import Runtime
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.real.conftest import ENGINE_MIB, PORT

pytestmark = [pytest.mark.real, pytest.mark.anyio]
YOU = Actor(kind="user", via="console")


async def run(kernel: Kernel, kind: str, **params: object) -> Operation:
    started = await kernel.operations.start(kind, {"slot": "main", **params}, actor=YOU)
    with anyio.fail_after(600):
        return await kernel.operations.wait(started.id)


def answers(model: str) -> str:
    """What the engine says to a short request for its model."""
    request = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 64}
    answer = httpx2.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", json=request, timeout=300)
    assert answer.status_code == 200, answer.text
    choice = answer.json()["choices"][0]["message"]
    return str(choice.get("content") or choice.get("reasoning_content") or "")


@pytest.mark.parametrize("preset", ["daily 262K"])
async def test_each_preset_installed_here_starts_answers_is_measured_and_stops(machine: Kernel, preset: str) -> None:
    runtime: Runtime = machine.parts["runtime"]
    items = {item.name: item for item in runtime.check(preset)}
    if items.get("install") is None or items["install"].status == "failed":
        pytest.skip(f"{preset}'s engine is not installed here")
    if items["fit"].status == "failed":
        pytest.skip(f"{preset} does not fit now: {items['fit'].detail}")
    assert all(item.status != "failed" for item in items.values()), items
    async with machine.operations.running():
        try:
            loaded = await run(machine, "runtime.load", preset=preset)
            assert loaded.status == "done", loaded.error
            [launch] = runtime.state.launches(1)
            assert launch.measured_mib is not None
            assert launch.seconds is not None
            models = httpx2.get(f"http://127.0.0.1:{PORT}/v1/models", timeout=30).json()["data"]
            assert answers(str(models[0]["id"]))
        finally:
            unloaded = await run(machine, "runtime.unload")
            assert unloaded.status == "done", unloaded.error
    with anyio.fail_after(60):
        while (now := gpu_memory()) is not None and now.used_mib > ENGINE_MIB:
            await anyio.sleep(1)
