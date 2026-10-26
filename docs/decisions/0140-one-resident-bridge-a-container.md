# 0140. One resident bridge a container, carrying the owner's requests

- Status: Accepted (with design 0023, approved by the owner on 2026-10-26); built at its step 3
- Date: 2026-10-26
- Decided by: the owner (approving design 0023), Claude (the measurement and the shape)

## Context

Every action the owner waits on (a message, an answer to a permission or a question, a stop, a compaction) is one
`docker exec` of the bridge: 1.1 to 1.5 s on the owner's machine, 5.3 s for a send behind the panel's reads
(2026-10-26). The watcher is already one long-lived `docker exec` per running container, reading OpenCode's event
stream for the service's whole life (design 0007 §4).

## Decision

- The watcher's process gains a request channel: the service writes `{"id", "action", "args", "body"}` lines on its
  input and the bridge answers `{"id", "ok", ...}` lines on its output among the event lines. The actions the owner
  waits on go through it: `prompt`, `new`, `abort`, `permission`, `question`, `summarize`, `page`, `part`, `servers`.
- A request waits at most `REQUEST_SECONDS`; a watcher that does not answer is ended and started again (the watch's
  own restart), and the request is sent once more through a one-off `docker exec`, so nothing the owner asked is lost.
- `run_in` and the one-off actions of a build or an export stay as they are.

## Alternatives considered

- **A second resident process** beside the watcher: one more process per container to keep alive, for the same work.
- **OpenCode's API over the network** (through the edge): see decision 0139; the channel needs no change to how
  OpenCode listens.
- **Leaving actions as they are**: a send under 150 ms is design 0023's goal; a process per action cannot reach it.

## Consequences

- One process per container for its life, instead of one per action; a message reaches OpenCode's `prompt_async` in
  under 150 ms (to measure when built).
- Until the channel is built, the panel shows the owner's message the instant Enter is pressed, marked sending.
