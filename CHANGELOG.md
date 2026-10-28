# Changelog

Every version of Clank, newest first: what it adds, what it fixes, and what it changes, in plain words. The one-line
installer installs the latest release; from the release after 0.3.0b1, `clank update` updates to the next one (or pulls
a clone). Problems known now are in
[docs/ISSUES.md](docs/ISSUES.md), open and fixed.

## Unreleased: since 0.3.0b3

The next release. Its version is set when it is tagged; until then, a clone has it (`git pull`, or `clank update`).

### Added

- **`clank setup`**: what Clank needs on this computer, item by item, and what to do about each one that is not done
  (design 0028): Docker installed, running and usable by your account (on Linux, whether it starts with the computer),
  Clank's service, the sandbox image, a model that answered a test request, a folder that is a workspace, and Clank's
  VS Code window. `clank setup --check` changes nothing and works without the service; the installers end with it. While
  something it needs is missing, `clank` opens the console on its **Setup** page (decision 0148), whose model item opens
  Add a model and folder item This folder; a Docker Desktop not started yet and a sandbox image a Clank update made
  stale are This folder's to put right, as before, so they open This folder. `clank setup` then offers each fix in order, showing its exact command and asking
  first: Docker Desktop started; on Linux `sudo systemctl start docker`, `sudo systemctl enable docker` and `sudo
  usermod -aG docker $USER`, run in your terminal, where sudo asks for your password itself (Clank never sees it), then
  a log out and in after joining the group; Clank's service started; a model added (in the cloud, on this computer's
  GPU, or both); the folder opened as a workspace. `--yes` does every fix that needs no administrator rights and lists
  the others. The sandbox image is built in the background meanwhile, so the first folder opens at once. On the Setup
  page, `s` starts Docker Desktop, `t` runs the command shown in the terminal and `b` builds the sandbox image.

## 0.3.0b3: Linux with Docker Engine, and the extension in every release (2026-10-27)

Clank on a Linux computer without Docker Desktop: the one-line installer sets Docker Engine up from Docker's own
packages (asking first), and the agent's container reaches its model through a socket only it mounts. Tested on every
push on GitHub's Ubuntu runner with Docker Engine. And no build for Clank's VS Code window: each release carries its
extension. From 0.3.0b2, `clank update`; from 0.3.0b1, run the installer again.

### Added

- **Clank's VS Code window without building its extension**: each release now carries Clank's VS Code extension, with
  its SHA-256. Installed with the one-line installer, `clank code` (or `c` on This folder) downloads the extension of
  its own release the first time, checks it against that SHA-256, keeps it and installs it: no Node and no build. A
  clone still builds its own.
- **Linux without Docker Desktop**: Docker Engine, the system's service from Docker's own packages, runs the workspaces'
  containers (design 0014, decision 0070). Clank reads its state from systemd and never starts, stops or wakes it: where
  it is stopped, `clank work`, `clank code`, the console and `clank doctor` say the command to run (`sudo systemctl
  start docker`), and an account outside the docker group is told how to join it. The adapter is chosen on its own
  (`"adapter": "auto"` in `config/docker.json`, the default; Docker's view says which and why). A workspace opens only
  where Docker can limit its container's memory, unless `allow_unlimited_memory` is set, and a folder the agent's user
  (1000) may not write is refused, saying how to let it. A workspace's own network gives this computer no address on it,
  so nothing listening here answers its container.
- **On Linux, the gateway's socket**: besides 127.0.0.1, the gateway listens on a socket, `gateway.sock`, and the
  agent's proxy on `proxy.sock`, in a folder of their own outside CLANK_HOME (`~/.cache/clank/<home id>`, the owner's
  alone; `socket_folder` in `config/gateway.json` moves it). `clank gateway status` names it. It is how the agent's
  container reaches the model on Docker Engine, where no new address is opened for it (decision 0071, 2026-10-27).
- **On Linux with Docker Engine, the agent reaches the model**: the edge, the workspaces' one door, mounts that folder
  read-only and forwards the gateway's port and the proxy's to the sockets, running as you. Opening a workspace asks
  the gateway's health through the edge and makes the edge again when it does not answer; a folder that holds the
  socket folder, or is inside it, is not opened as a workspace. Docker Desktop's way is unchanged.

## 0.3.0b2: the installer, updates, and the agent beside VS Code (2026-10-27)

