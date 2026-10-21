# 0106. The service hands a cloud provider's key to the gateway, behind its local token, while a cloud model is loaded

- Status: Proposed (Claude's call; the owner may choose decision 0073's (a) or (b) instead)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §5; it answers decision
  [0073](0073-how-the-gateway-gets-an-endpoints-key.md) for cloud keys with a third option, the way decision
  [0084](0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md) already built for pauses

## Context
- The gateway attaches the provider's key to each cloud request (design 0001 §6.1, step 6). The key is a secret of the
  kernel, `CLANK_HOME/secrets/endpoint/openrouter/key` (design 0002 §2.8): "a component gets one through the kernel,
  which records which component used which secret and why".
- Decision 0073 (proposed) offers two ways: (a) a process token for the gateway and routes only processes may call,
  which needs the kernel's `process` access level (design 0002 §2.7, not built: the API has one level, `control`); (b)
  the gateway reads the key's file itself and reports each use, a second reader of `secrets/`, a use unrecorded while
  the service is down.
- The gateway already holds the service's local token, read from the home at its start
  (`clank/components/gateway/server.py:957`), and serves routes only the service calls with it: the pauses' (decision
  0084). Containers reach the gateway through the edge and never hold the local token.
- A cloud key is money: whoever holds it can spend the owner's credits.

## Decision
- The gateway serves `PUT /keys/{endpoint}`, `DELETE /keys/{endpoint}` and `GET /keys`, each taking the service's
  local token; `GET /keys` names each key it holds by its endpoint, its last four, its launch and when it was set,
  never its value. No route of the gateway, or of the service, answers with a key.
- The gateway component's service, when the main slot's route names an endpoint that needs a key, reads it through
  the kernel (`Secrets.value`, `user="gateway"`, `why` naming the launch: one `secret.used` event) and puts it to the
  gateway; it deletes it there when no slot runs that endpoint. It does so on each `runtime.slot` event and each
  `secret.set` of the endpoint's scope, and checks `GET /keys` every five seconds, so a gateway started again gets it
  within seconds.
- The gateway keeps the key in memory only, while that launch is the route; a request that needs it before it arrives
  waits as for a starting slot.
- The moment of use is the launch (as decision 0073 proposed for both its options, refining decision 0021).

## Alternatives considered
- **0073's (a), a process token**: builds design 0002 §2.7's `process` level, which other data-plane processes will
  need; but it changes the kernel (a second access level, its scheme, the registered tokens, a test that every route
  declares its level) before the first cloud request, for the same result here: the key read only by the kernel,
  recorded at each read, never answered to a client.
- **0073's (b), the gateway reads the file**: one step, but a second reader of `secrets/`, and a use recorded only when
  its report reaches the service.
- **The key in the routes the gateway follows each second**: every local client could read it there.
- **The key in the gateway's environment at its start**: a key set later would need a restart of the gateway, which
  cuts requests in flight; every key would sit there whether used or not.

## Consequences
- The kernel stays the one reader of `secrets/`, each read is recorded when it happens (the service reads it), and no
  client can read a key through any API.
- A gateway started again while the service is down has no key until the service answers; cloud requests wait for the
  service then anyway (design 0016 §9).
- Any local client, which holds the local token, could put a key to the gateway; it can already set the key through
  the service, so nothing it could not do before.
- Design 0015's endpoints can use the same routes; when the kernel's `process` level is built, these routes can move to
  it without changing what the gateway holds.
- Once accepted, decision 0073's status names this decision for cloud keys.
