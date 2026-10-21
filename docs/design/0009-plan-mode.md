# Design 0009: plan mode, and handing a plan to the agent

The owner (2026-10-15): "a plan mode where we have no interest in writing up any code or making any figures, all this
would do is be the planning agent that I can toggle in the Clank menu or in the bottom of the VS code window ... we can
just send the detailed plan to either a review or auto agent to begin implementing the plan ... generalized to any
simulation that I will do, so nothing is super rigid". The owner's layout is the plan the agent wrote for a study
(a study's `plan.md`): the question, a table of parameters with the spec, the expected time, each figure with its
quantity, axes, what it shows and its file, and the output's tree.

The owner's choices (2026-10-15): phase 1 is built first, then phase 2; the planner may write any Markdown file; the
implementer starts in a fresh session; in review mode the implementer's edits to the plan are accepted and shown.

And, the same day: "if we are planning a large simulation, [we] benchmark an estimate for the runtime for a single
thread and for some maximum number of specified threads ... and obtain an estimate for how much
storage will be required ... if I include an upper limit for the runtime of the simulation then it should suggest
changes to the parameters to bring the runtime down. We should also include explicit layouts of how the data will be
stored, where it will be stored, and so on." And: "a clear 'Deliverables' final section that goes into exactly what I
want back, which will almost certainly be some kind of markdown document summarizing everything ... it should also
just straight up include the plots ... 'Plots' should also be its own section (so 'Deliverables' will just refer to the
plots in the 'Plots' section) where we can go into detail on the plotting details/settings/configurations for each
individual plot."

**Status:** written 2026-10-15; approved by the owner the same day ("write the phase 1 plan and begin implementing").
§1-§6 are phase 1, built 2026-10-15 ([the plan](../plans/s2-plan-mode.md)); §7 and §8 are phase 2, built
2026-10-16 ([its plan](../plans/s3-plan-mode-phase-2.md)).
Measured on building: in a workspace's container, the planner saw exactly the six tools a test project's server marked read-only,
wrote a plan, and was refused a `.py` file.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Approved 2026-10-15; built (phase 1) |
| 2 | What OpenCode 1.19 offers, as measured | Approved 2026-10-15 |
| 3 | The planner | Approved 2026-10-15; built |
| 4 | A plan | Approved 2026-10-15; built |
| 5 | Implementing a plan | Approved 2026-10-15; built |
| 6 | Outside Clank | Approved 2026-10-15; built |
| 7 | Choosing the mode from Clank (phase 2) | Approved 2026-10-15; revised 2026-10-16 by measurement (Tab, not the session's agent); built 2026-10-16 |
| 8 | Handing a plan over from VS Code (phase 2) | Approved 2026-10-15; revised 2026-10-16 (a first message, not a command); built 2026-10-16 |
| 9 | What plan mode does not cover | Approved 2026-10-15 |

## 1. What the owner gets

- **Plan mode.** An agent that plans and writes plans, and nothing else: no code, no scripts, no figures, no runs. In
  OpenCode, Tab switches between **Build** and **Planner** (phase 1). In phase 2 the workspace's mode, shown in VS
  Code's status bar and on the console's folder page (F4), is one of **Plan**, **Review** and **Auto**.
- **A plan.** A Markdown file with a short header, the sections the folder's template sets, and a checklist of steps
  (§4).
- **Cost and data, measured.** For a large simulation the planner measures the runtime on one thread and on the owner's
  thread count, and the storage, before the plan is ready. Given a limit on the runtime (or the
  storage), it proposes changes to the parameters that bring the run within it, each with its new cost and what it
  gives up. The plan lays out the data: where each file goes, what it holds, how large it is (§4.1).
- **Plots, each specified whole** (§4.2), and **Deliverables**, the plan's last section, saying exactly what the owner
  gets back: a report in Markdown with the parameters, the observables, the scripts, the data and its layout, the
  runtime and throughput of each run, the storage and what makes it up, and the plots themselves (§4.3).
- **Implementing it.** `/implement <plan>` in OpenCode (phase 1). In phase 2, an open plan in VS Code shows
  **▶ Implement with Review**, **▶ Implement with Auto** and **↻ Continue** at its top; each starts a fresh session.
- **The implementer** follows the plan step by step, ticks each step and logs what it did, and stops to ask when the
  plan is wrong or a check fails (§5).

## 2. What OpenCode 1.19 offers, as measured

Measured on 2026-10-15 with OpenCode 1.19.0 (the image's version) in a workspace's container, from its own API
(`GET /agent`, `GET /command`, `GET /doc`) and its binary's text.

- **Agents.** `build` and `plan` are primary; `explore` and `general` are subagents; `compaction`, `title` and
  `summary` are hidden. OpenCode's `plan` may edit only `.opencode/plans/*.md`, may ask questions, and has a
  `plan_exit` tool that asks "Plan at <path> is complete. Would you like to switch to the build agent ..." and then
  continues the same session. While it is the agent, OpenCode adds a reminder that it must not edit anything but its
  own plan file.
- **Rules.** An agent's rules are OpenCode's base rules, then the agent's own, then the configuration's top-level
  `permission`; the agent's `permission` in the configuration comes after those. The last rule that matches wins.
- **A fault this design fixes.** Clank's top-level `edit: ask` comes after the `plan` agent's own `edit: deny`, so
  under Clank OpenCode's planner may ask to change any file, and auto mode says yes. §3 gives the planner its own rules,
  which come last.
- **Routes** Clank can drive a running OpenCode with: `POST /api/session/{id}/agent` (switch a session's agent),
  `POST /tui/select-session` (show a session in the terminal interface), `POST /session/{id}/command` (run a command,
  with an agent), and `/tui/append-prompt`, `/tui/submit-prompt`, `/tui/execute-command`.
- **MCP prompts are commands.** A server's prompts appear as commands named `<server>:<prompt>`.

## 3. The planner

Clank's OpenCode configuration gains a primary agent, `planner`, and disables OpenCode's `plan`, so Tab switches
between Build and Planner, and OpenCode's plan reminder, which names its own plan file, never applies.

Its rules are its own `permission` in the configuration, so they come after every other rule (§2):

| What | Rule |
| --- | --- |
| Editing files | denied, except Markdown files (`*.md`) anywhere in the folder; those are allowed without asking. Denied again for the files other agents and assistants load as settings or instructions: anything under `.opencode`, `.claude`, `.git`, `.github`, `.vscode`, and `AGENTS.md`, `CLAUDE.md` (revised 2026-10-15 after the review: a planner that wrote those would set the rules of the next session) |
| Commands | reading ones only: `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `echo`, `pwd`, `diff`, `nl`, `file`, `stat`, `du`, `which`, `git status`, `git log`, `git diff`, `git show` (none has a flag that writes a file or runs a program; `find`, `rg`, `sed`, `sort` and `tree` have, and OpenCode's own read, glob, grep and list tools read instead). Any other command is refused at once, never asked (revised 2026-10-17, the owner: "It should never be asking to do anything when it is in Plan mode ... asking questions for clarification, never permission to run code"; it had asked to run `python3 -c`, `sed -n`, `git -C` and `echo`); so is a reading command that is redirected, substituted or told to write a file (`--output`), and a call repeated (`doom_loop`). OpenCode checks each part of a chained or piped command on its own, so reading commands piped together run. The `explore` helper the planner may call reads under the same rules |
| MCP tools | allowed when their server marks them read-only (`readOnlyHint` in the last check of the server, design 0004 §10); denied otherwise, so the planner does not see them |
| Questions | allowed (the `question` tool) |
| Subagents | `explore` only |
| The web, outside the folder | denied, as for every agent |

The planner's own edits are allowed outright, so they never reach Clank's review: VS Code shows the plan as it changes
when it is open. Build keeps every rule it has.

### 3.1 The planner's instructions

Kept in `clank/components/agents/prompts/planner.md`, given to OpenCode as the agent's prompt. In outline:

1. Understand the request. Read the folder's `AGENTS.md`, the plan template it names, and earlier plans.
2. Ask what is unclear with the `question` tool, a few things at a time, before writing.
3. Check with the read-only tools: validate every spec, estimate time and memory. Every number in the plan comes from
   a tool, a file or the owner, never from the model's own arithmetic.
4. Measure a large simulation (when the estimate passes about ten minutes, or when the owner asks): the runtime on one
   thread and on the owner's thread count, and the storage, with the simulator's benchmark (§6). When the owner gives a
   limit on the runtime or the storage and the run exceeds it, propose two or three ways to fit, each changing as
   little as it can (fewer trajectories, a coarser or narrower grid, fewer sizes, fewer evaluations of the costly
   probes, a smaller exhaustive cutoff), each with its cost from the estimate scaled by the measurement, and what it
   gives up (larger error bars, a size fewer). The owner picks; until then the choice is an open question.
5. Write the plan (§4). Never write code, scripts or figures, and never start a run (a benchmark writes nothing and is
   not a run).
6. Review it: every quantity is defined exactly; every plot is specified whole (§4.2); the checks are listed; the steps
   are concrete and in order, and the last one makes the deliverables; the costs come from tools and fit the owner's
   limits; the data's layout names every file; the deliverables name the report and everything in it, every plot
   included; every assumption is an open question. Set `status: ready` only when no open question
   is left.
7. End by saying how to hand it over: in phase 1, `/new`, then `/implement <path>`; in phase 2, the buttons (§8).

## 4. A plan

- **Its header** (front matter): `kind: plan`, `status:` one of `draft`, `ready`, `implementing`, `done`, and
  optionally `title:`. Clank knows a plan by this header, not by its place: a folder keeps its plans where it likes
  (for example `studies/<name>/plan.md`).
- **Its sections** are the folder's: its `AGENTS.md` names a template. When none is named, the planner uses Clank's
  default, the owner's layout made general:
  - **Question:** what is to be learned, and what would answer it.
  - **Parameters:** a table of every quantity and its values, the spec as it will run, the seeds.
  - **Cost:** the runtime and the storage (§4.1), the owner's limits and whether the run fits them, and how each part
    runs (at once, as a job, in the background).
  - **Checks:** what must hold before a result is trusted: known limits, a pilot, cross-checks.
  - **Plots:** each plot specified whole (§4.2); tables, when the study has them, the same way.
  - **Data:** where the data goes and what it holds (§4.1).
  - **Steps:** a checklist (`- [ ]`), in order, each step small enough for one sitting; the last makes the
    deliverables.
  - **Open questions:** what the owner must decide; empty when the plan is ready.
  - **Log:** one line per step done, written by the implementer.
  - **Deliverables:** always the last section: exactly what the owner gets back (§4.3).
- **Nothing is rigid.** A section that does not apply says so in one line; a study adds the sections it needs.

### 4.1 Cost and data

- **Cost** is a table, one row per point or group of points: the trajectories; the runtime on one thread and on the
  owner's thread count, each marked *estimated* (the simulator's model), *measured* (the benchmark) or *projected*
  (measured where the machine allows, scaled beyond it); the memory of the result; the storage on disk. Then the
  totals, the owner's limits, and where the run happens (the sandbox has half of the machine's CPUs; Windows has all).
- **Data** is the tree of every file the work leaves, each with what it holds (for arrays: name, shape, type, size),
  where it lives (`runs/<tag>/` and the like), how it is named, its size, and whether it is kept in git, kept outside it
  or made again from the seeds. Its sizes come from the benchmark or the estimate, never from guessing.

### 4.2 Plots

One subsection per plot, enough to draw it without asking:

- **Quantity:** what is plotted, defined exactly (the formula, or the observable's name in the simulator and its
  definition), and from which arrays of which files.
- **Axes:** each axis's quantity, units, scale (linear, logarithmic), range and label; the curves or series (one per
  what), and what the error bars are (one standard error over what).
- **Look:** markers and lines, colors or the colormap, the legend and where it goes, insets, reference lines (a known
  value, a fit), the size, the resolution and the file format.
- **What it shows:** what to read off it, and what would be surprising.
- **File and script:** the file it is saved to and the script that makes it.

### 4.3 Deliverables

The plan's last section. It names what the owner gets back, usually one report in Markdown (for example
`studies/<name>/report.md`), and what the report holds:

- the parameters as they ran, and the observables with their definitions;
- the scripts: which ones ran the simulations and which computed the observables and made the plots, by path;
- the data: where it is and its layout (§4.1), as it turned out;
- the cost as it turned out: for each run, the runtime, the threads, and the average samples (trajectories) per
  second; the storage in total and broken down by what contributes to it (each file, and in a result each array);
- the plots: each one embedded in the report (`![...](path)`), referring to its specification in the plan's Plots
  section, with its file;
- what the checks found, any deviation from the plan, and anything else the plan asks for.

Every number in the report comes from a script's output or a saved file.

## 5. Implementing a plan

- **`/implement <path>`** is Clank's command in OpenCode's configuration, run by `build`: the instructions of §5.1 with
  the plan's path. It is run in a new session (`/new` first), so the model's context holds the plan and not the
  conversation that made it (the owner's choice). Phase 2's buttons start the session themselves.
- **Continuing** is the same command: the implementer resumes at the first step not ticked.
- **In review mode**, an edit to a Markdown file in the folder whose header says `kind: plan`, before the edit or after
  it (the implementer's ticks and log lines), is accepted at once (never a file the planner may not write, §3: a
  header there must not let a change past the owner; revised 2026-10-15 after the review) and shown afterwards, as in auto mode (the owner's choice). Every other change asks as before
  (design 0007 §3).

### 5.1 The implementer's instructions

Kept in `clank/components/agents/prompts/implement.md`. In outline: read the plan whole; set `status: implementing`;
take the first step not ticked, do it, tick it, and add one line to the log (what was done, the files, any deviation);
follow the plan exactly; log each run's actual runtime and size beside the plan's cost, and stop to ask when one exceeds
it by more than half; when a step is wrong or ambiguous, or a check fails, stop and ask with the `question` tool
instead of improvising; never change the plan's question, parameters or plots without asking; run long work as the
folder's `AGENTS.md` says; make the deliverables as the plan's last section says, every number in them from a script or
a saved file and every plot embedded; when every step is ticked, set `status: done` and point the owner to the
deliverables.

## 6. Outside Clank

What a program's own tools give the planner. Clank needs nothing of them, but a planner can only measure what a
program offers; a simulator built for planning offers this (in one service, so its command line, its MCP server and
its Python share it):

- **An estimate** that takes `threads`, a list of thread counts (for example `[1, 32]`), and gives its estimate for
  each, and the result's layout: each array the saved result holds, with its shape, type and size, and the files
  beside it.
- **A benchmark** (`spec`, a sample size, `threads`) that runs a sample of the run's own work (the first part, with
  its seed), after a warm-up, on one thread and on the most threads the machine gives it, within a few tens of
  seconds. It reports the seconds per sample, the projected runtime of the whole run for each thread count asked
  (measured up to the CPUs it had, and beyond them scaled by the program's own model, marked *projected*), the ratio of
  measured to estimated time (to scale further estimates), and the storage: the sample saved as the real run saves it,
  scaled to the whole run. It writes nothing.
- **Its saved results' summary** gives the storage as it is: each file's size, and in a result each array's, so a
  report can break the total down without arithmetic of its own, beside the runtime and the throughput.
- **Its MCP server marks its read-only tools** (`readOnlyHint`): what describes, estimates, benchmarks or reads. The
  tools that run or cancel work are not marked, so the planner does not get them.
- **Clank's MCP check** keeps each tool's annotations with its name, so §3's rule can use them.
- **A folder's plan template** (for example `studies/TEMPLATE.md`, with checks, steps, open questions and a log) is
  named in its `AGENTS.md`.

## 7. Choosing the mode from Clank (phase 2)

- The workspace's mode, as the owner sees it, is **Plan**, **Review** or **Auto**. VS Code's status bar item shows it,
  and clicking it picks one of the three. On the folder page (F4), `p` chooses Plan and `r` Review or Auto.
- **Plan:** Clank switches OpenCode's window to `planner`. **Review** and **Auto:** to `build`, and the change rule is
  set as now (design 0007 §3). With no window running the rule is set, and a note says the agent was not switched.
- **Measured, 2026-10-16** (a real terminal interface on a pseudo-terminal, driven through its API; revised from the
  section as approved, which switched the session's agent through `POST /api/session/{id}/agent`): the window keeps
  its agent to itself, and switching a session's agent through the API does not change it; `POST /tui/execute-command`
  with `agent_cycle` (the command's old name, which 1.19 maps to `agent.cycle`) does what Tab does; showing another
  session (`/tui/select-session`) makes the window take that session's last message's agent, and showing the one it
  shows changes nothing. So Clank switches by Tab, as many times as the window's agents need (their order is Tab's:
  the primary agents shown, from `GET /agent`), from the agent it knows.
- **The agent Clank knows** is the agent of the last message sent in the window, which the watcher says (an `agent`
  line for each message, from the server that runs a terminal interface: an `opencode --port` process, not `opencode
  serve`, read from the container's processes), and Clank's own switches. Tab pressed with nothing sent since is not
  seen from outside: the next message corrects what the status bar and the folder page show. A window not seen yet
  works with `build`, OpenCode's first agent.

## 8. Handing a plan over from VS Code (phase 2)

- An open plan (§4's header) shows at its top: **▶ Implement with Review**, **▶ Implement with Auto** and
  **↻ Continue** (with how many steps are done).
- Each calls `POST /agents/implement` with the workspace, the plan and the mode. The service checks that it is a plan
  of the folder (§4, `plans.py`) and that a window runs (VS Code offers to open it first when none does, then hands
  the plan over once the window runs, half a minute at most: it took 5 s on the owner's machine), sets the
  change rule, makes a session in that window whose first message, sent by `build`, is `/implement`'s instructions with
  the plan's path (sent as a message, since `/session/{id}/command` waits for the whole run), and shows it once that
  message is there, so the window takes `build` (measured, 2026-10-16). `GET /agents/plans` lists the folder's plans.
- On the folder page, `i` picks a plan, then Review or Auto.

## 9. What plan mode does not cover

- **Commands outside the reading ones** are refused in plan mode (revised 2026-10-17): what only running code can show
  becomes a step of the plan, and Build runs it.
- **Markdown can hold anything,** code blocks included: the planner's rules keep it from writing other files, not from
  writing code inside a plan.
- **The rules are OpenCode's** (decision 0038). Design 0002 §2.6's plan mode, enforced by the container with the folder
  mounted read-only, stays the later and stronger form.
- **A benchmark in the sandbox measures the sandbox:** half of the machine's CPUs. A larger thread count is projected,
  and says so; a run on Windows with every thread can be measured there (the program's own benchmark, in the folder's
  own environment).
- **A small model plans less well than a large one.** A plan can be read by another assistant before it is implemented
  (Claude Code: "review studies/<name>/plan.md").
