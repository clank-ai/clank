# Design 0005: the phone (the first slice of M9)

The owner (2026-10-15): "Getting the phone section to work is a pretty big part of this project. The ability to
connect my phone to a session that is currently running and drive the model from anywhere as well as being able to ask
for certain figures from my phone and have the model either grab them or make them and send them to me is very, very
important." Decision 0012 chose the way: Clank's own page for the phone, over the owner's tailnet only, devices paired
from the computer, push alerts, and the whole switched on and off from Clank. Design 0002 §1-§2 placed it in the
`remote` component and gave paired devices their own access level.

**Status:** written 2026-10-15, every section *proposed*, built as proposed at the owner's
instruction; **Choice** marks what the owner may decide otherwise.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner does | Proposed 2026-10-15 |
| 2 | Reaching OpenCode in a workspace: the session bridge | Proposed 2026-10-15 |
| 3 | Files for the phone: the agent's outbox | Proposed 2026-10-15 |
| 4 | The phone page and who may reach it | Proposed 2026-10-15 |
| 5 | The console's Phone page | Proposed 2026-10-15 |
| 6 | What waits | Proposed 2026-10-15 |

## 1. What the owner does

- On the computer, once: the console's Phone page (F9), `x` turns remote access on (Tailscale publishes Clank's phone
  page on the tailnet only), `p` pairs a device: it shows the page's address and an eight-character code, good for
  fifteen minutes and once.
- On the phone: open the address, type the code. From then on the phone sees the workspaces where OpenCode runs, each
  session's conversation as it goes, and can: send a message to a running session (the same session the owner sees in
  VS Code or the terminal), start a new one in any workspace (Clank starts OpenCode without a terminal when none runs
  there), stop the agent, allow or refuse what it asks to do, answer its questions and Clank's, and see the files the
  agent sent, figures shown inline.
- "Send me the figure of …": the agent finds or makes the figure and sends it with its `send_to_phone` tool (§3); it
  shows in the conversation on the phone and in the phone's list of files.

## 2. Reaching OpenCode in a workspace: the session bridge

- OpenCode serves an API while its terminal interface runs (`--port`): sessions, their messages, sending a message
  without waiting for the answer (`prompt_async`), stopping, the permissions and questions waiting with their replies,
  and a stream of events. The terminal interface shows what arrives through the API as it shows what is typed.
- Clank starts every OpenCode with a port of its own inside the container (the first free one from 4096), so each
  terminal in VS Code or the console can be reached; the port listens on the container's loopback only, so nothing
  outside the container reaches it but `docker exec`.
- **Choice: how the service reaches it.** Recommended and built: a small program in the sandbox image
  (`/opt/clank/bridge.py`, Python's standard library only) that the service runs with `docker exec`, one run an action:
  list the servers and their sessions, statuses, permissions and questions; a session's messages (briefly: text, tools
  with their titles and states, files); send a message; start a session; stop; reply to a permission or a question;
  find a free port; start OpenCode without a terminal. No port of the container is published and the edge is unchanged.
  The other way, the edge forwarding the service to each container's port, is faster per call but opens a way in.
- The agents component owns it (`sessions.py`) and its routes (`/agents/sessions/...`), so the console and VS Code can
  use it too; every message sent and every reply is recorded as an event with who did it (a device, the console).

## 3. Files for the phone: the agent's outbox

- Clank gives every agent its own MCP server, `clank` (`/opt/clank/phone_mcp.py` in the image, standard library only),
  with one tool, `send_to_phone(path, caption)`: it copies a file of the folder into the folder's `.clank/outbox/`
  (with a `.json` beside it: the caption, when, which session) and says it is sent. `.clank/` holds a `.gitignore` of
  its own, so git ignores it.
- The service looks at each open workspace's outbox every few seconds (the folder is on this machine), records
  `remote.file_sent`, and the phone shows each file, an image inline.

## 4. The phone page and who may reach it

- **The page** is the remote component's: plain HTML, CSS and JavaScript in Clank's package (nothing fetched from
  elsewhere), made for a phone's screen, kept current by asking every few seconds while it is open. *Revised
  2026-10-15 at the owner's word ("more basic and terminal-like ... much easier to navigate ... prioritize the amount
  of information available from the phone home screen"):* it looks like the console (monospace, the console's colors,
  thin rules, rows to tap) and has three tabs at the bottom. **now** shows, in this order: the status (the model and
  its state; what the agent's model does this moment, read from the gateway: writing, its tokens and speed, or idle
  and how the last request went; the GPU and the CPU as gauges), what waits for the owner (permissions with their
  diff, questions), the sessions working now, the recent ones, a box to start a task, and the last files sent.
  **work** lists every workspace (the running ones first); a workspace shows its sessions and its own new-task box.
  **files** shows everything sent. A session shows its conversation, what waits in its workspace, and a composer that
  stays put while the page reads again.
- **Its listener**: a second address of the service, `127.0.0.1:7721`, which answers only the phone's routes; `tailscale
  serve` publishes it on the tailnet only (`https://<machine>.<tailnet>.ts.net:8445`, Tailscale's certificate) while
  remote access is on, and is told to stop when it goes off. The local API (`7720`) never answers the tailnet.
- **Every request** must come through Tailscale from the tailnet (a tailnet address, Tailscale's verified login in its
  header, never Funnel's public marker) and, but for pairing, carry a paired device's token (a cookie the page keeps):
  Tailscale's login is the first factor, the device the second. A device is paired only with a code made on the
  computer (the console or `clank remote pair`), typed on the device; codes are kept as hashes, used once, wrong ones
  counted (eight in fifteen minutes, then entry rests). A device's token lasts 30 days from its last use, 90 from its
  pairing, and is revoked from the computer.
- **What a device may do**: what §1 lists, in the workspaces Clank knows; it cannot pair other devices, change Clank's
  settings or reach the local API.

## 5. The console's Phone page

F9: whether remote access is on and its address; `x` turns it on or off; `p` pairs a device (the code and address,
shown until used or expired), `c` cancels the code; the paired devices with their last use, `d` revokes the highlighted
one; the files the agent sent and the last things done from a device.

**Everything exchanged, seen from both ends** (*added 2026-10-15*, the owner: "a major component of this project is
transparency, so I need to be able to see anything that is happening behind the scenes whenever I look"). Every request
of the phone's listener and its answer is kept (`remote/traffic.py`): when, which device, method, path and query,
status, time, bytes each way, and both bodies (JSON as it was, text as text, a picture by its type and size), in
`logs/phone/<day>.jsonl` for seven days. The device's token is never kept and a pairing code is masked; an answer the same
as the one before to the same request is kept as a reference to it. On the console, Enter on a device (F9) opens its
exchanges, newest first, the highlighted one whole; on the phone, the log tab shows that phone's own.

## 6. What waits

- **Push alerts** (decision 0012): Web Push needs its encryption (RFC 8291) and a key pair: a new dependency, so a
  decision record first. Until then the page shows what waits as soon as it is opened, and a phone's browser can keep
  it open.
- Live streaming of the answer as it is written (OpenCode's event stream through the bridge); the page asks every few
  seconds instead.
- Reviewing the agent's changes as diffs on the phone (M6, with VS Code's).
