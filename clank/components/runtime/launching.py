"""From a preset to exactly what would run, where, and whether it can (design 0003 §6.1 and §6.5).

A launch is planned from the preset; its engine adapter at its version; the catalog's model and the file in the format
that engine reads; the engine's install on a host (the preset's host, or the one host its engine is installed on); and
where the model's files are on that host (a `model-file` record, else the host's `models/` folder, laid out as
`<repository>/<revision>/<file>`); its memory estimate learns from the last launch of the same engine on the same
host that measured what it took (the difference from that launch's own estimate is added, and said: design 0001 §3.6).
The check walks the same road item by item and stops where it cannot go on: the
preset is valid; the engine is installed; its program is there; the model's files are there at their size (and a
projector, when the plan gives the engine one); the engine's own `--help` lists every flag the plan gives it; and the
plan fits in the GPU's free memory. A check starts nothing.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import EngineAdapter, Launch, Plan, flags
from clank.components.runtime.catalog import ModelEntry, ModelFileEntry, catalog, preset_problems
from clank.components.runtime.gpu import fit
from clank.components.runtime.hosts.host import EngineHost
from clank.components.runtime.kinds import ModelFile, Preset
from clank.components.runtime.state import InstallRecord
from clank.kernel.settings import Loaded

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

Status = Literal["passed", "failed", "unknown"]
RUNS = ("starting", "ready", "stopping")
PRESET_OPTION_WORDS = ("context ", "max_output ", "reasoning ", "images ", "openrouter has no preset option")


class LaunchError(Exception):
    """A preset that cannot be launched as it is, and why."""


@dataclass(frozen=True)
class CheckItem:
    """One item of a check: what was checked, whether it passed, and why."""

    name: str
    status: Status
    detail: str


@dataclass(frozen=True)
class Prepared:
    """A launch ready to start: the preset, its engine, where it runs, and its plan."""

    preset_id: str
    preset: Preset
    engine: EngineAdapter
    host_name: str
    host: EngineHost
    install: InstallRecord
    model: ModelEntry
    plan: Plan


def preset_of(runtime: "Runtime", name: str) -> tuple[str, Preset]:
    """The preset of that id or title, as a record."""
    view = runtime.preset(name)
    values = {key: value for key, value in view.items() if key in Preset.model_fields}
    values["title"] = view["title"]
    return view["id"], Preset.model_validate(values)


def models(runtime: "Runtime") -> dict[str, ModelEntry]:
    """The catalog the runtime uses."""
    return dict(runtime.models) if runtime.models is not None else catalog()


def install_of(runtime: "Runtime", preset: Preset) -> InstallRecord:
    """The install that runs the preset: on its host, or on the one host its engine is installed on."""
    engine = ENGINES.get(preset.engine)
    found = [
        install
        for install in runtime.state.installs()
        if (install.setup, install.version) == (preset.engine, preset.engine_version)
        and (not preset.host or install.host == preset.host)
    ]
    if len(found) == 1:
        return found[0]
    where = f"on {preset.host}" if preset.host else "on any host"
    if not found:
        raise LaunchError(
            f"{engine.LABEL} {preset.engine_version} is not installed {where}: "
            f"`clank engine install {preset.engine} --version {preset.engine_version}`"
        )
    hosts = ", ".join(install.host for install in found)
    raise LaunchError(f"{engine.LABEL} {preset.engine_version} is installed on several hosts ({hosts}): name one")


def running_on(runtime: "Runtime", host_name: str) -> list[tuple[str, str, Preset | None]]:
    """What the slots run on a host now (starting, ready or stopping): each slot's name, the title of what it runs, and
    its preset; None when that preset is gone since, so nothing says what it uses and whoever asks assumes the worst."""
    from clank.components.runtime.service import PresetNotFound

    found: list[tuple[str, str, Preset | None]] = []
    for slot in runtime.state.slots(runtime.settings().slots):
        if slot.status not in RUNS or slot.host != host_name or slot.preset is None:
            continue
        preset: Preset | None
        try:
            _, preset = preset_of(runtime, slot.preset)
        except PresetNotFound:
            preset = None
        found.append((slot.name, runtime.title(slot.preset), preset))
    return found


def model_record(runtime: "Runtime", model: ModelEntry, file: ModelFileEntry, host_name: str) -> Loaded | None:
    """The `model-file` record that says where the user keeps a model's file on a host, if there is one."""
    for loaded in runtime.kernel.settings.records("model-file"):
        record = ModelFile.model_validate(loaded.record.model_dump())
        if (record.model, record.file, record.host) == (model.id, file.path, host_name):
            return loaded
    return None


