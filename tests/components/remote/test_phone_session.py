"""Design 0025 §7 (design 0023 §3, design 0012 §9): the phone's session screen on the listener. The conversation
stream is served for a paired device: `connected`, then a snapshot of the workspace's session (its messages in the
Monitor's shape, its version), then each change the mirror hears with its version as the event's id; the stream is
logged as one line; a workspace Clank does not have is 404. The Guide's offer and the session's context totals pass
through to the phone, an action of the Guide from the phone is recorded as the device's, and what the agents refuse
comes back with their words. The listener is served for real, since a stream never ends on its own."""

from pathlib import Path
from typing import Any

import httpx2
import pytest

from clank.components.agents.service import Agents
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.components.agents.test_conversation import server, session
from tests.components.remote.test_phone_stream import ACT, THROUGH_TAILSCALE, Events, kernel, paired, served

__all__ = ["kernel", "served"]  # the fixtures, shared with the phone's own stream's tests
YOU = Actor(kind="user", via="console")
STREAM = "/api/conversation/stream?workspace=paper&session=ses_new"


def ready(kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Agents:
    """Workspace paper on `folder`, one server listing ses_new (busy), a history of one message."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    agents: Agents = kernel.parts["agents"]
    running = [server(4096, session("ses_new", "busy", 20, "the newest"))]
    monkeypatch.setattr(agents.sessions, "servers", lambda workspace: running)
    monkeypatch.setattr(agents.sessions, "runs", lambda workspace, id: None)

    def page(
        workspace: str, port: int, id: str, *, limit: int = 50, before: str = "", whole: bool = False
    ) -> dict[str, Any]:
        return {"messages": [{"info": {"id": "msg_1", "role": "user", "created": 100}, "parts": [
            {"id": "prt_1", "message": "msg_1", "type": "text", "text": "Plot it.", "length": 8, "whole": True}]}],
            "next": ""}  # fmt: skip

    monkeypatch.setattr(agents.sessions, "page", page)
    return agents


def line(kind: str, **more: Any) -> dict[str, Any]:
    return {"type": kind, "port": 4096, "session": "ses_new", **more}


def test_the_stream_gives_a_snapshot_of_the_session_then_each_change_with_its_version(
    kernel: Kernel, served: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    cookies = paired(kernel, served)
    events = Events(served, THROUGH_TAILSCALE, cookies, path=STREAM)
    try:
        found = events.until("snapshot")
        assert [name for name, _, _ in found] == ["connected", "snapshot"]
        snapshot = found[-1][2]
        assert (snapshot["workspace"], snapshot["session"]["id"], snapshot["session"]["busy"]) == (
            "paper",
            "ses_new",
            True,
        )
        assert [each["info"]["id"] for each in snapshot["messages"]] == ["msg_1"]
        version = snapshot["version"]
        agents.sessions.heard("paper", line("delta", message="msg_1", part="prt_1", field="text", text=" Now."))
        name, id, data = events.until("delta")[-1]
        assert (name, id, data["text"]) == ("delta", version + 1, " Now.")
    finally:
        events.close()
    log = kernel.parts["remote"].traffic.recent(limit=10)
    streamed = [each for each in log if each["path"] == "/api/conversation/stream"]
    assert len(streamed) == 1, "the stream is one line of the log"


def test_a_workspace_clank_does_not_have_is_said_and_an_unpaired_phone_is_refused(kernel: Kernel, served: str) -> None:
    cookies = paired(kernel, served)
    missing = httpx2.get(
        f"{served}/api/conversation/stream", params={"workspace": "nowhere"}, headers=THROUGH_TAILSCALE,
        cookies=cookies, timeout=10,
    )  # fmt: skip
    assert missing.status_code == 404
    assert "nowhere" in missing.json()["error"]
    unpaired = httpx2.get(
        f"{served}/api/conversation/stream", params={"workspace": "paper"}, headers=THROUGH_TAILSCALE, timeout=10
    )
    assert unpaired.status_code == 401


def test_the_guides_offer_and_the_context_totals_pass_through_and_an_action_is_the_devices(
    kernel: Kernel, served: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Guide's own rules are its tests' (tests/components/agents/test_guide*.py): here its offer is canned, in
    the shape `guide._action` gives, and the route's part is checked: who may read, who may act, as whom, and how a
    wrong action is refused."""
    agents = ready(kernel, tmp_path / "paper", monkeypatch)
    cookies = paired(kernel, served)
    canned: list[dict[str, Any]] = [
        {"action": name, "key": key, "title": name.title(), "can": name != "undo", "why": "" if name != "undo" else
         "no step yet", "brief": f"{name}s", "does": "", "calls": [], "cost": {"tokens": None, "seconds": None},
         "confirm": name != "stop", "state": None}
        for name, key in (("stop", "."), ("note", "m"), ("compact", "k"), ("pause", "p"), ("undo", "u"), ("drop", "x"))
    ]  # fmt: skip
    asked: list[tuple[str, str, str]] = []
    stopped: list[tuple[str, str, Actor]] = []

    def offer(workspace: str, session: str, *, item: str = "", pause: bool = True) -> dict[str, Any]:
        asked.append((workspace, session, item))
        return {"workspace": workspace, "session": session, "port": 4096, "actions": canned}

    def stop(workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        stopped.append((workspace, session, actor))
        return {"state": "stopping"}

    monkeypatch.setattr(agents.guide, "offer", offer)
    monkeypatch.setattr(agents.guide, "stop", stop)
    offered = httpx2.get(
        f"{served}/api/guide/paper/ses_new", params={"item": "prt_9"}, headers=THROUGH_TAILSCALE, cookies=cookies,
        timeout=10,
    )  # fmt: skip
    assert offered.status_code == 200, offered.text
    assert asked == [("paper", "ses_new", "prt_9")]
    actions = {each["action"]: each for each in offered.json()["actions"]}
    assert set(actions) == {"stop", "note", "compact", "pause", "undo", "drop"}
    assert (actions["undo"]["can"], actions["undo"]["why"]) == (False, "no step yet")
    totals = httpx2.get(f"{served}/api/context/paper/ses_new", headers=THROUGH_TAILSCALE, cookies=cookies, timeout=10)
    assert totals.status_code == 200, totals.text
    assert {"window", "used", "left", "line", "parts", "gpu"} <= set(totals.json())
    acted = httpx2.post(f"{served}/api/guide/paper/ses_new/stop", headers=ACT, cookies=cookies, timeout=10)
    assert acted.status_code == 200, acted.text
    assert [(workspace, session, actor.kind) for workspace, session, actor in stopped] == [
        ("paper", "ses_new", "device")
    ]
    plain = httpx2.post(
        f"{served}/api/guide/paper/ses_new/stop", headers=THROUGH_TAILSCALE, cookies=cookies, timeout=10
    )
    assert plain.status_code == 403, "an action needs the page's own header"
    wrong = httpx2.post(f"{served}/api/guide/paper/ses_new/shout", headers=ACT, cookies=cookies, timeout=10)
    assert wrong.status_code == 404
    unseen = httpx2.get(f"{served}/api/guide/paper/ses_other", headers=THROUGH_TAILSCALE, cookies=cookies, timeout=10)
    assert unseen.status_code == 200, "the offer is the Guide's to refuse: here it was canned"
