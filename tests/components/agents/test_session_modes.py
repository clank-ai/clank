"""Design 0013 §4 and §5 (decisions 0059 and 0060): a box's mode applies to its own session. The review answers a
session's changes, and its subagents', by the mode the flows' runner gave it, while the workspace's own mode answers
every other session's; and the service can start an OpenCode server without a terminal, and a session on it, apart, so
a flow's boxes each get a session of their own on the flow's server. Run against the fake bridge
(`tests/fakes/bridge.py`), with no container and no OpenCode."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.bridge import FakeBridge
from tests.fakes.platform import FakePlatform, container

OWNER = Actor(kind="user", via="console")
RUNNER = Actor(kind="clank", via="flow runner")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def bridge(kernel: Kernel, tmp_path: Path) -> FakeBridge:
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "a.py").write_text("x = 1\n", encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    made = FakeBridge("paper", folder, hear=kernel.parts["agents"].review.heard)
    platform.inside = made.inside
    kernel.parts["workspaces"].docker(refresh=True)
    return made


def asked(port: int, session: str, id: str) -> dict[str, Any]:
    """The watch's line for a change the agent asks to make to a.py."""
    return {
        "type": "asked", "port": port, "input": {"filePath": "/workspace/a.py", "oldString": "x = 1",
                                                 "newString": "x = 2"},
        "request": {"id": id, "sessionID": session, "permission": "edit", "patterns": ["a.py"],
                    "metadata": {"filepath": "/workspace/a.py", "diff": "@@ -1 +1 @@\n-x = 1\n+x = 2\n"}},
    }  # fmt: skip


def test_a_session_given_auto_has_its_changes_accepted_while_the_workspace_stays_in_review(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    review = kernel.parts["agents"].review
    review.session_mode("paper", "ses_box", "auto")
    bridge.say(asked(4097, "ses_box", "per_1"))
    assert bridge.done("permission") == [["4097", "per_1", "once"]], "answered at once"
    assert kernel.questions.waiting() == []
    assert review.mode("paper") == "review", "the workspace's own mode is unchanged"
    assert review.store.get("per_1")["mode"] == "auto"


def test_a_subagent_of_that_session_takes_its_mode(kernel: Kernel, bridge: FakeBridge) -> None:
    review = kernel.parts["agents"].review
    review.session_mode("paper", "ses_box", "auto")
    bridge.say({"type": "session", "port": 4097, "session": {"id": "ses_helper", "parent": "ses_box"}})
    bridge.say(asked(4097, "ses_helper", "per_2"))
    assert bridge.done("permission") == [["4097", "per_2", "once"]]


def test_another_sessions_change_waits_for_review(kernel: Kernel, bridge: FakeBridge) -> None:
    review = kernel.parts["agents"].review
    review.session_mode("paper", "ses_box", "auto")
    bridge.say(asked(4096, "ses_window", "per_3"))
    assert bridge.done("permission") == []
    [question] = kernel.questions.waiting()
    assert "a.py" in question.title


def test_a_session_given_review_waits_even_while_the_workspace_is_in_auto(kernel: Kernel, bridge: FakeBridge) -> None:
    review = kernel.parts["agents"].review
    review.switch("paper", "auto", actor=OWNER)
    review.session_mode("paper", "ses_box", "review")
    bridge.say(asked(4097, "ses_box", "per_4"))
    assert bridge.done("permission") == []
    assert len(kernel.questions.waiting()) == 1


def test_a_session_whose_mode_is_taken_back_takes_the_workspaces_again(kernel: Kernel, bridge: FakeBridge) -> None:
    review = kernel.parts["agents"].review
    review.session_mode("paper", "ses_box", "auto")
    review.session_mode("paper", "ses_box", None)
    bridge.say(asked(4097, "ses_box", "per_5"))
    assert bridge.done("permission") == []
    assert len(kernel.questions.waiting()) == 1


def test_a_mode_that_is_not_review_or_auto_is_refused(kernel: Kernel) -> None:
    from clank.components.agents.review import ReviewError

    with pytest.raises(ReviewError, match=r"made without asking \(auto\), not plan"):
        kernel.parts["agents"].review.session_mode("paper", "ses_box", "plan")


def test_a_server_and_a_session_on_it_are_started_apart_each_recorded(kernel: Kernel, bridge: FakeBridge) -> None:
    sessions = kernel.parts["agents"].sessions
    window = bridge.window()
    port = sessions.serve("paper", {"OPENCODE_DISABLE_AUTOUPDATE": "1"})
    assert port != window
    assert bridge.servers[port].terminal is False
    assert bridge.servers[port].env == {"OPENCODE_DISABLE_AUTOUPDATE": "1"}
    session = sessions.new("paper", port, "A new simulation study · plan · try 1", actor=RUNNER)
    assert bridge.servers[port].sessions[session]["title"] == "A new simulation study · plan · try 1"
    [event] = kernel.events.latest(types=["agents.acted"], limit=1)
    assert (event.data["action"], event.data["session"], event.actor) == ("start", session, RUNNER)
