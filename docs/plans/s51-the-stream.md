# Plan s51: talking to the agent, step 2: the stream, and the panel on it

Design 0023 §3 and §5 (and §8 step 2), approved 2026-10-26, on the mirror of step 1 ([plan s50](s50-the-mirror.md)):
what happens in a conversation is pushed to the agent panel as it happens, and the panel shows it the way the design
canvas draws it: the owner's message the instant Enter is pressed, the model's words as they stream, the header
following the model, one row of thinking that grows, tool calls as they start, questions inline, the scroll kept.

## What exists

- The mirror (`agents/mirror.py`) holds followed conversations with a version that moves on every change;
  `GET /agents/conversation` answers from it (2 ms).
- The kernel's event stream (`kernel/api.py`, `event_stream`): Server-Sent Events, a memory stream fed from any
  thread, keepalives, `closers` on the app's state so the service's stop ends every stream; `Client.events` reads it
  (Python), `ClankClient.events` with `EventReader` (the extension).
- The agent panel (`agentPanel.ts`) polls the route every 2 s while busy and 8 s idle, and the page (`agent.js`)
  redraws the whole list on each message; `core/conversation.ts` turns messages into items and blocks.

## Tasks

- [x] 1. **The mirror's change log and subscribers**: each change of a held conversation is kept with its version
  (`changes`, the newest `CHANGES`): `message`, `part`, `delta`, `removed`, `status` (busy, the kind), `waiting` (the
  waits open), and `snapshot` when a merge or the cap changed more than one thing; `changes_since(workspace, session,
  version)` (None when the client is behind the log); `subscribe(workspace, session, callback)` called with each new
  version outside the lock, returning what unsubscribes. Pure tests.
- [x] 2. **The stream route** `GET /agents/conversation/stream?folder=&session=&limit=&after=`
  (`agents/streaming.py`): the conversation found as the route finds it; `snapshot` first (the route's answer with its
  version), then each change as an event whose id is its version, gathered for `GATHER_SECONDS` (0.1) so a burst
  comes as one flush; `after` or `Last-Event-ID` resumes from a version, a client behind the log gets a snapshot; a
  `readout` event each second while the session works (`Agents.readout`: the foot's numbers and phase); `session` when
  the folder's newest session changed and none was named (the client reconnects); keepalives; `closing` when the
  service stops. A folder with no session yet: a snapshot saying so, then the newest session watched for. `Client.stream`
  in `clank/client.py` (any stream route). Tests with `live_service` and the mirror fed through the sessions' lines.
- [x] 3. **The extension's live state** (`core/live.ts`, pure, Node tests): `apply(state, event)` for every event,
  the pending owner message (sent, shown at once, replaced when its message arrives, returned with the error when the
  send fails), the version, `reconnect` when the session changed; `ClankClient.stream(path, parameters, signal)`
  generalizing `events`.
- [ ] 4. **The panel on the stream** (`agentPanel.ts`, `agent.js`): one stream while the panel shows (ended when hidden
  or disposed), reconnecting with a growing wait and resuming from its version, falling back to the old polling after
  three failures (said in the header); drawn at most ten times a second from the live state; the header's phase from
  the `readout` events; Enter shows the message at once and clears the composer, Esc stops; the page changes only the
  blocks whose content changed (keyed by id, folds kept), keeps the scroll at the bottom while the owner is there and
  shows "new ↓" when not. Edge page tests: a block changed is redrawn and its neighbors are the same elements; the
  pill; the pending message. Node tests for the panel's decisions.
- [ ] 5. **Docs and the measure**: design 0023 §3 and §5 built, §6's table after step 2 (`bench/talking.py`: the time
  from a delta fed to the fake OpenCode to its event on the stream, and live: Enter to the message shown, the model's
  first token to its words shown); the generated docs; `vscode/README.md`.

## Progress

Written 2026-10-26, after step 1 was built and measured.