The second public beta: the one-line installer and `clank update`; the agent beside VS Code; Clank for iPhone over
your tailnet; network access through Clank's proxy; flows that steer themselves; a new chat's first word in about a
second on frontier 262K; and the fixes of the owner's first full days of use and of a code review. From 0.3.0b1, run
the installer again; from this release on, `clank update` updates Clank.

### Added

- **The one-line installer**: `irm https://clank-ai.github.io/install.ps1 | iex` on Windows, `curl -fsSL
  https://clank-ai.github.io/install.sh | sh` elsewhere. It installs uv, Git and Docker Desktop when they are missing,
  then Clank's latest release, and runs `clank doctor`.
- **`clank update`**: `clank update --check` says how Clank was installed and what is newer, asking only GitHub (or
  your clone's own remote); `clank update` updates it the way it was installed; `--dry-run` says each step first.
- **`clank autostart on|off|status`**: Clank's service, and Docker, start when you sign in to Windows.
- **The agent beside VS Code**: the agent panel, the conversation beside OpenCode's terminal, live from one stream (your
  message shows at once, the model's words as it writes them); the model's readout in the status bar (its speed, the
  context used, the GPU); files the agent opens for you; figures found by what they show; images seen through Clank's
  vision model; artifacts (pages of results the agent makes); boards (canvases of figures, LaTeX and notes you and the
  agent share); jobs (long computations the agent starts and watches); and, in extension 0.10.3, a check of the agent's
  way to the model that says what is wrong and how to fix it.
- **LaTeX**: TeX in the workspace's container, LaTeX Workshop building there, checks of citations, references and
  numbers, a change's PDF beside its diff, and comments on a PDF answered in the source.
- **Flows that steer themselves**: the orchestrator (a model that steers a run on its own), jobs a box runs detached
  with its clock stopped while it waits, and side tasks.
- **Network access for the agent**: the internet only through Clank's proxy, by your allowances per workspace and host;
  a host the agent asks for waits while Clank asks you; named sets (packages, papers); `clank network log` and the
  console's Network view show every exchange.
- **Clank for iPhone**, an installed app over your tailnet: installed once by scanning a QR the console shows, live
  from one stream; Now, Flows, and a session with the Guide and its context; a launch screen that says what it waits
  for; `clank remote status` and `clank doctor` say why the page will not load when it does not (the iPhone offline on
  the tailnet, Funnel making the PC's name public, iCloud Private Relay bypassing Tailscale's DNS).
- **Presets**: the sampling each gives its engine, and a fallback loaded when its engine crashes.
- **VS Code on another computer**, through Remote-SSH.
- **[docs/ISSUES.md](docs/ISSUES.md)**: every confirmed problem, what you see, and what is next.

### Fixed

From the owner's first full day of use and an end-to-end test of a new user's first hour (2026-10-26):

- `getaddrinfo EAI_AGAIN edge`, then OpenCode crashing: the edge container, made again, had left older workspaces
  without their way to the model. It now rejoins every workspace's network, and Clank repairs a missing one within
  seconds.
- `clank code`, `clank work` and the console waited 22-32 s before anything; an agent's start took 16 s: both are now a
  second or less.
- A new OpenCode window waited a minute before its first answer (its plugin install was held by the proxy); a new chat
  on a fresh OpenCode server failed with "timed out": both fixed (6 s to a first answer on a cold server, measured).
- The service could stop answering on Windows, and neither `clank stop` nor `clank serve` could help: fixed, and
  `clank stop` now ends a service that holds its lock without answering.
- A model switch failed with `PermissionError` on `gateway.json`, and a gateway restart could start no gateway: fixed.
- A closed OpenCode window's sessions were read again forever (half a CPU core), and requests waited 10 s on a dead
  OpenCode: fixed.
- The phone: its tab bar sat higher on short tabs; its first screen took 12 s: fixed.
- The phone: the word "null" stood at the top of every tab, the header's "● live" was a green block, and the page
  you add the app from ran its lines down the whole screen and offered iOS an icon it does not take: fixed
  (2026-10-27).
- Removing a workspace while OpenCode was open in it gave no warning and left tracebacks in the service's log:
  the question now says that what runs in its container ends, and the service lets the workspace go quietly.
- Words a new user did not understand: the clients connected, the models not loaded, the doctor's line, the tool
  server's path, a refused request's fields, a waiting call's raw input, UTC times among local ones, log lines without
  times.
- The runtime's `fallback_preset` setting did nothing: with no model that had worked yet, `clank work`, `clank code`
  and This folder loaded the first preset that could load, or `daily-262k`. They now load the one it names (2026-10-27).
- A new chat waited 10 to 37 s for its first word on the local model, while it read OpenCode's system prompt and
  tools again. Frontier 262K's KVMem build now carries a patch that keeps a snapshot of the model's state at the
  system prompt's end ([decision 0146](docs/decisions/0146-kvmem-keeps-a-snapshot-at-the-end-of-the-system-prompt.md)):
  a new chat's first word comes in 0.5 to 1 s. The same patch keeps KVMem from resuming a conversation from
  another one's snapshot. Clank does not build KVMem: [frontier 262K's page](docs/models/frontier-262k.md) says
  how to build it with the patch (2026-10-27).
