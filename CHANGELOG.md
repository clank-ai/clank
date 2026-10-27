# Changelog

Every version of Clank, newest first: what it adds, what it fixes, and what it changes, in plain words. The one-line
installer installs the latest release; from the release after 0.3.0b1, `clank update` updates to the next one (or pulls
a clone). Problems known now are in
[docs/ISSUES.md](docs/ISSUES.md), open and fixed.

## Unreleased: since 0.3.0b2

The next release. Its version is set when it is tagged; until then, a clone has it (`git pull`, or `clank update`).

### Added

- **Clank's VS Code window without building its extension**: each release now carries Clank's VS Code extension, with
  its SHA-256. Installed with the one-line installer, `clank code` (or `c` on This folder) downloads the extension of
  its own release the first time, checks it against that SHA-256, keeps it and installs it: no Node and no build. A
  clone still builds its own.

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
