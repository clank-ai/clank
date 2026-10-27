# Design 0004: working in a folder (the first working slice of M3, M4 and M5)

The owner (2026-10-13): "I would like to have the ability to just run 'Clank' in any directory and it will default the
workspace to that directory and configure the container required for me to begin work", then "prioritize getting M3,
M4, and M5 working as long as M2 is not required for me to begin working. There are some design choices that we need
to make here, in particular the integration of the model with VS code is very important, meaning that I need a very
easy way to interact with the model in VS code which will likely be using an opencode terminal open somewhere in here.
Since the version of VS code we are going to run with this model side by side is pretty distinct from my main version
of VS code with all my extensions and other settings, I want you to make sure this version of VS code is stripped of
anything unnecessary to my work", and "any stuttering or massive slowdown of my PC is not acceptable for the final
product, since I need to use my PC for other work."

This design takes the smallest part of milestones M3 (the gateway), M4 (workspaces and containers) and M5 (agents) that
lets the owner start working, moves it ahead of M2 (llama.cpp and trials, not needed to begin), and adds the VS Code
window the owner asked for (which design 0002 placed in M6). The parts were designed in design 0001 §6 (the gateway)
and design 0002 §1-§2 (workspaces, sandboxes, the edge, agents plugged in by adapters, decision 0011); this document
applies them to the first slice. Decisions it rests on: 0008 (the role is the requested model name), 0011 (agent
programs are plugged in, OpenCode first), 0013 (one service), 0020 (enforce where it can be stopped), 0033 (Clank needs
nothing from the prototype).

**Status:** written 2026-10-13, every section *proposed*. As with design 0003, the owner asked
for it to be built now; what it decides that the owner said they want to decide together is marked **Choice** with a
recommendation, built as recommended so the owner can try it, and changed if the owner chooses otherwise.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner does | Proposed 2026-10-13 |
| 2 | The gateway, first slice | Proposed 2026-10-13 |
| 3 | Workspaces, the image and the container | Proposed 2026-10-13 |
| 4 | The agent: OpenCode in the container | Proposed 2026-10-13 |
| 5 | The VS Code window | Built 2026-10-14 (the agent's status bar item waits) |
| 6 | The desktop stays responsive | Proposed 2026-10-13 |
| 7 | NInfer's context | Retired 2026-10-13 with NInfer (decision 0034) |
| 8 | What the tests must prove, and what waits | Proposed 2026-10-13 |
| 9 | The console: easy to use, dynamic, the machine on the right | Built 2026-10-14; revised 2026-10-26 (a GPU whose handle its driver dropped) |
| 10 | A project's own software and MCP servers | Built 2026-10-14 as proposed; verified on a simulator |

## 1. What the owner does

```
cd C:\work\my-project
clank                      the menu (the console), on this folder's page: what is ready, what is not, and the agent
clank work                 straight to the agent, here: OpenCode in this folder's container, in this terminal
clank code                 the Clank VS Code window on this folder, the agent beside the files
```

`clank` opens the console on the page of the folder it was started in. The page says, item by item, what working there
needs and whether it is ready: Docker, the folder's workspace and its container, Clank's sandbox image, a model in the
main slot, the gateway, and the agent's configuration (and, as they come, its MCP servers). Each item that is not
ready has its key, and every setting can be changed from the console before work begins; one key then starts the
agent: the console steps aside while OpenCode runs in the same terminal, and comes back when OpenCode is left.

The first time in a folder, getting ready makes it a workspace (a record naming the folder; nothing is written in the
folder itself), builds Clank's sandbox image if it is not built yet (once, a few minutes, asked first), starts the
folder's container and makes sure a model runs. The next time it reuses all of it: the container starts in a second
or two, and OpenCode's sessions are kept per workspace. Leaving the agent stops nothing that costs anything but the
agent; `clank workspace stop` stops the container, and `clank workspace list | remove` manage the records (removing
one never touches the folder). `clank work` does every step at once, for when nothing needs looking at first.

**Decided: what a bare `clank` does.** The owner (2026-10-13), when it first opened the agent directly: "running
'clank' should start the menu, not the actual opencode terminal. Opening OpenCode should come from inside the Clank
menu ... the point of opening the menu first is to make sure everything is configured properly before beginning to
work with the model in the folder that I have opened it in." So `clank` is the console on the folder's page, and
`clank work` the agent at once.

## 2. The gateway, first slice

Design 0001 §6, the part the agent needs:

- **Its own process**, supervised by the service (it starts with the service and is adopted after a restart, as engines
  are), listening on `127.0.0.1:18210` for the host's tools and reached by containers only through the edge (§3). A
  restart of the service or the console cuts no request in flight.
- **One dialect first**, OpenAI Chat Completions (`/v1/chat/completions`, `/v1/models`), streaming included.
- **Roles by model name** (decision 0008): OpenCode asks for `agent`; the gateway finds the role's slot (`agent` and any
  unknown name: `main`) and its engine, and sends the engine the model name it answers to.
