# Slice 1: working in a folder (M3, M4 and M5's first slice): implementation plan

> As for M1, this plan gives the files, interfaces and tests by name and intent; the code is in the commits, written
> test-first. Built at the owner's instruction (2026-10-13: "prioritize getting M3, M4, and M5 working as long as M2 is
> not required for me to begin working"), from design 0004, whose marked choices the owner reviews as built.

**Goal:** `clank` in any folder opens OpenCode in that folder's own container, talking to the model the main slot runs
through Clank's gateway; `clank code` opens a separate, stripped VS Code on the folder with the agent beside the files;
the desktop stays responsive.

**Spec:** [design 0004](../design/0004-working-in-a-folder.md); design 0001 §6 (the gateway); design 0002 §1-§2
(workspaces, sandboxes, the edge, agents by adapters); decisions 0008, 0011, 0013, 0020, 0033.

## Global Constraints

- Everything of M1's constraints holds (synthetic data only, American English, no personal values in tracked files,
  a decision record for a new dependency, every step committed and pushed).
- Nothing Clank starts opens a window (`background_flags()`); every check runs at Idle priority while the owner works.
- Real engines, Docker builds and downloads run only when the owner is away or says so; the tests that need them are
  marked (`-m real`, `-m docker`) and skipped otherwise, saying why.
- Clank needs nothing from the prototype (decision 0033): its own image, its own gateway, its own VS Code instance.

## Review Focus

1. **A request while the slot switches**: held, then answered by the new engine, not refused.
2. **NInfer's strict fields**: a request with llama.cpp's `chat_template_kwargs` reaches NInfer as `enable_thinking`.
3. **A client that hangs up mid-answer**: the engine stops generating for it.
4. **A path or a symlink that leads outside the workspace**: nothing outside the folder can be read from the container.
5. **The owner's main VS Code**: untouched by `clank code` (its settings, extensions and profiles).

---

### Task 1: The gateway (M3, first slice)

**Files:** `clank/components/gateway/` (`component.py`, `kinds.py`, `service.py`, `server.py`, `routing.py`,
`records.py`, `titles.py`, `api.py`, `cli.py`); engine adapters' `translate`; tests `tests/components/gateway/`.

**Interfaces:** `GatewaySettings` (`config/gateway.json`: port 18210, records, local titles, hold); the gateway process
(`python -m clank.components.gateway.server`), supervised by the service and adopted after its restart; the service's
`/gateway` and `/gateway/routes`; `EngineAdapter.translate(body) -> (body, notes)`; `clank gateway status|restart`.

### Task 2: Workspaces and containers (M4, first slice)

**Files:** `clank/components/workspaces/` (`kinds.py` Workspace, `image/Dockerfile`, `sandbox.py`, the edge); the
Docker Desktop adapter's container commands and their recordings; tests, the escape tests marked `docker`.

**Interfaces:**
- `Workspace` (settings kind `workspace`, `config/workspaces/<name>.json`): `folder` (absolute, on this machine),
  `cpus` and `memory_mib` (empty: half the platform's CPUs, a quarter of its memory). Its name comes from the folder's
  (`workspace_name(folder, taken)`: lowercase letters, digits and dashes, made unique with `-2`, `-3`).
- `ContainerSpec` (`sandbox.py`): a container as Clank wants it (name, image, labels, networks with aliases, the
  folder's bind mount, named volumes, user, working folder, CPU, memory and process limits, `--init`, dropped
  capabilities, `no-new-privileges`, a read-only root for the edge, its command); `run_arguments(spec)` gives the exact
  `docker run` arguments, so what a container may reach is tested without Docker.
- `ContainerPlatform` gains its container commands: `limits()` (the platform's CPUs and memory), `image_exists`,
  `build_image` (each line as it comes, cancelable), `ensure_network(name, internal, labels)`, `container(name)`,
  `run_container(spec)`, `start_container`, `stop_container`, `remove_container`, `remove_volume`, and `exec_argv`
  (the command a terminal runs to enter a container).
- Operations: `workspaces.open` {folder, yes} (the record, the image, the networks, the edge, the container: each done
  only when missing, so it is safe to run again), `workspaces.stop` {name}, `workspaces.remove` {name} (asks first:
  the container and its home volume go, the folder stays). Locks `workspace:<name>`, and `sandbox-image` for a build.
- Routes `GET /workspaces`, `POST /workspaces/open`, `POST /workspaces/{name}/stop`, `POST /workspaces/{name}/remove`;
  commands `clank workspace list|open [FOLDER]|stop [NAME]|remove NAME`.

**Steps:**
- [x] `ContainerSpec` and `run_arguments`, with the workspace's and the edge's specs: tests of the exact arguments
  (the folder its only mount, no capabilities, the internal network only, the limits).
- [x] The Docker Desktop adapter's container commands, tested on a scripted `run` (and on recordings of the real
  `docker` once Docker may run: the owner uses the PC now).
- [x] The `Workspace` kind, names, and the three operations on the fake platform: open twice does nothing the second
  time; a stopped container is started, not made again; remove asks and leaves the folder.
- [x] The image's files (`image/Dockerfile`, `image/edge.py`, the image's tag from their checksum) and the build as a
  step of open, asked first (it downloads about a gigabyte), its lines in the operation's log; the edge's forwarder
  tested as a program on this machine.
