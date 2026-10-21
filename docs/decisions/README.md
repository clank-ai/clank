# Decisions

One file per decision: a choice between alternatives that someone will later ask "why?" about. Records are never
deleted or rewritten; a later decision supersedes an earlier one, and both say so. New records take the next number
and use the template below.

## Index

| # | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-clank-is-its-own-product.md) | Clank is its own product, in its own repository, with the prototype as its template | Accepted | 2026-10-11 |
| [0002](0002-design-principles.md) | The design principles | Accepted | 2026-10-11 |
| [0003](0003-one-terminal-console.md) | One terminal console both shows and controls everything | Accepted | 2026-10-11 |
| [0004](0004-sampling-per-role.md) | Sampling is set per role in the console and applied by the gateway | Accepted | 2026-10-11 |
| [0005](0005-textual-for-the-console.md) | The console is built with Textual | Accepted | 2026-10-11 |
| [0006](0006-runtime-service-with-adapters.md) | One runtime service with an adapter per engine | Accepted; refined by 0013 | 2026-10-11 |
| [0007](0007-settings-in-readable-files.md) | Settings, presets and the model catalog are readable files | Accepted | 2026-10-11 |
| [0008](0008-role-is-the-requested-model-name.md) | A tool names its role through the model name it requests | Accepted | 2026-10-11 |
| [0009](0009-test-a-configuration-in-a-trial-run.md) | A configuration can be checked, and tested in a trial run, before it is applied | Accepted | 2026-10-11 |
| [0010](0010-serving-setups-are-plug-and-play.md) | Serving setups are plug and play; the first are llama.cpp, KVMem and NInfer RTX 5080 as published | Accepted; NInfer retired by 0034 | 2026-10-11 |
| [0011](0011-agent-programs-are-plugged-in.md) | Agent programs are plugged in through adapters; OpenCode is the first | Accepted | 2026-10-11 |
| [0012](0012-the-phone-page-and-push.md) | Clank reaches its user's phone through its own page and push alerts, a service the user switches on and off | Accepted | 2026-10-11 |
| [0013](0013-one-service-control-and-data-planes.md) | One Clank service is the control plane; separate processes carry the traffic (refines 0006) | Accepted | 2026-10-11 |
| [0014](0014-state-in-sqlite-settings-in-files.md) | State lives in one SQLite database; settings stay in readable files | Accepted | 2026-10-11 |
| [0015](0015-kinds-defined-once-in-pydantic.md) | Each kind of record is defined once, in Pydantic; its schemas and types are generated from that definition | Accepted | 2026-10-11 |
| [0016](0016-fastapi-and-uvicorn.md) | The Clank API is built with FastAPI and served by Uvicorn | Accepted | 2026-10-11 |
| [0017](0017-one-server-sent-events-stream.md) | Clients follow one stream of Server-Sent Events | Accepted | 2026-10-11 |
| [0018](0018-deny-wins.md) | Policy rules combine by "deny wins": deny over ask, ask over allow, and no rule means deny | Accepted | 2026-10-11 |
| [0019](0019-components-use-declared-public-functions.md) | Components use one another only through declared public functions, checked by a test | Accepted | 2026-10-11 |
| [0020](0020-enforce-where-it-can-be-stopped.md) | Each permission is enforced by the part that can actually stop it | Accepted | 2026-10-11 |
| [0021](0021-policy-decisions-expire.md) | Policy decisions expire and name the policy's revision; the riskiest are made at the moment of use | Accepted | 2026-10-11 |
| [0022](0022-development-tools.md) | Development tools: uv, hatchling, pytest, Ruff and mypy | Accepted; its snapshot tool superseded by 0027 | 2026-10-11 |
| [0023](0023-click-for-the-command-line.md) | The `clank` command is built with click | Accepted | 2026-10-11 |
| [0024](0024-httpx-for-clients.md) | Clank's Python clients speak HTTP with httpx | Superseded by 0026 | 2026-10-11 |
| [0025](0025-psutil-for-the-machine.md) | The machine and its processes are read with psutil | Accepted | 2026-10-11 |
| [0026](0026-httpx2-replaces-httpx.md) | httpx2 replaces httpx as the HTTP client of Clank's Python code (supersedes 0024) | Accepted | 2026-10-11 |
| [0027](0027-console-snapshots-are-text.md) | The console's snapshots are text, made by the console itself (supersedes 0022's snapshot tool) | Accepted | 2026-10-11 |
| [0028](0028-the-vscode-extensions-tools.md) | The VS Code extension is TypeScript 7 tested with Node's runner; Clank's own tools write its types and package | Accepted | 2026-10-12 |
| [0029](0029-the-extension-is-tested-inside-vscode.md) | The extension is also tested inside a real VS Code, with @vscode/test-electron | Accepted | 2026-10-12 |
| [0030](0030-engines-run-on-hosts.md) | The service stays on Windows; engines run on hosts, WSL distributions first | Accepted | 2026-10-12 |
| [0031](0031-ninfer-follows-the-driver.md) | NInfer's version follows the CUDA the driver runs: v1.4 with CUDA 13.3.73 on this machine | Superseded by 0034 | 2026-10-12 |
| [0032](0032-engines-build-in-environments-of-their-own.md) | An engine is built in an environment of its own, under the host's Clank folder, without root | Accepted | 2026-10-12 |
| [0033](0033-clank-needs-nothing-from-its-prototype.md) | Clank needs nothing from the prototype, which is a template only; `clank import` removed | Accepted | 2026-10-13 |
| [0034](0034-ninfer-is-retired.md) | NInfer is retired: KVMem serves the model, and Clank stays built for other engines and models | Accepted | 2026-10-13 |
| [0035](0035-completion-runs-on-the-cpu.md) | Completion runs on the CPU: upstream llama.cpp's server and a small coder model, in the `fast` slot | Proposed | 2026-10-15 |
| [0036](0036-matplotlib-tests-figure-geometry.md) | Matplotlib is a development tool: the figure geometry is tested on real figures | Proposed | 2026-10-15 |
| [0037](0037-a-vision-model-on-the-cpu.md) | A model that reads images runs on the CPU, loaded on demand: Qwen3-VL 4B, in the `vision` slot | Proposed | 2026-10-15 |
| [0038](0038-plan-mode-is-an-opencode-agent.md) | Plan mode is an agent of Clank's in OpenCode, with its own rules | Proposed | 2026-10-15 |
| [0039](0039-notion-through-the-service-changes-reviewed.md) | Notion is reached by the service only, and the agent's changes are staged for the owner's review | Proposed | 2026-10-17 |
| [0040](0040-the-gateway-stops-an-answer-that-repeats-itself.md) | The gateway stops an answer that repeats itself: each part of a streamed answer read as it comes, stopped when its newest stretch compresses to under 6% | Proposed | 2026-10-18 |
| [0041](0041-the-consoles-look-is-a-style.md) | The console's look is a style: a readable file of named elements, loaded as a Textual theme | Accepted | 2026-10-18 |
| [0042](0042-only-clanks-styles-are-offered.md) | The console offers only Clank's styles; Textual's built-in themes leave the picker | Accepted | 2026-10-18 |
| [0043](0043-every-section-is-a-panel.md) | Every section of every page is a panel: one widget, drawn as a box with its title in its border | Accepted; for the windows, "never cut" superseded by 0081 | 2026-10-18 |
| [0044](0044-no-color-written-outside-a-style.md) | No color, and no mark of the style, is written outside a style file; a repository check refuses them | Accepted | 2026-10-18 |
| [0045](0045-text-never-spills-out-of-a-panel.md) | Text never spills out of a panel: prose wraps, a row is cut with "…" and shown whole by `?` | Accepted | 2026-10-18 |
| [0046](0046-the-keys-bar-shows-the-pages-keys-first.md) | The keys bar shows the page's own keys first, from one declaration of named actions per page | Accepted | 2026-10-18 |
| [0047](0047-the-monitor-is-a-menu-page-on-f10.md) | The Monitor is a page of the console's menu on F10, with three views: Flow, Session and Context | Accepted | 2026-10-18 |
| [0048](0048-the-monitor-follows-the-newest-session-of-its-folder.md) | The Monitor follows the newest active root session of its folder; a session is keyed by its server too | Accepted | 2026-10-18 |
| [0049](0049-a-sessions-flow-is-built-in-the-service.md) | A session's flow is built in the service from OpenCode's events, joined to the gateway's requests | Accepted | 2026-10-18 |
| [0050](0050-a-flow-branches-by-plan-items-fan-outs-and-side-lanes.md) | A session's flow branches by plan items, fan-outs and side lanes, all on one graph | Accepted | 2026-10-18 |
| [0051](0051-the-contexts-parts-are-estimated-in-the-gateway.md) | The context's parts are estimated in the gateway, labeled as estimates; exact sizes wait for a KVMem patch | Accepted | 2026-10-18 |
| [0052](0052-loop-text-is-a-part-of-its-own.md) | Loop text in the context is a part of its own | Accepted | 2026-10-18 |
| [0053](0053-watch-for-rules-run-in-the-service.md) | "Watch for" rules run in the service over each session's flow, each doing what the owner sets | Accepted; made exact by 0082 and 0083 | 2026-10-18 |
| [0054](0054-a-note-is-a-real-user-message.md) | A note to the model is a real user message, sent with the session's agent and model | Accepted | 2026-10-18 |
| [0055](0055-pause-is-the-gateway-holding-the-next-request.md) | Pause is the gateway holding the session's next model requests until the owner resumes | Accepted | 2026-10-18 |
| [0056](0056-undo-takes-back-the-last-step-drop-only-clears.md) | Undo takes back the last step, drop only clears a tool result, and the gateway never edits what OpenCode sends | Accepted | 2026-10-18 |
| [0057](0057-a-flow-is-a-chain-of-boxes.md) | A flow is a chain of boxes: only a VERIFY's fail line points back, and every loop ends at a gate once its box's tries are used; DECOMPOSE's tasks run one after another; other shapes wait for a later design | Accepted | 2026-10-18 |
| [0058](0058-integrate-starts-the-next-flow.md) | INTEGRATE's brief starts a next flow, linked to this one, after the last gate | Accepted | 2026-10-18 |
| [0059](0059-a-box-has-its-own-mode.md) | A box's mode (Plan, Review or Auto) applies to its own session; the workspace's mode to every other | Accepted | 2026-10-18 |
| [0060](0060-each-box-runs-in-a-new-session-on-the-flows-server.md) | Each box runs in a new session on the flow's own OpenCode server, without a terminal | Accepted | 2026-10-18 |
| [0061](0061-the-runner-is-an-operation-per-box-in-the-service.md) | The runner is an operation per box in the service; one flow runs at a time; gates, YOU boxes and proposals are questions; nothing starts again on its own after a change or a restart | Accepted | 2026-10-18 |
| [0062](0062-a-preset-per-box-switched-in-before-it-starts.md) | A box's model is a preset, switched into the main slot before the box starts, only while no request is in flight and the owner's own session in the workspace is idle; the owner's window is told its model changed | Accepted | 2026-10-18 |
| [0063](0063-verify-uses-the-preset-of-the-box-it-checks.md) | VERIFY uses the checked box's preset, in a fresh session, unless it names another | Accepted | 2026-10-18 |
| [0064](0064-the-model-changes-a-flow-only-by-proposals.md) | The model changes a flow only by proposals, accepted by the owner or by auto-accept within a cap; accepted boxes join the flow's file; a DECOMPOSE run again replaces only its tasks not started | Accepted | 2026-10-18 |
| [0065](0065-a-finished-box-goes-on-unless-a-gate-follows.md) | A finished box goes on by itself, unless a gate follows it or its *when done* waits | Accepted | 2026-10-18 |
| [0066](0066-a-flow-is-a-settings-file-in-clanks-home.md) | A flow is a settings file in Clank's home, its runs state beside it, copied into the folder on demand | Accepted | 2026-10-18 |
| [0067](0067-the-monitor-reads-the-loaded-models-facts.md) | The Monitor reads every context figure from the loaded slot's engine and model declarations, never one engine's numbers | Accepted | 2026-10-18 |
| [0068](0068-the-frontier-preset.md) | The frontier preset: Swift 1.5 at its template's own reasoning effort, thinking without a limit, the whole context attended exactly | Accepted | 2026-10-18 |
| [0069](0069-a-frontier-preset-over-262k-with-retrieval.md) | A second frontier preset keeps 262K of context: 57,344 tokens exact, the rest retrieved, a reserve for the longest answer; KVMem presets whose answers can outgrow the reserve are refused | Accepted; its sizes superseded by 0078, then restored by 0088 | 2026-10-18 |
| [0070](0070-a-docker-engine-adapter.md) | A Docker Engine adapter: Clank reports the engine's state, never wakes or starts it, and never runs sudo | Proposed | 2026-10-18 |
| [0071](0071-how-containers-reach-the-gateway-on-linux.md) | How containers reach the gateway on Linux: a socket only the edge mounts, or a guarded listener; never 0.0.0.0 | Proposed: the owner chooses | 2026-10-18 |
| [0072](0072-the-tunnel-is-openssh-with-a-config-clank-writes.md) | The tunnel is the owner's own OpenSSH, run with a configuration file Clank writes | Proposed | 2026-10-18 |
| [0073](0073-how-the-gateway-gets-an-endpoints-key.md) | How the gateway gets an endpoint's key: a process token, or the gateway reading the key's file | Proposed: the owner chooses; for cloud keys, 0106 proposes a third way | 2026-10-18 |
| [0074](0074-thinking-streamed-as-reasoning-is-read-too.md) | Thinking streamed as `reasoning` is read like `reasoning_content`; the stream reaches the tool unchanged | Proposed | 2026-10-18 |
| [0075](0075-where-a-workspaces-requests-may-go.md) | A workspace's requests stay on this machine until the owner widens its bound; each workspace has its own key, and each route a container reaches has its rule | Proposed: the owner chooses; for cloud models, answered by the owner's 0103 | 2026-10-18 |
| [0076](0076-an-endpoints-check-connects.md) | An endpoint's check connects: on a tunnel of its own, for the moment, with Clank's own made-up requests only | Proposed | 2026-10-18 |
| [0077](0077-an-endpoint-serves-the-main-slot.md) | An endpoint serves the main slot in an engine's place, or a slot of its own beside it | Proposed: the owner chooses; for cloud models, 0107 proposes (a) | 2026-10-18 |
| [0078](0078-frontier-262k-on-the-iq3-xxs-file.md) | "frontier 262K" runs the IQ3_XXS file with a 73,728-token window and a prompt batch of 256 | Accepted; superseded in part by 0088 (kept as "frontier 262K lean") | 2026-10-19 |
| [0079](0079-every-action-on-a-session-goes-to-the-server-that-runs-it.md) | Every action on a session goes to the server that runs it, the phone's too, with the session's agent and model | Accepted, as Claude's call | 2026-10-19 |
| [0080](0080-a-step-pairs-with-its-request-by-call-ids-else-by-time.md) | A session's step pairs with the gateway's request by the answer's call ids, else in order by time; the gateway gives a session's requests that ended | Accepted, as Claude's call | 2026-10-19 |
| [0081](0081-a-windows-long-title-is-cut-in-its-border-and-shown-whole-inside.md) | A window's title too long for it is cut in its border with "…" and shown whole as its first line (supersedes 0043's "never cut" for the windows) | Accepted, as Claude's call | 2026-10-19 |
| [0082](0082-a-watch-for-action-that-cannot-run-tells-the-phone.md) | A Watch for mark told to the phone is listed with what waits, not asked as a question; an action that cannot run (the note and the pause before their steps, or refused) tells the phone instead (makes 0053 exact) | Accepted, as Claude's call | 2026-10-19 |
| [0083](0083-notes-in-a-row-count-again-after-a-clean-step.md) | A Watch for rule's notes in a row count again from the owner's own message and from a step that finished cleanly after the rule's last note (makes 0053 exact) | Accepted, as Claude's call | 2026-10-19 |
| [0084](0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md) | The gateway's holds are set by the service, behind its local token | Accepted, as Claude's call | 2026-10-20 |
| [0085](0085-a-boxs-first-message-hands-the-brief-and-a-map-of-the-flow.md) | A box's first message hands the flow's brief and a map of the flow, before its task | Accepted (the owner's choice; the order and the map's lines, Claude's call) | 2026-10-20 |
| [0086](0086-a-box-hands-on-a-short-note.md) | A box hands on a short note, written in the folder and kept beside its try; a missing note is marked, not failed; a VERIFY is handed none | Accepted, as Claude's call | 2026-10-20 |
| [0087](0087-a-first-messages-size-is-counted-by-the-engine-else-estimated.md) | A first message's size is counted by the engine when it can, else estimated and said so; the check warns past a quarter of the window | Accepted, as Claude's call | 2026-10-20 |
| [0088](0088-frontier-262k-runs-the-iq3-s-file-again.md) | "frontier 262K" runs the IQ3_S file again, as decision 0069 sized it; the IQ3_XXS preset stays as "frontier 262K lean" (supersedes 0078 in part) | Accepted (the owner's decision) | 2026-10-20 |
| [0089](0089-opencode-is-told-the-window-less-a-margin.md) | OpenCode is told the engine's window less a margin for one step's tool results, 16,384 by default | Accepted, as Claude's call | 2026-10-20 |
| [0090](0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md) | The gateway answers an engine's refusal of a full context as an overflow OpenCode compacts on | Accepted, as Claude's call | 2026-10-20 |
| [0091](0091-the-next-flow-is-made-when-the-last-gate-is-approved.md) | The next flow is made from Clank's template once the last gate is approved, its brief copied in when it first runs, and the owner asked whether to run it now (how 0058 is built) | Accepted, as Claude's call | 2026-10-20 |
| [0092](0092-a-flows-server-reads-the-containers-one-configuration.md) | A flow's OpenCode server reads the container's one configuration, written for the main slot as it runs, until two servers each keeping their own is measured | Accepted, as Claude's call | 2026-10-20 |
| [0093](0093-the-flow-view-lays-a-flow-out-in-rows-of-stages.md) | The Flow view lays a flow out in rows of stages, from what the service says of it, and shows its boards on the page | Accepted, as Claude's call | 2026-10-20 |
| [0094](0094-undo-cuts-where-opencode-keeps-the-step-and-sends-the-revert-seen.md) | Undo cuts where OpenCode keeps the step (the steps with nothing before their last part taken back with it, the turn when the owner's message or a note comes first, never across a compaction), previews from the flow, and sends only the revert the owner saw (how 0056 is built) | Accepted, as Claude's call | 2026-10-20 |
| [0095](0095-clanks-flow-template-runs-on-frontier-262k.md) | Clank's flow template runs its boxes on "frontier 262K", the model the owner runs, so a new flow switches nothing | Accepted (the owner's decision); superseded for the shipped default by 0117 | 2026-10-20 |
| [0096](0096-the-census-keeps-no-prompt-text-when-records-are-off.md) | The census keeps no prompt text when the gateway's records are off: counts, kinds, tool names, sizes and places only | Accepted, as Claude's call | 2026-10-20 |
| [0097](0097-a-flow-is-built-by-talking-it-through.md) | A flow is built by talking it through: the model drafts it in a planning session (`flow_draft`), Clank checks it, answers its problems and warnings, and writes the flow's file | Accepted, as Claude's call | 2026-10-20 |
| [0098](0098-a-built-flow-runs-on-its-own-until-its-final-review.md) | A built flow runs on its own until its final review: auto-accept on, no gate but the last, no wait after any box (its first run included), its first YOU box done by the brief written with the model | Accepted (the owner's answers, built as Claude's call) | 2026-10-20 |
| [0099](0099-the-planning-session-opens-on-the-workspaces-window.md) | The planning session is started on the workspace's OpenCode window and shown there, the window started first in this terminal or in Clank's VS Code window; no OpenCode flag attaches a window to a session | Accepted, as Claude's call; for the console, revised by 0100 | 2026-10-20 |
| [0100](0100-a-planning-opens-beside-the-console.md) | Starting a planning from the console never takes its terminal: OpenCode runs beside it, in a second terminal with `clank flow attach`, a Windows Terminal pane, or Clank's VS Code window | Accepted (the owner's choice, built as Claude's call) | 2026-10-20 |
| [0101](0101-the-flow-view-shows-the-planning-while-it-is-open.md) | The Flow view shows the planning while it is open: its steps, the latest draft drawn and marked DRAFT, its session live | Accepted, as Claude's call | 2026-10-20 |
| [0102](0102-the-first-cloud-provider-is-openrouter.md) | The first cloud provider is OpenRouter, alone for now | Accepted (the owner's decision) | 2026-10-20 |
| [0103](0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md) | The cloud is agreed to once per provider and asked once per workspace; existing workspaces stay local; Notion and MCP servers marked local never go (answers 0075 for the cloud) | Accepted (the owner's decision) | 2026-10-20 |
| [0104](0104-cloud-cost-is-shown-with-an-optional-limit.md) | Each cloud request, session and flow shows what it cost; an optional daily or monthly limit pauses cloud requests until the owner raises it | Accepted (the owner's decision) | 2026-10-20 |
| [0105](0105-with-no-usable-model-the-console-opens-on-add-a-model.md) | With no usable model, the console opens on Add a model: cloud or local, in one pass | Accepted (the owner's decision) | 2026-10-20 |
| [0106](0106-the-service-hands-the-cloud-key-to-the-gateway.md) | The service hands a cloud provider's key to the gateway, behind its local token, while a cloud model is loaded (a third way beside 0073's) | Proposed (Claude's call) | 2026-10-20 |
| [0107](0107-a-cloud-model-serves-the-main-slot.md) | A cloud model serves the main slot in an engine's place, one provider at a time (0077's (a), for cloud models) | Proposed (Claude's call) | 2026-10-20 |
| [0108](0108-cloud-cost-is-openrouters-own-figure-kept-by-the-service.md) | Cloud cost is OpenRouter's own figure, kept by the service from the gateway's spool, in this computer's days and months | Proposed (Claude's call) | 2026-10-20 |
| [0109](0109-what-clank-sends-openrouter.md) | What Clank sends OpenRouter: the request as the tool sent it, the model's id, no data-keeping providers by default, the session's id for its cache, no attribution | Proposed (Claude's call) | 2026-10-20 |
| [0110](0110-the-gateway-never-sends-a-cloud-request-again.md) | The gateway never sends a cloud request again by itself; refusals reach the tool with their status, in words that say what to do and never OpenCode's retry words | Proposed (Claude's call); superseded in part by 0115 | 2026-10-20 |
| [0111](0111-local-only-content-is-kept-from-the-cloud-in-four-places.md) | Local-only content is kept from the cloud in four places: the agent's configuration, the gateway's Notion route, the tools it passes on, and each cloud request's history and session | Proposed (Claude's call) | 2026-10-20 |
| [0112](0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md) | A workspace is asked before its agent starts with a cloud model loaded, and a request that reaches the gateway first is held while it asks | Proposed (Claude's call) | 2026-10-20 |
| [0113](0113-an-event-says-whether-it-needs-the-owner.md) | An event type says whether its events need the owner's attention, and each event carries it | Proposed (Claude's call, on the owner's instruction) | 2026-10-21 |
| [0114](0114-a-questions-option-may-ask-for-a-number.md) | A question's option may ask for a number, with its bounds and unit, checked when it is answered | Proposed (Claude's call, on the owner's instruction) | 2026-10-21 |
| [0115](0115-a-refusal-not-to-retry-is-never-answered-with-a-status-opencode-retries.md) | A refusal OpenCode must not retry is never answered with a status it retries by | Proposed (Claude's call, at the review of plan s34); supersedes 0110 in part | 2026-10-21 |
| [0116](0116-the-public-release-generalizes-personal-and-research-details.md) | The public release generalizes personal and research details in earlier records | Accepted | 2026-10-21 |
| [0117](0117-a-new-flow-runs-on-what-the-main-slot-runs.md) | Clank's flow template names no model: a new flow runs on what the main slot runs (supersedes 0095 for the shipped default) | Accepted | 2026-10-21 |
| [0118](0118-clank-is-licensed-under-the-agpl.md) | Clank is licensed under the AGPL-3.0 | Accepted (the owner's decision) | 2026-10-21 |
| [0119](0119-sampling-and-gpu-layers-are-launch-options-left-unset.md) | An engine's sampling and its GPU layers are launch options, left unset unless a preset sets them, and shown with the engine's own defaults | Accepted (the owner's request; Claude's call how) | 2026-10-21 |

## Template

```markdown
# NNNN. <The decision, as a short sentence>

- Status: Proposed | Accepted | Superseded by [NNNN](NNNN-....md)
- Date: YYYY-MM-DD
- Decided by: <who, and how: e.g. the owner's answer to "<the question asked>">

## Context
<What made a decision necessary; the facts that bear on it.>

## Decision
<What was chosen, stated so it can be checked.>

## Alternatives considered
<Each option that was on the table, and why it was not chosen.>

## Consequences
<What follows: what becomes easier, what becomes harder, what must now be done.>
```
