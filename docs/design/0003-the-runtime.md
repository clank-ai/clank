# Design 0003: the runtime (M1)

Milestone M1 of [design 0002 §3.3](0002-the-foundation.md#33-the-milestones-after-m0): models that Clank starts,
watches, switches and stops on this machine, with KVMem and, moved in from M2 at the owner's request, NInfer. It is the
design that §3.1 of design 0002 asks for at the start of a milestone; the parts it builds were designed in
[design 0001](0001-runtime-and-console.md) §1-§4 and §7, which this document applies to this machine and to M1's
scope. Started 2026-10-12. Decisions it rests on: [0004](../decisions/0004-sampling-per-role.md),
[0006](../decisions/0006-runtime-service-with-adapters.md), [0007](../decisions/0007-settings-in-readable-files.md),
[0008](../decisions/0008-role-is-the-requested-model-name.md),
[0009](../decisions/0009-test-a-configuration-in-a-trial-run.md),
[0010](../decisions/0010-serving-setups-are-plug-and-play.md),
[0013](../decisions/0013-one-service-control-and-data-planes.md) and the kernel's (0014-0021); it adds
[0030](../decisions/0030-engines-run-on-hosts.md) and [0031](../decisions/0031-ninfer-follows-the-driver.md), and
later [0119](../decisions/0119-sampling-and-gpu-layers-are-launch-options-left-unset.md) (§4.1).

## Goal

The owner (2026-10-12): "move on to M1 but make sure you are implementing the runtime core, KVMem, and NInfer (either
https://huggingface.co/ninfer-5080 or whatever version is perfectly suited for my machine)." At the end of M1 the owner
can see what runs on the GPU and what it costs, and load, unload, check and switch KVMem and NInfer presets from the
console, VS Code and `clank`; install NInfer by its recipe and download its model, both asked first and verified; and
bring the prototype's profiles over as presets.

**Status:** written 2026-10-12 by Claude at the owner's instruction to build M1, which the owner gave before reading
it. Every section is *proposed*; it is built now, as the owner asked, and the owner reviews it as it is built (the
owner's way: build, then iterate on what can be run). Where it decides something new, a decision record says so.

*2026-10-13: NInfer is retired ([decision 0034](../decisions/0034-ninfer-is-retired.md)), after [the
measurement](../measurements/2026-10-13-ninfer-and-kvmem.md): KVMem serves the model. What this design says of NInfer
stays as the record of what was built and why, each such part marked.*

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What M1 delivers, and what moved | Proposed 2026-10-12; built at the owner's instruction |
| 2 | Where engines run: hosts | Proposed 2026-10-12; built at the owner's instruction (decision 0030) |
| 3 | Records | Proposed 2026-10-12; built at the owner's instruction |
| 4 | Engine adapters: KVMem and NInfer | Proposed 2026-10-12; built at the owner's instruction; NInfer's retired 2026-10-13 (decision 0034) |
| 4.1 | Sampling and the GPU's layers | Added and approved 2026-10-21 (the owner: make these settings visible; decision 0119); built 2026-10-21 (plan s37) |
| 5 | NInfer on this machine | Retired 2026-10-13 (decision 0034); built 2026-10-12 (decision 0031) |
| 6 | A slot, and switching it | Proposed 2026-10-12; built at the owner's instruction |
| 7 | Installs and models | Proposed 2026-10-12; built at the owner's instruction |
| 8 | The console, VS Code and the commands | Proposed 2026-10-12; built at the owner's instruction |
| 9 | Testing, and the order of work | Proposed 2026-10-12; built at the owner's instruction |

## 1. What M1 delivers, and what moved

*Proposed 2026-10-12.*

| The owner can | Behind it |
| --- | --- |
| See the main slot: its preset, engine, model and state, how long it has run, its GPU memory beside the desktop's | The runtime component's state, the console's models page, VS Code's status bar (§8) |
| Load, unload and switch presets for KVMem and NInfer | Operations of the Clank service (§6), from any client |
| Check a preset before anything starts: validity, memory fit, the engine accepts every flag | `runtime.check` (§6.5), design 0001 §3.6 and §3.8's *check* |
| Install NInfer and download its model | Recipes and downloads as operations that ask first (§7) |
| Use the KVMem build the prototype already uses, and the prototype's profiles as presets | Adopting an install (§7.1); `clank import` (§7.4, removed 2026-10-13 by decision 0033) |
| Read each option of a preset: its value, where it comes from, what it maps to | The launch options page (§8.2) |

**What moved.** NInfer comes into M1 from M2 (the owner's words above). llama.cpp, trials and the test suites (smoke,
speed, memory, context, quality) stay in M2 with the tests page. Sampling per role and the sessions using a slot need
the gateway, which sees every request (decision 0004; design 0001 §5.3), so their console entries move to M3. The
console's own settings (its layout and keys, M0's deferred item 18) close M1 if M1's core leaves room, else they move
to M2 by a recorded ruling.

**What its tests must prove** (design 0002 §3.3's list for M1, with NInfer's): Clank stops only what it started; a
failed switch returns to the last configuration that worked; after a restart of the service, a running engine is
adopted, not restarted; what each engine supports is read for its version and its launch options; KVMem and NInfer pass
one contract; an install or a download asks first and verifies what it got; a switch never starts an engine while
another program holds the GPU memory it needs or its port.

## 2. Where engines run: hosts

*Proposed 2026-10-12 (decision 0030).*

Design 0001 §7.1 put the service and the engines inside WSL on Windows. M0 built the service natively on Windows,
where the console, VS Code and Docker Desktop run, and M0.3 left the question to M1. The answer: the service stays on
Windows, and an engine runs on a **host**, a new kind of adapter (design 0002 §2.10). A host can run a command, start a
long-running process with its output in a log, tell whether that process still runs, signal it, and read a file. Two
hosts in M1:

| Host | Where it runs a process | On this machine |
| --- | --- | --- |
| `local` | On the service's own machine, when the service runs on Linux | CI, a Linux workstation |
| `wsl` | In a WSL distribution, through `wsl.exe -d <distro>`; WSL forwards the engine's port to Windows' `127.0.0.1` | KVMem in `Ubuntu-22.04`, where it is built today; NInfer in `Ubuntu` (24.04), whose packages meet NInfer's build (§5) |

SSH to another computer (design 0001 §7.6) is a third host, later.

- **A Clank folder on each host.** Engines and models stay on the host's own disk: loading a 16 GB model across WSL's
  bridge to Windows' disks is much slower (design 0001 §7.2). Each host has its folder, `~/.clank` by default, with
  `engines/` and `models/`. Logs and state stay in CLANK_HOME on Windows: an engine's output goes to
  `CLANK_HOME/logs/processes/`, written through WSL's view of Windows' disk (small, and the service reads it there).
- **Process identity** (design 0001 §4.6): the process id inside the host, its start time (from `/proc`) and its
  command line, kept in the slot's state. Clank signals a process only when all three match, and a running engine is
  adopted when the service starts again only when all three match.
- **A process outlives the call that started it**: the host starts it in a session of its own (`setsid`), so neither
  `wsl.exe` returning nor the service stopping ends it (design 0001 §1: closing a client, or restarting the service,
  does not stop the model).

## 3. Records

*Proposed 2026-10-12.*

Settings are files (decision 0007), state is in the database (decision 0014), and both are kinds of record defined once
(decision 0015). The runtime component owns:

| Kind | Sort | Where | Holds |
| --- | --- | --- | --- |
| `preset` | Settings | `CLANK_HOME/config/presets/<id>.json`; Clank's own in `clank/defaults/presets/` | Design 0001 §3.7: name, engine, engine version, model, the options that differ from the defaults, notes; and the slot it is for (`main`) |
| `host` | Settings | `CLANK_HOME/config/hosts/<id>.json` | A host's adapter (`wsl`, `local`), its distribution, its Clank folder |
| `model-file` | Settings | `CLANK_HOME/config/model-files/<id>.json` | Where a model's file is on a host, when the user keeps it outside the host's `models/` (the prototype's KVMem model is one) |
| `runtime` | Settings (single) | `CLANK_HOME/config/runtime.json` | The slots (M1: `main`), the engines' port (18200 until M3, design 0001 §9.2), the model name an engine that checks it answers to (by default the model's id in the catalog; added 2026-10-13 for NInfer, which refuses any other), the *tight* threshold (500 MiB, design 0002 §3.4), how long a start may take, how often health is checked |
| `slot` | State | the `slots` table | What runs in a slot: its state and since when, the preset and its options, the process identity, the host and port, why it changed; the last configuration that worked |
| `install` | State | the `installs` table | Each engine installed: setup, version, host, folder, how it was installed (recipe, adopted), what verified it |
| `launch` | State | the `launches` table | Each start: preset, plan, memory estimated and measured, how long it took, how it ended; what the fit check learns from (design 0001 §3.6) |

Clank's own knowledge ships in the package: `clank/catalog/models/<model>.json` (each model's files in each format,
their sources, sizes and checksums, the facts read from them) and `clank/recipes/<setup>/<version>.json` (§7). A
`preset` record changes only through the settings rules (decision 0007); a change to the preset a slot runs applies at
its next start, and the console says so (design 0002 §2.2, `ON_CHANGE`).

