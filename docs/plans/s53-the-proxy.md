# Plan s53: network access for the agent, step 1: the proxy

Design 0024 §1, §2 and §7 (and §8 step 1), decision 0141, approved 2026-10-26: the agent reaches the internet only
through Clank's forward proxy, and only where the owner allowed, workspace by workspace; private addresses never.
This step builds the way out and the allowances; the ask (§3), the named sets (§5), the views (§4) and the
instructions (§5 of §8) follow in their own plans.

## What exists

- The gateway process (`gateway/server.py`, `create_gateway`, `main`): FastAPI under uvicorn on the loopback, its
  `Routes` fetched from the service every second (`gateway/routes` carries the slots, the workspaces' cloud bounds,
  the cost), the service's local token for the owner's routes, `TrafficLog` in `logs/traffic/<day>.jsonl`.
- The edge (`workspaces/image/edge.py`): one port joined to one target, bytes both ways; `edge_spec` runs it with the
  gateway's port; `folders.py`'s `open` ensures it (made again only from a newer image).
- A workspace's container (`workspace_spec`): the internal network only; its environment `thread_env`; the agent's
  `CLANK_GATEWAY` and `CLANK_GATEWAY_KEY` set by the agents component when OpenCode is configured.
- The workspace record (`workspaces/kinds.py`, `Workspace`), the cloud allowance (`cloud.py`: the record written, the
  gateway told through the bounds, an event), `POST /workspaces/{name}/cloud`, `clank workspace allow FOLDER --cloud`.

## Choices made here

- **The workspace's token** in the proxy's URL (`http://<workspace>:<token>@edge:<proxy port>`) is derived: the
  SHA-256 HMAC of the service's local token over the workspace's name (`network_token`), so the gateway process, which
  holds the local token, checks it without being handed anything, it survives every restart, and it names the
  workspace; the gateway's own key (`CLANK_GATEWAY_KEY`) is `local` for every workspace until a cloud provider is
  agreed, so it cannot name one.
- **The allowances ride on the routes** the gateway fetches every second (`network`: each workspace's hosts), as the
  cloud bounds do; nothing new is handed.
- **The proxy runs in the gateway's process**, an `asyncio` server started with the application, on `proxy_port`
  (a gateway setting, 18211) of the loopback; the edge forwards it as it forwards the gateway's port.
- **One request a connection** for plain HTTP (`Connection: close` to the upstream): `pip`, `curl`, `uv` and `git`
  open another connection as they need; a tunnel lives as long as both sides keep it.
- **The edge is made again when the ports it forwards change** (its label `clank.ports`), stopped first when it runs:
  every workspace's way to the gateway pauses for the second it takes, said in the operation's log.

## Tasks

- [x] 1. **The proxy** (`gateway/proxy.py`): `network_token(local, workspace)`; `allowed_host(host, patterns)` (exact,
  or a suffix `.example.org` for the name and every name under it); `private_address(ip)` (loopback, RFC 1918,
  link-local, the carrier range 100.64/10, unique local and link-local IPv6, `::1`); `Proxy(hosts, token_of, log,
  resolve, private)`: `Proxy-Authorization: Basic workspace:token` names the workspace (407 otherwise); `CONNECT
  host:port` to an allowed host resolves it at the proxy, refuses a private name or address before and after
  resolving, connects to the address found and joins the two sides (bytes counted, never read); a plain request
  (`GET http://host/path`) is forwarded to the host with its path, the proxy's own headers dropped and `Connection:
  close`; a refusal is `403` with the words that say the host, the workspace and how it is allowed; a name that
  cannot be resolved `502`. `NetworkLog(folder, keep_days)`: one JSON line an exchange in `logs/network/<day>.jsonl`
  (time, workspace, host, port, method, path for plain HTTP, status, bytes each way, seconds, why refused), days
  older than kept removed. Tests against a fake upstream on this machine (`test_proxy.py`).
- [x] 2. **The gateway serves it**: `GatewaySettings.proxy_port` (18211); `create_gateway(..., proxy=, proxy_port=)`
  starts the proxy's server with the application and stops it with it; `main` makes the proxy with the routes'
  hosts, the local token and the network log; `Routes.hosts_of(workspace)` from the routes' `network`; the service's
  `routes()` carries each workspace record's hosts. Tests: the routes' shape; the proxy answering on a gateway made
  by `create_gateway` in a test.
- [x] 3. **The edge forwards two ports**: `edge.py LISTEN TARGET_HOST TARGET_PORT [LISTEN TARGET_HOST TARGET_PORT]...`;
  `edge_spec(home, image, *, gateway_port, proxy_port)` with the label `clank.ports`; `open` makes the edge again
  when the label differs (stopped first). Tests: `test_edge.py` with two pairs; `test_sandbox.py`'s edge test.
- [x] 4. **The container is told**: `workspace_spec(..., proxy="")` adds `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (the
  URL) and `NO_PROXY=edge,localhost,127.0.0.1` to its environment; `open` gives the URL with the workspace's token;
  the setup container is left as it is (the internet directly, design 0004 §10). Tests: `test_sandbox.py`.
- [x] 5. **The allowances**: `Workspace.hosts: dict[str, str]` (each host with when and how it was allowed; the
  schemas regenerated); `Workspaces.allow_host(name, host, allow, *, actor)` writes the record and records
  `workspaces.host_allowed`; `POST /workspaces/{name}/hosts` (`{"host", "allow"}`); `clank workspace allow FOLDER
  --host NAME` and `--no-host NAME`; the view's `hosts`. Tests: `test_workspace_commands.py`.
- [x] 6. **Docs and the live check**: design 0024 §1, §2, §7 and §8 step 1 built; decision 0141 built at step 1;
  `docs/EVENTS.md`, `docs/API.md`, the schemas, the code map and the tests page; getting started: how to let the
  agent reach a host; the roadmap (M7) and the plan index. Live: the service restarted, the edge made again, a
  `curl` from the throwaway workspace's container to a host allowed (200) and one not (403 with the words).

## Progress

Written 2026-10-26, after design 0023's steps 1 to 3 were built.

- All six tasks built 2026-10-26. Live on the owner's machine (the service and the gateway restarted, the edge made
  again with both ports, the throwaway workspace's container made again and told the proxy): a plain request to a
  host not allowed answered 403 with the words, a `CONNECT` to one refused (curl: "CONNECT tunnel failed, response
  403"), `host.docker.internal` refused as private, the gateway still reached through the edge without the proxy;
  `clank workspace allow FOLDER --host pypi.org --host files.pythonhosted.org`, then `https://pypi.org/simple/six/`
  answered 200 in 116 ms and `pip download six` came through the proxy; the day's log held each exchange with its
  status and bytes. Found on the way: the Docker adapter read only the three labels it knew, so the edge's `clank.ports`
  came back empty and the edge was made again at every open (the labels are read back now); a workspace's container
  made before the proxy is made again when stopped and opened (its label `clank.proxy`), since the environment is
  the container's; a taken proxy port no longer stops the gateway (said in its log). The owner's workspaces made
  before get the proxy when next stopped and opened.
