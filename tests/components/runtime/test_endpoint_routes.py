"""Design 0016 §4, §6, §9, §10 and §14: adding a cloud provider needs the owner's agreement, writes its record from the
adapter's template with `agreed` and marks the MCP servers the agreement screen marked local only (every one already
added when none are named); its key is kept only once OpenRouter accepts it, in `secrets/endpoint/openrouter/key`,
shown by its last four, and never in any answer, event or log; a refused key is not kept and says why; the account is
read with the key at most once a minute; changing the record's options or withdrawing the agreement is recorded; and
removing the provider removes its key with it. An MCP server added without saying which, while a provider is agreed,
is local only; before any is, it is not. Its live list of models is read with the key: the models that take
tool calls, programming's most used first, narrowed by a search, the free ones, or every one; sorted by price, window
or newest; kept an hour unless asked fresh."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.api import create_app
from clank.kernel.clock import to_text
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import KEY, FakeOpenRouter
from tests.support.served import free_port

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
ROUTES = "/api/v1/runtime/endpoints"


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def servers(rig: Rig, *names: str) -> None:
    """MCP servers of the owner's, added before any provider."""
    tools = rig.kernel.parts["tools"]
    from clank.kernel.events import Actor

    for name in names:
        tools.add(name, {"command": "python", "args": ["-V"]}, scope="user", folder="", actor=Actor(kind="user"))


def local(rig: Rig) -> dict[str, bool]:
    return {server["name"]: server["local_only"] for server in rig.kernel.parts["tools"].servers()}


def test_adding_a_provider_without_the_agreement_is_refused(rig: Rig, http: TestClient) -> None:
    answer = http.post(ROUTES, json={"id": "openrouter", "adapter": "openrouter"}, headers=AUTH)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "agreement_needed"
    assert not (rig.kernel.home.config / "endpoints" / "openrouter.json").exists()


def test_adding_writes_the_template_agreed_now_and_marks_the_mcp_servers_named(rig: Rig, http: TestClient) -> None:
    servers(rig, "lit", "plotter")
    asked = {"id": "openrouter", "adapter": "openrouter", "agree": True, "local_mcp": ["lit"]}
    answer = http.post(ROUTES, json=asked, headers=AUTH)
    assert answer.status_code == 201, answer.text
    view = answer.json()
    assert (view["id"], view["title"], view["adapter"], view["reach"]) == ("openrouter", "OpenRouter", "openrouter",
                                                                          "cloud")  # fmt: skip
    assert view["url"] == OpenRouter.URL
    assert view["agreed"] == to_text(rig.clock.now())
    assert view["options"] == {"data_collection": "deny", "zdr": False}
    assert view["key"] == {"set": False, "ends": "", "set_at": ""}
    assert (view["presets"], view["running"], view["check"], view["source"]) == ([], None, None, "user")
    assert view["file"].endswith("openrouter.json")
    assert local(rig) == {"lit": True, "plotter": False}
    [added] = rig.kernel.events.latest(types=["runtime.endpoint_added"])
    assert (added.data["id"], added.data["adapter"]) == ("openrouter", "openrouter")
    again = http.post(ROUTES, json=asked, headers=AUTH)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "exists")
    assert http.get(ROUTES, headers=AUTH).json() == [view]
    assert http.get(f"{ROUTES}/openrouter", headers=AUTH).json() == view
    assert http.get(f"{ROUTES}/elsewhere", headers=AUTH).status_code == 404


def test_the_agreement_marks_every_mcp_server_already_added_when_none_are_named(rig: Rig, http: TestClient) -> None:
    servers(rig, "lit", "plotter")
    answer = http.post(ROUTES, json={"id": "openrouter", "adapter": "openrouter", "agree": True}, headers=AUTH)
    assert answer.status_code == 201, answer.text
    assert local(rig) == {"lit": True, "plotter": True}


def test_an_mcp_server_is_marked_local_only_or_not_and_one_added_says_which(rig: Rig, http: TestClient) -> None:
    servers(rig, "lit")
    marked = http.put("/api/v1/mcp/servers/lit/local", json={"local_only": True}, headers=AUTH)
    assert (marked.status_code, marked.json()["local_only"]) == (200, True), marked.text
    added = http.post(
        "/api/v1/mcp/servers",
        json={"name": "notes", "entry": {"command": "python"}, "local_only": True},
        headers=AUTH,
    )
    assert (added.status_code, added.json()["local_only"]) == (200, True), added.text
    assert local(rig) == {"lit": True, "notes": True}
    unmarked = http.put("/api/v1/mcp/servers/lit/local", json={"local_only": False}, headers=AUTH)
    assert unmarked.json()["local_only"] is False


