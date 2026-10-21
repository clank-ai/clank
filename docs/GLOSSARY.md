# Glossary

Words with a special meaning in Clank's documents and code, defined once. Alphabetical.

- **Access level**: what a caller may do through the Clank API: `control` (the user's own clients on this machine),
  `remote` (paired devices), `process` (data-plane processes), `session` (an agent's session, through its edge)
  (design 0002 §2.7).
- **Adapter**: the one module through which Clank uses a program it does not own (an engine, a container platform,
  an agent program), meeting the interface of its kind; what it supports is read from the program in use, never
  assumed (design 0002 §2.10). See *contract test*, *recording*.
- **Add a model**: the console's page that adds the main slot's model in one pass: Cloud (OpenRouter, the
  agreement, the key pasted hidden, a model from the live list, its settings, one short request) or Local (this
  machine's presets and what each needs); the console opens on it while no model is usable (design
  [0016](design/0016-cloud-models.md) §14, decision [0105](decisions/0105-with-no-usable-model-the-console-opens-on-add-a-model.md)).
- **Agent adapter**: the one module per agent program that turns Clank's settings (the mode, the model by its role
  name, the tools and skills turned on) into the program's own configuration, starts the program in its sandbox,
  follows its sessions and events, and turns its permission prompts into questions to the user (decision
  [0011](decisions/0011-agent-programs-are-plugged-in.md)).
- **Agent program**: the program that plans, reads, edits and runs commands for the user, such as OpenCode. Clank
  plugs agent programs in through agent adapters.
- **Agreement** (to a cloud provider): the owner's one consent, when adding a cloud provider, that prompts and the
  files and command output the agent reads go to it; kept in the provider's record (`agreed`); nothing loads from a
  provider without it (design [0016](design/0016-cloud-models.md) §9).
- **Artifact**: a file that Clank or an agent made for the user (a figure the agent was asked for, a trial's report),
  kept in `CLANK_HOME/artifacts/` with where it came from (design 0002 §2.12).
- **Board** (of the Flow view): what the Monitor's Flow view shows in its panels: D1, the flow running (its boxes and
  lines, the box selected, what waits for you, its brief checked, its deliverables, what is ahead); D2, a box's
  settings, each with its key; D3, a gate and its answers; D4, a DECOMPOSE's proposals as cards. Named after the boards
  of the design canvas they were drawn on (design 0013 §12, decision
  [0093](decisions/0093-the-flow-view-lays-a-flow-out-in-rows-of-stages.md)).
- **Bounds**: what a workspace's agent has without asking: folders, hosts, repositories, tool servers, and where its
  model requests may go. Beyond them it may ask for access if its mode lets it; a grant then extends the bounds, never
  past a deny (design 0002 §2.6).
- **Box**: a step of a flow: a big task with a deliverable, done by a model in a session of its own (PLAN, VERIFY,
  DECOMPOSE, TASK, INTEGRATE) or by the owner (YOU, GATE); its settings say its model (a preset), its mode, the files it
  sees, its prompt, its deliverable and what makes it right (design 0013 §2, §4). A section of a console page is a
  *panel*.
- **Brief** (of a flow): the file the flow's first box, a YOU, writes (usually `BRIEF.md`): the goal and the limits of
  the work. Every box a model runs is handed it in its first message, once, whether or not its *sees* lists it (design
  0013 §5, decision [0085](decisions/0085-a-boxs-first-message-hands-the-brief-and-a-map-of-the-flow.md)).
- **Built flow**: a flow built with the model: the owner talks the work through in a *planning*, the model drafts the
  flow with `flow_draft`, and Clank checks each draft and writes the flow's file, marked `built`. It runs on its own
  from its brief to its final review: auto-accept on, no gate but the last, no wait after any box, its first YOU done
  by the brief written with the model (design 0013 §15, decisions
  [0097](decisions/0097-a-flow-is-built-by-talking-it-through.md) and
  [0098](decisions/0098-a-built-flow-runs-on-its-own-until-its-final-review.md)).
- **Button** (of the console): a key the console shows, drawn as its key and its words with a blank cell at each
  side, pressed by Enter or Space while it has the focus, by its key from anywhere on its page, or by a click, all
  three the same way; it belongs to a *group* (design 0011 §12, decision
  [0120](decisions/0120-every-key-is-a-button-of-one-group-widget.md)).
- **Check**: verifying a configuration without starting anything: validity, memory fit, cost, and what the engine's
  adapter can confirm (program, version, accepted flags, the model file). See also *trial*.
- **Clank service**: the one process that is Clank's control plane: it holds the settings and the state, makes every
  decision, records everything, and serves the Clank API (decision
  [0013](decisions/0013-one-service-control-and-data-planes.md)). Its components include the runtime and the gateway.
- **CLANK_HOME**: the one folder that holds everything of one user on one machine: configuration, secrets, state,
  logs, installed engines and (by default) models. `~/.clank` unless set otherwise (design 0001 §7.2).
- **Client**: a program that uses the Clank API and holds no state of its own: the console, the VS Code extension, the
  phone page, the `clank` command, other programs.
- **Cloud model**: a model run by a cloud provider, reached with the owner's key through the gateway; a *cloud
  preset* names its provider (`endpoint`) and the model's id there, and serves the main slot in an engine's place
  (design [0016](design/0016-cloud-models.md) §7).
- **Cloud provider**: an endpoint whose reach is `cloud`: a company's API reached with the owner's key, OpenRouter
  first (decision [0102](decisions/0102-the-first-cloud-provider-is-openrouter.md)); its record is
  `config/endpoints/<id>.json`, its key a secret (design [0016](design/0016-cloud-models.md) §4).
- **Component**: one part of the Clank service, with a fixed shape and a public interface (design 0002 §1): machine,
  runtime, gateway, workspaces, network, agents, tools, skills, remote.
- **Console**: Clank's terminal application: it shows what runs and lets the user change it (decision
  [0003](decisions/0003-one-terminal-console.md)).
