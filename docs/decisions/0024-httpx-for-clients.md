# 0024. Clank's Python clients speak HTTP with httpx

- Status: Superseded by [0026](0026-httpx2-replaces-httpx.md)
- Date: 2026-10-11
- Decided by: proposed by Claude in the M0.3 plan, under the owner's instruction to "plan and build M0.2 and everything
  else we have scheduled" (2026-10-11); the owner can revisit it

## Context
The `clank` command and the console are clients of the Clank API (design 0002 §2.15): they make ordinary requests and
follow the one stream of Server-Sent Events (decision [0017](0017-one-server-sent-events-stream.md)). Their tests must
reach the API without a network, and later Clank's own outside traffic goes through one HTTP client that refuses
undeclared hosts (design 0002 §2.13). FastAPI's test client is itself built on httpx.

## Decision
httpx is the HTTP client of Clank's Python code: the clients, the tests, and later Clank's own outside traffic.

## Alternatives considered
- **urllib**, in Python's standard library. No dependency, but no streaming convenience, no separate timeouts for
  connecting and reading, and no way to put a fake server behind it in tests.
- **requests.** Well known, but synchronous only, and FastAPI's test client needs httpx anyway.
- **aiohttp.** Asynchronous only, with its own server stack beside FastAPI's.

## Consequences
- One library for blocking and asynchronous clients, with streaming for the event stream.
- Tests run clients against the API in-process (FastAPI's test client) or against fakes (httpx's mock transport).
