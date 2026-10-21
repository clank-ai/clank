# 0104. Each cloud request, session and flow shows what it cost; an optional daily or monthly limit pauses cloud requests until the owner raises it

- Status: Accepted (the owner's decision); how cost is known and kept is decision
  [0108](0108-cloud-cost-is-openrouters-own-figure-kept-by-the-service.md)
- Date: 2026-10-20
- Decided by: the owner's third answer of 2026-10-20 ("Cost: show cost and an optional limit. Each request, session and
  flow shows what it cost (from the provider's prices and token counts) on the console, phone and Monitor; an optional
  daily or monthly limit pauses cloud requests when reached, until the owner raises it."), written into
  [design 0016](../design/0016-cloud-models.md) §11

## Context
A cloud model costs money per token, and an agent's session sends its whole history with every request: a long
session can make hundreds of requests of a hundred thousand tokens each. Principle 3 asks that the user see "every
request and what it cost". A local model costs nothing per request, so nothing in Clank counts money yet.

## Decision
- **Shown everywhere it matters**: each request's cost (the Requests page, the Monitor), each session's (the Monitor,
  This folder, the phone, VS Code), each flow's and each box's (the Flow view, the phone), and the totals today and
  this month (Home, the header, the Providers page, the phone, VS Code, `clank cost`).
- **An optional limit**, a day's and a month's, in US dollars, none by default.
- **When a limit is reached, cloud requests pause**: each new one is held before it is sent, and the owner is asked to
  raise the limit, from any client, the phone included; raised, the held requests go on. A day's pause also ends with
  the day, a month's with the month.

## Alternatives considered
- **Show cost, no limit**: the owner asked for a limit.
- **A limit that refuses instead of pausing**: OpenCode would stop each session at the limit, and the owner would send
  each message again after raising it.
- **Rely on OpenRouter's own key limit**: it refuses (402) instead of pausing, and Clank would not show what each
  session or flow cost. Design 0016 recommends it too, as a second guard.

## Consequences
- The gateway holds cloud requests at the limit, as it holds a paused session's (decision 0055).
- Spending can pass the limit by what the requests in flight cost when it is reached; the question says by how much.