- [x] Routes and commands.
- [x] The escape tests (`-m docker`, `tests/docker/test_escape.py`): passed on this machine's Docker on 2026-10-13 (the folder only; no internet by address, name or IPv6, no host, no other workspace; the edge answers; the limits apply).

### Task 3: The agent (M5, first slice)

**Files:** `clank/components/agents/` (`component.py`, `opencode.py` its adapter, `service.py`, `cli.py`: bare `clank`,
`clank agent`); tests.

**Interfaces:**
- The agent program kind of adapter (decision 0011), `AgentProgram`: its command in the container, the environment it
  runs with, and its configuration (a file in the container's home) for a model reached at a URL, with that model's
  context and output limits. OpenCode first: one provider, `clank`, at the edge (`http://edge:<gateway port>/v1`),
  with one model, `agent` (the role the gateway routes), the running preset's limits; nothing outside the folder, no
  web tools (there is no route out); OpenCode's own updates, downloads, plugins, sharing and file watcher off.
- `Agents.prepare(workspace, program)`: the configuration written into the workspace's container (the platform's
  `put_file`, as the container's user), and the command a terminal runs (`exec_argv` with the program's environment).
  Route `POST /agents/prepare` {workspace, program}.
- `clank work [FOLDER] [--yes]`, and a bare `clank` runs it (design 0004 §1's choice, as recommended): the service
  (started in the background when it does not run), Docker (started when it is stopped), the workspace (opened), a
  model in the main slot (when nothing runs: its last configuration that worked, else `daily 262K`), the agent's
  configuration, then the agent in this terminal.

**Steps:**
- [x] The kind and the OpenCode adapter: its configuration and environment, tested.
- [x] `put_file` and `exec_argv`'s environment on the platform (Docker Desktop's with `docker exec --interactive`, its
  input given; the fake's in memory); `run_answer` takes the input.
- [x] The agents component: `prepare`, its route; the limits from the gateway's route for `agent`, else a fallback said.
- [x] `clank work` and the bare `clank`, each step followed; tested with the terminal's command recorded, not run.

### Task 4: The VS Code window

**Files:** `clank/components/agents/vscode.py` (the separate instance, its extensions and settings), `clank code`;
the extension's agent terminal (`vscode/src/agent.ts`); tests.

### Task 5: Responsiveness, records and version

Containers' limits; the desktop-stall probe (`tools/stall.py`) and its use in the real tests; ROADMAP, the designs'
statuses, the plans index; version 0.3.0.

## Rulings made while building

- **Task 1: the gateway listens on 18210** (`config/gateway.json`), next to the engines' 18200, on 127.0.0.1 only. Cost
  if wrong: a setting to change.
- **Task 1: every role is the main slot's in this slice**; the routes name `agent` (what Clank's OpenCode asks for), and
  any other name goes to the main slot too (decision 0008). Roles with their own slots and sampling are the rest of M3.
  Cost if wrong: none until a second slot exists.
