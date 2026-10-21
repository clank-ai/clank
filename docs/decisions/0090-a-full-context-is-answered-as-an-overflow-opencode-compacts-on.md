# 0090. The gateway answers an engine's refusal of a full context as an overflow OpenCode compacts on

- Status: Accepted, as Claude's call on the owner's report of a failed session
- Date: 2026-10-20
- Decided by: Claude, from [the measurement of 2026-10-20](../measurements/2026-10-20-opencode-and-a-full-context.md);
  it answers design 0012 §10's question whether KVMem's refusal of a full context makes OpenCode compact or fail

## Context
KVMem refuses a request whose prompt and `max_tokens` pass its window with HTTP 400 and
`{"error":"prompt + max_tokens exceeds n_ctx"}`. OpenCode 1.19.0 reads that as an ordinary error, "Bad Request: prompt
+ max_tokens exceeds n_ctx", does not retry a 400, and stops the session: read in its code, and seen when it was run
against those words. It compacts and goes on only after an error it reads as a context overflow: in an HTTP error,
words such as upstream llama.cpp's "exceeds the available context size", or the code `context_length_exceeded`; inside
a stream whose 200 has gone out, only OpenAI's Responses shape, `{"type": "error", "error": {"code":
"context_length_exceeded"}}`, also written as JSON in the error's message. The margin of
[decision 0089](0089-opencode-is-told-the-window-less-a-margin.md) keeps an ordinary step's results from causing the
refusal, but not a step whose results are larger than the margin.

## Decision
- Each engine adapter says how its engine refuses a request its context cannot hold (`FULL`, and its context facts'
  `full`): KVMem's 400 with the words above; upstream llama.cpp's 400 with an error of type
  `exceed_context_size_error`. The gateway asks through the runtime's `context_full`, as it asks `translate_request`.
- When the engine refuses so, the gateway answers **400 in OpenAI's shape**, its code and type
  `context_length_exceeded`, its message "the context was full: <the engine's words> (the request exceeds the available
  context size; OpenCode compacts the session on this error)". OpenCode reads both the code and the words as an
  overflow; either alone would do.
- A held request (design 0012 §9.4), whose 200 has gone out, is told in its stream: an error event whose message is the
  Responses shape written as JSON, the one form OpenCode reads there as an overflow.
- The request's record keeps the engine's words in `full`, with its status 400 and the words told; the session's
  requests that ended carry `full` too, and the Requests page marks the line `full`. Any other refusal is passed on as
  the engine gave it, its error now recorded for a streamed request as for one not streamed.

## Alternatives considered
- **Passing KVMem's words on**: OpenCode stops the session, as it did on 2026-10-20.
- **The words alone, or the code alone**: each works in OpenCode 1.19.0; both are sent, so an OpenCode that drops one
  of its patterns still compacts.
- **Status 413**: OpenCode reads it as an overflow too, but other clients read 413 as a request too large to send at
  all, not a conversation to compact.
- **Changing KVMem's words**: Clank does not patch an engine for its words; another engine with other words is met by
  its adapter.
- **A retryable answer (503)**: OpenCode would send the same request again, refused again, up to five times.

## Consequences
- A session whose step's results pass the margin is compacted and goes on, instead of stopping. OpenCode's compaction
  after an overflow is not the one after a finished step: when the session has one message of the owner's, OpenCode
  tells the model that attachments were too large (its own words, written for images); otherwise it sends the owner's
  last message again after the summary. The owner sees the error in OpenCode and the request marked `full`.
- `opencode run` exits with 1 after an overflow even when the session went on; Clank does not use it, and follows a
  session by its state.
- A gateway started before this change answers as before until it is restarted (`clank gateway restart`).
