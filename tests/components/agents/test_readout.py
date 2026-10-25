"""Design 0021 §3: the model's readout. KVMem says in its log the tokens it drafted and how many were accepted, the
newest line counting; an engine that does not say it gives nothing. The runtime reads it from the newest launch's log of
a slot, and a slot never launched has none. `GET /agents/readout?folder=` composes, for the folder's workspace, its
newest kept session (or the one named) with that session's `now` and context totals, the main slot (its state, its
preset and title, and the options that change its speed), the GPU's newest meter and the drafts; a folder with no
workspace, or a workspace with no session yet, answers what there is."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.service import Agents
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.adapters.llamacpp import LlamaCpp
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
LOG = [
    "srv  load_model: loaded",
    "KVMEM_TRACE spec_stats n_gen=1779 n_drafted=1920 n_accept=1140 n_restore=0 accept_pct=59.4",
    "KVMEM_CHAT_TURN n_prompt=169419 n_gen=2178 prefill_ms=2940.03 gen_toks=35.28",
    "KVMEM_TRACE spec_stats n_gen=2178 n_drafted=2433 n_accept=1368 n_restore=0 accept_pct=56.2",
]


def test_kvmem_says_its_drafted_tokens_accepted_in_its_log_and_the_newest_line_counts() -> None:
    adapter = KvmemLlamacpp(KvmemLlamacpp.VERSIONS[0].name)
    assert adapter.drafts(LOG) == {"tokens": 2178, "drafted": 2433, "accepted": 1368, "share": 0.562}
    assert adapter.drafts(["srv  load_model: loaded"]) is None
    assert LlamaCpp(LlamaCpp.VERSIONS[0].name).drafts(LOG) is None, "an engine that does not say it gives nothing"


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def launched(kernel: Kernel, log: Path, preset: str = "frontier-262k") -> None:
    """The main slot ready, its newest launch's output in `log`."""
    state = kernel.parts["runtime"].state
    launch = state.add_launch(
        slot="main", preset=preset, options={"spec.draft_tokens": 4, "cuda_graphs": True}, engine="kvmem-llamacpp",
        engine_version=KvmemLlamacpp.VERSIONS[0].name, host="ubuntu-22.04", command_line="llama-kvmem-server", log="",
        estimate_mib=14791, before_mib=None,
    )  # fmt: skip
    state.set_log(launch, str(log))
    state.set_slot("main", "ready", "a test", actor=YOU, preset=preset, launch_id=launch, host="ubuntu-22.04",
                   port=18200)  # fmt: skip


def test_the_runtime_reads_the_drafts_from_the_slots_newest_launch_log(kernel: Kernel, tmp_path: Path) -> None:
    log = tmp_path / "main-1.log"
    log.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    launched(kernel, log)
    assert kernel.parts["runtime"].drafts("main") == {"tokens": 2178, "drafted": 2433, "accepted": 1368, "share": 0.562}
    assert kernel.parts["runtime"].drafts("fast") is None, "a slot never launched"
    log.unlink()
    assert kernel.parts["runtime"].drafts("main") is None, "a log that is gone"


def test_the_readout_composes_the_folders_newest_session_its_now_its_context_the_slot_and_the_machine(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    log = tmp_path / "main-1.log"
    log.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    launched(kernel, log)
    agents: Agents = kernel.parts["agents"]
    asked: list[tuple[str, str]] = []
    newest = [{"session": "ses_new", "title": "the newest"}, {"session": "ses_old", "title": "an older one"}]
    monkeypatch.setattr(agents.flows, "flows", lambda workspace: newest if workspace == "paper" else [])

    def now(workspace: str, session: str) -> dict[str, Any]:
        asked.append((workspace, session))
        return {"workspace": workspace, "session": session, "state": "thinking", "speed": {"now": 63.0}}

    monkeypatch.setattr(agents, "now", now)
    monkeypatch.setattr(agents, "context", lambda workspace, session: {"workspace": workspace, "used": 161000})
    reading = {"gpus": [{"name": "GPU", "use": 91.0, "memory_used": 15 * 2**30, "memory_total": 16 * 2**30}]}
    monkeypatch.setattr(kernel.parts["machine"], "meters", lambda: [{"gpus": []}, reading])
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:
        found: dict[str, Any] = client.get(
            "/api/v1/agents/readout", params={"folder": str(folder)}, headers={"Authorization": "Bearer t"}
        ).json()
        named = client.get(
            "/api/v1/agents/readout", params={"folder": str(folder), "session": "ses_old"},
            headers={"Authorization": "Bearer t"},
        ).json()  # fmt: skip
        nowhere = client.get(
            "/api/v1/agents/readout", params={"folder": str(tmp_path / "elsewhere")},
            headers={"Authorization": "Bearer t"},
        ).json()  # fmt: skip
    assert found["workspace"] == "paper"
    assert found["session"] == {"id": "ses_new", "title": "the newest"}
    assert found["now"]["state"] == "thinking"
    assert found["context"]["used"] == 161000
    assert found["slot"]["status"] == "ready"
    assert found["slot"]["preset"] == "frontier-262k"
    assert found["slot"]["title"] == "frontier 262K"
    assert found["slot"]["speed_options"] == {"spec.draft_tokens": 4, "cuda_graphs": True}
    assert found["drafts"]["share"] == 0.562
    assert found["gpu"] == {"name": "GPU", "use": 91.0, "memory_used": 15 * 2**30, "memory_total": 16 * 2**30}
    assert named["session"]["id"] == "ses_old"
    assert asked == [("paper", "ses_new"), ("paper", "ses_old")]
    assert nowhere["workspace"] is None
    assert (nowhere["session"], nowhere["now"], nowhere["context"]) == (None, None, None)
    assert nowhere["slot"]["status"] == "ready", "the machine's figures whatever the folder"