## 4. Engine adapters: KVMem and NInfer

*Proposed 2026-10-12.*

An engine adapter (design 0001 §2) is one module per serving setup, with the same interface:

- `versions`: the engine versions it was written for, each with what it supports (requests at once, vision,
  speculation), since a version's support is read, not assumed (design 0002 §2.10).
- `options(version)`: every launch option, each with the fields of design 0001 §3.1 (key, label and help, kind, range
  or choices, default, scope, `maps_to`, memory effect, `requires`, `tested`).
- `plan(preset, model file, host, port)`: the exact command line, environment and folder, and a memory estimate as a
  breakdown (weights, KV cache, buffers, the engine's own overhead), corrected by what earlier launches measured.
- `ready(line)`, `health(url)`: when the engine is up (its own words in its log, then its API listing the model).
- `memory(log)`: what the engine says it allocated, read from its log.
- `check(host, install)`: the program is there, is the version the adapter knows, and accepts each flag the plan
  uses (read from its `--help`).

Shared ideas keep shared keys, so a preset can move between engines where the same option exists: `context`,
`kv.type`, `spec.draft_tokens`, `vision`, `vision.max_tokens`, `thinking.budget`, `cuda_graphs`, `max_output`.

**KVMem/llama.cpp** (`kvmem-llamacpp`), v0.16.0-rc1, the build the prototype uses (commit `db4bc22`). Its options come
from its `--help`: `context` (`-c`), `max_output` (`-n`), `kvmem.budget` (the exact-attention window on the GPU),
`kvmem.gen_reserve`, `kvmem.method`, `kv.type` (`--kv-dtype`), `spec.type` and `spec.draft_tokens`, `vision` (off, on
the CPU, on the GPU: `--mmproj` with or without `--no-mmproj-offload`) and `vision.max_tokens`, `thinking` and
`thinking.budget`, `batch`, and `cuda_graphs` (the environment variable `GGML_CUDA_DISABLE_GRAPHS`; off by default, the
owner's decision of 2026-10-08 after three crashes on an MTP verify step). It runs one request at a time. It is ready
when its log says `listening on` and `/v1/models` names the model's file; its log reports the model's, the KV cache's
and the compute buffers' sizes. Versions 0.17 (several conversations, up to four requests at once) and 0.18
(NInfer-backed) are later recipes of the same adapter (design 0002 §3.4 asked M1 to choose: 0.16.0-rc1, because it is
what runs here and is proven; the others need building and their own trials).

**NInfer RTX 5080** (`ninfer-rtx5080`), `ninfer-serve` of the `toddballinger/ninfer-5080` releases (§5). Its options
come from its `--help`: `context` (`--max-context`), `ninfer.kv_capacity` (`--kv-capacity`), `ninfer.prefill_chunk`,
`kv.type` (`--kv-dtype`), `spec.type` (`--spec mtp`) and `spec.draft_tokens`, `cuda_graphs` (`--no-cuda-graph`),
`ninfer.embedding_host`, `vision` and `vision.max_tokens`, `thinking.budget` (`--default-thinking-budget`),
`ninfer.prefix_checkpoints`, `ninfer.max_concurrency` and its pending queue. It is ready when its log reports its
startup and `/v1/models` answers; its startup report gives the free memory after startup and the planned slack,
which the fit check compares with its estimate. *Its adapter was removed on 2026-10-13 (decision 0034).*

### 4.1 Sampling and the GPU's layers

*Added and approved 2026-10-21 (the owner: make these settings visible: "Let's go ahead and fix this gap in Clank so
that these settings are visible"); decision [0119](../decisions/0119-sampling-and-gpu-layers-are-launch-options-left-unset.md).
Built 2026-10-21 ([plan s37](../plans/s37-sampling-and-gpu-layers.md)).*

KVMem's server takes more than §4 listed: how many of the model's layers it puts on the GPU (`-ngl`, 99 by default:
every layer) and the sampling a request gets when it does not say (`--temp`, `--top-p`, `--top-k`, `--min-p`,
`--presence-penalty`, `--frequency-penalty`, `--repeat-penalty`, `--seed`). Its sampling defaults are Qwen3.8-27B's
model card's, one set with thinking and one without, chosen per request: temperature 1.0 / 0.7, top_p 0.95 / 0.80,
presence penalty 0 / 1.5, and top_k 20, min_p 0, frequency penalty 0 and repeat penalty 1 in both. A request gets its
mode's defaults, then the flags given at launch, then its own fields (its server, `tools/kvmem-chat-sampling.h` and
`tools/llama-kvmem-server.cpp`), so a flag holds for both modes and a request's own value wins over it. None of this
was an option, so the sampling in effect was neither seen nor changeable from Clank: on 2026-10-18 a runaway answer
ran with a presence penalty of 0 that nothing showed.

- **The options.** `gpu_layers` (`-ngl`, 0 or more) and `sampling.temperature` (0 to 2), `sampling.top_p` (0 to 1),
  `sampling.top_k` (0 or more, 0 for no limit), `sampling.min_p` (0 to 1), `sampling.presence_penalty` and
  `sampling.frequency_penalty` (-2 to 2), `sampling.repeat_penalty` (more than 0) and `sampling.seed` (0 to
  4,294,967,295), each with the bounds KVMem's server checks. A value below 0 for `gpu_layers` is refused: the engine
  would read it as every layer. llama.cpp's adapter (b11588) gets the same sampling keys, read from its `--help`
  (`--temp` 0.80, `--top-p` 0.95, `--top-k` 40, `--min-p` 0.05, `--repeat-penalty` 1, `--presence-penalty` and
  `--frequency-penalty` 0, `--seed` -1 for random), bounded as each value's meaning bounds it (a share from 0 to 1, a
  count or a temperature of 0 or more, a repeat penalty above 0; the presence and frequency penalties, which its help
  does not bound, unbounded); there a model file may carry
  its own temperature, top_p, top_k, min_p and repeat penalty (`general.sampling.*`), which a flag overrides. Its CPU
  build has no GPU, so it gets no `gpu_layers`.
- **Unset unless a preset sets one.** None of these options has a Clank default. Left unset, the engine receives no
  flag and keeps its own defaults, per mode (and, for llama.cpp, the model file's), so every preset launches exactly
  as before. Set, an option is always passed, even at a value one of the engine's defaults has, since it then holds for
  both modes (and over a model file's own). `gpu_layers` at 99 is the engine's own and passes nothing.
- **Shown with the engine's own default.** An option may say in words what the engine does when it is not given
  (`engine_default_words`), where one value cannot say it: "1.0 thinking, 0.7 not thinking" for KVMem's temperature,
  "0.80, or the model file's own" for llama.cpp's, "99 (every layer on the GPU)". The Launch options page (F2) shows
  those words for an option left unset, and beside one that is set the default it replaces; a line under the options
  says that a request's own values win. The Presets page and `clank preset show` list the sampling in effect. The
  Requests page (F7) shows the sampling fields a request sent, each beside the preset's.
- **The memory estimate with fewer layers.** With `gpu_layers` below the layers KVMem offloads (66 for Qwen3.8-27B and
  the Swift files: its log says "offloaded 66/66 layers to GPU"; the catalog's `layers`), the weights on the GPU are
  estimated as that share of the catalog's `gpu_weights_mib`, layers taken as equal in size; the rest is said to be in
  system memory, where the CPU reads it for every token and decoding is much slower. The KV cache and the buffers stay
  counted whole on the GPU, the safe side: whether KVMem v0.16 keeps a layer's cache on the GPU when the layer is in
  system memory, and retrieves well then, is not measured. The estimate says it is an estimate; a model whose catalog
  entry has no `layers` keeps its weights whole and says so.
- **Left for later.** The per-role sampling of decision 0004, which the gateway would set on each request, is still to
  build. KVMem logs the sampling each request ran with (`KVMEM_TRACE sampling ...`); reading it, to show what ran
  rather than what was asked and set, waits for a reason to read the engine's log per request.

## 5. NInfer on this machine (retired)

*Proposed 2026-10-12 (decision 0031); retired 2026-10-13 (decision 0034), its build and its model taken off this
machine with `clank engine uninstall` and `clank model remove` (§7.5).*

"Whatever version is perfectly suited for my machine." What this machine is, as read on 2026-10-12:

| | This machine | NInfer v1.5 (current) | NInfer v1.4 |
| --- | --- | --- | --- |
| GPU | RTX 5080, 16 GB, also driving the desktop (about 2 GB in use with no model) | RTX 5080, display elsewhere | RTX 5080, display elsewhere |
| CUDA the driver runs | 13.3 (driver 610.88) | Built and qualified with 13.4.92, driver 615.71 | 13.3.73 (its reproduction guide) |
| Compiler | GCC 15.2.0 from conda-forge, in the engine's own environment (decision 0032) | GCC 15.2 | GCC 15.2 |

- **The version: v1.4, built with CUDA 13.3.73**, the newest toolkit this driver runs and the one v1.4 was validated
  with. v1.5's notes say it moves to CUDA 13.4.92 and retunes one kernel for 13.4; a 13.4 build needs a newer driver,
  and v1.5 built with 13.3 would be a combination its author never qualified. v1.5's recipe comes with its adapter
  version, once the driver runs CUDA 13.4, and `clank doctor` says what a driver update to 615.71 or newer would allow.
  Built in an environment of its own with the compiler and the toolkit its reproduction guide names (decision 0032),
  v1.4 deviates from "exactly as published" only in FFmpeg's and libcurl's versions, recorded with the install
  (decision 0010).
- **The fit: the published profile cannot fit here.** It keeps a 131,072-token context and KV capacity with vision,
  and starts with about 800 MiB to spare on a GPU that drives no display; here the desktop holds about 2 GB. A WSL2
  user whose display runs on another GPU reports it fitting with 99 MiB to spare (its project's issue 39). So the
  known-good preset for this machine keeps every published option but the KV capacity (and vision off at first),
  whose largest safe value the first measured launch gives; it is recorded as a deviation with the preset's notes, and
  the console shows "context 131,072, KV capacity N" (not "true 128K", which the project defines as both 131,072).
  *Revised 2026-10-13 by the first launches:* v1.4 holds the whole context in its KV cache for each request at a time
  (its sequence planner sizes the smallest cache by the context), so the KV capacity cannot be lowered alone: the
  context is what has to fit. Beside this desktop (1.6 GB) NInfer has 1,655-1,669 MiB free after its weights and the
  CUDA context; its reservation is 352.6 MiB plus 18,496 bytes a token (the MTP head's KV included). The known-good
  preset, *NInfer 44K fitted*, sets the context and the KV capacity to 45,056 tokens (524 MiB of planned slack); with
  `auto`'s 1 GiB of headroom only about 15,600 tokens would fit.
- **The model**: `ninfer-5080/Qwen3.8-27B-RTX5080` at revision `e23a3301eed6`, `qwen3_8_27b.ninfer`, 16,461,267,456
  bytes, SHA-256 `c4a7e9ab593a7f42d58208fa0065d67a82d61921107686cc9f6ed1ec6b050e21` (unchanged since v1.2).

## 6. A slot, and switching it

*Proposed 2026-10-12.*

A slot has the states of design 0001 §4.1: `stopped`, `starting`, `ready`, `stopping`, `failed` (`busy` comes with
the gateway in M3, which sees requests). Each change is recorded with its reason.

### 6.1 Load, unload, switch

Each is an operation (design 0002 §2.4) under the slot's lock, with the steps of design 0001 §4.2:

| Operation | Steps |
| --- | --- |
| `runtime.load` | plan, start, health, measure |
| `runtime.unload` | stop |
| `runtime.switch` | plan, stop, start, health, measure; on failure, return |

- **Plan.** The preset is checked (§6.5); a preset that does not fit is refused unless the request says to start it
  anyway, and the operation's log shows the plan: the command line and the memory breakdown.
- **Before a start.** If the engines' port is taken, or the GPU's free memory is short of the plan because another
  program uses it, the start is refused, naming that program (by its window title or process, when it can be read)
  and never stopping it (design 0001 §4.6 and §9.2). The prototype's own KVMem on port 18200 is the common case.
- **Health.** The engine's log says it is up and its API lists the model, within a time limit scaled from its earlier
  starts (at first: KVMem 300 s, NInfer 300 s); then a request of a few tokens must come back.
- **Measure.** The GPU memory in use after the start, less what was in use before it, is the engine's; it is kept with
  the launch beside the estimate, and the next estimate for that engine on that host is corrected by the difference.
- **Return.** If a switch's start or health fails, Clank stops what it started, starts the last configuration that
  worked, and says why the new one failed, with the engine's last log lines and its reading of them ("out of GPU
  memory: the plan needed 15.6 GB, 14.2 GB was free").

### 6.2 Crashes

A watcher checks each running slot every few seconds: its process, and its health every 30 seconds. A process that
ended, or three failed health checks in a row, makes the slot *failed* with the reason and the log's last lines. Clank
starts the same configuration again once if it had been ready for ten minutes or more, and says so; a second crash
within an hour leaves it failed and asks the user (design 0001 §4.4).

### 6.3 Adoption

When the service starts, each slot whose state says an engine runs is checked by its process identity: alive and the
same, it is adopted (the slot stays `ready`, nothing restarts); gone, the slot becomes `stopped` with the reason
"stopped while the service was not running".

### 6.4 The last configuration that worked

The preset and options that last reached `ready` and answered the tiny request, with their time. A failed switch goes
back to it, and the service offers to start it when the service starts and the slot is empty.

### 6.5 Check

`runtime.check` starts nothing: the preset is valid for its engine's version (kinds, ranges, `requires` and
`conflicts`); the model's file exists on the host with its expected size (and, once per file, its checksum); the
engine's program is installed at that version and accepts each flag (its `--help`); and the memory fit: the plan's
breakdown beside the GPU's total and what the desktop uses now, with the verdict *fits*, *tight* or *does not fit*.

## 7. Installs and models

*Proposed 2026-10-12; §7.1 changed the same day by decision 0032.*

### 7.1 Recipes

A recipe is a readable file per setup and version (design 0001 §7.4, `clank/recipes/<setup>/<version>.json`): what it
fetches, its steps (each a command with what it makes, so a step already done is skipped), the program it makes, and
how it differs from the engine's own release. An engine is built in an environment of its own under the host's Clank
folder (decision 0032): nothing is installed with root, and nothing is written outside that folder. An install is an
operation: it shows what it will do (what it fetches and about how much, each command), asks first (a question,
answerable from any client), runs each step with its output in the operation's log, on half the cores at a low
priority so the computer stays usable, checks that the program it made lists every flag its adapter can give, and
records the install.

- **KVMem v0.16.0-rc1**: adopting the existing build, `~/src/kvmem-llama.cpp` at commit `db4bc22`, is an install of
  kind *adopted*: Clank checks its version and help and records where it is; it does not rebuild or move it.
- **NInfer v1.4** in `Ubuntu` (24.04): micromamba (a single program, checked against its SHA-256) makes an environment
  from conda-forge with the compiler and the toolkit its reproduction guide names (GCC 15.2.0, CUDA 13.3.73), CMake,
  Ninja, FFmpeg, libcurl and git, each at a pinned version; then the source at the release's commit is built with the
  guide's own commands into `~/.clank/engines/ninfer-rtx5080/v1.4/`. The program finds the environment's libraries by
  itself (its run path), and the GPU's through WSL. *Retired 2026-10-13 (decision 0034): the recipe and the build are
  gone.*

### 7.2 Model files

A download is an operation too: it says the size and the disk it leaves, asks first, resumes after an interruption,
can be limited in speed, says its speed as it goes, and verifies the checksum before the file is used (design 0001
§7.5). The host's own Python fetches it, so it goes straight to the host's disk. Files go to the host's `models/`; a
file whose checksum differs is kept aside as `<file>.bad`; a file the user already has elsewhere is recorded where it
is (a `model-file` record), with its checksum verified once.

### 7.3 The catalog

`clank/catalog/models/qwen3.8-27b.json` holds the model's GGUF IQ3_S file with its vision projector (what KVMem
reads), with their sources, sizes and checksums. (It held NInfer's `.ninfer` file too, until decision 0034.)

### 7.4 The prototype's profiles (removed)

*Removed 2026-10-13 by decision 0033: Clank needs nothing from the prototype.* `clank import <registry.json>`
wrote one preset per profile of the prototype's registry (design 0001 §9.2-9.3): the engine, the model and the options
its arguments set, and a note naming the profile it came from. The presets it wrote on the owner's machine stay as the
owner's.

### 7.5 Taking a model or an engine off a host

*Added 2026-10-13 at the owner's request ("the ability to delete models from Clank (with the ability to restore them
by downloading them again and having the configurations saved)"); plan [m1.7](../plans/m1.7-removal-and-retiring-ninfer.md).*

- **A model's files** (`clank model remove NAME --host H`, all of its files there unless `--format` or `--role` names
  some; the operation `runtime.remove`): what Clank put in the host's models folder is deleted, with a `.part` or
  `.bad` left of it and the folders that leaves empty, after a question that lists each file, what it frees and the
  download that brings it back. The catalog keeps the model and every preset stays, so the model comes back as it
  was. A file the user keeps elsewhere is only forgotten (its `model-file` record), never deleted.
- **An engine** (`clank engine uninstall SETUP --version V --host H`; `runtime.uninstall`): one Clank built by its
  recipe is deleted with its folder after a question that says what it frees and that `clank engine install` builds
  it again; one adopted where it was is only forgotten, its folder kept.
- Both refuse what a running slot uses (unload it first), and neither deletes anything outside the host's Clank
  folder: the host's own script checks every path. The console's Providers and models page does the same with `x` and
  `u`.

## 8. The console, VS Code and the commands

*Proposed 2026-10-12.*

### 8.1 The models page (the menu's Models entry, now built)

What it could look like with KVMem running:

```
 ─ main ───────────────────────────────────────────────────────────────────────────────────────────
 daily 262K   Qwen3.8-27B IQ3_S   KVMem/llama.cpp v0.16.0-rc1 (WSL Ubuntu-22.04)   READY 2h14m
 port 18200   started by you (console)   process 41873
 GPU memory   engine 13.6 GB (estimated 13.4) + desktop 1.9 GB = 15.5 of 15.9 GB    FITS (0.4 GB to spare)
 ─ last switches ──────────────────────────────────────────────────────────────────────────────────
 11:42  switched to daily 262K in 41 s
 l load a preset   u unload   w switch   c check   ? explain
```

### 8.2 Presets, providers and models, launch options

- **Presets**: each preset with its engine, model, fit now, and its last start (time, how long, memory); Enter
  switches to it, `c` checks it, `v` shows its file.
- **Providers and models**: each engine with its versions installed, where, and how it was installed; each model
  with its files on each host, sizes, and whether the checksum was verified; `i` installs an engine by its recipe,
  `d` downloads a model, `x` removes a model's files from a host and `u` removes an engine (§7.5).
- **Launch options**: the highlighted preset's options, each with its value, its source (design 0001 §3.5: the
  engine's default, the catalog's recommendation, the preset), the flag it maps to and what it does; the exact command
  line the preset produces. Editing a value is M2's (with trials); M1 shows them and `e` opens the preset's file.

### 8.3 VS Code

The status bar's Clank item shows the main slot (`$(server) Clank · daily 262K`), and a new command, *Clank: Switch
model*, picks a preset and starts the switch. Questions an install asks reach VS Code as any question does.

### 8.4 Commands

```
clank model status                     the slots: preset, engine, state, memory
clank model load "daily 262K"          start a preset in the empty main slot
clank model unload                     stop what the main slot runs
clank model switch "fast 128K"         stop what runs, start this one; back to the last that worked if it fails
clank preset list | show NAME | check NAME
clank engine list | install SETUP --version V --host H | uninstall SETUP --version V --host H    §7.5
clank model download qwen3.8-27b --format gguf --host H
clank model remove qwen3.8-27b --host H                              its files there; settings kept, §7.5
```

## 9. Testing, and the order of work

*Proposed 2026-10-12.*

- **Unit**: each adapter's options and its plans for the known presets (the exact command lines), the fit
  arithmetic, the slot's states, the recipes' steps.
- **Contract**: every engine adapter against what its engine printed at its version (`--help`, startup logs), recorded
  under `tests/fixtures/<setup>/<version>/`; every host adapter the same way.
- **Fake engines**: a fake OpenAI-compatible server that starts like each engine (its log lines, a slow start, a crash,
  an out-of-memory failure), so load, switch, return, crash and adoption run end to end on any machine.
- **Real engines**, on this machine only, when asked (`-m real`): each installed setup starts, answers, measures its
  memory and stops. They start an engine only when the GPU holds no other engine and port 18200 is free, and stop what
  they started (the owner's models are never touched).

The order, each step test-first, committed and pushed, with its own plan (design 0002 §3.1):

| Step | Builds |
| --- | --- |
| M1.1 | The runtime component: its kinds, the catalog, both adapters' options and plans, the recorded KVMem fixtures |
| M1.2 | Hosts: `local` and `wsl`; starting, identifying, adopting and stopping processes; the fake engine |
| M1.3 | Slots: load, unload, switch, return, crashes, adoption, memory measured and learned; the API and commands |
| M1.4 | Installs and models: recipes, adopting KVMem, building NInfer, downloads; NInfer's fixtures recorded |
| M1.5 | The console's models, presets, providers and launch options pages; VS Code; `clank import` (removed 2026-10-13, decision 0033) |
| M1.6 | Both setups started and measured on this machine; the console's layout and keys if room is left; version 0.2.0 |