- **Container platform**: where Clank's containers run: Docker Desktop first, Docker Engine on Linux later; the
  workspaces component's kind of adapter. A container is Clank's only when it carries this CLANK_HOME's `clank.home`
  label (design 0002 §2.9).
- **Context facts**: what an engine's adapter declares of its context for a preset's options (`context_facts`): its
  window and longest answer, its thinking budget, the part it attends to exactly (KVMem's retrieval budget) or its whole
  window, where it runs, whether it counts tokens or keeps one conversation, where its answer reports each figure, and
  how it refuses a request its context cannot hold (decision
  [0090](decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md)); with the model's template
  facts and calibration in its catalog entry, all the Monitor reads of the context window (design 0012 §4, decision
  [0067](decisions/0067-the-monitor-reads-the-loaded-models-facts.md)).
- **Context margin**: the tokens of the engine's window an agent program is not told of, kept free for one step's tool
  results, so that it compacts a session before a step's results can push its next request past the window
  (`context_margin` in `config/opencode.json`, 16,384 by default, at most a quarter of the window; design 0012 §4.1,
  decision [0089](decisions/0089-opencode-is-told-the-window-less-a-margin.md)).
- **Context parts**: what fills a session's context window, part by part (the system prompt, the tool definitions,
  the owner's messages, the model's text, the thinking sent back, the tool calls, the tool results and loop text) and
  item by item, as the Monitor shows them: the gateway counts each request's characters by part (its census), and the
  service shares them out to the engine's own count by the loaded model's template and calibration, so they are an
  estimate and say so (design 0012 §4.2, decision [0051](decisions/0051-the-contexts-parts-are-estimated-in-the-gateway.md)).
- **Contract test**: the one test file per kind of adapter (`tests/contract/test_<kind>.py`), run against every adapter
  of the kind with what its real program answered (design 0001 §8.2).
- **Control plane**: the Clank service, where decisions are made and records kept. It carries no traffic itself. See
  *data plane*.
- **Cost** (of a cloud request): what the provider charged for it, in US dollars: OpenRouter's own `usage.cost`, its
  generation's record for a stream cut short, an estimate (marked `≈`) until then; summed by session, workspace, flow,
  day and month (design [0016](design/0016-cloud-models.md) §11-§12).
- **Data plane**: the processes that carry the traffic (the engines, the gateway, the tool hub, the sandboxes and their
  edges), started, watched and stopped by the Clank service. While the service is down they keep what was already
  allowed and refuse anything new.
