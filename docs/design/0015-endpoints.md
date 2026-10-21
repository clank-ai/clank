# Design 0015: endpoints, models Clank did not start

Roadmap parts 1 (the runtime: providers, presets, slots) and 2 (the gateway). Started 2026-10-18. Design
[0001](0001-runtime-and-console.md) approved endpoints with the rest of the runtime (§1-§3, §4.2, §4.4, §5.3,
§6.1-§6.5, §7.3, §7.6, §8.2), and design [0002](0002-the-foundation.md) the policy and the secrets they need
(§2.6-§2.8). Endpoints are not built: a preset must name an engine (`runtime/kinds.py:37-38`), the gateway forwards
only to an engine on this machine (`gateway/server.py:207, 217`), and `docs/TESTS.md` lists no test for design 0001
§7.6. This design says how endpoints are built, and where it refines or reverses those sections. Decisions it rests
on: [0006](../decisions/0006-runtime-service-with-adapters.md),
[0007](../decisions/0007-settings-in-readable-files.md),
[0008](../decisions/0008-role-is-the-requested-model-name.md),
[0010](../decisions/0010-serving-setups-are-plug-and-play.md),
[0013](../decisions/0013-one-service-control-and-data-planes.md),
[0014](../decisions/0014-state-in-sqlite-settings-in-files.md),
[0019](../decisions/0019-components-use-declared-public-functions.md),
[0020](../decisions/0020-enforce-where-it-can-be-stopped.md), [0021](../decisions/0021-policy-decisions-expire.md),
[0026](../decisions/0026-httpx2-replaces-httpx.md), [0030](../decisions/0030-engines-run-on-hosts.md); it adds
[0072](../decisions/0072-the-tunnel-is-openssh-with-a-config-clank-writes.md) to
[0077](../decisions/0077-an-endpoint-serves-the-main-slot.md).

## Goal

