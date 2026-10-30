"""The runtime component's kinds of record (design 0003 §3): what the user decides, as readable files.

- `preset` (`config/presets/<id>.json`): a saved launch configuration, design 0001 §3.4 and §3.7: the serving setup
  (an engine adapter) at a version, the model from the catalog, the options that differ from the engine's defaults, and
  the slot it is for; or, for a cloud preset (design 0016 §7), the provider (`endpoint`) in place of the engine, its
  model the id the provider lists, for the main slot only. Its title is its name in every client; its id is its file's
  name. A change to the preset a slot runs applies at its next start.
- `host` (`config/hosts/<id>.json`): where engines run (decision 0030): a WSL distribution or the local Linux, and the
  Clank folder on it that holds engines and models.
- `model-file` (`config/model-files/<id>.json`): where one of the catalog's files is on a host, when the user keeps it
  somewhere other than the host's `models/` folder.
- `runtime` (`config/runtime.json`): the slots, the engines' port, and the limits of starts and health checks.
- `endpoint` (`config/endpoints/<id>.json`, design 0016 §4): a provider someone else runs, reached at its URL with the
  owner's key (kept with the secrets, never here): OpenRouter first. Its adapter fixes its URL, its reach and how the
  key is sent, and the options it takes (`runtime.endpoints` checks a record against them); `agreed` is when the owner
  agreed that prompts and what the agent reads go to it, empty while not agreed.

What runs, each install and each launch are state, in the runtime's tables (M1.3, M1.4).
"""

from typing import Literal

from pydantic import Field, model_validator

from clank.kernel.records import Settings

OptionValue = int | float | str | bool
Reach = Literal["this-machine", "my-servers", "cloud"]


class Preset(Settings):
    """A saved launch configuration."""

    KIND = "preset"
    LABEL = "Preset"
    HELP = (
        "A saved launch configuration: a serving setup at a version, a model, and the launch options that differ from "
        "the engine's defaults (design 0001 §3.4)."
    )
    ON_CHANGE = "next start"
    NEXT_START = "the next start of the slot that runs it"

    engine: str = Field(
        "",
        title="Serving setup",
        description="The engine adapter that runs it, such as kvmem-llamacpp; empty for a cloud preset.",
    )
    engine_version: str = Field(
        "", title="Engine version", description="The engine's version, such as v0.16.0-rc1; empty for a cloud preset."
    )
    endpoint: str = Field(
        "",
        title="Provider",
        description="For a cloud preset, in place of an engine: the provider someone else runs that serves its model "
        "(config/endpoints/<id>.json), such as openrouter (design 0016 §7).",
    )
    model: str = Field(
        title="Model",
        description="The model's id in the catalog, such as qwen3.8-27b; for a cloud preset, its id exactly as its "
        "provider lists it.",
    )
    options: dict[str, OptionValue] = Field(
        default_factory=dict,
        title="Launch options",
        description="The options that differ from the engine's defaults, by their keys (design 0001 §3.1); for a cloud "
        "preset: context, max_output, reasoning and images.",
    )
    slot: str = Field("main", title="Slot", description="The slot it is for (design 0001 §1).")
    host: str = Field(
        "", title="Host", description="Where it runs; empty: the one host its engine is installed on (decision 0030)."
    )
    notes: str = Field(
        "", title="Notes", description="Anything worth knowing: where it came from, what it deviates in."
    )
    fallback: str = Field(
        "",
        title="Fallback",
        description=(
            "A preset the slot loads when this one's engine crashes (settings on trial, design 0021 §10); empty: the "
            "crash rule every preset has (started again once, or asked)."
        ),
    )

    @model_validator(mode="after")
    def _one_provider(self) -> "Preset":
        if self.engine and self.endpoint:
            raise ValueError("a preset names an engine or an endpoint, never both")
        if not self.engine and not self.endpoint:
            raise ValueError("a preset names an engine (and its version) or an endpoint")
        if self.engine and not self.engine_version:
            raise ValueError("a preset that names an engine names its engine_version too")
        if self.endpoint and self.slot != "main":
            raise ValueError(
                "a cloud preset serves the main slot only: fast needs /infill on this machine (design 0006), and "
                "vision a model loaded on demand here (design 0008 §7)"
            )
        return self

    @property
    def cloud(self) -> bool:
        """Whether a provider someone else runs serves it (design 0016 §7)."""
        return bool(self.endpoint)


