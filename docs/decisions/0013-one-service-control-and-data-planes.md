# 0013. One Clank service is the control plane; separate processes carry the traffic

- Status: Accepted. Refines [0006](0006-runtime-service-with-adapters.md)
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §1 ("Section 1 looks right")

## Context
Decision 0006 made one runtime service the single source of truth for models. The owner then asked for workspaces in
containers, very specific network access, agents with modes, MCP servers, skills, approvals and questions answered
from anywhere, and the phone (design 0002). Each of these needs settings, state, decisions, records, and a place in
every client. Several services would each need their own API, records, access rules and clients. One service that
also carried the traffic would cut every agent's work whenever it restarted.

## Decision
- One **Clank service** is the control plane. It holds the settings and the state, makes every decision (what runs,
  what is allowed, what to ask the user), records everything, and serves the one Clank API (HTTP and one event
  stream). The runtime of decision 0006 is one of its components; the others are the gateway, workspaces, network,
  agents, tools, skills and reach (design 0002 §1).
- Every component is built from one shared **kernel** (design 0002 §2) and is used by others only through its public
  interface.
- The **data plane** carries the traffic, in separate processes that the service starts, watches, stops, and adopts
  again after its own restart: the engines, the gateway (model requests), the tool hub (tool calls), the sandboxes
  (the agent programs), and each sandbox's edge (its only door). A data-plane process asks the service when something
  needs a decision; while the service is down, it keeps what was already allowed and refuses anything new.
- Clients (the console, the VS Code extension, the phone page, the `clank` command, other programs) hold no state.

## Alternatives considered
- **A service per part** (runtime, agents, tools, phone). Each part could be deployed alone, but there would be several
  APIs, record stores, access rules and event streams to keep consistent, and every client would talk to all of them.
- **One process for everything, traffic included.** The simplest, but a restart (an upgrade, a crash) would cut every
  model request, tool call and agent in flight.

## Consequences
- The kernel is designed before any component is built, and changed only by a decision.
- A component's control part runs in the service; its traffic, if it has any, runs in its own process.
- Every data-plane process authenticates to the service and reports its events; the rule that it fails closed is
  tested for each.
- A feature is added as a component or an adapter, without changing the kernel or the other components.
