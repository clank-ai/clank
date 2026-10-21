# The Monitor's bridge: implementation plan

> At the owner's request (2026-10-18, designs 0012 and 0013 approved: "Approve all three"; 2026-10-19: the new menu,
> the Monitor and flows built as quickly as possible). As for the earlier plans, the files, interfaces and tests by
> name and intent; the code is in the commits.

**Goal:** design 0012 §11 step 4, *the bridge*, built once for both designs (design 0013 §5, §7): the watch forwards
the Monitor's events (statuses, sessions with their subagents, messages, parts, todos, compactions, errors,
questions), coalesced per burst, with each session's server, and the text as it is written only for the sessions
shown; `prompt` sends the session's agent and model; new actions reject a session's waiting asks, compact without
waiting, clear a tool result, revert and unrevert, and page through a session's messages; the service knows which
server runs each session and sends every action there.

**Architecture:** The bridge (`clank/components/workspaces/image/bridge.py`, standard library only, run in the
container with `docker exec`) gets one shape for a message and one for a part (`seen_message`, `seen_part`), used by
the watch's lines and by `page` alike, so the flow of step 5 reads the same thing from the live stream and from the
history. The watch holds the Monitor's lines in an ordered table keyed by what they describe (a part, a message, a
session's status), each new value replacing the old one and moving to the table's end, and writes the table once the
stream has been quiet for a moment, or at the latest a quarter of a second after its first line, so a part updated a
hundred times in a burst is said once, with its last state. The lines the review needs (`asked`, `replied`, `edited`,
`agent`, `gone`) are said at once, after what is held. The service tells the watch which sessions are shown by a line
on the watch's standard input, which it already reads to know when to end. In the service, `Sessions.heard` keeps
where each session runs (the server whose stream carried its run), and every action on a session goes to that server.

**Tech stack:** Python 3.12 standard library in the bridge; pytest; a fake OpenCode server (`tests/fakes/opencode.py`)
replaying a synthetic session's events (`tests/fixtures/opencode/1.19.0/session.json`).

**Spec:** [design 0012](../design/0012-the-monitor.md) §3, §5.1, §6.1, §9 and §11 step 4;
[design 0013](../design/0013-flows.md) §5 and §7; [decision 0048](../decisions/0048-the-monitor-follows-the-newest-session-of-its-folder.md),
[decision 0049](../decisions/0049-a-sessions-flow-is-built-in-the-service.md),
[decision 0054](../decisions/0054-a-note-is-a-real-user-message.md); [design 0007](../design/0007-reviewing-changes.md) §4
(the watcher).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: a GPU benchmark ran through them. The
  bridge is tested on this machine against the fake OpenCode, as its other actions are (`tests/components/agents/`).
