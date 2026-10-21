"""Design 0009 §7-§8: the mode as the owner sees it (plan, review or auto) and handing a plan to the agent.

The window's agent is the agent of the last message sent in OpenCode's window (a watcher's `agent` line from the server
that runs a terminal interface; the phone's sessions do not count), and Clank's own switches; it is not known until a
message was seen. Plan switches the window to the planner, review and auto to build with the change rule set, each by
what Tab does, as many times as the window's agents need; with no window running the rule is set and a note says so,
and an agent the window does not have is named. A plan is handed over only when it is a plan of the folder and a window
runs: a new session there carries out `/implement`'s instructions with the plan's path, and the window then works with
build. The folder's plans are listed with their titles, statuses and steps done.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents.adapters.opencode import prompt
from clank.components.agents.modes import ModeError, Modes
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="vscode")
PLAN = "---\nkind: plan\nstatus: ready\ntitle: A sweep\n---\n# A sweep\n\n- [x] pilot\n- [ ] runs\n- [ ] report\n"


class FakeSessions:
    """The bridge as `Modes` uses it: the servers (the window on 4096, a server without one on 4097), the window's
    agents in Tab's order, and what was asked of it."""

    def __init__(self, windows: bool = True) -> None:
        self.windows = windows
        self.done: list[tuple[Any, ...]] = []

    def servers(self, workspace: str) -> list[dict[str, Any]]:
        return [{"port": 4096, "terminal": self.windows}, {"port": 4097, "terminal": False}]

    def agents(self, workspace: str, port: int) -> list[str]:
        return ["build", "planner"]

    def cycle(self, workspace: str, port: int, count: int, *, actor: Actor) -> None:
        self.done.append(("cycle", port, count))

    def implement(self, workspace: str, port: int, text: str, *, title: str, actor: Actor) -> str:
        self.done.append(("implement", port, text, title))
        return "ses_new"


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "paper"
    (found / "studies" / "sweep").mkdir(parents=True)
    (found / "studies" / "sweep" / "plan.md").write_text(PLAN, encoding="utf-8")
    (found / "notes.md").write_text("# notes, no header\n", encoding="utf-8")
    (found / ".opencode" / "agent").mkdir(parents=True)
    (found / ".opencode" / "agent" / "x.md").write_text(PLAN, encoding="utf-8")
    (found / "runs").mkdir()
    (found / "runs" / "old-plan.md").write_text(PLAN, encoding="utf-8")
    return found


def modes_of(kernel: Kernel, folder: Path, sessions: FakeSessions) -> Modes:
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    modes: Modes = kernel.parts["agents"].modes
    modes.sessions = sessions  # type: ignore[assignment]
    return modes


def agent_line(agent: str, port: int = 4096, terminal: bool = True) -> dict[str, Any]:
    return {"type": "agent", "port": port, "session": "ses_1", "agent": agent, "terminal": terminal}


def test_the_mode_shown_follows_the_messages_sent_in_the_window_and_not_the_phones(
    kernel: Kernel, folder: Path
) -> None:
    modes = modes_of(kernel, folder, FakeSessions())
    review = kernel.parts["agents"].review
    assert (review.view("paper")["agent"], review.view("paper")["shown"]) == (None, "review"), "nothing seen yet"
    review.heard("paper", agent_line("planner"))
    assert (review.view("paper")["agent"], review.view("paper")["shown"]) == ("planner", "plan")
    review.heard("paper", agent_line("build", port=4097, terminal=False))
    assert review.view("paper")["shown"] == "plan", "a session without a window is not the window's"
    review.heard("paper", agent_line("build"))
    assert review.view("paper")["shown"] == "review"
    seen = kernel.events.after(0, types=["agents.agent_seen"])
    assert [event.data["agent"] for event in seen] == ["planner", "build"]
    assert modes.shown("paper") == {"agent": "build", "shown": "review"}


