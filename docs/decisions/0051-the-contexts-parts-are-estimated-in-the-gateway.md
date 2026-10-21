# 0051. The context's parts are estimated in the gateway, labeled as estimates; exact sizes wait for a KVMem patch

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §4.4's Choice as recommended

## Context
The owner wants to see "the context window, how much context is being stored, what the breakdown of different tokens
in the context window is, how much we have left" ([design 0012](../design/0012-the-monitor.md) §4.2, §4.4). Nothing
measures the parts today: the gateway's records keep only how many messages and tools a request had, and KVMem
reports only totals and has no route that counts tokens (it serves `/health`, `/v1/models` and
`/v1/chat/completions`). Once a conversation is longer than the 36,864 tokens KVMem attends exactly on the GPU, which
blocks it picks to keep there only the engine knows.

## Decision
- **Estimated in the gateway**, from the request body it already parses: each part's characters, shared out so that
  the parts add up to the engine's exact `prompt_tokens`. One pass per request, no engine work, no new dependency.
- **The parts**, as boards A and C draw them: the system prompt, the tool definitions, your messages, the model's
  text, thinking sent back (by the template's rule: only after the last real user message), tool calls, tool results,
  and loop text ([0052](0052-loop-text-is-a-part-of-its-own.md)).
- **Labeled**: the panel says "estimate" next to the exact total, and the Context view says how it is made. The
  estimate is calibrated on synthetic requests that differ by one part.
- **On the GPU, totals only**: the stored size, how much of it is on the GPU and how much in system memory, and whose
  conversation it is.
- **Exact sizes and the GPU's picks wait** for one KVMem patch (tens of lines: the token ranges, labeled, with the
  parts' exact sizes, in the usage chunk and in a comment at the stream's start), made once the estimate's error is
  measured, if the owner chooses, under its own decision record.

## Alternatives considered
- **The patch first**: a local change to KVMem to keep up, made before it is known whether the template's markers are
  single tokens, or how far the estimate errs.
- **KVMem's trace mode (`KVMEM_TRACE`) and reading its log**: rejected; it is a debug mode of unmeasured cost that
  prints nothing on some paths, and a log is not an interface.
- **Board C's "ask the engine to count each part"**: KVMem has no counting route; exact counts would come with the
  patch, with every request.

## Consequences
- The estimate has known errors (the template's own text is unseen, tool calls are rendered as XML, code and prose
  differ in tokens per character), which the calibration is for.
- Its CPU cost on a 262,144-token request, and the template inside the model file, are measured before step 12;
  whether the pool's cap shrinks KVMem's 36,864 for Clank's preset, before step 3.
- The estimate's error against the exact sizes decides whether the patch is worth keeping (step 13).
