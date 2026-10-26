# Design 0025: Clank for iPhone (M9)

An app on the iPhone's Home Screen that talks only to the owner's PC, through their tailnet: installed once from a QR
code, paired for as long as it is used, live from one stream, and heard from when something waits.

The owner asked for it on 2026-10-21 ("something much closer to a full phone application instead of having to go to a
link every time") and chose an installed web app over a native one. The design canvas "Clank for iPhone" (22 boards:
the parts and how they connect, installing, notifications, the offline screens, and every screen of the app, each
interactive) was drawn that day and approved in the owner's words ("honestly looking perfect"). This document writes
the canvas down, so it can be built from, and makes the choices the canvas left to confirm (§10). It builds on design
0005 (the phone page, the session bridge, the outbox, pairing, the console's Phone page), decision 0012 (Clank's own
page and push alerts, a service the owner switches on and off) and design 0023 §3 (the conversation stream).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What it is, and what leaves the PC | Approved 2026-10-21 (the canvas); written 2026-10-26 |
| 2 | Install once | Approved 2026-10-21 (the canvas); written 2026-10-26; built 2026-10-26 ([plan s57](../plans/s57-the-phone-app.md)): the pair link's QR on the console, the code spent by scanning it, the install claim, tokens renewed on use |
| 3 | Live: one stream, and when it drops | Approved 2026-10-21 (the canvas); written 2026-10-26; built 2026-10-26 ([plan s57](../plans/s57-the-phone-app.md)): the stream, the shell and its service worker, the reconnecting and offline screens |
| 4 | Notifications | Approved 2026-10-21 (the canvas); written 2026-10-26; its dependency decided when built |
| 5 | Now | Approved 2026-10-21 (the canvas); written 2026-10-26; built 2026-10-26 ([plan s57](../plans/s57-the-phone-app.md)) on the live stream; the Flows tab shows the flows' questions until step 2 brings the Flow view |
| 6 | Flows: the list, a flow, building one, a gate | Approved 2026-10-21 (the canvas); written 2026-10-26 |
| 7 | A session, the Guide, its context | Approved 2026-10-21 (the canvas); written 2026-10-26 |
| 8 | Work and Files | Approved 2026-10-21 (the canvas); written 2026-10-26 |
| 9 | More: activity, models, cost, settings | Approved 2026-10-21 (the canvas); written 2026-10-26 |
| 10 | Choices made since the canvas | Proposed 2026-10-26 (the owner may change any) |
| 11 | Order of work | Proposed 2026-10-26; step 1 built 2026-10-26 |

## 1. What it is, and what leaves the PC

- **The app** is Clank's phone page made into an installed web app (a PWA: Add to Home Screen, full screen from its
  own icon, a service worker for its shell and its notifications), not a native app: it installs from the PC itself,
  updates with Clank, and needs no store. It holds one device token, renewed on each use.
- **The way in** stays design 0005 §4's: the iPhone's Tailscale app joins the tailnet; the phone listener (`:7721` on
  the PC, published by `tailscale serve` as `https://<machine>.<tailnet>.ts.net:8445`) pairs devices, keeps their
  tokens, serves the app and its live stream, and logs every exchange (§5 of design 0005: both ends see everything).
  Nothing of the app is fetched from elsewhere.
- **What the app draws** is only what the PC sends: events with short titles in Clank's words, states, numbers, and
  questions with their options. It keeps on the phone only its device token and the last Now summary (names and
  numbers) for the offline screen.
- **What leaves the PC**: to the iPhone, through the tailnet, the live stream and what the owner opens; to Apple's push
  service, one push per event flagged for attention, encrypted for this iPhone (RFC 8291), at the detail the owner
  chose, so Apple sees when and how big, not what; to Tailscale's servers, nothing of Clank's. With pushes off, nothing
  leaves the tailnet. **Never**: files and their text, conversations, reasoning, tool output, briefs, plans, reviews,
  the notes the owner sends, research notes, cloud keys, the tailnet's keys.
