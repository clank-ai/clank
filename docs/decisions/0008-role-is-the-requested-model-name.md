# 0008. A tool names its role through the model name it requests

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner, approving design 0001 §3.3 ("Section 3 looks right")

## Context
Decision [0004](0004-sampling-per-role.md) has the gateway apply each role's sampling, so the gateway must know every
request's role. Its consequences named two ways: a label on the tool's container, or a per-tool key. Labels work only
for tools in containers; keys add a secret to every tool.

## Decision
A tool asks for its role as the model name: the coding agent is configured to call the model `agent`, a batch job
calls `batch`, and so on. The gateway maps the name to the role, the role to its slot, and the slot to its provider.
A request for a name Clank does not know gets the role `default`.

## Alternatives considered
- **Container labels.** Only for containerized tools; invisible in the request itself.
- **A key per tool.** Works anywhere, but adds secrets to manage and hides the role in an opaque string.

## Consequences
- Every tool needs only its usual model setting; scripts, sandboxed agents and editors work the same way.
- The role is visible in every recorded request.
- The real model behind a role can change (a switch) without touching any tool's configuration.