- **Each engine's own request fields** (design 0001 §6.3), from its adapter: thinking on or off is
  `chat_template_kwargs.enable_thinking` for KVMem, and a request in the other common form (`enable_thinking`) reaches
  it in that one (NInfer, retired by decision 0034, refused llama.cpp's form with an error). A field an engine refuses
  is translated or left out, and the record says which.
- **Records** (design 0001 §6.5): one JSON line per request in `logs/traffic/<day>.jsonl` (who asked, the role, the
  slot and preset, the timings, the tokens, the error), the streamed answer in pieces; secrets never.
- **A switch holds requests** (design 0001 §6.4): while the slot switches, requests wait up to their limit.
- **An engine that breaks off** (2026-10-14: KVMem crashed three times in a night, each time cutting OpenCode's
  request): a request the engine broke off before answering anything is sent again once the role's slot is served
  again (the runtime restarts a crashed engine), on the same stream, within the hold; one broken off after answering
  part, or whose slot is not served again, ends with an error event that says so (`engine_broke_off`).
- **What it does now** (the owner's request, 2026-10-14: the home page should say what is happening at any moment):
  each request in flight, with what it waits for (its slot while a model loads, the first token while the engine reads
  the prompt, or the rest of the answer), its time, its tokens and its speed, and how the last one went (its tokens,
  time and speed, the engine's own figures when it gives them, or why it failed), at `GET /activity`; the service
  passes it on at `GET /gateway/activity`. The console's home page shows it under "happening now", beside the
  operations that run, each with its step and the last line it wrote; "what runs" adds the gateway, the GPU's memory,
  Clank's workspace containers and the folder the console was started in (F4 gets it ready).
- **A loop guard** (the owner, 2026-10-18, after a `bash` call repeated closing tags for 16,384 tokens and OpenCode kept
  them in the session: "go ahead and implement the loop guard in the gateway"; *built 2026-10-18*): each streamed
  answer is read as it comes, each part apart (its thinking, its text, each tool call's arguments, a new call afresh);
  when a part's newest stretch compresses (zlib) to under 6% of its size (2,000 or 8,000 characters of the thinking and
  the text; 2,000 of a tool call, since files written from a template compress as far as a loop over 8,000), the answer
  repeats itself, and the gateway closes its connection to the engine (which stops writing it) and ends the stream with
  an error event that says what repeated and how to let such an answer through (`model_looped`), in words without
  numbers, so OpenCode does not retry it (it retries an error whose words hold 500, for instance); OpenCode then leaves
  that answer out of the session's later requests. The record keeps all of it (`looped`: what, over which stretch, how
  far it compressed; `error`); the Requests page marks it `looped`. Settings: `loop_guard` (on), `loop_windows` (2,000
  and 8,000), `loop_tool_windows` (2,000), `loop_ratio` (0.06), applied when the gateway restarts (`clank gateway
  restart`). A longer or reworded repeat still runs to the answer's limit. Measured on 1,566 real answers and three
  real loops ([2026-10-18](../measurements/2026-10-18-repetition-in-answers.md)); decision 0040.
- **A full context** (2026-10-20, after a session stopped at the context's limit): an engine's refusal of a request
  its context cannot hold (KVMem's 400, "prompt + max_tokens exceeds n_ctx", on which OpenCode 1.19 stops) is answered
  as OpenCode reads a context overflow (400, code `context_length_exceeded`, "the context was full: ..."), so it
  compacts the session and goes on; the record and the Requests page mark it `full` (design 0012 §4.1, decision 0090).
  Any other refusal is passed on as the engine gave it.
- Later in M3: other dialects, role sampling, queues with priorities, inline completion in VS Code.

## 3. Workspaces, the image and the container

- **A workspace** is a record (`config/workspaces/<name>.json`): its folder, its container's resources, and when it was
  last used. Its name comes from the folder's (`my-project`, made unique).
- **Clank's sandbox image** (`clank-sandbox:<version>`) is built from a Dockerfile in Clank's package: Ubuntu 24.04,
  Python 3.12 with pip and venv, Node.js 22, git, build tools, ripgrep, and OpenCode at a pinned version; a user
  `agent` (uid 1000). It is Clank's own (decision 0033). Other tools (Lean, TeX) are not in it yet: **Choice**,
  recommended: a second image layer per kind of work, added when first needed (`clank image add lean`).
- **The container** (`clank-<home id>-<workspace>`, Clank's labels) mounts the workspace's folder at `/workspace` and
  nothing else of the machine; it runs as `agent`, with no added capabilities, `no-new-privileges`, a process limit,
  and CPU and memory limits (§6). Its network is an internal Docker network of its own (`clank-<home id>-<workspace>-
  net`) with no route out, so another workspace does not answer from it either.
- **The edge** is one small container (`clank-<home id>-edge`), the only one on a network that reaches the host, and
  joined to each workspace's network as `edge` when that workspace opens: it forwards the gateway's port and nothing
  else. From inside a workspace, nothing but the edge answers. (Built 2026-10-13: one network per workspace rather
  than one shared, when the escape tests were written; their list asks that other workspaces not answer.)
- **Choice: the network.** Recommended for the first slice: the model only (no package downloads from inside; the
  image carries the common tools). Network grants (PyPI, GitHub pull and push) are M7.
- Escape tests (design 0002 §3.3, M4): no file outside the folder can be read, through symlinks and subprocesses
  included; nothing but the edge answers from inside (direct addresses, names, IPv6, the host, other workspaces).

## 4. The agent: OpenCode in the container

- Clank writes OpenCode's configuration in the container's home (a volume per workspace, so sessions survive): one
  provider, Clank's gateway through the edge, with one model, `agent`, whose context and output limits are the running
  preset's (KVMem's 262,144 for `daily 262K`), the context less a margin kept free for one step's tool results
  (16,384 by default, `config/opencode.json`: decision 0089, 2026-10-20), so OpenCode compacts a conversation before
  the engine refuses it.
- MCP servers: the user's (`clank mcp`), and the folder's own `.mcp.json` once the owner allows it (design 0002
  §2.11: a project's items are offered, never trusted). A server runs inside the container, so its command must be
  there (in the image or the folder); M8 gives each its own container.
- `clank` (in a terminal) runs `docker exec -it` OpenCode's terminal interface in the container, in the workspace. Modes
  (plan, ask, auto) and the program's questions on every client are the rest of M5.

## 5. The VS Code window

The owner's main VS Code is untouched. Clank runs the same VS Code program as a separate instance with its own settings
and extensions folders (`--user-data-dir` and `--extensions-dir` under `CLANK_HOME/vscode/`), so nothing of the main
one's extensions, settings or profiles leaks in (VS Code's profiles share some state, which is why a separate instance
rather than a profile; PROTOTYPE.md).

- **`clank code [folder]`** sets the instance up the first time (installs its extensions), then opens the folder in it.
  In a Clank workspace, Clank's extension opens the agent in a terminal beside the files (the editor area's right half;
  **Choice**, recommended there, rather than the panel at the bottom), with a status bar item for the model and the
  agent.
- **As built (2026-10-14)**: `clank code [folder]` and the console's `c` (on This folder, F4) first do every step the
  agent needs that is not done (Docker, the workspace, a model), then run the operation `agents.vscode`: the instance's
  settings, its extensions (Clank's from `vscode/clank-<version>.vsix`, built from Clank's folder, and the list's
  missing ones; one that cannot be installed is said and tried again next time), then the folder in a window. Clank's
  window turns on the extension's setting `clank.agent.openOnStart`, so the extension starts OpenCode in a terminal
  beside the files when the window opens (trying again while the service comes up; a reloaded window that kept its
  terminal gets no second one); `Clank: Start the agent beside the files` does it on demand. The status bar shows the
  model (design 0003 §8.3); the agent's own item waits.
- **The agent at the right edge (2026-10-15, the owner: "OpenCode should always open to the right of the screen, where
  the model lives")**: the extension opens the agent's terminal in a new editor group at the right edge (VS Code locks a
  group that holds a terminal, so files never open in it). When the window opens with the agent's group elsewhere (a
  window from before), and whenever a group opens to its right, the extension moves the agent's group back to the right
  edge and gives the keyboard back to the group that had it. A reloaded window is checked by its tabs as well as its
  terminals: VS Code revives a kept terminal after the extension starts, so only its tab is there at first (a second
  agent was started before 0.5.2). On Windows Clank runs VS Code's own program (`Code.exe`, with
  the command line `code.cmd` names), never `code.cmd` itself, so a folder's name never goes through cmd.exe.
- **One OpenCode window per workspace (2026-10-16, the owner: "There really should be only one opencode terminal open
  at a time, but this should be a toggle in the menu")**: found live, five OpenCode windows ran in one workspace, two
  of them terminals VS Code had relaunched with their saved command, whose port another OpenCode already had, so no
  mode switch could reach the window in front of the owner. Now the workspace's record has `one_window` (on unless
  turned off; `w` on This folder switches it, and the mode row beside `r` says which): opening OpenCode in a terminal
  (`agents/prepare`: VS Code's Start the agent, the console's `a` and `c`) first closes every OpenCode window in the
  container (`pkill -f` on `opencode --port`, ended after 10 s if it has not; `opencode serve`, the phone's, is left),
  and VS Code disposes its other agent terminals. The agent's terminal is transient (extension 0.6.1): VS Code never
  revives it with an old command; a reloaded window starts the agent afresh (its sessions are kept), so a long run
  should not be followed through a reload. Off, each opening adds a window, and the mode switches reach the one where a
  message was last seen.
- **Its extensions** (`config/vscode.json`, the owner edits the list): Clank's; Python, Pylance, the debugger, Ruff and
  Jupyter; Lean 4; LaTeX Workshop; a PDF viewer; Rainbow CSV; Markdown All in One and Mermaid; Even Better TOML.
  **Choice**: recommended exactly these, taken from the owner's main VS Code (39 extensions) by what research and coding
  use; left out: the other AI assistants (they would compete with Clank's agent), themes and icon packs, GitLens,
  remote development, spelling, diagrams and the rest. A theme can be added.
- **Its settings**: telemetry off, VS Code's own AI features off (the agent is Clank's), extension updates checked but
  not applied unasked, a window title that says Clank, long lines wrapped in every editor and in a change's diff (the
  owner, 2026-10-16). Each is added only when missing, so a value the owner changed stays.

## 6. The desktop stays responsive

A product requirement from the owner, not a test convenience. What Clank does:

- **Measures it.** A desktop-stall probe (frame-to-frame latency of a small window that redraws ten times a second,
  as Windows composes it) runs with each engine's trial and with the real-engine tests; a preset whose prompt reading
  stalls the desktop beyond a limit is marked so. Facts so far: with Windows' hardware-accelerated GPU scheduling off
  (the owner's setting since 2026-10-08) prompt reading caused hiccups of up to 0.5-0.7 s on KVMem; decoding never did.
- **Leaves the desktop room on the GPU.** A preset's fit keeps a margin for the desktop (it grows as the owner works:
  0.95-1.86 GB on 2026-10-13); an engine that would leave less is refused before it starts, as now, and the margin is a
  setting.
- **Keeps its own work below the owner's.** Containers get CPU and memory limits (half the cores and a quarter of the
  memory by default); Clank's background work (builds, downloads, its own checks) runs at a low priority; an engine's
  threads in WSL run at a lower priority than the desktop's.
