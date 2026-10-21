# 0114. A question's option may ask for a number, with its bounds and unit, checked when it is answered

- Status: Proposed (Claude's call, on the owner's instruction of 2026-10-21)
- Date: 2026-10-21
- Decided by: Claude, building [plan s34](../plans/s34-cloud-service-and-gateway.md) on the owner's instruction of
  2026-10-21: "Raising a limit needs an amount: give the question a generic typed answer (a number with bounds and a
  unit) rather than a console-only form, so the phone, VS Code and the console all answer it the same way"

## Context

- Clank asks the owner through the kernel's questions (design 0002 §2.5): an approval, a choice, or an answer in words,
  answered once from any client, the answer recording who gave it.
- Design 0016 §11's limit question offers *raise it to …*: an amount. As a choice whose answer carries the amount in its
  words (`text`), each client would have to know that this option wants a number, which bounds, in which unit, and the
  service would check nothing until it read the words.

## Decision

- A question's option may declare `asks`: the answer it needs besides the option, a number (`kind: "number"`) with its
  `unit` (such as `USD`), its bounds `min` and `max`, and its `step` (such as `0.01`; none: any number), the shape the
  clients of plan s35 read: `{"kind": "number", "unit": "USD", "min": 5.02, "max": 100000, "step": 0.01}`. The option's
  own label says what the number is.
- Answering that option takes the number in the answer's `text`; the kernel refuses an answer without one, or out of
  its bounds or off its step, saying the bounds and the unit, before the part that asked hears of it. Options are kept
  as JSON with the question, so nothing changes in the state database.
- Every client draws such an option's answer from the declaration alone: a number field with its unit and bounds.

## Alternatives considered

- **A form of the console's for the limit**: the phone and VS Code could not answer it, against the owner's instruction.
- **A text question**: the words would be checked only by the part that asked, after the answer was recorded.
- **A new question type, `number`**: a question with one number and nothing else; the limit question also offers
  *double it* and *keep paused*.

## Consequences

- The limit question's *raise it to …* (design 0016 §11) asks for a number in US dollars, above what was spent.
- Any later question that needs an amount, a count or a size declares it the same way.
