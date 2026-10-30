# 0149. Dev mode: for testing, every cloud provider is asked for any of a model's providers

- Status: Accepted (the owner's instruction of 2026-10-29: "We should have a 'dev mode' that allows us to override the
  privacy default"); refines [0109](0109-what-clank-sends-openrouter.md), whose policy (no data-keeping providers)
  stays the default; extended by [0152](0152-dev-mode-opens-the-agents-internet.md) (dev mode also opens the agent's
  internet)
- Date: 2026-10-29

## Context

- Decision 0109 asks OpenRouter only for providers that keep no data (`data_collection: deny`), unless the provider's
  record says otherwise. The owner can change one record (`o` on Providers and models, `o` at the agreement, or
  `clank model add`'s question), and the change applies at the next load of a cloud model.
- On 2026-10-29 OpenRouter's public list held 16 free models that take tool calls. The most used of them, NVIDIA's
  Nemotron 3 family and Thinking Machines' Inkling, are served only by providers that may train on what they are sent,
  so under `deny` OpenRouter refuses them. The owner's first tests of Clank alone on Linux are to start on free models.
- The owner asked for a dev mode that overrides the privacy default.

## Decision

- **One setting**: `dev_mode` in the runtime's settings (`config/runtime.json`), off by default. `clank dev on` and
  `clank dev off`, the Providers and models page's `D` (asked first, showing the call it makes) and
  `PUT /api/v1/runtime/dev` turn it on or off; each change is a `settings.changed` event naming who made it.
- **What it does**: while it is on, every request to a cloud provider whose adapter has a data policy goes with
  `data_collection allow`, whatever the provider's record says. That means any of the model's providers, including
  those that may keep or train on what they are sent. It covers the requests the gateway forwards, a load's tiny
  request, the provider's check and a preset's test. Nothing else changes: `zdr`, the agreement, a workspace's bound,
  the MCP servers marked local only and the cost limits stay as they are.
- **From the next request**: the gateway reads dev mode with each route, every second, as it reads the agreement. The
  launch keeps the record's own policy, so turning dev mode off applies at once too.
- **Said where it acts**: while dev mode is on, the console's header has a pill, "dev mode: any provider", in
  `attention`. Each provider's policy line says dev mode beside the record's own, and each request's notes say
  `provider.data_collection allow added (dev mode)`. The provider's check warns, and `clank dev` says whether it is on.
- **The record is never rewritten**: its own policy stays, and applies again once dev mode is off.

## Alternatives considered

- **Only the record's own option (`o`)**: it exists and stays. But it is set per provider, applies at the next load,
  and nothing outside the Providers page shows it. A named mode that the header shows, and that is undone in one step,
  suits testing better.
- **Allow any provider by default**: that would reverse decision 0109 for every owner, for the sake of a test.
- **Dev mode rewriting the record**: turning it off could not then restore what the owner had chosen.
- **A wider dev mode** (also skipping the agreement or a workspace's bound): not asked for. Each would need its own
  decision.
- **An environment variable**: a setting the owner cannot see in a file or in the console is a bug (AGENTS.md).

## Consequences

- Once dev mode is on, free models whose providers may train work for testing. OpenRouter's own account settings
  (openrouter.ai/settings/privacy) can still refuse them; Clank cannot change those, and its refusal now says so
  (design 0016 §8).
- Every client that shows the data policy shows dev mode too (each provider view's `dev_mode` and `said.policy`).
- Any later relaxation for testing joins dev mode only with a decision of its own.
