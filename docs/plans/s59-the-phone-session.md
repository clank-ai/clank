# Plan s59: Clank for iPhone, step 2b: a session, the Guide, its context

Design 0025 §7 and §11 step 2 (its session half), on step 1's app ([plan s57](s57-the-phone-app.md)), the Flows tab
([plan s58](s58-the-phone-flows.md)) and design 0023's conversation stream: a session's screen on the phone moves
with the stream (the message shown at once, the words as they stream, the live line marked, no polling), with the
Guide under it (Stop, Note, Pause, Compact, Undo, Drop, each with what it costs) and its context (the window used,
the compaction line, what fills it, the biggest items with Drop). The flows' running box and the planning open their
sessions here.

## What exists

- The conversation stream (`agents/streaming.py`, `GET /api/v1/agents/conversation/stream`): `connected`; a
  `snapshot` (the conversation route's answer: the session, its server's port, whether it is busy, a page of its
  messages in the Monitor's shape, what waits in it) with the mirror's version; then `message`, `part`, `delta`,
  `removed`, `status`, `waiting`, each with its version as the event's id; a `readout` each second while the session
  works; `session` when the folder's newest changed and none was named; `after` and `after_session` resume. The
  extension's client (`vscode/src/core/talking.ts`: `applyEvent`, `sent`, `failed`, `liveItems`) and its items
  (`conversation.ts`) are the reference.
- `Agents.folder_of(workspace)`, `Agents.conversation`, `Agents.readout`, `Agents.context` (the totals: the window,
  used, left, the compaction line, the cache share, the GPU, whose conversation the engine holds, the parts with
  their items), the Guide (`agents.guide.offer`: each action with its title, key, whether it can run and why not,
  what it does, its calls, its cost and its state; `stop`, `note`, `compact`, `undo`, `redo`, `drop`) and the pause
  (`agents.pausing.pause`, `resume`); the kernel's API routes over them (`agents/api.py`).
- The phone's session page (`app.js`: `sessionParts`, `drawSession`, `loadMessages`, `followSession`): the bridge's
  brief messages read every two to eight seconds, a composer, Stop; the listener's `/api/sessions/...` routes.

## Choices made here

- **The agents service exposes the stream** (`Agents.conversation_stream(...)`), so the listener reaches it through
  the service, as the architecture check holds (a component imports another's service only); the kernel's API keeps
  calling `streaming` directly, in its own component.
- **The phone's client is the extension's, ported** to `model.mjs` (`emptyTalk`, `applyTalk`, `sentTalk`,
  `failedTalk`), with the same Node tests' cases, so both clients read the stream alike; the items are drawn by
  `app.js` from the Monitor's message shape (the owner's words, the model's text, thinking folded with its length,
  each tool call one line with its state, a failed step, a compaction, the live part marked LIVE while the session
  works, a message sent shown at once as pending).
- **Polling goes**: the session screen opens `GET /api/conversation/stream` with its workspace and session; the
  listener names the folder; `Last-Event-ID` resumes; the stream's `readout` draws the header (the phase, the speed,
  the window's share). The listener logs the stream as one line, as it logs the phone's own stream.
- **The Guide is a sheet** under the conversation, read once when opened and again after each action: each action a
  button with its title and its cost's words, disabled with `why` when it cannot run; Stop runs at once; the others
  ask once more as `confirm` says; Note sends the composer's text as a note; Undo sends the revert the offer names
  (its message and part, the steps and the owner's messages it takes); Drop takes an item from the Context sheet.
- **Context is a sheet** too: the window used of the whole with the compaction line, what fills it (each part's share),
  the biggest items (the top eight, each with its step, its tool and its tokens) with Drop for a finished call's result.
- **Actions carry the device as actor**, as every action of the phone does.

## Tasks

- [x] 1. **The stream through the service** (`agents/service.py`: `conversation_stream(folder, session, limit, after,
  closers, after_session)`); the listener's `GET /api/conversation/stream` (`remote/sessionapi.py`: `workspace`,
  `session`, `limit`, `after`, `after_session`, `Last-Event-ID`; the folder from the workspace; 404 for a workspace
  Clank does not have), logged as one line. Tests (`tests/components/remote/test_phone_session.py`, over a real
  server as the phone's stream is tested): `connected`, then the snapshot of a workspace with no session yet; a
  change on the stream (a message fed to the mirror) within the gather window.
- [x] 2. **The Guide and the context on the listener** (`remote/sessionapi.py`): `GET /api/guide/{workspace}/{session}`
  (the offer), `POST .../{action}` for stop, note (`text`, `about`), compact, pause, resume, undo (`message`, `part`,
  `steps`, `said`), redo, drop (`part`), each the device's; `GET /api/context/{workspace}/{session}` (the totals).
  Tests on the flows rig (a box's session): the offer lists the actions; a stop from the phone is recorded as the
  device's; the totals pass through; an unknown action is 404.
- [ ] 3. **The client's logic** (`page/model.mjs`: `emptyTalk`, `applyTalk(talk, name, data, id)`, `sentTalk`,
  `failedTalk`, `talkItems(talk)`; `liveIndex(talk)` the part marked LIVE). Node tests (`tests/phone/talk.test.mjs`):
  a snapshot replaces the conversation; a delta appends to its part as the model writes; a part replaces the part;
  removed takes a part or a message; status and waiting change theirs; a message sent shows at once and settles when
  the mirror heard it; `session` names the one to open.
- [ ] 4. **The screen** (`page/app.js`, `page/style.css`): the session opened from Now, Work, a flow's box or a planning
  draws from the stream (the header with the model's phase, speed and the window's share from the readout; the
  conversation's items; what waits in the session answered in place; the composer with Send, the message pending at
  once); the Guide sheet and the Context sheet (`Guide`, `Context 16%` buttons); the stream closed when the screen
  closes; `loadMessages` and `followSession` go.
- [ ] 5. **Docs**: design 0025 §7 built and §11 step 2 whole; the roadmap (M9); the plan index; the generated pages.

## Progress

Written 2026-10-26. Tasks 1 and 2 built 2026-10-26 (the Guide's own rules stay its tests'; the listener's test cans
the offer and checks the route's part). Tasks 3 to 5, the client's logic, the screen and the documents, are next.
