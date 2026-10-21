# Working with Clank: the complete walkthrough

Everything you do to get work done with the agent in a project folder, in the order you do it: checking that Clank
runs, setting a folder up once, starting a session, asking the agent for work and reviewing what it changes, a whole
small study from a plan to marked-up figures, long runs, seeing what happens, and finishing. Installing Clank and adding
a model come first: [getting-started.md](getting-started.md). The practice behind the study (why plans, pilots and
analysis in code) is in [studies.md](studies.md); every key of the console is in [console.md](console.md).

The example throughout is a made-up project: `myproject`, a small Python package that simulates random walks on a
lattice, in a folder such as `C:\work\myproject`. It has a command line and an MCP server (`myproject-mcp`, named in
the folder's `.mcp.json`) whose tools are `capabilities` (what it can simulate, with every option), `estimate_run`
and `benchmark_run` (how long a run would take, estimated or measured on a sample), `run_sweep` (a small run, at
once), and `start_job` and `job_status` (a longer run in the background). Your own project has its own tools, or
none: the steps are the same.

## 1. What you work with

- **The console** (`clank` in a terminal): a menu of pages on the left, the machine on the right. It gets a folder
  ready, shows the models, the workspaces and what runs, and holds the questions waiting for you.
- **Clank's VS Code window** (a VS Code of its own; your usual VS Code is untouched): your files on the left,
  **OpenCode** (the agent) in a terminal at the right edge. The agent's changes open there for you to accept or
  reject, and a figure opens in the annotator, to mark it up for the agent.
- **The workspace**: a container that sees only the project folder (as `/workspace`) and reaches only the model. The
  agent, its commands, the folder's software and its MCP server all run in it.
- **The models**: the main one does the work, a cloud model through your API key or a preset on your GPU. With local
  models set up, two small ones on the CPU can complete code as you type (`completion 0.5B`) and read images
  (`vision 4B`, loaded only when wanted).
- **The phone** (optional): what runs, the questions, and the figures the agent sends.

## 2. Is everything running?

Type `clank` in any terminal. The header's pills say what runs: **service**, **docker**, the **model** and the
**gateway** (how the agent reaches the model). A gray or red pill:

| Pill | What to do |
| --- | --- |
| service down | `clank serve --background` (the console starts it too) |
| docker stopped | **Docker** (4): `s` starts it, or F4 `s` |
| no model | **Add a model** (F12): a cloud model with your key, or a preset on your GPU; **Models** (8) `l` loads a preset into a slot |
| gateway down | F4 `g` gets every step done, the gateway included |

**Models** (8) shows the three slots: `main` (the agent's model), `fast` (completion) and `vision`. `l` loads, `w`
switches a slot to another preset, `u` unloads, `c` checks one.

## 3. Set up a project folder (once per folder)

1. Open a terminal in the folder (for example `C:\work\myproject`) and type `clank`. The console opens on **This
   folder** (F4). If it was already open, leave it with `q` first, so it runs Clank's newest code.
2. **A container from an older image.** A workspace made before an update of the sandbox image runs without what the
   update brings (review in VS Code, figure marking, `look_at_figure`). On **Workspaces** (F6), select the workspace,
   press `x` (it stops the container and the OpenCode sessions in it: finish them first), then `o` to open it again
   from the new image. The workspace's home is kept, so its installed software stays.
3. **Every step green.** On F4, each line of "get ready to work here" shows ✓; a ✗ shows the key that does it, and
   `g` does every step that is not done:
   - `s` starts Docker; `o` opens the workspace (it builds the sandbox image the first time, about a gigabyte, asked
     first); `l` loads a model.
   - `e` installs the folder's software into the workspace (Clank proposes the command from `pyproject.toml` or
     `requirements.txt`, for `myproject` `pip install -e '.[dev]'`; it downloads in a container of its own, so the
     agent's never reaches the internet).
   - `m` gives an MCP server to the agent: yours (F3) always, the folder's own (its `.mcp.json`, for `myproject` its
     simulator's tools) once you allow it. Its tools show beside it.
4. **How changes are made.** Under "then work", `r` shows **review** (the default: the agent asks before it changes a
   file) or **auto**. Keep review until you trust the task.
5. **The image model** (local models only). On **CPU models** (F8), Vision says **on demand** (the default: loaded when
   a figure is read, unloaded after 10 idle minutes) once its files are downloaded. `v` switches it between off, on
   demand and always; `g` downloads its files (2.7 GB) if they are missing.

## 4. Start a working session (every time)

1. In the folder's terminal, `clank`, then `c` on F4 (or `clank code` without the console). It does any step that is
   not done, then opens Clank's VS Code window on the folder.
2. The window: files on the left, OpenCode in a group of its own at the right edge (it stays there; a window that had
   it elsewhere moves it back). Its status bar shows **Clank** with the model (a click shows the questions waiting for
   you, or switches the model when none waits), **Docker**, **Review** or **Auto** (a click switches), and
   **Completion**.
3. A window that was already open before an update of Clank's extension: reload it (Ctrl+Shift+P, "Developer: Reload
   Window"). The agent's terminal survives a reload (a second one is never started).
4. `a` on F4 runs OpenCode in the console's own terminal instead, without VS Code (`/exit` brings the console back).

## 5. Working with the agent

**Asking.** Type in OpenCode's box and press Enter. What works best:

- One task per message, said precisely: which files, which parameters, where results go. Name files by their path.
- For a program with its own tools, ask the agent to call the program's own help first (for `myproject`:
  `capabilities`), so it uses the real options rather than remembered ones, and to estimate the run time
  (`estimate_run`) before anything long.
- Ask for a plan in a file before anything runs; read it; then ask for the next step. Clank's **Planner** (Plan in
  the status bar, or Tab in OpenCode) reads and writes plans and never runs anything.
