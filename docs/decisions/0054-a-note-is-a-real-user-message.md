# 0054. A note to the model is a real user message, sent with the session's agent and model

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §9.3's Choice as recommended

## Context
The Guide lets the owner tell the model something while it works ([design 0012](../design/0012-the-monitor.md)
§9.3). There are four ways in: a real user message, hidden text that OpenCode marks as its own, the request's
`system` field, and text the gateway slips into the next request. OpenCode's `prompt_async` stores a message at once,
and a run cannot end without answering it (its `session/prompt.ts`). The bridge sends text only today, and OpenCode
then falls back to the build agent, so a note would turn a planner session into build.

## Decision
- A note is a **real user message**, which OpenCode shows: `prompt_async` while the session is busy, read at the next
  step; on an idle session, it starts a run on the server that ran the session.
- It is sent **with the session's agent and model**, and it **begins with what it is about**, the node under the
  flow's cursor ("About step 12, `bash pytest -q`: …"). The note line shows that, the agent it goes to ("planner")
  and when it arrives.
- **A call waiting for approval** offers "reject with this note" instead: the model reads it as the answer to that
  call and goes on, and no user message is added.
- Before it is sent, the note's window shows what it is estimated to cost.
- Its states: written; waiting (stored, not read yet); read by step *n*; answered. A note the run ended without
  reading is marked, with "send again".
- **Never the `system` field, never text the gateway adds.**

## Alternatives considered
- **Hidden text OpenCode marks as its own**: what the owner told the model would not show in OpenCode's view of the
  session, nor as the owner's words.
- **The request's `system` field**: it makes the engine read everything again (OpenCode's `session/llm/request.ts`).
- **Text the gateway slips into the next request**: the history would never show it, which breaks the transparency
  rule.

## Consequences
- A note likely makes the engine read again everything since the previous user message, and changes what KVMem picks
  for the GPU (§4.4); its cost, and the race of a note at a run's end, are measured before step 9.
- The bridge's `prompt` sends the agent and the model (step 4), which design 0013 needs too.
- In the flow, a note is a yellow node joined to the node it is about, with an arrow into the step that read it.
