"""Write `clank/schemas/<kind>.schema.json`: the JSON Schema of every settings kind's files (decision 0015).

Generated from each kind's one definition, never edited by hand, and checked by a test, so an editor that knows JSON
Schema can check a settings file as it is typed. `default_problems` reads Clank's own defaults (`clank/defaults/`) the
way the service does, so a default that does not read is caught here and not on a user's machine.
"""

import json
import sys
from pathlib import Path
from typing import Any

from clank import registry
from clank.kernel.clock import SystemClock
from clank.kernel.events import EventLog
from clank.kernel.home import Home
from clank.kernel.records import Settings
from clank.kernel.settings import DEFAULTS, SettingsFiles, SettingsProblem
from clank.kernel.store import Store, kernel_migrations

FOLDER = Path("clank/schemas")
COMMAND = "uv run python -m tools.schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def schema(kind: type[Settings]) -> dict[str, Any]:
    """The JSON Schema of a settings kind's files: its fields, their labels and help, and the "schema" constant."""
    body = kind.model_json_schema()
    properties: dict[str, Any] = {
        "schema": {
            "const": f"{kind.KIND}/{kind.VERSION}",
            "title": "Schema",
            "description": "The kind and version this file is written in; always its first field.",
        }
    }
    properties.update(body.get("properties", {}))
    generated: dict[str, Any] = {
        "$schema": DIALECT,
        "title": kind.LABEL,
        "description": kind.HELP,
        "type": "object",
        "properties": properties,
        "required": ["schema", *body.get("required", [])],
        "additionalProperties": False,
    }
    if "$defs" in body:
        generated["$defs"] = body["$defs"]
    return generated


def render_all() -> dict[str, str]:
    """Every schema file's name and text."""
    return {
        f"{kind.KIND}.schema.json": json.dumps(schema(kind), indent=2, ensure_ascii=False) + "\n"
        for kind in registry.kinds().settings()
    }


def default_problems(scratch: Path) -> list[SettingsProblem]:
    """The problems found reading Clank's own default settings, with an empty CLANK_HOME under `scratch`."""
    store = Store(None)
    try:
        store.migrate(kernel_migrations())
        clock = SystemClock()
        files = SettingsFiles(
            Home(scratch / "home"),
            registry.kinds().settings(),
            events=EventLog(store, clock, registry.event_types()),
            clock=clock,
            defaults=DEFAULTS,
        )
        return files.load()
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    """Write the schemas (removing those of kinds that are gone), or with `--check` only compare; returns the status."""
    args = sys.argv[1:] if argv is None else argv
    folder = Path(__file__).resolve().parents[1] / FOLDER
    expected = render_all()
    found = {path.name: path for path in folder.glob("*.schema.json")} if folder.is_dir() else {}
    if "--check" in args:
        stale = sorted(set(found) - set(expected))
        differ = sorted(name for name, text in expected.items() if name not in found or _text(found[name]) != text)
        if stale or differ:
            print(f"the schemas are out of date ({', '.join(stale + differ)}): run `{COMMAND}`", file=sys.stderr)
            return 1
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in expected.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    for name in set(found) - set(expected):
        found[name].unlink()
    print(f"wrote {len(expected)} schema(s)")
    return 0


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


if __name__ == "__main__":
    sys.exit(main())
