# 0095. Clank's flow template runs its boxes on "frontier 262K", the model the owner runs

- Status: Accepted (the owner's decision); superseded for the shipped default by
  [0117](0117-a-new-flow-runs-on-what-the-main-slot-runs.md)
- Date: 2026-10-20
- Decided by: the owner. Told that the template named "daily 262K", so a flow made from it would switch the main slot
  away from "frontier 262K" at its first box, they answered: "The other fix is simple and should be done right away."

## Context
Clank's template (`clank/defaults/templates/flow.json`) is the shape every new flow starts from, the next flow too
(decision 0091). Its `defaults.model` named "daily 262K", and no box named a model of its own, so every box ran on
"daily 262K". Since a model per box was built (plan s27), a flow switches the main slot to each box's preset before
the box starts. The owner runs "frontier 262K" (decision 0088) and chose it after long sessions on it, so the first
box of a flow made from the template would have swapped their model out, at the cost of a reload, without them
having asked for it.

## Decision
The template's `defaults.model` is "frontier 262K". No box of the template names a model of its own. A test holds
both.

## Alternatives considered
- **No default model** (an empty `defaults.model`: each box runs on whatever the main slot runs when it starts):
  never switches at all, but a flow would then say nothing of the model it was made for, and its first message's size
  check (decision 0087) would size against whatever happened to be loaded.
- **Keep "daily 262K"**: the preset a fresh install is set up with, but not the one the owner works with.

## Consequences
A flow made from the template, and each next flow, runs on "frontier 262K" and switches nothing while the owner runs
it. A machine without that preset's model file is told so by the flow's check, as for any preset a flow names; the
owner then names another in the flow's `defaults`.
