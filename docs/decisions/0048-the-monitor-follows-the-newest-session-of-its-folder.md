# 0048. The Monitor follows the newest active root session of its folder; a session is keyed by its server too

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §3's Choice as recommended; keying a session by
  its server was Claude's call (2026-10-18), approved with the design

## Context
The page follows one session, and the Guide acts on one ([design 0012](../design/0012-the-monitor.md) §3). OpenCode
1.19.0 sends `X-Session-Id` with every model request, and `x-parent-session-id` for a subagent; the gateway keeps
every header in its records, but does not show them yet. One edge container serves every workspace, so a request's
address names neither a workspace nor a session. A workspace's container may run several OpenCode servers (one for
each window, each `opencode serve` the phone starts, a flow's own), each with its own event stream and run state.

## Decision
- The page follows the **newest active root session of the console's folder** (F4's workspace), named in the session
  line. `s` lists the sessions, each with its server and its state; picking one pins it until the owner picks "follow
  the newest" again. When the folder has no session, the page says so.
- A request is joined to its session by the session's id alone (`X-Session-Id`).
- A session is keyed by its **workspace, its server (its port) and its id**, as the routes
  `/agents/sessions/{workspace}/{port}/{session}/…` already are. Every Guide action goes to the server that runs the
  session, and a note to an idle session starts its run on that server.
- **Subagents** are shown inside their parent's flow, found by the `task` call's `metadata.sessionId`; Enter opens a
  subagent's own flow and panels, and Esc returns to the parent.
- **The Guide acts on the root session**, so Stop stops the whole tree.
- KVMem holds one conversation at a time, so what sits on the GPU belongs to the engine, not to a session: the Context
  window panel says whose conversation the engine holds, and marks when another session took it.
- Requests without a session (completion in VS Code) stay on the Requests page (F7). A session joined mid-run takes
  its earlier steps from OpenCode's history, marked "before Clank watched".

## Alternatives considered
- **Always the owner's pick**: nothing would show before a pick, and a new session in the folder would go unseen.
- **The newest active session anywhere**: the page would leave the console's folder whenever another workspace's
  session became the newest.
- **Joining requests to sessions by their address**: the shared edge container hides which workspace sent them.
- **A session keyed by its id alone**: with several servers in one container, a Guide action could go to one that
  does not run the session.

## Consequences
- The gateway shows each request's session and parent (step 2); the bridge keeps child sessions in its listing, which
  leaves them out today, and reports the server that runs each session (step 4).
- That OpenCode sends these headers on the wire, and that a running subagent stops with its root, are measured first.
- A note to a subagent comes later; it is unmeasured.
