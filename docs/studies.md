# Simulations and studies with Clank

How to run simulations and studies with the local agent so that the results can be trusted, reproduced and written up.
The examples use a made-up simulator package with an MCP server (`myproject`, the walkthrough's example), but the
practice holds for any program the agent runs. Design 0004 §10 says how the pieces are built. Everything you do with
the agent, step by step, a whole study with figures marked up for it included: [walkthrough.md](walkthrough.md).

## Before the first study

1. `clank` in the project's folder, then on **This folder**: `o` opens the workspace, `e` installs the folder's
   software into it (for a Python project, `pip install -e '.[dev]'`: the package, its tests and its MCP server's
   libraries), `m` allows the folder's MCP server (its `.mcp.json`). The server's tools then show beside it.
2. `c` opens the folder in Clank's VS Code window with OpenCode beside the files; `a` runs OpenCode in the terminal.
3. Keep the project's `AGENTS.md` accurate: OpenCode reads it at the start of every session, so it is how the model
   learns the project's conventions, entry points and pitfalls.

## The shape of a study

1. **Plan before running, in plan mode.** Choose **Plan** in VS Code's status bar (or F4 `p`, or Tab in OpenCode until
   it shows **Planner**; design 0009). The planner
   writes Markdown and nothing else: no code, no figures, no runs. It asks what is unclear, checks every spec with the
   simulator's read-only tools, and writes the plan in the study's folder (for example
   `studies/2026-10-20-walk-scan/plan.md`), with a header (`kind: plan`, `status: draft` until it is `ready`)
   and the sections the folder's template sets (Clank's default: Question, Parameters, Cost, Checks, Plots, Data, Steps,
   Open questions, Log, and Deliverables last: exactly what you get back). Keep talking to it until the plan is right.
2. **Measure the cost.** For a large run the planner measures it (for `myproject`: `benchmark_run`, on one thread
   and on your thread count; the sandbox has half of the machine's CPUs, so a larger count is projected and says so)
   and adds up the total. Give it a limit ("at most 6 hours on 32 threads") and it proposes changes to the parameters
   that fit, each with what it gives up. A study that would take days is split, or sized down, before it starts.
   - The planner gets only the tools a server marks read-only, as of the server's last check. After a server is
     updated, check it again (`clank mcp check NAME`, or F3 `c`) and start a new OpenCode session.
   - **Hand it over:** open the plan in VS Code and click **▶ Implement with Review** or **▶ Implement with Auto** at
     its top (or F4 `i`; or start a new session with `/new` and type `/implement studies/<name>/plan.md`, in the mode
     the status bar shows). A new session in OpenCode's window takes it, and the Build agent
     carries the plan out step by step, ticking each step and writing a line in the plan's Log; in review mode its
     changes to the plan itself go in without asking, every other change still asks. It stops to ask when the plan is
     wrong, a check fails, or a run costs half again more than planned. **↻ Continue** (or `/implement` again) goes on
     from the first step not ticked.
3. **Pilot, end to end.** Run the smallest version of the whole study, analysis and figure included, and check it
   against what is known (a limit, a published point, a symmetry). A pilot that cannot be checked is not done yet.
4. **The full run, saved as it goes.** Each point gets its own output folder; the simulator saves chunks as they finish
   and resumes from them (for `myproject`: `start_job` with an output folder, then `job_status`). A run of minutes to
   an hour can be an MCP background job, which ends when the agent's session ends. A run of many hours should be the
   simulator's own command line, started in the background in the workspace's container (ask the agent to start it
   with `setsid nohup ... > run.log 2>&1 &`): it goes on after OpenCode closes, for as long as the workspace's
   container runs. Stopping the workspace, Docker or the computer stops it; it then resumes from its saved chunks.
5. **Analysis in code.** A script in the study's folder reads the saved results and writes every figure and number.
   Numbers that go into notes or a paper come from that script's output, never from the model's own text: the model
   summarizes, the code computes.
6. **Record.** Commit the plan, the scripts, the analysis and the small summaries, at a clean state of the code. Each
   run's folder keeps its spec, its seed and its provenance (the code's commit, the versions, the platform), so any
   point can be run again.

## Where things go

- **Code changes** (new observables, speed): on a branch, with the project's tests and its cross-checks (for a
  simulator: against a reference implementation) passing before a study uses them.
- **Raw results**: a folder git ignores (for example `runs/`), inside the workspace's folder so that VS Code and Windows
  see them. Paths the agent gives the simulator are the container's: the folder is `/workspace`.
- **Study folders** (`studies/`): plans, scripts, analysis, figures and notes, committed.

## Working with the local model

- One task per session, said precisely: which study, which points, where the results go. Start a new session for each
  step; a long one is compacted and loses detail.
- Ask the agent to show the exact spec or command before it runs anything long, and to call the simulator's own help
  first (for `myproject`: `capabilities`), so it uses the program's real options rather than remembered ones.
- Check its work: the spec it ran is in each run's folder, and the analysis script reproduces every number.
- It runs in the workspace's container: it sees the folder and nothing else of the machine, and reaches only the model.

## The computer stays usable

- A workspace's container has half of Docker's CPUs and a quarter of its memory unless its record says otherwise
  (`config/workspaces/<name>.json`, `cpus` and `memory_mib`; stop the workspace and open it again to apply). Numerical
  libraries in it start as many threads as it has CPUs (`NUMBA_NUM_THREADS` and the like), so the rest of the machine
  keeps the others.
- The model runs on the GPU and simulations on the CPU: both at once is fine. The panel on the right of the console
  (F5) shows both while they run.
