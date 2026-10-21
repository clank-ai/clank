"""Design 0016 §12 (decision 0108): each cloud request's cost is OpenRouter's own figure, its stream's or whole answer's
`usage.cost` (`how`: `usage`), kept in its record and appended to the gateway's spool with its tokens, its generation,
its session and workspace; a stream cut short has none, so it is spooled as an estimate (the tokens counted at the
model's prices) and made exact from the generation's `total_cost` when the service asks for it afterward (`how`:
`generation`); a refused request is spooled with its status and code, at no cost. The service takes the spool every two
seconds into its own table, by the spool's run and sequence, so a restart of the gateway or a take repeated counts
nothing twice; the spool's route takes only the service's token."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from clank.components.gateway.service import Gateway
from clank.components.gateway.spool import Spool
from clank.kernel.access import local_token
from tests.components.gateway.test_cloud_forwarding import ASKS, WORKSPACE_KEY, cloud_slot, forwarding, recorded
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter

SESSION, PARENT = "ses_made_up_one", "ses_made_up_parent"
GENERATION = "gen-1790000000-MadeUpGeneration01"


def asked(url: str, body: dict[str, Any] | None = None) -> httpx2.Response:
    headers = {"Authorization": f"Bearer {WORKSPACE_KEY}", "X-Session-Id": SESSION, "x-parent-session-id": PARENT}
    return httpx2.post(f"{url}/v1/chat/completions", json=body or ASKS, headers=headers, timeout=30)


def spooled(tmp_path: Path) -> list[dict[str, Any]]:
    return Spool(tmp_path / "state").pending()


def test_a_streams_usage_cost_is_its_cost_spooled_with_its_tokens_and_generation(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    openrouter.play("thinking")
    with forwarding(cloud_slot(openrouter.url), tmp_path, spool=Spool(tmp_path / "state")) as (url, _):
        assert asked(url).status_code == 200
    [record] = recorded(tmp_path)
    assert record["cost"] == {"usd": 0.00003, "how": "usage"}
    assert record["generation"] == GENERATION
    [entry] = spooled(tmp_path)
    assert {key: entry[key] for key in ("seq", "id", "session", "parent", "workspace", "preset", "model")} == {
        "seq": 1, "id": record["id"], "session": SESSION, "parent": PARENT, "workspace": "cloudy",
        "preset": "cloud-example-coder", "model": "example-vendor/example-coder",
    }  # fmt: skip
    assert entry["tokens"] == {"in": 12, "cached": 0, "out": 9, "thinking": 7}
    assert (entry["usd"], entry["how"], entry["generation"], entry["status"]) == (0.00003, "usage", GENERATION, 200)
    assert entry["time"] == record["time"]


def test_a_whole_answers_cost_too(openrouter: FakeOpenRouter, tmp_path: Path) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, spool=Spool(tmp_path / "state")) as (url, _):
        assert asked(url, {**ASKS, "stream": False}).status_code == 200
    [entry] = spooled(tmp_path)
    assert (entry["usd"], entry["how"], entry["generation"]) == (0.000021, "usage", GENERATION)


def test_a_stream_cut_short_is_spooled_as_an_estimate_and_a_refusal_with_its_code(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, spool=Spool(tmp_path / "state")) as (url, _):
        openrouter.play("cut")
        asked(url)
        openrouter.play("no credits")
        asked(url)
    cut, refused = spooled(tmp_path)
    assert (cut["how"], cut["generation"]) == ("estimate", GENERATION)
    assert cut["usd"] > 0
    assert cut["tokens"]["in"] > 0
    assert (refused["status"], refused["code"], refused["usd"], refused["how"]) == (402, "no_credits", 0.0, "usage")


def test_the_spool_survives_a_restart_and_forgets_only_what_was_taken(tmp_path: Path) -> None:
    first = Spool(tmp_path)
    for index in range(3):
        first.add({"id": f"r-{index}", "usd": 0.01, "how": "usage"})
    again = Spool(tmp_path)
    assert again.run == first.run
    assert [entry["seq"] for entry in again.after(0)["entries"]] == [1, 2, 3]
    assert [entry["seq"] for entry in again.after(2)["entries"]] == [3]
    assert [entry["seq"] for entry in Spool(tmp_path).pending()] == [3], "forgotten for good"
    assert Spool(tmp_path).add({"id": "r-4", "usd": 0.0, "how": "usage"})["seq"] == 4


@pytest.mark.anyio
async def test_the_service_takes_the_spool_once_and_makes_an_estimate_exact_from_the_generation(
    rig: Rig, openrouter: FakeOpenRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_openrouter(rig)
    gateway: Gateway = rig.kernel.parts["gateway"]
    spool = Spool(tmp_path / "state")
    with forwarding(cloud_slot(openrouter.url), tmp_path, spool=spool, token=local_token(rig.kernel.home)) as (url, _):
        port = int(url.rsplit(":", 1)[1])
        monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": port, "problem": ""})
        assert httpx2.get(f"{url}/spend", timeout=10).status_code == 401, "the service's alone"
        asked(url, {**ASKS, "stream": False})
        openrouter.play("cut")
        asked(url)
        openrouter.play("no credits", "no credits")
        asked(url)
        asked(url)
        assert gateway.take_spend() == 4
        assert gateway.take_spend() == 0, "nothing taken twice"
        rows = [row for row in gateway.cost_requests() if not row["code"]]
        assert [(row["how"], row["usd"] > 0) for row in rows] == [("estimate", True), ("usage", True)]
        [refused] = rig.kernel.events.latest(types=["gateway.cloud_refused"])
        assert refused.data == {"workspace": "cloudy", "session": SESSION, "code": "no_credits", "status": 402}
        assert refused.attention, "a refusal that stops the owner's work needs them"
        assert refused.summary == (
            "a cloud request of cloudy was refused: credits used up, or the key's limit reached (no_credits)"
        )
        openrouter.generations_ready = False
        rig.clock.advance(11)
        gateway.price_generations()
        known = [row["how"] for row in gateway.cost_requests() if not row["code"]]
        assert known == ["estimate", "usage"], "not yet known: asked again later"
        openrouter.generations_ready = True
        rig.clock.advance(60)
        gateway.price_generations()
    exact = next(row for row in gateway.cost_requests() if not row["code"])
    assert (exact["how"], exact["usd"]) == ("generation", 0.000021)
    assert exact["rev"] > max(row["rev"] for row in rows)
    assert any(sent.path.endswith("/generation") and sent.query == {"id": GENERATION} for sent in openrouter.sent)
    assert json.dumps(rows).count(WORKSPACE_KEY) == 0
