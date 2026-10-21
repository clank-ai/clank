"""Design 0016 §4 and §6: a cloud provider's record (`config/endpoints/<id>.json`, the kind `endpoint`) is written from
its adapter's template and reads back as the design's record; a URL other than the adapter's (so the key never goes
elsewhere), a reach other than `cloud`, a way of sending the key other than `bearer`, or options the adapter does not
take are refused, naming the file, the line and the field, both when the file is edited and when a client writes it;
an empty `agreed` reads as not agreed."""

import json
from pathlib import Path
from typing import Any

import pytest

from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.components.runtime.kinds import Endpoint
from clank.kernel.events import Actor
from clank.kernel.settings import SettingsError
from tests.components.runtime.conftest import Rig

YOU = Actor(kind="user", via="console")
AGREED = "2026-10-21T09:12:04.120Z"
DESIGNED = {
    "schema": "endpoint/1",
    "title": "OpenRouter",
    "adapter": "openrouter",
    "url": "https://openrouter.ai/api/v1",
    "auth": "bearer",
    "reach": "cloud",
    "options": {"data_collection": "deny", "zdr": False},
    "agreed": AGREED,
    "timeout_seconds": 600,
    "notes": "Added by Add a model.",
}


def edited(rig: Rig, values: dict[str, Any], id: str = "openrouter") -> Path:
    """An endpoint's file written by hand, and the files read again."""
    path = rig.kernel.home.config / "endpoints" / f"{id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    rig.kernel.settings.reload_changed()
    return path


def test_the_template_written_reads_back_as_the_designs_record(rig: Rig) -> None:
    values = {**OpenRouter.template(), "agreed": AGREED, "notes": "Added by Add a model."}
    written = rig.kernel.settings.write("endpoint", "openrouter", values, base=None, actor=YOU)
    designed = Endpoint.model_validate({key: value for key, value in DESIGNED.items() if key != "schema"})
    assert written.record == designed
    assert written.path == rig.kernel.home.config / "endpoints" / "openrouter.json"
    on_disk = json.loads(written.path.read_text(encoding="utf-8"))
    assert on_disk["schema"] == "endpoint/1"
    assert (on_disk["url"], on_disk["reach"], on_disk["auth"]) == (OpenRouter.URL, "cloud", "bearer")
    assert on_disk["options"] == {"data_collection": "deny", "zdr": False}


def test_the_designs_record_edited_by_hand_reads_without_a_problem(rig: Rig) -> None:
    edited(rig, DESIGNED)
    assert rig.kernel.settings.problems() == []
    record = rig.kernel.settings.get("endpoint", "openrouter").record
    assert isinstance(record, Endpoint)
    assert record.is_agreed


@pytest.mark.parametrize(
    ("field", "value", "words"),
    [
        ("url", "https://elsewhere.example/api/v1", "https://openrouter.ai/api/v1"),
        ("reach", "this-machine", "cloud"),
        ("auth", "none", "bearer"),
    ],
)
def test_a_url_a_reach_or_an_auth_other_than_the_adapters_is_refused_naming_the_file_line_and_field(
    rig: Rig, field: str, value: str, words: str
) -> None:
    path = edited(rig, {**DESIGNED, field: value})
    [problem] = rig.kernel.settings.problems()
    assert problem.path == path
    assert problem.field == field
    assert problem.line == list(DESIGNED).index(field) + 2  # the opening brace is line 1
    assert words in problem.message
    with pytest.raises(SettingsError):
        rig.kernel.settings.get("endpoint", "openrouter")
    values = {**OpenRouter.template(), field: value}
    with pytest.raises(SettingsError, match=field):
        rig.kernel.settings.write("endpoint", "other", values, base=None, actor=YOU)


def test_options_the_adapter_does_not_take_are_refused_each_by_its_field(rig: Rig) -> None:
    edited(rig, {**DESIGNED, "options": {"data_collection": "maybe", "color": "blue", "zdr": "yes"}})
    fields = {problem.field: problem.message for problem in rig.kernel.settings.problems()}
    assert set(fields) == {"options.data_collection", "options.color", "options.zdr"}
    assert "deny, allow" in fields["options.data_collection"]
    assert "openrouter takes no option color" in fields["options.color"]


def test_an_adapter_clank_does_not_know_is_refused(rig: Rig) -> None:
    edited(rig, {**DESIGNED, "adapter": "elsewhere"})
    [problem] = rig.kernel.settings.problems()
    assert problem.field == "adapter"
    assert "openrouter" in problem.message


def test_an_empty_agreement_reads_as_not_agreed(rig: Rig) -> None:
    edited(rig, {**DESIGNED, "agreed": ""})
    record = rig.kernel.settings.get("endpoint", "openrouter").record
    assert isinstance(record, Endpoint)
    assert not record.is_agreed
    assert Endpoint.model_validate(OpenRouter.template()).is_agreed is False
