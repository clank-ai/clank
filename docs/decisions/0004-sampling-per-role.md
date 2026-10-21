# 0004. Sampling is set per role in the console and applied by the gateway

- Status: Accepted. Refined by [0008](0008-role-is-the-requested-model-name.md), which settles how the gateway learns a
  request's role (the consequences below left it open).
- Date: 2026-10-11
- Decided by: the owner's answer to "How should the console's sampling settings (temperature, top_p, top_k, thinking
  budget, ...) apply to the tools that use the model?" (chose "Per role, console decides")

## Context
Several tools send requests to the model: the coding agent, batch jobs, the research companion, completion. In the
prototype each sets its own sampling (the agent's configuration says temperature 0.6, the server has its own defaults,
the thinking budget is a server flag), so no single place says what is in effect.

## Decision
Every request has a role (agent, batch, companion, completion, ...), taken from where it comes from. Each role has its
own sampling preset (temperature, top_p, top_k, min_p, penalties, thinking on or off and its budget, maximum output),
edited in the console. The gateway replaces the sampling a request carries with its role's values and records both, so
the console shows what the tool asked for and what actually ran.

## Alternatives considered
- **One global set for every request.** Simpler, but an agent and a batch job need different temperatures.
- **The console's values as defaults only (a tool's own values win).** Leaves the truth scattered across tools.

## Consequences
- The gateway must know each request's role (a label on the tool's container, or a per-tool key).
- A tool's own sampling settings stop mattering; the console says so where a user might look for them.
