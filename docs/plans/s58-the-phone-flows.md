# Plan s58: Clank for iPhone, step 2a: Flows

Design 0025 §6 and §11 step 2 (its flows half), on step 1's app and stream ([plan s57](s57-the-phone-app.md)) and
design 0013's flows: the Flows tab lists every flow with its state in words and filters it (All, Running, Waits,
Ended); a flow opens with its boxes as a column, the running box open, Pause and Stop, its proposals to accept or
reject, and what it waits for under its box, answered there; a flow being built with the model shows its planning's
steps; *Build a flow* opens a planning in Clank's VS Code window on the PC. The session screen with the Guide and its
context (§7) is step 2b, plan s59, written when this plan is done.

## What exists

- The flows component: `Flows.flows()` (every flow: id, title, how many boxes, what is wrong with its file),
  `Flows.view(folder, flow)` (what the Monitor's Flow view shows, design 0013 §12: the run, every box with its tries,
  the lines, the proposals, Waiting for you, the brief checked, the deliverables, Ahead, the counts, a `version`),
  `Flows.waiting()`, `Flows.go`, `pause`, `stop`, `Flows.decide` (proposals accepted or rejected, by id or all),
  `Flows.being_built` (a planning's steps, decision 0101), `Flows.new(workspace, folder, name, where, actor)`; a run
  (`runs.Run`: queued, running, done or stopped; paused; the box it is at; what it waits for: you, gate, failed, done
  or proposals, with its question; each box's tries); the `flows.*` events.
- The phone (step 1): the stream's events with their type, title, attention and what they are about (`flow`, `box`,
  `question`); `_overview.questions`, each about a flow with what it shows (`_flow_shown`: flow, box, kind, files,
  notes); `POST /api/clank-questions/{id}` answers one; `GET /api/flow-files/{question}/{index}` reads a file it
  shows; `app.js` draws a flow's question (`flowBox`) and the Flows tab lists those questions and nothing else.

## Choices made here

- **Summaries are the service's** (`flows/summaries.py`, `Flows.summaries()`, `GET /api/v1/flows/summaries`): the
  words of each flow's state are made once, in Python, tested, and every client lists flows the same way; the phone
  reads them (`GET /api/flows`) and knows no rule of the runner.
- **A flow's screen is the Flow view's JSON** (`GET /api/flows/{workspace}/{name}`, `Flows.view`), as design 0013 §12
  meant it ("the phone can later"); the phone draws from it, and nothing is shaped twice.
- **Every action carries the device as its actor** (`acting(request)`): pause, stop, run, accept, reject and new are
  recorded as the device's, as answers are.
- **Refresh by events, never by polling**: the Flows tab and an open flow read again when a `flows.*` or
  `question.*` event arrives on the stream, once per burst (300 ms); the view's `version` says when nothing changed.
- **Build a flow from the phone** opens the planning in Clank's VS Code window on the PC (`where="vscode"`: the one
  place that needs no terminal); the phone says where it opened and shows its steps. Its session can be talked to from
  the phone once step 2b brings the session screen.
- **Deliverable sizes** (`new +142`, `+38 −4`) wait for the file screen (step 3): the view says each file's box, its
  try and whether its check passed; a diff is a call per file.

## Tasks

- [x] 1. **Summaries** (`flows/summaries.py`, `Flows.summaries(workspace="")`, `GET /api/v1/flows/summaries`):
  `summarize(flow, run, planning, titles)`: `id`, `workspace`, `name`, `title`, `state` (never, queued, running,
  paused, waits, building, done, stopped), `words` (never: "not run yet"; queued: "queued behind <flow>"; running:
  "<box> · 3 of 9"; paused: "paused · <box> runs on" or "paused"; waits: "waits for you: <what> · <box>", what being
  gate, your part, a box failed, a box is done, proposals; building: "building: <its state>"; done: "done · approved
  by you" after a gate, else "done"; stopped: "stopped: <why>" or "stopped"), `box`, `box_title`, `position` (done,
  of), `model` (the running box's preset title, else the flow's default's), `time` (the run's end, else its start,
  else nothing), `question` (the id it waits for), `problems`. Tests (`tests/components/flows/test_summaries.py`)
  on runs built in the test: each state's words; the route lists them newest first.
- [x] 2. **The listener's flow routes** (`remote/flowsapi.py`, included by `app.py`): `GET /api/flows` (the summaries
  and, per workspace with a planning open, its steps), `GET /api/flows/{workspace}/{name}` (the view), `POST
  .../pause`, `.../stop`, `.../run`, `.../proposals/accept` and `.../proposals/reject` (`{"proposals": [...]}` or
  `{"all": true}`), `POST /api/flows/new` (`{"workspace", "name"}`), every action with the device as actor; errors
  as the kernel says them (403, 404, 409). Tests (`tests/components/remote/test_phone_flow_screens.py`) on the flows
  rig: the list's words as the study flow runs to its gate; the view read by the phone; pause and stop recorded as the
  device's; proposals accepted from the phone join the flow; a flow refused to run says why.
- [x] 3. **The Flows tab** (`page/app.js`, `page/model.mjs`): the list with *Build a flow*, the filters (All, Running,
  Waits, Ended: `flowFilter(rows, which)`; Running takes queued, running, paused and building), each row's state
  words, workspace, model and time; a flow: its title, workspace, model, time, the run's words, the controls its
  state allows (`runControls(run)`: Pause and Stop while running; Resume and Stop while paused; Run otherwise), the
  boxes as a column (`boxGlyph(state)`: ○ waiting, ● running, ✓ done, ✗ failed, ◇ a gate, ! stale or skipped) each
  with its type, tries ("try 1 of 3") and when it ended; the running box open with its tokens, files and a *Session*
  button; what the run waits for drawn under its box with `flowBox`; the proposals (title, type, why, *Accept*,
  *Reject*, and *Accept all*, *Reject all* while any waits); a planning's steps with the brief's first lines; a read
  again on each `flows.*` or `question.*` event. Node tests of `flowFilter`, `runControls`, `boxGlyph`.
- [x] 4. **Docs**: design 0025 §6 built (sizes waiting) and §11 step 2 half built; the roadmap (M9); the plan index;
  the generated pages (the API page gains the summaries route).

## Progress

Written 2026-10-26. Built 2026-10-26: the summaries list a planning's flow as building before its file is written,
and a flow's screen reads the planning's view then (`Flows.planning_view`, `Flows.plannings_open`); the phone's flow
routes reach the flows through their service only (the architecture check). The live look at the Flows tab on the
owner's phone waits for the owner's pairing.
