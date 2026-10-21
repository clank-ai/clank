# 0079. Every action on a session goes to the server that runs it, the phone's too, with the session's agent and model

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-19
- Decided by: Claude, without the owner (plan s14's call 5, building design 0012's step 4); it widens
  [0048](0048-the-monitor-follows-the-newest-session-of-its-folder.md) (the Guide's actions) and
  [0054](0054-a-note-is-a-real-user-message.md) (a note keeps the session's agent and model) to every client

## Context
A workspace's container may run several OpenCode servers (a window's, each `opencode serve` the phone starts, a
flow's). They list the same sessions, since their storage is the container's home, while only one runs each
([design 0012](../design/0012-the-monitor.md) §3). Decision 0048 sends the Guide's actions to the server that runs
the session. The phone and the API name a port too: the server their listing showed, which may not be the one running
the session. A note sent there could start a second run of the session on another server, and a stop sent there
stops nothing. A message that named no agent also went to OpenCode's `build`, so a phone note to a planner session
turned it into build (decision 0054 fixed that for the Guide's notes only).

## Decision
- The service keeps, from its watchers' lines, the server whose event stream carried each session's run
  (`Sessions.runs`). **Every** action on a session goes there, whoever sends it (the Guide, the phone, the API, a
  flow): a message, a stop, a reject, a compaction, a clear, a revert, an unrevert, a page of its history.
- The port a client names is used only for a session no watcher has placed: one no watcher saw run, one whose server
  is gone, and one whose server a watcher started again no longer follows (a container reopened).
- Every message goes with the agent and the model given, else those of the owner's last message in the session, read
  from its history (decision 0054). If that history cannot be read, the message fails, rather than silently going to
  `build`.

## Alternatives considered
- **Only the Guide's actions follow the running server** (decision 0048 as written): the phone's notes and stops could
  reach a server that does not run the session, and its notes would still turn a planner session into build.
- **The client finds the right port**: each client would need what only the watchers know, and the phone's routes
  would change.
- **The port named always wins**: simple, but wrong whenever two servers list the session.

## Consequences
- The phone's notes and stops now follow the running server and keep the session's agent: a change of behavior, and
  a fix.
- Each message first reads the session's history a page at a time (at most 100 pages of 20) to find the owner's last
  message.
- A port the service remembers is dropped when a watcher started again does not follow it any more; until that
  watcher has synced (a few seconds after a container is reopened), an action can still go to the old port and fail,
  and the owner tries again.