The owner's plan of 2026-10-18 runs Clank on a Raspberry Pi 5 with the agent's model served elsewhere: most likely by
vLLM (T0 says, §15), in a job on a cluster the owner has access to, reached through the cluster's login host, and from
outside its network through its jump host as well. The Pi itself (Docker Engine, the edge's way to the gateway on Linux)
is [design 0014](0014-linux-and-small-machines.md)'s; the model is this one's. The same parts serve this PC, a server on
the owner's network, and later a hosted API with a key.

A citation like `gateway/server.py:217` names `clank/components/gateway/server.py`, line 217, and one like
`kernel/api.py:55` names `clank/kernel/api.py`, both at commit e90c51a; other paths start at the repository's root.
Host names, user names, node names, job ids, model ids and keys here are made up (`login.example.org`,
`bastion.example.org`, `compute-node:8000`, `you`, `123456`, `example-org/example-coder`); the real ones live only in
the owner's `CLANK_HOME`, never in the repository.

**Status:** written 2026-10-18 by Claude, from the researched plan of that day, and revised on 2026-10-19 after its
review (the revision log says what changed); every section *proposed*. Decisions 0073 (how the gateway gets an
endpoint's key), 0075 (where a workspace's requests may go, and whether research content and Notion pages may go to the
remote server) and 0077 (an endpoint serves the main slot in an engine's place, or a slot of its own) are the
owner's to choose; §6, §9 and §10 are written for the recommended options and say what the others change. The dry run
T0 (§15) needs no code: its answers (the server's program, its fields, whether a key alone logs in, whether the
owner's node can be logged in to) may revise §3, §5 and §8 before they are built.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets, and what this design refines | Proposed 2026-10-18 |
| 2 | The endpoint record | Proposed 2026-10-18 |
| 3 | The endpoint adapter | Proposed 2026-10-18 |
| 4 | Presets name an engine or an endpoint | Proposed 2026-10-18 |
| 5 | The tunnel | Proposed 2026-10-18 (decision 0072) |
| 6 | A slot runs an endpoint | Proposed 2026-10-18; which slot is the owner's choice (decision 0077) |
| 7 | The watcher keeps the tunnel open | Proposed 2026-10-18 |
| 8 | The gateway forwards to an endpoint | Proposed 2026-10-18 (decision 0074) |
| 9 | Keys | Proposed 2026-10-18; how the gateway gets a key is the owner's choice (decision 0073) |
| 10 | Where a workspace's requests may go | Proposed 2026-10-18; the owner chooses (decision 0075) |
| 11 | The check | Proposed 2026-10-18 (decision 0076) |
| 12 | The commands, the console and VS Code | Proposed 2026-10-18 |
| 13 | `clank work`, `clank code` and the folder page | Proposed 2026-10-18 |
| 14 | Recordings, fakes and the capture tool | Proposed 2026-10-18 |
| 15 | Dry runs T0-T5 | Proposed 2026-10-18 |
| 16 | Build steps | Proposed 2026-10-18 |
| 17 | What this design does not cover | Proposed 2026-10-18 |

## 1. What the owner gets, and what this design refines

*Proposed 2026-10-18.*

The owner can:

- **add an endpoint**: a server reached at a URL, or through an SSH tunnel Clank opens (the login host, the jump host,
  the job's node and port), with its key kept by Clank;
- **check it**: ssh, the login, the server's models and context, tool calls, and how it streams its thinking;
- **trust it**: Clank refuses a server that does not hold the endpoint's key, so a job that ended and a stranger's
  server on the same port are told apart (§6);
- **load it**: write a preset for one of its models and load it into the main slot like any preset, and switch back to
  a model on this machine;
- **work with it**: `clank work`, `clank code` and the folder page use it;
- **keep each workspace's content where it belongs**: on this machine only, until the owner widens that workspace.

What this design changes in approved text:

| Approved | It says | This design | Where |
| --- | --- | --- | --- |
| 0001 §1 | "Endpoints and CPU engines run alongside" the engines that share the GPU | Reversed for serving: an endpoint serves the main slot in an engine's place, one provider at a time (decision 0077); `fast` and `vision` stay on this machine | §6 |
| 0001 §2 | An endpoint adapter: the connection, its authentication, an optional tunnel through a login host; the models and limits it reports | The record (§2), the `openai-compatible` adapter (§3), a jump host for the tunnel, and a tunnel that may end at the node (§5); measuring its speed waits for M2's suites | §2, §3, §5 |
| 0001 §3.4, §3.7 | A preset for an endpoint names `endpoint` instead of `engine` | As written; its `model` is the id the server lists; `config/endpoints/` joins the files | §2, §4 |
| 0001 §3.8 | A check "starts nothing"; a trial of a candidate that fits beside the live model, an endpoint included, "runs alongside it" | An endpoint's check connects (decision 0076). An endpoint's trial still runs alongside, on a tunnel of its own as the check's, when M2 builds trials | §11 |
| 0001 §4.2 | A switch disconnects an endpoint and closes its tunnel | An endpoint's plan is a connection plan; its start opens the tunnel | §6 |
| 0001 §4.4 | Network errors retried with backoff; a 401 or 429 shown as what it is; a dropped tunnel reopened, and shown | As written; an engine's crash rule never applies to a tunnel, and a request a silent server never answered is never sent again | §7, §8 |
| 0001 §5.3 | The providers screen shows endpoints, their health, whether a key is set | Also their reach, their tunnel, their last check, and whether they are insecure | §12 |
| 0001 §6.1 | Step 6 attaches an endpoint's key and an open tunnel | The tunnel is the slot's, opened once by the runtime; the key reaches the gateway by decision 0073 | §5, §9 |
| 0001 §6.2-§6.3 | Dialects; each setup's request fields | One dialect, Chat Completions; an endpoint gets the request as the tool sent it, but its model name | §3, §8 |
| 0001 §6.4-§6.5 | Holds; records that never keep a key | Requests wait while a tunnel reopens; a key a server echoes back is removed too | §7, §8 |
| 0001 §7.3, §7.6 | The guide's "On another computer"; a cluster behind SSH; keys in `secrets/`; a key tested with a few tokens | Commands now, the guide in M10; the tunnel; the check | §5, §11, §12 |
| 0001 §8.2 | One contract test per kind of adapter, on recordings of the real program | `tests/contract/test_endpoint.py` on HTTP recordings (`http.json`, which the repository's checks learn to accept), and a capture tool in place of §8.3's `clank dev capture` | §14 |
| 0002 §2.6 | `model.send`, workspace bounds, checked by the gateway per request | A bound per workspace, and a key per workspace so the gateway can tell them apart (decision 0075) | §10 |
| 0002 §2.7 | Data-plane processes get `process` access: "report events, ask for policy decisions, read its own configuration"; an agent's session is named by its edge | `process` access also reads the key of an endpoint a slot runs (decision 0073); a workspace is named by its key, since one edge serves every workspace | §9, §10 |
| 0002 §2.8 | Secrets through the kernel, never in a sandbox; their values removed from everything written | Endpoint keys (decision 0073). A workspace's key enters its own container only; the gateway, which knows it only by its hash, cannot remove it from what that workspace's agent sends (decision 0075) | §8, §9, §10 |
| 0002 §2.13 | Each component declares the outside hosts Clank contacts for it | An endpoint's hosts are the owner's, named in its record: the runtime declares that kind of host, and the Providers page lists the owner's own | §2 |
| 0010 §3 | The gateway forwards the agent's Notion requests to the service | Only a request that carries a known workspace key; under decision 0075's recommended answer, only one whose bound is this machine. The key names the workspace, which `CLANK_WORKSPACE_NAME` only claims | §10 |
| Decision 0021 | `secret.use` is decided at the moment of use | For an endpoint's key, the moment of use is the launch the owner started (decision 0073 refines 0021) | §9 |

## 2. The endpoint record

*Proposed 2026-10-18.*

A settings kind of the runtime component, `endpoint` (decision 0007): one file per endpoint,
`CLANK_HOME/config/endpoints/<id>.json`, its id the name the owner gives it. Clank ships none.

| Field | Holds |
| --- | --- |
| `title` | Its name in every client |
| `adapter` | Its kind of endpoint (§3): `openai-compatible` |
| `url` | The server's API, reached directly (`https://models.example.org/v1`); empty for a tunnel |
| `tunnel` | Or the tunnel Clank opens (§5): `login` and `jump` (`<user>@<host>`, with `:<port>` when not 22; `jump` empty when none), `remote` (`<node>:<port>`), `ends_at` (`login`, the cluster's own recipe, or `node`), `job` (the scheduler's job id, when there is one), `path` (`/v1`), and, when wanted, `identity_file` and `ssh` (the program) |
| `auth` | `none`, or `bearer`: a key, kept in `secrets/` (§9) |
| `reach` | Where content sent to it goes (§10): `this-machine`, `my-servers` or `hosted`; read as `hosted` when missing, so nothing passes a bound by default |
| `insecure` | `false`. `true` lets this endpoint run without a key beyond this machine, or over plain `http://` beyond the loopback; every check flags it (§11) |
| `timeout_seconds` | The longest the gateway waits for the next piece of an answer, or for a whole answer that is not streamed (§8); 600 |
| `notes` | Anything worth knowing |

Each rule below is refused with the file, line and field (design 0002 §2.2):

- A `url` or a `tunnel`, never both and never neither.
- A tunnel's reach is never `this-machine`, nor is the reach of a URL whose host is not this machine's loopback. A URL
  on the loopback may have any reach, since a tunnel the owner opened by hand looks like a local server (§5): the owner
  says which.
- **A key beyond this machine.** An endpoint whose reach is not `this-machine` has `auth: bearer`, unless `insecure`
  is set. Without a key, any program that reaches the server can use it, and Clank cannot tell the owner's server from
  another one at the same address (§6).
- **Encrypted beyond the loopback.** A `url` to any host but the loopback is `https://`, unless `insecure` is set:
  over `http://`, the key and every prompt would cross the network in clear (a shared Wi-Fi included). Certificates are
  always verified, as httpx2 verifies them by default; no setting turns that off. A server whose certificate this
  machine does not trust is reached through a tunnel instead.
- `insecure` is a field like any other: its change is recorded with who made it (design 0002 §2.2), and every check
  and the Providers page flag it (§11, §12).

An example, `CLANK_HOME/config/endpoints/hpc.json`:

```json
{
  "schema": "endpoint/1",
  "title": "remote cluster",
  "adapter": "openai-compatible",
  "tunnel": {
    "login": "you@login.example.org",
    "jump": "you@bastion.example.org",
    "remote": "compute-node:8000",
    "job": "123456"
  },
  "auth": "bearer",
  "reach": "my-servers",
  "notes": "Each vLLM job has its own node, port and id: clank endpoint set hpc --remote NODE:PORT --job JOB."
}
```

- **When a change applies.** Its `reach` applies to the next request (§6, §10); any other change at the tunnel's next
  start (`ON_CHANGE`, design 0002 §2.2), and `clank endpoint set` reopens a tunnel a slot runs (§12). An endpoint that
  a slot runs or a preset names is not removed: the refusal names them.
- **Outside hosts** (design 0002 §2.13, not built yet). An endpoint's hosts are the owner's, so the runtime declares
  them as a kind, "the hosts each endpoint record names", instead of a list; the Providers page lists the owner's own
  (§12). The gateway contacts a URL endpoint's host; `ssh` contacts a tunnel's.

## 3. The endpoint adapter

*Proposed 2026-10-18.*

A new kind of adapter of the runtime component, `endpoint` (design 0002 §2.10), beside `engine` and `host`: one module
per kind of endpoint. The first, `openai-compatible`, serves any server that speaks OpenAI's Chat Completions: vLLM,
SGLang, llama.cpp's `llama-server`, a hosted API. Its interface:

- `options()`: an endpoint preset's options (§4): `context` (at most the server's), `max_output` (8,192 unless set,
  the agent's fallback today, `agents/service.py:59`), and `images` (whether the model reads images; off).
- `models(answer)`: from `GET <base>/models`, each model's id exactly as the server lists it, and its context. vLLM and
  SGLang give `max_model_len`, llama.cpp a figure under `meta` (the research of 2026-10-18); the first recordings
  (§14) confirm each field before the adapter reads it. When a server gives none, the preset's `context` says it.
- `translate(body)`: the request as the tool sent it, but its model name (§8). Fields of its own (design 0001 §6.3)
  are declared once a recording shows them; none at first.
- `headers(key)`: `Authorization: Bearer <key>` for `bearer`, nothing for `none`.
- `refusal(status, headers, body)`: what a refused request means, in words that say what to do: 401 (the key was
  refused: `clank endpoint key`), 403, 404 (no such model: the ids the server lists), 429 (a limit, until its
  `Retry-After`), and a 400 that names vLLM's tool-call flags (§11).
- `capabilities()`: what its recorded servers support: tool calls, the field their thinking streams in, usage at the
  end of a stream. Never `/infill`: completion stays on this machine (design 0006).

Its contract test is `tests/contract/test_endpoint.py`, run against every HTTP recording of every endpoint adapter
(§14), as the engines' runs against theirs (design 0001 §8.2).

## 4. Presets name an engine or an endpoint

*Proposed 2026-10-18.*

Design 0001 §3.7 already says that "a preset for an endpoint names `endpoint` instead of `engine`". Today `engine` and
`engine_version` are required (`runtime/kinds.py:37-38`); they become optional, beside a new `endpoint`:

- An **engine preset** names `engine` and `engine_version`, and may name `host`; its `model` is the catalog's id.
  Unchanged.
- An **endpoint preset** names `endpoint`; its `model` is the id its server lists, sent exactly as listed; its options
  are its adapter's (§3); its slot is `main` (§6, decision 0077).
- Never both, never neither; refused with the file, line and field.

```json
{
  "schema": "preset/1",
  "title": "cluster coder",
  "endpoint": "hpc",
  "model": "example-org/example-coder",
  "options": { "context": 131072 },
  "notes": "Written by clank endpoint preset."
}
```

- **Every preset written before reads the same.** The schema stays `preset/1`: only optional fields are added.
- **One line for the provider.** Each preset as clients see it gains `provider`: `kvmem-llamacpp v0.16.0-rc1`, or
  `endpoint hpc`. The preset picker (`clank/console/pick.py:29`), the Presets and Models pages
  (`runtime/console/presets.py:42`, `runtime/console/models.py:47`), `clank preset list` and `show`
  (`runtime/cli.py:178, 195`) and VS Code (`vscode/src/core/controller.ts:429`) print it instead of the engine's
  fields.
- **Every reader of a preset's engine handles an endpoint preset**: its problems (`runtime/catalog.py:107-119`: the
  endpoint exists, its options are valid), its route (`runtime/service.py:81-108`), its plan
  (`runtime/launching.py:151-181`, §6), what it needs (`runtime/service.py:155-204`: nothing to install or download)
  and its check (§11).
- **The model name is the server's.** The runtime's `model_name` setting (`runtime/kinds.py:109-116`) renames the
  model for engines only; it never replaces an endpoint's model id, as `runtime/service.py:104` would today.

## 5. The tunnel

*Proposed 2026-10-18 (decision 0072).*

The cluster's own documentation gives the tunnel: `ssh -NL <local port>:<node>:<port> <user>@<login host>`, with `-J
<user>@<jump host>` added from outside the cluster's network. Clank opens the same tunnel, unattended, with the owner's
own OpenSSH and a file it writes (decision 0072):

```
ssh -F CLANK_HOME/state/tunnels/hpc.conf -N -T -L 127.0.0.1:18200:compute-node:8000 clank-hpc
```

```
# Written by Clank from config/endpoints/hpc.json at each start of its tunnel: change the endpoint, not this file.
Host clank-hpc
    HostName login.example.org
    User you
    ProxyCommand "<ssh's full path>" -F "<CLANK_HOME>/state/tunnels/hpc.conf" -W [%h]:%p clank-hpc-jump
Host clank-hpc-jump
    HostName bastion.example.org
    User you
Host clank-hpc clank-hpc-jump
    BatchMode yes
    ConnectTimeout 10
    ServerAliveInterval 15
    ServerAliveCountMax 3
    StrictHostKeyChecking yes
    UpdateHostKeys no
    ExitOnForwardFailure yes
```

- **Unattended, on both hosts.** `BatchMode yes`: ssh never prompts, so a login that wants a password or a second
  factor is refused at once, and said. Options given with `-o` apply to the destination alone (ssh(1), at `-J`), so
  nothing is given that way: the jump is a second `ssh` that the file names in `ProxyCommand`, with the same `-F` file,
  so its `Host` block applies there too.
- **Quoted by Clank.** `ProxyCommand` runs the same `ssh` by its full path. On Linux and macOS ssh hands it to a shell,
  so Clank quotes the program's path and the file's path for it, and doubles each `%` (ssh's own tokens); a path it
  cannot quote (one holding a quote) is refused, saying so. A `CLANK_HOME` or an `ssh` path with a space, common on
  Windows, works. How Windows' own OpenSSH runs the line is measured in T1 (§15).
- **No `known_hosts` written.** `UpdateHostKeys no`: from OpenSSH 8.5, ssh may otherwise add a host's other keys to
  the owner's `known_hosts` (ssh_config(5)).
- **The slot's own port, on the loopback.** The tunnel listens on `127.0.0.1` at the slot's port (main: 18200,
  `runtime/kinds.py:97-108`), where an engine would: the gateway reaches an endpoint through a tunnel as it reaches an
  engine (§8). No other computer can use it. Any program on this machine can, as it can use an engine. On Docker
  Desktop that includes a container that reaches `host.docker.internal`, which is how the edge reaches the gateway,
  itself listening on the loopback only (`workspaces/sandbox.py:168`, `gateway/server.py:611`). A workspace's setup
  container can (it runs on Docker's default network, `workspaces/sandbox.py:132-151`), and the gateway's bound check
  (§10) never sees it. The server's key, which no container holds, is what stops such a program: one more reason a
  server beyond this machine needs one (§2).
- **Where the tunnel ends** (`ends_at`). `login` is the cluster's recipe: the login host connects to the node's port,
  so the server listens for other computers on the cluster's network, and the traffic is encrypted only as far as the
  login host. `node`, where the cluster lets the owner log in to the node that runs their own job (T0's step 2b, §15):
  ssh logs in to the node itself, through the login host (a third block, `clank-hpc-node`, whose `ProxyCommand` names
  `clank-hpc`), and forwards to the node's own loopback (`-L 127.0.0.1:18200:127.0.0.1:8000 clank-hpc-node`). The
  server then listens on `127.0.0.1` only (vLLM's `--host 127.0.0.1`), the traffic is encrypted all the way to the
  node, and the node's host key proves which machine answers. Where the cluster lets only a job's owner log in to its
  node, and ends those logins with the job (as Slurm's `pam_slurm_adopt` does), a tunnel to a node whose job has ended
  cannot open. Recommended whenever T0's step 2b passes.
- **The job, confirmed before each open** (when `job` is set). Before the tunnel opens, and before each reopen (§7),
  Clank asks the scheduler through the login host (`ssh -F <file> clank-hpc squeue --noheader --jobs <job> --format
  "%T %N %L"`). The job must be running on the endpoint's node, or the open is refused: its job has ended or moved
  (`clank endpoint set`). The time it has left ends the slot when it runs out (§7), so nothing is sent to that node and
  port after the job's end. A job that ends sooner (canceled, or its server crashed) shows as refused connections and
  missed health checks (§6, §7).
- **A process of the local host** (design 0003 §2): started without a window, in a session of its own, its output in
  `logs/processes/<slot>-<launch>.log`, known by its identity and adopted after a restart of the service
  (`runtime/hosts/local.py:48-102`, `runtime/watching.py:61-89`).
- **The agent is the service's.** The service's environment reaches the tunnel (`runtime/hosts/local.py:56`), an SSH
  agent's socket (`SSH_AUTH_SOCK`) included; Windows' own OpenSSH finds its agent, a service of Windows, without one.
  So the agent is the one of the shell that started the service: `clank work` and `clank console` start it from the
  shell they run in when it does not run (`agents/cli.py:80-90`, `kernel/service.py:252`), and a service started from
  an SSH session with a forwarded agent loses that agent when the session ends. The check says whether the service's
  agent is alive (§11), and a refused login says what to do (below).
- **The owner's keys, agent and `known_hosts`, as ssh uses them.** Clank adds no key, never writes `known_hosts`, and
  never turns host key checking off. `identity_file` names a key when the owner wants one (`IdentityFile`, with
  `IdentitiesOnly yes`); otherwise ssh's defaults and the agent decide. The file holds user and host names, no
  secret, and only the owner may read or change it.
- **Which `ssh`.** The first on the PATH, or the program `tunnel.ssh` names, run by its full path; the check prints
  that path and its `ssh -V` (§11). Inside Clank the program is a list of arguments, as an install's is
  (`runtime/state.py:128`), so the tests run `[python, tests/fakes/ssh.py]` on every system, as the fake engine runs
  (`tests/fakes/engine.py:48-50`). This design is written for the OpenSSH versions recorded (§14: Windows' own and the
  Pi's); the check names the version in use, and says when it is older than the oldest recorded.
- **A port held for a moment.** On Windows, WSL's relay can hold a port for about a second after an engine in WSL
  stops (`runtime/slots.py:199-209`): a tunnel's start waits up to ten seconds for the port to be free.

**What ssh says, and what Clank says.** ssh's own words, as the versions recorded write them (§14), become what to do.
ssh names the host it could not reach (`ssh: connect to host bastion.example.org port 22: Connection timed out`), the
jump's words come before the login host's, and Clank reads the first line that matches:

| ssh says | Clank says | Tried again |
| --- | --- | --- |
| `Permission denied (...)`, its list naming `publickey` | The host refused every key ssh offered: load your key into the agent the service has (`ssh-add`), name it (`identity_file`), or register it with the cluster. When the list also names `password` or `keyboard-interactive`, the host may want a password instead, which an unattended tunnel cannot give: open the tunnel yourself (below). When the service's agent is gone (§11): "the agent the service started with is gone: start the service again from a shell with your agent, or name an `identity_file`" | No |
| `Permission denied (...)`, its list without `publickey` | The key was accepted, and the host wants a password or a second factor too, which an unattended tunnel cannot give: open the tunnel yourself (below) | No |
| `Host key verification failed` | This computer does not know the host's key, or the key changed: connect once yourself, and compare its fingerprint with the one the cluster publishes | No |
| `Could not resolve hostname` | The name was not found: check the network (a guest network may want its sign-in page first), or the name | Yes |
| `Network is unreachable` | This computer has no network: check its Wi-Fi or its cable | Yes |
| `Connection timed out`, no jump host set | The login host does not answer from this network: from outside the cluster's network, add the jump host (`clank endpoint set hpc --jump you@bastion.example.org`) | Yes |
| `Connection timed out` with a jump host set, or `No route to host` | This network reaches neither host (ssh names which), and may block SSH: try another network or a wired jack | Yes |
| `Connection refused`, at port 22 | The host named refuses SSH on that port: check the host and the port; a network that blocks SSH can answer so too | Yes |
| `kex_exchange_identification: Connection closed by remote host`, or `Connection reset by peer` | Something between this computer and the host closed the connection before SSH began, as a guest or shared network's sign-in page or filter often does: sign in to the network, or try another network or a wired jack | Yes |
| `Address already in use` | Another program holds the slot's port: it is named, and never stopped | No |
| `open failed: connect failed: Connection refused` | The server at `compute-node:8000` refused: its job may have ended or moved (`clank endpoint set hpc --remote NODE:PORT --job JOB`), or its server is still loading its model | §6, §7 |

"Tried again" is the watcher's reopening, with backoff (§7); a load is tried once and says what happened (§6).

**Jobs move.** The cluster's jobs end within a time limit (72 hours on a typical cluster), and a new job can land on
another node and port. `clank endpoint set hpc --remote NODE:PORT --job JOB` gives the endpoint the new ones, and
reopens the tunnel when a slot runs it. Starting a server through the scheduler comes later (design 0001 §7.6).

**When the login cannot be unattended** (T0's first step says so): the owner opens the tunnel by hand, on a port of
their choice (`ssh -N -L 127.0.0.1:18300:compute-node:8000 ...`), and the endpoint is the URL
`http://127.0.0.1:18300/v1`, with the reach `my-servers` and its key, as for any server beyond this machine (§2). Clank
connects to it like any URL endpoint; it can neither reopen it nor close it, and says so when it stops answering (§7).

## 6. A slot runs an endpoint

*Proposed 2026-10-18; which slot is the owner's choice (decision 0077).*

Loading, unloading and switching keep their operations and their steps (design 0003 §6.1, design 0001 §4.2), so every
client follows an endpoint as it follows an engine:

| Step | An engine, today | An endpoint |
| --- | --- | --- |
| plan | The launch: its command line, its memory, its fit (`runtime/launching.py:151-181`) | The connection: the endpoint, the base URL, the model id, the tunnel's command line and file, whether a key is needed and set. No install, catalog or GPU is read; for a tunnel, the slot's port must be free, as for an engine |
| start | The engine started on its host | For a tunnel with a `job`, the scheduler confirms it first (§5); then the tunnel opens. For a URL endpoint nothing starts, and the step says so |
| health | Its log says it is ready, its API lists a model, a tiny request comes back (`runtime/slots.py:288-322, 395-408`), with no key | The server shows it holds the endpoint's key and serves the preset's model (below), then the same tiny request (`runtime/slots.py:49`) comes back, for that model, with the key |
| measure | The GPU memory it took | The server's context for the model, and the time it took; no GPU |

**Health, and the server's identity.** A job that ended frees its node and port, and another user's job can take them
(vLLM's default port is 8000). So health is also a question of whose server answers:

1. With a key, a request with a made-up wrong key comes first, and the server must refuse it (401). A server that takes
   it takes any key: it is not the one this endpoint names, and the load fails before the real key is ever sent ("the
   server at compute-node:8000 takes any key: it is not this endpoint's; its job may have ended, and another taken its
   port").
2. Then, with the key, the server must list the preset's model by its exact id. A refused key (401, 403) fails the
   load at once. A model it does not list fails it at once, naming those it does.
3. Then the tiny request, for that model, with the key.

Every request the runtime sends to an endpoint carries its key (§9), the watcher's included (§7): vLLM started with a
key refuses every `/v1` route without it, `/v1/models` included, so a check without the key would never see it ready.

**What waiting cannot change fails at once**, instead of after `start_seconds` (300 s; `runtime/slots.py:303-322` waits
while the process lives): the refusals above, ssh's own that are never tried again (§5), and ssh's `open failed` in the
tunnel's log. ssh goes on running when the node refuses, since `ExitOnForwardFailure` does not cover connections made
through a forward (ssh_config(5)), so the log is read. One exception: when the endpoint names its `job` and the
scheduler said it runs, a refused connection means its server may still be loading its model, and the step says so and
waits, up to `start_seconds`.

- **The route.** Once ready, the slot's route (what the gateway follows, `runtime/service.py:81-108`) gives the
  provider (`endpoint`), the base URL (`http://127.0.0.1:<slot port>/v1` through a tunnel, else the endpoint's URL),
  the model id as listed, the endpoint's id when it needs a key (never the key), the context (the smaller of the
  server's and the preset's), the output limit, `images`, the read timeout (§8), and the reach (§10). The reach is
  read from the endpoint's record each time the routes are asked for (every second), so a change to it applies to the
  next request; the rest is kept with the launch, so another change to the endpoint's file applies at its next start.
- **The launch record.** Migration `runtime 0003` adds a launch's `endpoint` and its `route` (as JSON, without any
  key). An endpoint's launch keeps `engine` and `engine_version` empty (required today, `runtime/state.py:92-93`), so
  the memory a GPU launch learns from (`runtime/launching.py:184-197`) never reads one.
- **Unload** closes the tunnel and never touches the server. A slot without a process of its own (a URL endpoint)
  unloads too: today `runtime/slots.py:328-330` says it "runs nothing" and leaves it as it was.
- **Switch.** From KVMem to an endpoint, the engine stops first (the GPU and the port freed), then the tunnel opens on
  the same port; a failed start goes back to the last configuration that worked, as for engines (design 0001 §4.3).
  From an endpoint to KVMem, the tunnel closes, then the engine starts. A switch, an unload or a load of the slot
  cancels a reopen in progress (§7).
- **The main slot, in an engine's place** (decision 0077, the owner's choice). Recommended, (a): an endpoint serves
  `main`, one provider at a time, as a switch between engines does; this reverses design 0001 §1's "endpoints run
  alongside" for serving. Everything that follows the main slot today works unchanged: OpenCode's one model, the role
  `agent` (`agents/service.py:58`), its limits, the Monitor (decision 0067), the folder page, `clank work`, a flow's
  boxes (decision 0062). On the Pi nothing is lost. The cost is on this PC: while `main` runs an endpoint, KVMem does
  not run, and every workspace still bound to this machine is refused (§10) instead of being served by KVMem. Option
  (b), an endpoint in a slot of its own beside `main`, reached by a role that a workspace's OpenCode names as a second
  model (design 0013 §7 foresees one), removes that cost for about four more steps. Either way, `fast` needs
  llama.cpp's `/infill` (design 0006), and `vision` a model loaded on demand on this machine (design 0008 §7): an
  endpoint preset for either is refused, saying why.
- **The agent's limits** follow the route (`agents/service.py:305-324`), so OpenCode compacts before the server's
  context, not Clank's fallback; the Monitor's figures (decision 0067) read an endpoint's context from it too.

## 7. The watcher keeps the tunnel open

*Proposed 2026-10-18.*

Today a process that ends in a ready slot is an engine that crashed: the slot fails, and the engine is started again
only if it had been ready ten minutes (`runtime/watching.py:36, 119-144`). The watcher also skips a slot without a
process (`runtime/watching.py:96`), and checks health without a key (`runtime/watching.py:107, 153-158`). A tunnel is
not an engine: networks drop, computers sleep, and the server goes on running. For an endpoint's slot:

- **Health.** Every `health_seconds` (30), the check of §6 (a wrong key refused, then the preset's model listed, with
  the key), for every endpoint slot, a URL endpoint's included. It comes in the same step as the load's (§16, E7a), so
  no build of Clank stops a slot for a check sent without its key. A server that takes the wrong key, or no longer
  takes the right one, fails the slot at once: it is not this endpoint's. Three other misses in a row fail it too,
  saying why, and a tunnel still running is closed. The crash rule's restart (`runtime/watching.py:119-144`,
  `runtime.restart`) never applies to an endpoint's slot.
- **A dropped tunnel is reopened at once**, by an operation of its own, `runtime.reopen`, under the slot's lock. Every
  client shows it, the slot is `starting` with ssh's last words as its reason, and the gateway holds the slot's new
  requests meanwhile (`gateway/routing.py:104-115`). A request the drop broke off before any answer is sent again once
  the slot is served again, as for an engine that broke off (`gateway/server.py:287-345`); one broken off after part
  of its answer ends with `engine_broke_off`, saying so. A connection that dies without closing is noticed within
  about a minute (`ServerAliveInterval 15`, `ServerAliveCountMax 3`, §5), when ssh ends.
- **The job first.** Before each reopen, the job is confirmed when the endpoint names one (§5), and the slot fails
  when the job's time has run out.
- **With backoff**: tries 1, 2, 4, 8, 16 and 32 seconds apart, then every 60 seconds, for up to `reopen_seconds` (a
  runtime setting; 300, the gateway's hold); then the slot fails, saying why.
- **Not tried again**: what waiting cannot change (§5's table), a 401 from the server, and a server that is not this
  endpoint's (§6). The slot fails with what to do.
- **A switch cancels a reopen.** `runtime.reopen` holds the slot's lock while it tries, and an operation that needs a
  lock another holds is refused (`kernel/operations.py:7`). So a switch, an unload or a load of that slot cancels the
  reopen first, then runs: going back to KVMem while the network is down is not refused as busy.
- **After a restart of the service**, a tunnel still running by the same identity is adopted, and its slot stays
  ready. One that ended meanwhile is reopened once, as after a drop (an engine that ended meanwhile leaves its slot
  stopped, `runtime/watching.py:74-77`).
- **A tunnel the owner opened** (§5) is a URL endpoint: health-checked like any, never reopened by Clank. Its slot
  fails after three missed health checks, saying that the tunnel the owner opened answers no more.
- Each reopening is in the history: the slot's states (`runtime.slot` events) and the operation's log (design 0001
  §4.4: "the reconnection is shown").

## 8. The gateway forwards to an endpoint

*Proposed 2026-10-18 (decision 0074).*

Today the gateway forwards to `http://127.0.0.1:<port>/v1/chat/completions` (`gateway/server.py:207, 217`) and
requires a route that names an engine (`gateway/server.py:184-186`, `gateway/routing.py:45-48`). With an endpoint:

- **Where.** `<base URL>/chat/completions`, the base URL from the route (§6). An engine's base URL is
  `http://127.0.0.1:<port>/v1`, so one path serves both. Certificates are always verified (§2).
- **What.** The request as the endpoint's adapter makes it: as the tool sent it, but the model name, which is the id
  the server lists (where `gateway/server.py:188` puts the runtime's `model_name` today).
- **The key.** `Authorization: Bearer <key>` for an endpoint that needs one, got as decision 0073 says (§9). Never the
  tool's own header: the gateway builds its own request, and keeps doing so.
- **A read timeout, never sent again.** Today there is none (`gateway/server.py:107`), since an engine reading a long
  prompt can be silent for minutes. An endpoint's requests wait at most its `timeout_seconds` for the next piece of a
  streamed answer. An answer that is not streamed comes whole, so there it bounds the whole answer. Then the request
  ends saying so (`endpoint_silent`: an error event in a stream, a 504 otherwise), and its connection is closed. A
  timeout is not a broken-off engine: the request is never sent again. Today every error of httpx2 before the first
  token sends a request again once its slot is served (at the first send, `gateway/server.py:218-228`; reading a whole
  answer, `:232-246`; in the stream, `:321-341`; each through `again()`, `:196-215`), and httpx2's `ReadTimeout` is
  one of them: a server slow to read a long prompt, or one that queues it, would get it twice. The timeout is told
  apart from the errors that send a request again. Engines keep no read timeout.
- **Refusals pass on as they are.** A 401, 403, 404 or 429 reaches the tool with the server's own status and words;
  the record says what it is (§3's `refusal`: the key refused; the limit, and until when), and the Requests page shows
  it. The gateway never sends them again (design 0001 §4.4: "not retried blindly").
- **Thinking streamed as `reasoning`** (current vLLM) is read like `reasoning_content` by the loop guard, the live
  view and the rule that sends again a request broken off before any token (`gateway/server.py:431, 438-439,
  451-452`); the stream reaches the tool unchanged (decision 0074).
- **Where it may go.** Each request is checked against its workspace's bound before it is sent (§10).
- **Records.** A request's record names the provider (`endpoint hpc`), the model id sent, its workspace (§10) and the
  endpoint's reach. Keys are never kept: credential headers already are not (`gateway/records.py:22`), and a key value
  the gateway holds is replaced by `…` and its last four characters wherever it appears, in a record or in the live
  view, even when a server echoes it back in an answer (design 0002 §2.8's last rule). A workspace's own key (§10) is
  the exception: the gateway knows it only by its hash, so it cannot find it in what that workspace's agent sends (a
  prompt that quotes it). It still never keeps it from a header, and it opens nothing beyond that workspace's bound.
- Completion's fill in the middle (`/v1/infill`) and the vision role stay with this machine's engines (§6); an infill
  request for a role whose slot runs an endpoint is refused (§10).

## 9. Keys

*Proposed 2026-10-18; how the gateway gets a key is the owner's choice (decision 0073).*

- **Where.** An endpoint's key is a secret of the kernel (design 0002 §2.8, `kernel/secrets.py:67-100`):
  `CLANK_HOME/secrets/endpoint/<id>/key`, readable by the owner only, shown by its last four characters. Removing the
  endpoint removes it.
- **Needed beyond this machine** (§2). The key's steps are part of the first session (§16): its endpoint is a tunnel
  to a server beyond this machine, and without a key the server cannot be told from another (§6).
- **Set.** `clank endpoint key hpc` asks for it without showing it, or reads one line of standard input (`--stdin`)
  for a script; never from an argument, which other programs and the shell's history can read.
- **The server's side.** vLLM reads its key from the environment variable `VLLM_API_KEY`: the owner's job script sets
  it from a file in their cluster account that only they can read (`chmod 600`), and never passes `--api-key KEY`,
  which every user of a shared node can read (`ps`, `/proc`). Another server keeps it off its command line its own way
  (llama.cpp's `--api-key-file`). T0 shows that the server refuses a wrong key (§15).
- **Read once per launch.** The runtime reads it through the kernel for its own requests (a load's health, the
  watcher's checks: §6, §7), and the gateway gets it the first time a launch's route needs it, and again when the
  routes say the key was set since (they carry when it was set, never the key). Each keeps it in memory only while that
  launch runs, and each read is a `secret.used` event that names who read it and for which launch. Decision 0021
  decides `secret.use` at the moment of use; for an endpoint's key, this design takes that moment to be the launch the
  owner started, since a decision per request would stop every request to the endpoint while the service restarts
  (decision 0073 refines 0021).
- **How the gateway gets it** (decision 0073). Recommended, (a): the gateway's service makes a token for the gateway
  at each start of it and gives it in the gateway's environment (never in a file or on its command line). It registers
  the token's SHA-256 with the kernel, which keeps it in its state with the process it names, so a gateway adopted
  after a restart of the service (`gateway/service.py:4-7`) is still known; the gateway's next start replaces it. A
  route that only process tokens reach (the kernel's `process` access level, design 0002 §2.7; today the API has one
  level, `kernel/api.py:55`, and mounts every component's routes with it, `kernel/api.py:153`) gives the gateway the
  key, read through the kernel, while that endpoint serves a slot. The local token cannot read it: no client can read
  a key through the API. Option (b): the gateway reads the key's file itself and tells the service each time; no
  change to the kernel, but a second reader of `secrets/`, and a use recorded only when its report arrives.
- **Never written elsewhere**: not in the routes the gateway follows, a launch, an event, an operation's log, a
  process's log or the tunnel's file.

## 10. Where a workspace's requests may go

*Proposed 2026-10-18; the owner chooses (decision 0075).*

Design 0002 §2.6 approved `model.send`: a workspace's content goes to a model provider only within its bounds ("this
machine only, unless the user widens it"), checked by the gateway "against the provider serving it at that moment, so
switching a role to a hosted model never widens where a workspace's content goes". None of it is built: there is no
policy function yet, and the gateway cannot tell workspaces apart, since every workspace's OpenCode sends the key
`local` (`agents/adapters/opencode.py:142`) through one edge that serves every workspace
(`workspaces/sandbox.py:154-169`). That edge relays the gateway's whole port, bytes both ways
(`workspaces/image/edge.py:1-6`): whatever Clank's MCP server in a container can reach, the agent's shell there can
reach too, with or without a key.

- **Reach and bound.** What serves a slot has a reach: an engine, `this-machine`; an endpoint, its record's (§2).
  Each workspace has a bound, `models` on its record: the farthest reach its content may go. It is `this-machine` for
  every workspace, new or existing, until the owner widens it.
- **A key per workspace.** Each workspace's OpenCode, and Clank's MCP server in its container, send a key of their
  own: the workspace's name at the gateway. The gateway's service makes it and keeps it, as the secret
  `workspace/<id>/gateway-key`, and keeps its SHA-256 and the workspace's bound in the gateway's own state (the
  gateway's first migration). Two components reach them through public functions of the gateway's service: the agents
  component gets the key when it writes OpenCode's configuration (`agents/adapters/opencode.py:142`, its `apiKey`) and
  the MCP server's environment (`agents/service.py:270-271`); the workspaces component gives the bound its record
  says, at each change (by the command, the folder page, or an edit of the file, which the kernel reports as
  `settings.changed`) and at each start of the service. Both already use the gateway (`workspaces/component.py:38`,
  `agents/component.py:39`), and the gateway uses neither: a gateway that read the workspaces' records or state would
  close a cycle, which decision 0019 and `tests/test_architecture.py:67` forbid. The routes the gateway follows each
  second carry each key's hash with its workspace and bound, never a key. This refines design 0002 §2.7 (a session
  named by its edge: the edge is one plain relay) and §2.8 (no secret enters a sandbox: this one is the sandbox's own
  name; and the gateway cannot remove it from what that workspace's agent sends, §8).

**Every route a container reaches**, through the edge, and its rule:

| Route | What it gives | Who it answers |
| --- | --- | --- |
| `GET /health`, `GET /v1/models` | That the gateway answers; the roles' names | Anyone |
| `POST /v1/chat/completions` | A model's answer | A request within the bound of the workspace its key names; one without a known key only when its slot runs on this machine (below) |
| `POST /v1/infill` | Completion's fill in the middle | Only an engine on this machine answers it: a role whose slot runs an endpoint is refused (`no_engine`), since today `gateway/completion.py:101-113` would send it to the slot's port, the tunnel's |
| `GET`, `POST /notion/...` | The owner's Notion, through the service (design 0010 §3) | Only a request with a known workspace key; under the recommended answer below, only one whose bound is this machine (403, `notion_denied`, otherwise). Never a request without a key |
| `GET /activity`, `GET /activity/live`, `GET /completion` | Each request in flight; the live text of the newest, whichever workspace sent it: what it asked, and up to 400,000 characters of its thinking, answer and tool calls (`gateway/activity.py:28, 92-121`); completion's counts | Only the local token, which no container holds (401 otherwise). The service, their only caller, sends it (`gateway/service.py:87, 279, 294`) |

Today each of them answers any caller (`gateway/server.py:115-145`, `gateway/completion.py:86-90`): a widened
workspace's agent could read another workspace's live text and carry it beyond this machine in its own requests.

- **The check.** For each model request, the reach of what serves its role's slot at that moment, against the bound of
  the workspace its key names. Beyond it, the request is refused before anything is sent (403, `model_send_denied`),
  in words that say how to widen the bound or load a model on this machine, and recorded. A request with no known key
  (a script, an OpenCode started before its key was written, or one whose key a widening replaced) may go only to this
  machine, the narrowest bound. That is the safe side for model requests only: Notion is decided by a known key,
  never by a missing one (above). Switching a role to an endpoint never widens a bound.
- **Widening** is a change to the workspace's record (`clank workspace allow FOLDER --models my-servers`, or the
  folder page), recorded with who made it (design 0002 §2.2). Narrowing applies to the next request.
- **What widening sends.** The bound is checked per request, but each request carries the whole conversation: OpenCode
  sends its session's history every time, and its sessions stay in the workspace's home volume
  (`workspaces/sandbox.py:8-9`). A workspace that read research files or Notion pages while bound to this machine would
  send them with the next request of that session after widening; the Notion rule stops only the reads made after it.
  So widening:
  - asks first, on the folder page and in the command (`--yes` answers for a script), saying that each session the
    workspace already holds goes whole with its next request, and recommending a new session, or better, a workspace
    made for the purpose;
  - gives the workspace a new key, so each OpenCode started before the widening keeps the old bound (its key is no
    longer known: this machine only), and what it already read stays on this machine. The new bound applies from
    OpenCode's next start, which the folder page says.
- **While the service does not answer**, the gateway keeps the last bounds (design 0002 §1), but refuses requests to
  a `hosted` endpoint, which decision 0021 decides at the moment of use.
- **The owner's question** (decision 0075). The owner's rule is that research stays with local models. May a
  workspace's files go to the remote server, and may the Notion pages the agent reads? Widening one sends what
  its sessions already hold (above). Recommended: per workspace, starting with one new scratch workspace of made-up
  content for the dry runs (T1, T4), new so that no earlier session goes with it; and Notion not at all: the gateway
  answers `/notion/...` only to a known key whose bound is this machine, until the owner says otherwise. The other
  answers change this section: with one switch for every workspace, every workspace shares one bound, and the keys
  stay, since Notion is decided by a known key; Notion allowed lets any known key through, never a request without
  one. Under decision 0077's recommended answer, a workspace bound to this machine is refused while `main` runs an
  endpoint.
- **The first piece of the policy.** This is design 0002 §2.6's bounds layer for `model.send` alone. The policy
  function, the floor, modes and grants come with M7, where this rule becomes one of its rules; until then a request
  beyond its bound is refused, never asked about. A flow's box whose preset is an endpoint's (decision 0062) needs its
  workspace widened first, and the runner says so before it switches.

## 11. The check

*Proposed 2026-10-18 (decision 0076).*

Design 0001 §3.8's check "starts nothing". An endpoint's check has to connect to learn anything, so it connects,
briefly (decision 0076): `clank endpoint check hpc`, `clank preset check` of an endpoint preset, and `c` on the
console's Providers page. It can take a minute, so it is an operation. Each item passes, fails or is unknown, with why:

```
 CHECK  hpc (remote cluster)
  ok    ssh       C:\Windows\System32\OpenSSH\ssh.exe (OpenSSH for Windows, a version recorded)
  ok    config    ssh -G: login.example.org as you, through bastion.example.org; BatchMode yes on both
  ok    agent     the OpenSSH Authentication Agent service runs
  ok    key       set (ends …a1b2)
  ok    job       123456 runs on compute-node, 41 h left
  ok    tunnel    opened in 2.1 s on a port of its own; closed after the check
  ok    server    refused a wrong key, took this one
  ok    model     example-org/example-coder, context 131,072
  ok    answer    a reply of a few tokens in 0.8 s
  fail  tools     refused: start the server with --enable-auto-tool-choice and a --tool-call-parser
  ok    thinking  streamed as reasoning (read as thinking, decision 0074)
  ok    usage     given at the end of a stream
```

- The first four items start nothing, so a check that cannot connect still says what it could verify. The agent: on
  Linux and macOS, whether the service's `SSH_AUTH_SOCK` names a live socket (a service started from an SSH session
  loses a forwarded agent when the session ends, §5); on Windows, whether the OpenSSH Authentication Agent service
  runs.
- An `insecure` endpoint is flagged on a line of its own every time ("warn  insecure  no key beyond this machine", or
  "plain http to 192.0.2.10"), whatever else passes (§2).
- The tunnel is its own, on a free port of the loopback, never a slot's (the main slot's port may hold an engine);
  when a slot runs this endpoint, its tunnel is used instead. With `ends_at: node`, an unknown node's host key fails
  here, saying how to compare it (§15, T0's step 2b).
- It sends only Clank's own made-up requests: the wrong key, the list of models, the tiny reply of a load's health
  check, and a call to a made-up tool with `stream_options.include_usage`. Nothing of a workspace's; nothing on the
  server is started, stopped or changed.
- A refused tool call names what the server needs: vLLM refuses tools sent without a `tool_choice` unless it was
  started with `--enable-auto-tool-choice` and a `--tool-call-parser` (its tool-calling documentation).
- The thinking item says where the server streams thinking: `reasoning` (current vLLM), `reasoning_content` (SGLang,
  llama.cpp), or inside the text (`<think>`), which means the server runs without a reasoning parser.
- The result is kept as an event (`runtime.endpoint_checked`, with its items), and `clank endpoint show` gives the
  last one. This is design 0001 §7.6's "the guide tests a key with a request of a few tokens and lists the endpoint's
  models", from a command now and from the guide in M10.

## 12. The commands, the console and VS Code

*Proposed 2026-10-18.*

```
clank endpoint add hpc --ssh you@login.example.org --jump you@bastion.example.org \
    --remote compute-node:8000 [--ends-at node] [--job 123456] --auth bearer --reach my-servers
clank endpoint add lab --url https://models.example.org/v1 --auth bearer --reach my-servers
clank endpoint key hpc [--stdin]                asked without showing it; kept in secrets/ (§9)
clank endpoint list | show hpc                  show: the record, the tunnel's file, the key's last four, the last check
clank endpoint models hpc                       what the server lists, each with its context
clank endpoint set hpc --remote compute-node:8001 --job 123457    a new job; reopens a tunnel a slot runs
clank endpoint preset hpc example-org/example-coder [--title T] [--context N] [--output N]
clank endpoint check hpc                        §11
clank endpoint remove hpc                       with its key; refused while a slot runs it or a preset names it
clank model load "cluster coder"                as for any preset (§6)
clank workspace allow FOLDER --models my-servers [--yes]    widen a workspace's bound, after saying what it sends (§10)
```

- Each is a client of the API (design 0002 §2.15), with `--json`. `endpoint models` and `endpoint preset` connect as
  the check does (decision 0076). `--insecure` on `add` and `set` says, each time, what it allows (§2).
- **The console.** The Providers and models page (design 0001 §5.3's providers screen, design 0003 §8.2) lists each
  endpoint: its reach, whether its key is set (its last four), whether it is insecure, its tunnel (open or not, for
  which slot, since when; its job and the time left) and its last check; `c` checks it and `e` opens its file. The
  preset picker and the Presets page show an endpoint preset as `endpoint hpc · example-org/example-coder` (§4). The
  folder page shows the workspace's bound, and widens it after asking (§10).
- **VS Code.** *Clank: Switch model* lists endpoint presets the same way; a refused request (§10) reaches the agent's
  terminal in OpenCode's own words.
- The setup guide's "On another computer" (design 0001 §7.3, M10) walks through these same commands.

## 13. `clank work`, `clank code` and the folder page

*Proposed 2026-10-18.*

Today they load the main slot's last configuration that worked, else `daily-262k` (`agents/cli.py:28, 93-101`;
`agents/console/folder.py:51, 683, 779`). On a machine without a local engine (the Pi), that preset cannot run.

- They use what the main slot runs when it is ready, an endpoint included (as today).
- Else its last configuration that worked; else the preset the runtime's settings name, `fallback_preset`
  (`daily-262k` by default, Clank's own), which the owner sets to an endpoint preset on such a machine.
- **OpenCode's limits follow a model loaded after its configuration was written.** Today they stay at the fallback
  (`agents/service.py:59`). When the main slot becomes ready with other limits, each prepared workspace's
  configuration is written again, applied at OpenCode's next start, and the folder page and VS Code say so (as design
  0013 §7 does after a box's switch).
- A workspace bound to this machine, opened while the main slot runs an endpoint, is told so before its agent starts,
  with the two ways out (§10).

## 14. Recordings, fakes and the capture tool

*Proposed 2026-10-18.*

Design 0001 §8.2-§8.3 runs contract tests against what the real programs answered. For an endpoint, what it answers
is HTTP:

- **HTTP recordings**, `tests/fixtures/openai-compatible/<server>-<version>/http.json`: what a real server answered to
  Clank's fixed made-up requests: its list of models; a short reply, whole and streamed; a streamed answer with
  thinking, a tool call and usage; a request with a wrong key. Each exchange holds the request (its method, its path,
  its shape) and the answer (its status, the headers that matter, its body or its streamed lines). The first are from
  `llama-server` (llama.cpp b11588, the CPU build Clank already installs for the fast slot), recorded on this machine
  with the owner's go-ahead; the owner's capture of the cluster's server joins them after T1.
- **The repository's checks accept them.** The architecture test wants `program.json` for every recorded adapter
  (`tests/test_architecture.py:97-105`), as `clank/kernel/adapters.py`'s docstring says; both learn that an endpoint
  adapter's recordings are `http.json`, and `tests/fixtures/README.md` describes them. The kind of adapter is declared
  in the step that brings its first recording and its contract test (§16, E2), so no commit holds a kind without them.
- **A fake server**, `tests/fakes/endpoint.py`, plays a recording back over HTTP and fails the test on any request it
  has no recording for, as `tests/fakes/recorded.py` does for programs. Its flags make it require its key on every
  `/v1` route (as vLLM does, `/v1/models` included), take any key (a server that is not the endpoint's), stall (for the
  read timeout), answer 429 with a `Retry-After`, stream thinking as `reasoning` or `reasoning_content`, and drop its
  connection mid-answer.
- **A fake `ssh`**, `tests/fakes/ssh.py`, run as `[python, tests/fakes/ssh.py]` in place of `ssh` (a list, §5): it
  keeps its arguments and the file it was given, answers `-V` and `-G` as recorded, answers the job's `squeue` as it is
  told, and for `-N -L` listens on the local port and passes each connection to a fake server, or prints one of ssh's
  refusals in its own words and ends. `ssh -V` and `ssh -G` are recorded from Windows' OpenSSH and from a Linux one
  (`tests/fixtures/openssh/<version>/program.json`), with each refusal's words as OpenSSH's source writes them at that
  version, and as T0, T1 and T5 show them, names replaced.
- **The capture tool**, `tools/capture_endpoint.py`, a development tool that is never shipped, in place of design 0001
  §8.3's `clank dev capture`: it sends the fixed made-up requests to a server (a URL, or a tunnel the owner opened)
  and writes the recording with host names, node names, user names and keys replaced by made-up ones of the same
  form. The secrets check reads recordings like every other file.
- **Real tests**, `tests/real/test_endpoint.py`, under a marker of their own, `endpoint` (`-m endpoint`), never in CI.
  `-m real`, which starts this machine's engines (`tests/real/conftest.py`), never logs in to the cluster, and
  `-m endpoint` starts no engine. They take the endpoint's record by its id from the owner's `CLANK_HOME`
  (`CLANK_TEST_ENDPOINT`), and its key from an environment variable set for that run only
  (`CLANK_TEST_ENDPOINT_KEY`, typed without echo), held in memory: no copy of `secrets/` is made. Made-up prompts
  only: its models, a short answer, a tool call.

## 15. Dry runs T0-T5

*Proposed 2026-10-18.*

**T0, now: it needs no code and touches nothing of Clank.** In Git Bash on this PC (its `ssh` and `curl`), with the
capitals replaced by the real names, and a made-up prompt only:

```bash
# 1. Does a key alone log in, with no prompt, on both hosts? (-o reaches the login host only: the jump has its own.)
ssh -o BatchMode=yes -o ConnectTimeout=10 \
    -o ProxyCommand="ssh -o BatchMode=yes -o ConnectTimeout=10 -W %h:%p USER@bastion.example.org" \
    USER@login.example.org hostname
#    On the cluster's own network, also without the jump host:
ssh -o BatchMode=yes -o ConnectTimeout=10 USER@login.example.org hostname
# 2. Where does the server run now, and how long has its job left?
ssh -J USER@bastion.example.org USER@login.example.org 'squeue -u USER -o "%i %j %T %N %L"'
# 2b. Can you log in to the node of your own running job? The first time, ssh asks about the node's host key: compare
#     its fingerprint with the one the login host knows (there: ssh-keygen -lF NODE -f /etc/ssh/ssh_known_hosts).
ssh -J USER@bastion.example.org,USER@login.example.org USER@NODE hostname
#     Then again with -o BatchMode=yes: a host name with no prompt means the tunnel can end at the node.
# 3. Open the tunnel by hand. It seems to hang: that is the tunnel. Port 18300 is clear of Clank's own
#    (the service 7720, the gateway 18210, the slots 18200-18202).
ssh -N -L 127.0.0.1:18300:NODE:PORT -J USER@bastion.example.org USER@login.example.org
# 4. In a second terminal: what does the server say it serves? (Add -H "Authorization: Bearer KEY" when it needs one.)
curl -s http://127.0.0.1:18300/v1/models
# 4b. Does it refuse a wrong key? 401: yes. 200: it takes any key.
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer not-the-key" http://127.0.0.1:18300/v1/models
# 5. A streamed tool call that asks for usage (add -H "Authorization: Bearer KEY" when the server needs a key):
curl -sN http://127.0.0.1:18300/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "MODEL", "stream": true, "stream_options": {"include_usage": true},
  "messages": [{"role": "user", "content": "Use the tool to read notes.txt."}],
  "tools": [{"type": "function", "function": {"name": "read", "description": "Read a file",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]}'
```

What to look for:

- **Step 1.** A host name, with no prompt, means an unattended tunnel can work. A refusal means §5's fallback: a
  tunnel the owner opens.
- **Step 2b.** A host name with no prompt means `ends_at: node` (§5); a refusal means the tunnel ends at the login
  host, as the cluster's recipe has it.
- **Step 4.** The exact model id, which Clank sends as is; the context, as `max_model_len` (vLLM, SGLang) or under
  `meta` (llama.cpp).
- **Step 4b.** A 401 means the server checks keys. A 200 means it takes any key, and must be started again with one,
  kept off its command line (§9).
- **Step 5.** A 400 that names the tool-call flags means the server must be started again with them. Thinking arrives
  as `reasoning` (current vLLM), as `reasoning_content` (SGLang, llama.cpp), or inside the text when no reasoning
  parser runs. Look for a `tool_calls` delta, a `finish_reason` followed by `data: [DONE]`, and a `usage` chunk. A 401
  means a key is needed.

The owner sends these facts, with names and keys removed. They decide §3's fields, whether §5 runs unattended and
where its tunnel ends, §8's thinking field, and §14's second recording.

**Before T1:** the owner asks the cluster's help desk whether a model server kept running for days, reached by an
unattended tunnel that logs in again each time it reopens, is acceptable (§17).

**T1, this PC, after the B steps of §16.** The whole path with Docker Desktop; with only the B steps built, the
preset's file is written by hand (§4). First, on Windows:

- Turn on Windows' own SSH agent, in a PowerShell run as administrator (`Get-Service ssh-agent | Set-Service
  -StartupType Manual`, then `Start-Service ssh-agent`), and load the key into it with Windows' own `ssh-add`
  (`C:\Windows\System32\OpenSSH\ssh-add.exe`): the keys Git Bash's agent held for T0 are not in it.
- Use a new scratch folder of made-up content, never opened as a workspace before, so it holds no session (§10).

```text
clank endpoint add hpc --ssh USER@login.example.org --jump USER@bastion.example.org --remote NODE:PORT \
    --auth bearer --reach my-servers
clank endpoint key hpc
clank model load PRESET
clank workspace allow <that folder> --models my-servers
clank work <that folder>              then: clank code <that folder>
```

With step E6c built (§16), add `--job JOB`, and `--ends-at node` when T0's step 2b passed. Loading the endpoint into
the main slot stops this PC's KVMem first (§6, decision 0077), so it is done when no GPU work runs; the owner's other
workspaces are refused (§10) until the main slot runs a local model again. T1 also measures, on Windows, how Windows'
own OpenSSH runs the `ProxyCommand` Clank writes, that no window opens, and which agent the tunnel finds when the
service was started from PowerShell and from Git Bash (whose `SSH_AUTH_SOCK` names Git's own agent). Then the capture
runs once (§14).

**T2, CI, after design 0014's step P2:** its docker-marked tests on `ubuntu-24.04-arm`. Endpoints' tests run with the
fakes in every CI run already.

**T3, the Pi at home, beside the code:** design 0014's setup, then, for this design, `ssh -V` and T0's steps from the
Pi (its own OpenSSH and agent), with the service later started from a shell whose agent outlives it (the desktop's,
not an SSH session's).

**T4, the Pi at home, through the jump host, after T1 and design 0014's L steps:** T1's commands; `clank work` in a
terminal first, then `clank code` on the Pi's desktop; `free -m`, `docker stats` and `top` while it works; and the
network dropped once (Wi-Fi off and on), to see the tunnel reopen (§7; step E8a, a B step).

**T5, inside the cluster's network:** join that network; T0's step 1, with the jump host and without it, to see whether
that network reaches either host and counts as inside the cluster's firewall (if the direct path works, `clank endpoint
set hpc --jump ""`); when either fails, the words ssh prints, for §5's table; compare `ip route` with Docker's networks;
then the real session.

## 16. Build steps

*Proposed 2026-10-18.*

Each step is one commit that starts with a failing test (design 0001 §8.6); [plan s10](../plans/s10-endpoints.md) has
each one's files, interfaces and tests. **B** steps are needed for the first session on the Pi; **R** steps before
relying on it. The first session's endpoint is a tunnel to a server beyond this machine, so its key is needed (§2,
§9): the key's steps are B.

| Step | Builds | After |
| --- | --- | --- |
| E1 B | The endpoint record and its rules (a URL or a tunnel; a key beyond this machine; `https` beyond the loopback), and the `openai-compatible` adapter's module (§2, §3) | This design's approval |
| E2 B | The kind of adapter declared, with its contract test, its first HTTP recordings from `llama-server`, and `http.json` accepted by the repository's checks; the fake server (§3, §14) | E1 |
| E3a B | Presets name an engine or an endpoint, and every reader handles both (§4) | E1 |
| E3b R | `endpoint <name>` in the console, the command and VS Code (§4, §12) | E3a |
| E4 B | Keys: set, shown by their last four, removed from the gateway's records (§8, §9) | E1 |
| E5a B | The kernel's `process` access (decision 0073 (a)) | Decision 0073 |
| E5b B | The gateway gets an endpoint's key that way (§9) | E4, E5a |
| E6a B | The tunnel: its file (`ProxyCommand` quoted, `UpdateHostKeys no`), its command, the loopback only, the program as a list (§5) | E1 |
| E6b R | ssh's refusals become what to do; ssh recorded on Windows and Linux; the agent's state (§5, §11) | E6a |
| E6c R | The tunnel that ends at the node; the job confirmed before each open, and its time left (§5) | E6a, E8a |
| E7a B | A slot loads an endpoint: the server's identity and health with the key, what waiting cannot change failing at once; the watcher's checks with the key (§6, §7) | E2, E3a, E4, E6a |
| E7b B | The route, kept with the launch (migration `runtime 0003`), its reach read live; the agent's limits (§6) | E7a |
| E7c B | Unload and switch (§6) | E7b |
| E8a B | The watcher reopens a dropped tunnel, with backoff; refusals not tried again; a switch cancels a reopen (§7) | E7a |
| E8b R | A server not the endpoint's, or three misses, fail the slot without a restart; URL endpoints checked; adoption (§7) | E8a |
| E9a B | The gateway forwards with the key and the server's model id (§8) | E7b, E5b |
| E9b R | 401 and 429 recorded as what they are; the read timeout, never sent again (§8) | E9a |
| E10 B | Thinking streamed as `reasoning` (decision 0074) | Decision 0074 |
| E11a B | The gateway keeps a key and a bound per workspace; the workspaces component gives it each bound (§10) | E1, decision 0075 |
| E11b B | Each workspace's OpenCode and Clank's MCP server send its key (§10) | E11a |
| E11c B | Each model request checked against its workspace's bound (§10) | E11b, E9a |
| E11d B | The gateway's other routes: Notion by a known key, infill on this machine only, the activity routes by the local token (§10) | E11b |
| E11e B | Widening: asked first, a new key, recorded (§10) | E11b, E11c, E11d |
| E12a B | `clank endpoint add`, `key`, `list`, `show`, `remove` (§12) | E1, E4 |
| E12b R | `clank endpoint models`, `set`, `preset` (§12) | E12a, E7b |
| E12c R | `clank endpoint check` (§11) | E12b, E9a |
| E13 B | `clank work`, `clank code` and the folder page with an endpoint (§13) | E7b, E12a |
| E14a R | The capture tool's removal of names and keys; the real tests, under their own marker (§14) | E2 |
| E14b R | The cluster server's recording, after T1 (§14) | E14a, T1 |

20 B steps and 9 R steps, 29 in all: the researched plan's 26, with E6c, E11d and E11e added, and E4, E5a, E5b and
E8a now B. E9a, E11c and E11d change `gateway/server.py`, as design 0014's L5 does: no two of them are built at the
same time.

## 17. What this design does not cover

*Proposed 2026-10-18.*

- Starting or stopping a server through the cluster's scheduler, or finding its node from `squeue`: later (design
  0001 §7.6). Confirming a named job (§5) is the scheduler's only use here.
- Templates for hosted providers (each one's base URL, how it takes its key, the request options it honors): later;
  the generic adapter already serves an OpenAI-compatible hosted API with a bearer key.
- Other dialects (Responses, Anthropic Messages): design 0001 §6.2's order.
- An endpoint in a slot of its own beside `main` (decision 0077's option (b)), and endpoints in `fast` and `vision`
  (§6).
- An endpoint's speed: M2's `speed` suite and trials (design 0001 §3.8).
- The operating system's keychain for keys (design 0001 §7.6: later, with a decision of its own).
- The Pi itself: Docker Engine, the edge's way to the gateway on Linux, its page size (design 0014).
- **The cluster administrators' view** of a model server kept running for days, reached by an unattended tunnel that
  logs in again each time it reopens: no rule is published (the researched plan). The owner asks the cluster's help desk
  before T1 (§15); its answer may change §5 and §7.
- What happens to content inside the cluster's network. With `ends_at: login`, the tunnel encrypts it only as far
  as the login host; with `ends_at: node`, as far as the node (§5). The server's own key (§9) and the owner's choice
  (§10) are what this design offers.
- A firewall rule against programs on this machine reaching a tunnel's port (§5): the server's key is what stops them.

## Decisions to record

- [0072](../decisions/0072-the-tunnel-is-openssh-with-a-config-clank-writes.md): the tunnel is the owner's own
  OpenSSH, with a file Clank writes and passes with `-F`, each jump named whole by `ProxyCommand`; no SSH library (§5).
- [0073](../decisions/0073-how-the-gateway-gets-an-endpoints-key.md): how the gateway gets an endpoint's key: a
  process token on routes only processes may call, or the gateway reading the key's file; the owner chooses (§9).
- [0074](../decisions/0074-thinking-streamed-as-reasoning-is-read-too.md): thinking streamed as `reasoning` is read
  like `reasoning_content`, and the stream passes on unchanged (§8).
- [0075](../decisions/0075-where-a-workspaces-requests-may-go.md): each workspace sends only to this machine until the
  owner widens its bound, each workspace has a key of its own, and every route a container reaches has its rule;
  whether research content and Notion pages may go to the remote server is the owner's question (§10).
- [0076](../decisions/0076-an-endpoints-check-connects.md): an endpoint's check connects, on a tunnel of its own, with
  Clank's own made-up requests (§11).
- [0077](../decisions/0077-an-endpoint-serves-the-main-slot.md): an endpoint serves the main slot in an engine's
  place, or a slot of its own beside it; the owner chooses (§6).

## Revision log

- **2026-10-19, before approval, after the review of 2026-10-19.** Notion is decided by a known workspace key, never
  by a missing one; every gateway route a container reaches has its rule (the live view needs the local token, infill
  never reaches an endpoint); widening asks first and gives a new key, since a session's history goes with it (§10).
  The server proves it holds the endpoint's key, the runtime's own checks send the key, and a tunnel may end at the
  node, its job confirmed first (§5-§7). A URL beyond the loopback is `https`, and an endpoint beyond this machine
  needs a key, unless `insecure` (§2). A read timeout is never sent again (§8). The main-slot choice has its own
  decision, 0077, and §1 lists every approved text this design changes. The tunnel names each jump with `ProxyCommand`
  and sets `UpdateHostKeys no`; ssh's refusals cover networks that block SSH and a lost agent (§5). The key on the
  cluster's side is kept off the command line (§9). The keys' hashes and bounds live in the gateway's own state, so no
  component cycle forms (§10). Plan s10 has 29 steps.
