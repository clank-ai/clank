"""Design 0002 §2.2 and decision 0007: settings are readable JSON files that name their schema, replace Clank's own
defaults by name, are written in one fixed format only over the version they were read from, report any problem with
its file, line and field while the last good values stay in force, and record every change, told to their listeners
once no lock is held: a listener may wait for another thread that reads the settings (the event stream waits for the
service's event loop, where the flows' driver reads them)."""

import json
import threading
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, Field

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, Event, EventLog
from clank.kernel.home import Home
from clank.kernel.records import Migration, Settings
from clank.kernel.settings import SettingsError, SettingsFiles, render
from clank.kernel.store import Store

YOU = Actor(kind="user", via="console")


def louder(data: dict[str, Any]) -> dict[str, Any]:
    """Version 1 called the level "volume"."""
    migrated = {key: value for key, value in data.items() if key != "volume"}
    migrated["level"] = data.get("volume", 5)
    return migrated


class Dial(Settings):
    KIND = "dial"
    LABEL = "Dial"
    HELP = "A kind with one record, for these tests."
    SINGLE = True
    VERSION = 2
    MIGRATIONS: ClassVar[dict[int, Migration]] = {1: louder}

    level: int = Field(5, title="Level", description="How loud.")
    color: str = Field("blue", title="Color", description="Its color.")


class Preset(Settings):
    KIND = "preset"
    LABEL = "Preset"
    HELP = "A kind with many records, refused while in use, for these tests."
    ON_CHANGE = "refused"

    context: int = Field(4096, title="Context", description="How many tokens.")


@pytest.fixture
def defaults(tmp_path: Path) -> Path:
    folder = tmp_path / "defaults"
    folder.mkdir()
    return folder


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, registry.event_types())


@pytest.fixture
def files(home: Home, defaults: Path, log: EventLog, clock: FakeClock) -> SettingsFiles:
    in_use = {("preset", "busy"): "the main slot runs it"}
    files = SettingsFiles(
        home, [Dial, Preset], events=log, clock=clock, defaults=defaults, in_use=lambda kind, id: in_use.get((kind, id))
    )
    files.load()
    return files


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def kept(log: EventLog, type: str) -> list[Event]:
    return log.after(0, types=[type])


def test_a_single_record_kind_without_a_file_has_its_built_in_values(files: SettingsFiles) -> None:
    dial = files.get("dial", "dial")
    assert (dial.source, dial.record.model_dump()) == ("built-in", {"title": "", "level": 5, "color": "blue"})


def test_a_user_file_replaces_clanks_default_of_the_same_name(home: Home, defaults: Path, files: SettingsFiles) -> None:
    write(defaults / "presets" / "daily.json", '{"schema": "preset/1", "context": 8192}\n')
    write(defaults / "presets" / "fast.json", '{"schema": "preset/1", "context": 2048}\n')
    write(home.config / "presets" / "daily.json", '{"schema": "preset/1", "context": 262144}\n')
    files.load()
    found = {loaded.id: (loaded.source, loaded.record.model_dump()["context"]) for loaded in files.records("preset")}
    assert found == {"daily": ("user", 262144), "fast": ("default", 2048)}


def test_files_are_written_in_one_fixed_format() -> None:
    text = render(Dial(title="Main dial", level=7))
    assert text == '{\n  "schema": "dial/2",\n  "title": "Main dial",\n  "level": 7\n}\n'


def test_a_byte_order_mark_is_accepted(home: Home, files: SettingsFiles) -> None:
    (home.config / "dial.json").write_bytes(b'\xef\xbb\xbf{"schema": "dial/2", "level": 3}\n')
    assert files.load() == []
    assert files.get("dial", "dial").record.model_dump()["level"] == 3


def test_invalid_json_is_reported_with_its_line_and_the_last_good_values_stay(
    home: Home, files: SettingsFiles, log: EventLog
) -> None:
    path = write(home.config / "dial.json", '{"schema": "dial/2", "level": 3}\n')
    files.load()
    write(path, '{\n  "schema": "dial/2"\n  "level": 4\n}\n')  # a comma missing: line 3 in every Python's words
    [problem] = files.load()
    assert (problem.path, problem.line) == (path, 3)
    assert "not valid JSON" in problem.message
    assert files.get("dial", "dial").record.model_dump()["level"] == 3
    assert [event.data["line"] for event in kept(log, "settings.invalid")] == [3]


def test_a_wrong_type_and_an_unknown_field_are_reported_with_file_line_and_field(
    home: Home, files: SettingsFiles
) -> None:
    path = write(home.config / "dial.json", '{\n  "schema": "dial/2",\n  "level": "loud",\n  "shade": "red"\n}\n')
    problems = files.load()
    assert sorted((p.path, p.line, p.field) for p in problems) == [(path, 3, "level"), (path, 4, "shade")]
    assert any("not a field of dial" in p.message for p in problems)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"level": 3}\n', "names no schema"),
        ('{"schema": "preset/1", "level": 3}\n', "names the schema preset/1"),
        ('{"schema": "dial/3", "level": 3}\n', "written by a newer Clank"),
    ],
)
def test_a_file_without_its_own_current_schema_is_reported(
    home: Home, files: SettingsFiles, text: str, expected: str
) -> None:
    write(home.config / "dial.json", text)
    [problem] = files.load()
    assert expected in problem.message


