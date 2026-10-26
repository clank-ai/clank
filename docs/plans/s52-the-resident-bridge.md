# Plan s52: talking to the agent, step 3: the resident bridge's request channel

Design 0023 §4 (and §8 step 3), decision 0140, approved 2026-10-26: the actions the owner waits on (a message, a new
session, a stop, an answer to a permission or a question, a compaction, a page, a part, the servers) go through the
watcher's own `docker exec`, which already lives as long as the container runs, instead of one `docker exec` each
(0.5 to 2.1 s on the owner's machine, measured in plan s51). The goal: a message reaches OpenCode's `prompt_async` in
under 150 ms. Nothing the owner asked is lost: a watcher that does not answer is ended and started again, and the
request goes once more through a one-off `docker exec`.

## What exists

- The watch (`bridge.py`, `Watch`): one process per running container, reading OpenCode's event streams and writing
  JSON lines; its input carries `{"shown": [...]}` and `{"followed": [...]}` lines from the service.
- The watchers (`agents/watch.py`): `Watcher` (one process, read in a thread, `tell` on its input), `Watchers`
  (`keep` starts and ends them from Docker's reading; a watcher that ends while its container runs is started again,
  later each time).
- The sessions' bridge calls (`agents/sessions.py`, `_bridge`): `workspaces.run_in` of `python3 bridge.py ACTION ...`
  with the body on its input, one run an action; `act(argv)` in the bridge dispatches and reads the body with
  `given()` from standard input.
- The fake OpenCode (`tests/fakes/opencode.py`) and the watch tests that run the real bridge on this machine against it
  (`tests/components/agents/test_monitor_watch.py`, `Watching`; `test_monitor_sessions.py`, `watched`).

## Tasks

- [x] 1. **The bridge answers requests on the watch's input** (`bridge.py`): a line `{"id", "action", "args",
  "body"}` runs `act(args, body)` in a thread of its own (a slow action blocks neither the input nor another request)
  and answers `{"type": "answer", "id", "ok": true, ...}` or `{"type": "answer", "id", "ok": false, "error"}` at
  once, among the event lines; `act` takes the body from a callable (`given` for a one-off run). Tests
  (`test_monitor_watch.py`): `servers` answered with its id; `prompt` reaches the fake OpenCode and its answer says
  what was sent; an unknown action answers `ok: false` with the bridge's words; two requests get their own answers.
- [x] 2. **The service's channel** (`agents/watch.py`): `Watcher.request(action, args, body, timeout)` writes the
  line with a fresh id and waits for its answer (the reader routes `answer` lines to the request waiting, before the
  "bridge without watch" check); `Unanswered` after the wait, `NoChannel` when the watch is not alive and synced or
  its input cannot be written. `Watchers.request(workspace, ...)` with `REQUEST_SECONDS` (10): a watcher that did not
  answer is ended (`keep` starts it again) and `Unanswered` is raised, so the caller sends the request once more
  through a process of its own. Tests: against the real bridge (the fake OpenCode); a deaf watcher (a script that says
  `synced` and answers nothing) for the wait and the end.
- [x] 3. **The sessions go through the channel** (`agents/sessions.py`): `Sessions.channel` (set by `Agents` to the
  watchers' `request`); `_bridge` sends `prompt`, `new`, `abort`, `permission`, `question`, `summarize`, `page`,
  `part` and `servers` through it first and falls back to `run_in` on `NoChannel` or `Unanswered`; the answer is read
  the same way either way. Tests (`test_monitor_sessions.py`): the actions above start no process once the watcher is
  synced (the fake platform's `calls`); a deaf watcher's request goes through a process of its own and reaches
  OpenCode, and the watcher is started again.
- [x] 4. **The measure and the docs**: `bench/talking.py` on the real model (the send's own time, the owner's message
  on the stream); design 0023 §4 and §8 step 3 built, §6's table after step 3; decision 0140 built; the bridge's
  docstring; the generated docs; the roadmap and the plan index.

## Risks named

- A request that reaches OpenCode but whose answer is lost (the watcher ended between) is sent once more: a message
  could be sent twice. The decision accepts it (the watcher's end is rare, and the owner sees both in the panel);
  the one-off resend is logged with the request's action.
- `serve`, `implement`, `show`, `mcp-start` and the one-off actions of a build or an export stay as they are: they
  wait longer than `REQUEST_SECONDS` by design.

## Progress

Written 2026-10-26, after step 2 was built and measured.

- All four tasks built 2026-10-26. Measured live after the service restarted on the channel: the send's `POST`
  92 and 156 ms (was 515 to 2,145 ms), the owner's message on the stream 256 and 239 ms after Enter (was 590 to
  2,130 ms); the
  numbers are in design 0023 §6. Found on the way: `act` in the bridge read its body from standard input, so it takes
  the body from a callable now (the request's own line on the channel); the mirror's process-counting test counts the
  watcher's requests too, since the history's page goes through the channel. A request made from the watcher's own reader thread (the review's
  reply, a listener's read: a line heard) can never see its answer, which that thread reads: it says `NoChannel` at
  once and goes through a process of its own, as before (found by the review's test, which waited the whole
  `REQUEST_SECONDS` for a reply); a watcher stopped is ended from that moment, whatever its reader still reads.