- **Decision record**: a file in `docs/decisions/` that records a choice, why it was made and what it rules out,
  always named by its number ("decision 0014"). Not to be confused with a *policy decision*.
- **Deliverable**: the files a box of a flow must write in the workspace's folder, and what they hold; it counts only
  when written during the box's try, and each try's copy is kept with its fingerprint (design 0013 §4, §8).
- **Device**: a phone or a computer paired to reach Clank over the user's tailnet while remote access is on (decision
  [0012](decisions/0012-the-phone-page-and-push.md)).
- **Edge**: a sandbox's only door: to the gateway, the tool hub and the Clank service, and to git or the web only by
  grant.
- **Endpoint**: a provider that someone else runs (a cloud provider reached with a key, a server on an HPC cluster or
  another computer). Clank connects to it, but never starts or stops it.
- **Enforcement point**: the part that carries out a policy decision because it can actually stop the action: a
  sandbox's container, the edge, the tool hub, the gateway or the service (decision
  [0020](decisions/0020-enforce-where-it-can-be-stopped.md)).
- **Engine**: a server program that loads a model and answers requests through an OpenAI-compatible API, such as
  KVMem/llama.cpp. Clank starts and stops engines on the user's machine.
- **Engine adapter**: the one module per engine that tells Clank what options the engine has, how to launch it with a
  model, and how to read its health and metrics.
- **Engine's own default**: what an engine does with an option it is not given. A launch option left unset passes no
  flag and keeps it; where one value cannot say it (KVMem's temperature is 1.0 with thinking and 0.7 without), the
  option says it in words, and the console shows them (design 0003 §4.1, decision
  [0119](decisions/0119-sampling-and-gpu-layers-are-launch-options-left-unset.md)).
- **Event**: a record of something that happened: its id, time, type, subject, actor, a one-line summary and its data.
  Events are the history, and clients receive them on one stream (design 0002 §2.3).
- **First message** (of a box): the one message a box's fresh session is sent, kept as `first-message.md` beside its
  try: its type's instructions, where it sits in the flow, the brief, its task, the *handoff notes* of the boxes before
  it, the files it sees, what the boxes before it delivered, its deliverable and its own note, and its last try.
  `clank flow prepare` shows each box's as it would be sent now, with its size in tokens against its model's window,
  counted by the engine or an estimate said so (design 0013 §5, decision
  [0087](decisions/0087-a-first-messages-size-is-counted-by-the-engine-else-estimated.md)).
- **Floor**: Clank's safety floor: deny rules shipped with Clank that no setting changes, such as "no sandbox sees
  `CLANK_HOME`" (design 0002 §2.6).
- **Flow**: the work as a program of boxes joined by lines, kept as a readable file in Clank's home
  (`config/flows/<workspace>/<name>.json`), run box by box by the service and steered from the Monitor's Flow view
  (design 0013; decisions [0057](decisions/0057-a-flow-is-a-chain-of-boxes.md) to
  [0066](decisions/0066-a-flow-is-a-settings-file-in-clanks-home.md)). Not a session's flow: the chart of what one
  session did, drawn in the Monitor's Session view (design 0012).
- **Flow view**: the Monitor's view of a flow (F10, its first tab; `clank console --page monitor --view flow`): the
  flow the console's folder follows (its active run's, else the one run last or built last), drawn in rows of *stages*, with its *boards*; Enter on a running box opens its session
  in the Session view (design 0013 §12, decision
  [0093](decisions/0093-the-flow-view-lays-a-flow-out-in-rows-of-stages.md)).
- **Gate**: a box of a flow where the owner decides: approve, edit then approve, send back with a note, or stop; a
  question, answered once from any client, that never expires (design 0013 §10). VS Code shows it with **Open** (the
  file, the gate back once it is saved) and **Diff** (the last two tries); the phone lists it under its flow.
- **Gateway**: the data-plane process every model request passes through: it routes the request to the right
  provider, applies the role's sampling, and records the request and its answer.