def test_an_mcp_server_added_without_saying_which_is_local_only_while_a_provider_is_agreed(
    rig: Rig, http: TestClient
) -> None:
    before = http.post("/api/v1/mcp/servers", json={"name": "plotter", "entry": {"command": "python"}}, headers=AUTH)
    assert (before.status_code, before.json()["local_only"]) == (200, False), "no provider agreed: nothing changes"
    assert http.post(ROUTES, json={"id": "openrouter", "adapter": "openrouter", "agree": True}, headers=AUTH).is_success
    after = http.post("/api/v1/mcp/servers", json={"name": "notes", "entry": {"command": "python"}}, headers=AUTH)
    assert (after.status_code, after.json()["local_only"]) == (200, True), after.text
    said = http.post(
        "/api/v1/mcp/servers", json={"name": "web", "entry": {"command": "python"}, "local_only": False}, headers=AUTH
    )
    assert said.json()["local_only"] is False, "the owner's own word stands"


def test_a_key_openrouter_refuses_is_not_kept_and_says_why(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig, key=False)
    openrouter.key = "another-made-up-key"
    answer = http.put(f"{ROUTES}/openrouter/key", json={"key": KEY}, headers=AUTH)
    assert answer.status_code == 400
    error = answer.json()["error"]
    assert error["code"] == "key_refused"
    assert error["message"].startswith("OpenRouter refused the key")
    assert not (rig.kernel.home.secrets / "endpoint" / "openrouter" / "key").exists()
    assert KEY not in answer.text


