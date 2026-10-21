# 0073. How the gateway gets an endpoint's key: a process token, or the gateway reading the key's file

- Status: Proposed: the owner chooses; for cloud keys, decision
  [0106](0106-the-service-hands-the-cloud-key-to-the-gateway.md) proposes a third way (the service hands the key to the
  gateway behind its local token)
- Date: 2026-10-18
- Decided by: not yet: the owner chooses (a) or (b) below; Claude recommends (a). Written with
  [design 0015](../design/0015-endpoints.md) §9

## Context

- When an endpoint needs a key, the gateway attaches it to each request it forwards (design 0001 §6.1, step 6). The
  key is a secret of the kernel, `CLANK_HOME/secrets/endpoint/<id>/key`, readable by the owner only
  (`clank/kernel/secrets.py:67-100`).
- An endpoint beyond this machine needs a key (design 0015 §2): without one, any program that reaches its server can
  use it, and Clank cannot tell the owner's server from another one at the same address. The first session's endpoint
  is a tunnel to the owner's cluster, so the key is part of it.
- Design 0002 §2.8 (approved): "A component gets one through the kernel, which records which component used which
  secret and why, never the value." Clients see a secret's name, when it was set and its last four characters, never
  its value.
- Design 0002 §2.7 (approved): data-plane processes get a token of their own when they start, with the access level
  `process` ("report events, ask for policy decisions, read its own configuration"). It is not built: the API knows one
  level, `control` (`clank/kernel/api.py:55`), and mounts every component's routes with it
  (`clank/kernel/api.py:153`). The gateway calls the service with the local token, which allows everything
  (`clank/client.py:59-65`; `clank/components/gateway/server.py:586-600`).
- The gateway is a process of its own, adopted by its identity after a restart of the service
  (`clank/components/gateway/service.py:4-7`).
- The service and the gateway run as the owner's own account, so either one could read `secrets/` and
  `state/local.token` as files. Neither option below hides the key from the gateway: they differ in who reads the
  file, how each use is recorded, and whether the API can ever hand a key out.
- Decision 0021: `secret.use` is decided at the moment of use and never kept.

## Decision

**Not yet made: the owner chooses one of these.**

**(a) A process token, on routes only processes may call** (recommended). The gateway's service makes a token for the
gateway at each start of it, and gives it in the gateway's environment (never in a file or on its command line). It
registers the token's SHA-256 with the kernel, which keeps it in its state with the process it names, so a gateway
adopted after a restart of the service is still known; the gateway's next start replaces it. The kernel gains the
`process` access level: a component declares routes that only a process token reaches, and the token says which
process calls. The first is the gateway's `GET /api/v1/gateway/keys/{endpoint}`: the service reads the key through the
kernel (`Secrets.value`, `user="gateway"`, `why` naming the launch), so each read is a `secret.used` event, and answers
only while that endpoint serves a slot. The local token cannot call it, so no client (the console, VS Code, a paired
phone later) can ever read a key's value through the API. It costs a change to the kernel (a second access level, its
scheme, the registered tokens, and the test that every route declares its level) and the token's life (a new one at
each start of the gateway, kept through adoption): two steps of plan s10 (E5a, E5b).

**(b) The gateway reads the key's file itself.** When a launch's route names an endpoint with a key, the gateway reads
`secrets/endpoint/<id>/key` (with the kernel's own path rules, reading only) and tells the service it did, which
records it as `secret.used`. No change to the kernel: one step. But `secrets/` gets a second reader outside the kernel,
design 0002 §2.8's "through the kernel" is revised for it, and a use is recorded only when the gateway's report
arrives: the gateway has no spool, so while the service does not answer it would have to use the key unrecorded or
refuse it.

**Claude recommends (a)**: it builds what design 0002 §2.7 and §2.8 approved instead of a way around them. The kernel
stays the one reader of `secrets/` and the one recorder of each use, the API never hands a key to a client, and the
`process` level is the one the other data-plane processes (the tool hub, the edge's grants) will need. It costs one
step more.

**In either case:**

- The key is read once per launch: the gateway gets it the first time a launch's route needs it, keeps it in memory
  only while that launch is the route, and gets it again for the next launch or after the key changes. The runtime,
  part of the service, reads it through the kernel the same way for its own requests (a load's health, the watcher's
  checks), which send it as the gateway's do.
- This refines decision 0021 for endpoint keys: the moment of use is the launch the owner started, since a decision
  per request would stop every request to the endpoint while the service restarts. Once this record is accepted,
  decision 0021 says "Refined by 0073", as AGENTS.md asks of both records.
- The key never travels in the routes the gateway follows, and is never written into a record, an event, an
  operation's log, a process's log or the tunnel's file; the gateway removes its value from its records and its live
  view wherever it appears (design 0002 §2.8's last rule).
- `clank endpoint key` asks for it without showing it, or reads it from standard input; never from an argument.

## Alternatives considered

- **(b)**, above: one step instead of two, at the cost of a second reader of `secrets/` and a use that can go
  unrecorded.
- **The key in the routes the gateway follows each second.** It would travel every second, through a route the local
  token can call, so any client could read it: what design 0002 §2.8 forbids.
- **The key given to the gateway when it starts** (its environment). A key set or changed later would need a restart of
  the gateway, which cuts requests in flight; and every key would sit in the gateway's environment whether a slot uses
  it or not.
- **A route the local token may call.** Every client holds the local token, so every client could read every key.
- **The process token's hash kept by the gateway's service, beside the gateway's identity in `state/gateway.json`.**
  The kernel checks every token, so it keeps the hashes it checks against: one place for them all.

## Consequences

- With (a), design 0002 §2.7's `process` level exists from here on; the gateway's other calls (its routes, the vision
  model's wake-up, Notion) can move to its token in later steps, and the local token's reach over the gateway narrows.
- With (b), design 0002 §2.8 is revised for the gateway, and a later design that moves the gateway to another host
  needs a way for the key to get there.
- The key's steps (E4, E5a, E5b) are needed for the first session, no longer only when the server happens to need a
  key.
- Either way, an endpoint's first request after each load reads the key once, recorded once.
