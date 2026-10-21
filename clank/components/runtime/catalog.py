"""The model catalog (design 0001 §2, design 0003 §7.3): the models Clank knows, from `clank/catalog/models/*.json`.

Each model lists its files in each format it exists in (GGUF, which KVMem and llama.cpp read), each with its
role (the weights, or a vision projector), where it comes from (a Hugging Face repository at a revision), its
size and its SHA-256; the facts read from it (its context, its attention layers and KV width, which the memory
estimates need); and, for each engine, the sizes that engine's estimate uses, with where each number came from. A model
may also give its chat template's facts (`template`: how it renders earlier thinking and tool calls, its reasoning
markers) and its calibration (`calibration`: tokens per character by kind of part), which the Monitor reads (design 0012
§4, decision 0067); a model with neither says so, and the Monitor's estimate then uses a plain default.

`preset_problems` is the first part of a preset's check (design 0003 §6.5): its serving setup, its version and its
model are known, its engine reads one of the model's formats, and its options are valid for that version. What needs
the host (the files there, the program's own `--help`, the GPU's free memory) comes with the slots (M1.3).
"""

import functools
import json
from collections.abc import Mapping
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import EngineError
from clank.components.runtime.kinds import Preset
from clank.kernel.adapters import AdapterError


class ModelFileEntry(BaseModel):
    """One file of a model, in one format."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["gguf"]
    role: Literal["weights", "projector"]
    repository: str = Field(description="The Hugging Face repository it comes from.")
    revision: str = Field(description="The repository's revision it was taken at; empty when no longer known.")
    path: str = Field(description="The file's path in the repository.")
    size: int = Field(gt=0, description="Its size in bytes.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Its SHA-256.")
    notes: str = ""


class ModelFacts(BaseModel):
    """What is known of a model from its files."""

    model_config = ConfigDict(extra="forbid")

    architecture: str
    parameters: str
    context: int = Field(gt=0, description="The context it was trained for, in tokens.")
    attention_layers: int = Field(gt=0, description="The layers that keep a KV cache.")
    kv_width: int = Field(gt=0, description="The width of a key (and of a value) in one such layer.")
    abilities: list[str]


class EngineSizes(BaseModel):
    """The sizes one engine's memory estimate uses for a model, and where they came from."""

    model_config = ConfigDict(extra="forbid")

    sizes: dict[str, float]
    source: str


class TemplateFacts(BaseModel):
    """How a model's chat template renders a conversation (design 0012 §4, decision 0067), which the Monitor's estimate
    of the context's parts follows, and where that was read."""

    model_config = ConfigDict(extra="forbid")

    earlier_thinking: Literal["dropped", "kept", "none"] = Field(
        description="The thinking of earlier answers: left out before the last user message (Qwen's reference "
        "template), kept, or none (the model does not think)."
    )
    tool_calls: Literal["xml", "json"] = Field(description="How it writes a tool call into the conversation.")
    reasoning: list[str] = Field(description="The markers around its thinking; none when it does not think.")
    source: str = Field(description="Where these facts were read.")


class Calibration(BaseModel):
    """A model's tokens per character, by kind of part, for the Monitor's estimate (design 0012 §4.2), measured once
    per model on synthetic requests that differ by one part; and that measurement."""

    model_config = ConfigDict(extra="forbid")

    tokens_per_character: dict[str, float]
    measured: str = Field(description="When and how it was measured.")


class ModelEntry(BaseModel):
    """A model of the catalog."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    facts: ModelFacts
    files: list[ModelFileEntry]
    engines: dict[str, EngineSizes] = Field(default_factory=dict)
    template: TemplateFacts | None = None
    calibration: Calibration | None = None

    def file(self, format: str, role: str = "weights") -> ModelFileEntry | None:
        """Its file of a format and a role, if it has one."""
        return next((file for file in self.files if file.format == format and file.role == role), None)

    def sizes(self, engine: str) -> dict[str, float]:
        """The sizes an engine's memory estimate needs: the model's facts, then the engine's own."""
        found = {"attention_layers": float(self.facts.attention_layers), "kv_width": float(self.facts.kv_width)}
        return {**found, **(self.engines[engine].sizes if engine in self.engines else {})}

    def facts_view(self) -> dict[str, Any]:
        """What the Monitor reads of the model (design 0012 §4.7): its id and name, its template's facts and its
        calibration, `None` for either it has not."""
        return {
            "id": self.id,
            "name": self.name,
            "template": self.template.model_dump(mode="json") if self.template else None,
            "calibration": self.calibration.model_dump(mode="json") if self.calibration else None,
        }


@functools.cache
def catalog() -> dict[str, ModelEntry]:
    """Every model of the catalog, by its id."""
    folder = resources.files("clank").joinpath("catalog", "models")
    models: dict[str, ModelEntry] = {}
    for item in sorted(folder.iterdir(), key=lambda entry: entry.name):
        if item.name.endswith(".json"):
            data = json.loads(item.read_text(encoding="utf-8"))
            data.pop("schema", None)
            entry = ModelEntry.model_validate(data)
            models[entry.id] = entry
    return models


def size_text(count: int) -> str:
    """A size as people read it: 12 bytes, 600 KB, 16.5 GB."""
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if count >= scale:
            return f"{count / scale:.3g} {unit}"
    return f"{count} bytes"


def preset_problems(preset: Preset, models: Mapping[str, ModelEntry] | None = None) -> list[str]:
    """What makes a preset impossible to run as it is, one sentence each, before any plan; none here for a cloud
    preset, whose problems are its provider's (`runtime.endpoints`)."""
    if preset.endpoint:
        return []
    try:
        engine = ENGINES.get(preset.engine)(preset.engine_version)
    except (AdapterError, EngineError) as error:
        return [str(error)]
    model = (catalog() if models is None else models).get(preset.model)
    if model is None:
        return [f"the catalog has no model {preset.model}"]
    problems = []
    if model.file(engine.FORMAT) is None:
        problems.append(f"{model.id} has no {engine.FORMAT} file in the catalog, the format {engine.LABEL} reads")
    return problems + engine.validate(preset.options)
