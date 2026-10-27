# 0147. The gateway answers only Clank's own programs, and an agent's calls act for its own workspace

- Status: Accepted (Claude, fixing what the code review of 2026-10-27 found, at the owner's request to put the safe use
  of the models through Clank first); refines decision
  [0075](0075-where-a-workspaces-requests-may-go.md) and plan s34's item 10
- Date: 2026-10-27

## Context

The gateway forwards what an agent may ask of the service: Notion, its flow, and the agents' part (showing files, jobs,
artifacts, boards), each as the service's client `agent`. Each such call named its workspace in its body or query. The
gateway did not check that the name was the caller's own, and asked for no key on the flow and agents' routes, while
every workspace's container reaches the gateway through the one edge. Unlike the service's own API, which takes a
token and refuses any Host but its own, the gateway checked neither the Host a request was addressed to nor whether a
browser made it.

Decision 0075 gives each workspace a key of its own. Plan s34 made it only once the cloud was in play, and before,
each workspace's agent sent `local`, so the gateway could not tell local workspaces apart.

## Decision

1. **Every workspace has its gateway key**, a cloud provider agreed or not. The gateway's service makes it the first
   time the workspace's agent is given it, and OpenCode and Clank's tools in its container send it.
2. **An agent's call acts for its key's workspace only.** A call under `/agents/`, `/flows/` or `/notion/` without a
   key the gateway knows is refused (401). A workspace it names must be its key's (403); one left out is filled in, so
   what is forwarded always names the key's workspace (`gateway/agentcalls.py`). What else a call names (a job, a
   board, a flow, a Notion batch, a file) the service looks up inside that workspace.
3. **The gateway answers Clank's own programs only** (`gateway/callers.py`). A request addressed to another host than
   its own names with its port (`127.0.0.1`, `localhost` and `[::1]` on this machine, `edge` in the containers) is
   refused (421), as the service's API refuses one. A request with an `Origin` header, or with `Sec-Fetch-Site` other
   than `none`, is refused (403): a browser made it, and none of Clank's programs sends either.

## Alternatives considered

- **Check the workspace in the service.** The service sees only the gateway's client `agent`, never which container
  called: only the gateway, which holds the keys' hashes, can tell.
- **A key on the job routes only.** The flow, Notion, show and artifact routes read and open a workspace's files too.
- **Keep `local` until the cloud is in play.** Then no two local workspaces could be told apart, and the routes above
  could not be bound to one.

## Consequences

- An agent's window opened before this change sends no key: Clank's tools that go through these routes (show files,
  jobs, artifacts, boards, flows, Notion) are refused, in words that say to start the window again from Clank, which
  gives them the key. The model's requests, looking at a figure, sending to the phone and finding figures go on.
- Each workspace's key is a secret (`workspace/<name>/gateway-key`, with its `secret.set` and `secret.used` events)
  for every owner, not only for those with a cloud provider.
- A new way to the gateway under another host name must be added to `callers.NAMES`; a test client must address the
  gateway by one of its names (`tests/support/agentkeys.py`).
