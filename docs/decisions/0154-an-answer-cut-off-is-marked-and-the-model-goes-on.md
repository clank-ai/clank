# 0154. An answer cut off at the output limit is marked, and the model told to go on

- Status: Accepted (the owner's report of 2026-10-29: "the cloud model I am using has stopped twice without getting
  any large amount of work done, and there is nothing indicating why specifically the model stopped working … the
  reason the model keeps stopping is because it is hitting its thinking limit"); revises design 0012 §8
- Date: 2026-10-29

## Context

- A reasoning model's thinking counts against a request's output limit (`max_tokens`: a cloud preset's most output,
  16,384 tokens unless the owner set another). When the thinking reaches the limit, the provider ends the answer with
  the finish reason `length`, and OpenCode ends the run there: the session goes idle with the work not done.
- OpenCode keeps that reason on the step (its `finish`, which the bridge passes on to Clank's flow of the session), but
  nothing in Clank read it. Watch for's "Thinking or answer near its budget" marked the answer as it neared the limit,
  not that the run had stopped because of it.

## Decision

- **A rule of its own**, "An answer cut off at the output limit" (`answer_cut`, after the loop guard's): it marks each
  step whose finish is `length`, naming the limit (the slot's) and how much of the answer was thinking (OpenCode's
  count). The finish is OpenCode's own fact, so the rule marks it even when the limit is not known.
- **By default it marks and tells the model to go on**, as the loop guard's rule does (decision 0053): "Go on from
  where you were: think more briefly, and take the work in smaller steps (a long file in parts)." The cap of two notes
  in a row holds: a model cut off again and again is paused, and the phone told.
- **The way out is said** in the rule's words: `e` on the Presets page raises a cloud model's most output.

## Alternatives considered

- **Mark only, or mark and tell the phone**: the owner's runs stopped while nobody watched; a note costs one short
  request and keeps the run going, as it does after the loop guard.
- **Raise the output limit by itself**: the limit is the owner's setting, and a larger one can cost more; Clank says
  how to raise it instead.

## Consequences

- A run left alone goes on after a cut answer, at most twice in a row before it waits for the owner.
- Like every Watch for rule, it is the owner's to change or turn off in `config/monitor.json`.
