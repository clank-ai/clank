# Design 0001: the runtime, the gateway and the console

Roadmap parts 1 (runtime), 2 (gateway), 3 (console) and 4 (setup guide, §7). Started 2026-10-11. Decisions it rests
on:
[0003](../decisions/0003-one-terminal-console.md) (one console), [0004](../decisions/0004-sampling-per-role.md)
(sampling per role), [0005](../decisions/0005-textual-for-the-console.md) (Textual),
[0006](../decisions/0006-runtime-service-with-adapters.md) (runtime service with adapters),
[0007](../decisions/0007-settings-in-readable-files.md) (readable files),
[0008](../decisions/0008-role-is-the-requested-model-name.md) (a role is the requested model name),
[0009](../decisions/0009-test-a-configuration-in-a-trial-run.md) (check, and test in a trial run, before applying),
[0010](../decisions/0010-serving-setups-are-plug-and-play.md) (serving setups are plug and play).

## Goal

The user picks which model runs, how it is served (which engine, or an endpoint elsewhere), with which launch options,
and how each kind of request is sampled; sees all of it live, with what it costs; and changes any of it from one
console, or by editing a file. Every principle applies; the ones that shape this design most are modular (2), radical
transparency (3), portable (5) and the computer stays usable (6).

**Status:** every section approved on 2026-10-11, then self-reviewed the same day (the revision log at the end lists
what the review changed), and revised where design 0002, the foundation, was approved after it. Building follows design
0002 §3: one implementation plan per milestone, M0 first.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | Architecture | Approved 2026-10-11; revised the same day (adapters generalized to providers), and again when design 0002 §1 was approved (the runtime service became the runtime component of the Clank service) |
| 2 | Providers, engines and models | Approved 2026-10-11; revised the same day (the first serving setups named, decision 0010) |
| 3 | Settings: options, roles, presets, checks before a change | Approved 2026-10-11 (decision 0008); §3.8 (check and test) added after approval, approved the same day (decision 0009); §3.7 and §3.8 revised when design 0002 §2 was approved |
| 4 | Switching, failures and safety | Approved 2026-10-11; §4.2 and §4.8 revised when design 0002 §2 was approved |
| 5 | The console | Approved 2026-10-11; §5.3 revised when design 0002 §3 was approved |
| 6 | The gateway | Approved 2026-10-11; §6.6 revised when design 0002 §1 was approved (sandboxes reach it through their edge), §6.4 when its §2 was |
| 7 | Setup and portability | Approved 2026-10-11; §7.2 revised when design 0002 §2 was approved; §7.1 revised by decision 0030 (2026-10-12) |
| 8 | Testing | Approved 2026-10-11 |
| 9 | Order of work, and what comes over from the prototype | Approved 2026-10-11; §9.1 replaced by design 0002 §3 when it was approved |

## 1. Architecture

*Approved 2026-10-11. Revised the same day: the owner asked that Clank also work with an API key or a model on an HPC
cluster, so "engine adapters" became "providers" (managed engines and remote endpoints, §2); nothing else changed.
Revised again when [design 0002](0002-the-foundation.md) §1 was approved (2026-10-11): the runtime service is now the
runtime component of one Clank service, the control plane (decision
[0013](../decisions/0013-one-service-control-and-data-planes.md)). Design 0002 §1's diagram replaces the one below;
the points below stand, with "the runtime service" read as "the Clank service".*

```
   console (Textual)     command line     editor integration     other programs
          \                    |                   |                  /
           +------------- runtime API (HTTP, localhost) -------------+
                                       |
                        runtime service (one process)
        catalog: providers, models, presets, role sampling   (readable files, decision 0007)
        each slot:   stopped > starting > ready > busy > stopping
        switch:      validate > fit check > busy check > stop > start > health;
                     on failure, back to the last configuration that worked
        metrics and history: speed, context, memory, GPU and desktop load, every change
                 |                                            |
      providers, one adapter each                        gateway
        managed engines (Clank starts them):             every model request: find its role,
          llama.cpp, KVMem/llama.cpp,                      send it to its slot's provider, apply
          NInfer RTX 5080; later others                    the role's sampling, record what was
        endpoints (Clank connects to them):                asked and what ran
          hosted APIs with a key, remote servers
```

- **One service, one source of truth.** Front ends hold no state; closing the console does not stop the model.
- **Slots.** A slot is a seat for a model. Clank starts with two, `main` (the agent's model) and `fast` (completion
  and short side requests); the user can add more. One GPU usually fits one large model, so managed providers that
  need the GPU share it one at a time; endpoints and CPU engines run alongside.
- **Who can reach it.** The runtime API and the gateway listen on this machine only, unless the user opens them to
  other machines, and then only with a token.
- **Adapters.** Each provider type is one module with a fixed interface (§2). Adding an engine or an API dialect is one
  file and its tests.
- **Role sampling in the gateway** (decision 0004): the gateway replaces each request's sampling with its role's
  values and records both, so the console shows what a tool asked for and what actually ran.
- **Readable state** (decision 0007): presets, role sampling and the model catalog are JSON files; what runs now and
  the last configuration that worked are runtime state outside the repository.
- **Not carried over from the prototype:** its monitor's web page (the console replaces it).

## 2. Providers, engines and models

*Approved 2026-10-11. Revised the same day: the owner named the first serving setups, built together and plug and
play (decision [0010](../decisions/0010-serving-setups-are-plug-and-play.md)): llama.cpp, KVMem/llama.cpp, and
NInfer RTX 5080 exactly as published. The examples below changed accordingly.*

Clank reaches every model through the same kind of interface, an OpenAI-compatible HTTP API. Where that API comes
from is a **provider**, of one of two kinds:

| Kind | Who runs it | Examples | What Clank does |
| --- | --- | --- | --- |
| Managed engine | Clank, on this machine | First: llama.cpp (on the GPU or the CPU), KVMem/llama.cpp, NInfer RTX 5080 as published (decision 0010); later KVMem with NInfer, vLLM or others | Starts and stops the engine with a model and launch options; checks health; reads its log for speed, draft acceptance and memory |
| Endpoint | Someone else | A hosted API reached with a key; a server on an HPC cluster or another computer, directly or through an SSH tunnel Clank opens | Connects, checks health, lists its models and limits, measures speed; never starts or stops it |

**Engine adapter** (one module per engine), with this interface:
- `options()`: the engine's settings as a typed list, each described by the fields of §3.1 (its key, kind, range,
  default, whether it is set at launch or per request, exactly what it maps to, and how it changes memory use).
- `plan(model, settings, machine)`: the exact command line, environment, working folder, port and host (Linux, WSL or
  Windows), plus an estimate of GPU and system memory. The plan is shown to the user before anything starts.
