"""Design 0002 §2.2 and design 0013 §11 (decision 0066): a settings kind may keep its records one folder deeper, grouped
(a flow is `config/flows/<workspace>/<name>.json`): each record is named by its group and its name, read, written over
its revision and recorded like any other; a file that belongs to no group is reported; an id never reaches outside the
kind's folder; and the record routes read and write a grouped record by its id."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import Field

from clank import registry
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.components import Component
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor, EventLog
from clank.kernel.home import Home
from clank.kernel.records import Settings
from clank.kernel.settings import SettingsError, SettingsFiles
from clank.kernel.store import Store

YOU = Actor(kind="user", via="console")
TOKEN = "test-token-0123456789abcdefghijklmnopqrstuvwxyz"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Clank-Client": "console"}


class Note(Settings):
    KIND = "note"
    LABEL = "Note"
    HELP = "A kind kept by workspace, for these tests."
    GROUPED_BY = "workspace"

    text: str = Field("", title="Text", description="What it says.")


@pytest.fixture
def files(home: Home, store: Store, clock: FakeClock, tmp_path: Path) -> SettingsFiles:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    files = SettingsFiles(
        home, [Note], events=EventLog(store, clock, registry.event_types()), clock=clock, defaults=defaults
    )
    files.load()
    return files


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def test_a_grouped_kinds_records_are_read_from_a_folder_per_group_each_named_by_its_group_and_its_name(
    home: Home, files: SettingsFiles
) -> None:
    write(home.config / "notes" / "myproject" / "study.json", '{"schema": "note/1", "text": "a study"}')
    write(home.config / "notes" / "myproject" / "sweep.json", '{"schema": "note/1", "text": "a sweep"}')
    write(home.config / "notes" / "other" / "study.json", '{"schema": "note/1", "text": "another"}')
    assert files.load() == []
    found = {loaded.id: loaded.record.model_dump()["text"] for loaded in files.records("note")}
    assert found == {"other/study": "another", "myproject/study": "a study", "myproject/sweep": "a sweep"}
    assert files.get("note", "myproject/study").path == home.config / "notes" / "myproject" / "study.json"


def test_a_file_directly_in_a_grouped_kinds_folder_is_reported_saying_where_it_belongs(
    home: Home, files: SettingsFiles
) -> None:
    stray = write(home.config / "notes" / "study.json", '{"schema": "note/1"}')
    problems = files.load()
    assert [(problem.path, problem.field) for problem in problems] == [(stray, None)]
    assert "notes/<workspace>/<name>.json" in problems[0].message
    assert files.records("note") == []


def test_a_grouped_record_is_written_into_its_groups_folder_over_its_revision_and_refused_over_another(
    home: Home, files: SettingsFiles
) -> None:
    written = files.write("note", "myproject/study", {"text": "first"}, base=None, actor=YOU)
    assert written.path == home.config / "notes" / "myproject" / "study.json"
    files.write("note", "myproject/study", {"text": "second"}, base=written.revision, actor=YOU)
    with pytest.raises(SettingsError, match="changed since it was read"):
        files.write("note", "myproject/study", {"text": "third"}, base=written.revision, actor=YOU)


@pytest.mark.parametrize(
    "id", ["study", "myproject/../study", "../escape/study", "myproject/", "a/b/c", "myproject\\study", "/study"]
)
def test_an_id_that_names_no_group_or_climbs_out_of_the_kinds_folder_is_refused(
    home: Home, files: SettingsFiles, id: str
) -> None:
    with pytest.raises(SettingsError, match="cannot name a note"):
        files.write("note", id, {"text": "x"}, base=None, actor=YOU)
    assert [path for path in home.root.rglob("*.json")] == []


@pytest.fixture
def api(home: Home, clock: FakeClock) -> Iterator[TestClient]:
    kernel: Kernel = open_kernel(
        home, clock, [Component(name="notes", summary="Notes, for these tests.", kinds=(Note,))]
    )
    with TestClient(create_app(kernel, token=TOKEN, port=7720), base_url="http://127.0.0.1:7720") as client:
        yield client
    kernel.close()


def test_the_record_routes_read_and_write_a_grouped_record_by_its_id(api: TestClient, home: Home) -> None:
    put = api.put("/api/v1/records/note/myproject/study", headers=AUTH, json={"values": {"text": "hi"}, "base": None})
    assert put.status_code == 200, put.text
    assert put.json()["id"] == "myproject/study"
    assert (home.config / "notes" / "myproject" / "study.json").is_file()
    got = api.get("/api/v1/records/note/myproject/study", headers=AUTH)
    assert (got.status_code, got.json()["values"]["text"]) == (200, "hi")
    assert [record["id"] for record in api.get("/api/v1/records/note", headers=AUTH).json()] == ["myproject/study"]
    escape = api.put("/api/v1/records/note/..%2F..%2Fescape", headers=AUTH, json={"values": {}, "base": None})
    assert escape.status_code == 409, escape.text
    assert not (home.root / "escape.json").exists()
