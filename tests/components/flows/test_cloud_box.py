"""Design 0016 §7 and §9 (decisions 0062 and 0112): a flow's box may name a cloud preset. Before the runner switches the
main slot to it, the workspace is asked whether its agent may use the cloud model, the run saying it waits for the
answer: allowed, the slot switches as for any preset; kept on this machine, the box fails at a gate saying why and how
to allow it. `clank flow prepare` prices each box's first message at its model's input price. Run with the fake
OpenRouter, the fake bridge and a synthetic folder."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, make_rig, question, running, until
from tests.fakes.openrouter import KEY, served

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
CLOUD = "cloud: Example Coder"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    """The flows' rig with OpenRouter agreed, its key set, and the cloud preset "cloud: Example Coder"."""
    with served() as fake:
        monkeypatch.setattr(OpenRouter, "URL", fake.url)
        made = make_rig(home, clock, tmp_path, monkeypatch, None)
        settings = made.kernel.settings
        agreed = {**OpenRouter.template(), "agreed": "2026-10-21T09:12:04.120Z"}
        settings.write("endpoint", "openrouter", agreed, base=None, actor=YOU)
        made.kernel.secrets.put("endpoint/openrouter", "key", KEY, actor=YOU)
        options = {"context": 65536, "max_output": 16384}
        preset = {"schema": "preset/1", "title": CLOUD, "endpoint": "openrouter",
                  "model": "example-vendor/example-coder", "options": options}  # fmt: skip
        place = home.config / "presets" / "cloud-example-coder.json"
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(json.dumps(preset, indent=2) + "\n", encoding="utf-8")
        settings.reload_changed()
        made.fake = fake  # type: ignore[attr-defined]
        try:
            yield made
        finally:
            made.kernel.close()


def flow() -> dict[str, Any]:
    brief = {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]}
    work = {"id": "T1", "type": "task", "title": "Task T1", "writes": ["T1.md"], "prompt": "Write T1.md.",
            "model": CLOUD}  # fmt: skip
    return {"schema": "flow/1", "title": "Study", "boxes": [brief, work], "lines": [{"from": "brief", "to": "T1"}]}


async def started(rig: Rig) -> None:
    rig.write_flow(flow())
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "A made-up brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")


async def test_a_box_on_a_cloud_preset_waits_for_the_workspaces_answer_then_switches(rig: Rig) -> None:
    async with running(rig.kernel):
        await started(rig)
        asked = await until(lambda: question(rig, "use the cloud model"), seconds=20)
        assert asked.title == f"Let {WORKSPACE}'s agent use the cloud model {CLOUD}?"
        waits = await until(lambda: rig.run().waits_for, seconds=10)
        assert waits == f"waiting for your answer: may {WORKSPACE} use the cloud model {CLOUD}?"
        rig.kernel.questions.answer(asked.id, by=OWNER, option="allow")
        await until(lambda: rig.kernel.parts["runtime"].state.slot("main").preset == "cloud-example-coder", seconds=30)
    switched = [each for each in rig.kernel.operations.find(limit=50) if each.type == "runtime.switch"]
    assert [str(each.params["preset"]) for each in switched] == ["cloud-example-coder"]


async def test_a_box_on_a_cloud_preset_in_a_workspace_kept_local_fails_at_a_gate_saying_why(rig: Rig) -> None:
    rig.kernel.parts["workspaces"].allow_cloud(WORKSPACE, False, actor=OWNER)
    async with running(rig.kernel):
        await started(rig)
        gate = await until(lambda: rig.run().box("T1").state == "failed", seconds=20)
    assert gate
    events = [f"{each.summary} {each.data.get('reason', '')}" for each in rig.events("flows.box_ended", "flows.model")]
    assert any(f"{WORKSPACE} is kept on this machine" in each for each in events), events
    assert not [each for each in rig.kernel.operations.find(limit=50) if each.type == "runtime.switch"]


def test_prepare_prices_each_boxs_first_message_at_its_models_input_price(rig: Rig) -> None:
    rig.write_flow(flow())
    rig.kernel.parts["runtime"].endpoints.models("openrouter")
    shown = rig.kernel.parts["flows"].prepare(WORKSPACE, "study")
    [box] = shown["boxes"]
    assert (box["named"], box["preset"], box["window"]) == (CLOUD, "cloud-example-coder", 65536)
    assert box["price_usd"] == pytest.approx(box["tokens"] * 0.3 / 1_000_000)
    assert box["price_said"].startswith("≈ $")
    assert box["price_said"].endswith("at $0.30 per million tokens in")
