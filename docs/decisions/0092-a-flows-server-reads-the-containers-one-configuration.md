# 0092. A flow's OpenCode server reads the container's one configuration, written for the main slot as it runs

- Status: Accepted, as Claude's call; the owner may reverse it once the measurement below is made
- Date: 2026-10-20
- Decided by: Claude, without the owner ([plan s27](../plans/s27-flows-a-model-per-box.md)'s call 7, building
  design 0013's step 5); it applies [0060](0060-each-box-runs-in-a-new-session-on-the-flows-server.md) and
  [0062](0062-a-preset-per-box-switched-in-before-it-starts.md)

## Context
A flow's boxes run on its own OpenCode server, without a terminal, beside the owner's window in the same container
(decision 0060). A box whose preset has other limits gets that server started again for them ([design
0013](../design/0013-flows.md) §5), since changing OpenCode's configuration while it runs restarts its instance and
closes every event stream (design 0007 §2). OpenCode reads its configuration when it starts, from
`~/.config/opencode/opencode.json` in the container's home, which Clank writes (`Agents.configure`): the gateway as its
one provider, the role `agent` as its one model, with the limits of the preset the main slot runs. Design 0013 §5 left
"how two OpenCode servers in one container keep configurations of their own" to measure, with the owner's go-ahead;
step 5 was built on 2026-10-20 without it (nothing ran OpenCode).

## Decision
- The flow's server takes the container's one configuration, as every OpenCode there does: when it is started (or
  started again), Clank writes the configuration for the main slot as it runs now, after the box's *model* step, so
  its limits are the box's.
- The owner's window keeps the configuration it started with (Clank runs OpenCode without its file watcher, and the
  service asks nothing of the window), and takes the written one when it next starts, which is what decision 0062 asks
  after a switch ("its configuration is refreshed when it next starts"). That a running window never reads the file
  again is part of the measurement.
- The run keeps the limits its server was started with; the server is started again only when a box's differ.

## Alternatives considered
- **A configuration of the flow's server's own**, through OpenCode's `OPENCODE_CONFIG` (a file merged over the
  global one) or `OPENCODE_CONFIG_CONTENT` (the configuration in its environment): the window's file would then change
  only when the owner starts OpenCode. Not measured on OpenCode 1.19 in the sandbox: which one wins for the model's
  limits, and whether a merged file keeps the window's own MCP servers, are the measurement's questions.
- **A home of its own for the flow's server** (`XDG_CONFIG_HOME` pointed elsewhere): its sessions' storage might move
  with it, and the window, the phone and the Monitor read the sessions of the container's one storage.

## Consequences
- After a switch for a box, the window's next start gets the new preset's limits, as decision 0062 says; a window
  started between two boxes of different presets gets whatever the slot runs then, as it would without a flow.
- A server started again ends what its MCP servers ran in the background (design 0004 §10): the run log says so
  (`flows.server`), and it happens only when the limits differ.
- When the measurement shows two servers can each keep a configuration of its own, this decision is superseded by one
  that gives the flow's server its own and leaves the window's file to the window.