- Start a new session for each step of a long piece of work (`/new` in OpenCode): a long one is compacted and loses
  detail.
- Esc in OpenCode stops what the agent is doing.

**Reviewing.** In review mode each change the agent wants to make opens with your files as a diff titled
**Review: path (+added -removed)**, the file as it is and as the agent would leave it. In the tab's title bar:

- **✓ Accept** lets the agent write it.
- **✗ Reject** asks what to tell the agent (for example "keep the old name"); it tries again with that. Escape keeps
  the change waiting.

The same change can be answered in OpenCode's terminal, on the console (**Questions**, 2, or under "waiting for you"
on F4: `y`, `n`, `v` shows the diff) or on the phone; its tab closes wherever it is answered.

**Auto mode.** When you trust a task (say, only figures change), click **Review** in the status bar (or `r` on F4):
the agent then writes without asking, and each change opens as a preview after it is made. Click again to go back.

**What review does not cover.** Commands the agent runs (a script, `ruff format`, `git`) change files without asking,
in either mode. Commit or branch before a study: git is the safety net.

## 6. A whole study, step by step

How far a random walk spreads: the mean squared displacement against the number of steps, for three step rules. A
few minutes of computing; the prompts below are examples to adapt.

### 6.1 A plan, before anything runs

> Use the myproject MCP tools for this study, and call capabilities first. I want the mean squared displacement of a
> random walk on a square lattice against the number of steps, from 10 to 1,000 steps, for three step rules: simple,
> lazy (stays put half the time), and with a drift of 0.05 to the right; 500 walkers per point. Estimate the run time
> with estimate_run for each rule, then write a short plan to studies/walk-scan/plan.md: the question, the
> parameters, the expected time. Do not run the scan yet.

The agent calls `capabilities` and `estimate_run`, then asks to write `plan.md`: it opens as
**Review: studies/walk-scan/plan.md (new file)**. Read it; **✓ Accept**, or **✗ Reject** with what to change.

### 6.2 A script that runs the scan

> The plan looks right. Write studies/walk-scan/scan.py that runs this scan with the myproject Python API and saves
> studies/walk-scan/results.json with, for each point, the rule, the number of steps, and the mean squared
> displacement with its standard error. Then run it and tell me when it is done and how long it took.

Accept `scan.py` (and any fix it makes to it). Open `results.json` to see the numbers.

### 6.3 Figures, checked by the image model

> Now write studies/walk-scan/plot.py that reads results.json and saves two figures in studies/walk-scan/figures/:
> msd_vs_steps.png (the mean squared displacement against the number of steps, both axes logarithmic) and
> msd_per_step.png (the mean squared displacement divided by the number of steps), one line per rule with error
> bars, labeled axes, a legend and a title. Run it, then check both figures with the look_at_figure tool and fix
> anything that reads badly.

