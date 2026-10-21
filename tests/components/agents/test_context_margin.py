"""Design 0012 §4.1 (revised 2026-10-20, decision 0089): OpenCode is told the engine's window less a margin kept free
for one step's tool results (`config/opencode.json`'s `context_margin`, 16,384 unless the owner sets another), so it
compacts a session once a step's total reaches 229,376 tokens (262,144 less twice 16,384), before that step's results,
sent with the next request, can push the request and its answer's room past the engine's window (KVMem refuses such a
request: a session failed so at step 143, 35 tokens under the old line of 245,760). The margin is never more than a
quarter of the window, and 0 tells OpenCode the whole window. What `prepare` writes, what the folder page is told and
the Monitor's compaction line agree, and the Monitor still shows the engine's own window. The sessions are synthetic."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from clank import registry
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.adapters.program import AgentModel, kept_margin
from clank.components.agents.kinds import OpenCodeSettings
from clank.components.agents.service import Agents
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import SESSION, doing, ended, facts_of
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"
WINDOW, OUTPUT, MARGIN = 262144, 16384, 16384


def test_the_margin_is_16384_by_default_in_a_readable_settings_file_and_never_negative() -> None:
    assert OpenCodeSettings().context_margin == 16384
    assert registry.kinds().get("opencode") is OpenCodeSettings, "config/opencode.json, listed with every kind"
    assert "OpenCode's next start" in OpenCodeSettings.applies(), "the configuration is written when OpenCode starts"
    described = OpenCodeSettings.model_fields["context_margin"].description or ""
    assert "51,200 bytes" in described, "the default is explained by OpenCode's cut of one tool's output"
    with pytest.raises(ValidationError):
        OpenCodeSettings.model_validate({"context_margin": -1})


def test_opencode_is_told_the_window_less_the_margin_and_compacts_before_a_steps_results_can_overflow_it() -> None:
    model = AgentModel(url="http://edge:18210/v1", name="agent", title="daily 262K", context=WINDOW, output=OUTPUT,
                       margin=MARGIN)  # fmt: skip
    config = json.loads(OpenCode().configuration(model)[1])
    assert config["provider"]["clank"]["models"]["agent"]["limit"] == {"context": 245760, "output": 16384}
    rule = OpenCode().compaction(WINDOW, OUTPUT, MARGIN)
    assert (rule.line, rule.keeps) == (229376, 15000)
    assert "16,384" in rule.rule
    assert "tool results" in rule.rule
    largest = rule.line - 1  # the largest total of a step after which OpenCode does not compact
    assert largest + MARGIN + OUTPUT <= WINDOW, "its results up to the margin, and the answer's room, still fit"
    before = OpenCode().compaction(WINDOW, OUTPUT)
    failed_step, its_results = 245725, 1206  # the session of 2026-10-20: counts only
    assert failed_step < before.line, "without the margin it went on, 35 tokens under the line"
    assert failed_step + its_results + OUTPUT > WINDOW, "and its next request was refused"
    assert failed_step >= rule.line, "with it, OpenCode compacts after that step"


def test_the_margin_is_at_most_a_quarter_of_the_window_and_0_tells_opencode_the_whole_window() -> None:
    assert kept_margin(16384, 262144) == 16384
    assert kept_margin(16384, 32768) == 8192, "a quarter of a small window, so a step still has room"
    assert kept_margin(0, 262144) == 0
    model = AgentModel(url="u", name="agent", title="t", context=WINDOW, output=OUTPUT)
    assert model.margin == 0, "an AgentModel keeps no margin unless given one"
    assert json.loads(OpenCode().configuration(model)[1])["provider"]["clank"]["models"]["agent"]["limit"] == {
        "context": 262144, "output": 16384,
    }  # fmt: skip


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    gateway = kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "routes", routes)
    monkeypatch.setattr(gateway, "facts", facts_of)
    monkeypatch.setattr(gateway, "activity", lambda *given, **named: doing(ended("r-1", 150000, 2661)))
    yield kernel
    kernel.close()


def routes() -> dict[str, Any]:
    """The main slot running daily 262K, its limits and facts as the runtime gives them."""
    slot = {"status": "ready", "busy": False, "preset": "daily-262k", "title": "daily 262K", "context": WINDOW,
            "output": OUTPUT, "facts": facts_of("daily-262k")}  # fmt: skip
    return {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main"}


def opened(kernel: Kernel, platform: FakePlatform, folder: Path) -> str:
    """A workspace whose container runs; the container's name."""
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    return name


def set_margin(kernel: Kernel, margin: int) -> None:
    """The owner's margin, written to `config/opencode.json` as the console or an editor would."""
    base = kernel.settings.get("opencode", "opencode").revision
    kernel.settings.write("opencode", "opencode", {"context_margin": margin}, base=base, actor=YOU)


def told(platform: FakePlatform, name: str) -> dict[str, Any]:
    """The limits OpenCode's configuration in the container gives its model."""
    config = json.loads(platform.files[(name, CONFIG)])
    return dict(config["provider"]["clank"]["models"]["agent"]["limit"])


def test_prepare_tells_opencode_the_window_less_the_margin_and_the_monitors_line_agrees(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    name = opened(kernel, platform, tmp_path)
    agents: Agents = kernel.parts["agents"]
    prepared = agents.prepare("paper")
    assert told(platform, name) == {"context": 245760, "output": 16384}
    limits = {"context": 245760, "output": 16384, "window": 262144, "margin": 16384}
    assert prepared["limits"] == limits, "the folder page says what OpenCode is told, and the engine's window"
    assert agents.plan()["limits"] == limits
    shown = agents.context("paper", SESSION)
    assert (shown["window"], shown["line"], shown["left"]) == (262144, 229376, 229376 - 152661), (
        "the Monitor shows the engine's window, and the line OpenCode compacts at"
    )


def test_a_margin_the_owner_sets_is_what_opencode_is_told_at_its_next_start(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    name = opened(kernel, platform, tmp_path)
    agents: Agents = kernel.parts["agents"]
    set_margin(kernel, 0)
    agents.configure("paper")
    assert told(platform, name) == {"context": 262144, "output": 16384}
    assert agents.context("paper", SESSION)["line"] == 245760
    set_margin(kernel, 32768)
    agents.prepare("paper")
    assert told(platform, name) == {"context": 229376, "output": 16384}
    assert agents.context("paper", SESSION)["line"] == 212992