- **Choice: the desktop on the motherboard's GPU.** The discrete card drives the monitors today. Moving them to the
  motherboard's outputs (the processor's integrated GPU) would remove model-induced stutter entirely and give the
  engine the whole 16 GB (§7). The cost: an integrated GPU may not drive high-refresh monitors at their full rate, and
  3D work would render on the discrete card and pass through it. Recommended to try; the owner decides.

## 7. NInfer's context (retired)

*Retired 2026-10-13 with NInfer ([decision 0034](../decisions/0034-ninfer-is-retired.md)); kept as the record of why
its 131,072 tokens could not fit here.*

The two setups were compared on this machine on 2026-10-13: [the measurement](../measurements/2026-10-13-ninfer-and-kvmem.md).

NInfer's README and release notes give 131,072 tokens of context and KV capacity on an RTX 5080 16 GB. Checked
2026-10-13:

- **Versions.** The newest release is v1.5 (2026-09-28): the same model file, +4.5% prompt reading and +2.3% decoding,
  built and validated with CUDA 13.4.92 on driver 615.71.09. This machine has driver 610.88, which runs CUDA 13.3, so
  Clank runs v1.4 (decision 0031). A CUDA 13.4 build may still run on driver 610.88 (CUDA's minor-version
  compatibility, the kernels being compiled for this GPU), and if it does not run, the driver update is the owner's
  to make. A recipe for v1.5 that tries it was drafted but not shipped: the owner asked (2026-10-13) to retire NInfer
  if it proved much less useful than KVMem, and [the measurement](../measurements/2026-10-13-ninfer-and-kvmem.md) found
  it so. Since v1.5 the project has worked on serving two requests at once and on testing, not on memory.
