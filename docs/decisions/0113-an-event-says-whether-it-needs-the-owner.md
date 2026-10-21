# 0113. An event type says whether its events need the owner's attention, and each event carries it

- Status: Proposed (Claude's call, on the owner's instruction of 2026-10-21)
- Date: 2026-10-21
- Decided by: Claude, building [plan s34](../plans/s34-cloud-service-and-gateway.md) on the owner's instruction of
  2026-10-21 that the phone app (an installed web app with live updates and push notifications, designed separately)
  be as easy as possible to build: "where the kernel's event kinds allow it, mark which events deserve the owner's
  attention (a severity or notify field); if adding a field is a kernel change, record it in a decision and keep it
  minimal"

## Context

- Every state change of Clank is an event on the kernel's one stream (design 0002 §2.3, decision 0017), each with a
  one-line summary in Clank's own words; a client shows what it follows.
- A phone sends a push notification for only a few of them: a cloud spending limit reached, a question waiting, a
  refusal that stops the owner's work. Today a client would have to know which event types those are, and each client
  (the console, VS Code, the phone) would keep its own list.
- Questions already carry an urgency (`normal`, `high`: "high ones reach the phone at once"), for questions only.

## Decision

- An event type declares `attention` (a yes or no, no by default) beside its fields: whether its events need the
  owner's attention, so a client may notify (a push, a banner) without a list of its own.
- Each event carries it (`attention`), filled from its type when it is recorded and when it is read back; nothing is
  added to the state database, and the events page says it for each type ("kept, needs you").
- The first types that need the owner: `question.asked`, the cloud's `gateway.limit_warned`, `gateway.limit_reached`
  and `gateway.cloud_refused` (design 0016 §8, §11).

## Alternatives considered

- **A severity (info, warning, error) per event**: more than a client needs to decide whether to notify, and every
  existing type would need one chosen.
- **The flag in each event's data, set by whoever records it**: no column either, but the same type could be marked one
  way here and another there, and the events page could not say it.
- **A list in each client**: the phone, VS Code and the console would each keep one, and drift.

## Consequences

- A client notifies on `attention` and shows the event's summary as its title; the summaries of the types marked stay
  Clank's own words (a provider, a model, a workspace, a flow, a box, an amount), never prompt or file text.
- Marking a type is one word in its declaration; a type marked later applies to the events already kept as they are
  read back.
