# Design 0012: the Monitor, watching and guiding the model

The owner (2026-10-18): "create a new section of the menu for Clank where we can explicitly monitor EVERYTHING the
local model is doing, similarly to the way that we have the prototype's monitor working, but this time it needs to be
entirely inside the CLI on a new tab on the left. The point is that I want to see the context window, how much context
is being stored, what the breakdown of different tokens in the context window is, how much we have left, I want to see
the tool calls, [a] flow-chart like diagram showing me what the model is actually doing, and so on. Ultimately, this
will be a place for me to help guide the model as well as just monitor the model". Of the first boards: "I really like
the individual boxes for each thing that you have. Right now, I really like A the most, keeping in mind that we will
need to change the Flow section quite a bit"; the flow "should be more of a branching out effect rather than just a
linear chart"; and of A: "This is looking perfect so far, but we also need to make sure that everything is lined up
properly as well as make sure that it is easy for me to navigate this."

**Status:** written 2026-10-18, every section *approved* by the owner the same day ("Approve all three", the remaining
Choices as recommended); nothing here was built before its section was approved ([AGENTS.md](../../AGENTS.md)). This design covers the menu page **Monitor**, its **Session** and **Context** views,
the **Watch for** rules and the **Guide**. The page's third view, **Flow** (the flow as the program, boards D1 to D4),
is [design 0013](0013-flows.md); the look every page takes (the colors, each section a panel drawn as a box, the style
file) is [design 0011](0011-the-consoles-look.md). The screens are drawn on the canvas *Clank model monitor*, copied
into [docs/design/boards](boards/README.md), and named here by their boards' titles and files: *A · Everything on one
screen* ([Main.dc.html](boards/Main.dc.html): the Session view, the owner's pick), *B · Steps first: the context at
each step* ([Steps.dc.html](boards/Steps.dc.html): its right half becomes a step's details), *C · The context window,
in detail* ([Context.dc.html](boards/Context.dc.html): the Context view) and *D · The flow chart, and guiding the
model* ([Flow.dc.html](boards/Flow.dc.html): its Watch for and Guide panels). The boards' figures are examples: where
one differs from the engine (the first block KVMem keeps is 128 tokens, not the 1,024 drawn), the engine wins. Where a
board and this design's words differ, the words are the rule and the board is drawn again (Claude's call,
2026-10-18). What this design rests on was read in OpenCode 1.19.0's source and in Clank's code on 2026-10-18; what
was read but not yet seen working is marked *to measure* and listed in §10. **Choice** marks what the owner decides,
each with a recommendation.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Approved 2026-10-18 |
| 2 | The page: its views, its panels and its keys | Approved 2026-10-18 |
| 3 | Which session the page follows, and which the Guide acts on | Approved 2026-10-18; revised 2026-10-19 with step 2 (what the gateway names; a session's subagents' requests only when asked) |
| 4 | The context window | Approved 2026-10-18; revised 2026-10-18 at the owner's request (whatever model is loaded) and comment (§4.7: where the figures come from); revised 2026-10-20 after a session failed at the context's limit (§4.1: the margin OpenCode is not told of, and a full context answered as an overflow); revised 2026-10-20 with step 12 (§4.2: how the estimate was built); §4.1 revised after approval 2026-10-29 (the owner's request: OpenCode told the whole most output above its own cap of 32,000, decision 0153) |
| 5 | Now | Approved 2026-10-18; revised 2026-10-19 with step 2 (§5.2: the tokens counted by kind) |
| 6 | The session's branching flow | Approved 2026-10-18; revised 2026-10-19 with step 6 (§6.3: how it is laid out, a band holds what it folds; §6.4: a fold opens for the newest node while it works); revised 2026-10-26 (§6.1: a flow whose server ended is not read again until a server answers on its port; a watcher started again reads its flows once it synced) |
| 7 | Tool calls and the live text | Approved 2026-10-18; revised 2026-10-19 with step 2 (the live text's route) |
| 8 | Watch for: rules the owner sets | Approved 2026-10-18 |
| 9 | The Guide | Approved 2026-10-18; revised 2026-10-20 with step 11 (§9.4: how the hold was built); revised 2026-10-20 with step 10 (§9.5 and §9.7: where undo cuts, its preview from the flow, the revert confirmed, what Drop refuses and estimates) |
| 10 | What must be measured before it is relied on | Approved 2026-10-18 |
| 11 | Build steps | Approved 2026-10-18 |
| 12 | Decisions to record | Approved 2026-10-18 |

## 1. What the owner gets

- **The Monitor**, a page of the console's menu on F10 (the owner's "new tab on the left"), with three views:
  **Session** (board A), **Context** (board C) and **Flow** ([design 0013](0013-flows.md)).
- **The Session view** follows one OpenCode session as it works, each subject in its own panel: the **context window**
  (how full it is, what fills it, how much is left before OpenCode compacts, what sits on the GPU), **now** (what the
  model does this second, against its budgets, and the loop guard), the session's **flow** as a branching chart (the
  owner's message, the plan's items, their calls, subagents, dead ends, the owner's notes), the **tool calls**, the
  **biggest items** in the context, what to **watch for**, and the **Guide**.
- **The Context view** opens the context window whole: each part with its items and its trend, the exact window on
  the GPU, the session's growth, and what could be freed.
- **Watch for**: rules over what the page sees (a loop the guard stopped, a call made again and again, failures in a
  row, a limit near, an approval waiting), each doing what the owner set: mark it, pause the session, tell the phone,
  or tell the model and go on.
- **The Guide**: stop now, a note the model reads at its next step, pause after this step, undo the last step,
  compact now, and drop an item from the context. Each says what it will do, in words and as the exact call; what it
  costs; and, when it cannot run, why. Each shows in the flow afterward, so the flow is also the log of the owner's
  guidance.
- **Nothing claimed that is not known.** An estimate is labeled an estimate. An inference (a dead end, a guessed
  match) says why it was made. What Clank cannot tell apart (a request waiting for the engine, or being read by it) is
  shown as both.
- **No stutter.** The page is on screen while the model writes. The owner (2026-10-13): "any stuttering or massive
  slowdown of my PC is not acceptable for the final product". So the page redraws at most four times a second, only
  what changed, and nothing while idle (§2).

## 2. The page: its views, its panels and its keys

**Name and key.** The page is **Monitor**, on **F10**. F11 is Windows Terminal's full screen. F10 is free in Clank and
in Textual; whether it reaches the console is *to measure*, and F12 takes its place if it does not. The menu sorts
F-keys as strings today, which would put F10 between F1 and F2 (`clank/console/app.py`); that is fixed so F10 follows
F9. The name "Monitor" already belongs to the machine column in the code (its class, id, action and tests,
`clank/console/monitor.py`): design 0011's R2 renames it `MachineColumn`, with F5's words "machine column", and its
key (F5) stays. Beside "Monitor" the menu shows ● in the "now" color while the followed session works, as the E boards
draw it, and the count of marks not yet seen (§8). The header gets a pill for the followed session's phase (board A:
"monitor: answering").

**Three views**, named in a row of tabs at the page's top (board D1): **Flow**, **Session**, **Context**. The page
opens on the view last shown, the Flow view the first time (revised 2026-10-22, decision 0130). Esc closes a window;
Backspace goes back from the Context view to the Session view, and from a session opened from the Flow view to its box
([design 0013](0013-flows.md) §12; revised 2026-10-22, decision 0129: Esc goes to the menu).

**Choice** (how the views are reached): (a) F10 again, on the Monitor, moves to the next view; Enter on the Context
window panel opens the Context view; Enter on a box of the Flow view opens its session (board D1); (b) the capitals
`S`, `C` and `F`, beside the panels' letters in small. Recommended: (a), since it needs no new letters, so none clashes
with a panel's letter or with the Guide's keys.

**The Session view** is board A, with board D's Watch for and Guide panels added (the **Choice** below). Its first line
names the session: OpenCode, the workspace, the session's title, its agent (build or planner), its steps and calls,
since when, whether the page follows the newest session or is pinned to this one (§3), and, for a session a flow
runs, the flow and its box. Under it, the panels (their border kind is design 0011's):

```text
┌─ Context window  c ────────────────────────────────────────────────────────────────┐
│ used of the window · left before OpenCode compacts · read from the cache           │
│ the bar by part · what each part holds · on the GPU exactly · its growth           │
└────────────────────────────────────────────────────────────────────────────────────┘
┌─ Now  n ─────────────────────┐ ┌─ Flow  f ─────────────────────────────────────────┐
│ phase · prompt · thinking    │ │ the session's branching flow                      │
│ output · speed · loop guard  │ │                                                   │
└──────────────────────────────┘ │                                                   │
┌─ Watch for  w ───────────────┐ │                                                   │
│ the newest marks             │ │                                                   │
└──────────────────────────────┘ │                                                   │
┌─ Guide  g ───────────────────┐ │                                                   │
│ . stop  p pause  m note      │ │                                                   │
│ u undo  k compact  x drop    │ │                                                   │
└──────────────────────────────┘ └───────────────────────────────────────────────────┘
┌─ Tool calls  t ──────────────┐ ┌─ Biggest in the context  b ───────────────────────┐
│ newest first                 │ │ the largest items, by estimate                    │
└──────────────────────────────┘ └───────────────────────────────────────────────────┘
```

**Choice** (Watch for and the Guide in the Session view): (a) two small panels under Now, as above: Watch for with its
newest marks; the Guide with its actions and their keys, each grayed with its reason when it cannot run, and the note
line while a note is written; Tool calls gives them its rows; (b) keys only, as board A draws it: the keys bar lists
the Guide's keys, a note opens a line at the page's foot, and marks show only in the flow. Recommended: (a). The owner
called board D's guiding "VERY MUCH what I have been having in mind", and a grayed action with its reason on screen is
what the transparency rule asks.

**Room.** In a terminal 160 columns wide, the page has about 88 columns beside the machine column and about 128
without it, so the machine column is hidden on this page by default (F5 shows it). Narrower, the two columns stack
(Now, Flow, Watch for, Guide, Tool calls, Biggest), and under about 70 columns the flow stacks its branches too (§6.3).
When rows are short, Tool calls and Biggest give up rows first, then Watch for (down to its newest mark); the Guide
keeps one line. Text never spills out of a panel: it wraps, the panel grows, or it is cut with "…" and shown whole one
key away (design 0011).

**Keys**, so that the page is, in the owner's words, "easy for me to navigate": the boards' keys, and none of the
menu's (the digits, `q`, `?`, the F-keys and Ctrl+P keep their meaning).

| Key | Does |
| --- | --- |
| Tab, Shift+Tab | The next or the previous panel; the focused panel has a blue border |
| `c` `n` `f` `t` `b` `w` `g` | Go to a panel: context window, now, flow, tool calls, biggest, watch for, guide |
| ↑ ↓ | Move in the focused panel's list or tree |
| ← → | In the flow, fold or open a branch (the flow's own keys come first; elsewhere they move as on every page) |
| Enter | Open what is highlighted: a node's details, a call, a part's items, a mark; on the Context window panel, the Context view |
| Esc | Back |
| `z` | The focused panel on the whole page, and back (board A's "the whole flow") |
| End | In the flow: back to now, following it |
| `l` | The live text (§7) |
| `s` | Pick another session, which pins it (§3); board A drew this on `p`, which pause takes |
| `.` `m` `p` `u` `k` `x` | The Guide: stop, note, pause or resume, undo, compact, drop (§9) |

**Board B** is not a view of its own: the flow already lists the steps. Its right half is a step's details, opened
with Enter on a node (§6.5).

**Redraws.** The page follows [design 0001](0001-runtime-and-console.md) §5.7: at most four redraws a second, only
the rows that changed laid out again, and nothing redrawn while idle. The spinner touches only its own cells, and the
note line's cursor does not blink (a blinking cursor redraws twice a second). What costs a `docker exec` is read only
while the page is on screen, every few seconds (§7). Whether the page on screen slows the model's decoding is *to
measure* (§10). **The pass mark** (Claude's call, 2026-10-18): the model decodes at 95% or more of its speed with the
page on screen, measured against the page off (design 0001 §8.7). If the page fails it, it takes these, in this order,
until it passes: redraw at most once a second; freeze the live text and the flow while the model writes, drawing them
at each step's end; draw the flow only when asked. The measurement runs on the fake engine first, then once on the
real one with the owner's go-ahead, before steps 2 to 6 are built on the page (§11).

**Where it lives.** The page belongs to the agents component, beside This folder (F4), in
`clank/components/agents/console/`. The session's flow is kept by the agents component in the service, so the phone
can show it later; the gateway's figures come through the service's API. The page takes over the live watching and
guiding planned for the menu's **Agents** (M5); **Sessions** (M3) stays the list of each slot's conversations, and
Enter on one opens it here. Every Guide action is also a command of `clank` (design 0001 §5.8), named in the plan.

## 3. Which session the page follows, and which the Guide acts on

**How Clank knows a session.** OpenCode 1.19.0 sends `X-Session-Id` with every model request, and also
`x-parent-session-id` for a subagent (its `session/llm/request.ts`). The gateway keeps every header in its records
(`clank/components/gateway/server.py`), and since step 2 of §11 (built 2026-10-19) its activity and its records
summary name each request's session and parent (`clank/components/gateway/sessions.py`). This was read in the code;
seeing it on the wire is *to measure*. One edge container serves every workspace,
so a request's address names neither a workspace nor a session: a request is joined to its session by the session's
id alone.

**Which server runs it** (Claude's call, 2026-10-18). A workspace's container may run several OpenCode servers: one
for each window, each `opencode serve` the phone starts, and a flow's own server ([design 0013](0013-flows.md) §5).
Each has its own event stream and its own run state. So Clank keys every session by its workspace, its server (its
port) and its id, as the bridge's actions and the routes `/agents/sessions/{workspace}/{port}/{session}/…` already do.
The watch reports which server runs each session; every Guide action goes to the server that runs the session; `s`
lists the sessions with their server; and a note to an idle session starts its run on the server that ran it.

**Choice** (which session the page follows): (a) the newest active root session of the console's folder (F4's
workspace), named in the session line, with `s` to pick another, which pins it until the owner picks "follow the
newest" again; (b) always the owner's pick; (c) the newest active session anywhere. Recommended: (a). When the folder
has no session, the page says so, and `s` lists the others, each with its server and its state.

- **Subagents** are inside their parent's flow. The `task` call that starts one names its session in its metadata
  (`metadata.sessionId`, OpenCode's `tool/task.ts`), and its requests carry the parent's id. Enter on a subagent opens
  its own flow, and the panels then show its context, its now and its calls; Esc returns to the parent. The bridge
  leaves child sessions out of its listing today (`clank/components/workspaces/image/bridge.py`); step 4 keeps them.
  So the gateway's activity and live text of a session are its own requests and its own last; they include those of
  the subagents it started only when asked (`subagents=true`), and a subagent's request never takes the place of its
  parent's last (revised 2026-10-19).
- **The Guide acts on the root session**, so Stop stops the whole tree; that a running subagent stops with it is *to
  measure*. A note to a subagent comes later; it is unmeasured.
- **The engine holds one conversation.** KVMem keeps one conversation at a time, and a request that shares no
  checkpoint with it resets its store. So what sits on the GPU belongs to the engine, not to a session: the Context
  window panel says whose conversation the engine holds, and marks when another session took it.
- **Requests without a session**, such as completion in VS Code, are not sessions; the Requests page (F7) shows them.
- **A session joined mid-run**: its earlier steps come from OpenCode's history, without the gateway's timings, and are
  marked "before Clank watched".

## 4. The context window

**Whatever model is loaded** (revised after approval, at the owner's request). The owner (2026-10-18): "when you are
building the context monitor, please make sure that this is generalized to the specific choice of the LLM that is
loaded since we will likely end up using different models for different purposes, so this should be built in a way
that will let allow us to generalize easily." So nothing in this section is written for one engine or one model:
every figure comes from the slot the followed session's requests go to (the gateway's route), through two
declarations Clank keeps per engine and per model.

- **The engine's context facts**, declared by its adapter (`clank/components/runtime/adapters/`) for a preset's
  options, by one method, `context_facts`: the window and the output limit (every engine); the thinking budget, when it
  has one; an exact-attention window and how it chooses what it attends (KVMem: its retrieval budget, its first block,
  its pick by likeness to the last user message; an engine without one attends its whole window, and "On the GPU
  exactly" says so); whether it can count tokens (upstream llama.cpp's `/tokenize` makes the parts exact; KVMem cannot);
  the fields in which it reports the cache and its timings (KVMem's `prompt_cache_hit_tokens`, llama.cpp's `timings`);
  and how it says the context is full. A fact an engine does not report is absent, and the panel says "not reported by
  this engine" in its place, never a number. A new engine brings its facts with its adapter; the Monitor does not
  change.
- **The model's template facts**, in its catalog entry (`clank/catalog/`): how its chat template renders earlier
  thinking (left out before the last user message, as Qwen's reference template does, or kept), how it renders tool
  calls (XML or JSON) and its reasoning markers; and its **calibration** for the estimate (tokens per character, by
  kind of part), measured once per model on synthetic requests (§4.2) and kept with its measurement. A model with no
  calibration uses a plain default, and the estimate says so.
- **Several models.** Each slot's model has its own facts, and a flow's box may load another preset for its session
  (design 0013 §7): the panels follow the slot and the model the session's requests reach, and when the slot switches,
  the panel says so and the window, the bar and the GPU line change with the next step.
- The figures in this section (262,144, 16,384, 36,864, 4,096, 15,000) are those of the preset "daily 262K" (KVMem
  with Qwen3.8-27B), as examples.

### 4.1 How full, and how much is left

- **The window**: the slot's context and output limit, from `GET /gateway/routes`
  (`clank/components/runtime/service.py`): 262,144 and 16,384 for the preset "daily 262K". Clank gives OpenCode only
  these two limits (`clank/components/agents/adapters/opencode.py`), the window less a **margin** kept free for one
  step's tool results: `context_margin` in `config/opencode.json`, 16,384 by default, at most a quarter of the window
  ([decision 0089](../decisions/0089-opencode-is-told-the-window-less-a-margin.md)). The panel shows the engine's
  window; only what OpenCode is told is smaller.
- **Used**: the last finished step's total, its prompt (cached tokens included) plus its answer: the figure OpenCode's
  compaction reads. It changes when a step ends, since the engine reports usage only at a request's end.
- **The compaction line.** OpenCode compacts when that total reaches the window it is told less the output limit
  (counted up to 32,000), here 262,144 − 16,384 − 16,384 = **229,376** tokens (OpenCode's `session/overflow.ts`), or
  when the engine reports that the context overflowed. *Revised after approval 2026-10-29 (the owner's request;
  decision 0153):* above 32,000 the whole output limit is counted: OpenCode caps an answer at 32,000 unless
  `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` says more, and Clank sets it to an output limit above 32,000 when OpenCode
  starts, so OpenCode both sends and keeps room for all of it (read in OpenCode 1.19.4's source, the image's version:
  `provider/transform.ts`, `session/llm/request.ts`, `session/overflow.ts`). **Left before OpenCode compacts** is
  229,376 less the used total. The step's tool results go with the next request unchecked, and KVMem refuses a prompt
  that with `max_tokens`
  passes its window: told the window itself (a line of 245,760), a session failed when a step ended 35 tokens under the
  line and its result of 1,206 tokens pushed the next request over. With the margin, the results of a step that does
  not compact fit, up to 16,384 tokens: one tool output as OpenCode cuts it (51,200 bytes or 2,000 lines) of code or
  prose is about 13,000 ([the measurement of
  2026-10-20](../measurements/2026-10-20-opencode-and-a-full-context.md)). KVMem's own refusal (a prompt plus
  `max_tokens` over its window: HTTP 400, "prompt + max_tokens exceeds n_ctx") is not worded so that OpenCode compacts:
  OpenCode 1.19.0 stops the session on it (read in its code and seen when it was run). So the gateway answers an
  engine's refusal of a full context, which each engine adapter knows by its words, as OpenCode reads an overflow (400,
  code `context_length_exceeded`, "the context was full: ..."; in a held request's stream, the shape OpenCode reads
  there), and OpenCode compacts and goes on; the record and the Requests page mark it `full`
  ([decision 0090](../decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md)).
- **What a compaction keeps**: a summary and the newest turns, up to min(15,000, max(2,000, a quarter of 229,376)) =
  **15,000** tokens (OpenCode's `session/compaction.ts`). *Revised after approval 2026-10-29:* that quarter is of the
  window told less the output limit counted up to 32,000, whatever the variable (OpenCode 1.19.4's
  `preserveRecentBudget` leaves it out). The panel can preview "after compacting: a summary and the
  last 15,000 tokens".
- **The bar** runs from the parts in use, through the free room to the compaction line, to the room kept beyond it:
  the margin for a step's tool results and the 16,384 kept for the answer. Turning OpenCode's `compaction.auto` off
  changes the rule; the panel then says so (Clank never does). Clank sets `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`
  itself, above 32,000, and the rule counts it (revised after approval 2026-10-29).
- **Read from the cache**: the share of the last prompt the engine had cached (the gateway keeps the engine's
  `prompt_cache_hit_tokens` in each record).

### 4.2 The parts, estimated

Nothing measures the parts today. The gateway's records keep only how many messages and tools a request had; KVMem
reports only totals, and it has no route that counts tokens (it serves `/health`, `/v1/models` and
`/v1/chat/completions`). So the parts are estimated in the gateway, from the request body it already parses: the
characters of each part, shared out so they add up to the engine's exact `prompt_tokens`. The parts, as boards A and C
draw them: the **system prompt**, the **tool definitions**, **your messages**, the **model's text**, **thinking sent
back**, **tool calls**, **tool results**, and loop text (§4.3).

- **Labeled.** The panel says "estimate" next to the exact total, and the Context view says how it is made.
- **Thinking sent back is real**: Clank tells OpenCode to send it back (`reasoning_content`). The reference Qwen
  template renders it only after the last real user message, so the estimate follows that rule; the template inside the
  model file Clank runs is *to read* (§10).
- **Known errors**: the template's own text is invisible, tool calls are rendered as XML, and code and prose differ
  in tokens per character. The estimate is calibrated on synthetic requests that differ by one part, so that the
  engine's own count gives that part's size. Its CPU cost on a 262,144-token request is *to measure*.
- **One pass per request**, with no engine work and no new dependency. Exact sizes need the engine patch of §4.4.
- **As built** (step 12, 2026-10-20, Claude's calls in [plan
  s22](../plans/s22-monitor-the-parts-and-the-context-view.md)): the gateway makes each request's **census** from the
  body it parsed (`clank/components/gateway/census.py`: each part's characters, the thinking before the last user
  message apart, the biggest items with their call ids, loop text by the guard's measure), off its event loop, and keeps
  it with the session's requests that ended; the service shares the characters out to the engine's own count
  (`clank/components/agents/estimate.py`), where the engine's figures are read by its facts and the model's template and
  calibration are known (decision 0067). An uncalibrated model counts every part alike by its characters, and the
  estimate says so. The census costs about 8 ms on a 262,144-token request, about 40 ms at the worst seen ([the
  measurement of 2026-10-20](../measurements/2026-10-20-the-estimates-cost.md)). The owner's message is said with the
  step that read it and a text with no call with the step after the call before it, when the flow says that step made
  none; an item the flow does not place has no step, never a guess. "The earlier reads of a file read again" (§4.6) are
  counted as the earlier results of any call made again with the same arguments, a file read again among them.
- Board C's "e exact counts: ask the engine to count each part" cannot be built as drawn, since KVMem has no counting
  route; exact counts would come with the patch, with every request.

### 4.3 Loop text

An answer the loop guard stops leaves the context: OpenCode leaves an answer that ended in an error out of every later
request (its `session/message-v2.ts`). So loop text that stays in the context is a repeat the guard does not catch (a
longer or reworded one, [decision 0040](../decisions/0040-the-gateway-stops-an-answer-that-repeats-itself.md)), which
runs to the answer's limit and is kept, as board B's step 22 was before the guard existed; or the same call made again
across steps.

**Choice** (what the bar calls loop text): (a) a part of its own, as boards A and C draw it, taken out of the part it
came from: a kept item that compresses as far as a loop over its whole length (the guard's measure and share,
`clank/components/gateway/loops.py`), the tool result that echoes it, and the third and later identical call in the
last twelve; (b) no part of its own, only a mark on the items. Recommended: (a), each item's details saying why it
counts.

### 4.4 On the GPU exactly

KVMem attends exactly 36,864 tokens on the GPU: 288 blocks of 128 tokens for "daily 262K" (its default budget in
`clank/components/runtime/adapters/kvmem.py`; [the measurement of
2026-10-15](../measurements/2026-10-15-kvmem-long-tool-results.md)). While the conversation it holds is at most that
long, all of it is there. Beyond that, the GPU holds the first block (128 tokens), the mandatory suffix (from the later
of where the cache matched up to and the last real user message) and blocks picked by their likeness to the last user
message; the rest waits in system memory and is attended only when picked.

- **The totals**, a small change. The stored size is the last request's prompt and answer. The panel shows how much of
  it is on the GPU and how much in system memory ("36,864 on the GPU · 115,797 in system memory"), and whose
  conversation it is (§3).
- **The budget may be smaller**: the pool's cap (`--kvmem-gpu-ratio`, 0.50 by default) can shrink it; whether it
  does for Clank's preset is *to measure*.
- **Board C's picks** (the first block, the newest, what was picked and from which parts) need the engine to report
  them. A small engine patch, estimated at tens of lines: once the window is fixed, the engine sends its token ranges,
  labeled, with the parts' exact sizes, in the usage chunk and in a comment at the stream's start. Per-block scores
  would need one more accessor.
- **What the owner learns from it**: every step since the owner's last message picks by that same message (board C),
  and a note changes what is picked (§9.3).

**Choice** (exact or estimated): (a) ship the estimate, labeled, then make one KVMem patch for the exact sizes and the
picks once the estimate's error is measured, under its own decision record; (b) the patch first; (c) KVMem's trace
mode (`KVMEM_TRACE`) and reading its log. Recommended: (a). The patch is a local change to keep up, and whether the
template's markers are single tokens is *to measure*. (c) is rejected: it is a debug mode of unmeasured cost that
prints nothing on some paths, and a log is not an interface.

### 4.5 Growth over this session

A spark in the panel (board A's "This session") and a chart in the Context view (board C's "Over this session"): the
total at each step, from OpenCode's own tokens per step (input with the cache, output, thinking), paged from the
session's history; marked where OpenCode compacted, where the loop guard stopped an answer, and where another session
took the engine. With the estimate, the chart is split by part. It is drawn with the console's `tall_spark`
(`clank/console/gauges.py`).

### 4.6 The biggest items, and what could be freed

- **Biggest in the context** (board A): the largest items by estimated tokens, each with what it is and its step. A
  tool result's `tool_call_id` equals OpenCode's call id, so each item maps to the part the Guide can drop (§9.7).
  Items already cleared are marked, and so are items inside the 15,000-token tail a compaction would keep.
- **Could be freed** (board C): the Guide's actions that would free room, each with what it frees and what it costs:
  the loop text, the earlier reads of a file read again, compact now. Enter on one opens its action.

### 4.7 The Context view

Board C, opened with Enter on the Context window panel: the totals and the bar across the page; **What is in it** (each
part: its tokens, share, items, the biggest, and its last ten steps); **On the GPU exactly** (§4.4); **Over this
session** (§4.5) with **Where the room went**; and **Could be freed**. ↑↓ moves through the parts, Enter lists a
part's items, `x` drops the highlighted item and `k` compacts.

The parts are the loaded model's: a model whose template has no thinking has no thinking part. A panel, **Where these
figures come from**, names the engine adapter's context facts (the window, the output limit, the exact window or none,
whether it counts tokens), the model's catalog entry (its template's parts) and its calibration, or says the model is
not calibrated, so a box on another preset shows its own figures (revised 2026-10-18 at the owner's comment on the
interactive prototype: "Make sure that this is generalized to other models that I may end up loading later").

## 5. Now

### 5.1 What the session is doing

The phase comes from two sources: the gateway, for its requests (`clank/components/gateway/activity.py`), and
OpenCode, for the session (`session.status` and the session's parts).

| The panel says | When | From |
| --- | --- | --- |
| waiting for its slot | the model is starting or switching (the gateway waits up to its hold, 300 s) | gateway |
| reading the prompt (or queued) | the request went to the engine, and nothing has come back | gateway |
| thinking · answering · writing a call | tokens arrive, by kind | gateway |
| waiting for its engine to start again | the engine broke off | gateway |
| running a tool | a call runs, with its title (`bash pytest -q`) | OpenCode |
| waiting for you | an approval or a question waits | OpenCode |
| retrying | attempt *n* of at most 5, the next in *t* seconds | OpenCode |
| compacting | OpenCode is summarizing the session | OpenCode |
| held | the Guide paused it (§9.4) | gateway |
| stopped by the loop guard | the answer repeated itself (§5.4) | gateway |
| idle | waiting for the owner | OpenCode |

**"Reading the prompt (or queued)"** is worded so on purpose. The engine sends nothing until it holds its lock, so a
request queued behind another looks the same as one being read; and its progress through the prompt appears only in
its log. The page never claims either.

### 5.2 Thinking and the answer against their budgets

The thinking is shown against its budget, 4,096 tokens; the answer against the output limit, 16,384, inside the
engine's generation reserve of 16,384 (`kvmem.py`). The gateway counted one token per streamed event, without
telling the kinds apart, though its live text was already split by kind; since step 2 (built 2026-10-19) it counts
each kind. With MTP drafting (3 tokens), one event may carry several tokens (*to measure*), so live counts say
"about" and are corrected from the answer's `completion_tokens` at its end. Usage has no separate count for thinking.

### 5.3 The prompt, and speed

- **The prompt**: how long the engine took to its first token. The prompt's size and the share read from the cache
  arrive with the request's end, so during a step the panel shows the previous step's.
- **What is being written**: the call whose arguments stream now (`bash python -m …`). Only the gateway sees them;
  OpenCode holds a call's arguments as `{}` until they are complete.
- **Speed**: the gateway's tokens a second (`per_second`), and a spark of it.

### 5.4 The loop guard

The loop guard is built ([design 0004](0004-working-in-a-folder.md) §2, decision 0040). It reads each streamed
answer's thinking, its text and each call's arguments. Every 128 characters it compresses a part's newest stretches
(2,000 and 8,000 characters of thinking and text, 2,000 of a call); when one comes to under 6% of its size, the
gateway closes its connection to the engine, which stops writing, and ends the stream with `model_looped`, in words
without numbers so that OpenCode does not retry it.

- **Its state**: on or off (the gateway's settings, applied when the gateway restarts); "watching · nothing repeats";
  and, from step 2, each part's newest share against the 6%.
- **Its stops.** OpenCode follows the same path as when the engine breaks off: it records an error and does not retry,
  the run ends, the session goes idle, and the stopped answer leaves the context (*to measure*). The panel says
  "stopped; the session is idle; that text is not in the context", with a note ready to go on (§9.3), unless a rule
  the owner set acts first (§8). Each stop is a node in the flow. The gateway's record keeps what repeated, over which
  stretch and how far it compressed, and the Requests page marks it `looped`.

## 6. The session's branching flow

### 6.1 Where its facts come from

- **OpenCode's events are the spine.** One step is one assistant message. Its parts are the step's start, its
  reasoning, its text, its tool calls (each with its id and state), the step's finish (tokens, cost) and patches
  (OpenCode's `session/processor.ts`). OpenCode's event stream (`GET /event`) already carries every session of the
  folder, children included: `message.updated`, `message.part.updated` and its deltas, `session.status`,
  `todo.updated`, `session.compacted`, and the permission and question events. Today the bridge's `watch` forwards
  almost none of it.
- **Joined to the gateway's requests** by session id (§3). A session makes one model call at a time, so its requests
  and its steps pair in order, and each answer's tool-call ids equal OpenCode's call ids, which confirms the pairing
  (whether KVMem streams an id with every call is *to measure*). The gateway gives what OpenCode cannot: the time to
  the first token, the speed, the live text, the loop guard's state, the engine's errors.
- **Forwarded** by the bridge's long-lived watch (design 0007 §4), coalesced; deltas only for the session the page
  shows, in batches.
- **Kept in the service**: a flow for every session the watchers see, each with a version. The console asks for what
  changed since its version, as `/gateway/live` serves text after an offset. When the service starts again, or
  OpenCode's server ends (its `server.instance.disposed` event) and starts again, a flow is rebuilt from OpenCode's
  history, a page of messages at a time (how they page is *to measure*). No database table at first. A flow is never
  rebuilt from the gateway's records, which hold each request's whole body again.
- **A flow whose server ended is left as it was** (revised after approval, 2026-10-26): it is neither read nor tried
  again until a server answers on its port again or its session is heard again, and the log says once that the window
  closed; a watcher started again has its flows read once it synced, which says which servers still run.

### 6.2 What branches

**Choice** (what a branch is): (a) the plan's items; (b) fan-outs, for calls made at once and for subagents; (c) side
lanes, for dead ends and undone steps; (d) other histories of the session (OpenCode's fork: a new session with no link
back, sharing the same files). Recommended: (a), (b) and (c) on one graph, and (d) later, since it needs a branch of
the files too (a git worktree, for instance).

- **The plan's items** (Claude's call, 2026-10-18). When the session carries out a Clank plan (`/implement`,
  design 0009 §5.1), they are the plan file's numbered checklist steps: stable, and ticked by the implementer, who
  works on the first not ticked. Otherwise they are the items of OpenCode's todo list: `todo.updated` carries the
  whole list each time, and its items have no ids, so they are matched across revisions by their text, and the page
  marks a match it guessed. A step joins the item that was in progress when the step started. Without either, the
  branches are the owner's messages and the runs of calls between them (board D).
- **Calls made at once** fan out from their step and join again at the next.
- **A subagent** is a branch of its own, from the `task` call that started it (§3), ending with what it gave back.
- **A permission ask** attaches to its call through the call's id.
- **The owner's note** joins as a node where it was read (§9.3).

### 6.3 How it is drawn

The owner asked for "more of a branching out effect rather than just a linear chart". As board A draws it: time runs
down, and the branches open to the right, joined by box-drawing lines (─┬─, ├─, └─, │) aligned in columns. The owner's
message is the root; the plan's items are its main branches; each item's calls open to its right, and a run of the same
tool folds into one node (`read ×3`) that opens to its calls. The marks and colors come from design 0011's style: done
✓ in green, now ● in orange, failed ✗ in red, planned ○ in the quiet color on a dotted line (┄), a subagent ◆ in violet,
the owner's note ✎ in yellow; calls by kind, reading in blue, running in yellow, editing in teal, MCP tools in violet
(board D), from the style's `calls` group, and the context's parts (§4.2) from its `parts` group (design 0011 §2). A
compaction is a band across the whole flow, everything above it folded. A step that left the context (it
ended in an error, as a loop guard stop does) is drawn apart from a step that was stopped and stayed.

- **Room**: about 88 columns beside the machine column, about 128 without it; under about 70 the branches stack under
  their node.
- **A pure function draws it**, `render(view, width, cursor, folds)`, returning lines of styled text, as the machine
  column's parts are drawn (`clank/console/monitor.py`). Textual's tree widget gives only an indented outline, not a
  fan-out.
- **Nothing spills**: a node's text is cut with "…" and shown whole in its details.
- **Ambiguous widths**: ●, ✓ and the box-drawing characters are narrow in most terminals and wide in some. The
  snapshot tests pin the alignment, and the style file (design 0011) can name plain marks for a terminal that draws
  them wide.
- **Built with step 6** (revised 2026-10-19, [plan s16](../plans/s16-monitor-the-renderer.md)): beside its
  children a node takes at most half the room and 40 columns, its words cut only while it keeps 24 (a long title
  cut reads well, a short label cut does not), else its children stand under it; a node's children stand under
  it too where fewer than 24 columns are left to its right. A compaction's band holds the branches above it, so
  folding the band folds them; what it folds stands under it, since it runs across the flow. A step's calls made
  at once are one node (`read ×3 at once`), a run of one tool another (`bash ×4`), and a group's sizes line up.
  The snapshots pin the layout at 128, 88 and 60 columns; whether its glyphs are one cell each in the owner's
  terminal is *to measure*.

### 6.4 Folds and dead ends

- **Folds**: a done item folds to one line; a run of the same tool folds (`bash ×4`); a call that failed and then
  passed folds as "2 tries"; everything above a compaction folds into its band. The item in progress is always open,
  and a fold that holds the newest node opens while that node works (revised 2026-10-19 with step 6: a run or a
  subagent at work stays in sight; a finished one folds). A failed call never folds into a run, so a failure stays
  in sight.
- **Dead ends**: a failure is a call in the error state, or a `bash` call whose exit status is not 0. It stays on the
  main line until the agent moves on, and only then becomes a side lane ending in ⊘.
- **Warnings per lane**, from the prototype's monitor: the same call three times or more in the last 12; four failures
  or more in the last 8; one file edited six times or more in the last 30 (§8).
- **Inferences say why.** A dead end, a guessed match of plan items, a repeat: each one's details say what it rests on.

### 6.5 Moving in it, and a step's details

↑↓ moves from node to node in time order, ←→ folds and opens, Enter opens a node's details, Esc goes back, `z` puts
the flow on the whole page, and End returns to the newest node and follows it (the cursor follows now until the owner
moves it).

A step's details are board B's right half: its request and its time; **the context it was given** (the bar by part,
its size and share of the window, how much it grew since the step before, the share read from the cache and how long
reading took); **what it answered** (its thinking against its budget, its text, its calls, how it ended); and **what
it added to the next step**, or that it left the context. In the details, `t` shows its thinking, `a` a call's
arguments and `r` the result, each as text with its size. A call waiting for approval opens with its diff and three
answers: approve, reject, or reject with a note (§9.3). A question opens with its options.

## 7. Tool calls and the live text

**Tool calls** (board A): newest first, each with its time, its tool, what it does (its title or arguments, cut) and
its result's size; a failed one in red. A call goes from pending to running (with its input and title; `bash` keeps
the last 30,000 characters of its output) to completed, or to error, which includes "Tool execution aborted" when it
was stopped (OpenCode's `tool/shell.ts`). The bridge's reply cuts a call's input to 400 characters and its output to
1,500; Enter on a call fetches it whole (`/session/:id/message/:mid`). Each such read is a `docker exec`, so the panel
reads only while the page is on screen, every few seconds, until the forwarded events (step 4) make it live.

**The live text** (`l`): a panel under the flow with the current request's thinking, text and call arguments as they
are written, from the gateway's live view. OpenCode keeps a part's text only at its start (empty) and at its end, so
the gateway is the only source of text as it is written, and of a step for a viewer who joins in the middle. The
gateway's live view followed only the newest request; step 2 (built 2026-10-19) ties each request to its session,
so the panel follows the session the page shows (`GET /gateway/live?session=`): its own requests, and with
`subagents=true` those of the subagents it started too, each naming its own session and parent (§3).

## 8. Watch for: rules the owner sets

Each rule is a pure function over a session's flow, run in the service whenever the flow changes, so rules act while
no console is open. Each **mark** shows on its node in the flow, in the Watch for panel and beside "Monitor" in the
menu, and `?` on it says what it rests on. What each rule then does is the owner's to set, in a readable settings file
(`config/monitor.json`, a settings kind with its schema, like every other):

- **mark** it, and nothing more;
- **pause** the session (§9.4);
- **tell the phone**: the phone page lists it with what waits ([design 0005](0005-the-phone.md) §6), and pushes it
  once push alerts exist ([decision 0012](../decisions/0012-the-phone-page-and-push.md));
- **tell the model and go on**: a note in the rule's words (§9.3), at most twice in a row for the same rule in a
  session; after that, the rule marks, pauses and tells the phone.

The loop guard leaves this to the Monitor; decision 0040: "Telling the model what happened and going on by itself is
the Monitor's to decide (a rule the owner sets), not the guard's."

| Rule | Fires when | Its facts | Default |
| --- | --- | --- | --- |
| Waiting for you | an approval or a question waits | OpenCode, today | mark, tell the phone |
| The engine broke off | the last request ended in the engine's error | the gateway, today | mark |
| The loop guard stopped an answer | a request ended `model_looped` | the gateway, step 2 | **Choice**, below |
| OpenCode asks about a repeated call | its `doom_loop` ask (build asks; the planner and explore refuse at once); unanswered, it stalls a run left alone | OpenCode, step 4 | mark, tell the phone |
| The same call again | the same call three times or more in the last 12 | the flow, step 5 | mark |
| Failing again | four failures or more in the last 8 | the flow, step 5 | mark |
| One file again and again | one file edited six times or more in the last 30 | the flow, step 5 | mark |
| A call ran, then its step failed | a step ended in an error after one of its calls had started: the file may have changed, and the model is not told | the flow, step 5 | mark |
| Stopped with an approval waiting | the session stopped while an ask waits: the ask stays, and a later "once" could still write the file (likely; *to measure*) | OpenCode, step 4 | mark |
| A note not read | a note was stored, and the run ended without reading it (a likely race) | the flow, step 5 | mark, with "send again" |
| OpenCode retrying | attempt *n* of at most 5 | OpenCode, step 4 | mark |
| Compaction near | the next step would likely pass the compaction line, at the last steps' pace | the flow, step 5 | mark |
| Thinking or answer near its budget | within a tenth of 4,096, or of 16,384 | the gateway, step 2 | mark |
| The engine taken by another session | another session's request reset the engine's conversation, so the next step reads it again | the gateway, step 3 | mark |

**Choice** (after a loop guard stop): (a) tell the model and go on, in words such as "Clank's loop guard stopped your
last answer because it repeated itself, and that answer is not in your context. Go on from where you were, without
writing it the same way again."; (b) mark and tell the phone, the session waiting for the owner. Recommended: (a), so
a run left alone goes on, with the cap above and the note's cost (§9.3) shown in the mark.

## 9. The Guide

### 9.1 What every action shows

The Guide acts on the session the page follows, its root (§3). In the Flow view, `p` pauses the flow, and a
session's guiding is one Enter away, in the Session view (design 0013 §12). Each action, in the Guide panel and in its
window, shows:

- when it can run, and when it cannot, grayed with the reason ("Undo stops the session first");
- its key, taken by the page itself;
- what it will do, in words and as the exact call to OpenCode or to the gateway;
- what it costs: the tokens to read again, and the time that takes at the engine's reading speed, measured from the
  gateway's records;
- a confirmation (Enter, or Esc to leave it), except Stop, which must be quick;
- its states (asked, running, done, or failed with the reason), in the Guide panel and in Now;
- an event in Clank's own events (`agents.acted`, with who did it: the owner from the console or the phone, or a
  rule), shown on the History page;
- a node in the flow afterward, so the flow doubles as the log of the owner's guidance.

| Action | Key | How | What it costs |
| --- | --- | --- | --- |
| Stop now | `.` | OpenCode's `abort` of the root session, and a reject of a waiting ask | nothing read again |
| Note | `m` | a real user message, read at the next step | what a new message makes the engine read again (*to measure*) |
| Pause after this step | `p` | the gateway holds the session's next request | nothing while held |
| Undo the last step | `u` | OpenCode's `revert`, and `unrevert` to redo | *to measure* |
| Compact now | `k` | OpenCode's `summarize` | a full reading of the history (*to measure*) |
| Drop an item | `x` | OpenCode's own clearing of a tool result | everything after the item read once (*to measure*) |

### 9.2 Stop now

- **How**: `POST /session/:id/abort` on the root session (a path the agents component already has), and a reject of
  one waiting ask of that session, after which OpenCode rejects all of the session's asks, so none is left for a later
  "once" to approve.
- **What it does**: OpenCode cancels the model request (the gateway sees its client leave) and marks the unfinished
  calls interrupted. A stopped step that has content stays in the history the model sees.
- **When**: while the session is busy, held, or waiting for an approval.
- **States**: stopping; stopped (the session idle); or failed, with the reason.
- **In the flow**: the stopped step marked ⊘ "stopped by you", its interrupted calls, and the asks rejected. Calls
  made at once may end some done and some interrupted.

### 9.3 A note

**Choice** (what a note is): (a) a real user message, which OpenCode shows; (b) hidden text OpenCode marks as its
own; (c) the request's `system` field; (d) text the gateway slips into the next request, which the history would never
show. Recommended: (a). (c) makes the engine read everything again (OpenCode's `session/llm/request.ts`), and (d)
breaks the transparency rule.

- **How**: `prompt_async` while the session is busy: the note is stored at once and read at the next step, and the
  run cannot end without answering it (OpenCode's `session/prompt.ts`). On an idle session, it starts a run, on the
  server that ran the session (§3). The bridge sends text only today, and OpenCode then falls back to the build
  agent, so a note would turn a planner session into build: step 4 sends the session's agent and model with it.
- **About**: the note begins with what it is about, the node under the flow's cursor ("About step 12, `bash pytest
  -q`: …"). The note line shows that, the agent it goes to ("planner") and when it arrives.
- **A call waiting for approval** offers "reject with this note" instead: the model reads it as the answer to that
  call and goes on, and no user message is added.
- **What it costs** (inferred, *to measure*): a new user message likely makes the template stop rendering earlier
  steps' thinking, so the engine reads again everything since the previous user message; and KVMem picks its GPU
  window by the last user message, so the note also changes what is picked (§4.4). The window shows the estimate before
  the note is sent.
- **States**: written; waiting (stored, not read yet); read by step *n*; answered. A note the run ended without
  reading (a likely race at a run's end) is marked, with "send again".
- **In the flow**: a yellow node like the owner's message, joined to the node it is about, with an arrow into the step
  that read it.

### 9.4 Pause after this step

OpenCode cannot pause, and it reads its rules only when a run starts. **Choice** (how pause works): (a) the gateway
holds the session's next model request; (b) Clank stops the run at the step's end (OpenCode's `abort` when the step
finishes), and a note continues it. Recommended: (a), since nothing is stopped, subagents can be held too, and
OpenCode's own terminal still shows the session working. (b) stays the fallback; it costs at most a reading of the
prompt already begun, and OpenCode shows it as a stop.

- **How**: `p` marks the session paused in the gateway. The request in flight finishes, OpenCode runs that step's
  calls, and its next request, and any of its subagents' (by `x-parent-session-id`), is held. The gateway answers it at
  once (200, an event stream) and sends a comment line well within every 300 s, since OpenCode gives up after 300 s
  without headers or bytes, and then retries (OpenCode's `provider/provider.ts`). That comment lines keep OpenCode
  waiting past 300 s is *to measure*.
- **Resume**: `p` again; the held request goes to the engine.
- **A note while held**: the gateway closes the held request (OpenCode drops that empty step), and the note is sent.
  The pause stays, and the request that carries the note is held until the owner resumes (the order is measured with
  the hold).
- **Errors**: once the 200 has gone out, an engine failure can only be told inside the stream, and OpenCode then ends
  the run without retrying unless the words match its retry patterns. The gateway words such an error on purpose.
- **The slot's own wait**: the gateway already holds a request up to 300 s without headers while its slot starts
  (`hold_seconds`), the same as OpenCode's limit; the hold's keep-alive serves that wait too.
- **Choice** (how long a hold lasts): (a) until the owner resumes; (b) up to a limit in the settings, then a stop at
  the step's end. Recommended: (a), measured for an hour first. The pause belongs to the session in the gateway, so a
  held request that a timeout broke is held again when OpenCode asks again.
- **States**: pausing after this step; held, with a timer; resumed. A compaction asked for while held waits too.
- **In the flow**: a band on the main line, "⏸ held by you 12:22 to 12:25".
- **As built** (step 11, 2026-10-20, Claude's calls in [plan s21](../plans/s21-monitor-pause.md); revised after
  approval, deciding nothing against the above): only the service sets a pause, with its local token, since the agent
  reaches the gateway through the edge ([decision 0084](../decisions/0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md));
  the pause is the root's (a rule's on a subagent pauses its root), and the gateway keeps each session's parent as its
  requests named it, so a subagent's subagent is held too; a request is held at the gateway's door, before its slot is
  woken or waited for, a comment line at once and then every 15 s; once resumed it is timed from then, its hold kept in
  its record (`held`); a note, any message sent through Clank, is sent first and then closes only the session's own
  request held before it was sent, never a subagent's (whose run an empty step would end), nor one held since, which
  may carry the note (the session was idle, or its step ended meanwhile) and stays held until the owner resumes; a
  request not streamed waits without headers; an error after resuming holds "unavailable", to be retried, when the same
  failure without the hold would have been answered with a 5xx or 429 status, and otherwise none of OpenCode's retry
  words; the pauses outlive a restart of the gateway (`state/holds.json`), and a gateway from before pausing, still
  running, refuses them in words that say to restart it. The hold is drawn on its step's line, before its work, and one
  a note closed says "until a note".

### 9.5 Undo the last step

- **How**: when the session is busy, Undo asks to stop it first (OpenCode refuses to revert while busy). Then `revert`
  at the last part of the previous assistant message (OpenCode's `session/revert.ts`): OpenCode restores the files
  changed after that point from its own snapshots, and deletes the later messages at the next prompt; until then,
  `unrevert` brings everything back. Reverting with only a message id would take back the whole turn, the owner's
  message included, so Clank always names the part.
- **The first step after the owner's message** (Claude's call, 2026-10-18): its previous assistant message comes before
  the owner's message, so undo is refused with the reason ("undoing it would take back your message too"), and **undo
  the turn** is offered: `revert` at the owner's message, which takes back the message and every step after it, and
  puts the message's text back in the note line.
- **Preview**: the steps and the files it will take back (`/session/:id/diff`).
- **What it costs**: the next request is shorter; whether the engine reads anything again is *to measure*. That it
  takes back exactly one step, files included (a `bash` call's too), is *to measure*.
- **Choice** (how far undo reaches): (a) the last step; (b) back to any step the owner picks in the flow. Recommended:
  (a) first; (b) is the same call at an earlier part, and can follow once (a) is measured.
- **States**: preview; refused for the first step after the owner's message, with the reason and "undo the turn";
  undone (grayed, "redo until your next message", `u` again redoes); the turn undone, its message's text back in the
  note line; final at the next message.
- **In the flow**: the undone step (or turn) a gray side lane, "undone by you", kept folded once final.
- **As built** (step 10, 2026-10-20, Claude's calls in [plan s20](../plans/s20-monitor-the-guide-part-2.md) and
  [decision 0094](../decisions/0094-undo-cuts-where-opencode-keeps-the-step-and-sends-the-revert-seen.md); revised
  after approval, deciding nothing against the above): the cut is the step before's last part only when a text or a
  call comes before it in that step, since OpenCode 1.19.0 turns a revert at any other part into one of the whole turn;
  a step before with neither is taken back too, and the preview lists every step. A note counts as the owner's message,
  since in OpenCode's order it comes before the step that read it, so that step is undone only as the turn, the note's
  words given back. Undo does not cross a compaction, and it is grayed while the session works ("stop it first"). The
  preview is read from the flow, not `/session/:id/diff`, which answers only an owner's message's turn: the steps, the
  files their patch parts list (what the revert restores), the owner's messages and the subagents those steps started
  (whose own sessions' files are not restored). The console sends the revert its window showed and what it said that
  revert takes back, and the service refuses one the session moved on from, or one that names none; OpenCode's answer
  is drawn at once, and when OpenCode cut elsewhere what it took back is read from the flow and said in a window. The
  words of every message of the owner's an undo takes back come back from the session's newest page of history, whole
  up to the bridge's cap (else the flow's, said cut), in a window of several lines, their line breaks kept, which Esc
  keeps for `m`. The undone lane says "u redoes" until OpenCode removes what it took back, then "final".

### 9.6 Compact now

- **How**: `summarize`, with provider `clank`, the role as the model, and `auto` on (OpenCode's
  `session/compaction.ts`). It has no busy check: the compaction happens at the next step, and the work goes on after
  it. The call blocks until the run ends, so the bridge does not wait for it (its calls time out after 10 s).
- **What it costs** (*to measure*): OpenCode's hidden compaction agent reads the whole history as text, which likely
  resets the engine's store; the next step reads the summary and the last 15,000 tokens. A compaction that itself
  overflows stops the run.
- **States**: asked; compacting (the summary streams in the live text); done.
- **In the flow**: the compaction band (§6.3), "by you"; OpenCode's own compactions draw the same band, "by OpenCode".

### 9.7 Drop an item

- **How**: OpenCode's own clearing of a tool result: an update of the part with its `state.time.compacted` set to now
  (OpenCode's `session/message-v2.ts`). From the next step the model reads "[Old tool result content cleared]" in its
  place, and the call stays. OpenCode's routes do not check whether the session is busy, so Clank refuses an item of
  the step in progress.
- **Not by the gateway.** Board D's words ("the gateway leaves it out of what the model is sent") are not built: the
  gateway never changes what OpenCode sends, so OpenCode's history and what the model reads stay the same.
- **Choice** (how far drop reaches): (a) clear tool results only, never delete; (b) also remove a call with its result
  (OpenCode's `DELETE` of the part), which board C's "drop the loop text" needs for the looping call itself.
  Recommended: (a); (b) only for an item the owner picks, with its own confirmation.
- **What it costs**: the tokens freed (estimated), and everything after the item read once (likely; *to measure*).
  Whether a cleared result can be brought back is *to measure*, so the window says the drop is final.
- **States**: preview; cleared.
- **In the flow**: the call's node marked "result cleared by you, −18.6K"; the Biggest panel and the Context view mark
  it cleared.
- **As built** (step 10, 2026-10-20, Claude's calls in [plan s20](../plans/s20-monitor-the-guide-part-2.md); revised
  after approval, deciding nothing against the above): `x` drops the call highlighted in Tool calls when that panel has
  the focus, else the one under the flow's cursor, and its window is read for that call. Besides the step in progress,
  it refuses a call not finished (one that failed has no result), one in a step undone, one in a step that left the
  context, and one before a compaction that summarized it, since the model no longer reads any of these. What it frees
  is the result's characters at the model's calibration for tool results, else 0.3 tokens a character (decision
  0087's plain estimate); what it costs is the session's last total less the prompt of the first step after the call's,
  or nothing when no step has read it yet; both are labeled estimates. The node says "result cleared by you, freed
  about 18.6K" once OpenCode says the result is cleared (an estimate, said as the Guide says it), and one OpenCode
  cleared itself says "result cleared". The Biggest panel and the Context view come with step 12, and mark it then.

## 10. What must be measured before it is relied on

With the owner's go-ahead: on the fake model or a scripted one, with synthetic sessions only, and opening no windows;
the GPU only when the owner says so. Each result is written up in [docs/measurements](../measurements/README.md), as
the loop guard's was.

| What | Why it matters | Before |
| --- | --- | --- |
| F10 reaches the console in Windows Terminal | the page's key (F12 if not) | step 1 |
| decoding speed with the page on screen, against the page off (design 0001 §8.7): on the fake engine, then once on the real one | no stutter: 95% or more passes (§2) | step 2 |
| OpenCode 1.19.0 sends `X-Session-Id` and `x-parent-session-id` on the wire | every join of §3 and §6 | step 2 |
| whether one streamed event carries several tokens with MTP drafting | the live counts (§5.2) | step 2 |
| whether the pool's cap shrinks KVMem's 36,864 for Clank's preset | the GPU totals (§4.4) | step 3 |
| whether KVMem's refusal of a full context makes OpenCode compact or fail (read and run 2026-10-20: it fails; the gateway's answer makes it compact, decision 0090) | the compaction line (§4.1) | step 3 |
| how OpenCode's messages page (`limit`, `before`) | rebuilding a flow (§6.1) | step 4 |
| whether KVMem streams an id with every tool call | pairing requests with steps (§6.1) | step 5 |
| that `model_looped` and an engine breaking off lead to no retry and a dropped step | §5.4 and §8 | step 8 |
| that a note is read at the next step, and the session keeps its agent | §9.3 | step 9 |
| the race of a note at a run's end | §9.3 and §8 | step 9 |
| Stop with an approval waiting, and Stop while a subagent runs | §9.2 | step 9 |
| what a note, a cleared item and a compaction cost in reading again | the costs every action shows (§9.1) | steps 9 and 10 |
| that undo takes back exactly one step, files included | §9.5 | step 10 |
| whether a cleared result can be brought back | §9.7 | step 10 |
| a hold past 300 s, and for an hour | §9.4 | step 11 |
| the chat template inside the model file, and whether its markers are single tokens | the estimate (§4.2) and the patch (§4.4) | step 12 |
| the estimate's CPU cost on a 262,144-token request | §4.2 | step 12 |
| the estimate's error against the exact sizes | whether the patch is worth keeping | step 13 |

## 11. Build steps

**Before any code.** This design's sections are approved (only approved sections are built); the decisions of §12
are recorded; each step has a plan in [docs/plans](../plans/README.md) before its code, and each task starts with a
failing test. No new dependency. The [glossary](../GLOSSARY.md) gets this design's words (Monitor, Guide, a session's
step, hold, a Watch for rule's mark) with step 1, and the [roadmap](../ROADMAP.md) lists the page. The research of
2026-10-18 named these steps M1 to M13, in this order; they are numbered here so they are not read as the roadmap's
milestones.

**Build order** (Claude's call, 2026-10-18). [Design 0011](0011-the-consoles-look.md)'s R1 (the style) and R2 (the
panel and the shell) come first, because the Monitor and the Flow view are built of its panels. Then these steps, then
design 0013's: its step 6, the Flow view, needs this design's page (step 1) and renderer (step 6). The bridge's
changes both designs need, `prompt` with the agent and the model and the watch reporting a session's status, are
built once, in step 4. **Decided by the owner (2026-10-18):** after R1 and R2, this design's steps, then design
0013's.

1. **The page itself**, built of design 0011's panels: the Monitor on F10, after F9; its three tabs; empty titled
   panels saying "no session yet"; the machine column hidden on it. Tests prove the menu's key order, that F10 opens
   the page (and moves between its views, if so chosen), its snapshots at 88, 128 and 60 columns, and that nothing
   redraws while idle. Then the measurement of §10 that the page does not slow decoding (§2), before step 2. *Built
   2026-10-19 ([plan s11](../plans/s11-monitor-the-page.md)); the measurement of §10 before it (F10 in Windows
   Terminal) and the one after it (decoding with the page on screen) wait for the owner.*
2. **Session facts in the gateway.** The session and its parent, from the headers, in the activity and the records
   summary; live counts by kind; the loop guard's newest share per part; each request's session for the live text.
   Tests prove that a request with a session id shows its session, that a subagent's shows its parent, that counts
   split by kind, and that a request without the header still works. *Built 2026-10-19
   ([plan s12](../plans/s12-monitor-session-facts.md)); the three measurements of §10 before it wait for the owner.*
3. **Context totals, for whatever model is loaded.** Each engine adapter's `context_facts` (§4), and the model's
   template facts and calibration in its catalog entry; the routes carry the slot's facts; the Context window panel
   shows used, left, the cache share, the GPU line and whose conversation the engine holds, from those facts only.
   Tests prove, with both fake engine styles (KVMem, and upstream llama.cpp): that 262,144 and 16,384 give 245,760;
   that under KVMem a stored size of at most 36,864 is all on the GPU, and above it 36,864 on the GPU and the rest in
   system memory, while under llama.cpp the GPU line says the whole window is attended; that a fact an engine does not
   report shows as "not reported by this engine"; that a model without calibration is labeled so; that a compaction
   keeps 15,000; that a slot switch to another preset changes the window at the next step; and that another session's
   request marks the engine as taken. *Built 2026-10-19* ([plan s13](../plans/s13-monitor-context-totals.md)): the
   engines' `context_facts` (`clank/components/runtime/adapters/`), the catalog's `template` and `calibration` (the
   Qwen3.8 models give the reference template's, none is calibrated yet), a preset's facts (`Runtime.facts`) in each
   slot's route; the gateway keeps each request's `preset`, `usage` and `timings`, and names each slot's newest request
   (`slots`); the totals are made in the service (`clank/components/agents/context.py`,
   `GET /agents/context/{workspace}/{session}`) and drawn by the panel (`contextpanel.py`). The engine is said to be
   taken only when its facts say it keeps one conversation (KVMem); llama.cpp may keep several. An engine that
   stopped, started again or was switched holds none, and a stream it broke off is not a finished step (the review's
   fixes, in the plan). The two measurements of §10 before it wait for the owner.
4. **The bridge.** Its watch forwards the Monitor's events, coalesced, children included, and deltas only for the
   session shown, and reports each session's status and the server that runs it; `prompt` sends the agent and the
   model (with the status, what design 0013 needs too, built once, here); new actions: reject a session's waiting ask,
   summarize without waiting, clear a part, revert and unrevert, page through messages. Tests run against a fake
   OpenCode replaying recorded synthetic 1.19.0 events (`tests/contract`, `tests/fixtures`), and prove that each kind
   is forwarded once per burst, that a planner session stays planner after a note, that summarize returns at once,
   and that, with two servers in one container, a Guide action reaches the server that runs its session and no other.
   *Built 2026-10-19* ([plan s14](../plans/s14-monitor-the-bridge.md)): the events are written by hand in the shapes
   read in OpenCode 1.18.31's program (its paging by `limit`, `before` and `X-Next-Cursor` among them), until they are
   recorded from 1.19.0 in the sandbox image.
5. **The flow in the service.** Tests prove that parts become a step with its fan-out; that task metadata becomes a
   subagent's branch; that a Clank plan's numbered checklist steps become the main branches, even beside a todo list,
   and a step joins the first not ticked; that, without such a plan, todo revisions become items matched by their
   text, a guess flagged; that, without either, the owner's messages and the runs of calls between them become the
   branches; that a compaction becomes a band; that a step that ended in an error is marked "not in the context" and
   a stopped one kept; that a note sent while busy is delivered at the next step; that N requests pair with N steps;
   that the console gets only what changed since its version; and that a session joined mid-run marks its earlier
   steps. *Built 2026-10-19* ([plan s15](../plans/s15-monitor-the-flow-in-the-service.md)): the flows are kept by
   `clank/components/agents/sessionflow/` and served at `GET /agents/flow/{workspace}/{session}?since=`; a step pairs
   with its request by the answer's call ids, else in order by time
   ([decision 0080](../decisions/0080-a-step-pairs-with-its-request-by-call-ids-else-by-time.md)); whether KVMem
   streams an id with every call, measured before this step, waits for the owner.
6. **The renderer.** Tests prove snapshots of board A's flow, calls made at once, subagents, a dead end, a compaction
   band and a note, at 88, 128 and 60 columns; that junctions align; folding; the current node; that nothing spills
   out of a node; and that only the rows that changed are laid out again. Over generated sessions (many steps, many
   calls made at once, subagents within subagents, long names), at those widths, no node, junction or label overlaps
   another and every line stays within the panel's width (the owner's comment on the prototype, 2026-10-18: "we need
   to be sure we are testing out edge cases"). *Built 2026-10-19* ([plan s16](../plans/s16-monitor-the-renderer.md)):
   the flow's tree (`flowtree.py`), its layout (`flowchart.py`, `render`) and the Flow panel's widget
   (`flowpanel.py`: ↑↓ a node, ←→ fold or open, End back to now, Enter its details); the page follows the newest
   active root session of its folder (`following.py`, §3's choice (a)) and reads only what changed. Picking
   another session (`s`), a session idle since the service started, and `z` come later (the plan says why).
7. **Now, tool calls, the live text, growth.** Tests prove the phase table; that the page never claims "queued"; that
   it reads through `docker exec` only while shown; that the spinner touches only its own cells; that, while the
   model writes, the page redraws no more than §2 allows (four times a second, or the fallback the measurement before
   step 2 called for); that live counts say "about" and are corrected at the end; and that the growth spark marks
   compactions and loop guard stops. *Built 2026-10-20* ([plan s17](../plans/s17-monitor-now-and-the-live-text.md)):
   what a session does now is made in the service (`clank/components/agents/now.py`,
   `GET /agents/now/{workspace}/{session}`) from the gateway's activity of the session, which now says each request's
   time to its first token, the kind of text it wrote last and the call being written, and from its flow; the Now panel
   (`nowpanel.py`) draws it, its spinner a cell of its own; the answer's line counts everything the model writes
   against the output limit, the thinking's its thinking against its budget, and once the answer ended the engine's
   count wins, the thinking's scaled to it, still "about". The Tool calls panel (`callspanel.py`) lists the calls from
   the flow, live since step 4, and Enter reads one whole through the bridge's new `part` action (`GET
   /agents/sessions/{workspace}/{port}/{session}/part/{message}/{part}`), the only `docker exec` the panel makes. `l`
   shows the live text (`livepanel.py`) across the page under the Flow's row, read from the offset held. The growth
   spark stands in the Context window panel; where another session took the engine is not marked yet (the plan says
   why). The page draws what its readings brought on the console's own redraw ticks (`Page.tick`), at most four a
   second, the rhythm being one constant should the measurement before step 2 call for once a second; the Now panel's
   spinner turns on those ticks too, and the session's work does not turn the console's own spinner. When rows are
   short, Tool calls gives up rows first (§2's room), and the loop guard is said as the running gateway applies it
   (§5.4), a change in its settings file said as waiting for its restart (the review's fixes, the plan's task 9). That
   measurement, and the one of several tokens an event, wait for the owner.
8. **Watch for.** The rules, their marks, the settings file, and "tell the phone". Tests prove that each rule fires on
   a synthetic flow and stays quiet on a clean one; that each mark says why; that each action follows its setting; and
   that "tell the model" stops at its cap. (Its note comes with step 9, its pause with step 11.) *Built 2026-10-19*
   ([plan s18](../plans/s18-monitor-watch-for.md)): the rules in `clank/components/agents/watchfor/`, run once a second
   over the flows that changed, with the facts of the agent role's slot (its route now carries the thinking budget);
   `config/monitor.json`, one field per rule; "in a row" counted again from the owner's own message and after a step
   that finished cleanly ([decision 0083](../decisions/0083-notes-in-a-row-count-again-after-a-clean-step.md)); the
   marks served
   at `GET /agents/marks` and in each flow's answer, the Watch for panel and the count beside "Monitor" drawn; a mark
   told to the phone listed with what waits, and an action that cannot run yet (the note, the pause) telling the phone
   instead ([decision 0082](../decisions/0082-a-watch-for-action-that-cannot-run-tells-the-phone.md)). The measurement
   of §10 before it (the loop guard's stop and an engine breaking off under OpenCode 1.19.0) waits for the owner.
9. **The Guide, part 1: Stop, Note, Compact now.** Tests against the fake OpenCode prove that the exact calls are
   sent; that a note carries the agent, the model and what it is about; that Stop rejects a waiting ask; that each
   action leaves an `agents.acted` event; and that an action that cannot run says why. *Built 2026-10-20*
   ([plan s19](../plans/s19-monitor-the-guide-part-1.md)): the Guide in the service (`clank/components/agents/guide.py`:
   what it offers, a pure function of the session's flow, its totals and the gateway's figures; its actions through the
   bridge, to the server that runs the session), `GET /agents/guide/{workspace}/{session}` and `POST .../stop`, `.../note`,
   `.../compact`; the Guide panel (`guidepanel.py`) and the page's `.`, `m` and `k`, the note's window naming the node
   under the flow's cursor, Compact now's asking first (`clank/console/confirm.py`). The costs are estimates until
   measured: a note, everything since the owner's previous message; a compaction, the whole history; the time, at the
   reading speed of the session's newest step that read enough anew (the gateway now keeps each request's time to its
   first token). A compaction the Guide asked for is drawn "by you". Watch for's "tell the model" now sends its note
   through the Guide, as the rule; a rule never rejects a call the owner may approve. The four measurements of §10 for
   this step wait for the owner.
10. **The Guide, part 2: Drop and Undo.** Tests prove that the step in progress is refused; that the update carries the
    whole part with `time.compacted`; that the revert cuts at the previous assistant message's last part; that undo
    of the first step after the owner's message is refused with its reason and offers "undo the turn", whose revert
    names the owner's message and puts its text back in the note line; and that unrevert works. Then the live
    measurements of §10. *Built 2026-10-20* ([plan s20](../plans/s20-monitor-the-guide-part-2.md)): the flow names
    where a revert at each step's end cuts (`cut`), the files its patches list, the revert pending and the steps it
    undid, kept `final` once OpenCode removes them, and a result the Guide cleared (`sessionflow/flow.py`); the Guide
    offers Undo (Undo turn, or Redo) and Drop with their previews, costs and states, and acts through the bridge
    (`Guide.undo`, `redo`, `drop`), `GET /agents/guide/{workspace}/{session}?item=` and `POST .../undo`, `.../redo`,
    `.../drop`; the page's `u` and `x`, their windows, the note window after the turn, and the marks in the flow
    ([decision 0094](../decisions/0094-undo-cuts-where-opencode-keeps-the-step-and-sends-the-revert-seen.md): where
    undo cuts, its preview, the revert confirmed). Its measurements, §10's and two the plan adds, wait for the owner.
11. **Pause, the gateway's hold.** Tests with a fake clock prove that a held request gets its headers at once and
    comment lines within the limit; that resuming forwards it; that a note closes the hold; that a subagent is held
    with its parent; and that an error after resuming is worded on purpose (retried or not). *Built 2026-10-20*
    ([plan s21](../plans/s21-monitor-pause.md)): the holds in the gateway (`clank/components/gateway/holds.py`, the
    hold at the door in `server.py`, `GET`, `PUT` and `DELETE /holds/{session}` and its release behind the service's
    token, decision 0084); the service's `pause`, `resume` and `GET /gateway/holds`; the Guide's pause on the session's
    root (`clank/components/agents/pausing.py`, `GET` and `POST /agents/guide/{workspace}/{session}/pause`,
    `POST .../resume`), listed after Compact now, `p` on the Session view asking first, a Watch for rule's pause through
    it; a message sent to a held session closing its held request; the hold in the flow, on its step's line. The
    measurement of §10 before it (a hold past 300 s, and for an hour) waits for the owner, with the order of a note and
    the release, and what OpenCode does with each error after a resume (the plan says what).
12. **The parts, the biggest items, loop text and the Context view.** Tests prove that, for a synthetic request with
    known parts, the shares add up to `prompt_tokens`; that earlier thinking is left out by the template's rule; that
    tool results map to their call ids; that loop text is found by the guard's measure over whole items; and the Context
    view's snapshots. *Built 2026-10-20* ([plan s22](../plans/s22-monitor-the-parts-and-the-context-view.md)): the
    census in the gateway and the estimate in the service (§4.2's "As built"), carried by the context totals (`parts`,
    and each step's `steps`); the Session view's Context window draws its bar by part with a line saying what each part
    holds (`parts.py`), and Biggest in the context lists the largest items with their steps and marks, Enter showing one
    whole (`biggestpanel.py`); the Context view (`contextview.py`, `contextgpu.py`, `contextchart.py`,
    `contextfreed.py`) shows the totals, What is in it (↑↓ through the parts, Enter a part's items), On the GPU exactly,
    Over this session (each step's size split by part), Where the room went, Could be freed (Enter on Compact now asks
    first, as `k` does there) and Where these figures come from, each at 128, 88 and 60 columns, what is shortened first
    said in each module. `x` there drops the item highlighted in a part's items or in Could be freed (and, on the
    Session view, in Biggest in the context) through step 10's Drop, by the Session view's own path. Of §10's
    measurements before it, the census's CPU cost was measured; the chat template inside the model file waits for the
    owner.
13. **Later, if the owner chooses: the KVMem patch** (§4.4), under its own decision record, and the gateway keeping its
    new figures next to usage. Tests prove that a regression test in KVMem's repository passes, that the gateway keeps
    the figures, that the page shows the exact GPU ranges and the parts' exact sizes, and the estimate's error against
    them.

## 12. Decisions to record

Numbered in this document's order, 0047 to 0056: after design 0011's 0041 to 0046 and before design 0013's 0057 to
0066 (Claude's call, 2026-10-18).

- **0047**: The Monitor is a menu page on F10 (F12 if F10 does not reach the console), with three views, Flow,
  Session and Context; the machine column is hidden on it by default; it takes over the live watching planned for the
  Agents page.
- **0048**: The page follows the newest active root session of its folder, known by OpenCode's `X-Session-Id`; a pick
  pins it; subagents are shown inside their parent; the Guide acts on the root session. A session is keyed by its
  workspace, its server and its id, and the Guide acts on the server that runs it (Claude's call, 2026-10-18).
- **0049**: A session's flow is built in the service from OpenCode's events, forwarded by the bridge's watch and joined
  to the gateway's requests by session; it is rebuilt from OpenCode's history on start, never from the records, and
  kept without a database table at first.
- **0050**: A branch is a plan item, a fan-out (calls made at once, subagents) or a side lane (dead ends, undone
  steps), all on one graph; other histories (forks) wait for a branch of the files. A plan item is a checklist step of
  the Clank plan the session carries out, else an item of OpenCode's todo list (Claude's call, 2026-10-18).
- **0051**: The context's parts are estimated in the gateway, characters scaled to the engine's own count, and labeled
  as estimates; exact sizes and the GPU picks wait for one KVMem patch under its own record; KVMem's trace mode and
  reading its log are rejected.
- **0052**: Loop text in the context is a part of its own: kept items that compress like a loop by the guard's
  measure, the results that echo them, and calls repeated.
- **0053**: "Watch for" rules run in the service over each session's flow, each doing what the owner sets (mark,
  pause, tell the phone, tell the model and go on), from a readable settings file; telling the model is capped.
- **0054**: A note is a real user message, sent with the session's agent and model and beginning with what it is
  about; a call waiting for approval gets "reject with this note"; never the `system` field, never text the gateway
  adds.
- **0055**: Pause is the gateway holding the session's next model requests, answered at once and kept alive with
  comment lines, until the owner resumes; a stop at the step's end is the fallback.
- **0056**: Undo takes back the last step, with a preview and a redo until the next message; for the first step after
  the owner's message it is refused, and "undo the turn" takes back the message too, its text put back in the note line
  (Claude's call, 2026-10-18); drop only clears tool results, by OpenCode's own clearing, never in the step in
  progress; the gateway never edits what OpenCode sends.
- **0067**: The Monitor reads every figure of the context window from the loaded slot: its engine adapter's declared
  context facts (`context_facts`) and its model's template facts and calibration in the catalog, never from one
  engine's or one model's numbers; a fact an engine does not report is shown as not reported (§4, revised at the
  owner's request, 2026-10-18).

## Revision log

- **2026-10-18, §4 revised after approval, at the owner's request:** "please make sure that this is generalized to the
  specific choice of the LLM that is loaded since we will likely end up using different models for different
  purposes". §4 now opens with the rule that every figure comes from the loaded slot's engine and model declarations
  (`context_facts`, the model's template facts and calibration); step 3 builds them and is tested with both fake
  engine styles; decision 0067 records it.
- **2026-10-18, §4.7 revised after approval, at the owner's comment on the interactive prototype:** "Make sure that
  this is generalized to other models that I may end up loading later". The Context view's parts follow the loaded
  model's template, and its panel **Where these figures come from** names the engine's facts, the model's catalog entry
  and its calibration (or says it has none). Step 12 builds it with the view.
- **2026-10-18, §11 step 6 revised after approval, at the owner's comment on the prototype:** the renderer's tests lay
  out generated sessions at every width and prove that nothing overlaps or leaves the panel ("we need to be sure we
  are testing out edge cases for dealing with this in practice").
- **2026-10-19, §3, §5.2 and §7 revised after approval, with step 2** (Claude's call after its review,
  [plan s12](../plans/s12-monitor-session-facts.md)): §3 and §5.2 say what the gateway now shows, each request's
  session and parent and its tokens counted by kind, without changing what they decide. §7 names the route
  the live text reads (`GET /gateway/live?session=`), and §3 says that a session's activity and live text are its own
  requests and its own last, its subagents' only when asked (`subagents=true`). The first build included the
  subagents' always; a subagent's request that ended after its parent's then took the place of the parent's own last
  (the previous step's prompt of §5.3, its text), against §3's rule that a subagent's panels show only after Enter on
  it.
- **2026-10-19, §6.3 and §6.4 revised after approval, with step 6** (Claude's call, [plan
  s16](../plans/s16-monitor-the-renderer.md)): §6.3's last sentence ("the layout has not been tried in a terminal
  yet") says how step 6 laid it out, without changing what it decides; §6.4 adds that a fold holding the newest node
  opens while that node works, and that a failed call never folds into a run, so a fold never hides work under way
  or a failure.
- **2026-10-20, §9.4 revised after approval, with step 11** (Claude's calls, [plan
  s21](../plans/s21-monitor-pause.md)): an "As built" item says how the hold was built (who may set a pause, the root's
  pause and subagents at any depth, where a request is held, a note's release and its order, a request not streamed,
  the words of an error after a resume, pauses across a restart of the gateway), without changing what §9.4 decides;
  [decision 0084](../decisions/0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md) records the first.
- **2026-10-20, §4.1 revised after approval, after a session failed at the context's limit** (Claude's call, on the
  owner's report; [the measurement](../measurements/2026-10-20-opencode-and-a-full-context.md)): OpenCode was told the
  engine's window, compacted after a step whose total reached 245,760, and sent the step's tool results with the next
  request unchecked; a step that ended 35 tokens under the line had its next request refused by KVMem (a prompt and
  `max_tokens` over the window), and the session stopped. OpenCode is now told the window less a margin for one step's
  tool results (`config/opencode.json`, 16,384 by default), so it compacts at 229,376; the Monitor shows the engine's
  window and that line. [Decision 0089](../decisions/0089-opencode-is-told-the-window-less-a-margin.md) records it.
  The same day, §4.1's question (§10) whether KVMem's refusal of a full context makes OpenCode compact or fail was
  answered, read in OpenCode 1.19.0 and run: it fails. The gateway now answers such a refusal as an overflow OpenCode
  compacts on, for what the margin does not hold (a step's results larger than it), and marks the request `full`;
  [decision 0090](../decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md) records it.
- **2026-10-20, §9.5 and §9.7 revised after approval, with step 10** (Claude's calls, [plan
  s20](../plans/s20-monitor-the-guide-part-2.md)): an "As built" item in each says how undo cuts (a step before with
  nothing OpenCode counts before its last part taken back too; a note as the owner's message; never across a
  compaction), that its preview is read from the flow rather than `/session/:id/diff` (which answers only an owner's
  message's turn in OpenCode 1.19.0), that the console sends the revert it showed and the service refuses one the
  session moved on from, and what Drop refuses and estimates, without changing what §9.5 and §9.7 decide; [decision
  0094](../decisions/0094-undo-cuts-where-opencode-keeps-the-step-and-sends-the-revert-seen.md) records the first three.
- **2026-10-20, §4.2 revised after approval, with step 12** (Claude's call, [plan
  s22](../plans/s22-monitor-the-parts-and-the-context-view.md)): an "As built" item says how the estimate was built,
  without changing what §4.2 decides: the gateway counts each request's characters by part from its body (its census),
  and the service shares them out to the engine's own count, where each engine's figures are read by its facts
  (decision 0067); an uncalibrated model counts every part alike, said so; the census's cost was measured; an item's
  step is the flow's, never a guess; and §4.6's earlier reads of a file read again are counted as the earlier results
  of any call made again with the same arguments.
- **2026-10-22, the views revised after approval, at the owner's requests** (decisions 0129-0130): Esc goes to the
  menu, Backspace back from a view to the one before; the page opens on the Flow view the first time.
- **2026-10-26, §6.1 revised after approval, after the owner's lag** (Claude's call): the service's log held over a
  thousand lines in a day saying that the history of two sessions whose OpenCode had ended could not be read
  ("Connection refused"), each reading tried again a little later, and all of them again each time the workspace's
  watcher started again (which a bridge from before the request channel made happen every minute or so, design 0023
  §4). A flow whose server ended (the watcher's `gone`, a `synced` that no longer lists its port, the bridge's answer
  that nothing listens there) is now set aside until a server answers on its port again (the watch's `server` line,
  any line naming the port) or its session is heard again, and the log says once that the window closed; a watcher
  started again has its flows read once it synced, not before; and a reading that keeps failing is said once.
- **2026-10-29, §4.1 revised after approval** (the owner's request to raise a cloud model's most output; decision 0153):
  OpenCode caps an answer at 32,000 tokens unless `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` says more, so Clank now sets
  it to an output limit above 32,000 when OpenCode starts. The compaction line counts the whole limit, as OpenCode then
  does; what a compaction keeps is still counted with 32,000, as OpenCode 1.19.4 counts it. Read in OpenCode 1.19.4's
  source, the image's version (plan s65).