class Endpoint(Settings):
    """A provider someone else runs, reached at its URL with the owner's key (design 0016 §4)."""

    KIND = "endpoint"
    LABEL = "Endpoint"
    HELP = (
        "A provider someone else runs, reached with your key: a cloud provider such as OpenRouter (design 0016 §4). "
        "Its key is kept with the secrets (CLANK_HOME/secrets/endpoint/<id>/key), never in this file."
    )
    ON_CHANGE = "next start"
    NEXT_START = "the next load of one of its presets (clearing agreed applies to the next request)"

    adapter: str = Field(title="Adapter", description="The endpoint adapter that speaks to it, such as openrouter.")
    url: str = Field(
        title="Address",
        description="Its API's base URL; for a cloud provider the adapter's own, so the key never goes elsewhere.",
    )
    auth: Literal["bearer", "none"] = Field(
        title="Key sent as", description="bearer: the key in an Authorization header; none: no key."
    )
    reach: Reach = Field(
        title="Reach",
        description="Where what it is sent goes: this-machine, my-servers, or cloud (a company's API).",
    )
    options: dict[str, OptionValue] = Field(
        default_factory=dict,
        title="Provider options",
        description="The adapter's own options, such as OpenRouter's data_collection (deny: only providers that keep "
        "no data) and zdr (only zero-data-retention providers).",
    )
    agreed: str = Field(
        "",
        title="Agreed",
        description="When you agreed that prompts and the files and command output the agent reads go to it; empty: "
        "not agreed, and nothing loads from it.",
    )
    timeout_seconds: int = Field(
        600,
        ge=10,
        title="Read timeout",
        description="The longest the gateway waits for the next piece of an answer, in seconds.",
    )
    notes: str = Field("", title="Notes", description="Anything worth knowing.")

    @property
    def is_agreed(self) -> bool:
        """Whether the owner agreed to what goes to it."""
        return bool(self.agreed.strip())


class Host(Settings):
    """Where engines run."""

    KIND = "host"
    LABEL = "Host"
    HELP = "Where engines run (decision 0030): a WSL distribution, or the local Linux, with its own Clank folder."

    adapter: Literal["wsl", "local"] = Field(
        title="Kind of host", description="wsl: a WSL distribution, through wsl.exe; local: the service's own Linux."
    )
    distro: str = Field("", title="Distribution", description="For wsl: the distribution's name, such as Ubuntu-22.04.")
    clank_folder: str = Field(
        "~/.clank", title="Clank folder", description="The folder on the host that holds its engines and models."
    )


class ModelFile(Settings):
    """Where a model's file is on a host, outside the host's own models folder."""

    KIND = "model-file"
    LABEL = "Model file"
    HELP = "Where one of the catalog's model files is on a host, when it is kept outside the host's models folder."

    model: str = Field(title="Model", description="The model's id in the catalog.")
    file: str = Field(title="File", description="The file's name, as the catalog lists it.")
    host: str = Field(title="Host", description="The host the file is on.")
    path: str = Field(title="Path", description="Where it is on that host.")


class RuntimeSettings(Settings):
    """How the runtime runs its engines."""

    KIND = "runtime"
    LABEL = "Runtime"
    HELP = "The slots, the port engines listen on, how long starts and health checks may take, and dev mode."
    SINGLE = True

    slots: list[str] = Field(
        default_factory=lambda: ["main", "fast", "vision"],
        title="Slots",
        description="The seats for models: main for the agent's, fast for completion (design 0006), vision for the "
        "model that reads images on the CPU (design 0008).",
    )
    port: int = Field(
        18200,
        ge=1024,
        le=65535,
        title="Engines' port",
        description="Where an engine listens, until the gateway takes this port (design 0001 §9.2).",
    )
    ports: dict[str, int] = Field(
        default_factory=lambda: {"fast": 18201, "vision": 18202},
        title="Slots' ports",
        description="A port of its own for a slot whose engine runs beside another; the rest take the engines' port.",
    )
    model_name: str = Field(
        "",
        title="Model name",
        description=(
            "The model name the gateway puts in each request it passes to the engine; empty: the model's id in "
            "Clank's catalog."
        ),
    )
    tight_mib: int = Field(
        500, ge=0, title="Tight below", description="A fit with less spare GPU memory than this, in MiB, is tight."
    )
    start_seconds: int = Field(
        300, ge=1, title="Time to start", description="How long an engine may take to be ready, in seconds."
    )
    health_seconds: int = Field(30, ge=5, title="Health every", description="How often a running engine is asked.")
    cloud_health_seconds: int = Field(
        300,
        ge=30,
        title="Cloud health every",
        description="How often a cloud model's provider is asked whether it still takes the key (it costs nothing).",
    )
    fallback_preset: str = Field(
        "daily-262k",
        title="Fallback preset",
        description="What clank work, clank code and This folder load when the main slot runs nothing and no "
        "configuration has worked yet (design 0015 §13).",
    )
    dev_mode: bool = Field(
        False,
        title="Dev mode",
        description="For testing (decisions 0149 and 0152): while on, every cloud provider is asked for any of a "
        "model's providers (data_collection allow), those that may keep or train on what they are sent too, whatever "
        "its own record says, from the next request; and every workspace's agent reaches every public host at once, "
        "without a question (private addresses still never), OpenCode fetching and searching the web from its next "
        "start. The console's header says so. clank dev on, clank dev off.",
    )

    def port_of(self, slot: str) -> int:
        """The port a slot's engine listens on: its own, else the engines' port."""
        return self.ports.get(slot, self.port)
