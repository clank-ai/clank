# 0131. The Flow view shows the running box's session: its thinking, its tool calls and its context window

- Status: Accepted (the owner's request of 2026-10-23, built as Claude's call); revises 0125's arrangement of board D1
- Date: 2026-10-23
- Decided by: Claude, at the owner's request

## Context
- The owner, watching a long run: "move the 'waiting for you' and 'Models in this flow' boxes down so that we can
  include boxes for the thinking and the tool calls/context viewer."
- Seeing what the box at work does meant leaving the flow for the Session view (Enter on the box), losing the flow.

## Decision
- Under the flow: **Selected beside Thinking**, then **Tool calls beside Context window**, then the **Orchestrator
  beside Waiting for you**, then **Models in this flow**, The brief, checked, Deliverables and Ahead.
- The three new panels show the running box's session (the planning's while a flow is built), each naming it ("TASK
  search · try 1"): Thinking its model's text as it is written (the Session view's live text), Tool calls its calls,
  newest first, Context window its totals. They are read as the Session view reads its own session (a second
  `Following`, pinned to the box's session, and the gateway's live text), only while the Flow view is on screen.
  Between boxes they say no box is at work.

## Alternatives considered
- **The Session view's panels in a split of the screen**: the Session view stays, a tab away, with the Guide.
- **Following the folder's newest session**: an orchestrator's checkpoint is newest while it reads; the box at work is
  what the flow's panels are about.

## Consequences
- The Flow view reads three things more while a box runs; nothing while it is not shown.
- The Selected panel's Live box stays, the box's step, speed and context at a glance.