- **Task 1: the gateway outlives the service**, as engines do: the service adopts it after a restart (its identity in
  `state/gateway.json`), so a restart cuts no request; `clank gateway stop` stops it, and `start: false` keeps the
  service from starting it (what the test services use, `tests/support/served.py`). Cost if wrong: a gateway left
  running after `clank stop`, by design.
- **Task 1: requests and answers are kept whole by default** (design 0002 declined metadata-only records, for
  transparency), each field cut at 256 KiB, credentials never, 14 days. Cost if wrong: disk use, a setting.
- **Task 1: the gateway follows the routes by asking the service every second** rather than following its event
  stream: simpler, and a missed event cannot leave it wrong for long. Cost if wrong: one small request a second.
- **Task 1: the runtime's service re-exports `EngineHost` and `ProcessIdentity`, and gives `translate_request`**, so the
  gateway reaches the local host and the adapters only through it (decision 0019). Cost if wrong: none.
- **Task 1: timings use `perf_counter`**: on Windows `monotonic` advances in 15.6 ms steps, which made a first token
  read as 0 ms. Cost if wrong: none.
- **Task 2: a container command's refusal is raised in Docker's own words**, so the kernel gains `run_answer` (exit
  status, output and errors; `run_command` is now built on it). Cost if wrong: none.
- **Task 2: the edge joins the internal network after it starts** (`docker network connect --alias edge`) rather than
  by a second `--network` at `docker run`, which needs Docker Engine 25 or newer. Cost if wrong: one more command.
- **Task 2: the container's defaults come from what the platform has** (`docker info`: on Docker Desktop, its virtual
  machine's CPUs and memory), half the CPUs and a quarter of the memory. Cost if wrong: a setting per workspace.
- **Task 2: the container commands are tested on a scripted `docker` until Docker may run** (the owner uses the PC);
  their recordings of the real `docker` come with the escape tests. Cost if wrong: a difference found then.
- **Task 2: each workspace has an internal network of its own**, which the edge joins as `edge`, rather than one
  network for all: design 0004's escape list asks that another workspace not answer from inside. Cost if wrong: one
  network per workspace, and the edge on each.
- **Task 2: a workspace's folder is refused when its container would see more than it**: a drive's root, the user's
  home folder, a folder that holds CLANK_HOME (its secrets) or one inside it. Cost if wrong: the owner opens a folder
  inside the one refused.
- **Task 2: the record's field is `path`** (a settings kind already has `folder()`, where its records are kept). Cost
  if wrong: a name.
- **Task 2: a stopped container made from an older image is made again** (its home is a volume, so nothing is lost); a
  running one is left as it is until it stops. Cost if wrong: an old image runs until the workspace is stopped.
- **Task 2: the sandbox image's tag is the checksum of its folder** (`clank-sandbox:<12 hex>`), so any change builds a
  new one and an image of that tag is the one the files make. Cost if wrong: none.
- **Task 2: `clank docker status` prints no empty line when Docker is stopped** (a deferred minor of M0, fixed while the
  file was open).
- **Task 3: verified on this machine (2026-10-13)**: the sandbox image built (OpenCode 1.19.0), KVMem loaded, and
  OpenCode in a workspace's container fixed a bug in the folder's file through the edge, the gateway and KVMem in
  11 s (`opencode run`); the edge reaches the gateway though it listens on 127.0.0.1 only (Docker Desktop's
  `host.docker.internal`).
- **Task 3: the agents reach the container only through the workspaces' service** (`container_of`, `put_file`,
  `exec_argv`), which raises `WorkspaceUnavailable` in its own words, so no component imports another's adapters.
  Cost if wrong: none.
