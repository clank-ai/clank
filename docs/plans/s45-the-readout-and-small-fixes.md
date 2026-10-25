# Plan s45: the model's readout, and the small fixes

Builds [design 0021](../design/0021-all-llm-work-in-clank.md) §3, §7 (what is said), §9, §10 and the sign-in start of
§11, approved by the owner on 2026-10-25. Each task starts with a failing test; each ends with a commit pushed to
`main`. Jobs (§6), artifacts (§5) and the agent panel (§4) follow in plans s46-s48.

## Tasks

- [x] 1. **The readout's route** (§3): `GET /agents/readout?folder=&session=`: the folder's workspace, its newest kept
  session (or the one named), its `now` and its context totals as their routes give them, the main slot (its state,
  preset, title, and the options that change speed: drafted tokens, CUDA graphs), the GPU's newest meter (memory used
  and total, use), and the drafted tokens accepted as the engine's log last said (`spec_stats`, read by the KVMem
  adapter from the newest launch's log; absent for an engine that does not say it). A folder with no workspace, or a
  workspace with no session yet, answers what there is. Tests: `tests/components/agents/test_readout.py`.
- [ ] 2. **The readout in VS Code** (§3): `core/readout.ts` (the status line, the panel's rows, the speed graph, the
  context bar; tested without VS Code), the status bar item, and the panel: a webview in a group under the agent's
  terminal, a quarter of the column, read once a second while it shows; the agent's group kept at the right edge with
  it; `Clank: Show the model's readout`. Extension 0.9.3.
- [ ] 3. **Seeing images** (§9): the agent's instructions say its model reads no images and `look_at_figure` asks
  Clank's vision model; OpenCode's time limit for a call of Clank's own MCP server is measured (a slow tool in the
  live test) and set above the vision model's longest reading.
- [ ] 4. **The faster settings** (§10): a preset may name a `fallback`; when its engine ends on its own (a crash), the
  slot loads the fallback and says why. "frontier 262K fast (trial)" falls back to frontier 262K. Tests: the runtime's.
- [ ] 5. **The sign-in start** (§11): `clank autostart on|off|status`: an entry in Windows' Startup folder, run without a
  window, that starts Docker Desktop when it is stopped and then Clank's service; shown in Task Manager's startup
  apps like any other. Tests: the entry's command, on, off and status; the docs.

## Progress

Written 2026-10-25.
