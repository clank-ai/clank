# Plan s50: talking to the agent, step 1: the mirror

Design 0023 §2 and §8 (step 1), approved 2026-10-26: the conversation is read from the service's mirror, never from the
container at each read. Before it, the choice §7 makes first: Clank's programs in the container are mounted, not
copied, so this plan's changes to the bridge (and every later one) rebuild no image.

## What exists

- The watchers (`agents/watch.py`): one `docker exec bridge.py watch` per running container; its lines go to the review,
  then to every listener of `Sessions.listen` (the kept flows, `sessionflow/kept.py`, among them). The service tells a
  watch the sessions `shown`, whose text deltas it then says.
- The bridge's `watch` (`image/bridge.py`, class `Watch`): `message`, `part` (`seen_part`: text cut at `TEXT`, a tool's
  output at `OUTPUT`), `delta` (shown sessions only), `status`, `session`, `asked`/`replied`, `question`/`answered`,
  `removed`, `synced`, `gone`, `disposed`; and its actions `page` (a page of messages, the same cut shape) and `part`
  (one call whole).
- `Agents.conversation` (`agents/service.py`): `servers` and `page` through the bridge at every read.
- The sandbox image copies `edge.py`, `bridge.py`, `phone_mcp.py`, `find_figures.py` and `python/` to `/opt/clank`;
  its tag is the checksum of the whole image folder, so each change to them rebuilds it.

## Tasks

- [x] 1. **Programs mounted, not copied** (decision 0142): `ContainerSpec.programs`, the folder mounted read-only at
  `/opt/clank` by `run_arguments`; the workspace's, the setup's and the edge's specs mount Clank's image folder; the
  Dockerfile copies nothing; `image_tag` is the checksum of the Dockerfile alone. Tests: `test_sandbox.py` (the mount,
  read-only, in each spec), a tag that changes with the Dockerfile and not with `bridge.py`.
- [x] 2. **The bridge says whole parts for followed sessions**: `{"followed": [...]}` on the watch's input, answered
  `followed`; for those sessions `part` lines carry the part whole (`seen_part(part, whole=True)`: text and reasoning up
  to `WHOLE`, a tool's output up to `WHOLE`, `whole: true`) and deltas come as for shown sessions; `page` takes
  `--whole`. `Watchers.follow(workspace, sessions)`, told again to a watch started again; `Sessions.page(..., whole=)`.
  Tests: `test_monitor_watch.py` (a followed session's part whole, another's cut, deltas for both), the telling and
  telling again, `page --whole`.
- [x] 3. **The mirror** (`agents/mirror.py`, `Mirror`): per followed `(workspace, session)` the messages (info) and
  their parts whole, in order; the session's status, port and title; the permissions and questions open; a version.
  `heard` takes the watchers' lines (`message`, `part`, `delta`, `status`, `session`, `asked`, `replied`, `question`,
  `answered`, `removed`, `synced`); `merge(page)` takes a history page; `conversation(workspace, session, limit,
  before)` answers from memory in the route's shape, `None` when the session is not complete; `sessions(workspace)`
  the sessions known, newest first; `follow`, `unfollow`, `forget` (`FORGET_MINUTES` 30) and the cap (`FULL_BYTES` 4 MB:
  the oldest parts' text cut back to `TEXT`). Pure tests with fed lines: `test_mirror.py`.
- [x] 4. **The route from the mirror**: `Agents.conversation` follows the session (the mirror told, the watch told),
  reads its history once (`page --whole`, newest pages up to `limit`), and answers from the mirror; `before` from the
  mirror, else one page read and kept; the sessions listed from the mirror, `servers` only when it knows none; the
  waits from the mirror. The process-counting test: the fake OpenCode with the bridge on this machine, `inside`
  counted; a conversation read, then fed events (a message, parts, deltas, a status) and read ten times: no process
  after the history's, the text whole and the newest words there. The panel's shape unchanged (`test_conversation.py`
  still passes).
- [x] 5. **Docs and the measure**: design 0023 §2 built, §6's table given the mirror's read time (measured live:
  `bench/talking.py`, a read of the route before and after); decisions 0139, 0140 (accepted with the design); the
  generated docs; `vscode/README.md` where it says how the panel reads.

## Progress

Written 2026-10-26, after the owner approved designs 0023 and 0024 ("Approve both designs, go ahead with 0023's first
step").

- All five tasks built 2026-10-26. Measured live after the service moved to the mirror: a read of the conversation
  takes 2 ms at rest and 3 ms while the model writes (median), against 2.8 to 4.9 s before; the first read of a session
  reads its history once (1.0 to 1.3 s). Found on the way: a mirror that kept a session's port after its server was
  gone (the throwaway container made again) read from a port that answered no more; a `synced` or `gone` line now
  leaves such sessions without a port, and the route lists the servers again. The owner's workspaces move to the
  mounted programs when next stopped and opened; until then their watch says parts in the brief, as before.