- **Task 3: when no model runs, `clank work` loads the main slot's last configuration that worked, else `daily
  262K`**, and the agent's limits fall back to 32,768 and 8,192 tokens (said) only when the load was not waited for.
  Cost if wrong: a setting for the default preset.
- **Task 3: a bare `clank` opens the console on the folder's page** (the owner, 2026-10-13: "running 'clank' should
  start the menu, not the actual opencode terminal ... the point of opening the menu first is to make sure everything
  is configured properly before beginning to work"); design 0004 §1 says so now. `clank work` stays the shortcut.
- **Task 3: the folder's page is the agents component's** (`This folder`, F4), so it reaches the workspaces and the
  gateway through their routes only; two read-only routes close the gaps it found: `GET /workspaces/folder?folder=`
  (whether the folder may be a workspace and why not, its workspace and container, whether the image is built) and
  `GET /agents/plan` (what OpenCode would be given). Cost if wrong: two routes to move.
- **Task 3: `a` starts OpenCode only when every item is ready**, and else says which are not, with their keys; `g`
  does every missing step in order (Docker, the workspace, a model, the gateway), each followed on the page, and a
  question a step asks (the image's build) is answered there. Cost if wrong: a key that does the steps and starts.
- **Task 3: the console hands its terminal to OpenCode and takes it back** (`clank.console.terminal`, Textual's
  `App.suspend`): Ctrl+C is OpenCode's meanwhile, nothing may leave the console suspended, unread keys are dropped and
  a resized terminal is said to the console. Headless (tests, snapshots) the program runs without stepping aside; no
  test may run one in its terminal (`tests/conftest.py`). Cost if wrong: the console restarts after OpenCode instead.
- **Task 3: the keys bar shows F1 among the pages' keys**, as the console's design says (the keys that act anywhere);
  F2 to F4 are beside their pages in the menu, so the bar fits 80 columns again. Cost if wrong: none.
- **Task 3: one preset picker** (`clank.console.pick.preset_choices`) for the Models, Launch options and folder pages.
- **Task 4: opening the window is an operation** (`agents.vscode`, lock `vscode`), not the command line's own work, so
  the console's `c` and `clank code` share it, and Home shows its steps while the first one installs extensions. Cost
  if wrong: none; the window itself is started on its own and not waited for.
- **Task 4: on Windows Clank runs `Code.exe` with the `cli.js` that `code.cmd` names**, read from `code.cmd` each time
  (VS Code's updates move it into a folder named after the build), and opens windows with `Code.exe` itself: cmd.exe
  would read `&`, `%` or `^` in a folder's name. Cost if wrong: a VS Code whose `code.cmd` reads differently is not
  found; `config/vscode.json` (program) names it then.
- **Task 4: the agent opens on start only where `clank.agent.openOnStart` is on**, which Clank writes into its own
  window's settings: the extension may be installed in the main VS Code too, where it must not start the agent. Cost if
  wrong: none.
- **Task 4: VS Code's own AI features off is `chat.disableAIFeatures`** (VS Code 1.104 and later), with telemetry off,
  extensions checked for updates but not updated unasked, no welcome page, and a title that says Clank; each written
  only when missing, so the owner's own changes stay, and a settings file with comments is left as it is. Cost if
  wrong: one setting to add.
- **Task 4: Clank's extension is the `.vsix` built from Clank's folder** (`uv run python -m tools.vsix`), installed when
  its version is not the one in the window; its version is 0.2.1 for the agent's terminal. When it is not built the
  window opens without it, saying how to build it. Cost if wrong: a packaged Clank (not a checkout) will need the
  `.vsix` in its package (Task 5, with the release).
- **Task 4: no restricted mode in Clank's window** (the owner's first try, 2026-10-14: the window opened in restricted
  mode, so VS Code turned off every extension not declared safe there, Clank's included, and OpenCode never opened):
  the window's settings turn workspace trust off (`security.workspace.trust.enabled`), since it opens only folders the
  owner chose and the agent's container sees nothing else; Clank's extension (0.2.2) also declares it works in
  restricted mode, for a window where the owner turns trust back on. Verified live: the trial folder opened with
  OpenCode beside the files, on daily 262K. Cost if wrong: a folder from elsewhere opened in Clank's window is trusted;
  one setting turns trust back on.
- **Task 4: tests never find the real VS Code** (`tests/conftest.py`): a test names a fake `code` (`tests/fakes/code.py`)
  in its settings, a program of its own that records what it is asked and opens no window.