- `health()`, `metrics()` (parsed from the engine's log), `stop()`.
- The engine version the adapter was written for, and how to install or build that engine (the setup guide uses it).

**Endpoint adapter** (one module per kind of endpoint, a generic OpenAI-compatible server first): the connection
(base URL, authentication by none, an API key or a bearer token, an optional SSH tunnel through a login host to the
server's host and port) and the models and limits the endpoint reports. The request format it speaks is one of the
gateway's dialects (§6.2).

**Model catalog.** One entry per model: its name; its files in each format it exists in (GGUF, .ninfer, safetensors),
each with where it came from (repository, revision, checksum); facts read from the files (architecture, parameter
count, context length, quantization, an MTP head); what it can do (tools, reasoning, vision); which engines can load
which format; and its known-good presets with their measured speed.

**Secrets.** API keys and tokens live in the user's own folder (`CLANK_HOME/secrets/`, §7.2 and §7.6), outside the
repository. They are never logged and never shown in full (the console shows that a key is set and its last four
characters). The gateway attaches them to requests sent to the endpoint.

**Machine profile.** Detected on first run (operating system, WSL, GPUs and their memory, RAM, CPU, disks) and kept in
the user's configuration (`CLANK_HOME/config/machine.json`). It feeds the memory-fit estimates and the setup guide's
recommendations. Tracked files never contain one machine's specifics.

What the preset picker could look like on the machine Clank was first built on:

```
 PRESETS          model                provider                 context  fits  last speed
 daily 262K       Qwen3.8-27B IQ3_S    KVMem/llama.cpp (WSL)    262K     yes   48 tok/s
 fast 128K        Qwen3.8-27B .ninfer  NInfer RTX 5080 (WSL)    128K     yes   not run
 plain 64K        Qwen3.8-27B IQ3_S    llama.cpp (WSL)          64K      yes   not run
 hosted           (a hosted model)     endpoint, API key        -        -     not run
 cluster          (a larger model)     endpoint, SSH tunnel     -        -     not run
```

## 3. Settings: options, roles, presets, checks before a change

*Approved 2026-10-11. §3.3's way of naming a role is decision
[0008](../decisions/0008-role-is-the-requested-model-name.md). Revised after approval, the same day: §3.8 (checking
and testing a configuration before applying it) added at the
owner's request and approved (decision [0009](../decisions/0009-test-a-configuration-in-a-trial-run.md)). Revised when
[design 0002](0002-the-foundation.md) §2 was approved: the example preset names its schema (§3.7), and a trial is an
operation of the Clank service (§3.8). Revised after approval on 2026-10-21, at the owner's request: an engine's own
sampling defaults are launch options too (§3.2, decision 0119).*

Every value that shapes how a model runs is an **option**. Every option is visible, explained, and changeable both in
the console and in a file. Nothing is set where the user cannot see it.

### 3.1 Options

Each option is described once, by the adapter that understands it (launch options) or by Clank itself (request
options):

| Field | Meaning | Example |
| --- | --- | --- |
| `key` | Stable name. Shared concepts use shared names; engine-specific ones carry the engine's prefix | `context`, `kv.type`, `spec.draft_tokens`, `kvmem.budget` |
| `label`, `help` | What it does and what it trades, in one sentence | "Tokens the model attends to exactly; more costs GPU memory" |
| `kind` | `integer`, `number`, `choice`, `switch`, `text` or `file` | `choice` |
| `range` or `choices`, `unit`, `default` | The allowed values | `q8_0`, `f16`, `q4_0`; default `q8_0` |
| `scope` | `launch` (the engine restarts to change it) or `request` (the next request uses it) | `launch` |
| `maps_to` | Exactly what the engine receives: a flag, an environment variable, or a field of the request | `--kv-dtype {value}` |
| `memory` | How it changes GPU and system memory (used by the fit check, §3.6) | KV bytes per token, times the cells |
| `requires`, `conflicts` | Other options or model features it needs or excludes | vision needs a model with a projector |
| `tested` | Whether Clank's tests or benchmarks have run this value on this engine | true for `q8_0` |

`maps_to` makes the engine transparent: for any set of options the console can show the exact command line, or the
exact request, that they produce.

### 3.2 Launch options and request options

- **Launch options** are each engine's own; its adapter declares them. For KVMem/llama.cpp, for example: the context,
  the KVMem retrieval budget (the exact-attention window on the GPU), the generation reserve, the KV cache type, draft
  tokens for speculative decoding (MTP), CUDA graphs, vision (off, on the CPU, on the GPU) and its image token limit,
  the maximum output, threads and batch sizes. NInfer has its own list (KV capacity, prefill chunk, host-mapped
  embeddings, and so on). Shared concepts keep shared names, so a preset can move to another engine wherever the same
  option exists.
- **Request options** are Clank's own: temperature, top_p, top_k, min_p, the repetition, presence and frequency
  penalties, the seed, thinking (on or off) and its token budget, and the maximum output. Each provider declares which
  ones it honors. A value a provider ignores is shown as "not supported by <provider>"; it is never dropped silently.
- *Revised after approval, 2026-10-21:* an engine's own sampling defaults, which a request's fields override, are also
  launch options (`sampling.temperature` and the rest), unset unless a preset sets them, each shown with the engine's
  own default ([design 0003 §4.1](0003-the-runtime.md#41-sampling-and-the-gpus-layers), decision
  [0119](../decisions/0119-sampling-and-gpu-layers-are-launch-options-left-unset.md)).

### 3.3 Roles

A **role** says what a request is for. Clank ships five: `agent` (the coding agent), `batch` (scripted jobs),
`companion` (the research companion), `completion` (tab completion) and `side` (short side requests such as titles).
The user can add more, such as an audit screen or a reviewer. Each role names its slot (§1) and its request options.

A tool tells the gateway its role through the model name it asks for: the agent is configured to call the model
`agent`, a batch job calls `batch`. This asks nothing of a tool beyond its usual model setting, works the same for a
sandboxed agent and for a script, and keeps the role visible in every request the console shows. A request for a name
Clank does not know gets a sixth role, `default`, whose slot and options the user sets like any other's.

Sampling advice depends on the model (a model's authors often publish their recommended settings), so a role's values
can also be set for one model: "agent: temperature 0.6; with model X, 0.7".

### 3.4 Presets

A **preset** is a saved launch configuration: a provider (an engine at a named version and a model, or an endpoint and
one of its models) plus the launch options that differ from the defaults. A slot runs one preset at a time; a switch
(§4.2) replaces it. Only differences are stored, so a preset file can be read at a glance. A preset can be switched
to, copied, edited, compared with another (the console shows their differences and their measured speeds side by
side), and exported to share. Clank keeps each preset's benchmark results (speed at fixed prompt sizes, draft
acceptance, memory used) with the preset, so choices rest on measurements.

### 3.5 Where each value comes from

Every value in effect has one source, and the console shows it next to the value:

- a launch option: the engine's default, overridden by the model's recommendation (from the catalog), then by the
  preset, then by a change made now and not yet saved;
- a request option: the model's recommendation, overridden by the role's value, then by the role's value for this
  model. What the tool itself sent is replaced (decision 0004) and recorded.

A change made in the console stays "unsaved" until the user saves it to the preset or as a new preset, like an edit in
an editor. Switching away from a preset with unsaved changes asks first.

### 3.6 Checking a change before it is applied

- **Validity.** Kinds, ranges, `requires` and `conflicts`; the engine can read the model's file format; the context
  fits the model's trained context.
- **Memory fit.** The GPU memory a launch needs, as a breakdown the user can read: the weights (from the model's file),
  the KV cache (bytes per token for this model and KV type, times the cells the options imply), the compute buffers and
  the engine's own overhead (the adapter's estimate, corrected by what Clank measured on earlier launches on this
  machine), and what the desktop uses right now. The verdict is *fits*, *tight* (less than 500 MiB to spare) or *does
  not fit*; system memory is checked the same way (host-side KV stores, mapped weights). A launch that does not fit is
  not started unless the user overrides the check, and the console says what to expect: spilling into system memory
  makes decoding several times slower.
- **Cost.** What applying the change means now: a restart and how long the last one took, which sessions lose their
  cached context, and how long re-reading it will take.
- **Learning.** After each launch Clank compares its estimate with the memory actually used and keeps the difference
  for that engine on that machine, so the next estimate is closer.

### 3.7 Files

Clank's own files ship inside its package; the user's live in `CLANK_HOME` (§7.2):

| File | Where | Holds |
| --- | --- | --- |
| `clank/defaults/roles.json` | Repository | The roles Clank ships, with their default request options |
| `clank/catalog/models/<model>.json` | Repository | The models Clank knows: sources, checksums, facts, recommended settings |
| `clank/schemas/<kind>.schema.json` | Repository | The schema of each kind of file |
| `CLANK_HOME/config/presets/<preset>.json` | User | The user's presets, with their measurements |
| `CLANK_HOME/config/roles.json` | User | The user's changes to the roles, and new roles |
| `CLANK_HOME/config/models.json` | User | Where the user's model files are |
| `CLANK_HOME/config/machine.json` | User | The machine profile |
| `CLANK_HOME/secrets/` | User | Keys and tokens, readable only by the user |

The runtime service validates every file it reads against its schema, refuses an invalid one with a message that names
the file, the line and the field, reloads a file that changes on disk, and writes it back when the console changes
something (decision 0007).

An example preset, `CLANK_HOME/config/presets/daily-262k.json` (a preset for an endpoint names `endpoint` instead of
`engine`):

```json
{
  "schema": "preset/1",
  "name": "daily 262K",
  "engine": "kvmem-llamacpp",
  "engine_version": "v0.16.0-rc1",
  "model": "qwen3.8-27b-iq3s",
  "options": { "context": 262144, "kvmem.budget": 36864, "spec.draft_tokens": 3, "vision": "cpu", "cuda_graphs": false },
  "notes": "The daily default."
}
```

What the console's launch options form could look like:

```
 LAUNCH OPTIONS   preset: daily 262K (1 unsaved change)           engine: KVMem/llama.cpp
 option              value     source        what it does
 context             131072 *  changed now   tokens the model can see; past the budget, retrieved
 retrieval budget    36864     preset        exact attention on the GPU; more costs GPU memory
 KV cache type       q8_0      engine        q4_0 halves KV memory, may cost quality
 draft tokens (MTP)  3         preset        2 to 4; 3 is the tested value
 CUDA graphs         off       preset        faster; crashed KVMem v0.16 with tools (lessons)
 vision              CPU       preset        on the GPU it costs 0.6 GB more
 GPU memory  weights 10.9 + KV 1.7 + buffers 1.2 + desktop 1.5 = 15.3 of 15.9 GB   FITS (0.6 GB to spare)
 Enter edit   r revert   c check   t test   s save   S save as   a apply (restart, about 40 s)
```

### 3.8 Checking and testing a configuration before applying it

*Added after approval, 2026-10-11, at the owner's request: "the ability to 'check' the settings that we have selected
as well as running tests ... headless to test the settings before they are applied". Approved the same day.*

Two steps, each started from the console (keys `c` and `t` in any settings form) or from the command line, and each
recorded with the preset:

- **Check** takes seconds and starts nothing. It runs everything in §3.6, plus what the adapter can verify without a
  launch: the engine's program exists and is the version the adapter was written for; the engine accepts every flag
  the options produce (read from its own `--help`); the model file exists, has the expected size and checksum, and is
  in a format the engine reads. The result is a list of passed and failed items, each with its reason.
- **Test** is a trial run, headless. The runtime service starts the candidate configuration as a *trial* (an operation
  of the Clank service, design 0002 §2.4), runs one or more test suites against it, saves the results, then stops the trial and puts back what was running before, unless
  the user asked to keep the candidate when every test passes. The trial runs inside the runtime service, not in the
  console: closing the console does not stop it, and the console shows its progress and results live. When the
  candidate needs the GPU the live model is using, the trial is a switch with an automatic return (§4.2: the busy
  check, the held requests, the cached contexts that will be read again), and the user can schedule it for when the
  slot is idle. A candidate that fits beside the live model (an endpoint, an engine on the CPU) runs alongside it.

The test suites are files the user can read and change: Clank's ship in `clank/suites/<suite>.json`, and a suite of
the same name in `CLANK_HOME/config/suites/` replaces Clank's for that user. Each check states its pass condition and
what it measures:

| Suite | Takes | Checks |
| --- | --- | --- |
| `smoke` | About a minute | Starts within its time limit; health; a short answer; streaming; a tool call that matches its schema; thinking on and off honored; the request options the provider claims to honor take effect (temperature 0 with a fixed seed repeats itself) |
| `speed` | A few minutes | Clank's fixed benchmark: cold prompt reading and decoding speed at fixed prompt sizes up to the configured context, draft acceptance, time to the first token; compared with the preset's earlier results and with what runs now |
| `memory` | During the others | Peak GPU and system memory against the estimate; engine memory that lives in system RAM (a sign of a spill) |
| `context` | Several minutes | Recall of facts placed at several depths of a long prompt, up to the configured context; for a retrieval engine such as KVMem this tests the retrieval settings |
| `quality` | Longer; optional | A small fixed set of coding and math tasks with checked answers, so a cheaper quantization or KV type that hurts the answers shows up |

Every preset shows its last check and test results (with their date and the engine version) next to its name; a
preset that was never tested says so.

What a test could look like in the console:

```
 TEST  fast 128K   trial: daily 262K comes back afterwards        suites: smoke, speed
  ok    starts in 33 s (limit 120 s)
  ok    short answer; streaming
  ok    tool call matches its schema
  ok    thinking off honored; thinking budget 2048 honored
  ok    temperature 0 with seed 7 repeats itself
  ...   speed at 4K: reading the prompt
  q stop the test (daily 262K comes back)    k keep fast 128K if every test passes
```

## 4. Switching, failures and safety

*Approved 2026-10-11. Revised when [design 0002](0002-the-foundation.md) §2 was approved: a switch is an operation and
its busy check a question (§4.2); the history is the event log in the state database (§4.8).*

Changing what runs must never leave the user guessing, lose work silently, or leave a broken model behind. Every
number below (timeouts, thresholds, limits) is a default and an option the user can change.

### 4.1 A slot's states

```
 stopped --start--> starting --healthy--> ready <--> busy
    ^                   |                   |
    |                   v                   v
    +---- stopping <-- failed <---- crash, or health checks failing
    ^                                       |
    +------------- stop, or switch ---------+
```

Every state change is recorded with its time and reason. The console shows each slot's state, how long it has been in
it, and, when it has failed, why.

### 4.2 The switch procedure

A switch replaces what serves a slot, always by the same sequence. It is an operation of the Clank service (design 0002
§2.4), so every client shows each step as it happens, and closing a client stops nothing:

1. **Plan.** The target (a preset, with any unsaved changes) is checked (§3.6): validity, memory fit, cost. The plan
   (the command line or endpoint, the memory breakdown, the expected time) is shown before anything stops.
2. **Busy check.** The gateway reports what uses the slot: the requests in flight, and the sessions whose context the
   provider has cached. The user chooses to wait for the running requests to finish and then switch (the default),
   to switch now (the running requests end with a clear error), or to cancel. The choice is a question (design 0002
   §2.5), so it can be answered from any client, the phone included.
3. **Hold.** While the slot switches, the gateway holds its new requests (up to two minutes), so tools see a slow
   answer instead of an error. The console lists the held requests.
4. **Stop** the current provider. A managed engine is asked to stop and is ended if it does not stop within its
   timeout; Clank then checks that its GPU memory has been freed. An endpoint is disconnected and its tunnel closed.
5. **Start** the new provider by its plan. A managed engine's log streams into the console while it loads.
6. **Health.** The provider must answer its health check, and a tiny test request (a few tokens, checked), within a
   time scaled from its earlier starts.
7. **Release.** The held requests go to the new provider. The switch is recorded with its duration and with the
   memory measured against the estimate (§3.6, learning).

If step 5 or 6 fails, Clank stops what it started, starts the last configuration that worked again (§4.3), and
reports the failure with the engine's last log lines and its reading of them ("out of GPU memory: the plan needed
15.6 GB, 15.2 GB was free"). If that fails too, the slot is *failed*, the held requests get a clear error, and the
console offers the log, the preset and a retry. Only one switch per slot runs at a time; a second request to switch
is refused with the name of whoever started the first.

A **trial** (§3.8) follows the same sequence and adds a last step: once its tests are done, it switches back to the
configuration that was running before, unless the user chose to keep the candidate and every test passed.

### 4.3 The last configuration that worked

The configuration that last reached *ready* and answered requests, kept in the runtime state with its time. A failed
switch goes back to it, and the service offers to start it when the service itself starts.

### 4.4 Crashes and slowdowns while running

- **Crash.** A managed engine exits unexpectedly, its health check fails three times in a row, or requests fail with
  engine errors (KVMem's "failed to find a memory slot" on 2026-10-11 was one). The slot becomes *failed*, with the
  reason and the log, and the request in flight gets a clear error. Clank restarts the same configuration once if it
  had been ready for at least ten minutes, and says so; a second crash within an hour stops it and asks the user.
- **Slowdown.** A slot that answers, but well below its preset's measured speed (under 60% for two minutes, counting
  only comparable requests), gets a warning in the console with what Clank can measure about the likely causes: the
  desktop's share of the GPU, engine memory living in system RAM, other programs on the GPU, temperature and clocks.
  This check would have caught the 2026-10-11 slowdown within minutes.
- **Endpoints.** Network errors are retried with backoff. A rejected key (401) or a reached limit (429, with its reset
  time) is shown as what it is and not retried blindly. A dropped SSH tunnel is reopened automatically, and the
  reconnection is shown.

### 4.5 Sessions and their cached context

Switching or restarting a slot discards the provider's cache of every session's context, so each session's next
request reads its whole context again; for a long agent session that takes minutes. Before a switch, the console
shows which sessions lose what (their size, and an estimate of the time to read it again). Clank never ends a session
on its own; where the agent supports it, the console offers the agent's own tools (compaction, a written hand-off).

### 4.6 What Clank may stop

Clank stops only the processes it started, which it identifies by process id, start time and command line, kept in
the runtime state. A port or a GPU that another program uses is reported (the program's name and process id), never
cleared. When the runtime service itself restarts, it finds the engines it started by that same identity and adopts
them, so a model keeps running through a restart of the service or of the console.

### 4.7 The rest of the computer

Before a launch, Clank checks what else is using the GPU and warns about heavy users (a game, a video). It checks the
platform settings known to cause trouble, such as Windows' hardware-accelerated GPU scheduling, which froze the
desktop while long prompts were read. It never changes them itself: it explains and offers.

### 4.8 Every change is recorded

State changes, switches and their steps, failures with the log lines that explain them, and every settings change
with its old and new value and where it came from (the console, a file edit, another program) go into one history: the
event log in the state database (design 0002 §2.3; decision
[0014](../decisions/0014-state-in-sqlite-settings-in-files.md)), which `clank events export` writes out as JSON lines.
The console shows and filters it.

What the console's switch dialog could look like:

```
 SWITCH  main slot: daily 262K -> fast 128K
  plan     NInfer RTX 5080 (WSL)   qwen3_8_27b.ninfer   context 131072   KV q4   MTP 3
  memory   15.1 of 15.9 GB   FITS
  busy     agent: 1 request running for 2 min
           2 sessions lose their cached context: 130K and 40K tokens (read again in about 2 min)
  time     stop about 5 s, start about 35 s (33 s last time)
  w wait for the running request, then switch    n switch now (it ends with an error)    Esc cancel
```

## 5. The console

*Approved 2026-10-11. Revised when [design 0002](0002-the-foundation.md) §3 was approved: the console became the
control center of every component, with a shell built in M0; the screens of §5.3 are its models screen, built in M1.*

### 5.1 What it is

`clank console` is one Textual application (decision 0005) that runs in any terminal: Windows Terminal, a WSL or
Linux shell, macOS. It is a client of the runtime API and holds no state of its own (decision 0006), so it can be
closed and opened at any time without touching a model, and several can run at once. It is keyboard-first: every
action has a key and is listed in the command palette (Ctrl+P). The mouse works too.

### 5.2 The main screen

```
 CLANK  main: daily 262K · Qwen3.8-27B IQ3_S · KVMem/llama.cpp (WSL) · READY 2h14m    fast: 0.5B on CPU · READY   11:42
 GEN   43.2 tok/s ▂▃▅▆▅▃▂▃▅▆  WRITING   agent · opencode · 017 identify   4,205 tokens   3.3 tokens per step
 CTX   [██████████████░░░░░░] 130K of 262K   exact window 36K, older context retrieved   cache reused 97%
 GPU   [||||||||||   71%]  memory [||||||||||| 15.2/15.9 GB]  desktop 31%  in system RAM 0.9 GB  215 W  45 °C
 CPU   [|||         22%]   RAM [|||||||   29/48 GB]   engine: 94% of one core, 9.7 GB
 ─ activity ─────────────────────────────────────┬─ live text ────────────────────────────────────────
 11:34:25 TOOL bash audit.py pages 017    0.4 s  │ (thinking) Let me find the proof text for
 11:35:35 RESP 1,474 tokens   31 tok/s           │ Corollary 1.2. From page 19: "Taking a nearest
 11:37:47 TOOL bash grep -rn "theorem ...  1.2 s │ integer numerator in that theorem gives ...
 ! slower than its preset: 27 against 48 tok/s for 2 min; the desktop uses 31% of the GPU     F8 details
 F1 help  F2 presets  F3 providers  F4 launch  F5 sampling  F6 sessions  F7 tests  F8 history  F9 layout  ? explain  q quit
```

From the top: each slot with its preset, model, provider and state; generation (speed with its last two minutes,
the phase, the request's role, tool and conversation, tokens so far, tokens per decoding step); the context (how full,
the exact window and whether older context is being retrieved, the share of the cache reused); the GPU (use, memory,
the desktop's share, engine memory living in system RAM, power, temperature); the CPU, RAM and the engine process;
then the activity (requests, answers, tool calls with their results and times, errors, model events) beside the text
the model is writing right now; then warnings (§4.4), then the keys.

### 5.3 The control screens

*Revised when design 0002 §3 was approved: these screens are the parts of the console's models screen, built in M1
(the tests screen in M2). The keys below are the models screen's own; the console's shell (design 0002 §3.2) gives each
component's screen its key.*

| Key | Screen | What it does |
| --- | --- | --- |
| F1 | Help | Every key; what each panel shows; links to the glossary and this design |
| F2 | Presets | The presets with their fit, last speed and last test (§3.4); switch, compare two, check, test, new, copy, edit |
| F3 | Providers and models | Engines (installed, version, adapter), endpoints (health, whether a key is set), models (files, formats, sources) |
| F4 | Launch options | The form of §3.7: each option with its value, source and effect; check, test, apply |
| F5 | Sampling | The roles (§3.3) and their per-model values; a change applies from the next request |
| F6 | Sessions | The conversations using each slot: role, tool, size, whether their context is cached, last activity |
| F7 | Tests | Check and trial results per preset (§3.8); start a suite |
| F8 | History | Everything recorded (§4.8), filtered by slot, kind or time |
| F9 | Layout | Which panels show, in what order and size, and where each one is defined (§5.5) |
| q | Quit | Closes the console; never stops a model |

### 5.4 Explain anything

On any screen, `?` on a value shows: what it is, its value and its source (§3.5), what it maps to (the engine's flag
or the request's field), the file and line that store it, and the decision or design section behind it. Radical
transparency at the level of a single number: the user never has to search the code to learn why a value is what it
is or where to change it.

### 5.5 Changing how it looks and what it shows

- **Look.** Textual style sheets: `clank/console/clank.tcss` ships with Clank, and `CLANK_HOME/config/console.tcss`
  is the user's, loaded after it, so any rule there wins. The console reloads a style file when it is saved, so a
  color, a width or a border shows its change at once.
- **What it shows.** `CLANK_HOME/config/console.json` lists the main screen's panels, their order and sizes, and the
  redraw limit. The F9 screen edits it, or the user edits the file.
- **Keys.** `CLANK_HOME/config/keys.json` maps keys to actions; each action's name is shown in the command palette.
- **Where each thing is defined.** The F9 screen shows, for each panel, its module (for example
  `clank/console/panels/context.py`), its style rules and the files they are in, and its configuration entries, so a
  person or a model knows exactly which file to open.

### 5.6 Panels are modules

Each panel is one small module: the data it needs from the runtime API (which events, which state), how it draws
itself, and its default style. A new panel is one new file plus a line in `CLANK_HOME/config/console.json`. The main
screen and the control screens are all made of panels, so the same rules hold everywhere.

### 5.7 Redraws and load

The console redraws only what changed, at most four times a second (a setting); the live text and the speed graph
follow that rhythm. Animations are off (Textual's animation level set to none): no spinners, no pulsing (principle 6;
a redraw at a high-refresh display's rate once cut decoding to a third). Data arrives as events on one stream from the runtime
API instead of each panel polling. Tests hold the console's own CPU use to a stated limit (§8).

### 5.8 Without a screen

- `clank console --snapshot` prints one frame as text (for scripts, bug reports, and a model that cannot see a
  screen); `--screen presets` picks another screen.
- Every action in the console is also a command: `clank preset switch "fast 128K"`, `clank sampling set agent
  temperature 0.4`, `clank test "fast 128K" --suite smoke`. The console never does anything that cannot be done without
  it.
- Tests drive the console headless with Textual's test harness (pressing keys and reading what is on the screen) and
  compare snapshots of its screens.

## 6. The gateway

*Approved 2026-10-11. Revised when [design 0002](0002-the-foundation.md) §2 was approved: what a provider supports at
once is what its adapter declares for its version and launch options (§6.4). Design 0002 §3.4 lists what M3's own
design will settle here.*

Every model request from every tool passes through the gateway, so it is where roles take effect, where the
differences between serving setups are bridged, and where everything is recorded.

### 6.1 The path of a request

1. **Receive** the request in the tool's own API dialect (§6.2) and read it into Clank's one internal form.
2. **Find its role** from the model name it asks for (decision 0008), then the role's slot, then the provider that
   serves the slot now.
3. **Apply the role's request options** (§3.5), replacing the sampling the tool sent.
4. **Translate** the request into what the provider understands: its dialect and, for each request option, the field
   its adapter declares (§6.3). An option the provider cannot take per request is left out and the record says why.
5. **Queue or hold** it if the slot is busy or switching (§6.4).
6. **Attach** what the provider needs: an endpoint's key (from `CLANK_HOME/secrets/`), an open SSH tunnel (through
   the runtime service).
7. **Forward** it and **stream** the answer back to the tool, translated into the tool's dialect.
8. **Record** the request as the tool sent it, as it was applied, as the provider received it, and the answer with
   its timings (§6.5).

### 6.2 Dialects

Tools speak different APIs, and so do serving setups. NInfer RTX 5080, for example, serves OpenAI Chat Completions,
OpenAI Responses and Anthropic Messages, besides `/health` and `/v1/models`. The gateway has one translator module per
dialect (plug and play, decision 0010), each converting between that dialect and Clank's internal form:

| Dialect | Who speaks it | Order |
| --- | --- | --- |
| OpenAI Chat Completions | Most tools (OpenCode among them) and engines (llama.cpp, KVMem, NInfer) | First |
| OpenAI Responses | Codex and other newer tools; NInfer | Second |
| Anthropic Messages | Tools written for Claude; NInfer | Later |

A tool can therefore use any provider, whatever each speaks. The console's request view shows a request in all three
forms: as the tool sent it, in Clank's form, and as the provider received it.

### 6.3 Request options per serving setup

Each adapter declares, for every request option (§3.2), whether its provider takes it per request and in which field.
Thinking control is the clearest difference: KVMem takes `chat_template_kwargs.enable_thinking` and a per-request
reasoning budget; NInfer takes `enable_thinking`, `reasoning_budget` or `reasoning_effort`; hosted APIs take
`reasoning_effort`. Upstream llama.cpp's exact fields are taken from its own help and recorded answers when its adapter
is written (§8.3), not from memory. An option a setup takes only at launch (NInfer's `min_p` is a server flag) is
shown in the console as "set in the launch options for this setup", never dropped without a word.

### 6.4 Queues and holds

- **One queue per slot.** A provider that answers one request at a time (KVMem v0.16 has one slot, while later versions
  can be launched with several, as their adapter declares (design 0002 §2.10); NInfer's release profile runs one
  request at a time) gets its requests from a first-in, first-out queue that the console shows. Interleaving
  requests from several tools on a one-request server evicts each one's cached context, so the order matters. Roles
  can be given priorities (the agent before batch jobs, for example).
- **Holding during a switch** (§4.2): the slot's new requests wait, up to their limit, instead of failing.
- **Side requests.** Small requests (a conversation title, a summary) on the main slot evict its cached context, which
  the prototype measured as minutes of re-reading. The `side` role therefore uses the `fast` slot (a small model, often
  on the CPU). Without a fast slot, the gateway answers the side requests it recognizes, such as titles, itself, as the
  prototype's gateway does.

### 6.5 Records

- One record per request, in one file per day under `CLANK_HOME/logs/traffic/`: the ids (request, conversation), the
  role, slot, provider and preset, the tool, the sampling as sent and as applied, the timings (queue wait, time to the
  first token, prompt reading and decoding speed, from the provider's own numbers where it reports them), the token
  counts, the share of the cache reused, and any error. The streamed answer is recorded in pieces as it arrives, so
  the console can show the live text.
- Keys and tokens are never recorded. Bodies can be very large; how much of them to keep, and for how many days, are
  settings.
- The gateway only records. The runtime service turns the records into metrics, sessions and warnings (§4.4), and the
  console shows them.

### 6.6 Where it runs and who can reach it

The gateway is its own process, started and supervised by the runtime service, so a restart of the service or of the
console does not cut requests in flight. Tools reach it at one address (`http://127.0.0.1:<port>/v1` by default); a
sandboxed tool reaches it through its sandbox's edge (design 0002 §1). It listens on this machine only, unless the
user allows other machines, and then only with a token.

### 6.7 What comes from the prototype's gateway

Its record format (requests, answers and the streamed pieces in daily JSON-lines files) and its local answers to title
requests come over. Its network rules for the sandbox (allowed hosts, the research proxy, the git credential proxy)
belong to the coding agent's sandbox (roadmap part 5), not to the model gateway, and move there.

What the console's request view could look like:

```
 REQUEST r-81f2   agent · opencode · conversation c-17   main slot: daily 262K (KVMem/llama.cpp)
  option        tool sent   applied (agent)   provider received as
  temperature   0.6         0.6               temperature
  top_p         0.95        0.95              top_p
  top_k         -           20                top_k
  thinking      -           on, budget 4096   chat_template_kwargs.enable_thinking, reasoning budget
  timing        queued 0.0 s   read 2,604 tokens in 1.9 s (cache reused 97%)   wrote 1,474 tokens at 31 tok/s
  v view the request as sent / in Clank's form / as received      a the answer      Esc back
```

## 7. Setup and portability

*Approved 2026-10-11. Revised when [design 0002](0002-the-foundation.md) §2 was approved: `CLANK_HOME` gained the
folders of its §2.16 (§7.2).*

Someone who pulls Clank from GitHub gets from nothing to a working model on their own machine (a local model, an API
key, or a model on another computer) through a guide built into Clank (principle 5).

### 7.1 Where Clank runs

| Platform | First version | Notes |
| --- | --- | --- |
| Linux (Ubuntu 22.04, 24.04) | Yes | The runtime, the gateway and the engines run natively |
| Windows 11 with WSL2 | Yes | The service runs on Windows and the engines inside WSL distributions (decision 0030); the console runs in Windows Terminal. A Windows-native engine (such as KVMem's Windows build) is a later adapter on the Windows host |
| macOS | Later | llama.cpp with Metal |

Clank needs Python 3.12 or newer, in its own environment, with every dependency pinned in a lock file.

### 7.2 The user's Clank folder

Everything that belongs to one user on one machine lives in one folder, `CLANK_HOME` (`~/.clank` by default; a
developer can point it at the repository's ignored `local/` folder):

| Folder | Holds |
| --- | --- |
| `config/` | The user's presets, roles, model locations, console layout, style and keys |
| `secrets/` | Keys and tokens, one file each, readable only by the user |
| `state/` | The state database (`clank.db`: what runs now, the last configuration that worked, the learned memory corrections, the history), the local token, the service's address (`connection.json`), and the data plane's spool (design 0002 §2) |
| `logs/` | The gateway's records (§6.5) and each process's output (`logs/processes/`) |
| `engines/` | The installed serving setups, one folder per setup and version |
| `models/` | Model files, unless the user puts them elsewhere: a fast local disk (under WSL, WSL's own file system: loading a model across the bridge to Windows' disks is much slower) |
| `library/` | What the user installs: skills, tool servers, modes, shared suites and presets (design 0002 §2.11) |
| `artifacts/` | Files made for the user, such as a figure the agent was asked for (design 0002 §2.12) |

Clank touches nothing outside this folder except what the user approves in the guide (installing system packages, for
example). Removing Clank means removing this folder and the repository; the guide shows how much disk each folder
takes.

### 7.3 The first-run guide

`clank setup`, or the console's first screen while nothing is set up. Five steps. Each one shows exactly what it will
do (the commands it will run, the files it will write, what it will download and how big) before it does it, asks
first, can be run again or resumed, and is recorded:

1. **Machine.** Detect the operating system and WSL; the GPUs (model, memory, driver, the newest CUDA version the
   driver supports); RAM, CPU, free disk, and Docker. Check the settings known to matter (Windows' hardware-accelerated
   GPU scheduling, WSL's memory limit, the order Docker and WSL start in). Show the result and what it means.
2. **Where the model runs.** On this machine, with an API key, or on another computer. For this machine, the serving
   setups that fit, ranked for it with the reason for each: on a 16 GB RTX 5080, NInfer RTX 5080 for speed at up to
   128K, KVMem for 262K, llama.cpp as the plain option.
3. **Install.** For a local setup, the engine by its recipe (§7.4) and the model (§7.5); for an endpoint, its address
   and its key or tunnel (§7.6).
4. **Test.** Create the setup's known-good preset and run its check and its smoke suite (§3.8). A setup is ready only
   when both pass; a failure says what failed and what to try.
5. **Tools.** Show the address and the role names to enter in tools (OpenCode, Codex-style tools, editors), and offer
   to write the configuration of the agent Clank ships (roadmap part 5).

### 7.4 Recipes for serving setups

Each serving setup ships a recipe next to its adapter: a readable file that lists the prerequisites (a compiler,
CMake, a CUDA toolkit), how to check each one and the versions needed; the pinned version (a git commit or a release,
with checksums); the exact commands for each platform; where the result goes (`engines/<setup>/<version>/`); and how
to verify it (the engine's version and help output, then the smoke suite).

Several versions can be installed side by side, and a preset names its version. An upgrade means installing the new
version, testing it in a trial, and switching. Long builds (compiling CUDA kernels takes a while) run as jobs in the
runtime service, visible and cancelable in the console, on a limited number of cores so the computer stays usable.

An example: NInfer RTX 5080 v1.5 is published as built on Linux with GCC 15.2 and CUDA 13.4.92, and its community
reports a WSL2 build. Its recipe checks that the GPU driver supports CUDA 13.4, installs the 13.4.92 toolkit inside
WSL next to any other version, builds the pinned source, and verifies the downloaded `.ninfer` file against its
published SHA-256. If the user keeps another toolkit, the recipe records that deviation (decision 0010), and the
trial compares the speed with the published numbers.

### 7.5 Models

- **Sources.** A Hugging Face repository (a pinned revision, the file name, its checksum), a direct URL, or a file the
  user already has. Conversions (to `.ninfer`, for example) are recipes too.
- **Downloads** ask first (size, expected time, disk left), resume after an interruption, verify the checksum, and can
  be limited in speed so the network stays usable.
- **The catalog** (in the repository) lists the models known to work with each setup, with their sizes and checksums.

### 7.6 Endpoints

- **Templates** for the common kinds: a generic OpenAI-compatible server; known hosted providers (base URL, how the
  key is sent, which request options they honor); a server on an HPC cluster behind SSH (the login host, user and key
  file, then the compute node and port). Starting a server through a cluster's job scheduler comes later; first, Clank
  connects to one that is running.
- **Keys** go into `secrets/`, one file each, readable only by the user; the operating system's keychain can be added
  later, with its own decision. The guide tests a key with a request of a few tokens and lists the endpoint's models.

### 7.7 Rules that keep Clank portable

- No path, port, GPU identifier or user name is written into the code: each comes from the user's configuration, with
  a documented default.
- Every file in `config/` carries a schema version. A newer Clank migrates an older file, keeps a copy of the
  original, and has a test for every migration.
- The tests run on a machine without a GPU (with fake servers), so anyone can run them, and so can continuous
  integration (§8).
- Recipes and templates live in the repository: supporting another machine or provider is adding a file.

What the guide's first screen could look like:

```
 CLANK SETUP   1 machine   2 where the model runs   3 install   4 test   5 tools
  machine   Windows 11 with WSL2 (Ubuntu 22.04) · RTX 5080, 16 GB · driver supports CUDA 13.x · 62 GB RAM
            hardware GPU scheduling off (good) · WSL memory limit 48 GB · Docker installed
  How do you want to run a model?
  > On this machine        fits: NInfer RTX 5080 (fastest, up to 128K), KVMem (262K), llama.cpp
    With an API key        a hosted model, through an OpenAI-compatible API
    On another computer    a server on your network, or on an HPC cluster through SSH
  Enter choose   ? what this means   Esc later
```

## 8. Testing

*Approved 2026-10-11.*

What is not tested does not work (principle 7). Tests are also documentation: each one says what it proves and which
part of the design it holds to, so a person or a model can see what is covered and what is not.

### 8.1 Layers

| Layer | What it proves | Where it runs | What it needs |
| --- | --- | --- | --- |
| Unit | Each module alone: option schemas and validation, the memory-fit arithmetic, where each value comes from (§3.5), file schemas and migrations, dialect translators, queues, the slot state machine | Every machine, every commit | Nothing: no GPU, no network |
| Contract | Every adapter of a kind meets the same interface (§8.2) | Every machine, every commit | Fixtures recorded from the real engines (§8.3) |
| Fake servers | The runtime service and the gateway end to end, against fake engines that behave like each serving setup: its API dialect, streaming, tool calls, thinking fields, slow starts, crashes, and errors such as "failed to find a memory slot" | Every machine, every commit | The fakes in `tests/fakes/` |
| Console | Headless: keys, screens, forms, the explain key, snapshots of every screen, the redraw limit and the console's own CPU use | Every machine, every commit | Textual's test harness |
| Real engines | Each serving setup installs, launches, answers and passes its smoke suite | A machine with the GPU and the engine, on demand and before every release | The engine and its model |
| Trials (§3.8) | One configuration on this machine: smoke, speed, memory, context, quality | The user's machine, from the console | The configuration |

Every test runs against a temporary `CLANK_HOME`, never the user's.

### 8.2 Contract tests make plug and play safe

For each kind of plug-in (engine adapter, endpoint adapter, dialect translator, console panel) there is one contract
test file, run against every plug-in of that kind. A new serving setup is accepted when it passes the same contract as
llama.cpp, KVMem and NInfer: its options are well formed and each one's `maps_to` is valid; its plans for the known
presets match the recorded command lines exactly; it reads health and metrics from the recorded logs; it stops what it
started and nothing else. This turns principle 2 (plug and play) into something checked on every commit.

### 8.3 Fixtures recorded from the real engines

`clank dev capture <setup>`, run on a machine that has the setup, records what the engine really produces at its
pinned version (its help text, its version, log lines, API answers including streamed pieces) into
`tests/fixtures/<setup>/<version>/`, checked into the repository. Contract and fake-server tests use these recordings.
When a setup's version changes, capturing again shows the difference, so a renamed flag or a changed log line fails a
test instead of surprising the user.

### 8.4 Continuous integration

On every push, GitHub Actions runs on Linux: the unit, contract, fake-server and console tests; a lint and type check;
validation of every JSON file in the repository against its schema; a documentation check (every link resolves, every
decision is in the index, every design section has a status); and a scan that refuses anything that looks like a key,
a token, a home path or a machine identifier. The console's tests also run on Windows. Tests that need a GPU cannot run
there; they run on the owner's machine before each release, and their results go into the release notes. The tools
(test runner, linter, type checker, Textual's snapshot plugin) are chosen in a decision record when the
implementation plan is written.

### 8.5 Tests say what they prove

Each test file begins with a docstring naming the behavior and the design section it verifies, and test names are
sentences:

```python
"""Design 0001 §4.2: a switch whose new provider fails its health check goes back to the last configuration that
worked, and the history records both steps."""


def test_a_failed_start_returns_to_the_last_configuration_that_worked(runtime, fake_engines): ...
```

From these docstrings a generated page, `docs/TESTS.md`, lists every design section with the tests that hold it to its
word, and shows the sections that have none yet.

### 8.6 Tests come first

During implementation every behavior starts as a failing test, then the code that makes it pass (the plan for each
part says which tests come first). A bug fix starts with a test that reproduces the bug.

### 8.7 The computer stays usable, measured

Tests hold Clank to principle 6 with numbers: the console redraws at most four times a second and stays under a CPU
limit while idle and while the model streams; the gateway adds less than a stated delay per request (measured with
the fake servers); the runtime service's memory stays bounded over a long run with many requests.

### 8.8 Model quality is measured, not asserted

The `context` and `quality` suites (§3.8) are measurements: fixed tasks with checked answers and facts placed at
known depths, kept in `clank/suites/` with their expected answers. Their results are compared across presets and over
time; they inform choices and do not block a commit.

## 9. Order of work, and what comes over from the prototype

*Approved 2026-10-11. Revised when [design 0002](0002-the-foundation.md) §3 was approved: its milestones replace those
of §9.1.*

### 9.1 Milestones

*Replaced when design 0002 §3 was approved.* The milestones are now those of
[design 0002 §3](0002-the-foundation.md#3-the-skeleton-m0-and-the-order-of-milestones): M0, the skeleton (the kernel,
the service and its API, the `clank` command, the console's shell, the VS Code extension's shell), then M1 to M10. This
design's M1 (runtime core with KVMem), M2 (NInfer RTX 5080 and llama.cpp, with trials) and M3 (the gateway, now with
inline completion in VS Code) keep their numbers and their content; its M0 became design 0002's M0; its M4 (the
console) is spread over every milestone, each bringing its own screens; its M5 (the setup guide) became M10. The
reasons given for the order still hold: the riskiest question (one adapter interface for three different programs)
comes first, and what the owner needs soonest (switching serving setups and seeing their speed on this machine) right
after it.

### 9.2 Living next to the prototype

The prototype stays the owner's daily tool until Clank replaces each of its parts.

- **One model on the GPU at a time.** Clank never starts an engine while another program's server holds the GPU or
  the port; it says which program and how to stop it (§4.6).
- **The port in between.** Until Clank's gateway exists (M3), Clank's engines listen on the address the prototype's
  tools already use, so OpenCode, the prototype's gateway and its monitor keep working with an engine Clank started.
  From M3, the gateway takes that address and the engines move to internal ports.
- **Importing the prototype's settings.** `clank import` turned the prototype's model registry into presets and
  catalog entries the owner could read before anything used them (built in M1.5, removed 2026-10-13 by decision 0033:
  Clank needs nothing from the prototype).

### 9.3 What comes over, and when

| From the prototype | Into | When |
| --- | --- | --- |
| The GGUF reader and the memory-fit estimate | The model catalog and the fit check (§2, §3.6) | M1 |
| Server profiles (`registry.json`) | Presets, through `clank import` (removed 2026-10-13, decision 0033) | M1 |
| How servers are identified and stopped (`server.py`, `kvmem_service.sh`) | The KVMem adapter and §4.6 | M1 |
| The speed benchmark's method (`bench/speed.py`) | The `speed` suite | M2 |
| The gateway's records and its local title answers | The gateway (§6.5, §6.4) | M3 |
| The monitor's collectors and context panel, and its terminal view | Runtime metrics and the console's models screen | M1 |
| Completion; the sandbox; the workbench; the companion | The gateway's completion role and the VS Code extension; workspaces and containers; VS Code as the place of work; later | M3; M4; M6; later |
| The lessons in [PROTOTYPE.md](../PROTOTYPE.md) | Checks in `clank doctor`, the slowdown warning, tests | M0 onward |

### 9.4 Risks known now

- **NInfer under WSL2.** The release is qualified on native Linux; a community report says WSL2 works on an RTX 5080.
  The Windows driver must support CUDA 13.4, and the desktop's own GPU memory (about 1.5 GB on the owner's machine)
  may not leave room for the published profile's 131,072-token KV capacity. M2's trial answers both; any deviation is
  recorded (decision 0010).
- **Speed on a busy desktop.** On 2026-10-11 decoding ran at half its benchmark speed while the desktop was in use; the
  cause is not yet confirmed. The speed suite (M2) and the slowdown warning (§4.4) measure it for every setup.
- **Long builds and large downloads.** NInfer's CUDA build takes a while and its model is 16.5 GB. Both run as visible
  jobs that ask first (§7.4, §7.5).

## Revision log

Every change to an approved section, with its reason. Approvals themselves are in the status table above.

| Date | Section | Change | Why |
| --- | --- | --- | --- |
| 2026-10-11 | §1 | "Engine adapters" became providers (managed engines and endpoints) | The owner asked for API keys and HPC servers too |
| 2026-10-11 | §2 | The first serving setups named | Decision 0010 |
| 2026-10-11 | §3.8 | Check and test before applying, added | The owner's request (decision 0009) |
| 2026-10-11 | §1 | The diagram lists the first serving setups; the starting slots (`main`, `fast`) named; who can reach the runtime API stated | Self-review: the diagram predated decision 0010; slots and access were unstated |
| 2026-10-11 | §2 | The option fields deferred to §3.1; the endpoint adapter separated from the gateway's dialects; secrets and the machine profile placed in `CLANK_HOME` | Self-review: two lists of fields disagreed; two meanings of "dialect"; paths predated §7.2 |
| 2026-10-11 | §3.3, §3.4 | The `default` role made explicit; a slot runs one preset at a time; a preset names its engine version | Self-review: gaps |
| 2026-10-11 | §3.7, §3.8, §4.8, §5.5, §5.6, §6.1, §6.5, §8.8 | Paths made consistent: Clank's own files in the `clank/` package, the user's in `CLANK_HOME`, suites in `clank/suites/` with user overrides | Self-review: `local/`, `logs/` and `tests/suites/` predated §7.2 |
| 2026-10-11 | §6.3 | Upstream llama.cpp's thinking fields left to its recorded help instead of asserted | Self-review: not verified |
| 2026-10-11 | §1 | The runtime service became the runtime component of the Clank service; design 0002 §1's diagram replaces this one | Design 0002 §1 approved (decision 0013) |
| 2026-10-11 | §6.6 | Sandboxed tools reach the gateway through their sandbox's edge | Design 0002 §1 approved |
| 2026-10-11 | §3.7, §3.8 | The example preset names its schema; a trial is an operation of the Clank service | Design 0002 §2 approved (records name their schema; operations) |
| 2026-10-11 | §4.2, §4.8 | A switch is an operation and its busy check a question; the history is the event log in the state database instead of `logs/runtime.jsonl` | Design 0002 §2 approved (decision 0014) |
| 2026-10-11 | §5, §5.3 | The console became the control center of every component; §5.3's screens became the parts of its models screen, built in M1 | Design 0002 §3 approved |
| 2026-10-11 | §6.4 | What a provider supports at once is what its adapter declares for its version and launch options (KVMem v0.17 can run several requests) | Design 0002 §2 approved (§2.10), after the outside review checked KVMem's releases |
| 2026-10-11 | §7.2 | `CLANK_HOME` gained the state database, the local token, the service's address, the spool, `library/`, `artifacts/` and `logs/processes/` | Design 0002 §2 approved (§2.16) |
| 2026-10-11 | §9.1, §9.3 | The milestones replaced by design 0002 §3's, and §9.3's milestone numbers changed to match | Design 0002 §3 approved |
| 2026-10-12 | §7.1 | On Windows the service runs on Windows and the engines in WSL distributions, through hosts | Decision 0030 (design 0003 §2) |
| 2026-10-21 | §3.2 | An engine's own sampling defaults are also launch options, unset unless a preset sets them, shown with the engine's default | The owner: make these settings visible (decision 0119, design 0003 §4.1) |
