# 0060. Each box runs in a new session on the flow's own OpenCode server, without a terminal

- Status: Accepted (the owner's choice, 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, choosing (a), as recommended, in the Choice of
  [design 0013 §5](../design/0013-flows.md#5-running-a-box-a-fresh-session)

## Context
Each box is a big task with its own prompt, model, limits and tools, and the owner asked that INTEGRATE be "a brand
new session which is only dedicated to taking all the outputs of this last step". Meanwhile the owner works in the
workspace's OpenCode window, and changing OpenCode's configuration while it runs restarts its instance and closes
every event stream (design 0007 §2). The model battery ran one fresh session per task and did twelve of thirteen
right, and found a conversation past about 60K tokens best started afresh, where KVMem's replay failed
([2026-10-15](../measurements/2026-10-15-model-battery.md)).

## Decision
- A new session for each box, and for each try; none inherits the history of the boxes before it.
- Its first message is, in order: the type's instructions, the box's prompt, the files it sees, its deliverable and
  *accept when*, and on a later try what happened to the last one. It is sent with the box's agent and model and kept
  as a file beside the box's tries; the session's title names the flow, the box and the try.
- The session runs on the flow's own OpenCode server without a terminal (`opencode serve`, which the bridge starts and
  the one-window rule leaves alone: designs 0005 §2 and 0004 §5), watched in the Monitor and listed on the phone with
  the other sessions.
- The runner starts that server with the box's limits and tools, and starts it again only when a box's preset has
  other limits; the run log says so.

## Alternatives considered
- **(b) In the workspace's OpenCode window,** as `/agents/implement` does (design 0009 §8), seen in VS Code. A box
  would take over the window the owner works in, and a box's other limits would restart the owner's OpenCode.
- **One session for the whole flow,** each box a message in it. The owner asked for a fresh start, and the battery
  found a conversation past about 60K tokens best started afresh.

## Consequences
- A box never takes over the window the owner works in.
- A restart of the flow's server ends what its MCP servers run in the background (design 0004 §10), which is why it
  happens only when the limits differ.
- Each fresh session reads its first prompt without the engine's cache: KVMem took 13 s to the first token for about
  8K tokens, and 41 s for about 31K (2026-10-13); the Flow view shows a flow's fresh starts before it runs (§7).
- The bridge's `prompt` must send the agent and the model, and the watcher must say when a session's status changes;
  both are built once, for the Monitor too, in design 0012's step 4.
- To measure: how two OpenCode servers in one container keep configurations of their own, and whether the owner's
  window can show a session the other server runs.
