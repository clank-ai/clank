"""Recipes: how a serving setup's engine is installed at a version (design 0001 §7.4, design 0003 §7.1, decision 0032).

A recipe is a readable file, `clank/recipes/<setup>/<version>.json`: what it fetches (and about how much), its steps,
the program it makes, the libraries that program needs, and any deviation from the engine's own release. Each step is
one command run on the host in the engine's folder (`<Clank folder>/engines/<setup>/<version>`), with what it makes
(`makes`, a file in that folder): a step whose result is already there is skipped, so an install that failed goes on
from where it stopped. A step that makes something large makes it under another name and renames it at its end (or
writes its file last), so what a step left half done is never taken for made; a step that is quick to repeat (a
configure, an incremental build) makes nothing and always runs. In a step, `{folder}` is the engine's folder. A
recipe's build runs on half the host's cores at a low priority, so the computer stays usable while it runs.

Every step, and the check of the program it made, runs with the recipe's environment (`env`), a step's own variables
added to it. Clank's recipes set `HOME` in the engine's folder there: tools write into the user's home unasked
(micromamba registers its environments in `~/.conda` and keeps a cache in `~/.mamba`, CUDA keeps one in `~/.nv`), and
an install writes nothing outside its folder (decision 0032).
"""

import functools
import json
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field


class RecipeStep(BaseModel):
    """One command of a recipe."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="What it does, in a word: fetch, environment, source, configure, build.")
    run: list[str] = Field(description="The command, run in the engine's folder; {folder} is filled in.")
    makes: str = Field("", description="What it makes, in the engine's folder; the step is skipped when it is there.")
    env: dict[str, str] = Field(default_factory=dict, description="Variables it needs, {folder} filled in.")


class Recipe(BaseModel):
    """How an engine is installed at a version."""

    model_config = ConfigDict(extra="forbid")

    setup: str
    version: str
    summary: str
    download: str = Field(description="What it fetches, and about how much.")
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Variables every step and the check of its program run with, {folder} filled in.",
    )
    steps: list[RecipeStep]
    program: list[str] = Field(description="The command that runs the engine it makes, {folder} filled in.")
    library_path: list[str] = Field(default_factory=list, description="Folders of the libraries the engine needs.")
    deviations: list[str] = Field(default_factory=list, description="How it differs from the engine's own release.")


def fill(text: str, folder: str) -> str:
    """A recipe's text with its engine's folder filled in."""
    return text.replace("{folder}", folder)


@functools.cache
def recipes() -> dict[tuple[str, str], Recipe]:
    """Every recipe Clank ships, by setup and version."""
    found: dict[tuple[str, str], Recipe] = {}
    top = resources.files("clank").joinpath("recipes")
    if not top.is_dir():  # no recipe ships now: KVMem is adopted where it was built
        return found
    for setup in sorted(top.iterdir(), key=lambda entry: entry.name):
        if not setup.is_dir():
            continue
        for item in sorted(setup.iterdir(), key=lambda entry: entry.name):
            if item.name.endswith(".json"):
                data = json.loads(item.read_text(encoding="utf-8"))
                data.pop("schema", None)
                recipe = Recipe.model_validate(data)
                found[(recipe.setup, recipe.version)] = recipe
    return found