def file_path(runtime: "Runtime", model: ModelEntry, file: ModelFileEntry, host_name: str, host: EngineHost) -> str:
    """Where a model's file is on a host: its `model-file` record's path, else in the host's models folder."""
    loaded = model_record(runtime, model, file, host_name)
    if loaded is not None:
        return host.expand(ModelFile.model_validate(loaded.record.model_dump()).path)
    return default_path(runtime, file, host_name, host)


def clank_folder(runtime: "Runtime", host_name: str) -> str:
    """A host's Clank folder, as its record says it (`~` not expanded), which holds its engines and models."""
    return str(next(found["clank_folder"] for found in runtime.hosts() if found["name"] == host_name))


def file_place(runtime: "Runtime", model: str, file: ModelFileEntry, host_name: str, host: EngineHost) -> str:
    """Where a model's file is on a host: its `model-file` record's path (one the user adopted), else the host's models
    folder."""
    for loaded in runtime.kernel.settings.records("model-file"):
        record = ModelFile.model_validate(loaded.record.model_dump())
        if (record.model, record.file, record.host) == (model, file.path, host_name):
            return host.expand(record.path)
    return default_path(runtime, file, host_name, host)


def default_path(runtime: "Runtime", file: ModelFileEntry, host_name: str, host: EngineHost) -> str:
    """Where a model's file goes in a host's models folder: `<repository>/<revision>/<file>`."""
    folder = clank_folder(runtime, host_name)
    return host.expand(f"{folder}/models/{file.repository}/{file.revision[:12]}/{file.path}")


def prepare(runtime: "Runtime", name: str, options: Mapping[str, Any] | None = None) -> Prepared:
    """The launch of a preset, planned (with other options, for the last configuration that worked); `LaunchError`
    when it cannot be."""
    preset_id, preset = preset_of(runtime, name)
    if options is not None:
        preset = preset.model_copy(update={"options": dict(options)})
    known = models(runtime)
    problems = preset_problems(preset, known)
    if problems:
        raise LaunchError("; ".join(problems))
    engine = ENGINES.get(preset.engine)(preset.engine_version)
    install = install_of(runtime, preset)
    host = runtime.host(install.host)
    model = known[preset.model]
    weights = model.file(engine.FORMAT)
    assert weights is not None  # preset_problems saw to it
    facts = {"folder": host.expand(install.folder)}
    if install.library_path:
        facts["library_path"] = ":".join(host.expand(part) for part in install.library_path.split(":") if part)
    projector = model.file(engine.FORMAT, "projector")
    if projector is not None:
        facts["projector"] = file_path(runtime, model, projector, install.host, host)
    launch = Launch(
        program=tuple(host.expand(part) for part in install.program),
        model_path=file_path(runtime, model, weights, install.host, host),
        port=runtime.settings().port_of(preset.slot),
        facts=facts,
        sizes=model.sizes(engine.NAME),
    )
    plan = learned(runtime, engine.NAME, install.host, engine.plan(preset.options, launch))
    return Prepared(preset_id, preset, engine, install.host, host, install, model, plan)


def learned(runtime: "Runtime", engine: str, host: str, plan: Plan) -> Plan:
    """The plan with what the last launch of the engine on the host took (or needed free to start, when its engine
    says) beyond its estimate added to its memory."""
    for launch in runtime.state.launches(20, engine=engine, host=host):
        used = launch.needed_mib if launch.needed_mib is not None else launch.measured_mib
        if used is None or launch.estimate_mib is None:
            continue
        difference = used - launch.estimate_mib
        than = "beyond" if difference >= 0 else "below"
        verb = "needed" if launch.needed_mib is not None else "took"
        note = f"learned: {difference:+,} MiB, what launch {launch.id} on {host} {verb} {than} its estimate"
        memory = replace(plan.memory, learned_mib=difference, notes=(*plan.memory.notes, note))
        return replace(plan, memory=memory)
    return plan


