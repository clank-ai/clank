# Design 0023: Talking to the agent

One live link to each container, and a conversation that keeps up with the model.

The owner, on 2026-10-26, after the first days with the agent panel (design 0021 §4): "sending a message to the agent
is fairly laggy, and talking to the agent and watching it work is not very satisfying yet." This design says why,
with numbers, and what Clank does instead: the conversation is read from what the service already hears live, never
from the container at each read; what happens is pushed to every window as it happens; and acting (a message, an
answer, a stop) no longer waits on a process started for it. The design canvas "Clank · Talking to the agent" draws
the experience; this document says what holds it up.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner felt, measured | Approved 2026-10-26 |
| 2 | The conversation is read from the service's mirror | Approved 2026-10-26 |
| 3 | Pushed, not polled: the conversation stream | Approved 2026-10-26 |
| 4 | Acting without waiting: the resident bridge | Approved 2026-10-26 |
| 5 | What the owner sees | Approved 2026-10-26 |
| 6 | Measurements that hold it to its word | Approved 2026-10-26 |
| 7 | What else it mends | Approved 2026-10-26 |
| 8 | Order of work | Approved 2026-10-26 |

## 1. What the owner felt, measured

Measured on 2026-10-26 on the owner's PC (Docker Desktop over WSL 2), the PC otherwise idle, frontier 262K fast on
the main slot, a throwaway workspace with one session:

| What | Time |
| --- | --- |
| `docker exec <container> true` (nothing else) | 0.9 s |
| One action of the bridge (`servers`, `free-port`): one `docker exec` of `bridge.py` | 1.1 to 1.5 s |
| `docker ps`, `docker inspect` | 0.16 to 0.19 s |
| One read of the conversation (`GET /agents/conversation`: `servers`, then `page`) | 2.8 to 4.9 s |
| `POST .../message` (the bridge's `prompt`) | 5.3 s |
| The owner's message visible in the next read | 6.1 s after Enter |
| The model's first words visible (a one-word answer) | 12.2 s after Enter |

The agent panel reads the conversation every two seconds while the session works (design 0021 §4), so with reads of
three seconds it reads back to back and every frame is about three seconds old; the Monitor's page and the phone read
the same way and queue behind it. Nothing of this is the model's: it answered the word in about a second.

The cause is the shape of the link, not a slow part. Every read is one process started in the container
(`docker exec`, 0.9 s before Python starts), though the service already keeps, for every running container, a watcher
fed by OpenCode's own event stream (design 0007 §4, design 0012 §6.1): every message, part, delta, status, permission
and question arrives there the moment it happens. The panel does not use it; the Monitor uses only a brief of it.

## 2. The conversation is read from the service's mirror

**The rule: a client's read of a conversation never reaches the container.** The service answers from what it holds.

- **The mirror is made complete for the sessions clients follow.** Today the watch keeps a part's text cut at 6,000
  characters and a tool's output at 1,500, a reasoning part's length only, and deltas only for the sessions "shown"
  (the Monitor's). For a followed session it keeps every part whole (text, reasoning, a tool's input and output up to
  the bridge's `WHOLE`), and its deltas as they stream. A session is followed while a client's stream (§3) names it,
  and the newest session of each workspace is followed by default, so the panel opens on a mirror already warm.
- **History once.** When a session is first followed, its messages before the mirror began are read once from OpenCode
  (the bridge's `page`, a page at a time, newest first) and kept; older pages are read when a client scrolls back.
- **Bounded.** Full parts are kept for followed sessions only, up to `FULL_BYTES` (4 MB) a session; past it the oldest
  parts fall back to their brief and are read whole again on demand (`part`). A session no client has followed for
  `FORGET_MINUTES` (30) falls back to the brief the Monitor keeps today.
- **The route stays.** `GET /agents/conversation` keeps its shape (design 0021 §4) and answers from the mirror in
  microseconds; `before` pages from the mirror, else from OpenCode once. The console and the phone, which read it
  today, get the speed without a change.
- **A test counts the processes.** A conversation followed for a minute of fake work starts no `docker exec` after
  its first page; the test fails on the first one more.

## 3. Pushed, not polled: the conversation stream

`GET /agents/conversation/stream?folder=&session=` is one Server-Sent Events stream per client (decision 0017's way
for events; a stream of its own, since it carries a session's text and not the kernel's events):

- First an **opening snapshot**: the conversation as `GET /agents/conversation` gives it, with a `version`.
- Then **what changes**, each with the version after it: `message` (a message's info, new or changed), `part` (a
  part's whole new state: a tool's input, state and output, a text's full text at a step's end), `delta` (text appended
  to a part: its id, the field, the text; batched, at most ten a second), `status` (the session busy or idle, and its
  phase as the Now panel says it, design 0012 §5: reading the prompt with its tokens and speed, thinking, writing,
  running a tool with its command, waiting for you, compacting), `waiting` (the permissions and questions open),
  `session` (the folder's newest session changed, when none was named). A `Last-Event-ID` on reconnect brings the
  snapshot again; a client behind by more than the batch window gets the snapshot, never a gap.
- **The phase comes from the gateway** (its request in flight: `Gateway.activity`), joined to the session as the
  Monitor joins them (design 0012 §3), so the header says "reading your message · 12,300 tokens · 1,800 tokens a
  second" the moment the engine reads, before OpenCode says anything.
- **One stream serves every window**: the agent panel, the console's Monitor and Flow view (which read the flow's
  versions today), and the phone (design 0005, M9) read the same stream; the phone's redesign (the installed app) is
  built on it.
- **Fallback**: a client whose stream fails reads the route at the panel's old pace until it reconnects, and says so
  in its header.
- The VS Code extension reads the stream in its host (Node 22 has no `EventSource` of its own: a small reader over
  `fetch`'s body, no dependency), and posts the changes to the webview, which changes only the items named.

## 4. Acting without waiting: the resident bridge

Each running container keeps one `docker exec` for its life: the watcher's. It gains a request channel, and the bridge
actions the owner waits on go through it:

- The service writes a request line on the watcher's input, `{"id", "action", "args", "body"}`, and the bridge answers
  `{"id", "ok", ...}` on its output among the event lines (the same JSON lines; a request's answer names its id). The
  actions: `prompt`, `new`, `abort`, `permission`, `question`, `summarize`, `page`, `part`, `servers`; `run_in` and the
  one-off actions of a build or an export stay as they are.
- A request waits at most `REQUEST_SECONDS` (10); a watcher that does not answer is ended and started again (the
  watch's own restart, design 0007 §4), and the request is sent once more through a one-off `docker exec`, so nothing
  the owner asked is lost while the link heals.
- **Until the channel is built**, and whenever it is down, the panel shows the owner's message the instant Enter is
  pressed, marked sending, and marks it sent when the mirror shows it; a send that fails puts the text back in the
  composer with the service's words.
- Goal: a message reaches OpenCode's `prompt_async` in under 150 ms, an answer to a permission or a question in
  under 150 ms, where each takes a second or more today.

## 5. What the owner sees

Drawn on the design canvas "Clank · Talking to the agent" (its boards: the path before and after, the panel while it
sends, reads, thinks, writes, runs a tool and waits, and the same stream on the Monitor and the phone):

- **Send**: the message appears at once, quietly marked sending, then sent; the composer clears and keeps focus; Esc
  while the model works is Stop; a failure returns the text with why.
- **The header follows the model**: reading your message (tokens, speed, a thin progress line), thinking (a live
  count and timer), writing, running `python make_fig1.py` (the command, its last lines live), waiting for you (the
  question inline), idle. Each from the stream's `status`, never guessed from the last message.
- **Thinking is one row that grows** ("thinking · 1,240 tokens · 8 s"), folded, expandable; never a row per redraw
  (the live test of 2026-10-26 showed repeated Thinking rows).
- **Tool calls appear as they start**, each with its command, its live output's last lines, then its result folded;
  three or more in a row fold into a step, as the panel does today.
- **Text streams**: deltas appended as they come; Markdown and math render by block, the completed blocks at once and
  the one being written as plain text until it closes, so nothing jumps.
- **Questions and permissions** are cards at the bottom with their keys (y, n, v; the choices), answered through the
  channel; an answered card folds to a line.
- **Scroll** stays pinned to the bottom while the owner is there; scrolled up, a "new ↓" pill, and nothing moves under
  the eye.
- **Pace**: at most ten redraws a second; the page keeps each item by id and changes only what the event names.
- **The foot** reads the gateway's live numbers (speed, context used) from the same stream's `status`.
- The agent panel's remaining items of "A · full design" (jobs tray, artifact previews, change review, the start page,
  Build and Plan, the narrow layout) build on this stream, not on the polling.

## 6. Measurements that hold it to its word

Tests against the fake OpenCode (`tests/fakes/opencode.py`) and a bench on the real one (`bench/talking.py`), before
and after, kept in this section once measured:

| Measure | Today | Goal |
| --- | --- | --- |
| The owner's message visible after Enter | 6.1 s | under 150 ms (shown at once), confirmed under 1.5 s |
| The model's first words visible after its first token | about 6 s later | under 150 ms later |
| One read of `GET /agents/conversation` | 2.8 to 4.9 s | under 5 ms from the mirror |
| A stream event after OpenCode's | (none) | under 100 ms |
| `docker exec` started in a minute of one followed session | about 25 | 0 (one for the container's life) |
| An answer to a permission reaching OpenCode | 1.1 s or more | under 150 ms |

## 7. What else it mends

- The Monitor's redraws (at most four a second from polled versions) become pushes; the Flow view's reads too.
- The phone's live view gets the stream the installed app needs (its design canvas waits on it).
- `bridge.py` (1,165 lines, one process per action) splits: the watcher and its channel in the container, a typed client
  of OpenCode's API in the service (`agents/opencode.py`) tested against the fake OpenCode without Docker. The one-off
  actions stay until the channel carries them all.
- The service's bridge calls no longer queue behind the panel's reads, so builds, exports and `run_in` answer sooner.
- **Clank's programs in the container are mounted, not copied** (a choice this work makes first, since the bridge
  changes most): `bridge.py`, `phone_mcp.py`, `edge.py` and the instructions are copied into the sandbox image today,
  so each change to them rebuilds a 2 GB image and remakes every container (32 image tags were found on the owner's
  machine on 2026-10-26). Mounted read-only from Clank's own package folder into `/opt/clank`, they are always the
  service's own version, and the image changes only when its Dockerfile does. A decision record says so when built.

## 8. Order of work

1. The mirror made complete for followed sessions (§2): the watch keeps whole parts and deltas for a `followed` set
   named on its input (as `shown` is today); history read once; `GET /agents/conversation` from the mirror; the test
   that counts processes.
2. The stream (§3) and the panel on it (§5): the extension's reader, optimistic send, the header's phases from the
   gateway, incremental rendering, the scroll and pace rules; the bench's before-and-after.
3. The resident bridge's request channel (§4): `prompt`, `permission`, `question`, `abort` first; the recovery path.
4. The Monitor and the Flow view on the stream (§7).
5. The phone on the stream, with its redesign (M9).

Decisions this design asks for, written when it is approved: the conversation is read from the service's mirror and
never from the container at each read; one resident process a container, carrying its requests. No new dependency.
