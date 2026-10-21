"""Design 0004 §4 and decision 0011: every agent program adapter meets the same contract. It says the command its
program runs in a workspace's container and the environment it runs with (plain names), and writes, for a model
reached at a URL, a configuration that names that URL, that model and its limits, kept in the container's home (never
in the user's folder); and what it supports is declared."""

import pytest

from clank.components.agents.adapters import AGENT_PROGRAMS
from clank.components.agents.adapters.program import AgentModel, AgentProgram

MODEL = AgentModel(url="http://edge:18210/v1", name="agent", title="daily 262K", context=262144, output=16384)
CASES = [pytest.param(adapter, id=adapter.NAME) for adapter in AGENT_PROGRAMS.all()]


@pytest.mark.parametrize("adapter", CASES)
def test_its_command_and_environment_are_well_formed(adapter: type[AgentProgram]) -> None:
    program = adapter()
    assert program.argv(), "it runs something"
    assert all(name.isidentifier() and name.isupper() for name in program.env())
    assert all(isinstance(value, str) for value in program.env().values())
    assert program.capabilities()


@pytest.mark.parametrize("adapter", CASES)
def test_its_configuration_names_the_model_and_lives_in_the_containers_home(adapter: type[AgentProgram]) -> None:
    path, text = adapter().configuration(MODEL)
    assert path.startswith(f"{AgentProgram.HOME}/"), "in the container's home, not the user's folder"
    assert MODEL.url in text
    assert str(MODEL.context) in text
    assert str(MODEL.output) in text