- **Requirements**: iOS 16.4 or newer (web push, Home Screen apps only); Safari to add it; the Tailscale app on the
  iPhone, on the same tailnet, on while Clank is used; MagicDNS and HTTPS certificates on in the tailnet; the PC awake
  with Clank serving and the phone listener on; for pushes, the PC may reach Apple's push service (outbound HTTPS).

## 2. Install once

About a minute, nothing to type.

1. **The console shows a QR** (Phone, F9, `p`): a link to the listener's address that carries a one-time **pair
   code**, single use, ten minutes; `r` makes a new one, `d` lists the devices. `clank remote pair` prints the link.
2. **The camera opens it** in Safari, on the tailnet (Tailscale must be on). The page pairs the device by the code in
   the link (no typing), spends the code, and shows the steps for the iOS version it sees: Share, Add to Home Screen,
   keep *Open as Web App* on if shown, Add. Why: full screen, its own icon, notifications (iOS sends them only to Home
   Screen apps), and it stays paired.
3. **Clank's icon** on the Home Screen: its start link carries a one-time **install claim** (single use, good until the
   first launch or one hour), because iOS keeps a Home Screen app's storage apart from Safari's; the first launch
   trades the claim for the device's token and opens paired, full screen, live, with no code.
4. **Notifications, if the owner wants** (§4): asked only after they tap *Turn on* (iOS needs a tap); they choose how
   much a notification says.

**Staying paired**: the app holds one device token, a cookie only the PC reads; each use renews it; after thirty days
unused it lapses (design 0005's 90-day ceiling is dropped: a device in use stays paired). Revoke it on the console (F9,
`d`) or in the app (More, Settings, Sign out). **When a step fails**: QR expired, `r` on the console; the page does not
load, turn on Tailscale on the iPhone; opened in Safari but never added, the claim lapses after an hour, scan a new QR.

## 3. Live: one stream, and when it drops

- **One live stream of events** (server-sent, the listener's `/api/stream`), in place of asking every two to eight
  seconds: the kernel's events with their titles and an attention flag, the model's state and speed, the sessions
  working and waiting, the operations running, and the flows' changes; after a drop it resumes from the last event it
  saw (`Last-Event-ID`). A session screen (§7) reads the conversation stream (design 0023 §3) through the listener,
  so the words arrive as the model writes them.
- **When the stream drops**: the app keeps the last state on screen, dimmed, with its age ("Live updates paused 0:14.
  Below: as of 14:32"), retries every five seconds and resumes from the last event, so nothing is missed. After thirty
  seconds it shows **Can't reach the PC**: whether this iPhone is online, that the address did not answer (how many
  tries, the last when), what to check (Tailscale on this iPhone: open it and see *Connected*; the PC asleep or off:
  the app cannot wake it), *Try again* with the next try's countdown, and *Last known* (when, how long ago; the flow
  running, what waits, the model loaded): names and numbers only, kept on the iPhone.
- **The launch screen** says "connecting to the PC, through your tailnet"; the icon is the console's ◆ in orange over
  a blue cursor on the console's ground, served by the PC (iOS rounds the corners); the same mark sits beside every
  notification.

## 4. Notifications

iOS web push (decision 0012), sent only to the Home Screen app, each an event flagged for attention; its text is the
event's own title in Clank's words (flow, box, workspace, model), never what is in files, conversations or notes.

- **Levels**, one for all kinds, set per device (More, Settings): **Quiet** ("Something waits for you", "A flow
  finished"), **Names** (the default: "Final review waits · paper-1", "OpenCode asks a permission · paper"), **Names +
  numbers** ("Final review waits · paper-1 · 4 files, 3 verdicts"). Session titles are never in a push.
- **Kinds**, each on or off: gates and questions (a gate waits; OpenCode asks; Clank asks); flows end, stop or a box
  runs out of tries; a cost limit reached; a model failed; operations finished (off unless turned on).
- **A tap opens** where the event points: the gate; Now with the permission or the question open; the flow (a box
  open at *try again* when it ran out of tries); Cost with the raise question open; Models; Activity.
- **Inside the app** no push shows: a line under the header ("Final review waits · paper-1 · Open").
- iOS's own *Show Previews* can hide the text on the lock screen as well. **Activity** lists every push sent, with its
  exact text and when it left the PC.
- **How it is sent**: Web Push with VAPID keys of the PC's own (made once, kept in Clank's secrets) and the payload
  encrypted for the device (RFC 8291); the standard library has no P-256 or AES-GCM, so a dependency decision comes
  with the build (§11 step 4), weighed against writing the two primitives.