def test_plan_review_and_auto_switch_the_window_by_what_tab_does_and_set_the_change_rule(
    kernel: Kernel, folder: Path
) -> None:
    sessions = FakeSessions()
    modes = modes_of(kernel, folder, sessions)
    view = modes.switch("paper", "plan", actor=YOU)
    assert (view["shown"], view["agent"], view["mode"], view["note"]) == ("plan", "planner", "review", "")
    assert sessions.done == [("cycle", 4096, 1)], "a window not seen yet works with build, OpenCode's first agent"
    view = modes.switch("paper", "plan", actor=YOU)
    assert sessions.done == [("cycle", 4096, 1)], "already the planner: nothing pressed"
    view = modes.switch("paper", "auto", actor=YOU)
    assert (view["shown"], view["agent"], view["mode"]) == ("auto", "build", "auto")
    assert sessions.done[-1] == ("cycle", 4096, 1)
    kernel.parts["agents"].review.heard("paper", agent_line("planner"))  # Tab pressed, a message sent
    modes.switch("paper", "review", actor=YOU)
    assert sessions.done[-1] == ("cycle", 4096, 1)
    assert modes.shown("paper") == {"agent": "build", "shown": "review"}
    switched = kernel.events.after(0, types=["agents.mode_switched"])
    assert [event.data["shown"] for event in switched] == ["plan", "plan", "auto", "review"]
    with pytest.raises(ModeError, match="plan, review or auto, not sometimes"):
        modes.switch("paper", "sometimes", actor=YOU)


def test_with_no_window_the_change_rule_is_set_and_a_note_says_why_the_agent_was_not_switched(
    kernel: Kernel, folder: Path
) -> None:
    sessions = FakeSessions(windows=False)
    modes = modes_of(kernel, folder, sessions)
    view = modes.switch("paper", "auto", actor=YOU)
    assert view["mode"] == "auto"
    assert "no OpenCode runs in a window" in view["note"]
    assert not sessions.done


def test_a_plan_is_handed_to_a_new_session_in_the_window_with_implements_instructions(
    kernel: Kernel, folder: Path
) -> None:
    sessions = FakeSessions()
    modes = modes_of(kernel, folder, sessions)
    found = modes.implement("paper", "studies\\sweep\\plan.md", "auto", actor=YOU)
    assert found == {"workspace": "paper", "plan": "studies/sweep/plan.md", "mode": "auto", "port": 4096,
                     "session": "ses_new"}  # fmt: skip
    [(_, port, text, title)] = sessions.done
    assert (port, title) == (4096, "Implement studies/sweep/plan.md")
    assert text == prompt("implement.md").replace("$ARGUMENTS", "studies/sweep/plan.md")
    assert kernel.parts["agents"].review.mode("paper") == "auto"
    assert modes.shown("paper") == {"agent": "build", "shown": "auto"}
    [handed] = kernel.events.after(0, types=["agents.plan_handed"])
    assert handed.data["plan"] == "studies/sweep/plan.md"


@pytest.mark.parametrize("plan", ["notes.md", ".opencode/agent/x.md", "studies/sweep/missing.md", "../plan.md"])
def test_only_a_plan_of_the_folder_is_handed_over(kernel: Kernel, folder: Path, plan: str) -> None:
    modes = modes_of(kernel, folder, FakeSessions())
    with pytest.raises(ModeError, match="is not a plan of paper"):
        modes.implement("paper", plan, "review", actor=YOU)


def test_a_plan_is_not_handed_over_without_a_window_nor_in_plan_mode(kernel: Kernel, folder: Path) -> None:
    modes = modes_of(kernel, folder, FakeSessions(windows=False))
    with pytest.raises(ModeError, match="no OpenCode runs in a window in paper"):
        modes.implement("paper", "studies/sweep/plan.md", "review", actor=YOU)
    with pytest.raises(ModeError, match="review or auto mode, not plan"):
        modes.implement("paper", "studies/sweep/plan.md", "plan", actor=YOU)


def test_the_folders_plans_are_listed_with_their_steps_done(kernel: Kernel, folder: Path) -> None:
    modes = modes_of(kernel, folder, FakeSessions())
    [plan] = modes.plans("paper")
    assert {key: plan[key] for key in ("path", "title", "status", "done", "steps")} == {
        "path": "studies/sweep/plan.md", "title": "A sweep", "status": "ready", "done": 1, "steps": 3,
    }, "not the settings' Markdown, not the runs' folder"  # fmt: skip
