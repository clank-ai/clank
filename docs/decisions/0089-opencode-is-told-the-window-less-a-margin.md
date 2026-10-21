# 0089. OpenCode is told the engine's window less a margin for one step's tool results

- Status: Accepted, as Claude's call on the owner's report of a failed session; the owner may change the margin
- Date: 2026-10-20
- Decided by: Claude, from [the measurement of 2026-10-20](../measurements/2026-10-20-opencode-and-a-full-context.md)

## Context
Clank told OpenCode the engine's window and output limit (design 0004 §4, design 0012 §4.1), so that OpenCode compacts
a session before the engine refuses it. OpenCode compacts after a step whose total reaches the window less the output
limit; the step's tool results then go with the next request unchecked. KVMem refuses a request whose prompt and
`max_tokens` pass its window, so a step that ends just under the line, with results longer than the room left, makes
the next request fail: on 2026-10-20 a session stopped so at step 143, 35 tokens under the line of 245,760, after a
result of 1,206 tokens. OpenCode cuts each tool's output at 51,200 bytes or 2,000 lines: about 13,000 tokens of code,
prose or JSON, up to 49,000 of digits; a step may make several calls.

## Decision
- Clank tells OpenCode a window smaller than the engine's by a **margin**, kept free for one step's tool results:
  `context_margin` in `config/opencode.json`, **16,384** by default, applied when OpenCode next starts in a workspace
  (its configuration is written then). OpenCode then compacts once a step's total reaches 262,144 − 16,384 − 16,384 =
  229,376 tokens for `daily 262K`.
- The margin kept is at most a quarter of the window (`kept_margin`), so a small window still leaves a step room; 0
  tells OpenCode the whole window.
- Only what OpenCode is told shrinks. The Monitor shows the engine's own window, and its compaction line counts the
  margin, as OpenCode does; the folder page says what OpenCode is told and the margin kept.
- 16,384 is one cut output of code, prose or JSON (about 13,000 tokens), with room to spare, and the size of the
  answer's room. What it does not hold, a cut output of digits or a long listing, or several large outputs in one step,
  is left to the gateway, which answers the engine's refusal as an overflow OpenCode compacts on (the record of that
  choice follows this one).

## Alternatives considered
- **A margin of 51,200**, a token a byte of one cut output: it holds any single output, digits included, but takes 21%
  of the room before compacting for `daily 262K`, and still not several outputs in one step.
- **32,768**: it holds every kind measured but digits, at 13% of the room; the outputs it holds beyond 16,384 (long
  logs and listings cut at 51,200 bytes) are rarer than the compactions it would add, and the gateway's answer covers
  them.
- **OpenCode's own `compaction.reserved`**: OpenCode 1.19 reads it only when a model's `limit.input` is set, and then
  keeps at most 20,000 for the answer's room whatever `max_tokens` it sends; telling it the window less the margin gives
  the same line with one setting, and nothing else in OpenCode reads `limit.input`.
- **The gateway lowering `max_tokens` until the prompt fits**: KVMem cannot count a prompt's tokens, so the gateway
  could only guess, and an answer cut short is worse than a compaction.
- **The engine's window as before, the gateway's answer alone**: OpenCode compacts on it, but as an overflow, the step
  unfinished: it tells the model of attachments too large, or sends the owner's last message again.

## Consequences
- The failure of 2026-10-20 cannot recur from one step's results of up to 16,384 tokens: after any step that does not
  compact, its results and the answer's room still fit the window.
- A session compacts somewhat sooner (229,376 instead of 245,760 tokens for `daily 262K`), so a little more often.
- A changed margin applies to OpenCode started afterward; one running keeps the window it was told until it starts
  again, while the Monitor's line follows the setting at once.
- The margin is chosen for OpenCode's cut of 51,200 bytes; another program, or another version of OpenCode with another
  cut, is checked again.