def test_an_older_file_is_migrated_and_its_original_kept(home: Home, files: SettingsFiles, log: EventLog) -> None:
    path = write(home.config / "dial.json", '{"schema": "dial/1", "volume": 9}\n')
    assert files.load() == []
    assert files.get("dial", "dial").record.model_dump()["level"] == 9
    assert json.loads(path.read_text(encoding="utf-8")) == {"schema": "dial/2", "level": 9}
    assert (home.config / "dial.v1.json").read_text(encoding="utf-8") == '{"schema": "dial/1", "volume": 9}\n'
    assert [event.data["original"] for event in kept(log, "settings.migrated")] == ["config/dial.v1.json"]


def test_a_write_based_on_an_old_revision_is_refused_with_the_current_version(home: Home, files: SettingsFiles) -> None:
    first = files.write("preset", "daily", {"context": 8192}, base=None, actor=YOU)
    write(home.config / "presets" / "daily.json", '{"schema": "preset/1", "context": 16384}\n')
    with pytest.raises(SettingsError, match="changed since") as refused:
        files.write("preset", "daily", {"context": 32768}, base=first.revision, actor=YOU)
    current = refused.value.current
    assert current is not None
    assert current.record.model_dump()["context"] == 16384


def test_a_change_to_a_record_in_use_is_refused_when_its_kind_says_so(files: SettingsFiles) -> None:
    with pytest.raises(SettingsError, match="the main slot runs it"):
        files.write("preset", "busy", {"context": 8192}, base=None, actor=YOU)


def test_a_write_records_each_fields_old_and_new_value(files: SettingsFiles, log: EventLog) -> None:
    built_in = files.get("dial", "dial")
    files.write("dial", "dial", {"level": 8, "color": "blue"}, base=built_in.revision, actor=YOU)
    [event] = kept(log, "settings.changed")
    assert event.data["changes"] == [{"field": "level", "old": 5, "new": 8}]
    assert event.actor == YOU
    assert event.summary == "you (console) changed Dial: level"


def test_a_file_edited_on_disk_is_reloaded_and_recorded_as_changed_by_a_person(
    home: Home, files: SettingsFiles, log: EventLog
) -> None:
    write(home.config / "dial.json", '{"schema": "dial/2", "color": "green"}\n')
    [event] = files.reload_changed()
    assert event.actor == Actor(kind="user", via="file")
    assert event.data["changes"] == [{"field": "color", "old": "blue", "new": "green"}]
    assert files.reload_changed() == []


def test_deleting_a_user_file_brings_clanks_default_back(home: Home, defaults: Path, files: SettingsFiles) -> None:
    write(defaults / "presets" / "daily.json", '{"schema": "preset/1", "context": 8192}\n')
    files.load()
    changed = files.write("preset", "daily", {"context": 9000}, base=files.get("preset", "daily").revision, actor=YOU)
    files.delete("preset", "daily", base=changed.revision, actor=YOU)
    assert files.get("preset", "daily").source == "default"
    with pytest.raises(SettingsError, match="Clank's own"):
        files.delete("preset", "daily", base=files.get("preset", "daily").revision, actor=YOU)


class Inner(BaseModel):
    level: int = Field(1, title="Level", description="How loud, inside.")


class Rig(Settings):
    KIND = "rig"
    LABEL = "Rig"
    HELP = "A kind whose fields nest and repeat a name, for these tests."
    SINGLE = True

    level: int = Field(5, title="Level", description="How loud.")
    inner: Inner = Field(default_factory=Inner, title="Inner", description="A nested record.")
    steps: list[Inner] = Field(default_factory=list, title="Steps", description="Nested records in a list.")


def test_a_problem_in_a_nested_or_repeated_field_names_that_fields_own_line(
    home: Home, defaults: Path, log: EventLog, clock: FakeClock
) -> None:
    files = SettingsFiles(home, [Rig], events=log, clock=clock, defaults=defaults, in_use=lambda kind, id: None)
    lines = [
        "{",
        '  "schema": "rig/1",',
        '  "level": 2,',
        '  "inner": {',
        '    "level": "high"',
        "  },",
        '  "steps": [',
        '    {"level": 1},',
        "    {",
        '      "level": "low"',
        "    }",
        "  ]",
        "}",
    ]
    write(home.config / "rig.json", "\n".join(lines) + "\n")
    found = sorted((problem.field, problem.line) for problem in files.load())
    assert found == [("inner.level", 5), ("steps.1.level", 10)]


def readers_waited_for(log: EventLog, files: SettingsFiles) -> list[str]:
    """A listener that, on each settings event, has another thread read the settings and waits for it, as the event
    stream's listener waits for the service's event loop: the events during which that read could not finish."""
    waited: list[str] = []

    def read(done: threading.Event) -> None:
        files.records("preset")
        files.get("dial", "dial")
        done.set()

    def listener(event: Event) -> None:
        if not event.type.startswith("settings."):
            return
        done = threading.Event()
        threading.Thread(target=read, args=(done,), daemon=True).start()
        if not done.wait(5):
            waited.append(event.type)

    log.subscribe(listener)
    return waited


def test_a_change_is_told_with_no_lock_held_so_a_listener_may_wait_for_a_reader(
    home: Home, defaults: Path, files: SettingsFiles, log: EventLog
) -> None:
    write(defaults / "presets" / "daily.json", '{"schema": "preset/1", "context": 8192}\n')
    files.load()
    waited = readers_waited_for(log, files)
    changed = files.write("preset", "daily", {"context": 9000}, base=files.get("preset", "daily").revision, actor=YOU)
    files.delete("preset", "daily", base=changed.revision, actor=YOU)
    write(home.config / "dial.json", '{"schema": "dial/2", "color": "green"}\n')
    files.reload_changed()
    write(home.config / "dial.json", '{"schema": "dial/2", "level": }\n')
    files.reload_changed()
    assert [event.type for event in log.after(0)] == ["settings.changed"] * 3 + ["settings.invalid"]
    assert waited == []