- **Why 131,072 does not fit here.** Every 131,072-token result is on a 5080 that drives no display: the release's own
  validation left 886 MiB free after starting, and the one WSL2 report (NInfer issue #39) used the integrated GPU for
  the display and had 99 MiB to spare. The KV cache for 131,072 tokens is 2.26 GiB; beside a desktop that takes
  0.95-1.86 GB of the same GPU there is room for about 44,000-64,000 tokens, whatever the version.
- **What gets 128K here.** The desktop on the integrated GPU (§6), then NInfer v1.5's full profile. Without that, the
  largest context that fits beside the desktop of the moment: Clank's fit check computes it, keeping the desktop's
  margin (a preset whose context is `fit`).

## 8. What the tests must prove, and what waits

- Gateway: a request reaches the slot's engine with the engine's own model name and fields; a streamed answer streams;
  a canceled request stops generating; a switch holds requests; every request is recorded, with no secret.
- Workspaces and containers: the escape tests (§3); a container is Clank's by its labels; restarting the service
  adopts running containers; a removed workspace leaves its folder untouched.
- Agent: OpenCode starts in the container, reaches the model through the edge and the gateway, and edits the folder;
  its sessions survive a restart of the container.
- VS Code: the instance is separate from the main one (its folders, its extensions); `clank code` opens the folder with
  the agent beside it.
- Responsiveness: the stall probe's limit for the default presets; the containers' limits are applied.
- **Waits** (the rest of M3-M6, then M7-M8): other dialects, role sampling and queues, inline completion; plan, ask and
  auto modes enforced by the container; the program's questions on every client; reviewing and accepting changes in VS
  Code; network grants; the tool hub; M2 (llama.cpp, trials, the console's layout and keys).

## 9. The console: easy to use, dynamic, the machine on the right

The owner, 2026-10-14: the menu must be extremely easy to use, visually appealing in the terminal, more dynamic, and
built so it is easy to change; "a place that is constantly showing us the CPU, GPU, disk, RAM, etc., on the right side
of the terminal"; and an indicator that cycles while things load, as OpenCode's and Claude Code's do.

- **The machine's meters**: the service reads them every second (`clank/components/machine/meters.py`): the CPU (as a
  whole and per logical processor), the memory and page file, the disks' and the network's rates, each fixed drive's
  space, and each NVIDIA GPU's use, memory, temperature and power from NVIDIA's management library (NVML, which comes
  with the driver), read through ctypes: no program is started each second and no dependency is added. The last five
  minutes are kept (`GET /machine/meters`) and each reading is sent live (`machine.meters`, never stored). A GPU whose
  handle its driver dropped (an update, a reset: an access violation, which ctypes raises as `OSError`) is read again
  from a fresh start of the library, or else left out of the readings until the service starts again, said once in the
  log, while the rest of each reading goes on (revised 2026-10-26: every reading failed, each second for hours, its
  traceback logged each time).
- **The panel on the right** (`clank/console/machine.py`, `MachineColumn`, the machine column since design 0011's R2,
  two panels): "machine" (bars colored by load, the last minute as
  sparklines, each CPU thread as a cell in its load's color, the GPU's clocks and fan, VRAM, each drive, the network,
  each workspace's container's CPU and memory from `docker stats` every ten seconds on a thread of its own, and the
  busiest and largest processes every three seconds, added 2026-10-15 when the owner found the panel said too little;
  46 columns wide from 170 columns of terminal) and "clank now" (operations with their step,
  model requests in flight with their speed, the last request). It shows when the terminal is at least 130 columns
  wide; F5 shows or hides it at any width. Each meter is a function in a list.
- **Spinners**: while an operation runs, a model request is in flight or a page works on its own steps, a spinner
  turns ten times a second in the header, the panel, Home's "happening now" and the step being worked on; nothing is
  redrawn for it otherwise.
- **The header** (`clank/console/header.py`): a pill per part that runs, a dot in its state's color: the service and
  how long it has been up, Docker, the model in the main slot, the gateway and its requests in flight, the questions
  waiting.
- **Easy to change**: each part of the header and of the panel is a small function in a list, every color is a theme
  variable (`$success`, `$warning`, `$error`, `$accent`), and sizes and the panel's breakpoint are in `clank.tcss` and
  `ClankConsole`; `docs/console.md` says where each thing is and how to change it.

## 10. A project's own software and MCP servers

The owner, 2026-10-14, about a simulator (a Python package with an MCP server for agents): the work is both studies
run with it and changes to it, its full runs take many hours, and the owner wants to open the model inside VS Code in
an OpenCode terminal, and to configure the project's MCP server in the menu before launching the model. So a
workspace's agent must be able to run the folder's own
software (its tests, its scripts, its MCP server), which the sandbox image does not hold and the container cannot
download (§3: no route out).

- **Its software** (`clank/components/workspaces/setup.py`): a workspace has a *setup* command that installs the
  folder's own software into its home, in a Python virtual environment at `~/.venv` (the home is the workspace's volume,
  so it is installed once and survives the container). Clank proposes it from the folder's files: a `pyproject.toml`
  gives `pip install -e '.[dev]'` (its `dev` extra when it has one, else `.`), a `requirements.txt` gives
  `pip install -r requirements.txt`; the owner may write another (`clank workspace setup --command`, or `e` on the
  folder's page), and it is kept in the workspace's record.
- **Choice: where the setup reaches the internet.** Recommended and built: in a container of its own, made for the
  setup and removed after it (`docker run --rm` of the sandbox image, the folder and the home mounted as in the
  workspace's container, the same user and limits), on Docker's default network, which reaches the internet; the
  workspace's container, where the agent runs, never does. The operation `workspaces.setup` asks first (it names the
  command and says it downloads), each line of the install goes to its log, and the record keeps the command that last
  ran to its end, so the folder's page says whether the software is installed and with what. Network grants from inside
  (M7) stay as designed; this is the one way out, run by Clank, not by the agent.
- **The image** puts `~/.venv/bin` first on the `PATH` and has a `python` command, so the agent, its terminal and the
  MCP servers it starts find the folder's programs without being told.
- **Threads**: the workspace's container (and its setup's) sets `OMP_NUM_THREADS`, `NUMBA_NUM_THREADS`,
  `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` to its CPUs, so numerical code starts as many threads as it may use
  (Docker's limit does not change how many CPUs a program sees: a 16-CPU container saw 32, 2026-10-16) and the desktop
  keeps the rest (§6). Every program in it gets them, not only the agent: a shell, a script, an MCP server checked by
  Clank. The agent is started with them too, for a container made before the container set them (it takes them once
  it is stopped and opened again).
- **MCP servers for the agent**: the ones the agent gets are written into its configuration when it starts (OpenCode's
  `mcp`, each a local command run in the container). The user's own servers (`clank mcp add`) are given to every
  workspace's agent unless the owner takes one away for a workspace; a folder's own servers (its `.mcp.json`, which
  other harnesses read too) are offered, never trusted (design 0002 §2.11): each is given once the owner allows it for
  that workspace, and the record keeps a fingerprint of the entry as allowed, so an entry changed since is not given
  until it is allowed again. A server reached by address (`http`, `sse`) is not given: nothing but the model is
  reachable from the container until network grants (M7). A server's command must be there in the container (the
  image's, or the folder's software above).
