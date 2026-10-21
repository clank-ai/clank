# 0105. With no usable model, the console opens on Add a model: cloud or local, in one pass

- Status: Accepted (the owner's decision)
- Date: 2026-10-20
- Decided by: the owner's fourth answer of 2026-10-20 ("First run: a guided first step. With no usable model, the
  console opens on "Add a model": Cloud (pick OpenRouter, paste the key hidden, pick a model from its live list, Clank
  tests it with one short request) or Local (today's setup guide). One pass and they are working."), written into
  [design 0016](../design/0016-cloud-models.md) §14

## Context
Design 0001 §7.3 (approved) has a five-step first-run guide, `clank setup` or the console's first screen, planned for
M10 and not built. Today `clank` opens the console on This folder, whose "load a model" step lists presets that a new
computer cannot run: no engine installed, no model downloaded, and for a cloud model nothing at all.

## Decision
- When no model is usable (none runs in the main slot, and no preset for it can load now), `clank` and `clank console`
  open on **Add a model**.
- **Cloud**: OpenRouter, the agreement, the key pasted hidden and checked, a model picked from OpenRouter's live list,
  its settings, and a test of one short request; then it is loaded.
- **Local**: today's setup for this machine (Clank's presets, what each needs here, and the operations that install,
  download and load), on one screen.
- One pass: the last screen leads to This folder, where the agent starts.
- It is the first slice of M10's guide; the rest of design 0001 §7.3 stays M10's.

## Alternatives considered
- **The whole M10 guide first** (the machine, where the model runs, install, test, tools): the owner asked for the
  model step now.
- **A command only** (`clank model add`): built too, but a new user starts with `clank`, which opens the console.
- **Open on This folder with a note**: a new user would meet Docker and workspaces before having a model at all.

## Consequences
- The service answers whether a model is usable (`GET /runtime/usable`), and the console reads it at its start.
- Docker is still needed to work in a folder; Add a model's last screen says so and how to get it.
