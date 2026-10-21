# 0102. The first cloud provider is OpenRouter, alone for now

- Status: Accepted (the owner's decision)
- Date: 2026-10-20
- Decided by: the owner's first answer of 2026-10-20 ("Providers: OpenRouter only, for now (one key, every major model
  behind it). Other providers later."), written into [design 0016](../design/0016-cloud-models.md) §2

## Context
The owner asked that anyone who downloads Clank can use it with a cloud model from an API key, configured entirely
from the console, with no complicated model setup. Principle 5 already promised "an API key for a hosted model", and
design 0001 §7.6 templates for "known hosted providers"; design 0015 (endpoints, proposed) foresaw "later a hosted API
with a key". Each provider has its own key, base URL, model list, prices and refusals, and each one Clank supports is
one more adapter to write, record and test.

## Decision
- The first cloud provider is **OpenRouter**: one account and one key reach the major models (OpenAI's, Anthropic's,
  Google's, open-weight ones), each at its own price, through one OpenAI-compatible API.
- It is the first adapter of a new kind, `endpoint` (design 0002 §2.10, design 0015 §3); nothing outside its adapter,
  its record and its words names OpenRouter.
- Other providers come later, each with its own design note and decision.

## Alternatives considered
- **Each major provider's own API** (OpenAI, Anthropic, Google): one key per provider for the owner, and three or more
  adapters and dialects (Anthropic's Messages, Google's own) before the first works.
- **A generic OpenAI-compatible endpoint with a key** (design 0015's `openai-compatible`): it serves many providers, but
  a new user must find a base URL and a model id, and Clank cannot list prices, check a key's credit or explain a
  refusal in the provider's own terms: not "without any kind of complicated model setup".

## Consequences
- Clank's first cloud models reach the user through one more company, OpenRouter, between them and the model's
  provider; Add a model's agreement screen says so (design 0016 §9, §14).
- The `endpoint` adapter kind is built now, with OpenRouter as its first adapter; design 0015's `openai-compatible`
  joins it later without changing the gateway or the console.