- The events are written by hand, in the shapes of OpenCode's event and route schemas as read on 2026-10-19 in the
  program of OpenCode 1.18.31 installed on this machine (its `message.part.delta`, `session.status`, `todo.updated`,
  `session.compacted`, `server.instance.disposed`, the question events, `limit`, `before` and `X-Next-Cursor` for
  messages, `PATCH` of a part, `summarize`'s body) and in design 0012's reading of 1.19.0's source; their file says
  so. Recording them from OpenCode 1.19.0 in the sandbox image is left for later (below).
- The bridge stays standard library only, and runs on Windows for the tests: nothing it starts opens a window.
- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections.
- Every commit's author is the owner, with no trailer; nothing is pushed from this lane.

## Review Focus

1. **A burst split in two**: the watch writes what it holds after 0.1 s of quiet or 0.25 s after the first line held;
   a test that needs one burst sets a longer quiet (`CLANK_BRIDGE_BURST`), so a busy machine does not split it.
2. **Order**: a value replaced moves to the table's end, so a status that went busy, then idle, is said after the
   step's parts; the lines said at once are written after what is held.
3. **A note to a session another server runs**: two OpenCode servers in one container list the same sessions (their
   storage is shared), so the port a client names can be the wrong one; the service sends to the server whose stream
   carried the session's run, and only to the port it was given when no watcher saw the session run.
4. **The compaction's holder**: a process of the bridge's own (`held`), started in a session of its own as `serve`
   is, keeps OpenCode's `summarize` request open until the run ends, so the bridge returns at once and OpenCode never
   sees its client leave.
5. **The agent kept**: a message that names no agent goes, in OpenCode, to `build`; `prompt` names the agent and the
   model of the session's last message of the owner unless the caller names others.

## Tasks

### Task 1: A session's messages, a page at a time, in one shape

- [x] **Files:** create `tests/fakes/opencode.py` (`FakeOpenCode`: OpenCode's server as the bridge uses it, several
  sharing one `Store` of sessions, messages, asks and questions, each with its own run state, event stream and record
  of what was sent), `tests/fixtures/opencode/1.19.0/session.json` (a synthetic planner session with a subagent, its
  history and its events in bursts), `tests/components/agents/test_monitor_bridge.py`; change
  `clank/components/workspaces/image/bridge.py` (`page`, `seen_message`, `seen_part`, `fetch`) and
  `tests/fixtures/README.md`.
- [x] **Interfaces:** `page PORT SESSION [LIMIT] [BEFORE]` → `{"messages": [{"info": seen_message, "parts":
  [seen_part]}], "next": cursor or ""}`, oldest first, from `GET /session/:id/message?limit=&before=` and its
  `X-Next-Cursor`. `seen_part` keeps a part's id, message, type and, by type: text and reasoning cut at 6,000
  characters with their length; a tool call's tool, call id, status, title, input (400) and output (1,500) cut, the
  output's length, times (with `compacted`), and from its metadata the subagent's `sessionId` and the `exit` status;
  a step's finish with its tokens, cost and reason; a patch's files; a compaction's `auto`.
- [x] **Tests:** the bridge gives a session's messages a page at a time, oldest first within a page, each next page
  by its cursor, the last without one; each part in the watch's shape, a long output cut with its length.

### Task 2: A message keeps the session's agent and model

- [x] **Files:** `bridge.py` (`prompt`, `last_said`); the fake OpenCode of `tests/components/agents/test_sessions.py`
  reads a path without its query (a page asked for is the whole list there). `Sessions.send` taking an agent and a
  model went to Task 8, with the service's other changes.
- [x] **Interfaces:** `prompt PORT SESSION` with `{"text", "files", "agent"?, "model"?: {"providerID", "modelID"}}`;
  without them, the agent and the model of the session's last message of the owner (its `variant` too), found a page
  at a time; a session without one sends none, as before. Its answer names the agent and the model sent.
- [x] **Tests:** a planner session stays planner after a note; an agent and a model given are sent instead; the
  owner's last message is found however far back, with its variant; a new session's first message names none.

### Task 3: Rejecting what waits, clearing a result, reverting

- [x] **Files:** `bridge.py` (`reject`, `clear`, `revert`, `unrevert`).
- [x] **Interfaces:** `reject PORT SESSION` rejects the asks and questions waiting in the session and its subagents
  (`/session/:id/children`), one ask at a time until none is left (OpenCode rejects a session's other asks with the
  first); `clear PORT SESSION MESSAGE PART` writes the whole part back with `state.time.compacted` set (OpenCode's
  `PATCH .../part/:id`), refused for a step not finished, for a part that is not a finished tool call;
  `revert PORT SESSION MESSAGE [PART]` and `unrevert PORT SESSION`.
- [x] **Tests:** Stop's reject leaves nothing waiting in the session or its subagent and touches no other session;
  a cleared result is sent whole with its time; the step in progress and a text part are refused, saying why; revert
  names the part, unrevert follows.

### Task 4: Compacting without waiting

- [x] **Files:** `bridge.py` (`summarize`, `held`).
- [x] **Interfaces:** `summarize PORT SESSION` (`{"providerID", "modelID"}` given, else the session's model) starts
  `held`, a process of the bridge in a session of its own that sends `{"providerID", "modelID", "auto": true}` and
  keeps the connection until OpenCode answers; the bridge returns `{"asked": true, "answered": false}` within a
  second or so, or OpenCode's error when it answers at once.
- [x] **Tests:** summarize returns at once while OpenCode works, and the request stays open until OpenCode answers;
  an unknown session's error is said.

### Task 5: The listing keeps subagents

- [x] **Files:** `bridge.py` (`servers`); `tests/components/agents/test_sessions.py`.
- [x] **Interfaces:** each server's `children`: its subagents' sessions, each with its `parent` and its status;
  `sessions` stays the root sessions, so the phone, This folder and the plan handover read what they read.
- [x] **Tests:** the listing gives the subagent beside, not among, the root sessions.

### Task 6: The watch forwards the Monitor's events, once per burst

- [x] **Files:** `bridge.py` (`Watch`: `hold`, `_write_held`, the `_writer` thread; the lines below).
- [x] **Interfaces:** new lines, each with its `port`: `status` (a session's `idle`, `busy` or `retry` with its
  attempt, message and next time; those busy are said when a server is first followed), `session` (created, updated or
  deleted, a subagent with its `parent`), `message` (`seen_message`), `part` (`seen_part`), `removed` (a message or a
  part), `todo`, `compacted`, `error`, `question` and `answered` (a question asked, and replied or rejected; those
  waiting when a server is first followed too), `disposed` (OpenCode's instance ended); held and coalesced per burst,
  but for `question`, `answered` and `disposed`, which are said at once as the review's lines are.
- [x] **Tests:** replaying a step's burst gives each kind once, with its last state, a status that went busy and
  idle said idle after the step's parts; a subagent's session and status come with its parent; a server first followed
  says its busy sessions and its waiting questions; the review's lines still come at once.

### Task 7: The text as it is written, only for the sessions shown

- [x] **Files:** `bridge.py` (`Watch._until_input_closes` reads `{"shown": [...]}` lines; `delta` lines).
- [x] **Interfaces:** a line `{"shown": ["ses_..."]}` on the watch's input sets the sessions shown and is answered
  `{"type": "shown", "sessions": [...]}`; `message.part.delta` events of those sessions are joined per part and field
  and said once per burst as `delta` (`message`, `part`, `field`, `text`); of other sessions, never.
- [x] **Tests:** a shown session's deltas come joined in one line per part; another session's never; nothing shown,
  none.

### Task 8: The service knows where each session runs, and acts there

- [x] **Files:** `clank/components/agents/sessions.py` (`heard`, `runs`, `seen`, `listen`, `reject`, `compact`,
  `clear`, `revert`, `unrevert`, `page`; `send` and `stop` go to the server that runs the session),
  `clank/components/agents/review.py` (each watcher line to `sessions.heard` too), `clank/components/agents/watch.py`
  (`Watcher.tell`, `Watchers.show`, the shown sessions told again to a watcher started again).
- [x] **Interfaces:** `Sessions.runs(workspace, session) -> int | None` from the watch's lines (the server whose
  stream carried the session's status, messages or parts; none once that server is gone); `seen(workspace)` each
  session seen with its server, status and parent; `listen(heard)` for step 5's flows and design 0013's runner;
  every action takes the port a client names and goes instead to the server that runs the session when one is known;
  `agents.acted` for each (`reject`, `compact`, `clear`, `undo`, `redo`).
- [x] **Tests:** with two servers in one container listing the same session, a note, a stop, a reject, a compaction
  and a clear reach the server that runs it and no other, each recorded; a session no watcher saw goes to the port
  named; a server gone leaves its sessions unplaced; `show` reaches the watch and is told again after it restarts.

### Task 9: Documents and generated files

- [x] **Files:** design 0012 §11 step 4 (*built*), the roadmap's M5 row, the bridge's docstring, `docs/EVENTS.md`
  and the code map and tests page regenerated (`uv run python -m tools.check --fix`), this plan's boxes.
- [x] **Tests:** `uv run python -m tools.check --fix` passes.

### Task 10: After review

- [x] **A server no longer followed is forgotten.** The review found that a session's server outlived a watcher
  started again (a container reopened, as this plan asks for the new image): the service sent the phone's notes and
  stops to a port where nothing listened. Now `synced` drops every port the new watch does not follow, so the session
  goes to the port the client names. Test: `test_monitor_sessions.py`:
  `test_a_watcher_started_again_forgets_a_server_its_sync_no_longer_follows`.
- [x] **A stream opened again says idle for a run that ended.** OpenCode's instance started again (its stream ends,
  its server still listens): the watch now keeps each port's sessions it said running and says idle for those
  `/session/status` no longer lists, so a flow waiting for idle (design 0013 §7) does not wait forever. Test:
  `test_monitor_watch.py`: `test_a_stream_opened_again_says_idle_for_a_session_that_no_longer_runs` (the fake's
  `restart`).
- [x] **reject goes on past a question answered meanwhile**, as it did for an ask; what was rejected is still said
  and recorded. Test: `test_monitor_bridge.py`: `test_reject_goes_on_past_an_ask_or_a_question_answered_meanwhile`
  (the fake's `settled`).
- [x] **A holder that does not confirm in time is ended**, so no compaction starts after the service said it failed.
  Test: `test_monitor_bridge.py`:
  `test_a_compaction_not_confirmed_in_time_is_ended_so_it_cannot_start_after_the_error`.
- [x] **Listeners hear a line once the review has handled it**, so a flow that hears an ask finds its question asked
  (`Review.heard` hands the line to the sessions last). Test: `test_monitor_sessions.py`:
  `test_listeners_hear_a_line_once_the_review_has_handled_it`.
- [x] **The tests the review found missing:** `test_monitor_watch.py`:
  `test_asks_questions_answers_and_an_instance_that_ended_come_at_once_after_what_the_burst_held` (a burst said six
  seconds after its last line, so a line that waited for it would be late) and
  `test_compactions_removals_and_errors_said_again_in_a_burst_are_said_once_with_the_last`; the two-servers test now
  proves that `page` read the history from the server that runs the session (the fake's `read`).
- [x] **Documents:** `agents.acted`'s `detail` describes the new actions' details (the events page regenerated); the
  fixture's sessions carry no OpenCode version, since none was recorded; decision 0079 records call 5.

## Left for later (needs OpenCode 1.19.0 in the sandbox image, which could not start then)

- Record `session.json`'s events from OpenCode 1.19.0 with a scripted model and compare them with the hand-written
  ones (design 0012 §10: how messages page; whether two servers in one container share their sessions).
- That a compaction asked through `held` runs to its end and the run goes on, and that `held` then ends.
- That a note sent with the session's agent and model keeps a planner session planner (design 0012 §10, before
  step 9).
- Rebuild the sandbox image so the workspaces' containers get the new bridge: until a workspace is reopened (F6: `x`,
  then `o`), its old bridge answers the new actions "no action", which the service words as an older image.

## Claude's calls (2026-10-19)

1. **Subagents beside the root sessions.** `servers` gives them under `children`, not among `sessions`, so the phone,
   This folder, the plan handover and Notion's agent read the root sessions they read before.
2. **The sessions shown are told on the watch's standard input** (`{"shown": [...]}`, answered `shown`), which the
   service already holds open to end the watch; no second exec, no file in the container.
3. **A compaction's request is held by `held`**, a process of the bridge in a session of its own, rather than
   dropped: what OpenCode does when its client leaves (its server ends the handler's work, or not) is unmeasured, and
   holding costs one sleeping process for the run's length (twelve hours at most).
4. **A burst** is 0.1 s of quiet, or 0.25 s at most, so a model writing without pause is said four times a second, as
   the console redraws; each key's last value moves to the burst's end, and a line said at once writes the burst
   first, so the order of what happened is kept.
5. **Every action goes to the server that runs the session**, as the watch last saw it, even when a client names
   another port (decision 0048: the Guide acts on the server that runs the session); the port named is used only for
   a session no watcher saw. The phone's messages and stops now follow this too, and keep the session's agent.
   Recorded after review as [decision 0079](../decisions/0079-every-action-on-a-session-goes-to-the-server-that-runs-it.md).
6. **Reject reaches the subagents' sessions**, since Stop stops the whole tree (design 0012 §3); OpenCode's
   `/session/:id/children` names them.
7. **Paging uses OpenCode's own cursor** (`limit`, `before`, `X-Next-Cursor`, read in 1.18.31's program), not the
   whole history read and cut in the container; an OpenCode that ignored `limit` would still be read whole, correctly.
8. **The tests live beside the bridge's other tests** (`tests/components/agents/`) rather than in `tests/contract`,
   which holds one contract per kind of adapter; the bridge is not an adapter. Their events are in `tests/fixtures`.
9. **`Sessions.stop` stays OpenCode's abort**; the Guide's Stop, an abort and a reject together, is step 9's.
