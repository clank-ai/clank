"""Design 0012 §8 (decision 0053) and design 0005 §6: a Watch for rule set to tell the phone lists its mark on the
phone page, with what waits, until the mark is seen, from the phone or from the computer; seen from the phone, it is
recorded as the device's. A mark of an ask the page already shows in OpenCode's own box (a permission, a question)
is not listed again. The page's script draws the overview's marks with what waits and marks one seen."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.remote.app import create_phone_app
from clank.kernel.core import Kernel
from clank.kernel.processes import background_flags
from tests.components.agents.test_watch_for_rules import LIMITS, bash, steps_with, waiting_for_you
from tests.components.remote.test_phone import ACT, THROUGH_TAILSCALE, YOU, kernel, paired, phone  # noqa: F401
from tests.support.flowlines import SESSION, lines, updated

PAGE = Path(create_phone_app.__code__.co_filename).parent / "page" / "app.js"


def marked(kernel: Kernel) -> str:  # noqa: F811
    """A session that made the same call three times, its rule set to tell the phone: the mark's id."""
    loaded = kernel.settings.get("monitor", "monitor")
    values = loaded.record.model_dump()
    values["same_call_again"]["do"] = ["mark", "tell the phone"]
    kernel.settings.write("monitor", "monitor", values, base=loaded.revision, actor=YOU)
    agents = kernel.parts["agents"]
    messages = steps_with([bash(f"c{n}", "pytest -q") for n in range(1, 4)])
    for line in lines([event for message in messages for event in updated(message)]):
        agents.flows.heard("paper", line)
    agents.marks.watch(agents.flows, lambda: LIMITS)
    [mark] = agents.marks.phone()
    return str(mark["id"])


def test_a_mark_told_to_the_phone_is_listed_with_what_waits_until_it_is_seen(
    kernel: Kernel,  # noqa: F811
    phone: TestClient,  # noqa: F811
) -> None:
    paired(kernel, phone)
    id = marked(kernel)
    [listed] = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()["marks"]
    assert (listed["id"], listed["workspace"], listed["session"], listed["name"]) == (
        id, "paper", SESSION, "The same call again"
    )  # fmt: skip
    assert "3 times in the last 12" in listed["why"]
    assert phone.post("/api/marks/seen", json={"ids": [id]}, headers=THROUGH_TAILSCALE).status_code == 403, (
        "an action needs the page's own header"
    )
    seen = phone.post("/api/marks/seen", json={"ids": [id]}, headers=ACT)
    assert seen.status_code == 200, seen.text
    assert seen.json() == {"seen": 1}
    assert phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()["marks"] == []
    [event] = kernel.events.after(0, types=["agents.marks_seen"])
    assert (event.actor.kind, event.actor.via) == ("device", "my phone")


def test_a_mark_seen_on_the_computer_leaves_the_phones_list(kernel: Kernel, phone: TestClient) -> None:  # noqa: F811
    paired(kernel, phone)
    id = marked(kernel)
    kernel.parts["agents"].marks.seen([id], actor=YOU)
    assert phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()["marks"] == []


def test_an_ask_shown_in_opencodes_own_box_is_not_listed_again_as_a_mark(
    kernel: Kernel,  # noqa: F811
    phone: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paired(kernel, phone)
    agents = kernel.parts["agents"]
    flow, _ = waiting_for_you()  # an approval (per_1) and the question tool, both waiting
    agents.marks.check("paper", SESSION, flow.view(), LIMITS)
    assert len(agents.marks.phone()) == 2
    servers: list[dict[str, Any]] = []
    monkeypatch.setattr(kernel.parts["workspaces"], "workspaces", lambda: [{"name": "paper", "state": "running"}])
    monkeypatch.setattr(agents.sessions, "servers", lambda workspace: [dict(each) for each in servers])
    marks = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()["marks"]
    assert len(marks) == 2, "OpenCode's own boxes not listed: the marks are"
    asking = {"id": "que_1", "session": SESSION, "questions": [{"question": "Which axis?"}]}
    servers.append({"port": 4096, "terminal": True, "sessions": [], "children": [],
                    "permissions": [{"id": "per_1", "session": SESSION, "permission": "bash", "patterns": ["*"],
                                     "metadata": {}}],
                    "questions": [asking]})  # fmt: skip
    overview = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
    assert [each["id"] for each in overview["workspaces"][0]["servers"][0]["permissions"]] == ["per_1"]
    assert overview["marks"] == [], "each ask listed once, in OpenCode's own box"


def test_the_phone_page_draws_a_mark_with_what_waits() -> None:
    script = PAGE.read_text(encoding="utf-8")
    assert "overview.marks" in script, "the page reads the overview's marks"
    assert "api/marks/seen" in script, "and marks one seen"
    assert "markBox" in script.split("function waitingBoxes", 1)[1].split("\n}\n", 1)[0], "with what waits"
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not on the PATH: the script's syntax is checked where it is")
    checked = subprocess.run(
        [node, "--check", str(PAGE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        creationflags=background_flags(),  # no console window on Windows
    )
    assert checked.returncode == 0, checked.stderr
