# 0039. Notion is reached by the service only, and the agent's changes are staged for the owner's review

- Status: Proposed (built at the owner's instruction, 2026-10-17; the owner reads design 0010)
- Date: 2026-10-17
- Decided by: Claude, on the owner's request (2026-10-17) that the local agent read their Notion databases and that
  every change it wants be reviewed in VS Code first

## Context
The owner keeps research databases in Notion to share results with others. The agent's container reaches nothing
but the edge (design 0004 §3), and network grants (M7) are not designed. Notion offers a hosted MCP server and an
open-source local one; either would need the container to reach Notion with the owner's secret, and either lets the
agent write directly.

## Decision
A `notion` component in the service holds the secret, talks to `api.notion.com` (Notion-Version 2025-09-03) and
answers the agent's reads; the agent's writes are proposals kept in batches (JSON files in Clank's state) that the
owner approves, rejects or sends back with comments; only the service writes, and only what was approved. The agent
reaches the service through Clank's own MCP server and the gateway, which forwards the reading and proposing routes
only (design 0010).

## Alternatives
- **Notion's hosted MCP server, or its local one, given to the agent.** The container would need the internet and the
  secret, and writes would go straight to Notion with no review.
- **A Notion MCP server run by the service, with its tools forwarded.** No container route needed, but its write tools
  write at once; staging would mean rewriting each tool's meaning anyway.
- **Copies of the databases as files in the folder.** Reads with the agent's own tools and no route at all, but stale
  copies of the owner's research in every workspace, and no way to stage a change against what Notion holds now.

## Consequences
The service has its first outside host besides model downloads; the gateway forwards a few non-model routes; the
sandbox image's MCP server grows Notion tools (the image changes). The review editor in VS Code (design 0010 §6) and
comments (§7) are new work, in phases.
