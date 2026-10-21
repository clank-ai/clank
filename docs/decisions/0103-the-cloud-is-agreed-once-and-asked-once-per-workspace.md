# 0103. The cloud is agreed to once per provider and asked once per workspace; existing workspaces stay local; Notion and MCP servers marked local never go

- Status: Accepted (the owner's decision); how a workspace is asked is decision
  [0112](0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md), and how local-only content is kept
  from the cloud is decision [0111](0111-local-only-content-is-kept-from-the-cloud-in-four-places.md)
- Date: 2026-10-20
- Decided by: the owner's second answer of 2026-10-20 ("Privacy: ask once per workspace. Adding the provider asks the
  owner once to agree that prompts and the files the agent reads go to that provider; each workspace then asks the
  first time it would use the cloud model; existing workspaces stay local until the owner says otherwise; Notion pages
  and MCP servers marked local never go to the cloud."), written into [design 0016](../design/0016-cloud-models.md) §9

## Context
- The owner's rule is that research stays with local models. Design 0002 §2.6 approved `model.send` with a bound per
  workspace, "this machine only, unless the user widens it", checked by the gateway against the provider serving at
  that moment; none of it is built, and the gateway cannot tell workspaces apart (every OpenCode sends the key `local`).
- Decision [0075](0075-where-a-workspaces-requests-may-go.md) (proposed with design 0015) proposes a key per workspace,
  a bound per workspace, and Notion only for a key whose bound is this machine, and asks the owner whether a
  workspace's files and the Notion pages it reads may go to a server beyond this machine.
- OpenCode sends a session's whole history with each request, so what a session read while local goes with its next
  request once it may use the cloud.

## Decision
- **Agreed once per provider.** Adding a cloud provider asks the owner once to agree that prompts, and the files and
  command output the agent reads, go to that provider (and from it to the model's provider). Without the agreement,
  nothing loads from it.
- **Asked once per workspace.** Each workspace asks the first time it would use the cloud model. The answer is kept in
  its record: allowed, or kept local (not asked again until the owner changes it).
- **Existing workspaces stay local** until the owner says otherwise: nothing about them changes when a provider is
  added, and their question says that their earlier sessions and folder may hold research.
- **Never to the cloud**: Notion pages, and the MCP servers the owner marks local.
- This answers decision 0075's question for the cloud: per workspace ((ii) for files), and Notion not at all ((i)).
  Its keys and bounds are built for the cloud by design 0016; its question for the owner's cluster (`my-servers`) stays
  with design 0015.

## Alternatives considered
- **One switch for every workspace**: simpler, but adding the provider would send every workspace's research with its
  next request, against the owner's rule.
- **Refuse beyond the bound, never ask** (decision 0075 as proposed): safe, but a new user's first workspace would be
  refused until they found the command; the owner asked for one pass.
- **Ask at every session**: more questions than the owner wanted ("ask once per workspace").

## Consequences
- The gateway must know each request's workspace: design 0016 builds decision 0075's workspace keys and bounds.
- A workspace allowed the cloud reads no Notion and gets no MCP server marked local (decision 0111).
- Decision 0075's status names this decision for the cloud.
