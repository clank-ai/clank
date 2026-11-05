# 0166. A folder's own MCP server is checked in its workspace's container alone, never on this computer

- Status: Accepted (the audit of 2026-10-30); revises design 0004 §10 and the M8.0 plan's ruling on `check`
- Date: 2026-11-05

## Context

- A folder's own MCP servers are its `.mcp.json`, the file other harnesses read and write, which comes with the folder
  (a clone, a download, a colleague's project). Design 0002 §2.11 has a project's items offered, never trusted, and
  design 0004 §10 gives one to the agent only once the owner allows it for the workspace, with a fingerprint of its
  entry as allowed, so an entry changed since is not given until it is allowed again.
- The agent runs such a server in its workspace's container, which sees only the folder and reaches nothing but the
  model and the hosts the owner allowed. A check is meant to show what the agent will find there.
- `clank mcp check` (and `c` on the MCP servers page when the folder was no workspace) started a folder's server on
  this computer unless a workspace was named, so it was checked where the agent never runs it, outside the container
  that holds a folder's programs to the folder.

## Decision

- **A folder's own server is checked only in its folder's workspace container**, as `check --workspace` did: the
  service finds the folder's workspace itself when none is named, and starts the server there with the agent's
  environment. It is never started on this computer.
- **A check that cannot run there is refused, saying how to check it**, and starts nothing: the folder is no workspace
  yet (`clank workspace open` makes it one), its container does not run (`clank workspace open` starts it), another
  folder's workspace was named (the folder's own is named instead), or the server is reached by address (nothing but
  the model is reachable from the container yet, and the agent does not get such a server either). The console says the
  same before it asks the service.
- **The check says whether the workspace's agent may use the server as it is now**: allowed, not allowed yet, or
  changed since it was allowed (its command, its arguments or its environment), which counts as not allowed until the
  owner allows it again. The allowance and the check read one fingerprint (`fingerprint` in the tools component's
  service, the digest of the entry the agents component keeps when the owner allows it), so they never disagree.
- **A check is not an allowance**: checking a folder's server in its container gives it to no agent, and a server not
  allowed may still be checked there, so the owner can see its tools before allowing it.
- **The owner's own servers** (`clank mcp add`, Clank's configuration) are checked as before: on this computer, or in
  the folder's workspace with `--workspace` (in the console, while an agent runs there). Clank's own is checked in a
  workspace only, as before.

## Alternatives considered

- **Refuse every check without `--workspace`, saying to add it**: as safe, but a folder's server has one place to be
  checked, so asking for the flag adds a step and nothing else; the service names the workspace it used in the
  check's log.
- **Ask the owner before starting a folder's server on this computer**: whatever the answer, the server would run
  outside the container that holds a folder's programs to the folder, and not where the agent runs it, so the check
  would show less than it does in the container.
- **Check a folder's server only once it is allowed**: the owner's natural order is to look at a server's tools, then
  allow it; the container already holds the server to what the folder may do, so the check does not wait for the
  allowance and says where it stands instead.
- **Keep reaching a folder's server at an address from this computer**: the address and its headers come from the
  folder's file, and the agent never reaches such a server from its container, so a check from here would show what
  the agent cannot use.

## Consequences

- A folder must be a workspace, with its container running, before its own servers can be checked; the refusal says
  how. `clank mcp check NAME` in such a folder now runs the server in its container without `--workspace`.
- A folder's server reached by address cannot be checked until the container may reach addresses other than the
  model's (M8's tool hub, or a host the owner allows).
- The words "allowed", "not allowed yet" and "changed since you allowed it" now come from the check too, in
  `clank mcp check`'s output and the console's message after `c`.
