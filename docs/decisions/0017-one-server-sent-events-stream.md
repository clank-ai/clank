# 0017. Clients follow one stream of Server-Sent Events

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
Every client (the console, the VS Code extension, the phone page, `clank events --follow`) shows what happens as it
happens, and design 0001 §5.7 rules out polling. Clients act through ordinary requests; from the service they only need
to listen. A client that loses its connection (a phone on a train, a laptop that slept) must catch up without missing
anything, or know that it missed something.

## Decision
One stream, `GET /api/v1/events`, in the Server-Sent Events format, filtered by type and subject. Every kept event has
an id that only grows; a client that reconnects gives the last id it saw, and the stream resumes after it. When that
event is older than anything kept, the stream says so, and the client reloads the records it shows before following
again (design 0002 §2.3).

## Alternatives considered
- **WebSockets.** Two-way, which no client needs; more code in every client, and resuming after a break is ours to
  design.
- **Polling.** Load on the service and on the computer, and changes seen late.
- **One stream per component.** More connections, and events of different components lose their order.

## Consequences
- Python (httpx) and VS Code (Node's fetch) read the stream without another library.
- Browsers' `EventSource` cannot send a token header, so the phone page reads the stream with `fetch`, or with a
  session cookie; the phone's design (M9) chooses.
- Live-only events (the text a model is writing, progress ticks) have no id to resume from: the record they belong to
  keeps the result.