def test_a_key_is_not_kept_when_openrouter_does_not_answer(rig: Rig, http: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(OpenRouter, "URL", f"http://127.0.0.1:{free_port()}/api/v1")
    add_openrouter(rig, key=False)
    answer = http.put(f"{ROUTES}/openrouter/key", json={"key": KEY}, headers=AUTH)
    assert (answer.status_code, answer.json()["error"]["code"]) == (502, "cloud_unreachable")
    assert "OpenRouter did not answer" in answer.json()["error"]["message"]
    assert not (rig.kernel.home.secrets / "endpoint" / "openrouter").exists()


def test_a_key_it_takes_is_kept_shown_by_its_last_four_and_never_anywhere_else(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig, key=False)
    answer = http.put(f"{ROUTES}/openrouter/key", json={"key": KEY}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    found = answer.json()
    assert found["key"] == {"set": True, "ends": KEY[-4:], "set_at": to_text(rig.clock.now())}
    assert (found["account"]["label"], found["account"]["remaining_usd"]) == ("made-up key label", 18.71)
    assert openrouter.sent[-1].headers["authorization"] == f"Bearer {KEY}"
    events = json.dumps([event.model_dump(mode="json") for event in rig.kernel.events.latest(500)])
    texts = [answer.text, http.get(ROUTES, headers=AUTH).text, events]
    texts.append(http.get(f"{ROUTES}/openrouter/account", headers=AUTH).text)
    assert not any(KEY in text for text in texts)
    holding = [
        path.relative_to(rig.kernel.home.root).as_posix()
        for path in rig.kernel.home.root.rglob("*")
        if path.is_file() and KEY.encode() in path.read_bytes()
    ]
    assert holding == ["secrets/endpoint/openrouter/key"]
    [kept] = rig.kernel.events.latest(types=["secret.set"])
    assert (kept.data["scope"], kept.data["name"], kept.data["ends"]) == ("endpoint/openrouter", "key", KEY[-4:])


def test_the_account_is_read_with_the_key_at_most_once_a_minute(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig, key=False)
    assert http.get(f"{ROUTES}/openrouter/account", headers=AUTH).json()["error"]["code"] == "key_not_set"
    add_openrouter_key(rig)
    first = http.get(f"{ROUTES}/openrouter/account", headers=AUTH).json()
    assert (first["label"], first["used_today_usd"], first["days"]) == ("made-up key label", 0.12, "UTC")
    asked = len(openrouter.sent)
    http.get(f"{ROUTES}/openrouter/account", headers=AUTH)
    assert len(openrouter.sent) == asked, "kept for a minute"
    http.get(f"{ROUTES}/openrouter/account?fresh=true", headers=AUTH)
    assert len(openrouter.sent) == asked + 1
    rig.clock.advance(61)
    http.get(f"{ROUTES}/openrouter/account", headers=AUTH)
    assert len(openrouter.sent) == asked + 2
    openrouter.key = "another-made-up-key"
    refused = http.get(f"{ROUTES}/openrouter/account?fresh=true", headers=AUTH)
    assert (refused.status_code, refused.json()["error"]["code"]) == (400, "key_refused")


def add_openrouter_key(rig: Rig) -> None:
    from clank.kernel.events import Actor

    rig.kernel.secrets.put("endpoint/openrouter", "key", KEY, actor=Actor(kind="user", via="console"))


def test_changing_the_options_or_withdrawing_the_agreement_is_recorded(rig: Rig, http: TestClient) -> None:
    add_openrouter(rig, key=False)
    allowed = http.patch(f"{ROUTES}/openrouter", json={"options": {"data_collection": "allow"}}, headers=AUTH)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["options"] == {"data_collection": "allow", "zdr": False}
    wrong = http.patch(f"{ROUTES}/openrouter", json={"options": {"data_collection": "maybe"}}, headers=AUTH)
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (400, "invalid")
    withdrawn = http.patch(f"{ROUTES}/openrouter", json={"agreed": ""}, headers=AUTH)
    assert withdrawn.json()["agreed"] == ""
    changes = [event.data for event in rig.kernel.events.latest(types=["runtime.endpoint_changed"])]
    assert {"id": "openrouter", "fields": ["agreed"]} in changes
    assert {"id": "openrouter", "fields": ["options"]} in changes


def test_removing_the_provider_removes_its_key_with_its_record(rig: Rig, http: TestClient) -> None:
    add_openrouter(rig)
    answer = http.delete(f"{ROUTES}/openrouter", headers=AUTH)
    assert answer.json() == {"removed": "openrouter"}
    assert not (rig.kernel.home.config / "endpoints" / "openrouter.json").exists()
    assert not (rig.kernel.home.secrets / "endpoint" / "openrouter").exists()
    [removed] = rig.kernel.events.latest(types=["runtime.endpoint_removed"])
    assert removed.data == {"id": "openrouter"}
    assert http.get(ROUTES, headers=AUTH).json() == []


def test_removing_the_key_alone_leaves_the_record(rig: Rig, http: TestClient) -> None:
    add_openrouter(rig)
    answer = http.delete(f"{ROUTES}/openrouter/key", headers=AUTH)
    assert answer.json() == {"key": {"set": False, "ends": "", "set_at": ""}}
    assert http.get(f"{ROUTES}/openrouter", headers=AUTH).json()["key"]["set"] is False
    assert json.loads((rig.kernel.home.config / "endpoints" / "openrouter.json").read_text(encoding="utf-8"))


def listed(http: TestClient, query: str = "") -> Any:
    answer = http.get(f"{ROUTES}/openrouter/models{query}", headers=AUTH)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_list_asks_for_tool_models_programmings_most_used_first(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    found = listed(http)
    assert openrouter.sent[-1].query == {"supported_parameters": "tools", "category": "programming",
                                         "sort": "most-popular"}  # fmt: skip
    assert openrouter.sent[-1].headers["authorization"] == f"Bearer {KEY}"
    assert [model["id"] for model in found["models"]] == ["example-vendor/example-coder",
                                                          "example-vendor/example-small:free"]  # fmt: skip
    assert (found["count"], found["sort"], found["read_at"]) == (2, "most-popular", to_text(rig.clock.now()))
    coder = found["models"][0]
    assert (coder["window"], coder["output"], coder["price"]["in"], coder["tools"]) == (262144, 32768, 0.3, True)


def test_a_search_narrows_the_list_by_name_or_id_and_free_shows_the_free_ones(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    assert [model["id"] for model in listed(http, "?search=coder")["models"]] == ["example-vendor/example-coder"]
    assert [model["name"] for model in listed(http, "?search=SMALL")["models"]] == ["Example Small (free)"]
    assert [model["id"] for model in listed(http, "?free=true")["models"]] == ["example-vendor/example-small:free"]


@pytest.mark.parametrize(
    ("sort", "order"),
    [
        ("price", ["example-small:free", "example-chat", "example-coder"]),
        ("context", ["example-coder", "example-chat", "example-small:free"]),
        ("newest", ["example-small:free", "example-coder", "example-chat"]),
    ],
)
def test_the_list_sorts_by_price_window_or_newest_and_all_shows_models_without_tools(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter, sort: str, order: list[str]
) -> None:
    add_openrouter(rig)
    found = listed(http, f"?sort={sort}&all=true")
    assert openrouter.sent[-1].query == {}
    assert [model["id"].removeprefix("example-vendor/") for model in found["models"]] == order
    assert found["sort"] == sort


def test_the_list_is_kept_an_hour_unless_asked_fresh(rig: Rig, http: TestClient, openrouter: FakeOpenRouter) -> None:
    add_openrouter(rig)
    listed(http)
    asked = len(openrouter.sent)
    listed(http, "?search=coder")
    assert len(openrouter.sent) == asked
    listed(http, "?fresh=true")
    assert len(openrouter.sent) == asked + 1
    rig.clock.advance(3601)
    listed(http)
    assert len(openrouter.sent) == asked + 2


def test_the_list_needs_the_key_and_says_when_openrouter_does_not_answer(
    rig: Rig, http: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(OpenRouter, "URL", f"http://127.0.0.1:{free_port()}/api/v1")
    add_openrouter(rig, key=False)
    unset = http.get(f"{ROUTES}/openrouter/models", headers=AUTH)
    assert (unset.status_code, unset.json()["error"]["code"]) == (400, "key_not_set")
    add_openrouter_key(rig)
    silent = http.get(f"{ROUTES}/openrouter/models", headers=AUTH)
    assert (silent.status_code, silent.json()["error"]["code"]) == (502, "cloud_unreachable")
