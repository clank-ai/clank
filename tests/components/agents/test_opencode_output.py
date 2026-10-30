"""Design 0016 §7 and design 0012 §4.1 (revised after approval 2026-10-29, decision 0153): OpenCode caps each answer at
32,000 tokens unless `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` says more (read in OpenCode 1.19.4's source, the image's
version), so for a model whose most output is above 32,000, Clank sets the variable to that most output when OpenCode
starts, from a terminal or without one, and its notes say so; at 32,000 or under it sets nothing. OpenCode then counts
the whole most output in its compaction line, and so do the Monitor's rule and Watch for's line, while what a
compaction keeps is still counted with 32,000, as OpenCode counts it. Run against the fake bridge, with no container
and no OpenCode."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from clank import registry
from clank.components.agents.adapters.opencode import OUTPUT_VARIABLE, OpenCode
from clank.components.agents.adapters.program import AgentModel
from clank.components.agents.service import Agents
from clank.components.agents.watchfor.rules import Facts
from clank.components.gateway.service import Gateway
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.agents.test_watch_for_rules import compaction_near, found_by
from tests.fakes.bridge import FakeBridge
from tests.fakes.platform import FakePlatform, container

OWNER = Actor(kind="user", via="console")
MODEL = AgentModel(url="http://edge:18100/v1", name="agent", title="cloud: Example Coder", context=262144,
                   output=65536, images=False, margin=16384)  # fmt: skip
CLOUD = {"status": "ready", "busy": False, "preset": "cloud-example-coder", "title": "cloud: Example Coder",
         "context": 262144, "output": 65536, "images": False}  # fmt: skip
NOTE = (
    "OpenCode may send up to 65,536 tokens an answer: Clank sets OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX to the most "
    "output, OpenCode's own cap being 32,000"
)


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    routes = {"slots": {"main": CLOUD}, "roles": {"agent": "main"}, "default_slot": "main", "demand": {}}
    monkeypatch.setattr(Gateway, "routes", lambda self: routes)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def bridge(kernel: Kernel, tmp_path: Path) -> FakeBridge:
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    made = FakeBridge("paper", folder, hear=kernel.parts["agents"].review.heard)
    platform.inside = made.inside
    kernel.parts["workspaces"].docker(refresh=True)
    return made


def agents(kernel: Kernel) -> Agents:
    found: Agents = kernel.parts["agents"]
    return found


def test_the_variable_is_the_most_output_above_32000_and_unset_at_or_under_it() -> None:
    assert OUTPUT_VARIABLE == "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"
    assert OpenCode().env(MODEL)[OUTPUT_VARIABLE] == "65536"
    assert OUTPUT_VARIABLE not in OpenCode().env(replace(MODEL, output=32000))
    assert OUTPUT_VARIABLE not in OpenCode().env(), "no model: nothing to say of its output"
    assert OpenCode().env_said(MODEL) == [NOTE]
    assert OpenCode().env_said(replace(MODEL, output=16384)) == []


def test_the_compaction_line_counts_the_whole_most_output_and_what_it_keeps_counts_32000() -> None:
    rule = OpenCode().compaction(262144, 65536, 16384)
    assert rule is not None
    assert (rule.line, rule.keeps) == (262144 - 16384 - 65536, 15000)
    assert "65,536" in rule.rule
    assert "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX" in rule.rule
    small = OpenCode().compaction(65536, 32768, 16384)
    assert small is not None
    assert small.line == 65536 - 16384 - 32768, "all 32,768 of it counted"
    assert small.keeps == (65536 - 16384 - 32000) // 4, "a quarter of the window less 32,000, not of the line"
    under = OpenCode().compaction(262144, 16384)
    assert under is not None
    assert (under.line, under.keeps) == (245760, 15000), "under 32,000 the rule is as it was"


def test_watch_for_counts_the_whole_most_output_above_32000() -> None:
    flow, _ = compaction_near()  # steps of 200,000, 220,000 and 240,000 tokens
    [found] = found_by("compaction_near", flow, Facts(context=262144, output=65536))
    assert "of 196,608 tokens used before OpenCode compacts" in found.why, "262,144 less all 65,536"
    assert "the output limit 65,536" in found.why


def test_opencode_started_from_a_terminal_gets_the_variable_and_its_note_says_so(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    prepared = agents(kernel).prepare("paper")
    assert f"{OUTPUT_VARIABLE}=65536" in prepared["argv"]
    assert NOTE in prepared["notes"]
    assert NOTE in agents(kernel).plan()["notes"]


def test_opencode_started_without_a_terminal_gets_the_variable_too(kernel: Kernel, bridge: FakeBridge) -> None:
    assert agents(kernel).configure("paper")[OUTPUT_VARIABLE] == "65536"
    assert agents(kernel).agent_env("paper")[OUTPUT_VARIABLE] == "65536"