Accept `plot.py`. When the agent calls `look_at_figure`, the image model describes the figure, with the figure's
geometry from Matplotlib (its axes, its curves and their values); the agent fixes what reads badly, such as an axis
that plots the wrong values.

### 6.4 Mark up a figure

1. In the Explorer, click `studies/walk-scan/figures/msd_vs_steps.png`: it opens in the annotator.
2. Pick the circle (`C`) and drag around the place where the drifting walk's curve leaves the other two: mark 1.
3. Pick the arrow (`A`) and drag from empty space to the legend: mark 2. The marks are listed under the figure.
4. In the box under the figure, say what to do, naming the marks:

   > Mark 1: add an inset that zooms on this region, with a dashed vertical line where the drift starts to dominate.
   > Mark 2: move the legend outside the plot, to the right, so it never covers data.

5. Enter sends it. The agent gets each mark in the figure's own terms (for mark 1: the range of steps it covers, with
   the curves inside it and their values), your words, and the marked-up image.
6. It changes `plot.py` (accept it), runs it and looks at the result; the annotator shows the new figure by itself
   ("The figure changed on disk"). Mark it up again as often as you like.

### 6.5 Finish the study

Commit `studies/walk-scan/` (the plan, the scripts, `results.json` and the figures) on a branch. Numbers that go into
notes come from the scripts' output, never from the model's text.

## 7. Figures and the image model

**The annotator** opens every PNG and JPEG in Clank's VS Code window ("Open With" shows the plain image).

| Tool | Key | How |
| --- | --- | --- |
| Pen | `P` | draw freely |
| Box | `B` | drag a rectangle |
| Circle | `C` | drag an ellipse |
| Arrow | `A` | drag from the tail to the tip; a tip on a curve or near the legend points at it |
| Note | `T` | click the spot (a numbered pin goes there), type in the bubble that opens, Enter keeps it |

- A note's bubble can be dragged anywhere on the figure; its pin stays on the spot. A click on the bubble edits it.
- Four colors; undo (Ctrl+Z), redo (Ctrl+Y), clear; Ctrl and the wheel zoom, **Fit** fits the figure again.
- Enter in the message box sends the marks, your words and the marked-up copy; Shift+Enter starts a new line.
- Each mark is said to the agent in the figure's own terms when Matplotlib saved the figure in the workspace (its
  axes, data ranges, curves and legend are recorded at the save); otherwise by its place in the image.

**The image model** (`vision 4B`, on the CPU) reads a marked-up figure for an agent whose model cannot see images, and
answers the agent's `look_at_figure`. It uses the CPU for the 20 or so seconds of each look: with a simulation running
on the CPU, set it **off** (F8 `v`) and ask the agent to read the figure's numbers from the data instead. **Always**
keeps it loaded (about 3 GB of memory).

## 8. Long runs

- **Minutes to an hour**: the program's MCP background job, when it has one (for `myproject`: `start_job` with an
  output folder, then `job_status`). It ends when the agent's session ends.
- **Hours**: the program's own command line, started in the background in the workspace (ask the agent to start it
  with `setsid nohup ... > run.log 2>&1 &`). It goes on after OpenCode closes, for as long as the workspace's container
  runs, saving its results as it goes; stopping the workspace, Docker or the computer stops it, and a program that
  saves in chunks resumes from them.
- Results go in a folder git ignores (`runs/`); paths the agent gives the program are the container's (`/workspace`).
- A workspace's container has half of Docker's CPUs and a quarter of its memory unless its record says otherwise
  (studies.md, "The computer stays usable").

## 9. Seeing what happens

- **Home** (1): what happens now, the workspace working.
- **Requests** (F7): the model's requests; `v` shows the text the model is writing, live.
- **Questions** (2): everything waiting for you (changes to review, questions the agent asks).
- **History** (3), **Operations** (6): what was done, and the work Clank runs (loading a model, opening a workspace).
- **Phone** (F9): `x` turns remote access on or off, `p` pairs a phone (type the code on the phone), Enter on a device
  shows everything it exchanged, `d` revokes it. The agent can send you a figure (ask it to "send me the figure").
