"""Design 0002 §2.2 and design 0013 §14 (its step 1: an unknown preset is refused): a component may check a kind's
records against other records, which the kind's own validation cannot see (a flow's presets); a record that check finds
wrong is refused when written, naming each field, and its file is reported when read, with its line and field, the last
good values staying in force; and a check added after the files were read checks the records read before."""

from pathlib import Path

import pytest
from pydantic import Field

from clank import registry
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor, EventLog
from clank.kernel.home import Home
from clank.kernel.records import Settings
from clank.kernel.settings import SettingsError, SettingsFiles
from clank.kernel.store import Store

YOU = Actor(kind="user", via="console")
KNOWN = {"daily 262K", "frontier 96K"}


class Step(Settings):
    KIND = "step"
    LABEL = "Step"
    HELP = "A kind whose records name a preset, for these tests."

    model: str = Field("", title="Model", description="The preset it runs on.")


def presets(id: str, record: Settings) -> list[tuple[tuple[str | int, ...], str]]:
    """The test's check: the preset a step names exists."""
    assert isinstance(record, Step)
    if record.model in KNOWN:
        return []
    return [(("model",), f"names the preset {record.model!r}, which does not exist: {', '.join(sorted(KNOWN))}")]


@pytest.fixture
def log(store: Store, clock: FakeClock) -> EventLog:
    return EventLog(store, clock, registry.event_types())


@pytest.fixture
def files(home: Home, log: EventLog, clock: FakeClock, tmp_path: Path) -> SettingsFiles:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    files = SettingsFiles(home, [Step], events=log, clock=clock, defaults=defaults)
    files.load()
    return files


def write(path: Path, model: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f'{{\n  "schema": "step/1",\n  "model": "{model}"\n}}\n'.encode())
    return path


def test_a_record_the_components_check_finds_wrong_is_refused_when_written_naming_each_field(
    home: Home, files: SettingsFiles
) -> None:
    files.check_with("step", presets)
    good = files.write("step", "plan", {"model": "daily 262K"}, base=None, actor=YOU)
    with pytest.raises(SettingsError, match=r"model: names the preset 'dialy 262K'.*daily 262K, frontier 96K") as error:
        files.write("step", "plan", {"model": "dialy 262K"}, base=good.revision, actor=YOU)
    assert error.value.current == good, "the record as it is now comes back, for the client to show beside its own"
    assert files.get("step", "plan").record.model_dump()["model"] == "daily 262K"
    assert '"daily 262K"' in (home.config / "steps" / "plan.json").read_text(encoding="utf-8")


def test_a_file_the_components_check_finds_wrong_is_reported_with_its_line_and_field_and_the_last_good_values_stay(
    home: Home, files: SettingsFiles, log: EventLog
) -> None:
    files.check_with("step", presets)
    path = write(home.config / "steps" / "plan.json", "daily 262K")
    files.reload_changed()
    write(path, "dialy 262K")
    files.reload_changed()
    assert [(p.path, p.line, p.field) for p in files.problems()] == [(path, 3, "model")]
    assert "daily 262K, frontier 96K" in files.problems()[0].message
    assert files.get("step", "plan").record.model_dump()["model"] == "daily 262K", "the last good values stay"
    assert [(event.data["line"], event.data["field"]) for event in log.after(0, types=["settings.invalid"])] == [
        (3, "model")
    ]
    new = write(home.config / "steps" / "sweep.json", "nothing")
    files.reload_changed()
    assert {p.path for p in files.problems()} == {path, new}
    assert [loaded.id for loaded in files.records("step")] == ["plan"], "a new file found wrong is no record"


def test_a_check_added_after_the_files_were_read_checks_the_records_read_before(
    home: Home, files: SettingsFiles
) -> None:
    path = write(home.config / "steps" / "plan.json", "nothing")
    files.load()
    assert [loaded.id for loaded in files.records("step")] == ["plan"]
    files.check_with("step", presets)
    assert [(p.path, p.field) for p in files.problems()] == [(path, "model")]
    assert files.records("step") == []
