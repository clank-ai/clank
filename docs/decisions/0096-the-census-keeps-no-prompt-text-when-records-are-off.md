# 0096. The census keeps no prompt text when the gateway's records are off: counts, kinds, tool names, sizes and places only

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, building design 0012's step 12 ([plan s22](../plans/s22-monitor-the-parts-and-the-context-view.md)),
  from its independent review's sixth finding; it says what
  [0051](0051-the-contexts-parts-are-estimated-in-the-gateway.md)'s estimate in the gateway may carry

## Context
Step 12 gave the gateway a census of each request: its characters by part (system prompt, tool definitions, the
owner's messages, the model's answers and calls, tool results) and item by item, so the Monitor's Context view can show
what fills the window and its biggest items (decision 0051). As first built, each item kept up to 80 characters of
what it was: the start of the owner's message, of the model's thinking or text, or a call's first argument. The
gateway served that in `/activity`'s ended requests, to the service and the console, whether or not its records
(`records`, design 0012 §3) were on. With records off, nothing of a prompt's text had left the gateway before.

The owner's work in Clank is their research; what they type and what the model reads of it stays where they chose to
keep it, and the gateway's records setting is that choice.

## Decision
With the gateway's records off, a census item carries its kind, its tool's name, its sizes, its step and its place,
and no text of the prompt: not the owner's message, the model's words or thinking, nor a call's arguments. With them
on, an item may carry the short text the records already keep. Tests hold both, on the census itself and through
`/activity`.

## Alternatives considered
- **Always keep the 80 characters**: Biggest in the context would name each item by its words, which is easier to
  read, but text would leave the gateway against the owner's own setting.
- **Never keep any text**: the same privacy with records on too, where the owner has chosen to keep text; Biggest
  would lose what it can show then.

## Consequences
With records off, Biggest in the context and the Context view name an item by its kind, its tool and its step (for
example "read · step 97"), not by its words. Turning records on brings the words back for requests made after.