- One workspace's agent could, through the gateway, start a job in another workspace's container, read its flow or
  open its files, and a web page could send the gateway requests: each agent's call now carries its workspace's key
  and acts for that workspace only, and the gateway answers only Clank's own programs. Close and start again any
  agent's window opened before this update, so its tools get the key (2026-10-27).

### Changed

- Scientific Python in the sandbox image; Clank's programs mounted read-only into each container instead of copied.
- The agent is told to ask one short question with options when a request could mean different things, and to show a
  figure it made.
- The phone app looks as its design drew it (and as the website shows it): rounded cards and buttons, the first answer
  filled, the tab on screen in blue, its quieter words readable on every ground (WCAG AA), and its buttons' words
  capitalized like every other client's.
- The console's menu stands on the page's ground, as its design and the website draw it, so the page you are on shows
  clearly in it (Textual drew it on a lighter ground, where the highlight barely showed).
- VS Code (extension 0.10.4): Clank Night, the console's colors, now reaches the model's readout under the agent panel,
  and the readout colors each part of the context as the console does (by what it is, not by its place in the bar);
  every page takes its colors from one sheet; an artifact's bar is drawn in the window's theme.

## 0.3.0b1: the first public beta (2026-10-21)

Clank is a local LLM suite: an AI coding and research assistant that runs on your own hardware, or with a cloud model
through an API key. This is its first public release. Start with [docs/getting-started.md](docs/getting-started.md).
Free and open source under the AGPL-3.0.

### What works (on Windows)

- **The console** (`clank`): every page of the menu, This folder (getting a folder ready in one key), the questions
  waiting for you, history, operations, records, and **Add a model**.
- **Cloud models through OpenRouter**: one agreement, a key kept in Clank's secrets folder, a live list of models, a
  test request, each workspace asked once, and cost shown everywhere with optional daily and monthly limits.
- **Local models** with llama.cpp and KVMem in WSL: presets, slots (the main one, completion and vision), checks of
  what fits the GPU, and one setup written up whole in [docs/models/](docs/models/README.md).
- **Workspaces**: a Docker container per folder, which sees only that folder and reaches only the model, with the
  folder's own software and MCP servers.
- **The agent**: OpenCode, in review mode (each change waits for you) or auto, the Planner (plans in Markdown, never
  runs anything) and `/implement`.
- **The gateway**: every request recorded, the loop guard, cost.
- **The Monitor** (F10): the agent's context window, its steps and tool calls, and the Guide to stop, pause, note,
  compact, undo and drop.
- **Flows**: a larger piece of work as boxes (plan, verify, tasks, integrate, your review), each a fresh session,
  built by talking it through with the model.
- **The VS Code extension**: reviews of the agent's changes, the figure annotator, completion, the Notion review, and
  your flows' gates; built from this repository (see getting started).
- **Notion**: the agent reads your shared databases and proposes changes you review before anything is written.
- **The phone page**, over your tailnet only (Tailscale), a device paired with a code: what runs, the questions
  waiting for you, and the figures the agent sends.

### Not yet

- A one-line installer and an update command: Clank is installed from a clone with uv, and updated with `git pull`.
  (Both came after this release: see Unreleased.)
- Linux and macOS: not tested yet; on Linux, the agent's container reaching the gateway is still being built.
- Local models need building: the engine is built in WSL and the model files downloaded, step by step.
- The "daily 262K" preset needs a vision projector Clank cannot download; run it with its vision off, or another
  preset.
- Push alerts to the phone, and the iPhone app (being redesigned); the phone page works in the phone's browser.
- Milestones still to design are listed in [docs/ROADMAP.md](docs/ROADMAP.md).
