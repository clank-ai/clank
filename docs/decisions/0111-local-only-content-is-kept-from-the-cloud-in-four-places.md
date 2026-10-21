# 0111. Local-only content is kept from the cloud in four places: the agent's configuration, the gateway's Notion route, the tools it passes on, and each cloud request's history and session

- Status: Proposed (Claude's call)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §10; it says how decision
  [0103](0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md)'s "Notion pages and MCP servers marked local
  never go to the cloud" is enforced

## Context
- The agent reads Notion through Clank's MCP server in its container, which calls the gateway's `/notion/...` routes
  (design 0010 §3); an MCP server's answers enter the agent's context as tool results. Either then goes with every
  later request of the session, to whatever model serves it.
- The main slot can switch between a local and a cloud model while an OpenCode session runs (the owner, or a flow's
  box), and a session allowed the cloud mid-way already holds what it read.
- OpenCode names an MCP tool `<server>_<tool>` (its unsafe characters made `_`,
  `clank/components/agents/adapters/opencode.py:72, 102-104`); Clank's own server is `clank`, so its Notion tools are
  `clank_notion_*`. It sends `X-Session-Id`, and `x-parent-session-id` for a subagent.
- MCP server records have no local mark today (`clank/components/tools/kinds.py:14`).
- OpenCode compacts a session into a summary, after which the calls are gone from its requests.

## Decision
- **The mark**: an MCP server record gains `local_only`. When the owner agrees to a provider, every MCP server already
  added is marked local (they were added when nothing left this machine); one added later asks. Clank's Notion tools
  are always local.
- **1. The agent's configuration**: a workspace allowed the cloud gets no server marked local, and Clank's MCP server
  lists no Notion tools there, from OpenCode's next start.
- **2. Notion at the gateway**: `/notion/...` answers only a known workspace key whose bound is this machine (decision
  0075's (i)).
- **3. The tools passed on**: the gateway removes local-only tools from a cloud request's `tools`, so the cloud model is
  never offered them.
- **4. History and session**: the gateway refuses a cloud request (403, `local_only`) whose messages hold a call to a
  local-only tool, or whose session, or parent session, it has marked; it marks a session the first time it sees such
  a call in any of its requests, whatever slot serves it, and keeps the marks in `state/local-only.json`, so a
  compaction does not clear them.

## Alternatives considered
- **The configuration alone**: an OpenCode started before the workspace was allowed, or before the slot switched, still
  holds the tools and what they returned.
- **The history check alone**: a compaction's summary carries what a call returned without the call.
- **Refuse a cloud request whose tools list holds a local-only tool**, instead of removing them: every session started
  before the workspace was allowed would be refused until OpenCode starts again, though it may never have used one.
- **Unmarked by default** (the owner's words, "marked local", read strictly): an MCP server added for research before the
  cloud existed would go to the cloud unless the owner remembered to mark it.

## Consequences
- What the agent wrote into the folder's files from a Notion page or a local server's answer is not seen; the
  workspace's question says so when its sessions used one.
- A session that used Notion or a local server never uses the cloud model; a new session does.
- The agents component gives the gateway the local-only tool names (the gateway may not use the tools component:
  decision 0019).