def check(runtime: "Runtime", name: str) -> list[CheckItem]:
    """The check of a preset, item by item; it starts nothing. A cloud preset's: its options, then its provider
    (added, agreed to, its key set); the provider's own check asks it (`runtime.endpoint_check`)."""
    preset_id, preset = preset_of(runtime, name)
    if preset.cloud:
        problems = runtime.endpoints.preset_problems(preset)
        options = [problem for problem in problems if problem.startswith(PRESET_OPTION_WORDS)]
        rest = [problem for problem in problems if problem not in options]
        return [
            CheckItem(
                "preset", "failed" if options else "passed", "; ".join(options) or f"valid for {preset.endpoint}"
            ),
            CheckItem(
                "provider",
                "failed" if rest else "passed",
                "; ".join(rest) or f"{preset.endpoint} is agreed to and its key is set",
            ),
        ]
    known = models(runtime)
    problems = preset_problems(preset, known)
    if problems:
        return [CheckItem("preset", "failed", "; ".join(problems))]
    engine = ENGINES.get(preset.engine)(preset.engine_version)
    items = [CheckItem("preset", "passed", f"valid for {engine.LABEL} {preset.engine_version}")]
    try:
        install = install_of(runtime, preset)
    except LaunchError as error:
        return [*items, CheckItem("install", "failed", str(error))]
    items.append(CheckItem("install", "passed", f"{install.setup} {install.version} on {install.host} ({install.how})"))
    prepared = prepare(runtime, preset_id)
    host = prepared.host
    program = host.expand(install.program[0])
    there = host.exists(program)
    items.append(CheckItem("program", "passed" if there else "failed", program if there else f"{program} is not there"))
    model = known[preset.model]
    for role in files_read(engine, preset.options):
        file = model.file(engine.FORMAT, role)
        if file is None:
            items.append(CheckItem(role, "failed", f"{model.id} has no {role} file for {engine.LABEL}"))
            continue
        path = file_path(runtime, model, file, install.host, host)
        size = host.size(path)
        name_of = "model" if role == "weights" else role
        if size is None:
            items.append(CheckItem(name_of, "failed", f"{file.path} is not on {install.host} at {path}"))
        elif size != file.size:
            items.append(
                CheckItem(name_of, "failed", f"{path} has {size:,} bytes, not the {file.size:,} of {file.path}")
            )
        else:
            items.append(CheckItem(name_of, "passed", f"{path} ({file.size:,} bytes)"))
    items.append(_flags(prepared))
    found = fit(prepared.plan.memory, runtime.read_gpu(), runtime.settings().tight_mib)
    status: Status = (
        "unknown" if found.verdict == "unknown" else "failed" if found.verdict == "does not fit" else "passed"
    )
    items.append(CheckItem("fit", status, "; ".join(found.lines)))
    return items