## 5. Now

The home screen, in this order:

1. **The header**: ◆ CLANK, the PC's name, *live* (or *reconnecting*, *offline*).
2. **The model**: the main slot's preset and kind ("frontier 262K · local · 27B" is the owner's; the words are the
   preset's), its speed, what it does now ("writing · T2 · paper-1 · step 14"), the window used of the whole; then the
   machine as four small gauges: GPU, VRAM, CPU, RAM.
3. **Waiting for you** (its count in the tab's badge): each card with its age; an OpenCode permission with the file and
   the change's size (`Allow once`, `Always`, `Reject`, `Diff`); a Clank question with its words and options (the
   cloud for a workspace: `Allow in <workspace>`, `This session`, `No`); a flow building that waits on a proposal
   (`look`). Answered from here, or on the console: the first answer counts.
4. **Working now**: each session at work: its box and flow or its title, its step and try, its time, its tokens; a
   planning writing a proposal.
5. **The tabs**: Now (with the badge), Flows, Work, Files, More.

## 6. Flows: the list, a flow, building one, a gate

- **Flows**: *Build a flow* at the top; filters All, Running, Waits, Ended; each flow with its state (running: the box
  and "6 of 9"; building: "waits for you: proposal 1 of 2"; finished: "approved by you"; stopped: why), its workspace,
  its model, its time.
- **A flow**: its name, workspace, model and time; `Pause after <box>` and `Stop`; its boxes as a column (brief, plan,
  check, split, the tasks as a tree, integrate, review) each with its tries and time; the running box open: its
  title, "try 1 of 3", the last words of its session, tokens, speed, time and files, then `Session`, `Guide`,
  `Context 16%`; a gate as "gate · you decide".
- **Building a flow with the model** (design 0013 §15): the five steps (talk it through; BRIEF.md written, `open`;
  draft the flow, each draft accepted or refused with why; proposals, "1 of 2 waits"; look, then run); the brief's
  first lines; each proposal with its words and why, `Accept`, `Reject`, `Accept all`, `Reject all`; `Run after
  proposals`.
- **A gate** (the final review): the deliverables with their sizes (`new +142`, `+38 −4`); the review box's verdicts
  (pass, concern, with its words); a note, sent with *Send back*; `Approve`, `Send back`, `Stop`; a proposal from the
  review ("runs after Approve": `Accept`, `Reject`).

## 7. A session, the Guide, its context

- **A session**: its box and flow (or its title), its model, its running time, its context share; the task from the
  flow; then the conversation as the agent panel draws it (design 0021 §4): tool calls with their sizes and exits, the
  thought folded ("thought · 1,188 tokens · show"), the text, the live line marked LIVE with the speed, the words as
  they stream (§3). Under it, **the Guide** (design 0012 §9) with what each costs under its name: `Stop` (now, files
  stay), `Note` (read next step), `Pause` (after this step), `Compact` (its time and tokens freed), `Undo` (steps and
  files), `Drop` (a result, its size).
- **Drop a result** opens a sheet: the biggest results in the window (the step, the size, "failed, fixed since"), the
  window after, when (the next step, about how long), `Drop at next step`, `Cancel`.
- **Context**: the window used of the whole, the compaction line ("compacts at 80%"); what fills it, counted each step
  (tool results, messages, tool definitions, system prompt, task and files, reasoning, each with its share); the
  biggest items, each with `Drop` or marked `fixed`.

## 8. Work and Files

- **Work**: Docker's state; each workspace with its state and time, its model, its sessions ("3 sessions · 1 works ·
  2 wait for you"), its flow; a stopped one with `Start` (what it does first, how long); Docker's line (containers up,
  images, size); `New task`, `Build a flow`.
