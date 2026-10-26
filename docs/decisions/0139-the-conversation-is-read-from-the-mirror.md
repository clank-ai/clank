# 0139. A conversation is read from the service's mirror, never from the container at each read

- Status: Accepted (with design 0023, approved by the owner on 2026-10-26)
- Date: 2026-10-26
- Decided by: the owner (approving design 0023 after "sending a message to the agent is fairly laggy"), Claude (the
  measurement and the shape)

## Context

Measured on 2026-10-26: one `docker exec` costs 0.9 s before Python starts; a read of the agent panel's conversation
ran two bridge actions (2.8 to 4.9 s) and the panel polled every 2 s; the owner's message showed 6.1 s after Enter and
a one-word answer 12.2 s after. The service already keeps, for every running container, a watcher fed by OpenCode's
event stream (design 0007 §4, design 0012 §6.1), which hears every message, part, delta, status, permission and
question as it happens; the Monitor reads a brief of it, the panel none of it.

## Decision

- A client's read of a conversation is answered from what the service holds: the mirror of the sessions clients
  follow, built from the watcher's lines, whole (every part's text, a tool's input and output up to the bridge's
  `WHOLE`), with its deltas as they stream.
- A session's history before the mirror began is read from OpenCode once, when it is first followed, and older pages
  once when a client scrolls back; nothing else starts a process in the container for a read.
- The mirror is bounded: whole parts for followed sessions only, up to `FULL_BYTES` a session, and a session no client
  followed for `FORGET_MINUTES` falls back to the brief the Monitor keeps.
- A test counts the processes a followed conversation starts and fails on the first one more than the history's.

## Alternatives considered

- **Reading OpenCode's API directly from the service** through the edge: plain HTTP would be fast too, but needs
  OpenCode to listen on the container's network and the edge to forward a port per server; the watcher is already
  there and already hears everything.
- **A faster bridge** (a resident process per container, decision 0140): it cuts the cost of an action, but a read
  still asks the container for what the service has already heard; both are wanted, this one first.
- **Polling less often**: hides the cost without removing it; what the owner sees stays seconds behind.

## Consequences

- `GET /agents/conversation` answers in microseconds once a session's history is read; the panel, the console and
  the phone get the speed without a change of shape.
- The watch says whole parts for followed sessions (`followed` on its input), beside the brief it says for the rest.
- The stream of design 0023 §3 is built on the mirror's versions.
