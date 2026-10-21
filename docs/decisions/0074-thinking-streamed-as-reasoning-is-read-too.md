# 0074. Thinking streamed as `reasoning` is read like `reasoning_content`; the stream reaches the tool unchanged

- Status: Proposed
- Date: 2026-10-18
- Decided by: Claude, with [design 0015](../design/0015-endpoints.md) §8, from the research of 2026-10-18; the owner
  approves or changes it with the design

## Context

- The gateway reads a streamed answer's thinking for three things: the loop guard
  (`clank/components/gateway/server.py:438-439`), the live view (`:451-452`), and the rule that sends a request again
  when its engine broke off before any token (`:431`: a delta that carries thinking counts as a token). It reads only
  `reasoning_content`, the field llama.cpp, KVMem and SGLang stream.
- vLLM, which the owner's cluster most likely runs (T0 says, design 0015 §15), now streams thinking as `reasoning`
  (its `docs/features/reasoning_outputs.md`, https://github.com/vllm-project/vllm), where it used to stream
  `reasoning_content`.
- Read as it is today, such a stream would show no thinking in the live view; a looping thinking would never be
  stopped; and a stream cut during its thinking would count as nothing answered and be sent again on the same stream,
  so the tool would see that thinking twice.
- OpenCode 1.19.0's provider package, `@ai-sdk/openai-compatible` 2.0.41, reads either field (the research of
  2026-10-18), and replays earlier thinking as `reasoning_content`
  (`clank/components/agents/adapters/opencode.py:133`), which vLLM accepts (the same research).

## Decision

- The gateway reads thinking from `reasoning` as from `reasoning_content`, for the loop guard, the live view and the
  rule that sends a request again. A delta that carries both is read once: `reasoning_content` when it has text, else
  `reasoning`.
- The stream reaches the tool unchanged: no field is renamed, added or removed.
- OpenCode's configuration stays as it is.
- An endpoint's check reports which field its server streams (decision 0076).

## Alternatives considered

- **Rename `reasoning` to `reasoning_content` in the stream.** The tool would get something other than what the server
  sent, and OpenCode reads both already.
- **Tell OpenCode to replay thinking as `reasoning` for an endpoint.** It changes what OpenCode sends back, for nothing:
  vLLM accepts `reasoning_content`.
- **Read the field by the provider: `reasoning` for endpoints, `reasoning_content` for engines.** A server's field is
  known only from its stream, and an engine may move to the new name too.

## Consequences

- Any server that streams either field gets the loop guard, the live view and the right rule for sending again.
- A server that streams its thinking inside the text (`<think>`, no reasoning parser) is read as text; the check says
  so, and that the server needs a reasoning parser for OpenCode to show its thinking apart.
- The fake engine and the fake server stream thinking in either field (design 0015 §14).