- **A workspace**: its container, image, folder, model, cloud allowance (and when it was asked), flows; its sessions
  with their state; **New task**: what the model should do, the model to use (the presets and the cloud), `Start`;
  `Build a flow with the model`.
- **Files**: changed today, by workspace, newest first: the file, its folder, which box or session, when, its change
  (`+38 −4`, `new +61`, "asks to edit it" for one waiting). The flow's own file too.
- **A file**: read only; its changes one at a time (`Previous change`, `Next change`) as a diff with line numbers, or
  the whole file. The outbox's files (design 0005 §3) show here too.

## 9. More: activity, models, cost, settings

- **More** lists Activity (operations, the stream's age), Models (what the main slot holds), Cloud cost (today and the
  month), Questions and permissions (waiting, answered today), Settings (this iPhone, notifications); then the PC: its
  address, "through Tailscale · tailnet only", the stream's last event; Clank's version ("the app updates with it").
- **Activity**: All, Operations, Events, Exchanges. Operations running with their step and progress and who asked
  ("asked from this iPhone at 14:33"); events newest first, each marked `pushed` when it was; the exchanges of this
  device (design 0005 §5's log, from the phone's side: the stream's events a minute, the pushes with their level and
  size).
- **Models**: the GPU's use; each slot (main, fast, cloud) with its preset, state, where it runs and its speed; **Switch
  the main slot**: the presets with their speed and window, what happens (unload, load, how long, which session waits
  and whether its tokens fit), `Switch after <box>'s step`, `Switch now: <box> stops`.
- **Cloud cost** (design 0016 §11): the provider and model; a pause at a limit as a card (`Raise the limit`, `Keep
  paused`); today and the month against their limits; today by flow and session; the last requests with their tokens
  and cost; the prices and limits in one line. **Raise** (the question Clank asks at the limit): the new limit for
  today as a typed number within the bounds the PC checks too, what it means for the month, that tomorrow goes back;
  `Raise`, `Keep paused`; "also on the console; the first answer counts".
- **Settings**: this iPhone (paired when, renewed when, lapses after 30 days unused, `Sign out`); other devices with
  their last use and `Revoke`; Notifications (the level, each kind on or off, the words of §4).

## 10. Choices made since the canvas

The canvas left these to the owner; Clank takes the canvas's defaults until the owner says otherwise:

- The tabs are Now · Flows · Work · Files · More (the Log tab of today moves under More, Activity).
- Push levels Quiet, Names (the default) and Names + numbers; session titles never in a push.
- Now's order: the model and the machine, Waiting for you, Working now.
- Files are read only on the phone; a file's text is shown while the owner looks and never kept.
- The install claim rides in the icon's start link (iOS keeps a Home Screen app's storage apart from Safari's).
- The device token renews on each use and lapses after 30 days unused (no 90-day ceiling).
- The type is the system's monospace (iOS has one); JetBrains Mono is not served by the PC.
- The app is served by the listener as today's page is, from Clank's package: no build step, no bundler.

## 11. Order of work

1. **The shell and the stream** ([plan s57](../plans/s57-the-phone-app.md)): the listener's `/api/stream` (events with
   titles and attention, the model and machine, the sessions and operations), the service worker and manifest (icon,
   full screen, offline shell), the pair link with its code and the install claim, the device token renewed on use,
   Now with its cards, the tabs, the reconnecting and offline screens; the console's Phone page shows the QR.
   Built 2026-10-26.
2. Flows, a flow, building one, a gate (§6); a session with the Guide and its context (§7), on the conversation stream.
3. Work, a workspace, New task, Files and a file (§8).
4. Notifications (§4): the dependency decision, the VAPID keys, the subscriptions per device, the sender, Settings.
5. More: Activity, Models with the switch, Cost with Raise (§9).

Design 0005's phone page is replaced screen by screen; its listener, pairing and traffic log stay. A decision record
says the phone is an installed web app, not a native one (decision 0143).
