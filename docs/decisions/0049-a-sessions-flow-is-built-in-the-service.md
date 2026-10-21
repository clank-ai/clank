# 0049. A session's flow is built in the service from OpenCode's events, joined to the gateway's requests

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three")

## Context
The Monitor draws each session's flow, its Watch for rules act on that flow while no console is open, and the phone
is to show it later ([design 0012](../design/0012-the-monitor.md) §6.1, §8). OpenCode's event stream (`GET /event`)
carries every session of the folder, children included: messages, their parts and deltas, `session.status`,
`todo.updated`, `session.compacted`, and the permission and question events; the bridge's `watch` forwards almost
none of it today. OpenCode keeps a part's text only at its start and its end, and holds a call's arguments as `{}`
until they are complete. Only the gateway sees the time to the first token, the speed, the live text, the loop guard's
state and the engine's errors.

## Decision
- **OpenCode's events are the spine**: one step is one assistant message, with its reasoning, its text, its tool
  calls, its finish and its patches.
- **Forwarded** by the bridge's long-lived watch (design 0007 §4), coalesced, children included, with deltas only for
  the session the page shows, in batches.
- **Joined to the gateway's requests** by session id: a session makes one model call at a time, so its requests and
  its steps pair in order, and each answer's tool-call ids, equal to OpenCode's call ids, confirm the pairing.
- **Kept in the service** by the agents component: a flow for every session the watchers see, each with a version;
  the console asks for what changed since its version, as `/gateway/live` serves text after an offset.
- **Rebuilt from OpenCode's history**, a page of messages at a time, when the service starts again, or when OpenCode's
  server ends (`server.instance.disposed`) and starts again; **never from the gateway's records**.
- **No database table at first.**

## Alternatives considered
- **The flow built in the console**: the rules could not act while no console is open, and the phone could not show
  it.
- **Rebuilding it from the gateway's records**: they hold each request's whole body again.
- **OpenCode alone, or the gateway alone**: OpenCode lacks the timings, the live text and the loop guard; the gateway
  sees model requests only, not the calls' states, the todo list or the asks.
- **Reading each session through the bridge as the page refreshes**: each read is a `docker exec`, and its replies cut
  a call's input to 400 characters and its output to 1,500. The Tool calls panel reads so, only while the page is on
  screen, until the forwarded events make it live.

## Consequences
- The bridge's watch forwards the Monitor's events, with each session's status and server, in step 4; the flow in the
  service is step 5.
- How OpenCode's messages page (`limit`, `before`), and whether KVMem streams an id with every tool call, are measured
  first.
- A flow lost when the service stops is rebuilt, not restored.