- **Generation reserve** (KVMem's `kvmem.gen_reserve`): room kept on the GPU, beside the retrieval budget, for the
  answer being written. KVMem v0.16 fails an answer that outgrows it once older context has been retrieved, so Clank
  refuses a preset whose longest answer is more than its reserve (decision
  [0069](decisions/0069-a-frontier-preset-over-262k-with-retrieval.md)).
- **Grant**: what an approval creates when it is for longer than once: a permission and its exact target, for a
  session or a workspace, until a set end. It can be revoked at any time (design 0002 §2.6).
- **Group** (of buttons): one widget of the console that takes the focus and holds buttons in a row or a column, with
  its own cursor: the keys bar, a panel's actions, a question's options, a window's keys. Tab moves between groups,
  the arrows inside one, stopping at its ends (design 0011 §12, decision
  [0121](decisions/0121-how-the-focus-moves-between-buttons.md)).
- **Guide**: the Monitor's actions on the session it follows, each on its own key: stop now (`.`), a note the model
  reads at its next step (`m`), pause after this step (`p`), undo the last step (`u`: OpenCode's revert at the end of
  the step before, or of the whole turn when the owner's message comes first, its text back in the note window; `u`
  again redoes it until the owner's next message), compact now (`k`), drop an item from the context (`x`: a finished
  call's result cleared as OpenCode clears it, the call kept). Each says what it will do, as the exact call, what it
  costs and, when it cannot run, why; each shows in the flow afterward (design 0012 §9). Stop, the note and Compact now
  are built (step 9), Undo and Drop (step 10), and the pause (step 11); a Watch for rule's note and its pause go
  through the Guide too.
- **Handoff note**: the few lines a PLAN, TASK or INTEGRATE box writes last, `.clank/handoff/<flow>/<box>.md` in the
  folder: what it did, the decisions it made and why, what is still open. Copied beside its try when written during it,
  and handed to every later box but a VERIFY; a VERIFY's verdict and a DECOMPOSE's summary stand for theirs; a missing
  one is said, never a failure. Not a *note*, which is the owner's message to a working session (design 0013 §5,
  decision [0086](decisions/0086-a-box-hands-on-a-short-note.md)).
- **Hold**: the gateway keeping a session's next model request, and its subagents', answered at once and kept alive
  with comment lines, until the owner resumes: how the Guide pauses a session after its step (design 0012 §9.4,
  decision [0055](decisions/0055-pause-is-the-gateway-holding-the-next-request.md)). A note sent while held ends the
  request held before it as an empty step, so OpenCode reads it, and the pause stays (the request that carries the
  note is held until the owner resumes); only the service, with its local token, pauses and resumes (decision
  [0084](decisions/0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md)).
  The flow shows each hold on its step's line, "⏸ held by you 12:22 to 12:25".
- **Kernel**: the parts every component is built from: records, events, operations, questions, policy, secrets,
  processes, adapters (design 0002 §2).
- **Keys bar**: the console's bottom row: the keys of the page on screen, then the keys that act anywhere, each key
  with its words; each page declares its keys once, as named actions (`Page.KEYS`), which the keys bar, Help and `?`
  read (design 0011 §7, decision [0046](decisions/0046-the-keys-bar-shows-the-pages-keys-first.md)).
- **Kind**: the type of a record (a preset, a workspace, a mode, a question), defined once as a Pydantic class from
  which its file schema, its API description and its TypeScript types are generated (decision
  [0015](decisions/0015-kinds-defined-once-in-pydantic.md)).
- **Launch option**: a setting fixed when an engine starts (context window, KV cache type, retrieval budget, draft
  tokens). Changing one restarts the engine.
- **Library item**: something the user installs: a skill, an MCP server, a mode, a test suite or a preset shared by
  others. All share one life cycle: a source, installing with review, turning on, updating, removing (design 0002
  §2.11).
- **Live text**: a session's model request as it is written (its thinking, its answer and its calls' arguments),
  which only the gateway sees as it comes, since OpenCode keeps a part's text only at its start and its end; the
  Monitor shows it with `l`, and the Requests page (F7) the newest of all with `v` (design 0012 §7).
- **Local only**: said of an MCP server the owner marked so, and of Clank's Notion tools: what they return never goes
  to a cloud model, kept from it in four places (design [0016](design/0016-cloud-models.md) §10, decision
  [0111](decisions/0111-local-only-content-is-kept-from-the-cloud-in-four-places.md)).
- **Loop guard**: the gateway's watch on each streamed answer: when a part of it (the thinking, the text, a tool call)
  repeats itself, its newest stretch compressing to almost nothing, the gateway stops the answer and says so
  (`model_looped`) (design 0004 §2, decision 0040).
