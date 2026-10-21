# 0080. A step pairs with its request by the answer's call ids, else in order by time; the gateway gives a session's requests

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-19
- Decided by: Claude, without the owner (plan s15's call 4, building design 0012's step 5); it makes
  [0049](0049-a-sessions-flow-is-built-in-the-service.md)'s "joined to the gateway's requests by session id" exact

## Context
Decision 0049 joins a session's steps (OpenCode's assistant messages) to the gateway's requests by session: a session
makes one model call at a time, so they pair in order, and each answer's tool-call ids, equal to OpenCode's call ids,
confirm the pairing ([design 0012](../design/0012-the-monitor.md) §6.1). Three things make "in order" less simple
than it reads: the gateway's activity named only each session's last request; a step may have several requests
(OpenCode retries, the gateway sends a request again after its engine broke off); and a session joined mid-run, or
one whose older requests the gateway no longer keeps, has steps with no request to pair. Whether KVMem streams an id
with every tool call is not measured yet (design 0012 §10). A step's start is written by OpenCode on the container's
clock, a request's by the gateway on this machine's.

## Decision
- **The gateway gives a session's requests**: asked for them (`GET /activity?session=...&ended=true`), its activity
  lists the session's own requests that ended, oldest first, numbers only, up to 64 of each session it keeps; every
  request in flight and ended names the ids of the calls its answer made (`calls`), kept in its record too. The
  service asks once a second at most, after the session's steps changed; it never reads the records for it.
- **Call ids first**: a request whose calls are one step's calls is that step's, confirmed.
- **Else in order by time**: a request pairs with the step, after the one the request before it paired with, that
  began nearest to when the request began, among those that began no later than 2 seconds after it; steps passed
  over had requests the gateway no longer keeps. When no later step began by then, the request is another try of the
  step before it, and a step's last request is its answer. The pairing says which way it was made.
- **Never a step from before Clank watched**: steps a flow's first reading of the history found finished are not
  paired (design 0012 §3: "without the gateway's timings").

## Alternatives considered
- **The last request only, asked when a step ends**: a step that ends while the next one's request already ended, or
  a round asked late, would shift every pairing after it.
- **Strictly in order, one request a step**: retries would push every later pairing one step on.
- **The latest step begun by then**: wrong whenever a request is shorter than the clocks' difference; the nearest step
  is right unless the clocks differ by more than the time between two steps.
- **Reading the records**: they hold each request's whole body again (decision 0049).
- **A note in the request's body naming the step**: the gateway never changes what OpenCode sends (decision 0056).

## Consequences
- With KVMem streaming call ids, steps with calls are paired exactly; steps without calls, and every step until that
  is measured, are paired by time and say so.
- Two clocks more than a second apart, with steps quicker than that, can pair a request with the next step; the
  measurement of the clocks is pending (plan s15).
- The gateway's activity keeps a little more per session (64 requests' numbers).
