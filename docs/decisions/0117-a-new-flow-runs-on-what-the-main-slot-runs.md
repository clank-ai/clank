# 0117. Clank's flow template names no model: a new flow runs on what the main slot runs

- Status: Accepted; supersedes [0095](0095-clanks-flow-template-runs-on-frontier-262k.md) for the shipped default
- Date: 2026-10-21
- Decided by: the owner, preparing the first public beta: a new user's flows must run on the model that user set up

## Context
Decision 0095 made Clank's flow template (`clank/defaults/templates/flow.json`) name "frontier 262K", the preset the
owner runs, so a flow made from it never switched the owner's model away. A new user has no such preset: one who
added a cloud model through OpenRouter has no local model at all, and a flow made from the template would ask for a
preset whose files that user never downloaded. The flows already run a box that names no preset, the flow naming none
either, on whatever the main slot runs when the box starts (design 0013 §7, `clank/components/flows/models.py`).

## Decision
The template's `defaults` names no model (the field is left out; empty means "what the main slot runs"). No box of the
template names one. So a flow made from the template, and each next flow, runs on the main slot's model, local or
cloud, and switches nothing. A planning (decision 0097) tells the model that every box runs on what the main slot runs
when the box starts, unless the user asks for a preset; a draft that names none is written naming none. The Flow view
shows such boxes as on the "main slot's model", and its Models panel says it switches nothing. Tests hold each.

## Alternatives considered
- **Keep "frontier 262K"** (decision 0095): right for the owner's machine, wrong for everyone else's.
- **Name the preset the main slot runs when the flow is made**: it would pin a flow to whatever happened to be
  loaded, and its first switch would surprise a user who changed models since.

## Consequences
- A new flow never switches the main slot; a user who wants a box on another preset names it (`e` on the box, or
  `defaults.model`).
- A flow's first message's size check (decision 0087) sizes against the model the main slot runs, or says its window
  is not known when none runs.
- The owner, who runs "frontier 262K", names it in a flow's `defaults` when a flow should switch to it.
