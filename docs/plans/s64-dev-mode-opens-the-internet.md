# Plan s64: dev mode opens the agent's internet

Decision 0152, the owner's request of 2026-10-29: "the model is having trouble doing the benchmark that I have assigned
it because it has no ability to git clone and the network is blocked. In dev mode, these types of restrictions should
be completely lifted." Design 0024 §1, §3, §4, §6 and §7 and design 0016 §4, §15 and §16 are revised after approval
with it. Dev mode (decision 0149) asked every cloud provider for any of a model's providers; it now also lets every
workspace's agent reach every public host at once, without a question, and lets OpenCode fetch and search the web.
Private addresses stay refused.

## What exists

- The proxy (`gateway/proxy.py`, `Proxy._admitted`): a host in the workspace's allowances goes out; any other is held
  up to `HOLD_SECONDS` (60) while the service asks the owner (`workspaces/network.py`, `HostAsks`), refused 403 when
  not allowed, and not asked for again for `QUIET_MINUTES` (10). Private addresses are refused before resolving and
  after, whatever the allowances.
- The allowances reach the gateway's process with the routes it asks the service for every second (`Gateway.routes`
  and `network_routes`; `Routes.hosts_of`, which `main` hands the proxy).
- Dev mode: `runtime.json`'s `dev_mode` (`RuntimeSettings`), `Endpoints.dev_mode` and `set_dev`, `GET` and
  `PUT /runtime/dev`, `clank dev`, the Providers page's `D`, the header's pill (read from each provider's view, so
  shown only once a provider is added), `DEV_SAID`.
- OpenCode's configuration denies `webfetch` and `websearch` (`OpenCode.configuration`). It is written with Clank's
  files for the agent at each start of OpenCode in a folder (`Agents.prepare` and `configure`, `agent_files`), the
  network instructions (`image/instructions/network.md`) among them.

## What happened

The owner gave the agent a benchmark that clones a repository. `git clone` reached a host the workspace had not
allowed; the proxy held it while the console asked; the owner was in OpenCode's window and never saw the question; the
clone failed with 403.

## Choices made here

- **Dev mode is the one switch** (decision 0152): no second setting. The proxy follows it with the routes, as the
  gateway follows the data policy: `dev_mode` beside the allowances, read every second.
- **Private addresses stay refused**, before resolving and after: dev mode opens the internet, never this machine, the
  local networks or the tailnet, which keeps the agent from Clank's own service and the owner's network.
- **The log says why**: an exchange dev mode let out (a host not in the workspace's allowances) is logged with why
  `dev mode`; one to a host allowed is logged as before; host, bytes and time as always.
- **From the next connection**: turning dev mode on lets the next connection out, and one held while the owner is
  asked at once; turning it off applies to the next connection, one already open finishing.
- **The instructions are one file, written as dev mode says**: `network.md` is written with the dev mode rules in
  place of its first part (`instructions/dev/network.md`), so turning dev mode off leaves nothing behind. A change of
  dev mode writes it again in every running workspace's container at once; an agent's start writes it as dev mode says
  then; both under one lock, so neither can leave the other's words.
- **OpenCode's web tools** are allowed in the configuration written at OpenCode's next start in a folder; a window
  already open keeps what it started with until it starts again.
- **The pill shows whatever providers exist**: the console reads dev mode itself (`GET /runtime/dev`, a topic of its
  own), so dev mode with a local model only is shown too; `D` turns it on or off without a provider.

## Tasks

- [x] 1. **The proxy in dev mode** (`gateway/proxy.py`, `routing.py`, `server.py`, `service.py`): `Proxy(dev_mode=)`,
  a callable; while it says on, a public host not allowed is let out at once, logged why `dev mode`, never asked for;
  a connection held while the owner is asked is let out once dev mode is turned on; private addresses refused as
  before; the routes carry `dev_mode` (`Gateway.routes`, the runtime's setting), `Routes.dev_mode()`, `main` hands it
  to the proxy. Tests with a fake upstream and a flag (`test_proxy_dev_mode.py`), the service's routes
  (`test_service.py`).
- [x] 2. **OpenCode may fetch and search** (`agents/adapters/program.py`, `opencode.py`, `agents/service.py`):
  `configuration(web=)`, `webfetch` and `websearch` allowed with it; `prepare` and `configure` pass dev mode. Tests
  in `test_dev_mode_agent.py`.
- [x] 3. **The agent is told** (`workspaces/image/instructions/dev/network.md`, `workspaces/sandbox.py`,
  `workspaces/service.py`, `agents/service.py`): `network_instructions(dev_mode)`, `agent_files(dev_mode=)`,
  `network_file`; `prepare` and `configure` write them as dev mode says, under the lock; a change of dev mode writes
  them again in every running container (`Agents.tell_network`, heard from `settings.changed`, off the thread that
  changed it). Tests in `test_dev_mode_agent.py`, with the fake platform's files.
- [x] 4. **Every description of dev mode** (`runtime/guide.py`'s `DEV_SAID`, `devcli.py`, `endpoint_routes.py`,
  `kinds.py`, `console/header.py`, `console/data.py`, `runtime/console/providers.py`, `agents/console/folder.py`): the
  pill "dev mode: any provider, any host" ("dev mode" when narrow, before the other pills go short), shown whatever
  providers exist; `D` asked first in words that say both halves and when each applies, without a provider too;
  `clank dev` in the service's words; This folder's hosts line says every public host while dev mode is on (design
  0024 §4, revised with it). Tests: `test_dev_mode_console.py`, `test_data.py`, `test_dev_command.py`,
  `test_dev_mode.py`.
- [x] 5. **Records and docs**: decision 0152 and the index (0141's and 0149's lines), 0149's status; design 0024 §1,
  §3, §4, §6, §7 and design 0016 §4, §15, §16 revised, with their revision logs and the designs' index; getting started,
  `docs/console.md`, the glossary and `SECURITY.md`; the generated pages (the API page, the settings schema, the
  extension's types, the code map, the tests page).

## Progress

Written 2026-10-30, from the owner's request of 2026-10-29.

- All five tasks built 2026-10-30, each task's tests written before its code (those of tasks 1 to 3 and of This
  folder's line seen to fail first). The race the lock guards was checked the other way too: with `tell_network`
  writing without the lock, the test that turns dev mode off in the middle of an agent's start found dev mode's words
  left in the container.
- Two more places said what dev mode no longer is, and say it now: This folder's hosts line said "none" while every
  public host answered (design 0024 §4 revised with it), and the header's pill showed only once a cloud provider was
  added, though dev mode now matters with a local model too (the console reads `GET /runtime/dev` itself). At 120
  columns with every part running, the header has no room for the pill's whole words, as it had none for the old
  ones: dev mode's go short ("dev mode") before the other pills'.
- Not tried live: this was built in a worktree, away from the owner's service, home and containers. To check on the
  owner's machine, with the gateway restarted so the new proxy runs (the service adopts a running gateway, and one
  started before this keeps the old proxy): `clank dev on`; from a running workspace's container, `git clone` of a
  host the workspace was never allowed goes through at once and `clank network log` says `dev mode`; a `curl` to the
  computer's own address or `host.docker.internal` is still refused; `~/.clank/instructions/network.md` in the
  container says dev mode, and no longer once `clank dev off`; OpenCode started again has `webfetch` and `websearch`.
- Still to see with the image's OpenCode (1.19.4): whether it offers `websearch` with Clank's provider at all, since
  OpenCode may give that tool only with some providers.
