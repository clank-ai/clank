# 0026. httpx2 replaces httpx as the HTTP client of Clank's Python code

- Status: Accepted. Supersedes [0024](0024-httpx-for-clients.md)
- Date: 2026-10-11
- Decided by: proposed by Claude while building M0.3, under the owner's instruction to build the rest of M0 (2026-10-11);
  the owner can revisit it

## Context
Decision 0024 chose httpx for the Python clients, the tests and later Clank's own outside traffic. Building the API's
tests showed that the test client of Starlette 1.7 (which FastAPI's is) now warns that using httpx with it is
deprecated and asks for httpx2: the next generation of the same client, by its original author, maintained under the
Pydantic organization (github.com/pydantic/httpx2), version 2.13 at the time of writing. A deprecated client would be
debt from the first commit.

## Decision
httpx2 is the HTTP client of Clank's Python code, for everything decision 0024 gave to httpx.

## Alternatives considered
- **Keep httpx 0.28.** It works, but Starlette's test client warns on every use, and tests treat warnings as errors.
- **Quiet the warning.** Hides the problem instead of following the libraries Clank is built on.

## Consequences
- The import is `httpx2`; httpx leaves the dependencies.
- What decision 0024 says about streaming, separate timeouts and fakes in tests holds for httpx2.