- **Checking a server where it runs**: `mcp.check` of a workspace's server runs it in the workspace's container
  (`docker exec --interactive`, no terminal) and asks it for its tools, so the folder's page says what the agent will
  find before it starts.
- **The folder's page**: a step "Its software" (installed with what, or the key `e` that installs it; `g` installs it
  too, asked first), and under "then work" each MCP server with whether the agent gets it and its tools once checked;
  `m` picks a server and gives it or takes it away (a given one is checked at once when the container runs).
- **Long runs** (hours): a run the agent starts with the folder's own command line in the background goes on after the
  agent ends, while the workspace's container runs (it stops only with `clank workspace stop`, Docker, or the machine);
  an MCP server's background jobs end with the agent that started the server. Seeing such runs on Home, and keeping
  them across a container's restart, waits for a later section. `docs/studies.md` is the practice for the user.
- **As built, 2026-10-14**, on a simulator (a Python package with an MCP server and a Windows `.venv` in its
  folder): the setup installed it with its `dev` extra in 36 s; its MCP server answered in the container with its 10
  tools; OpenCode ran a small run through them (capabilities, estimate, run) with 16 threads. VS Code's Python extension typed the folder's Windows `.venv` activation into the agent's terminal, which
  OpenCode took as a prompt: Clank's VS Code window now has the Python extensions' terminal activation off (§5).

