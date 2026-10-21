# 0040. The gateway stops an answer that repeats itself

- Status: Proposed (built at the owner's instruction, 2026-10-18: "I also want you to go ahead and implement the loop
  guard in the gateway")
- Date: 2026-10-18
- Decided by: Claude, from [the measurement of 2026-10-18](../measurements/2026-10-18-repetition-in-answers.md) and a
  review of the change, on the owner's instruction

## Context
On 2026-10-18 the agent's model began a `bash` call and, about 200 characters in, repeated closing tags until the
answer's limit: 16,384 tokens and 3.7 minutes of the GPU, then about 23,000 tokens of the same tags kept in the
session (the cut call and OpenCode's error repeating it), sent again with every later step. It had happened before
that night, and once in a thinking. Nothing between the model and OpenCode noticed: the engine's sampling had no
penalty against repeating, and OpenCode only stops a call made three times over, not an answer that repeats inside
itself.

## Decision
The gateway, which passes every streamed answer on, reads each one as it streams, each part apart: its thinking, its
text, and each tool call's arguments (a new call starts afresh). Every 128 characters of a part, it compresses (zlib)
the part's newest stretches: 2,000 and 8,000 characters of the thinking and the text, 2,000 of a tool call's
arguments. When one comes to under 6% of its size, the answer repeats itself. A tool call is not read over the long
stretch because a file written from a template (records that differ only by an id, rows of a table, a compose file of
near-identical services) compresses that far over 8,000 characters, and a stop would come again each time it is asked
again; over 2,000 it stays above 7%.

The gateway then closes its connection to the engine, which stops writing, and ends the stream with an error event
that says what repeated (`model_looped`) and how to let such an answer through, in words without numbers: OpenCode
1.19 retries an error whose words hold 429, 500, 502, 503, 504 or 524 (or words such as "unavailable"), and a stretch
of 2,500 characters would otherwise ask it to, up to five times, though no one chose that. The record keeps the whole
of it (`looped`: what, over which stretch, how far it compressed; and the error), so the console's pages show it. It
is on by default; its settings are in `config/gateway.json` (`loop_guard`, `loop_windows`, `loop_tool_windows`,
`loop_ratio`) and apply when the gateway restarts (`clank gateway restart`), as the error says.

## Alternatives considered
- **A penalty against repeating, in the sampling** (presence or repetition penalty). It changes every answer, not only
  the broken ones, and a penalty hurts code, which repeats names by nature; it is for the owner to choose per model,
  in the model settings planned on the console, not a guard.
- **A lower limit on an answer's length.** It caps the waste but stops long, ordinary answers too, and a loop still
  runs to the limit.
- **An exact repeat (the newest text equal to itself shifted by a period).** The real loops vary (one tag twice, then
  once) and break an exact period; compression does not mind.
- **Counting distinct lines.** A tool call's arguments arrive as JSON, with no new lines in them.
- **The long stretch for tool calls too.** It stopped ordinary templated files (above).
- **Reading each new stretch against the part's earlier text** (zlib with the earlier text as its dictionary). It
  would find repeats of any length up to the dictionary's and reworded ones, but it costs more and would stop a draft
  written out a second time, which models do; possible later, measured first.
- **Holding a tool call back until it ends, and asking again in its place.** The owner would no longer see a file
  being written as it is written, and the thinking already sent cannot be taken back; possible later, with care.

## Consequences
- The three loops measured are stopped within 2,176 characters (the two `bash` calls) and 2,432 (the thinking),
  some 15 seconds, instead of the answer's whole limit; and none of it stays in the session: OpenCode 1.19 leaves an
  answer that ended in an error out of every later request (its `message-v2.ts`).
- Not every loop is found: prose said again every 600 to 800 characters is (by the long stretch), a longer repeat, or
  one that rewords itself or counts up ("check n = 41 again"), runs on to the answer's limits as before (4,096 tokens
  of thinking, 16,384 of answer).
- The agent sees an error, not an answer: OpenCode stops its turn there and the session waits; the owner asks again.
  Telling the model what happened and going on by itself is the Monitor's to decide (a rule the owner sets), not the
  guard's.
- An ordinary answer that compresses as far as a loop (a list of 900 zeros, `[0.0, 0.0, …]`, some 4,500 characters; a
  literal identity matrix) is stopped too; the margin measured is over three times for real answers, 1.6 times for
  Clank's most repetitive file and 1.25 times for templated files in tool calls. The error says how to turn it off.
- Only streamed answers are read; a whole answer (not streamed) is not, since nothing of it arrives before it ends.
