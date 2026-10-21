# OpenCode and a full context (2026-10-20)

**When:** 2026-10-20. OpenCode 1.19.0 was read and run in Clank's sandbox image (`opencode-ai@1.19.0`, a
compiled Bun program whose bundled code is kept as text inside it), in containers started for the purpose with no
network and removed afterward. Tokens were counted by Qwen3.8-27B's own tokenizer (llama.cpp's `llama-tokenize`, which
loads the model file's vocabulary only, on the CPU) on synthetic text. Nothing of the owner's sessions, records or logs
was read: the figures of the failed session are counts from the report of the failure.

**Question:** why did a long OpenCode session fail at the context's limit, how much of the window must be kept free,
and what does OpenCode do when the engine says the context is full?

## What failed

KVMem (`daily 262K`, a window of 262,144) refuses a request whose prompt and `max_tokens` together pass its window: HTTP
400, `{"error":"prompt + max_tokens exceeds n_ctx"}` (its server, `tools/llama-kvmem-server.cpp`; it has no other
words for a full context). Clank told OpenCode the window itself and the output limit, 16,384, so OpenCode compacted a
session once a step's total reached 245,760. Step 143 ended at 245,725, 35 tokens under the line; its tool result,
1,206 tokens, went with the next request: a prompt of 246,931, with 16,384 for the answer 263,315 tokens, over the
window. KVMem refused it, and OpenCode showed the session failed and stopped. Another session crossed the line inside a
step, and OpenCode compacted it after that step as it should.

## When OpenCode compacts

Read in its `session/overflow.ts` and `provider/transform.ts`: after a step whose total (input, output, cache read and
cache write) reaches the window it is told less `min(limit.output, 32,000)`, the `max_tokens` it sends. (With a model's
`limit.input` set, the line is that less `compaction.reserved`, by default `min(20,000, max_tokens)`; Clank sets
neither.) Nothing is checked between a step's end and the next request, which carries the step's tool results.

## One tool's output

OpenCode cuts each tool's output at 2,000 lines or 51,200 bytes, whichever comes first, and saves the rest to a file
(its `Truncate`: `MAX_LINES`, `MAX_BYTES`). One output cut there, in tokens, by kind (synthetic text):

| Kind | Text | Bytes | Lines | Tokens |
| --- | --- | ---: | ---: | ---: |
| Code | Clank's gateway modules | 51,200 | 1,020 | 13,349 |
| Prose | Clank's first decision records | 51,200 | 819 | 13,048 |
| JSON | short records, cut at 2,000 lines | 24,175 | 2,000 | 13,827 |
| Test log | one `path::test PASSED [ n%]` line a test | 51,200 | 831 | 19,531 |
| Listing | `ls -l` lines | 51,200 | 853 | 30,618 |
| Numbers | eight numbers a line, six decimals | 51,200 | 561 | 49,192 |

The tokenizer writes each digit as a token of its own, so digits cost about a token a byte. A step may make several
calls, each with its own output.

## How OpenCode reads an error

Read in its `provider/error.ts`, `session/processor.ts`, `session/prompt.ts` and `session/compaction.ts`:

- **An HTTP error** is a context overflow when its message matches one of OpenCode's patterns (among them `exceeds the
  available context size`, upstream llama.cpp's, `context[_ ]length[_ ]exceeded`, `maximum context length is \d+
  tokens`, `prompt is too long`, `too many tokens`) and none of `rate limit`, `too many requests`, or a start of
  `service unavailable:` or `throttling error:`; or when its status is 413; or when its body's `error.code` is
  `context_length_exceeded`. The message is OpenAI's `error.message` when the body has OpenAI's shape; otherwise the
  status's words, followed by the body's `error` when that is a string.
- **An error event inside a stream** (its 200 already sent) is an overflow only in the shape of OpenAI's Responses
  API: `{"type": "error", "error": {"code": "context_length_exceeded"}}`, also when that object is the error's message,
  written as JSON. An error event whose `type` is `error` with another code is retried as a server's error.
- **On an overflow** OpenCode does not retry. Unless `compaction.auto` is false (Clank leaves it on), it marks the step
  for compaction, publishes the error (the terminal interface shows it), compacts and goes on. The compaction is an
  overflow's, the step having no end: when the session's last message of the user's is not its first, the history
  before that message is summarized and the message sent again after the summary; when it is the first, the whole
  session is summarized and OpenCode adds a message of its own, written for an attachment too large: "The previous
  request exceeded the provider's size limit due to large media attachments. The conversation was compacted and media
  files were removed from context. [...] Continue if you have next steps, or stop and ask for clarification if you are
  unsure how to proceed." A compaction whose own request overflows ends the session ("Conversation history too large to
  compact").

## OpenCode run against each answer

`opencode run` in a container of the sandbox image, against a fake server in the same container that refused the
agent's first request in one way and answered every other:

| The first request refused with | OpenCode |
| --- | --- |
| KVMem's 400, `{"error":"prompt + max_tokens exceeds n_ctx"}` | "Error: Bad Request: prompt + max_tokens exceeds n_ctx"; no retry, no compaction: the session stops |
| 400, OpenAI's shape, the message saying `the request exceeds the available context size`, code `context_length_exceeded` | shows the error, compacts (a summary request), adds its message about attachments, and goes on: the next request is answered |
| the same, the code only | the same |
| the same, the words only | the same |
| an error event in a 200 stream, its message the Responses shape as JSON | shows "Input exceeds context window of this model", compacts and goes on |
| an error event in a 200 stream, OpenAI's shape with the code | the error, as JSON; no compaction: the session stops |

`opencode run` exits with 1 whenever an error was published, even when the session went on to its end.

## What follows

- [Decision 0089](../decisions/0089-opencode-is-told-the-window-less-a-margin.md): OpenCode is told the window less a
  margin of 16,384, which holds one cut output of code, prose or JSON.
- [Decision 0090](../decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md): what the
  margin does not hold (several large outputs in one step, a cut output of digits) is answered by the gateway as an
  overflow OpenCode compacts on, its words and code those of the run above that went on.
