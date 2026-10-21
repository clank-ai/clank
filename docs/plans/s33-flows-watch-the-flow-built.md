# Flows, step 10 revised: watch the flow built, beside the console: implementation plan

> At the owner's request (2026-10-20, through the build's coordinator), before their first real test: "I would prefer
> to work with the model to build the flow in a way where I can watch the flow being built while the model is working,
> which means that I should be able to open OpenCode on one side and keep the Clank menu on the other side, and I also
> want to start the building of the flow from the monitor section as well as the ability to start it from the 'This
> folder' section." They chose two SSH windows side by side. The files, interfaces and tests by name and intent; the
> code is in the commits.

**Goal:** [design 0013](../design/0013-flows.md) §15's **Beside the console** (revised after approval 2026-10-20) and
§14 step 10's revision: `n` on the Flow view and `f` on This folder open a planning and show it without taking the
console's terminal; `clank flow attach` runs OpenCode on it in another terminal (at the PC, a Windows Terminal pane);
the Flow view shows the planning while it is open: its steps, the latest draft marked DRAFT, its session live, Enter
on it.

**Architecture:** The planning (`building.py`) keeps each draft's number, time, state and problems (`Planning.drafts`
becomes its history's length) and the latest draft's values (`draft.json`); `Building.open` gains `where="attach"`, a
planning that waits for whichever window prepares next; `Building.attach` prepares the window for `clank flow attach`
and, for a planning already talking, shows its session there (the bridge's new `show`, `Sessions.show_in_window`). The
service's view (`Flows.view`) follows an open planning before any flow: `building.watched` names it, `building.steps`
says its steps from its file, the folder and the session's flow (the agents' `SessionFlows`), and the latest draft is
drawn through `view.view` as far as it reads (`building.readable`). `clank.kernel.where` says where OpenCode opens from
the console (`console_opening`: message, Windows Terminal or VS Code) and makes Windows Terminal's command
(`split_argv`); `split` runs it, refused in every test. The Flow view draws the planning: Selected becomes "Building it
with the model" with a Live box, Waiting for you says how to talk with the model, the heading and the Flow panel's note
say DRAFT; Enter opens the session. This folder gains `f`.

**Tech stack:** Python 3.12, FastAPI, click, Textual, pytest; the runner's rig, the fake bridge, the fake OpenCode
server of the bridge's tests.

**Spec:** [design 0013](../design/0013-flows.md) §12, §14 step 10 and §15 (revised after approval 2026-10-20);
decisions [0100](../decisions/0100-a-planning-opens-beside-the-console.md) and
[0101](../decisions/0101-the-flow-view-shows-the-planning-while-it-is-open.md); plan
[s32](s32-flows-a-flow-built-with-the-model.md), whose planning this builds on.

## Global Constraints

- Nothing runs OpenCode, a container, Docker, a model, the service on its port, the gateway on its port or Windows
  Terminal: the fake bridge, the fake OpenCode server and synthetic folders only; `wt` is never run (the launcher is
  refused in every test); nothing opens a window.
- No new dependency. Tests first, each test file's docstring naming the design sections it verifies, test names
  sentences. The owner is the sole author of every commit, no trailer. Not pushed: an independent review comes next.
- Frames at 128, 88 and 60 columns: the owner's SSH windows will be about half a screen wide.

## Claude's calls (2026-10-20)

Design 0013 §15's call 15 and decisions 0100-0101 record them: `f` on This folder (`n` answers a question there); no
clipboard (the console has no copy mechanism); Windows Terminal's command from the console's own Python, `--home` when
`CLANK_HOME` is set; attach shows a talking planning, never a second session; the planning in Selected's place; a
draft drawn as far as it reads. Also:

1. **The planning watched** is the workspace's newest planning while waiting, opening, talking, or failed with no run
   started since; it comes before any flow in the folder's Flow view.
2. **Its steps** are read when the view is: its file, `BRIEF.md`'s fingerprint and time against the one kept when it
   began, and the session's flow (its head: status, steps, calls; a question waiting). The session's flow is the
   service's own, as the Session view reads it: nothing new is asked of the container.
