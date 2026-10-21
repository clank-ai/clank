# 0016. The Clank API is built with FastAPI and served by Uvicorn

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
The Clank service serves HTTP and JSON under `/api/v1/` and one event stream (design 0002 §2.14) to local clients,
paired devices and data-plane processes. Its records are Pydantic classes (decision
[0015](0015-kinds-defined-once-in-pydantic.md)). The API must describe itself, so that its documentation and the
clients' types are generated, not written.

## Decision
The API is a FastAPI application, served by Uvicorn.

## Alternatives considered
- **Starlette alone** (what FastAPI is built on). Fewer layers, but request validation and the API's description would
  be ours to write.
- **aiohttp.** Mature, but with no Pydantic integration and no generated description.
- **Flask or Django.** Synchronous by default, or far larger than one service needs.

## Consequences
- FastAPI and Uvicorn are runtime dependencies (with what they bring: Starlette, Pydantic, AnyIO).
- `docs/API.md` is generated from the API's own description.
- Tests call the API in-process through FastAPI's test client.
- The service is asynchronous, so nothing may block its event loop: database writes and other slow calls run off it.
- Other services on this machine are built the same way, so its patterns (authentication, Server-Sent Events) are
  known to work here.
