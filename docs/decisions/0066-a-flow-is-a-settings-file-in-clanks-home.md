# 0066. A flow is a settings file in Clank's home, its runs state beside it, copied into the folder on demand

- Status: Accepted (the owner's choice, 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, choosing (b), as recommended, in the Choice of
  [design 0013 §11](../design/0013-flows.md#11-where-a-flow-lives-and-its-file)

## Context
A flow is a settings record (design 0002 §2.2): a readable JSON file that names its schema (`flow/1`), is checked when
read, is read again when it changes on disk, and is written back in one fixed format so diffs stay small; an edit made
on a version that has since changed on disk is refused, with both versions shown. Where the file lives decides whether
the rule that the model only proposes changes to a flow
([0064](0064-the-model-changes-a-flow-only-by-proposals.md)) is enforced or only checked afterwards.

## Decision
A flow's file lives in Clank's home, `CLANK_HOME/config/flows/<workspace>/<name>.json`, and its runs under
`CLANK_HOME/state/flows/`: each run's folder holds its state, each try's first message and copies of its
deliverables (§8). No sandbox sees them (Clank's floor); the model reads the flow through `flow_read`, and
`clank flow export` puts a copy in the workspace's folder when the owner wants one there. Clank ships the flow's
shape as a template in `clank/defaults/`, as it ships its other settings.

## Alternatives considered
- **(a) In the workspace's folder** (`flows/<name>.json`). It would travel with the project and its git history, and
  the model would read it as a file. But the agent's commands can change it without asking (design 0007 §8), so the
  rule that the model only proposes could be checked afterwards, by a fingerprint as a folder's MCP servers are
  (design 0004 §10), and not enforced.

## Consequences
- The rule is enforced where it can be stopped ([decision 0020](0020-enforce-where-it-can-be-stopped.md)), and flows
  live where Clank's other settings already do.
- A flow does not travel with the project or its git history; a copy does, made by `clank flow export`.
- No agent writes a flow's file: the owner edits it, and the service writes in the boxes accepted from the model's
  proposals.
- A flow belongs to one workspace, by its path; flows across workspaces come later (§13).
