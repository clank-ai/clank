# Plan s56: network access for the agent, step 4: what the owner sees

Design 0024 §4 (and §8 step 4), decision 0141, approved 2026-10-26, on the proxy, the ask and the sets
([plans s53](s53-the-proxy.md), [s54](s54-the-ask.md), [s55](s55-the-named-sets.md)): every exchange the agent makes
is visible, as everything Clank does is: in the console's Requests page beside the model's requests, from the command
line, and on This folder, where the hosts are allowed and taken back with one key. The Monitor's "fetching" line
comes with the Monitor's move to the stream (design 0023 step 4), which changes the Now panel anyway.

## What exists

- The network log (`logs/network/<day>.jsonl`, one line an exchange: time, workspace, host, port, method, path,
  status, bytes, seconds, why) written by the gateway's process; the traffic log's readers (`records.recent`,
  `_newest_first`) as the pattern for reading a day's files from their ends.
- The allowances per workspace (`Workspace.hosts`, the sets, `POST /workspaces/{name}/hosts`, `/sets`); the routes
  carry them to the gateway (`network_routes`).
- This folder (`agents/console/folder.py`): the steps, the software line, the MCP servers' lines with `m` (a
  `PickScreen`), the forms (`FormScreen`); its frames in `tests/console/snapshots`.
- Requests · F7 (`gateway/console/requests.py`): the model's requests as the gateway recorded them.

## Choices made here

- **The service reads the log** (`GET /gateway/network/log?limit=&workspace=`, `GET /gateway/network/hosts`): the
  gateway's process writes it, the service's routes read it from the files' ends, as the traffic log is read; no new
  channel.
- **`clank network log` and `clank network hosts`** are the gateway component's commands (the proxy is its part).
- **This folder's line** stands under the MCP servers: "Hosts its agent reaches: none (h: a set, or a host)" or the
  hosts allowed; `h` opens a picker of the sets (each allowed or not, with what it opens) and "a host by name", which
  takes a form; picking a set allowed takes it back.
- **Requests · F7's Network view** is a second view of the page (`n`): the newest exchanges first, one line each
  (when, workspace, host, status, bytes each way, time, why), the day's bytes by host under them, and the hosts allowed
  per workspace.

## Tasks

- [ ] 1. **The routes and the commands**: `NetworkLog.recent(folder, limit, workspace)` and `by_host(folder, day)` in
  `gateway/proxy.py`; `Gateway.network_log`, `network_hosts` in the gateway's service; the routes; `clank network log
  [--limit N] [--workspace NAME] [--json]` and `clank network hosts [--json]`. Tests over the service's test client
  with a log written by the tests (`test_network_views.py`).
- [ ] 2. **This folder's hosts** (`agents/console/folder.py`): the line, the `h` key, the picker and the form; the
  page's help and keys bar; the snapshots rewritten and read. Console tests drive `h`.
- [ ] 3. **Requests · F7's Network view** (`gateway/console/requests.py`): the `n` view with its lines, the day's bytes
  by host, the hosts per workspace; its snapshot.
- [ ] 4. **Docs**: design 0024 §4 built (the Monitor's line deferred to design 0023 step 4, said there); the console
  page (`docs/console.md`); the roadmap, the plan index, the generated pages.

## Progress

Written 2026-10-26, after steps 1 to 3 and 5 were built.