- **Loop text**: text that repeats itself kept in a session's context: an item the model wrote that compresses as far
  as a loop over its whole length (the loop guard's measure), the result of a call that did, and the third and later
  identical call in the last twelve with its result; a part of its own among the context parts (design 0012 §4.3,
  decision [0052](decisions/0052-loop-text-is-a-part-of-its-own.md)).
- **Machine column**: the console's right-hand column: the machine's meters and what Clank does now, each a panel; F5
  shows or hides it (design 0011 §7).
- **Machine profile**: what Clank detected about the computer it runs on (operating system, GPUs and their memory,
  RAM, CPU). Kept in the local configuration, never in the repository.
- **Managed provider**: an engine plus a model plus launch options, run by Clank on this machine.
- **Mark**: what a Watch for rule leaves when it fires (a loop the guard stopped, a call made again and again, an
  approval waiting): on its node in the session's flow, in the Monitor's Watch for panel and beside "Monitor" in the
  menu, with what it rests on; the rule then does what the owner set (design 0012 §8). Seen once the owner opens it in
  the console (Enter on Watch for) or marks it seen on the phone.
- **Mode**: a readable file that says what an agent may do alone, must ask about, and may not do: plan, ask, auto, or
  the user's own (design 0002 §2.6; designed in M5).
- **Model**: a set of weights, in one or more file formats (GGUF, safetensors), with what it can do (tools,
  reasoning, vision) and where its files came from.
- **Monitor**: the console's page on F10 where the owner watches the local model's work in one OpenCode session, and
  guides it: three views, Flow, Session and Context, each made of panels; the machine column is hidden on it until F5
  shows it (design 0012, decision [0047](decisions/0047-the-monitor-is-a-menu-page-on-f10.md)). Not the machine column,
  whose code is still named `Monitor` until design 0011's R2 renames it.
- **Next flow**: the flow made from Clank's template once a flow's last gate is approved, with the brief its last
  INTEGRATE wrote (`NEXT.md`), linked both ways (`follows`, `next`); it never starts without the owner's answer to the
  question that asks, unless the flow's `next_flow` says so, and its first run copies the brief into its own brief's
  file (design 0013 §3, decisions [0058](decisions/0058-integrate-starts-the-next-flow.md) and
  [0091](decisions/0091-the-next-flow-is-made-when-the-last-gate-is-approved.md)).
- **Note**: a message of the owner's sent to a session while it works, stored at once and read by its next step, with
  the session's agent and model, beginning with what it is about ("About step 12, `bash pytest -q`: ..."); while a call
  waits for approval, the note rejects that call instead and is read as its answer. Not read when the run ended without
  it (design 0012 §9.3, decision [0054](decisions/0054-a-note-is-a-real-user-message.md)).
- **Operation**: anything that takes more than a moment (a switch, a trial, a download), run in the Clank service with
  its steps, progress and result, and reconciled after a restart of the service (design 0002 §2.4).
- **Owner**: in Clank's records, the person who directs its building and decides what the records leave open; in
  what Clank does, the person it works for on this computer, its user (whose clients act as `you`). The words Clank
  sends a model call that person "the user".
- **Page**: one screen of the console, opened from its menu: home, questions, history, Docker, the machine, operations,
  records, help. A component declares its own pages (design 0002 §2.1). See *planned entry*.
- **Panel**: a section of a console page, drawn as a box with its title set in its top border and, at the right of that
  border, a note; the panel that holds the focus draws its border in the style's `border-focused`
  (`clank/console/panel.py`, design 0001 §5.6, design 0011 §4). In flows, a box is a step of a flow (design 0013).
- **Permission**: the name of something an actor may or may not do, such as `git.push` or `model.send`, declared by
  the component that needs it (design 0002 §2.6).
- **Plan**: the step-by-step implementation plan of a milestone or of one of its steps, in `docs/plans/`; each step
  starts with a failing test.
- **Planned entry**: a page of the console's menu that a later milestone brings, shown in red with its milestone; it
  opens a page saying what it will do and where it is designed, until the milestone builds it.
- **Planning** (of a flow): the owner's talk with the model that builds a flow: a fresh OpenCode session on the
  workspace's window, sent to the planner with Clank's instructions (`prompts/build.md`), opened by `n` in the Flow
  view, `f` on This folder or `clank flow new`; from the console, beside it, never in its terminal (over SSH, `clank
  flow attach` in another terminal); one open in a workspace at a time, kept beside the flow's runs (`building.json`,
  its drafts' history and its latest draft, `draft.json`), and drawn in the Flow view while it is open (design 0013
  §15, decisions [0099](decisions/0099-the-planning-session-opens-on-the-workspaces-window.md),
  [0100](decisions/0100-a-planning-opens-beside-the-console.md) and
  [0101](decisions/0101-the-flow-view-shows-the-planning-while-it-is-open.md)). Not a *plan*.
