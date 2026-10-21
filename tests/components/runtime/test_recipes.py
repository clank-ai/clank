"""Design 0003 §7.1 and decision 0032: every recipe Clank ships is for a serving setup and a version Clank has an
adapter for, makes its program in the engine's folder, and builds the source the adapter's version names; nothing it
runs needs root. None ships now (KVMem is adopted where it was built, decision 0034 retired NInfer's): the tests of a
shipped recipe wait for the next one, and Clank with none has none rather than an error."""

from pathlib import Path

import pytest

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.recipes import Recipe, recipes

SHIPPED = list(recipes().values())


def test_with_no_recipe_shipped_clank_has_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clank.components.runtime.recipes.resources.files", lambda package: tmp_path)
    recipes.cache_clear()
    try:
        assert recipes() == {}
    finally:
        recipes.cache_clear()


@pytest.mark.parametrize("recipe", SHIPPED, ids=lambda recipe: f"{recipe.setup}-{recipe.version}")
def test_a_shipped_recipe_is_for_a_version_an_adapter_knows_and_fetches_what_it_names(recipe: Recipe) -> None:
    """A build checks out the commit its version names; a release's archive is fetched by its tag and checked against
    its SHA-256 (llama.cpp's CPU build, decision 0035)."""
    adapter = ENGINES.get(recipe.setup)
    version = adapter.known(recipe.version)
    assert all(part.startswith("{folder}/") for part in recipe.program[:1])
    commands = [" ".join(step.run) for step in recipe.steps]
    if version.source.startswith("release "):
        tag = version.source.removeprefix("release ").split(",")[0]
        assert any(f"/download/{tag}/" in command and "sha256sum --check" in command for command in commands)
    else:
        commit = version.source.removeprefix("commit ")
        assert any(commit in command for command in commands), f"no step checks out {commit}"
    assert not any(word in command.split() for command in commands for word in ("sudo", "apt", "apt-get"))


@pytest.mark.parametrize("recipe", SHIPPED, ids=lambda recipe: f"{recipe.setup}-{recipe.version}")
def test_a_shipped_recipe_keeps_every_tool_out_of_the_users_home(recipe: Recipe) -> None:
    """micromamba registers its environments in ~/.conda and keeps a cache in ~/.mamba, CUDA keeps one in ~/.nv: with
    the steps' home in the engine's folder, nothing is written outside it (decision 0032)."""
    assert recipe.env.get("HOME", "").startswith("{folder}/")
    assert all("HOME" not in step.env for step in recipe.steps), "a step keeps the recipe's home"


@pytest.mark.parametrize("recipe", SHIPPED, ids=lambda recipe: f"{recipe.setup}-{recipe.version}")
def test_each_step_that_makes_something_makes_it_whole_or_not_at_all(recipe: Recipe) -> None:
    for step in recipe.steps:
        if not step.makes:
            continue
        command = " ".join(step.run)
        assert ".part" in command or "touch" in command or step.makes.endswith("CMakeLists.txt"), step.name
