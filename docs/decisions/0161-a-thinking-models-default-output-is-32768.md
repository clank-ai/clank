# 0161. A thinking model's most output by default is 32,768

- Status: Accepted (the owner's report of 2026-10-29 and the audit of 2026-10-30); revises design 0016 §6
- Date: 2026-11-04

## Context

- A cloud preset's most output was 16,384 tokens unless the owner set another or the model's own is smaller. A
  reasoning model's thinking counts against that limit, so its thinking used it up and its answer was cut: the
  owner's runs stopped with nothing done (decision 0154 now says so and lets the model go on, and decision 0153 lets
  the owner raise it).
- A most output is at most half the context (decision 0153), so the agent keeps room for the conversation.

## Decision

- **By default, a model that thinks gets 32,768 when its context is at least 131,072**; any other keeps 16,384; never
  more than the model's own most, nor half the context (`default_output` in the OpenRouter adapter, the one place the
  numbers live; the guide fills Add a model's settings with it).
- **The setting says what it covers**: for a thinking model, "Its most output, in tokens: its thinking and its answer
  together".

## Alternatives considered

- **The model's own most, always**: some list 128,000 or more, which would take a large share of a small context and
  cost more per request than most answers need.
- **Leave 16,384 and rely on the cut being said**: each cut costs a request and a pause; the owner's first runs hit it
  at once.

## Consequences

- Presets already made keep the most output they have; `e` on Presets, or `clank preset change`, changes it.
- A thinking model's requests may cost more when it thinks long; the cost shows per request, as before.