def options_view(engine: EngineAdapter, options: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Each launch option of a preset as clients show it (design 0001 §3.5): its value and where it comes from (the
    preset, else Clank's default, else unset), what the engine receives for it or why nothing, what it maps to and what
    it does, and what the engine does when it is not given it (design 0003 §4.1)."""
    values = engine.resolved(options)
    shown = []
    for option in engine.options():
        gives, why = engine.receives(option, values)
        source = "preset" if option.key in options else "Clank's default" if option.default is not None else "unset"
        shown.append(
            {
                "key": option.key,
                "label": option.label,
                "help": option.help,
                "kind": option.kind,
                "value": values.get(option.key),
                "source": source,
                "gives": list(gives),
                "left_out": "" if gives or why == "no value" else why,
                "maps_to": option.maps_to(),
                "unit": option.unit,
                "memory": option.memory,
                "choices": list(option.choices),
                "minimum": option.minimum,
                "maximum": option.maximum,
                "engine_default": option.engine_default,
                "engine_default_words": option.engine_default_words,
                "more_than": option.more_than,
                "tested": list(option.tested),
            }
        )
    return shown


def plan_view(runtime: "Runtime", name: str) -> dict[str, Any]:
    """A preset's plan as clients show it: its options; then, when it can be planned, its command line, its memory
    estimate and its fit in the GPU's memory now; else why it cannot (`PresetNotFound` for no such preset)."""
    preset_id, preset = preset_of(runtime, name)
    view: dict[str, Any] = {
        "preset": preset_id,
        "title": preset.title or preset_id,
        "engine": preset.engine,
        "engine_version": preset.engine_version,
        "options": [],
        "problem": None,
        "command_line": None,
        "memory": None,
        "fit": None,
    }
    try:
        engine = ENGINES.get(preset.engine)(preset.engine_version)
        view["options"] = options_view(engine, preset.options)
        prepared = prepare(runtime, preset_id)
    except Exception as error:  # an unknown setup, version or option, or a launch that cannot be planned: said as is
        view["problem"] = str(error)
        return view
    memory = prepared.plan.memory
    found = fit(memory, runtime.read_gpu(), runtime.settings().tight_mib)
    view["command_line"] = prepared.plan.command_line()
    view["memory"] = {
        "weights_mib": memory.weights_mib,
        "kv_mib": memory.kv_mib,
        "buffers_mib": memory.buffers_mib,
        "overhead_mib": memory.overhead_mib,
        "learned_mib": memory.learned_mib,
        "total_mib": memory.total_mib,
        "notes": list(memory.notes),
    }
    view["fit"] = {"verdict": found.verdict, "spare_mib": found.spare_mib, "lines": list(found.lines)}
    return view


def models_view(runtime: "Runtime") -> list[dict[str, Any]]:
    """The catalog's models as clients show them: each file, and where it is on each host whose installed engine reads
    its format (its `model-file` record's path, else the host's models folder), and whether it is there at its size.
    Only those hosts are asked: asking a WSL distribution that does not run starts it."""
    from clank.components.runtime.service import HostNotFound

    readers: dict[str, set[str]] = {}
    for install in runtime.state.installs():
        if install.setup in {adapter.NAME for adapter in ENGINES.all()}:
            readers.setdefault(ENGINES.get(install.setup).FORMAT, set()).add(install.host)
    records = {}
    for loaded in runtime.kernel.settings.records("model-file"):
        record = ModelFile.model_validate(loaded.record.model_dump())
        records[(record.model, record.file, record.host)] = record.path
    shown = []
    for model in models(runtime).values():
        files = []
        for file in model.files:
            hosts = []
            for name in sorted(readers.get(file.format, set())):
                try:
                    host = runtime.host(name)
                except HostNotFound:
                    continue
                recorded = records.get((model.id, file.path, name))
                path = host.expand(recorded) if recorded else default_path(runtime, file, name, host)
                size = host.size(path)  # the same place `file_place` names
                how = "adopted" if recorded else "models folder"
                hosts.append({"host": name, "path": path, "how": how, "present": size == file.size, "size": size})
            files.append(
                {
                    "format": file.format,
                    "role": file.role,
                    "path": file.path,
                    "size": file.size,
                    "sha256": file.sha256,
                    "repository": file.repository,
                    "revision": file.revision,
                    "notes": file.notes,
                    "hosts": hosts,
                }
            )
        shown.append({"id": model.id, "name": model.name, "files": files})
    return shown


def files_read(engine: EngineAdapter, options: Mapping[str, Any]) -> list[str]:
    """The model's files a launch reads: its weights, and its projector when an option gives the engine its path
    (KVMem's `--mmproj`; an engine whose model file holds its vision reads no projector)."""
    values = engine.resolved(options)
    given = (part for option in engine.options() if option.key in values for part in option.mapped(values[option.key]))
    return ["weights", *(["projector"] if any("{projector}" in part for part in given) else [])]


def _flags(prepared: Prepared) -> CheckItem:
    """Whether the engine's own `--help` lists every flag the plan gives it."""
    argv = prepared.plan.argv
    used = [part for option in prepared.engine.options() for part in flags(option) if part in argv]
    used += [part for part in ("--host", "--port") if part in argv]
    help_text = prepared.host.output([*prepared.plan.argv[: len(prepared.install.program)], "--help"])
    if help_text is None:
        return CheckItem("flags", "unknown", "its --help did not answer")
    missing = [flag for flag in dict.fromkeys(used) if flag not in help_text]
    if missing:
        return CheckItem("flags", "failed", f"its --help does not list {', '.join(missing)}")
    return CheckItem("flags", "passed", f"its --help lists all {len(set(used))} flags the plan gives it")
