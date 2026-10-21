# 0075. A workspace's requests stay on this machine until the owner widens its bound; each workspace has its own key, and each route a container reaches has its rule

- Status: Proposed: the owner chooses; for cloud models, answered by the owner's decision
  [0103](0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md) (per workspace, asked once; Notion never),
  built as decisions [0111](0111-local-only-content-is-kept-from-the-cloud-in-four-places.md) and
  [0112](0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md) say
- Date: 2026-10-18
- Decided by: not yet: the owner answers the question below; Claude recommends. Written with
  [design 0015](../design/0015-endpoints.md) §10, and revised after its review of 2026-10-19

## Context

- Design 0002 §2.6 (approved) declares `model.send`: "a workspace's content going to a model provider: on this
  machine, on a server of the user's, or a third party's hosted API". A workspace's bounds say "where its model
  requests may go: this machine only, unless the user widens it". The gateway enforces it: "Each request is checked
  against the provider serving it at that moment, so switching a role to a hosted model never widens where a
  workspace's content goes."
- None of it is built. There is no policy function yet, and the gateway cannot tell workspaces apart: every
  workspace's OpenCode sends the key `local` (`clank/components/agents/adapters/opencode.py:142`), through one edge
  that relays every workspace's traffic (`clank/components/workspaces/sandbox.py:154-169`). Design 0002 §2.7 has the
  edge name the session, but the edge relays the gateway's whole port, bytes both ways, and reads no HTTP
  (`clank/components/workspaces/image/edge.py:1-6`). So the agent's shell reaches every route that Clank's MCP server
  in its container reaches, and that server sends no credential today
  (`clank/components/workspaces/image/phone_mcp.py:221-223, 306-308`).
- Every route of the gateway answers any caller. `/activity/live` gives the newest request's last message from the
  user and up to 400,000 characters of its thinking, answer and tool calls, whichever workspace sent it
  (`clank/components/gateway/activity.py:28, 92-121`; `clank/components/gateway/server.py:128-130`). `/v1/infill`
  sends a request to whatever port its role's slot has (`clank/components/gateway/completion.py:101-113`).
- An endpoint on a cluster the owner has access to is a server the owner runs (a job in their account) on the
  cluster's machines. The tunnel encrypts traffic only as far as the login host, unless it ends at the node (design
  0015 §5); the cluster's documentation says its compute nodes have publicly routable addresses, and its tunnel recipe
  has the server listen for other computers.
- The owner's rule: research stays with local models. The agent reads the owner's Notion through the gateway
  (`clank/components/gateway/server.py:134-142`), and what it reads enters its context, so it goes wherever the
  workspace's model requests go.
- OpenCode sends a session's whole history with each request, and its sessions stay in the workspace's home volume
  (`clank/components/workspaces/sandbox.py:8-9`): what a session read while bound to this machine goes with its next
  request after a widening.
- The main slot serves every workspace at once (decision 0077). A switch made for one workspace, or by a flow's box
  (decision 0062), changes where every workspace's next request goes.
- The workspaces and agents components use the gateway (`clank/components/workspaces/component.py:38`,
  `clank/components/agents/component.py:39`), and the gateway uses only the runtime
  (`clank/components/gateway/component.py:34`). Decision 0019 and `tests/test_architecture.py:67` forbid a cycle.
- Decision 0021: `model.send` to a third party is decided at the moment of use.

## Decision

**Proposed, for the owner to answer:**

