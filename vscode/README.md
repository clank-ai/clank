# Clank for VS Code

Clank in VS Code (design 0002, M0.6): the Clank service and Docker in the status bar, and the questions Clank asks you,
answered from here or from any other client; the agent's changes to your files, reviewed beside them (design 0007); the agent's proposals for your Notion,
reviewed before anything is written (design 0010); and the gates of your flows, with their files and tries (design 0013). It is a client of the Clank API and keeps nothing of its own: it reads
where the service answers and the local token from CLANK_HOME each time it connects.

| Where | What |
| --- | --- |
| Status bar, left | `Clank`: whether the service runs, and how many questions wait for you (click: the questions) |
| Status bar, left | `Docker`: its state (click: start or stop it) |
| Status bar, left | The model's readout (design 0021 §3): its writing speed, the context used of its window and what it does now, e.g. `63 tok/s · 161K/262K · thinking` (click: the panel) |
| Editor, under the agent | **Clank · the model**: the model and its speed settings; writing speed (live), the last prompt's reading speed, the drafted tokens accepted and recent steps as a graph; what it does now; the context window part by part with the compaction line and the cache's share; what is attended exactly on the GPU and what is retrieved; whether the engine holds this session's conversation; the GPU's memory and use; the jobs running in the folder's workspace (design 0021 §6). It opens with the agent (`clank.readout.openWithAgent`) or from `Clank: Show the model's readout` |
| Editor, beside the agent | **Clank · agent** (design 0021 §4): the agent's conversation drawn, on the same session as OpenCode's terminal: the owner's messages, the model's Markdown with its math (KaTeX), its thinking and each tool call folded, the figures it looked at or showed, the artifacts it made as cards that open, and what waits (a permission, a question) with its buttons; a box to write to it (Enter sends, `@` names a file, an image can be pasted), and Sessions, New, Stop, Compact and Terminal (this session shown in OpenCode's terminal). It opens with the agent as a tab beside the terminal, which stays in front (`clank.agentPanel.openWithAgent`), or from `Clank: Show the agent panel`, or the link `vscode://clank.clank/agent-panel` |
| Editor, a `.board` file | **A board** (design 0022): a canvas you and the agent share. Figures from the folder's images (drawn again when a script writes them again), LaTeX (math drawn at once with KaTeX), notes (Markdown with math), frames, slots for the agent to fill, highlights, pins with comments, pen strokes and arrows. Select, move (snapping to other items and the grid), resize, align, frame, delete, duplicate; pan with the wheel, zoom with Ctrl and the wheel; a double click edits in place; drop images from the Explorer or paste them. **Ask the agent** about a selection, **Fill** a slot, **Send pins**: each goes to the agent's session, which places things with its board tools. `Clank: New board` makes one |
| Status bar, left | `Plan`, `Review` or `Auto`: the Planner, or how the agent of the window's folder changes files (click: pick one) |
| Editor | On an open plan (a Markdown file whose header says `kind: plan`): **▶ Implement with Review**, **▶ Implement with Auto**, and **↻ Continue (k of m steps done)** when some checklist items are done; each hands the plan to the agent (design 0009) |
| Status bar, left | `Completion`: on and served (check), on but its model not running (warning), or off (click: turn it off or on) |
| Editor | Gray text after the cursor as you type, from the model in Clank's fast slot: Tab takes it (design 0006) |
| Editor | A figure (PNG, JPEG) opens in Clank's annotator: draw on it (pen, box, circle, arrow, note), say what to do, Enter sends it to the agent with each mark in words (design 0008); `Clank: Annotate with Clank` opens one from the explorer |
| Editor | A change the agent asks for opens beside your files (the file as it is, and as the agent would leave it), with **✓ Accept** and **✗ Reject** in its title bar; in auto mode, each change opens after it is made |
| Activity bar | **Notion changes** (design 0010 §6): each batch the agent proposes for your Notion, its databases and their entries (new, changed, removed), with **Approve all** and **Reject…**; its badge counts what waits |
| Editor | A batch's review: each database as a table (changes and their neighbors, or all rows), the chosen entry's Fields, Page and how it will look in Notion; uncheck what should wait, then **Approve N checked**; comment on the batch, an entry, a field or a paragraph, and **Send back with N comments** for the agent to revise it (its answers show under your comments) |
| Status bar, left | `Notion: N changes waiting`, when some do (click: the Notion changes) |
| Editor | An artifact the agent made (design 0021 §5): its page beside your files, drawn with Clank's libraries and nothing from the network; its bar picks a version, sends your **Comment** to the session that made it, and opens it **in your browser** as one self-contained page; `Clank: Open an artifact` lists the folder's |
| Notifications | A question asked while VS Code is open, with its options as buttons |
| Notifications | A job the agent started in the window's folder (design 0021 §6) that ended: how, after how long, and where its log is |
| Notifications | When a flow's box switched the main slot (design 0013 §7): the model your OpenCode window talks to now, its limits, and a preset too small for one of your sessions, named; the window takes the new limits when it next starts |
| Notifications | A flow's gate, YOU box or failed box (design 0013 §10), with its answers, **Open** (the file it shows, in the folder: the gate comes back once you save it, to approve what you edited) and **Diff** (the file's last two tries, in VS Code's diff); *Send back* and *Try again* ask for your note first, and Escape keeps the gate waiting. The Clank item's count (or the Questions command) shows a gate again, even one whose notification went unclicked to the notification center. One answered on the phone or the console is not shown again, and its diffs close |
| Commands (Ctrl+Shift+P) | `Clank: Questions waiting for you`, `Clank: Start Docker`, `Clank: Stop Docker`, `Clank: Start or stop Docker`, `Clank: Connect to the Clank service again`, `Clank: Accept the change`, `Clank: Reject the change`, `Clank: Pick the mode: Plan, Review or Auto`, `Clank: Implement the plan with Review`, `Clank: Implement the plan with Auto`, `Clank: Continue implementing the plan`, `Clank: Turn completion on or off`, `Clank: Review the Notion changes` |
| Setting | `clank.home`: CLANK_HOME, when it is not the environment's or `~/.clank` |
| Setting | `clank.changes.showInAuto`: in auto mode, open each change the agent makes (on by default) |
| Setting | `clank.readout.openWithAgent`: open the model's readout under the agent when it starts (on by default) |
| Setting | `clank.agentPanel.openWithAgent`: open the agent panel beside the agent's terminal when it starts (on by default) |
| Setting | `clank.agentPanel.theme`: the agent panel's colors, `vscode` (the window's VS Code theme, the default) or `clank-night` (Clank's console) |

What you do here is recorded as you (vscode), and every other client shows it.

## Working on it

From the repository's root, `uv run python -m tools.check` compiles and tests the extension with the rest. In this
folder: `npm ci` installs its tools from the lock, `npm run check` compiles and tests it. Its core (`src/core/`) never
imports `vscode`, so it is tested with Node's own test runner; `src/extension.ts` is the thin glue to VS Code.
`src/core/kinds.ts` is generated (`uv run python -m tools.tstypes`): never edit it by hand.
