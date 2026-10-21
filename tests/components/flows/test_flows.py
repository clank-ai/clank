"""Design 0013 §3, §6, §7, §11 and §14 (decisions 0061, 0063 and 0066): the flows component reads every flow, kept by
workspace in Clank's home, and checks it: the file's own rules, then what needs other records (a preset that does not
exist is refused naming those that do, when the flow is saved and when its file is read; a flow is for the workspace
whose folder keeps it); a file is checked as it is on disk now, and one that is gone is said to be; a good one says the
switches of the main slot a run of it makes; and its `/flows/` routes list, show and check flows."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

D1 = Path(__file__).with_name("d1-flow.json")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


def put(home: Home, place: str, flow: dict[str, Any] | str) -> Path:
    """A flow's file at `config/flows/<place>.json`."""
    path = home.config / "flows" / f"{place}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = flow if isinstance(flow, str) else json.dumps(flow, indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


def d1() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(D1.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "myproject"
    (found / "runs").mkdir(parents=True)
    return found


@pytest.fixture
def kernel(home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    workspace = home.config / "workspaces" / "myproject.json"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.write_text(json.dumps({"schema": "workspace/1", "path": str(folder)}), encoding="utf-8")
    put(home, "myproject/new-study", d1())
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as client:
        yield client


def call(http: TestClient, method: str, path: str, status: int = 200, **body: Any) -> Any:
    answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=body or None)
    assert answer.status_code == status, answer.text
    return answer.json()


def test_the_flows_are_listed_by_workspace_with_their_boxes_and_a_file_that_does_not_read_with_its_place(
    kernel: Kernel, http: TestClient, home: Home, folder: Path
) -> None:
    broken = d1()
    broken["lines"].append({"from": "approve", "to": "plan"})
    put(home, "myproject/broken", broken)
    stray = put(home, "stray", d1())
    kernel.settings.reload_changed()
    listed = call(http, "GET", f"flows?folder={folder / 'runs'}")
    assert listed["workspace"] == "myproject", "a folder inside a workspace's is that workspace's"
    assert listed["folder"] == str(home.config / "flows")
    assert listed["template"].endswith("flow.json")
    assert [(f["id"], f["workspace"], f["name"], f["title"], f["boxes"]) for f in listed["flows"]] == [
        ("myproject/new-study", "myproject", "new-study", "A new simulation study", 11)
    ]
    assert listed["flows"][0]["problems"] == []
    unreadable = {Path(p["file"]).name: p for p in listed["unreadable"]}
    assert set(unreadable) == {"broken.json", "stray.json"}
    assert (unreadable["broken.json"]["field"], unreadable["broken.json"]["line"]) == ("lines.14.to", 226)
    assert "belongs to no workspace" in unreadable["stray.json"]["message"]
    assert Path(unreadable["stray.json"]["file"]) == stray
    assert call(http, "GET", "flows?workspace=elsewhere")["flows"] == []


def test_a_flow_is_shown_by_its_name_in_its_workspace_or_by_its_title(http: TestClient, home: Home) -> None:
    shown = call(http, "GET", "flows/myproject/new-study")
    assert (shown["id"], shown["title"], shown["source"]) == ("myproject/new-study", "A new simulation study", "user")
    assert shown["file"] == str(home.config / "flows" / "myproject" / "new-study.json")
    assert shown["values"]["lines"][3] == {"from": "check", "to": "plan", "when": "fail"}
    assert shown["values"]["boxes"][6]["writes"] == ["runs/estimates.md"]
    assert call(http, "GET", "flows/myproject/a new simulation STUDY")["id"] == "myproject/new-study"


def saved(http: TestClient, id: str, flow: dict[str, Any], status: int) -> Any:
    """`PUT /records/flow/<id>`, the generic save every client may use, over the flow's revision now."""
    current = http.get(f"/api/v1/records/flow/{id}", headers=AUTH)
    base = current.json()["revision"] if current.status_code == 200 else None
    values = {key: value for key, value in flow.items() if key != "schema"}
    return call(http, "PUT", f"records/flow/{id}", status, values=values, base=base)


def test_an_unknown_preset_is_refused_naming_those_that_exist(kernel: Kernel, http: TestClient, home: Home) -> None:
    flow = d1()
    flow["boxes"][6]["model"] = "fast 8K"
    flow["boxes"][7]["model"] = "completion 0.5B"
    flow["boxes"][8]["model"] = "frontier-96k"
    refused = saved(http, "myproject/new-study", flow, 409)["error"]["message"]
    assert "boxes.6.model: names the preset 'fast 8K'" in refused
    assert "daily 262K, frontier 262K, frontier 262K lean, frontier 96K" in refused
    assert "boxes.7.model: completion 0.5B is a preset for the fast slot" in refused
    assert "frontier-96k" not in refused, "a preset is named by its id or its title"
    path = put(home, "myproject/new-study", flow)
    kernel.settings.reload_changed()
    invalid = kernel.events.after(0, types=["settings.invalid"])
    assert [event.data["field"] for event in invalid] == ["boxes.6.model", "boxes.7.model"]
    shown = call(http, "GET", "flows/myproject/new-study")
    assert shown["values"]["boxes"][6]["model"] == "", "the last good flow stays in force"
    assert [p["field"] for p in shown["problems"]] == ["boxes.6.model", "boxes.7.model"]
    checked = call(http, "POST", "flows/check", flow="myproject/new-study")
    assert checked["file"] == str(path)
    problems = {p["field"]: p for p in checked["problems"]}
    assert set(problems) == {"boxes.6.model", "boxes.7.model"}, "a preset is named by its id or its title"
    unknown = problems["boxes.6.model"]
    assert path.read_text(encoding="utf-8").splitlines()[unknown["line"] - 1].strip() == '"model": "fast 8K"'
    assert "fast 8K" in unknown["message"]
    assert "daily 262K, frontier 262K, frontier 262K lean, frontier 96K" in unknown["message"]
    assert "the fast slot" in problems["boxes.7.model"]["message"]


def test_a_flow_is_for_the_workspace_whose_folder_keeps_it(http: TestClient, home: Home) -> None:
    refused = saved(http, "other/new-study", d1(), 409)["error"]["message"]
    assert "workspace: names the workspace myproject, but it is kept in other's folder" in refused
    nameless = {key: value for key, value in d1().items() if key != "workspace"}
    assert "no workspace named other" in saved(http, "other/new-study", nameless, 409)["error"]["message"]
    assert not (home.config / "flows" / "other").exists()
    put(home, "other/new-study", d1())
    elsewhere = call(http, "POST", "flows/check", file=str(home.config / "flows" / "other" / "new-study.json"))
    assert [(p["field"], p["line"]) for p in elsewhere["problems"]] == [("workspace", 4)]
    assert "myproject" in elsewhere["problems"][0]["message"]
    assert "other" in elsewhere["problems"][0]["message"]
    nameless = d1()
    del nameless["workspace"]
    put(home, "nowhere/new-study", nameless)
    unknown = call(http, "POST", "flows/check", file=str(home.config / "flows" / "nowhere" / "new-study.json"))
    assert [p["field"] for p in unknown["problems"]] == [None]
    assert "no workspace named nowhere" in unknown["problems"][0]["message"]


def test_a_file_is_checked_as_it_is_on_disk_now_before_the_service_reads_it_again(
    http: TestClient, home: Home, tmp_path: Path
) -> None:
    broken = d1()
    broken["boxes"][1]["writes"].append("grid.json")
    put(home, "myproject/new-study", broken)
    checked = call(http, "POST", "flows/check", flow="myproject/new-study")
    assert [p["field"] for p in checked["problems"]] == ["boxes.1.writes.1"]
    assert call(http, "GET", "flows/myproject/new-study")["values"]["boxes"][1]["writes"] == ["PLAN.md"]
    draft = tmp_path / "draft.json"
    shutil.copy(D1, draft)
    checked = call(http, "POST", "flows/check", file=str(draft))
    shown = {key: checked[key] for key in ("file", "flow", "problems", "warnings")}
    assert shown == {"file": str(draft), "flow": None, "problems": [], "warnings": []}
    assert [each["box"] for each in checked["switches"]] == ["plan"], "a good file says the switches a run makes"


def test_a_flow_whose_file_is_gone_is_listed_shown_and_checked_saying_so_until_the_service_reads_again(
    kernel: Kernel, http: TestClient, home: Home
) -> None:
    path = home.config / "flows" / "myproject" / "new-study.json"
    path.unlink()
    listed = call(http, "GET", "flows")["flows"]
    assert [(p["file"], p["line"], p["field"]) for p in listed[0]["problems"]] == [(str(path), None, None)]
    assert "is gone" in listed[0]["problems"][0]["message"]
    assert "is gone" in call(http, "GET", "flows/myproject/new-study")["problems"][0]["message"]
    assert "is gone" in call(http, "POST", "flows/check", flow="myproject/new-study")["problems"][0]["message"]
    kernel.settings.reload_changed()
    assert call(http, "GET", "flows")["flows"] == []


def test_a_flow_that_does_not_exist_is_not_found_naming_where_flows_are_kept(http: TestClient, home: Home) -> None:
    missing = call(http, "GET", "flows/myproject/nothing", status=404)
    assert str(home.config / "flows" / "myproject") in missing["error"]["message"]
    assert (
        call(http, "POST", "flows/check", status=404, file=str(home.root / "none.json"))["error"]["code"] == "not_found"
    )
    assert call(http, "POST", "flows/check", status=400, flow="no-workspace")["error"]["code"] == "invalid"
