# Design 0006: completion in VS Code (the rest of M3's completion)

The owner (2026-10-15) asked to "begin working on the workspaces, completion, requests, and Phone section of the menu".
Design 0002 §3.3 brought completion forward to M3: "inline completion in VS Code, served through Clank", and its
milestone table asks that "completion meets its latency target while the agent is writing". Design 0001 §1 gave it the
`fast` slot: "One GPU usually fits one large model, so managed providers that need the GPU share it one at a time;
endpoints and CPU engines run alongside."

**Status:** written 2026-10-15, every section *proposed*, built as proposed at the owner's
instruction; **Choice** marks what the owner may decide otherwise.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-15 |
| 2 | Where it runs: a small model on the CPU | Proposed 2026-10-15 |
| 3 | The engine, the model and the `fast` slot | Proposed 2026-10-15 |
| 4 | The gateway: fill in the middle, newest wins | Proposed 2026-10-15 |
| 5 | VS Code | Proposed 2026-10-15; built 2026-10-15 (extension 0.4.0), revised: what it sends |
| 6 | The console's Completion page | Proposed 2026-10-15; built 2026-10-15 (the `completion` settings, F8) |
| 7 | Order of work | Proposed 2026-10-15 |

## 1. What the owner gets

Gray text after the cursor in VS Code, as one types: the rest of the line, or the next few lines on an empty line after
a block opens; Tab takes it, typing on ignores it. It comes from a model on this computer, through Clank: nothing leaves
the machine. A click on Clank's item in the status bar turns it off and on; the console's Completion page (§6) shows
whether it is served, how fast, and lets the owner start and stop it.

## 2. Where it runs: a small model on the CPU

[The measurement of 2026-10-15](../measurements/2026-10-15-completion-on-the-cpu.md) settled it:

- The main slot cannot serve it. KVMem's server has no fill-in-the-middle endpoint (only chat completions) and runs one
  request at a time: a completion would wait behind the agent's whole answer. A chat request for a few tokens would also
  take the slot's cache from the agent.
- The GPU has about 600 MiB free beside `daily 262K`: no room for a second model.
- On the CPU, Qwen2.5-Coder 0.5B (Q8_0, 531 MB) in llama.cpp's server writes the rest of a line in **about 0.3 s per
  keystroke** on 6-8 threads (1.2-1.5 s the first time in a file or after a jump), and what it wrote fit the place. The
  1.5B model took 2.4-3.4 s: too slow here.

So completion runs on the CPU, on **6 threads** (**Choice**: 8 are 10-15% faster; 6 leave more to the owner, whose
computer must stay responsive). The GPU model is untouched: the agent loses nothing.

## 3. The engine, the model and the `fast` slot

- **Engine `llamacpp`**: upstream llama.cpp's `llama-server`, its CPU build for Ubuntu x64, from the project's own
  release archive, pinned by build and checksum (a recipe, design 0003 §7.1: build `b11588` of 2026-10-13,
  `llama-b11588-bin-ubuntu-x64.tar.gz`, 17.7 MB). It installs in the `wsl` host (`Ubuntu-22.04`) beside KVMem, in
  `~/.clank/engines/llamacpp/b11588`. Its adapter (design 0003 §4) knows `context`, `threads`, `cache_reuse` and
  `parallel`; it is ready when its log says the server listens and `/v1/models` names the model. A new engine is a new
  dependency: [decision 0035](../decisions/0035-completion-runs-on-the-cpu.md).
- **Model `qwen2.5-coder-0.5b`** in the catalog: `ggml-org/Qwen2.5-Coder-0.5B-Q8_0-GGUF`, one file of 531,068,128
  bytes with its checksum; downloaded to the host's `models/` like any model file (design 0003 §7.2).
- **Slot `fast`** beside `main` (the runtime's settings: `slots: [main, fast]`), with **a port of its own**: `main` keeps
  18200, `fast` takes 18201 (a slot's port becomes a setting, `ports`). A CPU engine plans no GPU memory, so the GPU
  check that guards `main` does not stop it, and loading or switching `main` leaves `fast` running.
- **Preset `completion 0.5B`** (Clank's own, slot `fast`): the model above, 6 threads, an 8,192-token context, one
  request at a time, cache reuse in chunks of 256 tokens.

## 4. The gateway: fill in the middle, newest wins

- **Role `completion`** names the `fast` slot (design 0001 §3.3's roles), as `daily` names `main`.
- **`POST /v1/infill`**, llama.cpp's own dialect (`input_prefix`, `input_suffix`, `prompt`, `input_extra`,
  `n_predict`, `stop`, ...), with `model` naming the role: the gateway forwards it to the role's slot unchanged but for
  its limits (`t_max_prompt_ms`, `t_max_predict_ms`: a late completion is worth nothing).
- **Newest wins.** A completion is worth something only until the next keystroke: when a new one comes for the role,
  the gateway breaks off the one in flight (it closes its connection to the engine, which stops it; the client's answer
  is an empty completion). VS Code also cancels what it no longer needs, so a request rarely waits.
- **Kept briefly.** Completions come at typing speed; each is counted, not recorded like the agent's requests: the
  gateway keeps the last 200 in memory (when, the tokens read and written, the time to the answer, whether it was
  broken off) and `GET /completion` gives them with their median and 95th percentile; the Requests page (F7) stays the
  agent's.

## 5. VS Code

Clank's extension registers an inline completion provider for every file it has a document for:

- **When.** After the owner stops typing for 120 ms (the request is canceled when typing goes on), not inside a
  selection, not when the line after the cursor holds more than closing brackets and quotes.
- **What it sends.** The file's text before the current line, up to 120 lines (about 1,000 tokens), the current line
  up to the cursor, and what follows, up to 20 lines (about 250 tokens: the measured cost of each keystroke is mostly the
  suffix read again). *Revised when built (2026-10-15):* no first line with the file's name and language; llama.cpp's
  infill has no place for it outside extra chunks of context, and the measurement was made without it. **One line** (stop at the line's end, at most 32 tokens), or **a
  few lines** (at most 64 tokens, stop at a blank line) when the cursor is on an empty line after one that opens a block
  (ending with `:`, `{`, `(`, `[`).
- **Where.** The gateway's address, from the service (as the extension finds the service today); in the workspace's
  window as in any other.
- **On and off.** A status bar item, `Clank: completion` with a check or a slash; clicking it turns completion off or on
  for every window (the `completion` setting of §6, so the console and VS Code agree). When the `fast` slot is not
  serving, the item says so and nothing is requested.

## 6. The console's Completion page

The menu's Completion entry (F8) becomes a page:

- **Served?** The `fast` slot's state and preset, its engine and model, installed or not; keys: `l` loads (installing
  the engine and downloading the model first when they are missing, each as its own operation the owner can follow),
  `u` unloads, `x` turns completion off or on in VS Code.
- **How fast.** From the gateway's last 200 completions: how many in the last minute and hour, the median and 95th
  percentile time to the answer, how many were broken off by newer ones; the last ten, each with its tokens and time.
- **Settings.** The `completion` setting (on, the delay before asking, one line or a few) with each value's source, as
  the Launch options page shows a preset's.

## 7. Order of work

1. The engine, the model and the slot (§3): the adapter, the recipe, the catalog entry, per-slot ports, the preset; a
   fake engine in tests; a real load on this computer, measured.
2. The gateway's `/v1/infill`, the role, newest wins and the in-memory counts (§4).
3. The Completion page (§6) and the `completion` setting.
4. VS Code (§5).

Each step is tested and pushed on its own; the measurement is repeated through VS Code when step 4 is done.
