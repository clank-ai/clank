# Changelog

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
- Linux and macOS: not tested yet; on Linux, the agent's container reaching the gateway is still being built.
- Local models need building: the engine is built in WSL and the model files downloaded, step by step.
- The "daily 262K" preset needs a vision projector Clank cannot download; run it with its vision off, or another
  preset.
- Push alerts to the phone, and the iPhone app (being redesigned); the phone page works in the phone's browser.
- Milestones still to design are listed in [docs/ROADMAP.md](docs/ROADMAP.md).
