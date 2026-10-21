# 0084. The gateway's holds are set by the service, behind its local token

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, without the owner (building design 0012's step 11, [plan s21](../plans/s21-monitor-pause.md));
  it says how [0055](0055-pause-is-the-gateway-holding-the-next-request.md)'s "marks the session paused in the gateway"
  is done

## Context
Decision 0055 makes a pause the gateway's: it holds a paused session's next model requests, and its subagents', until
the owner resumes. The gateway is a process of its own, which the service starts and which outlives it; the service
tells it where each role's requests go, and the gateway asks for those routes every second. Every workspace's container
reaches the gateway through the edge, which forwards its port byte for byte (design 0004 §3), so whatever route the
gateway serves, the agent in a container can call; from the gateway's side, the edge's connections may come from the
same address as the service's. The gateway already refuses the agent everything under `/flows/` but a VERIFY's verdict,
and under `/notion/` all but reading and proposing, since running, pausing and approving are the owner's.

## Decision
- The pauses live in the gateway (`holds.py`), as 0055 says, and the gateway serves the routes that change them:
  `GET /holds`, `PUT /holds/{session}` (pause, saying by whom), `DELETE /holds/{session}` (resume) and
  `POST /holds/{session}/release` (a note's: the session's own requests held before the note was sent end as empty
  steps, the pause stays).
- Each of these takes **the service's local token** (`state/local.token`, design 0002 §2.7), which the gateway reads from
  the home when it starts: a caller without it is refused (401) in words that say pausing is the owner's; a gateway
  given no token refuses them all (503). The agent never has the token (it is in the home, never in a container), so it
  can neither resume its own pause nor pause another session.
- The service sets them (`Gateway.pause`, `resume`, `release`, `holds`) for the Guide's `p` and for a Watch for rule,
  each an `agents.acted` event with who did it. The pauses are kept in the home's `state/holds.json`, so they outlive a
  restart of the gateway; a restart of the service changes nothing, since the gateway outlives it.

## Alternatives considered
- **The gateway follows the pauses with its routes every second**: no new route at all, so nothing for the agent to
  call; but a pause or a resume reaches the gateway up to a second late, a request that comes in that second is not
  held, a note's release needs a counter of its own in the routes, and a service that started again (its pauses in
  memory) would resume every pause.
- **Refusing by the caller's address**: the edge forwards connections from the containers, and on Docker Desktop they
  may reach the gateway from the loopback address as the service's do; an address proves nothing here.
- **Pauses in the service alone, the gateway asking whether each request is held**: a call from the gateway to the
  service on every model request, and a held request that cannot be told to go on at once.

## Consequences
- Pausing and resuming take effect at once, and a request that comes just after the pause is held.
- The gateway reads the home's token at its start; a token made again (the file deleted) needs a restart of the gateway
  (`clank gateway restart`) before the service can pause through it again, and until then the Guide says the gateway
  refused.
- The token never leaves this machine's home: the routes are on 127.0.0.1, and the service is their only caller.
- A gateway from before these routes, still running when the service is updated (the service adopts the gateway that
  runs), answers them with FastAPI's own 404: the service takes that for a gateway to restart, never for a pause set,
  and the Guide says so (`clank gateway restart`); only the gateway's own `not_paused` answers a resume with "not
  paused".