1. **Reach.** What serves a slot has a reach: an engine, `this-machine`; an endpoint, what its record says:
   `this-machine`, `my-servers` (a server the owner runs elsewhere, a job on a cluster included) or `hosted` (a third
   party's API). A missing reach reads as `hosted`.
2. **A bound per workspace.** Each workspace's record has `models`, the farthest reach its content may go:
   `this-machine` for every workspace, new or existing, until the owner widens it (`clank workspace allow FOLDER
   --models my-servers`, or the folder page). Widening is a change to the workspace's settings, recorded with who made
   it; narrowing applies to the next request.
3. **A key per workspace, kept by the gateway.** Each workspace's OpenCode, and Clank's MCP server in its container,
   send a key of their own: the workspace's name at the gateway. The gateway's service makes it and keeps it, as the
   secret `workspace/<id>/gateway-key`, and keeps its SHA-256 and the workspace's bound in the gateway's own state.
   The agents component gets the key, through a public function of the gateway's service, when it writes OpenCode's
   configuration and the MCP server's environment; the workspaces component gives the gateway each workspace's bound,
   at each change of its record and at each start of the service. No component cycle forms. The routes the gateway
   follows carry hashes and bounds, never a key. This refines design 0002 §2.7 (the edge cannot name a session) and
   §2.8: no secret enters a sandbox, but this one is the sandbox's own name; and the gateway, which knows it only by
   its hash, cannot remove it from what that workspace's agent sends.
4. **The gateway checks every model request**: the reach of what serves its role's slot at that moment, against the
   bound of the workspace its key names. Beyond it, the request is refused before anything is sent (403,
   `model_send_denied`), in words that say how to widen the bound or load a model on this machine, and recorded. A
   request with no known key may go only to this machine. Switching a role never widens a bound. While the service
   does not answer, the gateway keeps the last bounds, but refuses requests to a `hosted` endpoint (decision 0021).
5. **Each other route a container reaches has its rule.** `/notion/...` answers only a request with a known workspace
   key (under (i) below, only one whose bound is this machine): never one without a key. `/activity`,
   `/activity/live` and `/completion` answer only the local token, which no container holds; the service, their only
   caller, sends it. `/v1/infill` is answered only by an engine on this machine. `/health` and `/v1/models` answer
   anyone.
6. **Widening says what it sends, and gives a new key.** The folder page and the command ask first (`--yes` answers
   for a script), saying that each session the workspace already holds goes whole with its next request, and
   recommending a new session, or a workspace made for the purpose. The workspace gets a new key, so each OpenCode
   started before the widening keeps the old bound (its key is no longer known: this machine only), and the new bound
   applies from OpenCode's next start.
7. **The owner's question.** Your rule is that research stays with local models. Whatever you answer, widening a
   workspace sends what its sessions already hold, research files and Notion pages included, with their next request
   (6, above).
   - **May a workspace's files go to the remote server?** (i) No workspace's: endpoints serve only a scratch
     workspace of made-up content, for the dry runs. (ii) Per workspace, each one widened by you. (iii) All at once,
     with one switch.
   - **May the Notion pages the agent reads go there?** (i) No: the gateway answers `/notion/...` only to a known
     key whose bound is this machine. (ii) Yes: any known key, wherever that workspace's bound allows.
   - **Claude recommends (ii) for the files, starting with one new scratch workspace of made-up content for the dry
     runs (T1, T4), new so that no earlier session goes with it, and (i) for Notion**, until you decide otherwise: it
     keeps your rule for everything that is research, and lets you widen one workspace at a time, each widening asked
     first and on record.

## Alternatives considered

- **One switch for every workspace** (iii). One bound instead of one per workspace (the keys stay, since Notion is
  decided by a known key), but weaker: widening it for a test widens it for every workspace, research included; and
  design 0002 §2.6 asks for bounds per workspace.
- **Name the workspace at the edge**, as design 0002 §2.7 says. The edge would have to read HTTP and add a header the
  agent cannot forge, for every workspace through one relay: a larger change to the sandbox, for the same result.
- **Tell workspaces apart by their address.** Every container's traffic reaches the gateway from the same relay.
- **No check: the owner loads the right model.** A switch of the main slot for one workspace, or by a flow, would send
  every other workspace's next request along with it.
- **Treat a request without a key as bound to this machine, for Notion too.** The safe side for model requests, but
  the open side for Notion: the agent of a widened workspace could fetch a page from its shell without the key, and
  the next request of its OpenCode, which carries the key, would take it to the cluster.
- **Keys and bounds kept by the workspaces component, read by the gateway.** The gateway would then use the workspaces
  component, which uses the gateway: the cycle decision 0019 forbids.
- **Refuse widening while the workspace holds sessions.** Clank sees a workspace's sessions only while its container
  runs (`clank/components/agents/api.py:153-156`), and a new session in the same workspace reads the same folder.
  Asking, with a new key, says what matters and keeps every OpenCode already running at the old bound.

## Consequences

- This is the first piece of design 0002 §2.6's policy: the bounds layer's `model.send` rule alone. The policy
  function, the floor, modes and grants come with M7, where this rule becomes one of its rules; until then a request
  beyond its bound is refused, never asked about.
- Under decision 0077's option (a), while the main slot runs an endpoint, every workspace still bound to this machine
  is refused, saying why (T1).
- Each workspace's OpenCode configuration changes at its next prepare (its key). An OpenCode started before has no
  known key, so its requests stay on this machine, and it reaches no Notion, until it starts again: the safe side.
- The gateway's activity routes need the local token from here on, and the service's calls send it.
- A flow's box whose preset is an endpoint's needs its workspace widened first, and the runner says so before it
  switches the slot.
- Each request's record names its workspace, which the Requests page can show.
- Five steps of plan s10 (E11a-E11e).
