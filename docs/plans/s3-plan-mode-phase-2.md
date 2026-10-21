# Plan mode, phase 2: implementation plan

> At the owner's request (2026-10-16): "go ahead and then immediately begin phase 2". As for phase 1
> ([s2](s2-plan-mode.md)), the files, interfaces and tests by name and intent; the code is in the commits. Measured
> first, with a real terminal interface on a pseudo-terminal: the window keeps its agent to itself (design 0009 §7, as
> revised), so the switch is Tab's, and a plan is handed over as a new session's first message.

**Goal:** design 0009 §7-§8: Plan, Review or Auto chosen from VS Code's status bar and the folder page (F4 `p`, `r`);
a plan handed to the agent from its top in VS Code (▶ Implement with Review, ▶ Implement with Auto, ↻ Continue) and
from the folder page (`i`).

**Spec:** [design 0009](../design/0009-plan-mode.md) §7-§8 (revised 2026-10-16 by measurement).

## Global Constraints

- OpenCode 1.19.0 as measured: `/tui/execute-command {"command": "agent_cycle"}` does what Tab does; a session shown
  with `/tui/select-session` makes the window take its last message's agent; the API's session agent does not.
- The bridge (`/opt/clank/bridge.py`) changes, so the sandbox image does: a workspace's container is made again from
  it once stopped (F4 `o`).
- The owner is the sole author of every commit; American English; tests first; tests named as sentences.

## Tasks

- [x] **The bridge:** `servers` says which server runs a terminal interface (`terminal_ports`, from `/proc`); actions
  `agents` (Tab's order), `cycle PORT COUNT`, `implement PORT`; the watcher's `agent` lines, one per message sent
  (`tests/components/agents/test_sessions.py`, `test_review.py`).
- [x] **`modes.py`:** the window's agent from the watcher and Clank's own switches; `switch` (plan, review, auto; a
  note when no window runs or the window lacks the agent); `implement` (a plan of the folder only, a window required,
  `/implement`'s instructions with the plan's path); `plans` (the folder's plans with their steps done); events
  `agents.mode_switched`, `agents.agent_seen`, `agents.plan_handed` (`tests/components/agents/test_modes.py`).
- [x] **The API:** `GET /agents/review` adds `agent` and `shown`; `POST /agents/mode`; `POST /agents/implement`;
  `GET /agents/plans`.
- [x] **The folder page:** `p` plan, `r` review or auto (from plan, back to the rule kept), `i` a plan then Review or
  Auto; the mode line says plan (`tests/console/test_folder.py`).
- [x] **VS Code (0.6.0):** the status bar's Plan, Review or Auto, a pick of the three; the lenses on a plan; the
  events followed (`vscode/src/core/*.test.ts`).
- [x] **Documents:** design 0009 §7-§8 revised; the studies guide; the help page.
- [x] **On the owner's machine:** a second window in a project's workspace (port 4097; the owner's own on
  4096 left alone), switched to plan, then handed a plan (2026-10-16). The window was seen 2.8 s after it started;
  `POST /agents/mode` to plan pressed Tab in that window (the next message was the planner's) and `GET /agents/review`
  said `shown: plan`; back to review, the next message was build's; the plan handed over in review mode was ticked,
  logged and set done, its edits accepted without asking. Everything the check made was removed.
- [x] **In Clank's VS Code window (0.6.0),** a workspace opened again on the new image (the bridge in it, 68 s to
  build): the status bar's item picked Plan (OpenCode's footer said Planner) and Review again (Build); a plan showed
  Implement with Review, Implement with Auto and Continue (1 of 2 steps done); with no window, Implement offered to
  open the agent, and once opened the plan was handed over and carried out. The window took 5 s to start there, more
  than the fixed 4 s the extension waited before handing the plan over again: it now looks for the window every half
  second, half a minute at most (`vscode/test/plans.test.ts`).
- [x] **Every check passes:** the plan tests' paths are under `/srv`, not a home folder; the annotator test failed
  again under load: its Escape went to the page before the note's editor had the focus (it takes it a moment after
  opening), so it now waits for the focus.
- [x] **Commit and push** (2026-10-16), with CI's three gateway tests that failed before this work.
