# Design 0013: flows, the work as a program of boxes

The owner (2026-10-18), on the Monitor's first boards: "part D for the flow chart and guiding the model is VERY MUCH
what I have been having in mind, and I really, really need us to flesh this out in more detail." Their comment on
board D, in full:

> "This idea for D is actually kinda genius, one of the extra ideas is for a 'Human in the loop' type of planner, where
> each of these individual steps are big tasks for the model to complete, and at the end there are some deliverables
> and the model begins writing a prompt for the next task, then when we have verified that a task is completed the
> model moves on to the next one, and in this loop while the model is working we can add/change certain things, and in
> this look we can select individual sections of the plan to also make sure we are editing certain settings (for
> example, maybe one of these boxes is a plan, and the next one is a verifier, and then I can include a conditional
> loop where if the verifier catches something then it goes back and keeps planning, making the right changes, and if
> the plan looks good then the model moves on to the next part of the flowchart which is to begin implementing the
> plan, but likely in some very structured way. So for example we could have the model break up a plan into actionable
> items each with a deliverable, and then have it write a prompt for each of these items, and then it will begin
> working on these sequentially and then at the end the model starts a brand new session which is only dedicated to
> taking all the outputs of this last step and wrapping everything together to then continue working. This could be
> especially useful because it would enable us to select different models for different tasks, so we could just
> straight up load and unload models as we go along this flowchart. This would be a major agent orchestration
> endeavor, but if it is done right I think this could be very useful. I need you to help me plan this as well. This
> will largely be what D is doing, since we will be going in and creating these flowcharts, and the model will have
> the ability to access this flowchart and create new items if it needs to (especially when a plan is then being
> broken up into individual actionable chunks)."

A **flow** is that planner: a program of **boxes** joined by lines, kept as a readable file. Each box is a big task
with a deliverable, done by a model in a session of its own, or a decision the owner makes; the lines say what comes
next, a verifier's loop back included. It is drawn and steered in the Monitor's Flow view (boards D1-D4). Design 0012
covers the rest of the Monitor (watching and guiding one session) and design 0011 the console's look; both are
written beside this one. The Session view also draws a "flow": what one session did (board A). This design's flow is
what the owner tells a series of sessions to do. Here a **box** is always a step of a flow (the owner's own word, and
boards D1-D4's); a section of a console page is a **panel** (design 0011; on screen it is drawn as a box with its title
in its top border), and the machine area at the console's right is the **machine column** (Claude's call, 2026-10-18).

