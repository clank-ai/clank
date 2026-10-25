# Design 0021: all LLM work in Clank

Part of Clank Code ([design 0018](0018-clank-code.md)). Started 2026-10-25 at the owner's request: "take a step back
for a moment and understand the setup of Clank up to this point and identify if there are any major issues with the
way that we are trying to set up the VS code integration for using these local LLMs to help me with my research and my
coding and running my simulations ... We need to get to the point where ANYTHING i need to do with LLMs can largely be
done with Clank, including other things like making analogues to the Artifacts that you can make."

It is the review the owner asked for (§2), and a section for each fix it found (§3-§10), in the order they would be
built (§11). The owner approved §3-§7 and §9-§11 the same day, chose the sign-in start, and leaves §8 for later. Measurements are of 2026-10-25, on this PC, by counts and timings only (never the owner's text).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | Where Clank stands | Recorded 2026-10-25 |
| 2 | What the review found | Recorded 2026-10-25 |
| 3 | The model's readout | Approved 2026-10-25 (the owner chose the panel under OpenCode, and every figure) |
| 4 | The agent panel | Approved 2026-10-25 |
| 5 | Artifacts | Approved 2026-10-25 |
| 6 | Jobs: long work for the agent | Approved 2026-10-25 |
| 7 | The engine keeps one conversation | Approved 2026-10-25 |
| 8 | Sessions that stay fast | Proposed 2026-10-25; the owner decides later ("Decide later"): OpenCode compacts near the whole window, as now |
| 9 | Seeing images | Approved 2026-10-25 |
| 10 | The faster settings | Approved 2026-10-25 |
| 11 | Order of work | Approved 2026-10-25, with the sign-in start (the owner: "Yes, both") |

## 1. Where Clank stands

Clank runs the model (frontier 262K, on KVMem in WSL), its gateway, a Docker container per folder, and OpenCode in that
container. In VS Code, OpenCode runs in a terminal on the right and the files on the left; the extension adds per-change
review, figure annotation, LaTeX checks and comments, `show_files`, gates of flows, Notion's review, completion, and the
status bar. The console (Monitor, flows, Requests) and the phone show what the model does. Since 2026-10-25 the PC can
be reached over SSH through Tailscale, and VS Code on another computer opens connected to it (design 0018 §8).

## 2. What the review found

| | Finding | Evidence | Its fix |
| --- | --- | --- | --- |
| A | **The agent lives in a terminal program Clank cannot extend.** OpenCode's TUI shows its own sidebar (MCP, LSP, a small context line) and plain text; Clank cannot add to it (its settings have no sidebar keys; its plugins can only append to the prompt, run a command or show a toast). So no images, rendered math or Markdown, artifacts, speed or context breakdown appear where the owner talks to the model, and every Clank feature goes around it (files opened on the left, notifications, the status bar). | OpenCode's configuration schema and plugin documentation, read 2026-10-25 | §3 now, §4 next |
| B | **Nothing like artifacts.** Interactive pages of results, parameter explorers, explainers, reports and slides have no place: the model can write files, but Clank neither shows them as pages nor takes the owner's comments on them back to it. | | §5 |
| C | **Long work has no home for the interactive agent.** OpenCode's shell tool stops a command at its time limit (2 minutes by default, 10 at most), so a simulation either blocks the session or runs in the background where nothing tracks it, tells the owner it ended, or keeps it from slowing the model. Flows have jobs; the agent in a session does not, and the HPC is not reached yet. | OpenCode long runs (2026-10-16 to 10-18); `tests/components/flows/test_jobs.py` covers flows only | §6 |
| D | **The model shares the PC unmanaged.** Writing speed falls from 57 to 33-43 tokens a second at long context when the CPU is busy, and by about half while the desktop redraws; simulations, the vision model and completion all run on the same CPU. | 2026-10-18 and 2026-10-25 measurements; docs/models/frontier-262k.md | §6 (jobs at low priority), §3 (shown), §10 |
| E | **The engine keeps one conversation.** KVMem is a single-slot server: any request of another session (a flow's box, a planning, a subagent, a benchmark) replaces the agent's cached prompt, and its next step reads it all again. | 3 re-reads of 21,612 to 103,906 tokens today, the largest 145 s before the first token; KVMem's `--help`: "Independent single-slot ... server", no save or restore | §7 |
| F | **Long sessions are slow, and past the exact window the model sees only what is retrieved.** At 160K tokens writing is about 25% slower than at 8K, and past 57,344 tokens older context is retrieved by likeness (5 of 6 recall probes passed). The owner's sessions reach 157,000-245,000 tokens. | 54-56 vs 72-73 tokens a second (thinking-heavy prompts, idle PC); docs/models/frontier-262k.md | §8 |
| G | **The model is told it cannot see, and its seeing tool times out.** The main model reads no images; `look_at_figure` asks the vision model on the CPU (8-44 s today), and 2 of the session's 17 calls timed out in OpenCode, after which the model told the owner no vision model was loaded. | Today's traffic: 20 vision requests, all answered; the session's tool results by Clank's own status words | §9 |
| H | **The fastest settings are not the default.** CUDA graphs on and 4 drafted tokens a step write 14% faster at 160K (65 vs 57 tokens a second) and 7% at 8K. | Two runs of three requests each, 2026-10-25 | §10 |
| I | **After a restart the PC is not ready for remote work.** Docker Desktop does not start at sign-in, and Clank's service cannot be started over SSH (Docker's sign-in). | Docker's `AutoStart: false`; getting-started §5 | The owner's choice (a sign-in start for both), §11 |

Not found to be a problem: the extension-not-fork direction (design 0018 §1), the container per folder, the gateway's
records, and remote work over SSH (tested 2026-10-25: the GPU, WSL, Docker and the service all answer an SSH login).

## 3. The model's readout

What the owner asked for on 2026-10-25 ("display the tokens per second and other important feedback regarding the
model ... like the breakdown on the context window"), as they chose it: a panel under OpenCode's terminal in the right
column, and a line in the status bar.

- **What it shows**, every figure the owner chose: *speed* (writing tokens a second while the model writes, each recent
  step's as a short graph, the last prompt's reading speed, the share of drafted tokens accepted); *the context* (used
  of the window, part by part: system prompt, tools, conversation, tool results; the exact window on the GPU and
  OpenCode's compaction line; the share read from the cache); *now* (thinking, writing, writing a call and which,
  running a tool and which, waiting for the owner, idle, and for how long); *the machine* (the preset and its key
  settings, GPU memory and use, and whether the engine holds this session's conversation or must read it again).
- **One route** composes it: `GET /agents/readout?folder=` gives the folder's workspace's newest session (or the one
  named), with its `now` (design 0012 §5), its context totals (§4), the main slot's preset and state, the GPU's
  newest meter, and the drafted tokens accepted as the engine's log last said (KVMem's `spec_stats`). The service
  composes; the extension draws, about once a second while the panel shows, and the status bar from the same answer.
- **The status bar**: the speed, the context used of the window, and the phase ("63 tok/s · 161K/262K · thinking").
- **The panel**: a webview in a group of its own under the agent's terminal, a quarter of the column's height; the
  agent's group stays at the right edge with it. Its first line says how to hide OpenCode's own sidebar (Ctrl+X, B).

When the agent panel (§4) is built, the readout moves into it, docked at its foot.

## 4. The agent panel

Clank's own view of the agent, in the right column, beside or in place of OpenCode's terminal (both stay: design 0018
§2, "both Clank's own panel (OpenCode) and VS Code's Chat"). It talks to the same OpenCode server the terminal does,
through the session bridge the phone and the Monitor already use (design 0005 §2): the same session, so the owner can
switch between the two at any moment.

- **The conversation**, rendered: Markdown, math (KaTeX), code with highlighting, the model's thinking folded, each tool
  call folded with its state, images inline (a figure the agent made or showed), artifacts (§5) as cards that open.
- **Asking and answering inline**: a permission, a question or a change waiting for review shows in the conversation
  with its buttons.
- **The input**: text, files of the folder by `@`, an image pasted (read by the vision model, §9), and commands
  (compact, a new session, the model).
- **The readout** (§3) at its foot.

It is the place every later part shows itself: artifacts, jobs, a claim's marks (design 0018 §4).

## 5. Artifacts

A page the agent makes for the owner, as Claude makes artifacts: an interactive plot of results, a parameter explorer,
an explainer, a report, slides, a diagram. Local: nothing leaves the PC.

- **Made by a tool**: `make_artifact(name, title, kind, files)` in Clank's MCP server, the agent having written the
  page's files (HTML, or Markdown with math, or SVG, with its data files). Clank keeps each version in the folder's
  `.clank/artifacts/<name>/` with `artifact.json` (title, kind, versions, what made it), and opens it.
- **Shown** in VS Code on the left (a webview with its versions, Open in browser, Comment, Send to phone), in the agent
  panel as a card, and on the phone. Pages run with no network: the libraries they may use (charts, math, diagrams)
  are served by Clank from its own copies, and a page reads only its own folder's files. A page whose data file
  changes (a job writing results, §6) is drawn again.
- **Comments back**: the owner comments on a version (a note, or a mark on a point of the page, as on a figure);
  they go to the agent as one message naming the version, as LaTeX comments do (design 0020 §11).
- **Kept as files**: an artifact is the owner's, in their folder, with every version; `clank artifact export` makes it
  one self-contained HTML file.

The libraries are a new dependency of Clank's (front-end files it serves), so they come with a decision record.

## 6. Jobs: long work for the agent

The agent starts long work as a job and goes on: `run_job(command, name)` runs it in the workspace's container,
detached, at the lowest CPU priority and on fewer cores than the machine has (so the model keeps its speed), its output
in `.clank/jobs/<id>.log`; `job_status`, `job_tail` and `job_stop` follow it. Clank keeps every job (in VS Code's
side bar, the console and the phone), says when one ends, and tells the agent's session when the owner allows it. A
job writing results can feed an artifact (§5). Flows' jobs (design 0013) are the same jobs; the HPC's (Slurm over
SSH, design 0015) come after.

## 7. The engine keeps one conversation

Until the engine can keep several (KVMem's own work), Clank keeps the main model for the session the owner works in:

- **Side work goes elsewhere**: requests that are not the owner's session (a flow's orchestrator checks, summaries,
  titles: already) go to the fast slot or a cloud model when the owner allows it, by their role in the gateway.
- **Said**: the readout (§3) shows when the engine holds another conversation, and how many tokens the next step will
  read again.
- **To find out**: whether KVMem v0.17 or later can save a conversation and restore it (seconds, against minutes of
  reading), and if not, whether to ask its authors.

## 8. Sessions that stay fast

The owner chooses how long a session may grow before Clank hands it over: OpenCode's compaction near the whole window
(as now), or a hand-over near the exact window (about 96,000 tokens: faster writing, and the model sees all of it),
the session's summary and the files it worked on carried into a fresh one. The readout shows where the session is
against both lines.

## 9. Seeing images

- The agent is told plainly that its model reads no images, and that `look_at_figure` asks Clank's vision model.
- Clank's own MCP server gets OpenCode's tool time limit set for it, so a reading that takes a minute answers.
- An image the owner pastes in the agent panel (§4) is read by the vision model, and its reading goes with the message.

## 10. The faster settings

"frontier 262K fast (trial)" (CUDA graphs on, 4 drafted tokens a step) runs the owner's work for a few days; with no
crash, it becomes frontier 262K's own settings, with a decision record and the measurement in docs/measurements/. A
crash sends the slot back to frontier 262K's settings, and is said.

## 11. Order of work

1. The readout (§3): the route, the status bar, the panel.
2. Seeing images (§9) and the faster settings' trial (§10): small.
3. Jobs (§6), since simulations run now.
4. Artifacts (§5).
5. The agent panel (§4), with the readout moved into it.
6. Side work kept off the main model, and KVMem's save and restore looked into (§7).
7. Sessions that stay fast (§8), once the owner has chosen.
8. A sign-in start for Docker and Clank's service (§2, I), if the owner wants it.