- **Monitor** (F10): follows the newest working OpenCode session of this folder, in three views (F10 again moves
  between them). The Session view shows its context window (how full, what fills it part by part, what sits on the
  GPU, its growth), what it does now (its phase, its budgets, its speed, the loop guard), its branching flow, its tool
  calls (Enter reads one whole), the biggest items in its context (Enter shows one whole), what to watch for and the
  Guide (`.` stop, `m` a note, `k` compact, `p` pause, `u` undo the last step, again to redo it, `x` clear the result
  of the call under the flow's cursor or highlighted in Tool calls); `l` shows the live text, the model's answer as it
  is written. Enter on the context window opens the Context view: each part with its tokens and its last ten steps
  (Enter lists a part's items), what sits on the GPU, a chart of the session's growth by part, where the room went,
  what could be freed, and where the figures come from.

## 10. Code completion

With a local completion model served: gray text after the cursor in any file; Tab takes it, typing on ignores it. It
comes from `completion 0.5B` on the CPU, about a third of a second after you stop typing. **Completion** in the status
bar turns it off or on for every window; on F8, `u` stops its model and `l` serves it again.

## 11. When you are done

1. Commit the work (on a branch for a study).
2. Leave OpenCode (`/exit`, or close its tab) and the window.
3. To free the GPU for something else: **Models** (8), select `main`, `u`. To free the workspace's CPU and memory:
   **Workspaces** (F6), `x` (a long run in it stops too).

## 12. When something is wrong

| What you see | What it means, and what to do |
| --- | --- |
| "...runs an older sandbox image..." (console, VS Code or the agent) | F6, select the workspace, `x`, then `o` (§3) |
| No **Review** tab opens for a change; no annotator | the same: an older image, or a window opened before an update (reload it) |
| "An Invalid Python interpreter is selected" in VS Code | the folder's `.vscode/settings.json` names a `.venv` the folder does not have. It does not touch the agent (its Python is the container's); make the `.venv` or dismiss it |
| OpenCode not at the right edge, or two OpenCode terminals | reload the window (Ctrl+Shift+P, "Developer: Reload Window"); close an extra one |
| Odd letters in OpenCode's box after a reload | clear them before pressing Enter |
| `look_at_figure` says the vision slot is empty | F8: Vision must not be **off**; `clank gateway restart` when no request runs |
| The agent seems stuck | F7 `v` shows what the model writes now; Esc in OpenCode stops it |
| The agent says the model failed on a long prompt | ask for summaries written by a script instead of whole files |
| Docker shows "wsl distro proxy ... backend.sock" | unload the model (8, `u`), quit Docker Desktop, `wsl --shutdown`, start Docker Desktop first, then load the model again |

## 13. Keys at a glance

| Page | Key | Keys on it |
| --- | --- | --- |
| Home | 1 | |
| Questions | 2 | the options' keys, `v` the whole question |
| History | 3 | |
| Docker | 4 | `s` start or stop, `r` read again |
| Machine | 5 | |
| Operations | 6 | |
| Records | 7 | |
| Models | 8 | `l` load, `w` switch, `u` unload, `c` check |
| Presets, Providers | 9, 0 | |
| Help | F1 | every key |
| Launch options | F2 | |
| MCP servers | F3 | Enter its tools, `s` start or stop, `c` check |
| This folder | F4 | `g` everything, `a` OpenCode here, `c` VS Code, `r` review or auto, `e` software, `m` MCP, `s`, `o`, `l` |
| Machine panel | F5 | shows or hides it |
| Workspaces | F6 | `o` open, `x` stop, `e` software, `d` remove |
| Requests | F7 | `v` live view |
| CPU models | F8 | `l` serve completion, `u` stop it, `x` off or on, `v` vision mode, `g` vision files |
| Phone | F9 | `x` on or off, `p` pair, `c` cancel the code, `d` revoke |
| Monitor | F10 | F10 again the next view (Flow, Session, Context); in Session `c` `n` `f` `t` `b` `w` `g` go to a panel; Enter on Context window opens the Context view, Esc back, on a tool call reads it whole, on a biggest item shows it whole; in Context ↑↓ the parts, Enter a part's items or what could be freed (`x` there drops the result highlighted), `k` compact; `l` the live text; `.` `m` `k` `p` `u` `x` the Guide |
| Add a model | F12 | `c` cloud, `l` local |
