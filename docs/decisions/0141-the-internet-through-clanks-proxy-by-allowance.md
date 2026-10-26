# 0141. The agent reaches the internet only through Clank's proxy, by the owner's allowances; private addresses never

- Status: Accepted (with design 0024, approved by the owner on 2026-10-26); the proxy, the allowances and the refusals built 2026-10-26 ([plan s53](../plans/s53-the-proxy.md)); the ask and the named sets follow
- Date: 2026-10-26
- Decided by: the owner (approving design 0024), Claude (the design)

## Context

A workspace's container joins an internal network where nothing answers but the edge (design 0004 §3): the agent
cannot fetch a paper, read documentation, download data or install a package while it works. Clank's rules: nothing
leaves without the owner seeing where it goes (design 0016 §9: each workspace asked once before the cloud), deny
wins (decision 0018), everything recorded.

## Decision

- The agent's only way to the internet is a forward proxy at the gateway (HTTP `CONNECT` for TLS, plain HTTP
  forwarded), reached through the edge as the gateway is; the container's environment names it (`HTTP_PROXY`,
  `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`), with the workspace's token in the proxy's URL, so each request meets its
  own workspace's allowances.
- The owner allows hosts per workspace (exact names or suffixes), kept in the workspace's record; a host the agent
  reaches without an allowance is held while the owner is asked (once, always, no), and refused in plain words
  otherwise. Named sets (packages, papers, code, data, documentation) are sugar over the same allowances.
- Private addresses (the machine, the local networks, the tailnet, other containers) are refused always, before and
  after resolving; the gateway and the service are reached only on the edge's port as today.
- Every exchange is recorded by time, workspace, host, method, status, bytes and duration (the path for plain HTTP);
  never a body, never a tunnel's bytes.

## Alternatives considered

- **A second network with the internet** on the container: no allowance, no record, and the machine's own services
  reachable.
- **Allowing at the firewall or with iptables in the container**: needs root in the container, says nothing to the
  owner, and cannot ask.
- **Letting only the setup container reach the internet** (today): reproducible installs, but no paper, no
  documentation and no data while the agent works.

## Consequences

- The edge forwards a second port; the proxy is a part of the gateway component (the standard library, no
  dependency).
- Programs that honor the proxy variables work at once (`pip`, `uv`, `curl`, `git`, Python's `requests` and `httpx`,
  Bun's `fetch`); the instructions say which to use.
- Search stays the owner's choice (design 0024 §6).