**Status:** written 2026-10-18, every section *approved* by the owner the same day ("Approve all three", the remaining
Choices as recommended). **Choice** marks what the owner decided: where a box's session runs (§5), whether a box goes
on by itself (§10) and where a flow lives (§11), each chosen by the owner, as recommended; what follows INTEGRATE (§3)
and VERIFY's model (§7), as recommended by the owner's approval. The worked example is
the boards' own, "A new simulation study" in the workspace `myproject`; boards are named by their titles on the
owner's design canvas and by their files in [docs/design/boards/](boards/README.md), their source copied there and
readable as text (their titles, panels and figures): D is [Flow.dc.html](boards/Flow.dc.html), D1
[FlowRun.dc.html](boards/FlowRun.dc.html), D2 [FlowNode.dc.html](boards/FlowNode.dc.html), D3
[FlowGate.dc.html](boards/FlowGate.dc.html) and D4 [FlowPropose.dc.html](boards/FlowPropose.dc.html). Where a board and
these words differ, the words are the rule, and the board is drawn again (Claude's call, 2026-10-18).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Approved 2026-10-18 |
| 2 | The kinds of box | Approved 2026-10-18; revised 2026-10-20 at the owner's request (each box prepared: decisions 0085-0087): a VERIFY is handed no handoff notes; revised 2026-10-20 at the owner's request (a flow built with the model, §15) |
| 3 | Lines, and loops that end | Approved 2026-10-18; revised 2026-10-20 with step 4 (how a DECOMPOSE's task is handed the deliverables before it); revised 2026-10-20 (the next flow, as built: decision 0091) |
| 4 | A box's settings | Approved 2026-10-18 |
| 5 | Running a box: a fresh session | Approved 2026-10-18; revised 2026-10-20 at the owner's request (each box prepared: decisions 0085-0087): the brief always, the map, handoff notes, the preview |
| 6 | The runner, an operation of the service | Approved 2026-10-18; revised 2026-10-20 at the owner's request (each box prepared: decisions 0085-0087): `clank flow prepare`; revised 2026-10-20 (the next flow: decision 0091): `clank flow next` |
| 7 | A model per box, and what a switch costs | Approved 2026-10-18 |
| 8 | Deliverables, tries and stale boxes | Approved 2026-10-18; revised 2026-10-20 at the owner's request (each box prepared: decisions 0085-0087): a try keeps its handoff note |
| 9 | The model proposes boxes | Approved 2026-10-18; revised 2026-10-18 at the owner's comment (`flow_verdict`'s criteria); revised 2026-10-20 with step 4 (how a DECOMPOSE's task is handed the deliverables before it); revised 2026-10-20 at the owner's request (a flow built with the model, §15) |
| 10 | Gates | Approved 2026-10-18; revised 2026-10-20 (the next flow, as built: decision 0091); revised 2026-10-20 at the owner's request (a flow built with the model, §15) |
| 11 | Where a flow lives, and its file | Approved 2026-10-18; revised 2026-10-20 (the next flow, as built: decision 0091): `next_flow`, `follows`, `next`; revised 2026-10-20 at the owner's request (a flow built with the model, §15) |
| 12 | The Flow view in the Monitor | Approved 2026-10-18; revised 2026-10-18 at the owner's comment (board D4's cards); revised 2026-10-20 at the owner's request (a flow built with the model, §15); revised after approval 2026-10-20 (the planning watched beside the console, §15) |
| 13 | What flows do not cover | Approved 2026-10-18 |
| 14 | Build steps | Approved 2026-10-18; revised 2026-10-20 at the owner's request (each box prepared: decisions 0085-0087): step 8; revised 2026-10-20 (the next flow: decision 0091): step 9; revised 2026-10-20 at the owner's request (a flow built with the model, §15): step 10 |
| 15 | A flow built with the model | Approved 2026-10-20 (the owner's three answers); Claude's calls listed in it (decisions 0097-0099); revised after approval 2026-10-20 (the owner: OpenCode beside the console, watch it built, start from the Monitor and This folder; two SSH windows): **Beside the console** (decisions 0100-0101); revised 2026-10-21: the template names no model (decision 0117) |
| 16 | The orchestrator: a model that steers the run | Approved 2026-10-22 (the owner's request: a toggle, research the best configurations, implement what is useful); Claude's calls listed in it (decisions 0123-0124) |

## 1. What the owner gets

- **A flow per piece of work**, drawn in the Monitor's Flow view. Board "D1 · The flow is the program: running (click
  a box)": the owner's brief; a plan; a check that sent the plan back once with three findings and passed its second
  try; the owner's approval (after 8 minutes); the plan broken into four tasks, which the owner accepted with one
  prompt edited; the tasks one after another; a session that puts it all together; and the owner's review of the
  whole, then the next flow.
- **Each box is its own session**, with its own prompt, the files it is handed, its deliverable and its own model:
  Clank loads the box's preset before the box starts.
- **The owner steers while it runs.** Any box can be edited (board "D2 · A box's settings (select it, then e)"). At a
  gate the owner approves, edits or sends back (board "D3 · A gate: your checkpoint"). The boxes the model proposes
  are accepted, edited or rejected (board "D4 · The model adds boxes (DECOMPOSE proposes)"). The flow can be paused or
  stopped, and a running box's session opens in the Session view to be watched and guided (design 0012).
- **The model adds boxes only as proposals**, which wait for the owner, or for a setting that accepts them within a
  cap.
- **Nothing is hidden.** Each box's whole first message, each try's deliverables, each verdict, proposal and decision
  is a file or an event that the owner can open, diff, and trace to who did it.

Board "D · The flow chart, and guiding the model" drew one session's work by its own todo list, with a Guide beside it;
that view is design 0012's. This design is what the owner's comment on it asks for.

## 2. The kinds of box

A box's type sets what it must produce, how it ends, its default mode (§4), and Clank's instructions for it: one file
per type, `clank/components/flows/prompts/<type>.md`, put at the top of the box's first message (§5).

| Box | Done by | Produces |
| --- | --- | --- |
| **YOU** (the brief) | the owner | a file, usually `BRIEF.md`: the goal and the limits (in the example, about 60 grid points and at most 48 CPU-hours). Every flow starts with one |
| **PLAN** | a model, as the planner (design 0009 §3) | a plan in design 0009 §4's format (`PLAN.md`) |
| **VERIFY** | a model, in a fresh session | a verdict on one earlier box's deliverable: *pass*, or *fail* with numbered findings |
| **DECOMPOSE** | a model | proposed TASK boxes, each with a deliverable, what to accept, and a drafted prompt (§9) |
| **TASK** | a model | its deliverable: the files it names (`grid.json`, `scripts/sweep.py`) |
| **INTEGRATE** | a model, in a fresh session | a summary of every deliverable before it (`STUDY-PLAN.md`) and the next flow's brief |
| **GATE** | the owner | a decision: approve, edit then approve, send back with a note, or stop (§10) |

- **YOU** waits like a gate: the owner writes its file (Clank's VS Code window opens it, design 0004 §5) and says it
  is done, from any client. A YOU box later in a flow is work the owner does by hand. In a flow built with the model
  (§15; revised 2026-10-20, decision 0098), the first YOU is done by itself when each of its files is in the folder:
  the brief the owner wrote with the model while building the flow; a file missing, it asks as any YOU.
- **VERIFY** is handed only the brief, the deliverable it checks and that box's *accept when* (§4), never the session
  that made it, nor the handoff notes of the boxes before it, which are that session's own account (§5; revised
  2026-10-20, decision 0086): in the example it saw `BRIEF.md` and `PLAN.md`, and the map of the flow, which names the
  boxes and carries none of their sessions. It ends by calling `flow_verdict` (§9). A session that ends without a
  verdict is a failed box, never a pass.
- **DECOMPOSE** ends by submitting its proposals (`flow_submit`, §9). The tasks accepted join the flow between it and
  the box after it.
- **TASK** is today's `/implement` made smaller (design 0009 §5): one session per task instead of one per plan, with
  checks between tasks. A flow whose one TASK's prompt is `/implement PLAN.md` is today's hand-over.
- **INTEGRATE** starts afresh, as the owner asked: "a brand new session which is only dedicated to taking all the
  outputs of this last step and wrapping everything together to then continue working".

## 3. Lines, and loops that end

Boxes are joined by lines (the boards' word for edges). A flow is a chain of boxes, with two exceptions only: a
VERIFY's fail line back, and DECOMPOSE's tasks (Claude's call, 2026-10-18).

- **Then.** A box that is done passes to the box its line leads to.
- **Pass and fail.** A VERIFY has two lines: *pass* to the box after it, and *fail* back to the box it checked,
  carrying the findings. In the example the first check failed with three (no CPU-hour budget; seeds not fixed; 240
  grid points where the brief allows about 60), PLAN wrote its second try, and the check passed.
- **DECOMPOSE's tasks, one after another.** They run in turn, as the owner asked ("it will begin working on these
  sequentially"), each handed the deliverables of those before it, so they are a chain: editing T1 makes T2 and those
  after it stale (§8). Its first message names each of them by its path, the task that wrote it and its size, as §5
  hands a file too large to give whole, to read with its tools; it is given whole only those it sees. The box after
  them waits for all of them (board D2: "joins when all 4 are done"). Board D1 draws them fanned out from DECOMPOSE and
  joined at INTEGRATE, which is how the Flow view draws them (§12).
- **Loops end.** Only a VERIFY's fail line may point back. The box it returns to runs again while it has tries (§4);
  when they are used up, the fail goes to a gate instead (board D2: "up to 3, then a gate decides"). So a flow never
  runs forever, and such a loop is the only work that runs again by itself.
- **The next flow.** After the last gate, a dashed box points to the next flow (board D1: "next flow: Run the study",
  "prompt from INTEGRATE"). As built (revised 2026-10-20, decision 0091): once a run's last box, a GATE, is approved
  and the run ends, the next flow is made from Clank's template, `<name>-<n>` in the same workspace, titled by its
  brief's first heading. Its brief is the last INTEGRATE's `NEXT.md`, else the last of its two or more files; none, no
  next flow, and an event says why. The two are linked both ways (`follows`, `next`). Nothing in the folder changes
  then: when the next flow's first run starts, the brief is copied into its YOU box's file (`BRIEF.md`), unless the
  owner changed that file since, and the owner edits it as any brief. The owner is asked whether to run it now (§10);
  the flow's `next_flow` setting may run it at once, or make none.
- **Checked when saved.** A flow that breaks these rules is refused, naming the file, line and field (design 0002
  §2.2): a line pointing back that is not a VERIFY's fail; a box with two *then* lines, or a join (a box two lines lead
  into), outside the two exceptions above (until a later design); a VERIFY checking a box that is not before it; a box
  no line reaches; a deliverable that is not Markdown in a box in Plan mode (the planner may not write it). In the Flow
  view, `c` (connect, §12) offers only what these rules allow.

**Choice: what follows INTEGRATE.** (a) The same flow goes on: the next brief feeds a new PLAN appended to this flow.
(b) A next flow: once the last gate approves, a new flow is made from a template with INTEGRATE's brief as its YOU
box, linked both ways, and it waits for the owner to start it. (c) The last gate offers both. **Recommended: (b)**, as
board D1 draws it: each flow stays finite and readable, its run ends with its deliverables, and the history of the
work is the chain of flows.

## 4. A box's settings

Board D2 shows them, each with its key; the flow's own settings give the defaults (§11).

| Setting | What it is |
| --- | --- |
| Type | §2 |
| Model | A preset, such as "daily 262K", loaded before the box starts (§7) |
| Mode | Plan, Review or Auto, the three the owner already knows (design 0009 §7): Plan is the planner; Review and Auto are `build`, its changes waiting for the owner or accepted at once (design 0007) |
| Sees | The files its first message hands it, each with where it came from ("grid.json, from T1") |
| Prompt | The box's own words: the owner's, or drafted by DECOMPOSE (§9) |
| Deliverable | The files it must write, and what they hold ("runs/estimates.md, a table: grid point, CPU-hours, method") |
| Accept when | What makes the deliverable right, in words, checked by a VERIFY or by the owner at a gate; optionally also a command the runner runs in the container after the box, which passes when it exits 0 |
| When done | Go on, or wait for the owner (§10) |
| Tries | How many times the box may run, 3 by default; then a gate decides |
| Limits | Time, and the tokens the model writes, thinking included (a prompt is mostly re-read from the engine's cache, so counting its tokens would count the same history many times) |
| Tools | OpenCode's own tools, and which of the workspace's MCP servers it gets (board D2: bash, read, edit, and the simulator's server with its 10 tools) |
| Network | None: the container reaches nothing but the gateway, through the edge (design 0004 §3); a host for a box waits for network grants (M7) |

- **The mode is the box's, for its session only.** Today the workspace's record says review or auto, and Clank
  answers every change asked in the container by it (design 0007 §3). A box's session is answered by the box's mode
  instead (Clank knows which session asks), so a TASK can run in Auto while the owner reviews their own work. A box
  that names no mode takes the workspace's. PLAN, VERIFY, DECOMPOSE and INTEGRATE are Plan by default; a VERIFY that
  must run tests needs Review or Auto, since Plan mode runs reading commands only (design 0009 §3).
- **Sees is not a wall.** The box can still read any file of the folder with its tools: the folder is its sandbox.
  *Sees* is what it is handed.
- **A change while the flow runs** (board D2: "It is running: a change here applies from its next try"): a box not
  started takes it when it starts, a running box at its next try, and a finished box is marked changed, the boxes after
  it stale (§8).
- **Tools per box** are set on the flow's OpenCode server (§5): before the box starts, an MCP server is connected or
  disconnected there (the bridge's `mcp-start` and `mcp-stop`, which act on one OpenCode server). Whether OpenCode 1.19
  takes its own tools per message is to measure; until then the mode decides them.

## 5. Running a box: a fresh session

- **A new session for each box, and for each try.** None inherits the history of the boxes before it, as the owner
  asked. It is also what works best here: the model battery ran one fresh session per task and did twelve of thirteen
  right, and found a conversation past about 60K tokens best started afresh, where KVMem's replay failed
  ([2026-10-15](../measurements/2026-10-15-model-battery.md)).
- **Its first message** is, in order (revised 2026-10-20 at the owner's request, decision 0085): the type's
  instructions; **where it sits in the flow**; **the brief**; the box's prompt; **the notes of the boxes before it**;
  the files it sees, the brief's excepted (a text file whole up to a size, a setting; a larger or binary one by its path
  and size, to read with its tools); what the boxes before it delivered (an INTEGRATE: every deliverable; a DECOMPOSE's
  task: those of the tasks before it, §3); its deliverable, *accept when* and **its own handoff note**; and, on a later
  try, what happened to the last one (VERIFY's findings, the owner's note, the limit it reached). It is kept as a file
  beside the box's tries (§8), and `v` shows it whole (board D2: "shows the whole first message: this prompt, the files
  it sees, its tools").
- **The brief, always.** The owner (2026-10-20): "make it so that each of the individual tasks are brand new sessions
  that get fresh context windows, but making sure that we are preparing each of these tasks with the correct context
  for the agent at that task to get the work done properly." The flow's brief, the file its first box (a YOU) writes,
  usually `BRIEF.md`, is handed to every box a model runs, whether or not its *sees* lists it, and once: so every task
  knows the goal and the limits.
- **Where it sits in the flow.** A short map: the boxes before it in the order they run, each on one line with what it
  delivered (its files, a verdict, the tasks it broke the work into, the owner's approval) or that it was skipped; this
  box, marked, with its try; the boxes after it, each with its title and, when it uses this box's deliverable, how (sees
  it, checks it, is told of it). It orients; it carries no history.
- **Handoff notes** (decision 0086). PLAN, TASK and INTEGRATE end by writing a few lines for the boxes after them,
  `.clank/handoff/<flow>/<box>.md` in the folder: what it did, the decisions it made, what is still open. A note written
  during the try is copied beside it as `handoff.md` (§8); a VERIFY's verdict and a DECOMPOSE's summary stand for theirs.
  Every later box but a VERIFY (§2) is handed the notes of the boxes before it, in the order they ran, each naming where
  it came from and cut at the flow's `defaults.note_up_to` characters (2,000). A missing note is marked (the try keeps
  none, its event says so, later boxes are told), never a failure: the note is not the deliverable.
- **Seen before it is sent** (decision 0087). `clank flow prepare <flow> [box]` (`GET /flows/{workspace}/{name}/prepare`)
  shows each box's first message as it would be sent now, from the files as they are now and the active run's state,
  with its size in tokens against the window of the preset it runs on: counted by the engine when the main slot runs
  that preset and its engine counts (llama.cpp's `/tokenize`), else an estimate from the model's calibration or a
  plain default, always labeled as one. `clank flow check` warns when a box's first message would be over a quarter of
  its window, and when a file a box sees is neither in the folder nor written by it or a box before it.
- **Sent with the box's agent and model.** OpenCode 1.19 gives a message that names no agent to `build` (its
  `agent.ts`, read 2026-10-18), and the bridge's `prompt` sends text parts only today (`bridge.py`); its `implement`
  already names its agent. The Monitor needs the same fix (design 0012); it and the watcher's widening below are
  built once, in design 0012's step 4 (§14).
- **Its title** names the flow, the box and the try ("A new simulation study · T2 · try 1"), so the session is known in
  OpenCode, on the phone and in the Monitor.
- **It ends** when the session goes idle. The runner hears it from the workspace's watcher (design 0007 §4), which
  must then say when a session's status changes: today it says asks, replies, edits and each message's agent
  (`bridge.py`); the Monitor needs the same widening. Should the watcher not say it, the runner reads the session's
  status itself every minute (revised 2026-10-22, decision 0128: OpenCode keeps a stream open after its instance ended
  but sends nothing more on it, and one opened as it starts says nothing at all; the first long run waited out its
  limits). The watcher opens a stream again when it does not say it is connected, and after two minutes of silence. The box is **done** when every deliverable was
  written during this try (and VERIFY gave its verdict, DECOMPOSE submitted). Otherwise it **failed**, and the run says
  why: a deliverable missing; a limit reached (the runner stops the session, design 0005 §2); the loop guard or the
  engine cutting an answer (OpenCode then leaves the run idle and the cut answer out of its context, design 0004 §2);
  or the owner's stop. A failed box waits at a gate (§10).
- **While it runs,** its questions and the changes it asks to make reach the owner as any session's do (designs 0005
  and 0007), and the Flow view says the flow waits for them.

**Choice: where a box's session runs.** (a) On the flow's own OpenCode server without a terminal (`opencode serve`,
which the bridge starts and the one-window rule leaves alone: designs 0005 §2 and 0004 §5), watched in the Monitor and
listed on the phone with the other sessions. (b) In the workspace's OpenCode window, as `/agents/implement` does
(design 0009 §8), seen in VS Code. **Decided by the owner (2026-10-18): (a)**, as recommended. A box never takes
over the window the owner works in, and
the runner can start that server with the box's limits and tools: changing OpenCode's configuration while it runs
restarts its instance and closes every event stream (design 0007 §2), so a box whose preset has other limits gets the
server started again for them. That restart ends what its MCP servers run in the background (design 0004 §10), so it
happens only when the limits differ, and the run log says so. To measure: how two OpenCode servers in one container
keep configurations of their own, and whether the window can show a session the other server runs.

## 6. The runner, an operation of the service

- **The flows component** (`clank/components/flows/`, in the shape of every component) runs flows in the service, so
  closing a client stops nothing and every client shows the same state, through the service's `/flows/` routes.
- **A run** records the flow's state: the version of the flow it started from, each box's state (waiting, running,
  done, failed, stale) and tries, where the run is, its deliverables' fingerprints, and what waits for the owner. It
  is a readable JSON file in the run's folder (§8), beside everything the run made, as Notion's batches are (design
  0010 §5).
- **Each box's work is an operation** (design 0002 §2.4), `flows.box`, with the steps *model* (switch the slot when
  needed, §7), *server* (the flow's OpenCode server with the box's limits and tools), *session* (start it with its
  first message), *work* (follow it to its end) and *collect* (check and copy the deliverables). Every step but
  *session* is safe to run again. The Operations page shows each one ("4 of 5: work").
- **Gates, YOU boxes and proposals are questions** that the component asks outside any operation, so they survive a
  restart of the service (design 0002 §2.5).
- **One flow runs at a time.** Every box uses the main slot, and KVMem holds one conversation at a time (its source,
  read 2026-10-18): two flows would evict each other and switch models back and forth. A second flow started waits,
  and the Flow view says behind which. Flows side by side wait for a second provider.
- **The owner's controls:** pause (no box starts; the running one goes on); stop (the running box's session is
  stopped, and the box counts a failed try); run from here (the chosen box and every box after it run again, as new
  tries).
- **After a restart of the service**, the box's operation is *interrupted*, then reconciled: its session runs in the
  container, so the runner reads it through the bridge, follows it if it still works and collects it if it ended;
  neither repeats any work. A session that is gone (the container stopped) makes the box failed. No session is ever
  started again on its own.
- **Events**, each with its actor (the owner through a client, auto-accept, the runner): `flows.run_started`,
  `flows.box_started`, `flows.box_ended` (done, failed, stopped), `flows.verdict`, `flows.proposed`,
  `flows.proposal_decided`, `flows.stale` and `flows.run_ended`; a gate's answer is its question's own event. The run
  log of board D1 is these events. No event holds the text of a prompt or a deliverable.
- **Commands**, for scripts and as the view's backup: `clank flow list|show|check|run|pause|stop`, `clank flow
  proposals|accept|reject`, `clank flow prepare` (each box's first message and its size, §5; revised 2026-10-20), and
  `clank flow next` (the next flow: shown, made, or run, §3; revised 2026-10-20).

## 7. A model per box, and what a switch costs

The owner: "it would enable us to select different models for different tasks, so we could just straight up load and
unload models as we go along this flowchart."

- **A box's model is a preset.** Before the box starts, when the main slot does not run it, the runner starts the
  runtime's switch (`runtime.switch`: plan, stop, start, health, measure; design 0003 §6.1) and waits for it. It
  starts the switch only while the gateway's activity shows no request in flight on the slot (design 0004 §2), which
  is the *wait* of design 0001 §4.2's busy check. A switch that fails returns the slot to the last configuration that
  worked, as every switch does, and the box fails with the engine's reason.
- **Every request of the box** reaches the main slot through the gateway as the role `agent`, as today. A box on
  another slot (a small model on the CPU in `fast`) would need OpenCode's configuration to name that role as a second
  model: later.
- **What a switch costs.** KVMem's `daily 262K` was ready 19-25 s after loading
  ([2026-10-13](../measurements/2026-10-13-ninfer-and-kvmem.md)). The whole switch is recorded with its duration
  (design 0001 §4.2), and the Flow view shows the last one recorded for each preset (board D2: "another preset loads
  before this box starts").
- **What a fresh session costs**, with or without a switch. Its first prompt is read without the cache: KVMem took
  13 s to the first token for a prompt of about 8K tokens, and 41 s for about 31K (2026-10-13). Its later steps come
  mostly from the cache (86-97%, the first token in 2-4 s; 2026-10-15). To measure: the size of a box's first prompt
  (OpenCode's own instructions and tool definitions with the box's message), and whether the opening two sessions
  share (those instructions) is read from the cache (KVMem resets its store for a request that shares no checkpoint
  with the conversation it holds).
- **The desktop.** Reading a prompt caused hiccups of up to 0.5-0.7 s on KVMem (design 0004 §6), and a flow of many
  short boxes reads many prompts afresh, so the Flow view shows a flow's switches and fresh starts before it runs.
- **The owner's own sessions** on the same slot interleave with a running box, and each evicts the other's
  conversation from the engine, so both read their prompts again (the cost to measure). The Flow view says so when it
  happens.
- **The owner's OpenCode window** (Claude's call, 2026-10-18). The runner never switches the slot's preset while the
  owner's own OpenCode session in that workspace is working (the watcher reports its status, §5): it waits, and the
  Flow view says "waiting for your session to be idle to load <preset>". After a switch, the owner's window is told its
  model changed, on This folder and in VS Code, and its configuration is refreshed when it next starts (the one-window
  rule, design 0004 §5). A preset whose context is smaller than what the owner's session already holds is named in
  that message as too small for it.
- **Models in this flow** (a panel of board D1) lists each preset the flow uses, whether it is loaded, and how many
  boxes use it.

**Choice: VERIFY's model.** (a) The checked box's preset, in a fresh session: no switch, and its independence comes
from being handed only the brief and the deliverable. (b) Another preset by default, for a second model's view: up to
two switches a try, so up to six for three tries. (c) A small model on the CPU, as the vision model is (design 0008):
no GPU switch, its quality to measure. **Recommended: (a)** by default, any VERIFY free to name another preset, with
the switches' cost shown before the flow is saved.

## 8. Deliverables, tries and stale boxes

- **A deliverable is files in the folder**, written where the box was told. When a box ends, the runner copies each
  one into the run's folder, `CLANK_HOME/state/flows/<workspace>/<flow>/run-<n>/<box>/try-<k>/`, with its fingerprint
  and size, beside the box's first message, its handoff note (`handoff.md`, when it wrote one during the try, §5;
  revised 2026-10-20) and, for a VERIFY, its verdict (`verdict.md`). A file above a size (a setting) is kept by its
  fingerprint only.
- **The owner opens and diffs them.** `o` opens a deliverable in Clank's VS Code window; `d` diffs two tries there
  (VS Code's diff) and on the console (board D3: the plan's try 2 with try 1's lines struck out, "changed since try 1:
  7 lines").
- **A deliverable counts only when written during its try.** A file left by an earlier try or by another box does not,
  so a box that wrote nothing fails.
- **Stale.** A finished box is *changed* when its settings are edited, or when its deliverable in the folder no longer
  matches its fingerprint (the owner edited it, or a later box rewrote it). Every box after it along the lines
  (DECOMPOSE's tasks in their order, §3) that has run is then *stale*, and the Flow view says why. Board D2: "Changing
  a finished box marks every box after it stale; nothing reruns on its own." The owner runs again from a box (`r`) or
  keeps what is there.
- **Progress is not a change** (Claude's call, 2026-10-18). The run's own TASK boxes tick the plan's steps and add to
  its Log as they work, as `/implement` does (design 0009 §5.1); that must not make PLAN changed and every box after it
  stale. So the runner compares the plan's progress apart from the rest of the file: its progress is each step's tick
  in the checklist, the Log's lines and the header's `status`; the rest includes the steps' own words. A change to the
  progress made between the start and the end of one of the run's TASK boxes is that box's progress, not a change; any
  other change to a file a later box saw counts.
- **An edit at a gate is the owner's.** The deliverable's fingerprint after the edit is the one approved, and the boxes
  after the gate have not run yet, so nothing is stale.

## 9. The model proposes boxes

The owner: "the model will have the ability to access this flowchart and create new items if it needs to (especially
when a plan is then being broken up into individual actionable chunks)."

- **Its tools**, in Clank's own MCP server (`clank`, design 0005 §3), answered by the service through the gateway's
  `/flows/` routes, as the Notion tools are (design 0010 §3):
  - `flow_read()`: the flow, its boxes, their states and deliverables (marked read-only);
  - `flow_propose_box(after, type, title, prompt, deliverable, accept_when?, model?, mode?, sees?, why?, flow?)`: one
    box, proposed after a box of the flow (board D4 shows DECOMPOSE's four calls);
  - `flow_submit(summary)`: the proposals are ready for the owner;
  - `flow_verdict(result, findings, criteria?)`: a VERIFY's verdict (§2); `criteria` lists each line of the brief's
    limits and of what done means that the check touched, met or not, with its evidence (Claude's call, 2026-10-18,
    for **The brief, checked**, §12). A line no verdict names stays "not checked yet".
  - `flow_draft(flow)` (added 2026-10-20, §15): a whole flow drafted in a planning session, checked and written by
    Clank, or refused with what to fix; given to the planning open in the workspace, never to a box.
- **Only proposals.** The gateway forwards reading, proposing and the verdict, and refuses anything else under
  `/flows/` (403); the service refuses an acceptance that comes from the agent; the flow's file is out of the
  container's reach (§11). The rule is enforced where it can be stopped
  ([decision 0020](../decisions/0020-enforce-where-it-can-be-stopped.md)).
- **Any box may propose**, DECOMPOSE above all. The MCP server knows its workspace but not its session (design 0010
  §7), so the service gives a proposal to the box running in that workspace (one box at a time, §6). With no box
  running, the proposal names its flow (`flow`) and comes from the workspace's agent; it waits all the same.
- **Checked when staged**, each refusal with its reason so the model can fix it: the type exists; `after` names a box
  of the flow; the preset exists; the deliverable lies in the folder and is no file that agents load as settings or
  instructions (`plans.SETTINGS`, `plans.INSTRUCTIONS`); the prompt is not empty; the flow still keeps §3's rules.
- **Staged, then decided.** Proposals gather in a batch (a JSON file in the run's folder) and show dashed in the flow,
  "proposed: not in the flow until you accept it" (board D4). `flow_submit` asks the owner, who **accepts**, **edits**
  (the prompt or any setting) then accepts, or **rejects** each one, or accepts all (`A`). The phone may accept or
  reject them all. The tasks run one at a time, in the order shown, each handed the deliverables of those before it
  (named in its first message, §3).
- **Auto-accept**, a setting of the flow, off by default (board D4: "auto-accept is off for this flow"): proposals that
  pass the checks join at once, marked as accepted by the setting, up to a cap per run (10 proposed); beyond it they
  wait for the owner. The owner may remove any box that has not started.
- **Accepted boxes join the flow's file** (Claude's call, 2026-10-18), as the owner asked ("the model will have the
  ability to access this flowchart and create new items"), each marked with the run and the box that proposed it (a
  DECOMPOSE, above all); the batch file in the run's folder keeps the history of what was proposed and decided.
  Auto-accept writes the flow's file through the service like any change of a setting, so an edit the owner makes at
  the same moment is refused with both versions shown (design 0002 §2.2).
- **A DECOMPOSE that runs again** (Claude's call, 2026-10-18) proposes anew: its new proposals replace the tasks it
  added that have not started; those that ran stay, marked stale when their inputs changed (§8), for the owner to keep
  or remove. A second run of the flow starts from the file as it is then.
- **The planner may use these tools**, since they write nothing in the folder: its rules (design 0009 §3) gain them,
  so PLAN, VERIFY, DECOMPOSE and INTEGRATE can all run in Plan mode.

## 10. Gates

- **A gate is a question** (design 0002 §2.5), answered once, from any client: the console (board D3, and the
  Questions page), VS Code (a notification with its answers, as other questions are, design 0007 §6), and the phone
  (what waits, design 0005 §4). Push alerts wait for Web Push (design 0005 §6); until then the phone shows a gate when
  its page is open.
- **What it shows** (board D3): where the flow is; the deliverable before it, with `d` to diff it with the last try;
  the VERIFY's report (each finding of the failed try and how the next try answered it, and the brief's limits beside
  the plan's figures); and the decision.
- **Its answers:** *approve and go on*; *edit, then approve* (the file opens in Clank's VS Code window, and the owner
  approves once it is saved); *send back with a note* (the box whose deliverable the gate shows runs its next try with
  the note, and the boxes after it run again: board D3, "PLAN writes try 3 of 3 with your note; VERIFY checks it
  again"; at its last try the gate says so); and *stop the flow*. The last gate also offers the next flow (§3): as
  built (revised 2026-10-20, decision 0091), once it is approved and the next flow made, a question of its own asks
  whether to run it now (*run it now*, *later*), from any client, or `clank flow next NAME --run`.
- **A gate waits** until it is answered (board D3: "nothing runs until you choose"). It never expires.
- **A gate the runner asks on its own**, when a loop's tries are used up or a box failed (§3, §5), offers three more
  answers: *one more try* (past the cap, by the owner's choice), *take it as it is*, and *skip the box*.
- **Waiting for you** (a panel of board D1) lists everything the flow waits for: its gates, its proposals, and its
  sessions' own questions and changes to review.

**Choice: whether a box goes on by itself.** (a) A finished box passes to the next unless a gate follows it or its
*when done* says wait, so the flow runs unattended between gates. (b) Every box waits for the owner's OK until the
owner switches the flow to (a). (c) As (a), but the first run of a new flow waits after every box. **Decided by the
owner (2026-10-18): (a)**, as recommended, with a flow setting "wait after every box", off by default, for a run the
owner wants to step through. Board
D2's *when done* ("go on to T3 (or: wait at a gate)") and the gates the example places (after the plan's check, after
INTEGRATE) have this shape, and a long flow can run while the owner is away. Whichever is chosen, a loop at its cap, a
failed box, the model's proposals (unless auto-accept is on) and the sessions' own asks always wait.

**A flow built with the model** (revised 2026-10-20 at the owner's request, §15, decision 0098): "during the run it
stops only at the end". Option (c) above, "the first run of a new flow waits after every box", was not chosen, and a
built flow says so in its own file: Clank writes it with `wait_after_every_box` off and `auto_accept` on, and the
model's draft may place no gate but the last, no box whose *when done* waits and no box in review (a box that changes
files runs in auto). So a built flow runs from its brief to its final review on its own, its first run included: every
task its DECOMPOSE proposes joins, with no cap, and its changes are made at once; a VERIFY sends work back within its
tries (§3); and it waits only at its last gate, a box out of tries or failed, and the sessions' own questions. The owner may still add a gate or set any box to wait
before running it (board D2).

## 11. Where a flow lives, and its file

A flow is a settings record (design 0002 §2.2): a readable JSON file that names its schema, is checked when read, is
read again when it changes on disk, and is written back in one fixed format so diffs stay small; an edit made on a
version that has since changed on disk is refused, with both versions shown. In short (the whole file also holds each
box's prompt, *accept when*, limits and tools):

```json
{
  "schema": "flow/1",
  "title": "A new simulation study",
  "workspace": "myproject",
  "defaults": {"model": "daily 262K", "tries": 3, "limits": {"minutes": 30, "tokens": 200000}},
  "auto_accept": false,
  "boxes": [
    {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
    {"id": "plan", "type": "plan", "title": "Write the study plan", "sees": ["BRIEF.md"], "writes": ["PLAN.md"]},
    {"id": "check", "type": "verify", "title": "Check the plan", "checks": "plan", "sees": ["BRIEF.md", "PLAN.md"]},
    {"id": "approve", "type": "gate", "title": "You approve the plan", "shows": ["PLAN.md"]},
    {"id": "split", "type": "decompose", "title": "Break it into tasks", "sees": ["BRIEF.md", "PLAN.md"]},
    {"id": "join", "type": "integrate", "title": "Put it together", "writes": ["STUDY-PLAN.md", "NEXT.md"]},
    {"id": "review", "type": "gate", "title": "You review the whole"}
  ],
  "lines": [
    {"from": "brief", "to": "plan"}, {"from": "plan", "to": "check"},
    {"from": "check", "to": "approve", "when": "pass"}, {"from": "check", "to": "plan", "when": "fail"},
    {"from": "approve", "to": "split"}, {"from": "split", "to": "join"}, {"from": "join", "to": "review"}
  ]
}
```

Clank ships this shape as a template in `clank/defaults/`, as it ships its other settings. A flow also says what
follows it (revised 2026-10-20, decision 0091): `next_flow` (`ask`, the default; `run`; `off`), and, once made, the
links both ways: `next` (the flow made from its INTEGRATE's brief) and `follows` (the flow, run and INTEGRATE it came
from, and its brief's file). A flow built with the model (§15; revised 2026-10-20) says so in `built`: the planning
session it was drafted in, when, and its brief's file.

**Choice: where the file lives.** (a) In the workspace's folder (`flows/<name>.json`): it travels with the project
and its git history, and the model reads it as a file. But the agent's commands can change it without asking (design
0007 §8), so the rule that the model only proposes could be checked afterwards, by a fingerprint as a folder's MCP
servers are (design 0004 §10), and not enforced. (b) In Clank's home, `CLANK_HOME/config/flows/<workspace>/<name>.json`,
its runs under `CLANK_HOME/state/flows/`: no sandbox sees it (Clank's floor), the model reads it through `flow_read`,
and `clank flow export` puts a copy in the folder when the owner wants one there. **Decided by the owner
(2026-10-18): (b)**, as recommended: the rule is
enforced where it can be stopped (decision 0020), and Clank's settings already live there.

## 12. The Flow view in the Monitor

The Monitor (design 0012: a page of the menu, F10, with the views Flow, Session and Context) shows a flow in its Flow
view. It takes design 0011's look; each part below is a panel, its title set in its top border.

- **Board D1, running.** The header names the model and what the flow does ("flow running: T2"); under the views'
  tabs come the flow's name, its workspace and its start. **Flow** draws the boxes and their lines. Each box shows its
  type (YOU and GATE in the attention color, PLAN blue, VERIFY violet, DECOMPOSE cyan, TASK teal, INTEGRATE in the
  text color: the style's `boxes` group, design 0011 §2), its title, its model, its deliverable or last result, and its
  state: ✓ done, ● running (a heavier
  border in the "now" color), ○ waiting (dashed), ✗ failed, proposed (dashed, cyan), stale. Lines are green for pass,
  red for fail ("fail ⟲ back with 3 findings · 1 of 3 tries used"), the "now" color for the path being run, and dashed
  for what has not run. **Selected** shows the chosen box's settings and state, its tries and a verdict's findings,
  and for a running box a **Live** panel inside it: its step, its speed, its context bar, the loop guard. Beside them
  are **Models in this flow** and **Waiting for you**. Under the flow (revised 2026-10-18 at the owner's comment: the
  run log there "seems out of place"): **The brief, checked**, each line of the brief's limits and of what done
  means, with the newest verdict on it and its evidence ("at most 48 CPU-hours: 41.5, by T2's dry runs"), "not
  checked yet" while no verdict names it, and how many are met; **Deliverables**, every file the flow has written,
  with the box and try that wrote it and whether its check passed, `Enter` opening it; and **Ahead**, the boxes still
  to run, each with what it will cost (a switch, a fresh prompt) or that it will ask the owner. The **Run log** opens
  whole in a window on `h`.
- **Board D2, a box's settings** (`e`): the flow as a list on the left, the tasks indented under DECOMPOSE; the box's
  settings on the right, each with its key (`t` type, `m` model, `o` mode, `i` sees, `p` prompt, `d` deliverable, `a`
  accept when, `n` when done, `r` tries, `l` limits, `u` tools, `w` network); `v` the whole first message; a change
  marked as not saved until `s`.
- **Board D3, a gate** (`Enter` on a gate): §10.
- **Board D4, proposals** (`Enter` on DECOMPOSE while its proposals wait): the flow so far with the proposals dashed;
  the proposals as **cards side by side, in the order they will run**, each titled with its place and its code
  ("1 · TASK T1"), its state in its border (to decide: dashed in the proposals' color; accepted: solid in the good
  color; rejected: dim and struck), its model (and the switch it needs, if any), what it sees, its deliverable and what
  to accept, and its own `a` accept, `e` edit and `r` reject; the highlighted card's whole drafted prompt below the
  cards, where `e` edits it; the arrows move between cards; `A` accepts all; **How it proposed them** lists the model's
  calls; the tasks run one at a time, as the cards' order says (revised 2026-10-18 at the owner's comment on the
  interactive prototype: "We need a better way of displaying the different tasks, since a simple list like this is
  difficult to deal with").
- **Moving.** The arrows move between boxes, the chosen one in the selection color. `Enter` opens what a box holds: for
  a running box, its session in the **Session view** (design 0012), pinned to that session and naming the box, with
  `Esc` back to the same box; for a finished box, its deliverable; for a gate or proposals, D3 or D4. D1's other keys:
  `e` edit, `a` add a box, `c` connect two boxes, `r` run from here, `p` pause the flow, `?` explain (why a box is
  stale, failed or waiting). Revised 2026-10-20 at the owner's request (§15): `n` builds a new flow with the model,
  where the owner is (in VS Code when the console runs in VS Code's terminal, else in this terminal), `N` in Clank's
  VS Code window; `r` on a flow that has not run yet starts it at its first box, asked first.
- **One fix to board D1:** its Live panel also shows `p` as the session's pause. In this view `p` pauses the flow; the
  session's own guiding (stop, pause after this step, a note) is the Session view's, one `Enter` away. A note sent
  there goes into the run log as the owner's note to that box.
- **Room.** Board D1 is drawn wide. Narrower, the side panels move under the flow; below about 70 columns the flow
  becomes the list on board D2's left. In a terminal 160 columns wide the Monitor has about 88 columns beside the
  machine column and about 128 without it (research of 2026-10-18).
- **Drawing** uses design 0012's renderer (lines of styled text from a pure function), so a flow is drawn as a
  session is. Nothing redraws while nothing changes, and a running box redraws only its changed rows, at most four
  times a second (design 0001 §5.7): the owner's PC must not stutter (design 0004).

## 13. What flows do not cover

- **Tasks at once.** Board D4 offers "at once"; on one engine the tasks would wait for each other in the gateway and
  evict each other's conversation. Tasks run one at a time, and "at once" waits for a second provider.
- **Undoing a box.** Its deliverables are kept, but the files it changed are not put back: a box's changes are the
  folder's, as any session's are (git, or design 0012's undo of a step).
- **Files beyond the deliverables.** A box may change other files. The watcher sees what its file tools write (design
  0007 §4), not what its commands write (design 0007 §8).
- **Long runs** belong to the folder's command line, in the background, which outlives the session (design 0004 §10);
  an MCP server's jobs end with the OpenCode server that started it.
- **Later:** flows across workspaces, flows started at a set time, and flows shared as library items (design 0002
  §2.11).

## 14. Build steps

**Build order** (Claude's call, 2026-10-18). Design 0011's R1 (the style) and R2 (the panel and the shell) come first,
because the Monitor and the Flow view are built of its panels; then design 0012's steps; then these. Step 6 needs
design 0012's page and renderer. The bridge changes both designs need, `prompt` sending the agent and the model, and
the watcher reporting a session's status (§5, §7), are built once, in design 0012's step 4; steps 2 and 5 here use
them. **Decided by the owner (2026-10-18):** after R1 and R2, design 0012's steps, then this design's.

Each step starts with failing tests (design 0001 §8.6). Tests use synthetic folders, the fake OpenCode and the scripted
model of `tests/fakes` only, and open no window. Every route, kind and event type is declared in the registry, and the
generated documents are regenerated in the same commit.

1. **The flow file.** The kinds `Flow`, `Box` and `Line`
   ([decision 0015](../decisions/0015-kinds-defined-once-in-pydantic.md)), their schema, the template, `clank flow
   list|show|check`, and the glossary's new words (flow, a flow's box, gate, deliverable, stale; its entry for flow
   tells it apart from a session's flow, in design 0012). Tests prove: board D1's flow loads and is written back
   unchanged; each rule of §3 refuses its flow, naming the file, line and field; an unknown preset is refused, naming
   those that exist; a deliverable outside the folder is refused.
2. **The runner, one box after another, with gates.** The flows component; runs and their folders; `flows.box` and
   its five steps; the flow's OpenCode server; each first message sent with its box's agent and model; YOU boxes and
   gates as questions; pause, stop and run from here; stale marks; `clank flow run|pause|stop`. Tests prove: a flow of
   YOU, PLAN, GATE and TASK runs in order, one new session per box, each first message naming the box's agent and
   kept as a file; a gate waits, and its answer through the API, as the phone sends it, lets the flow go on; *send
   back* puts the note in the box's next first message; a box that ends without its deliverable, or with one left from
   before, fails and waits at a gate; a box over its time limit has its session stopped; a box in Auto has its changes
   accepted while the workspace stays in Review; an edit to a finished box marks the boxes after it stale and starts
   nothing; a TASK box that ticks its step in PLAN.md, adds its Log line and sets the plan's `status` marks nothing
   stale, while a change to the plan's other lines, or a tick made between boxes, does; a restart in the middle of a box
   marks its operation interrupted, follows the session still working and starts none; a gate asked before a restart
   still waits after it; each step is an event with its actor.
3. **VERIFY and its loop.** `flow_verdict` through the gateway's `/flows/` routes; the fail line back with the
   findings; tries, and the gate at the cap; each try's copies and their diff; *accept when* as a command. Tests
   prove: a fail hands the checked box's next try the findings; the third fail goes to a gate, never to a fourth try;
   a pass goes on; a VERIFY that ends without a verdict fails; the gateway refuses anything else under `/flows/` (403).
4. **DECOMPOSE's proposals.** `flow_read`, `flow_propose_box` and `flow_submit`; the checks; the batch; accept, edit,
   reject and accept all (from the command line first); auto-accept and its cap; the planner's rules. Tests prove: a
   proposal outside the folder is refused with its reason; the agent cannot accept; accept all puts T1-T4 in order
   between DECOMPOSE and INTEGRATE in the flow's file, each marked with its run and DECOMPOSE; a rejected proposal
   never runs; an edited prompt is the one sent; auto-accept stops at its cap and the rest wait; an owner's edit made
   on the version auto-accept has just replaced is refused with both versions shown; a DECOMPOSE run again replaces
   only its tasks that have not started; a proposal from one workspace's server reaches only that workspace's flow;
   INTEGRATE's first message names every deliverable.
5. **A model per box.** The *model* step; the server started with the box's limits; the tools per box. Tests, with
   fake engines, prove: a flow alternating two presets switches exactly before the boxes that need it; no switch
   starts while a request is in flight on the slot, or while the owner's own session in that workspace is working,
   and the run says what it waits for; after a switch, the owner's window is told on This folder and in VS Code, a
   preset with a smaller context than that session holds is named, and the window's configuration changes only when
   it next starts; a failed switch returns the slot and leaves the box failed at a gate; the server is started with
   the box's context and output limits, and again only when they differ.
6. **The Flow view.** Boards D1-D4 in the Monitor, once design 0012's page exists. Tests prove: snapshots of D1's
   moment at 128 and 88 columns and below 70; D2's fields and its unsaved mark; D3's answers; D4's decisions; `Enter`
   on a running box opens the Session view on its session, and `Esc` comes back to the box; nothing redraws while
   nothing changes, and a running box redraws at most four times a second. **The layout's edge cases** (the owner's
   comment on the prototype, 2026-10-18): over generated flows of 1 to 12 tasks, with and without proposals waiting, a
   fail loop, an added box and the next flow, with titles longer than a box, at 128 and 88 columns and below 70, no
   box, line label or legend overlaps another or leaves its panel's drawing area; a flow taller than its panel scrolls
   rather than packing its boxes together.
7. **Gates in VS Code and on the phone.** Tests prove (the extension's suite, and the phone page's routes): a gate
   shows in VS Code with its answers, *edit* opens the deliverable and *diff* the two tries in VS Code's diff; the
   phone lists a gate and a batch of proposals and answers them; an answer from one client closes the question on the
   others.

8. **Each box prepared** (added 2026-10-20 at the owner's request; decisions 0085-0087). The brief in every first
   message, once; the map of the flow; handoff notes written, kept beside the try and handed on; `clank flow prepare`
   and its route; the check's warnings. Tests prove: a box whose *sees* omits the brief is handed it, and one that lists
   it is handed it once; the map lists the boxes before it with what each delivered, marks the box, and names the boxes
   after it that use its deliverable; a TASK's first message names its note's file, and a note written during its try
   is copied beside it while one left from before is not; a missing note leaves the box done and is said; a later box
   is handed the notes before it in order, cut at the setting, a VERIFY none; the preview is the message the runner
   sends, with its size counted by the engine when it can, else an estimate labeled as one, against the box's window;
   the check warns past a quarter of the window and on a file nothing gives a box.

9. **The next flow** (added 2026-10-20: decision 0058 was not built; decision 0091). Tests prove: approving the last
   gate makes the next flow from Clank's template with INTEGRATE's brief, linked both ways, and asks whether to run it
   now, starting nothing; a run stopped, or one whose last box is no gate, makes none, nor an INTEGRATE that wrote no
   brief; *run it now* starts it, *later* leaves it for `clank flow run`; a flow set to `run` starts it unasked, one
   set to `off` makes none; its first run copies the brief into its YOU box's file unless the owner changed that file
   since; `clank flow next` shows, makes or runs it.

10. **A flow built with the model** (added 2026-10-20 at the owner's request, §15; decisions 0097-0099). Tests prove:
    `n` and `clank flow new` open a planning whose first message names the workspace, the flow, the presets with their
    windows, the owner's three answers and Clank's template without its plan's gate; the planning session is started on
    the workspace's OpenCode window, sent to the planner and shown there, once that window's server answers (here: the
    window `agents/prepare` starts in this terminal; in VS Code: the window running, else the one VS Code's extension
    starts); `flow_draft` reaches the service only through the gateway's exact allowlist, and only while a planning is
    open in its workspace; a draft that breaks §3's rules or a built flow's own (its brief first and in the folder, one
    gate and last, no other YOU, no box that waits) is refused naming each field, with the check's warnings; a draft
    that keeps them is written as the flow's file with auto-accept on, no wait after any box, the template's model and
    its `built` mark, and the owner is told "flow built: look, then r to run" as the next flow's question is; a
    built flow's YOU box is done by itself when its brief is in the folder, and a built flow runs from its brief to its
    last gate asking nothing else, its DECOMPOSE's tasks accepted on their own; the Flow view follows a flow built and
    not run yet, says so in Waiting for you with the warnings whole, and `r` starts it; frames at 128 and 88 columns and
    below 70. Revised after approval (2026-10-20, Beside the console): `n` and This folder's `f` open a planning and
    show it, the console's terminal never handed over; over SSH the Flow view says to run `clank flow attach` in
    another terminal, in Windows Terminal a pane is split for it (its command checked, no `wt` run in a test), in VS
    Code's terminal Clank's VS Code window; `clank flow attach` starts the waiting planning's session on its window,
    shows a talking one there, closes another window first under the one-window rule and says so, and with none open
    says how to open one; the Flow view shows the open planning (its steps, the latest draft marked DRAFT even when
    refused, its session live) and Enter opens its session; frames at 128, 88 and 60 columns.

Before step 5, with the owner's go-ahead and on synthetic folders: measure a box's first prompt (its size and time to
the first token), a whole switch for each preset, and two OpenCode servers in one container, each with its own
configuration.

## 15. A flow built with the model

The owner (2026-10-20): "for starting the flow I need the ability to use the LLM to build the flow at the beginning,
and then I want to let the flow go from there". Asked how, they answered:

1. **Describe it by talking it through.** `n` in the Flow view, or `clank flow new [name]`, opens a planning session
   in the workspace's OpenCode, in the terminal or in VS Code. The model reads the folder, asks the owner questions,
   then writes the brief and the flow. Clank checks the flow and shows it on F10.
2. **Once built, the owner looks, then runs.** The built flow appears in the Flow view with its boxes, models and the
   check's warnings; one key (`r`) starts it; the owner can change any box first (board D2).
3. **During the run it stops only at the end.** Task boxes the model proposes are accepted on their own, VERIFY sends
   work back on its own up to its cap, and it waits for the owner only at the final review (INTEGRATE's gate) or when
   a box runs out of tries. So a built flow has no "approve the plan" gate and does not wait after every box, its
   first run included (§10, revised).

**Status:** approved 2026-10-20 (the owner's three answers); how it is built is Claude's calls, below.

- **A planning.** `n` in the Flow view, `f` on This folder (both revised: they never take the console's terminal,
  **Beside the console** below), or `clank flow new [NAME] [--here | --vscode]` (OpenCode where the command runs:
  here, in Clank's VS Code window from VS Code's terminal, always here over SSH) opens a planning: a record of the service, `state/flows/<workspace>/<name>/
  building.json`, with the planning session's first message beside it (`first-message.md`), so the owner can read
  what the model was told. One planning is open in a workspace at a time; a newer one sets the older aside, said in
  its event. Its name is the one given, else Clank's (`flow`, then `flow-2`, the first free in the workspace); a name
  an existing flow has is refused.
- **Over SSH** (revised 2026-10-20 at the owner's request: their first real test runs over SSH from a Linux PC into
  this Windows PC, the console in that SSH terminal). When the console or the command runs in an SSH session
  (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` in its environment), the planning always opens in that terminal: `N`
  and `--vscode` open it there too, saying why, so nothing on the way from `n` to `r` needs the PC's own screen (no
  window, no clipboard, no notification seen only there). The Monitor's Flow view is reached without F10, which a
  terminal may keep for itself: `clank console --page monitor --view flow`.
- **Where it opens** (decision 0099). The planning session is a fresh OpenCode session on the server of the
  workspace's OpenCode window (its terminal interface), shown there with OpenCode's `/tui/select-session`, as
  `/implement` hands a plan over (design 0009 §8, measured 2026-10-16). *Here:* Clank writes OpenCode's configuration
  and gives the console the command that starts the window (`agents/prepare`, the one-window rule as always); the
  console steps aside while OpenCode runs in its terminal and comes back when it ends. *In VS Code:* the window
  running in the workspace takes the session; with none, Clank's VS Code window is opened, its extension starts
  OpenCode in its terminal through `agents/prepare`, and that window takes it. Either way the session is started once
  the window's server answers on its port (the bridge waits up to a minute) and shown again twice a few seconds later,
  since a terminal interface just started may not hear the first. Neither the recorded fixtures nor Clank's code know
  an OpenCode 1.19.0 flag that opens a window on a given session, and a session started on another server would run
  there, out of the window's sight.
- **The planning session.** Titled "<name> · building the flow", its first message sent to the planner (Plan mode,
  design 0009 §3: it reads the folder, asks the owner, writes Markdown only, and uses Clank's flow tools), so the
  window takes the planner. The message is `clank/components/flows/prompts/build.md` filled in by Clank: what a flow
  is; the box types and their rules (§2, §3); the flow file's fields (§4, §11); each preset of the main slot with its
  window; how a built flow runs (the owner's three answers); Clank's template as the example, its plan's gate taken
  out; every box on the template's model (since decision 0117 it names none: what the main slot runs when the box
  starts), unless the owner asks for another in the conversation; and how to
  talk it through: read the folder; ask what it needs to know, a few questions at a time; write `BRIEF.md` with the
  owner (the goal, the limits, what done means); then submit the flow with `flow_draft` and fix what Clank reports.
- **`flow_draft(flow)`** (§9). The model sends the whole flow as its file holds it (title, defaults, boxes, lines). The
  gateway forwards `POST /flows/draft` as the client `agent`, its exact allowlist gaining that one route and nothing
  else; the service gives the draft to the planning open in the workspace its MCP server names, since that server
  knows its workspace and not its session (design 0010 §7), as a verdict goes to the VERIFY at work there. With no
  planning open there, or once the flow it builds has run, the draft is refused. Checked as a saved flow is (§3's
  rules, its presets, its workspace) and against a built flow's own rules (below), a draft that breaks one is refused
  (409) naming each problem with its field; the check's warnings (decision 0087: each box's first message past a
  quarter of its window; a file nothing gives a box) come back with the problems, or with the flow written, so the
  model fixes what it can and drafts again.
- **What Clank writes.** The draft's title, defaults, boxes and lines, with Clank's own settings over whatever the
  draft says: the workspace; `auto_accept` on, with no cap (a built flow accepts every task its DECOMPOSE proposes);
  `wait_after_every_box` off; `next_flow` "ask"; the mode auto on a box that changes files and names none (a TASK,
  whose mode would be the workspace's, review by default), and on each task accepted into the flow, so no change waits
  for the owner; the template's model when the draft names none (since decision 0117 none, so none is set); and `built` (the planning session, when, the brief's
  file and its fingerprint when the planning began).
  It is the flow's file, `config/flows/<workspace>/<name>.json` (decision 0066): the model never writes it. A later
  draft replaces it until the flow first runs.
- **A built flow's own rules** (the owner's answers, held on the model's draft only): its first box is a YOU whose
  first file is the brief, `BRIEF.md`, in the folder and changed since the planning began (written with the owner, not
  one left from before), each other file it writes in the folder too; its last box is a GATE, the final review; it has
  no other GATE and no other YOU; no box waits when done; and no box runs in review. The owner may change any of it in the Flow view
  (board D2) before or after a run.
- **Told.** `flows.built` records each draft written. The owner is asked "<title>: flow built: look, then r to run",
  a question about the flow with the next flow's answers, *Run it now* and *Later* (§10), so it shows on the console,
  the phone and VS Code as that one does; *Run it now* starts it, and a run started otherwise withdraws it. A draft
  written again asks again, the older question withdrawn. When OpenCode ends in this terminal, the console (and `clank
  flow new`) says whether the flow was built and how to look and run it, in that terminal.
- **Looked at.** The Flow view (F10, or `clank console --page monitor --view flow`) follows a flow built and not run
  yet as if it ran when it was built, so the folder's view shows it once the planning ends. Waiting for you says it
  was built with the model, to look, then `r`, and lists the check's warnings of its last draft, each whole. `r` on a flow that has not run starts it at its first box, asked
  first. `e` changes a box first (board D2).
- **Run** (decision 0098). At the start of each run of a built flow, its first box, the YOU, is done by itself when
  each of its files is in the folder and not empty and the brief differs from what it was when the planning began:
  the brief written with the model; its event says so and its fingerprints are kept as a YOU's are. A file missing, or
  the brief as it was before, it asks as any YOU. The run then goes on by itself (§10).
- **After the review** (2026-10-20, before shipping): a planning is refused in a workspace whose container runs an
  older sandbox image (its bridge and Clank's MCP server are baked in), naming the fix; a session the window does not
  show stands, the planning saying to pick “<name> · building the flow” from OpenCode's session list (`/sessions`), and
  `clank flow new` names that session before OpenCode opens; a field a draft should not have is named with the fields
  of what it is in; and the planning's first message overrides the Planner's own instructions (`planner.md`: a plan
  file, `/implement`) wherever they differ.

**Beside the console** (revised after approval 2026-10-20 (the owner: OpenCode beside the console, watch it built, start from the Monitor and This folder; two SSH windows); decisions 0100 and 0101). The owner: "I would prefer to work with the model to
build the flow in a way where I can watch the flow being built while the model is working, which means that I should be
able to open OpenCode on one side and keep the Clank menu on the other side, and I also want to start the building of
the flow from the monitor section as well as the ability to start it from the 'This folder' section." From two
mockups they chose two SSH windows side by side on another computer: on the left the console, on the right a second SSH
window running `clank flow attach`.

- **Starting never takes the console's terminal.** `n` on the Monitor's Flow view and `f` on This folder (`n` answers
  a question there, "y n ...") open a planning and bring the console to the Flow view, which shows it. The planning
  waits for its OpenCode window; nothing is handed the console's terminal. `clank flow new` keeps OpenCode in its own
  terminal, for the command line. A planning open already (waiting, opening, talking, or failed with no run since) is
  never overwritten: `n`, `N` and `f` ask first whether to set it aside (Esc leaves it), `clank flow new --set-aside`
  says so on the command line, and the service refuses a new one otherwise; a new planning takes a name no flow and no
  planning has. Pressed again while a planning starts, `n`, `N` and `f` do nothing.
- **Where OpenCode opens, from the console** (decision 0100): over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY`)
  nothing opens: the Flow view says "talk with the model: in another terminal, cd <folder> then clank flow attach"
  (the console has no way to copy to the clipboard, so nothing is copied); at the PC in Windows Terminal (`WT_SESSION`
  set, not SSH), the window is split and OpenCode runs in the new pane on the right (`wt -w 0 split-pane -V -d
  <folder> <python> -m clank flow attach --workspace <W>`), the message instead when `wt` is missing or refuses; in VS
  Code's terminal, in Clank's VS Code window as before (`N` asks for that anywhere but over SSH).
- **`clank flow attach [--workspace W]`** runs OpenCode's terminal interface in this terminal on the workspace's open
  planning, the path `clank flow new` takes, and comes back when OpenCode ends. A planning still waiting for its
  window starts its session there; one already talking (its window closed, or in another terminal) is shown there
  (the bridge's `show`, which waits for the window as `implement` does). It follows the one-window rule: another
  OpenCode window open in the workspace is closed first, and the command says so (`w` on This folder allows several).
  A planning that failed (its window did not answer in time, say) and is still shown, no run in the workspace since,
  is tried again: its session starts on the new window. One whose session is still starting on the window prepared
  before is left to it (that window is not closed for another): attach says to wait, then attach again, which shows
  the session once it talks, or tries it again once it failed. With no planning open, it says so and how to open one.
- **Watching it built.** While a planning is open (waiting, opening, talking, or failed and not followed by a run),
  the Flow view shows it, read once a second and drawn again only where it changed:
  - **Building it with the model** (in place of Selected): its steps: started; reading the folder (its tool calls so
    far); waiting for your answer (the model's last message ended without a tool call, or a question of its waits);
    `BRIEF.md` written or changed since the planning began, with the time; each draft as sent, its number, refused
    with each problem (its field and message) or accepted; and a **Live** box for the planning session (what it does
    now, its step), as a running box has.
  - **The latest draft** drawn with the Flow view's own layout and marked DRAFT (the heading and the Flow panel's
    note), even when refused, so the owner sees the flow take shape: what of it reads (boxes that read, lines between
    them) is drawn. The service keeps the latest draft as Clank would write it (`draft.json`) and each draft's number,
    time, state and problems with the planning, in Clank's state, never in the folder.
  - **Waiting for you** says how to talk with the model (`clank flow attach`, or where OpenCode opened) until its
    session runs; for a planning that failed, why, and that `clank flow attach` tries it again (or `n` opens another).
  - **Enter** opens the Session view on the planning session (and from it the Context view), **Esc** back.
  - Once a draft is accepted, the view becomes the built flow, with "flow built: look, then r to run".

**Claude's calls (2026-10-20):**

1. The planning session runs on the workspace's OpenCode window and is shown there (`/tui/select-session`); no CLI
   flag attaches a window to a session (decision 0099).
2. Here: `agents/prepare`'s command in this terminal; in VS Code: the window running, else Clank's VS Code window,
   whose extension starts one; the session started once the window's server answers, shown again twice.
3. `n` opens where the owner is (VS Code when `TERM_PROGRAM` says the console runs in VS Code's terminal), `N` in VS
   Code; `clank flow new` the same way, `--here` and `--vscode` choosing.
4. The planning is a file of the service's state, one open per workspace, a newer setting the older aside; its name
   given or Clank's (`flow`, `flow-2`, ...), never an existing flow's.
5. Its first message is sent to the planner, from `prompts/build.md` filled in by Clank, and kept beside the planning.
6. `flow_draft` reaches the service only through the gateway's exact allowlist, scoped to the planning open in the
   workspace (decision 0097); refused once the flow has run.
7. Clank writes the flow file, its own settings over the draft's: auto-accept on, no wait after any box, `next_flow`
   ask, the template's model when none is named, `built`.
8. A built flow's own rules: brief first and in the folder, one gate and last, no other YOU, no box that waits.
9. The YOU box of a built flow is done by itself at each run when its files are in the folder (decision 0098).
10. The owner is told through the next flow's question (*Run it now*, *Later*), so every client shows it unchanged.
11. The Flow view follows a built flow not run yet as of its build; `r` on a flow not run starts it.
12. Over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set where the console or the command runs), always this
    terminal, whatever key or flag asked for VS Code, said so (the owner's requirement, 2026-10-20); `clank console`
    gains `--view` to open the Monitor on its Flow view without F10.
13. Left out: VS Code's extension starting OpenCode by itself when its window is already open without OpenCode (the
    owner opens it there, Clank: Open the agent), a planning resumed after the service restarts (a new `n` starts
    another), and changing an existing flow with the model (§15 builds new flows).
14. After the review: a built flow's boxes that change files run in auto mode and its DECOMPOSE's tasks are accepted
    with no cap, so nothing stops the run in its middle; the brief must change during the planning; the Planner's own
    instructions are overridden by the planning's first message rather than a second planner agent, which would join
    OpenCode's Tab order (decisions 0097, 0098).
15. Beside the console (revised after approval): `f` on This folder, where `n` answers a question; no clipboard copy
    (the console has none); the Windows Terminal split runs `python -m clank` from the console's own Python, passing
    `--home` when `CLANK_HOME` is set, since a new pane does not inherit the console's environment; `clank flow
    attach` shows a planning already talking on its new window (the bridge's `show`), never a second session; the
    watched planning takes the place of Selected, since at half a screen's width the panels stack and Selected comes
    right under the flow; a draft that does not read whole is drawn as far as it reads; after the review, `clank flow
    attach` tries a planning that failed again, and leaves one whose session is still starting to its window, saying
    to wait, so the owner is never stuck (decisions 0100, 0101).

## 16. The orchestrator: a model that steers the run

The owner (2026-10-22): "we need to have the ability to have a full orchestration agent that acts as the guider for
the Flows in the case where the user, like myself, wants to let the entire flow run autonomously and let the main
orchestration model really be the one to help let the flow evolve and will look at the reports that are created after
steps are completed and determine how the flow should be built and if anything needs to change at any moment and will
make informed decisions at any of the Gate sections." And: "do some research online on the best configurations that
are similar to what I am doing here and just implement anything that is really useful"; "a pretty major point of this
work is to really orchestrate extremely nicely." What the survey found, and what it keeps for later, is
[docs/research/orchestration.md](../research/orchestration.md).

**What it is.** The **orchestrator** is a flow setting, off unless the owner turns it on (the Flow view's `O`, `clank
flow orchestrator NAME on`, or the planning's draft). While it is on, a run steers itself at **checkpoints**: after
each box ends, and whenever the run would wait for the owner. A checkpoint is a fresh session (§5), in Plan mode, on
the flow's own server and model (its own preset if named), handed: the brief, the flow's map, what the box just did
(its outcome, its deliverables, its handoff note, a VERIFY's findings, its accept command's result), the run so far
(each box's state, tries, time and tokens), the question when there is one with its answers, the budget left, and the
**ledger**. It decides with one tool, `flow_decide`, and its session ends.

**The ledger** (Magentic-One's two ledgers): the run's own file, kept by Clank beside the run (`orchestrator.md`),
never by the model's hand. Its **facts and plan**, what is known now and the plan from here, are rewritten by each
decision; its **progress**, one entry per checkpoint, holds the five answers every decision gives: is the brief met
(line by line), is the run looping, is it progressing, what happens next, and the note the next box is told. Every
checkpoint reads the ledger whole, so each starts fresh yet knows the run; none relies on a long context (the local
model's window is the limit that matters).

**What it decides.** At a question, one of the question's own answers, with the owner's words for a note: at a gate,
*approve*, *send back* (with what must change) or *stop*; at a box that failed or used its tries, *one more try*,
*take it as it is*, *skip the box* or *stop*. The answer is given as the owner's would be (§10), by the orchestrator,
and the run goes on exactly as it would have. After a box that is done: *go on*, *change* (the boxes ahead), *send
back* to an earlier box with a note, or *stop*. A **change** edits a box not yet run (its prompt, what it sees, what
accepts it, its limits, its tries, its model) or adds one (a TASK or a VERIFY, with the full contract of §4: prompt,
files seen and written, what accepts it); it never touches a box that ran, `BRIEF.md`, or the folder, and it is
checked by the rules of §11 like any edit. A **note** goes to the next box's first message ("The orchestrator's note:
..."), as the owner's note does.

**How it decides** (its prompt, `prompts/orchestrator.md`, from the survey):
- *Machine checks first.* An accept command that passed or failed (a verifier, a test) outranks a VERIFY's verdict,
  which outranks the orchestrator's own reading (AlphaEvolve, FunSearch: the evaluator decides).
- *No claims of its own.* It reports what the checks confirmed; it never calls a result new or important (the AI
  Scientist's papers overclaimed novelty); the owner judges.
- *A failure's class decides the remedy* (the Stabilizer Rank Challenge's research loop): a failure outside the work
  (the session gone, the server, a model switch) is tried again as it was; a time or token limit reached by work that
  was progressing gets more of it; a result that failed its check gets a changed approach (a sharper prompt, a smaller
  step, a different method), never the same try again.
- *Effort follows the budget* (Anthropic's research system): the budget left is in every message; with little left it
  wraps up (the tasks that can finish, then INTEGRATE) rather than starting new work.
- *Stalls are named.* A **stall count** rises at each checkpoint that answers "not progressing" or "looping", and
  returns to 0 at progress; at the flow's stall limit (3) the next decision may not be *go on*: it changes the plan
  (sends the work back to the PLAN with what must change, or changes the boxes ahead) or stops (Magentic-One's reset).

**Its limits**, a flow setting, always set (Magentic-One's framework leaves them unlimited by default, and must be
told): `changes` per run (12: each change, send back, skip and extra try counts one), `extra_tries` per box past its
cap (2), `stall` (3), a checkpoint's own limits (20 minutes, 60,000 tokens written), and `final_review`:
`orchestrator` (it decides the last gate too, as the owner asked) or `owner` (the last gate waits for the owner).
Past a limit the orchestrator cannot act: the question waits for the owner, as without it, saying why.

**The owner stays in charge.** A question the orchestrator is deciding shows "the orchestrator decides" in Waiting for
you, and the owner may answer it first (the orchestrator's later answer is then set aside). The Flow view's
**Orchestrator** panel shows it on or off, its model, its last decision with why, the stall count and the limits used;
`O` turns it off or on at any moment, the run going on; `L` shows the ledger whole. Every checkpoint and decision is
an event (`flows.orchestrator`) and a line of the run's log; `clank flow orchestrator NAME` prints the ledger.

**Built flows.** The planning's first message tells the model the setting exists, and a draft may turn it on; Clank
writes it off unless the draft or the owner says otherwise, and the owner may turn it on in the Flow view before `r`.

**Its word for the owner, and its role** (revised 2026-10-22 at the owner's request, decision 0127): "the orchestration
occurs after each completed step just to make sure things are on track and to get my attention if there is anything
that I need to be aware of out of nowhere." It runs on the flow's model (the local model, unless the flow or the
setting names another preset). Each decision may carry `tell_user`, what the owner should know now: a question of
high urgency (it reaches the phone at once) that the run does not wait for, answered *Seen*, *Pause the run* or *Stop
the run*. After a box it may also choose `pause`, and at a question `leave` it to the owner, each telling them why.
Its **role** is `steer` (all of the above) or `watch`: after each box it goes on or pauses and tells the owner what
they should know, and every question stays the owner's. `O` turns it on steering, then watching, then off. A
checkpoint that ends without calling `flow_decide` is reminded once in its session before the question is left to the
owner (a local model wrote its decision as text in the first long run).

Claude's calls, the owner to check: checkpoints after every box (not only at questions), since the owner asked it to
"look at the reports that are created after steps are completed"; the final review decided by the orchestrator by
default when it is on, since the owner asked for "informed decisions at any of the Gate sections", with `owner` one
key away; the limits' numbers; its tool answers the question through the questions API rather than a path of its own,
so a gate means the same thing whoever answers it.

**Kept for later** (the survey's other ideas): a SEARCH box (a program evolved against an evaluator, with a database of
candidates: AlphaEvolve), a tree of tries (alternatives branched from a failed try: the AI Scientist v2), a tournament
of plans (Google's co-scientist), and parallel workers where the machine has room for them.

## Decisions to record

- 0057: A flow is a chain of boxes; only a VERIFY's fail line points back, and every loop ends at a gate once its
  box's tries are used; DECOMPOSE's tasks run one after another, each handed the ones before; other shapes wait for a
  later design (§3).
- 0058: INTEGRATE's brief starts a next flow, linked to this one, after the last gate (§3, the owner's **Choice**).
- 0059: A box's mode (Plan, Review or Auto) applies to its own session; the workspace's mode to every other (§4).
- 0060: Each box runs in a new session on the flow's own OpenCode server without a terminal (§5, decided by the owner
  2026-10-18).
- 0061: The runner is an operation per box in the service; one flow runs at a time; gates, YOU boxes and proposals are
  questions; nothing starts again on its own after a change or a restart (§6).
- 0062: A box's model is a preset switched into the main slot before the box starts, only while no request is in
  flight and the owner's own session in the workspace is idle; the owner's window is told its model changed (§7).
- 0063: VERIFY uses the checked box's preset in a fresh session unless it names another (§7, the owner's **Choice**).
- 0064: The model changes a flow only by proposals through Clank's MCP server and the gateway, accepted by the owner
  or by auto-accept within a cap; accepted boxes join the flow's file, marked with the run that proposed them; a
  DECOMPOSE run again replaces only its tasks not started; the planner may make proposals (§9).
- 0065: A finished box goes on by itself unless a gate follows it or its *when done* waits (§10, decided by the owner
  2026-10-18).
- 0066: A flow is a settings file in Clank's home, its runs state beside it, copied into the folder on demand (§11,
  decided by the owner 2026-10-18).
- 0085: A box's first message hands the flow's brief and a map of the flow, before its task (§5, the owner's choice of
  2026-10-20).
- 0086: A box hands on a short note, written in the folder and kept beside its try; a missing note is marked, not
  failed; a VERIFY is handed none (§2, §5, §8).
- 0087: A first message's size is counted by the engine when it can, else estimated and said so; the check warns past
  a quarter of the window (§5, §6).
- 0093: The Flow view lays a flow out in rows of stages (one box, or a DECOMPOSE's tasks as a fan), from what the
  service says of it, and shows its boards D2-D4 on the page in place of D1's panels (§12, §14 step 6; Claude's call
  while building step 6, [plan s28](../plans/s28-flows-the-flow-view.md)).
- 0091: The next flow is made from Clank's template once the last gate is approved, its brief copied in when it first
  runs, and the owner asked whether to run it now (§3, §10, §11; how 0058 is built).
- 0092: A flow's OpenCode server reads the container's one configuration, written for the main slot as it runs,
  until two servers each keeping their own is measured (§5, §7; Claude's call, building step 5).
- 0097: A flow is built by talking it through: the model drafts it with `flow_draft` in a planning session, Clank
  checks it, answers its problems and warnings, and writes the flow's file (§15; Claude's call, at the owner's
  request).
- 0098: A built flow runs on its own until its final review: auto-accept on, no gate but the last, no wait after any
  box (its first run included), its first YOU box done by the brief written with the model (§10, §15; the owner's
  answers, built as Claude's call).
- 0099: The planning session is started on the workspace's OpenCode window and shown there, the window started first
  in this terminal or in Clank's VS Code window; no OpenCode flag attaches a window to a session (§15; Claude's
  call).
- 0100: Starting a planning from the console never takes its terminal: OpenCode runs beside it, in a second terminal
  with `clank flow attach` (over SSH, said), a Windows Terminal pane, or Clank's VS Code window (§15, revised after
  approval; the owner's choice of two SSH windows, built as Claude's call).
- 0101: The Flow view shows the planning while it is open: its steps, the latest draft drawn and marked DRAFT (kept in
  Clank's state), its session live, Enter on it (§15, revised after approval; Claude's call).

- 0123: The orchestrator steers a run at checkpoints (after each box, and at each question): a fresh Plan-mode session
  handed the run and a ledger Clank keeps, deciding with `flow_decide`; its answer to a question is given through the
  questions API as the owner's would be; off unless turned on (§16; the owner's request, built as Claude's call).
- 0124: The orchestrator's limits are always set (changes, extra tries, stall, its own time and tokens, who decides
  the final review); past one, the question waits for the owner (§16; Claude's call).

## Revision log

- **2026-10-18, §12 revised after approval, at the owner's comment on the interactive prototype:** "We need a better
  way of displaying the different tasks, since a simple list like this is difficult to deal with". Board D4 shows the
  proposals as cards side by side in the order they will run, each with its state, its settings and its own answers,
  the highlighted one's whole prompt below them. Step 6 builds it.
- **2026-10-18, §14 step 6 revised after approval, at the owner's comment on the prototype's Switch board:** "This
  tab is overlapping with the legend, so we need to make sure we are careful with the way we are treating the layout
  in these diagrams and we need to be sure we are testing out edge cases for dealing with this in practice". Step 6's
  tests lay out generated flows of 1 to 12 tasks and prove that nothing overlaps; a flow taller than its panel
  scrolls.
- **2026-10-18, §9 and §12 revised after approval, at the owner's comment on the prototype's live board:** "I also
  don't really like the run log below the flow, it seems out of place and seems like we should have something more
  productive down here". Under the flow: The brief, checked; Deliverables; Ahead; the run log in a window on `h`.
  `flow_verdict` gains `criteria`, the brief's lines a check touched, so the first panel shows evidence, not guesses.
- **2026-10-20, §3 and §9 revised after approval, with step 4** (Claude's call 17, [plan
  s26](../plans/s26-flows-proposals.md), at the review of step 4): how a DECOMPOSE's task is handed the deliverables
  of the tasks before it. Its first message names each by its path, the task that wrote it last and its size, as §5
  hands a file too large to give whole, and gives whole only those it sees: handing every task its forerunners' files
  whole would make each first message of a long series longer and slower to read (§7), and the task reads what it
  needs with its tools. What decision 0057 decides, the tasks a chain each handed what those before it delivered, is
  unchanged.
- **2026-10-20, §2, §5, §6, §8 and §14 revised after approval, at the owner's request** (decisions 0085-0087, [plan
  s30](../plans/s30-flows-each-box-prepared.md)): "The big thing that we need to implement is to make it so that each
  of the individual tasks are brand new sessions that get fresh context windows, but making sure that we are preparing
  each of these tasks with the correct context for the agent at that task to get the work done properly." A box
  already ran in a new session for each try; the owner chose four additions to its first message, all built now: the
  brief handed to every box a model runs, once; a short map of where it sits in the flow; a handoff note each PLAN,
  TASK and INTEGRATE writes and every later box but a VERIFY is handed (a VERIFY stays independent of the sessions it
  checks); and `clank flow prepare`, each box's first message as it would be sent now with its size against its model's
  window, with `clank flow check` warning past a quarter of it and on a file nothing gives a box. Step 8 builds them.
- **2026-10-20, §3, §6, §10, §11 and §14 revised after approval** (decision 0091, [plan
  s31](../plans/s31-flows-the-next-flow.md)): decision 0058, the next flow, was decided but not built. Built now, as
  §3 and §10 say: once the last gate is approved, the next flow is made from Clank's template with the last
  INTEGRATE's brief, linked both ways, and the owner is asked whether to run it now, as a question of its own rather
  than as an extra answer of the gate, since the next flow is made only once the gate is approved; its brief is copied
  into its YOU box's file when its first run starts, so approving one flow changes no file of the folder; the flow's
  `next_flow` setting may run it at once or make none; `clank flow next` shows, makes or runs it. Step 9 builds it.
- **2026-10-20, §15 added and approved, §2, §9, §10, §11, §12 and §14 revised after approval, at the owner's request**
  (decisions 0097-0099, [plan s32](../plans/s32-flows-a-flow-built-with-the-model.md)): "for starting the flow I need
  the ability to use the LLM to build the flow at the beginning, and then I want to let the flow go from there". Their
  three answers are §15's: talk it through with the model (`n`, `clank flow new`), look, then run (`r`), and stop only
  at the end. The first YOU of a built flow is done by its brief (§2); `flow_draft` joins the flow tools (§9); a built
  flow has no gate but the last and waits after no box, its first run included, which §10's Choice already allowed and
  a built flow now says in its file (§10); `built` marks it (§11); `n`, `N` and `r` on a flow not run (§12). Step 10
  builds it.
- **2026-10-20, §15 revised after approval, at the owner's request** (decisions 0100-0101, [plan
  s33](../plans/s33-flows-watch-the-flow-built.md)): "I would prefer to work with the model to build the flow in a way
  where I can watch the flow being built while the model is working ... OpenCode on one side and keep the Clank menu
  on the other side ... start the building of the flow from the monitor section as well as ... from the 'This folder'
  section." They chose two SSH windows side by side. Starting from the console (`n`, This folder's `f`) never takes
  its terminal; `clank flow attach` runs OpenCode on the planning in another terminal; at the PC, Windows Terminal is
  split; the Flow view shows the planning while it is open: its steps, the latest draft marked DRAFT, its session live.
- **2026-10-21, §15 revised after approval, for the first public beta:** Clank's template names no model, so a flow
  built with the model runs on what the main slot runs unless the user names a preset (decision 0117, superseding
  0095 for the shipped default); the planning's message speaks of "the user" and quotes no one.
- **2026-10-22, §5 and §16 revised after approval, after the first long run** (decisions 0127-0128, [plan
  s40](../plans/s40-the-first-long-runs-fixes.md)): a session's end is read by the runner itself should the watcher not
  say it, and the watcher opens a stream again after its instance ended; the orchestrator's word for the owner, `pause`,
  `leave` and the role `watch`, at the owner's request.
