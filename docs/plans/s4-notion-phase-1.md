# Notion, phase 1: implementation plan

> At the owner's request (2026-10-17): "begin the design and start implementing this immediately". As for the plan
> mode's plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0010 §11, phase 1: the service connects to Notion with the owner's secret, reads the shared
databases, keeps the agent's proposals in batches, and writes a batch once approved; the agent reads and proposes
through Clank's MCP server and the gateway; `clank notion` connects, lists and approves or rejects.

**Spec:** [design 0010](../design/0010-notion.md); [decision 0039](../decisions/0039-notion-through-the-service-changes-reviewed.md).

## Global Constraints

- Notion's API at `Notion-Version: 2025-09-03`: databases hold data sources; entries are queried and created in a
  data source; a relation names a data source.
- Never the owner's Notion: every test uses the fake Notion (`tests/fakes/notion.py`, an `httpx2` mock transport over
  a made-up workspace); the first live check is the owner's, with a test database (`docs/notion-setup.md`, part 5).
- No Notion content in events, logs or records; the secret only in `CLANK_HOME/secrets/notion/`.
- The container may read and propose, never approve: the gateway forwards those routes only.
- The owner is the sole author of every commit; American English; tests first; tests named as sentences.

## Tasks

- [x] **The component and the connection:** `clank/components/notion/` (component, kinds: `NotionSettings`, service,
  api, cli), `client.py` (the API: requests one at a time, `429` waits `Retry-After`); `connect` (the secret kept and
  checked with `users/me`), `status`; `clank notion connect` (asked without echo) and `clank notion status`
  (`tests/components/notion/test_connection.py`).
- [x] **Reading:** `databases` (the shared data sources with their properties), `query` (compact rows, a cursor),
  `page` (properties and the page as Markdown: `markdown.py`, `properties.py`), `search`
  (`test_reading.py`, `test_markdown.py`).
- [x] **Staging:** proposals of a new entry, a change and a removal, checked against the data source's properties and
  kept with their base in a batch (`batches.py`: JSON files in `state/notion/batches/`); `submit`; the batches listed
  (`test_staging.py`).
- [x] **Applying:** approve (new entries, then changes, then removals; a page's differing blocks replaced; an entry
  changed in Notion since staged left out and said so; each entry's result kept, nothing written twice), reject with a
  reason; `clank notion batches|approve|reject` (`test_applying.py`).
- [x] **The agent's way in:** the gateway forwards `/notion/` reading and proposing routes to the service; Clank's MCP
  server in the container gets `notion_databases`, `notion_query`, `notion_page`, `notion_search`,
  `notion_propose_entry`, `notion_propose_change`, `notion_propose_removal`, `notion_submit`; its environment names the
  workspace; the planner may use the reading tools (`tests/components/gateway/test_notion_forwarding.py`,
  `tests/components/workspaces/test_clank_mcp.py`, `tests/components/agents/test_planner_rules.py`).
- [x] **Documents:** design 0010 and the setup guide; the design, decision and plan indexes; the roadmap (M7's first
  host); the code map and the tests page.
