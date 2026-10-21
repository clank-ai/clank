# 0101. The Flow view shows the planning while it is open: its steps, the latest draft drawn and marked DRAFT, its session live

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, building the owner's request to "watch the flow being built while the model is working"
  ([design 0013 §15](../design/0013-flows.md#15-a-flow-built-with-the-model), [plan
  s33](../plans/s33-flows-watch-the-flow-built.md))

## Context
Until now the Flow view showed only flows with a file, so a planning showed nothing until its first draft was
written, and a refused draft never showed at all. The model's drafts reached Clank and were answered, but only the
model saw them. The owner's SSH windows will be about half a screen wide, where the Flow view's panels stack: the
flow, then Selected, then the others.

## Decision
- **Which planning.** A folder's Flow view shows its workspace's newest planning while it is waiting, opening, talking,
  or failed with no run started since, before any flow; built, the view is the built flow, as before.
- **Its steps**, in the panel that Selected is otherwise (right under the flow when stacked), titled "Building it with
  the model": started; reading the folder, with the session's tool calls so far; waiting for your answer (the session
  idle after the model's message, or a question of its waiting); `BRIEF.md` written or changed since the planning
  began, with its time; each draft as sent, its number and time, refused with each problem (its field and message) or
  accepted. Inside it, a Live box for the planning session, as a running box has one.
- **The latest draft** is kept with the planning in Clank's state (`draft.json`, the values Clank would write), with
  each draft's number, time, state and problems, never in the folder. The view draws it with the Flow view's own
  layout, marked DRAFT in the heading and the Flow panel's note, refused or not: the boxes that read and the lines
  between them, so the flow is drawn as far as it reads.
- **Waiting for you** says how to talk with the model until the session runs (the attach command, or where OpenCode
  opened), then what the session waits for.
- **Enter** opens the Session view on the planning session, and from it the Context view; Esc comes back.
- **Read once a second**, as the Flow view reads a flow, and drawn again only where it changed (its version).

## Alternatives considered
- **A new panel for the planning**: at half a screen's width it would stack below the flow, Selected and Models in this
  flow, out of sight.
- **Drawing only a draft that keeps every rule**: the owner would not see the flow take shape while the model fixes it.
- **The draft in the folder**: the model, or a box, could then write the flow (decision 0066 keeps flows out of the
  sandbox's reach).

## Consequences
The owner sees the model's work as it goes: what it reads, what it asks, the brief, and each draft with Clank's
answer. Selected's box details are behind `?` while a planning is shown.