- **Policy**: the one function that decides whether something may happen, from layers of rules: the floor, the
  workspace's bounds and rules, the mode, and grants (design 0002 §2.6).
- **Policy decision**: the policy's answer: *allow*, *ask* or *deny*, with the rule behind it and the file and line
  where that rule is written. It carries the policy's revision and an expiry (decision
  [0021](decisions/0021-policy-decisions-expire.md)).
- **Preset**: a saved, named combination of a provider, a model and launch options ("daily 262K", "fast 128K").
- **Proposal** (of a flow): a box that the model of a box at work proposes for its flow with `flow_propose_box`, a
  DECOMPOSE's tasks above all: checked when staged, then kept in a batch beside its try
  (`run-<n>/<box>/try-<k>/proposals.json`) with an id of its own (T1), waiting for the owner, who accepts it (it joins
  the flow's file, marked with its run and the box that proposed it), edits then accepts it, or rejects it, one by one
  or all at once; the run waits at that box until each is decided. *Auto-accept*, a flow setting off by default,
  accepts those that pass the checks at once, up to a cap in a run (design 0013 §9, decision
  [0064](decisions/0064-the-model-changes-a-flow-only-by-proposals.md)).
- **Provider**: anything that answers model requests: a managed engine with its model, or an endpoint.
- **Question**: something Clank asks the user and waits for: an approval, a choice, or an answer in words. Any client
  can answer it (design 0002 §2.5). A model *request* is something else: one call to a model.
- **Reach**: where an endpoint sends what it is given: `this-machine`, `my-servers` (a server of the owner's, such as
  a remote cluster's) or `cloud` (a cloud provider's API; design 0015 calls it `hosted`); a workspace's requests go
  only as far as its bound allows (design [0015](design/0015-endpoints.md) §10, design [0016](design/0016-cloud-models.md) §9, decision
  [0075](decisions/0075-where-a-workspaces-requests-may-go.md)).
- **Reasoning effort**: how hard a reasoning model is told to think, a line its chat template adds to the prompt
  (Qwen3.8: `low`, `medium` or `xhigh`; `xhigh` when a request sets none). It is not a limit: the *thinking budget*
  is, a count of tokens after which the engine cuts the thinking off (decision
  [0068](decisions/0068-the-frontier-preset.md)).
- **Recipe**: the readable file that says how to build or install a serving setup at its pinned version: prerequisites,
  exact commands per platform, where the result goes, how to verify it (design 0001 §7.4).
- **Record**: anything Clank manages, of a kind, with an id and a title: either settings or state (design 0002 §2.2).
- **Recording**: what a real program answered at one version, in each of its states, kept in
  `tests/fixtures/<adapter>/<version>/program.json` with made-up names; contract tests play it back (design 0001
  §8.3).
- **Remote**: the component that reaches the user away from the computer: the phone page, push alerts, paired devices,
  whether the user is away. Remote access is switched on and off by the user (decision 0012).
- **Request option**: a setting sent with each model request (temperature, top_p, top_k, thinking budget, maximum
  output). Changing one takes effect at the next request, with no restart.
- **Retrieval budget** (KVMem's `kvmem.budget`): the tokens of the context KVMem keeps on the GPU and attends to
  exactly. Past it, the context waits in system memory in blocks of 128 tokens, and the blocks most like the last user
  message are brought back; 0 means the whole context, attended exactly (design 0003 §4; "frontier 262K" keeps 57,344,
  [docs/models/frontier-262k.md](models/frontier-262k.md)).
- **Role**: what a request is for: the agent, a batch job, the companion, completion. Each role has its own sampling,
  decided in the console and applied by the gateway (decision [0004](decisions/0004-sampling-per-role.md)). A tool
  names its role as the model it asks for (decision [0008](decisions/0008-role-is-the-requested-model-name.md)); a
  name Clank does not know gets the role `default`.
- **Run** (of a flow): one time a flow runs, from its first box, kept as a readable file in Clank's home
  (`state/flows/<workspace>/<flow>/run-<n>/run.json`) beside each *try*'s first message and deliverables: where it is,
  what it waits for, and each box's state (waiting, running, done, failed, stale, skipped). One flow's run is active at
  a time; another started meanwhile is queued behind it (design 0013 §6, decision
  [0061](decisions/0061-the-runner-is-an-operation-per-box-in-the-service.md)).
- **Runtime**: the component of the Clank service that owns which providers run in which slots, the role sampling,
  switching, health and metrics. Called "the runtime service" before decision 0013 made it a component (decision
  [0006](decisions/0006-runtime-service-with-adapters.md)).
- **Sampling**: the request options that shape the model's choice of tokens (temperature, top_p, top_k, min_p, penalties)
  and its thinking (whether, and how many tokens). An engine has its own sampling defaults, which a preset may set as
  launch options (`sampling.temperature` and the rest, unset unless set: the *engine's own default*); a request's own
  fields win over them.
- **Sandbox**: a container that holds an agent program and only the folders its workspace names. It reaches nothing
  but its edge.
- **Serving setup**: a way of serving models: an engine adapter, the recipe to build or install the engine at a pinned
  version, and its validated launch profile. Plug and play: adding one changes nothing else (decision
  [0010](decisions/0010-serving-setups-are-plug-and-play.md)). The first: KVMem/llama.cpp, then llama.cpp (M2);
  NInfer RTX 5080 was the third until [decision 0034](decisions/0034-ninfer-is-retired.md).
- **Session's flow**: what one OpenCode session did, as the Monitor draws it: its steps (each an answer of the
  model, with its calls made at once), its subagents, the owner's messages and notes, its compactions, and its main
  branches (a Clank plan's steps, else the todo list's items, else the owner's messages). The service keeps one for
  every session its watchers see, each step paired with the gateway's request that answered it (design 0012 §6;
  `clank/components/agents/sessionflow/`). Not a flow of boxes (design 0013). The Monitor's Flow panel draws it as a
  tree whose branches open to the right (`clank/components/agents/console/flowchart.py`); a **dead end** is a call
  that failed after which the agent moved on (⊘), a **band** a compaction, holding what it folded.
- **Settings**: records the user decides (presets, roles, modes, workspaces), kept in readable JSON files (decision
  [0007](decisions/0007-settings-in-readable-files.md)).
- **Slot**: a seat for a model: `main` (the agent's model), `fast` (completion, short side requests), and so on. Each
  slot is served by one provider at a time; roles use slots.
- **Snapshot**: one frame of the console as text (`clank console --snapshot`); the console's tests compare frames with
  the snapshots checked in under `tests/console/snapshots/` (decision [0027](decisions/0027-console-snapshots-are-text.md)).
- **Spending limit**: an optional daily or monthly amount for cloud requests (`config/cost.json`); when reached, the
  gateway holds each new cloud request and the owner is asked to raise it (design [0016](design/0016-cloud-models.md) §11).
- **Stage** (of a flow, as the Flow view lays it out): one box, or a DECOMPOSE's tasks stacked as one fan; the stages
  read left to right in rows that wrap (decision [0093](decisions/0093-the-flow-view-lays-a-flow-out-in-rows-of-stages.md)).
- **Stale**: said of a box of a flow that has run when a box before it changed (its settings edited, or its
  deliverable no longer matching its fingerprint); nothing runs again on its own (design 0013 §8).
- **State**: records Clank keeps about what happens (what runs, sessions, questions, grants, operations, events), in
  one SQLite database that only the Clank service writes (decision
  [0014](decisions/0014-state-in-sqlite-settings-in-files.md)).
- **Step** (of a session): one assistant message of an OpenCode session: one model request, and what it answered (its
  reasoning, its text, its tool calls) and how it ended. The Monitor's flow is built of a session's steps, and its
  details show what context each step was given (design 0012 §6).
- **Style**: the console's look, as a settings file of named elements: its colors, each named for what it colors
  (`good`, `failed`, `quiet`, `planned`, ...), the data colors of a chart, the colors of named kinds, its marks and
  glyphs, its border and its spacing. Clank's own is `clank`; the owner's go in `CLANK_HOME/config/styles/`, and
  `config/console.json` names the one in force. The console's code and style sheet name only its elements
  (`$clank-good`), never a color (design 0011 §2, §3, §6).
- **Subagent**: a session another OpenCode session started with its `task` call, to do part of its work. Its model
  requests name their own session (`X-Session-Id`) and the session that started it (`x-parent-session-id`); the
  Monitor shows it inside its parent's flow, and the gateway's activity and live text of a session include its
  subagents' requests only when asked (`subagents=true`), so a subagent never takes its parent's last (design 0012 §3,
  revised 2026-10-19).
- **Switch** (of a slot): replacing what serves a slot by another preset, always by the same steps (plan, stop, start,
  health, measure), going back to the last configuration that worked when the new one fails (design 0001 §4.2, design
  0003 §6.1). A flow switches the main slot before a box whose preset it does not run, once no request is in flight on
  it and the owner's own session is idle (design 0013 §7, decision
  [0062](decisions/0062-a-preset-per-box-switched-in-before-it-starts.md)).
- **Test suite**: a file of checks run against a configuration in a trial: each check with its pass condition and
  what it measures (`smoke`, `speed`, `memory`, `context`, `quality`).
- **Tool hub**: the data-plane process every tool call passes through, to MCP servers that each run in their own
  container (or remotely).
- **Tool server**: an MCP server, run by Clank in its own container or reached remotely, and called only through the
  tool hub.
- **Trial**: a test run of a candidate configuration, headless, inside the Clank service; afterwards what ran before
  comes back, unless the user chose to keep the candidate and every test passed (decision
  [0009](decisions/0009-test-a-configuration-in-a-trial-run.md)).
- **Try** (of a box): one time a box of a flow runs, each in a new session with its own first message; a box has
  3 tries by default, and a failed try waits at a gate, as does a VERIFY's fail once the box it checks has used its
  tries (design 0013 §3, §5, §8).
- **Tunnel**: the owner's own `ssh`, run by Clank with a configuration file it writes, that forwards a port of this
  machine's loopback to a model server on a cluster's node, through its login host (design
  [0015](design/0015-endpoints.md) §5, decision [0072](decisions/0072-the-tunnel-is-openssh-with-a-config-clank-writes.md)).
- **Verdict**: what a VERIFY box of a flow gives with `flow_verdict` on the deliverable of the box it checks: *pass*,
  or *fail* with numbered findings, each one thing to fix, and the lines of the brief and of *accept when* it checked,
  each met or not with its evidence; kept on its try and as `verdict.md` (design 0013 §2, §9). A fail sends the box it
  checks back for its next try, handed the findings.
- **Watch for**: the Monitor's rules over each session's flow (a loop the guard stopped, the same call again,
  failures in a row, an approval waiting, a limit near), run in the service whether or not a console is open; what each
  does when it fires, mark it, pause the session, tell the phone or tell the model and go on, is set in
  `config/monitor.json` (design 0012 §8, decisions [0053](decisions/0053-watch-for-rules-run-in-the-service.md),
  [0082](decisions/0082-a-watch-for-action-that-cannot-run-tells-the-phone.md) and
  [0083](decisions/0083-notes-in-a-row-count-again-after-a-clean-step.md)).
- **Window**: what opens over a console page and closes with Esc: a question or a value shown whole (`v`, `?`), a
  choice to pick, a form, an MCP server's tools, a device's traffic; each is one panel (`WindowPanel`; the traffic
  window two), its border in the style's `border-focused` (design 0011 §7). Not Clank's VS Code window.
- **Workspace**: the folders an agent may see and work in, with its sandbox's settings. The user chooses which
  workspace an agent works in.
- **Workspace key**: the key each workspace's OpenCode sends to the gateway, by which the gateway knows the workspace
  and applies its bound (design [0015](design/0015-endpoints.md) §10, built for cloud models by design [0016](design/0016-cloud-models.md)
  §9).