3. **`where="attach"`** never takes a window already running in the workspace (one may be on the PC's own screen); it
   waits for the window `clank flow attach` (or the Windows Terminal pane) prepares.

## Tasks

### Task 1: The planning keeps its drafts

- [x] **Files:** `clank/components/flows/building.py` (`Draft`: number, at, state, problems; `Planning.history`;
  `draft.json`).
- [x] **Tests first** (`tests/components/flows/test_building.py`, design 0013 §15): each draft is kept with its number,
  time, state and problems, the latest's values beside the planning in Clank's state, none in the folder.

### Task 2: `clank flow attach` in the service: a planning that waits, its window prepared, a talking one shown

- [x] **Files:** `clank/components/workspaces/image/bridge.py` (`show`); `clank/components/agents/sessions.py`
  (`show_in_window`); `building.py` (`open` with `where="attach"`, `attach`); `service.py`, `api.py` (`POST
  /flows/attach`, the owner's); `tests/fakes/bridge.py` (`show`).
- [x] **Tests first** (`tests/components/agents/test_sessions.py`, `test_building.py`, design 0013 §15): the bridge
  shows a session on a window that answers late, and again; a planning opened to attach takes no window running and
  waits; attach prepares the window, its session starting there; attach to a talking planning shows its session on the
  new window and starts no other; another window is closed first and said; with no planning open, refused saying how
  to open one; the agent cannot attach.

### Task 3: `clank flow attach`

- [x] **Files:** `clank/components/flows/cli.py` (`attach`, `--workspace`, `--home`).
- [x] **Tests first** (`tests/cli/test_flow_commands.py`, design 0013 §15): it runs OpenCode's command in this terminal
  on the open planning, says what the one-window rule closed, names the session, and once OpenCode ends says whether
  the flow was built; with none open it says how to open one; `--home` sets Clank's home.

### Task 4: The planning in the service's view

- [x] **Files:** `building.py` (`watched`, `steps`, `readable`); `service.py` (`view`); `view.py`.
- [x] **Tests first** (`tests/components/flows/test_planning_view.py`, design 0013 §12, §15): the folder's view follows
  an open planning before a flow that ran; its steps say started, the tool calls so far, waiting for your answer,
  `BRIEF.md` changed with its time, each draft refused with its problems or accepted; the latest draft is drawn and
  marked DRAFT even when refused, as far as it reads; with no draft yet, none; once accepted, the view is the built
  flow.

### Task 5: Where OpenCode opens from the console

- [x] **Files:** `clank/kernel/where.py` (`console_opening`, `split_argv`, `split`); `tests/conftest.py` (the launcher
  refused).
- [x] **Tests first** (`tests/kernel/test_where.py`, design 0013 §15): over SSH the message, whatever else is set; in
  Windows Terminal the split, its arguments as `wt` documents them, `--home` when `CLANK_HOME` is set, `;` escaped; in
  VS Code's terminal VS Code; elsewhere the message; a launch that fails is said.

### Task 6: The Flow view draws the planning, and `n` never takes the terminal

- [x] **Files:** `clank/components/agents/console/flowview.py`, `flowpanels.py`, `monitor.py`; the snapshots.
- [x] **Tests first** (`tests/console/test_monitor_flow_watch.py`, design 0013 §12, §15): `n` opens a planning and the
  console keeps its terminal: over SSH the view says to attach in another terminal, in Windows Terminal the split is
  asked (its command checked), in VS Code's terminal Clank's VS Code window; the view draws the planning (Building it
  with the model, its Live box, the draft marked DRAFT); Enter opens the Session view on its session, Esc back; frames
  at 128, 88 and 60 columns.

### Task 7: This folder's `f`

- [x] **Files:** `clank/components/agents/console/folder.py`.
- [x] **Tests first** (`tests/console/test_folder.py`, design 0013 §15): `f` opens a planning and brings the console
  to the Monitor's Flow view, the keys bar saying `f`.

### Task 8: The words, the documents, the generated files

- [x] **Files:** `docs/console.md` (the flow section, its Over SSH part: two windows), `docs/GLOSSARY.md`,
  `docs/ROADMAP.md`, the indexes, the generated files.
- [x] **Tests:** `uv run python -m tools.check --fix`, then `uv run python -m tools.check`.

## Progress

- 2026-10-20: written.
- 2026-10-20: tasks 1-8 built, test-first: the drafts kept with the planning, `where: attach`, the bridge's `show`,
  `clank flow attach`, the watched planning in `GET /flows/view`, Windows Terminal's split, the Flow view drawing the
  planning, This folder's `f`, the documents.
- 2026-10-20: the early review of tasks 1-3, fixed test-first: a new planning starts with no draft; `clank flow
  attach` tries a planning that failed again, and says to wait while its session starts; attach tested through the
  service's own answer and against an older image; the opened event and `show` worded as what they are; every
  refused draft in the history; design 0013's calls in order.

**Built** (2026-10-20). Design 0013 §15's Beside the console and its call 15 hold as written; an independent review of
the console side (tasks 4-8) found six things, fixed test first, one commit each, before shipping:

1. `n` while a planning was open overwrote it (the same free name, its session and drafts lost) and a double `n` acted
   twice: now the service refuses a new planning while one is open unless told to set it aside (`aside`, `clank flow
   new --set-aside`), a new planning takes a name no flow and no planning has, `n`, `N` and `f` ask first (Esc leaves
   it), and pressed again while one starts do nothing.
2. Help still said the console steps aside: the keys' help, the `?` text and the Flow view's docstring say what `n`
   does now.
3. This folder's keys acted under a window: they do nothing while one is over the page.
4. While building, the keys bar showed keys refused then and lost `n` at 60 columns: it shows F10, Enter, `n`, `N`.
5. A planning in Clank's VS Code window was told to attach from another terminal: it is told to talk, or wait, there.
6. A failed planning's retry could sit below a stacked page: Building it with the model says it too.

## Left for the owner

- The sandbox image is made again (its bridge has `show`), and the workspace reopened on it, before the first try.
- The service restarted, so it answers `POST /flows/attach` and draws the planning in `GET /flows/view`.
- Real checks owed: two SSH windows side by side (the console with `--no-start --page monitor --view flow` on the
  left, `clank flow attach` on the right): `n`, then OpenCode on the planning session in the right window (`docker
  exec -it` over Windows OpenSSH), the Flow view's steps, drafts and Live box following the talk, `r` once built;
  `clank flow attach` again after leaving OpenCode, on the planning already talking (the bridge's `show` on a window
  just started); at the PC in Windows Terminal, `n` splitting the window with OpenCode on the right (`wt -w 0
  split-pane -V`); in VS Code's terminal, Clank's VS Code window; frames at 88 columns and below on the owner's own
  terminals.
