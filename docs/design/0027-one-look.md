# Design 0027: One look: Clank's surfaces beside its website

What Clank looks like where the owner uses it (the console, VS Code, the iPhone app, boards and artifacts) against
what the website ([clank-ai.github.io](https://clank-ai.github.io), its own repository) draws of it: every difference
that matters, which side is better, and what to do. The owner asked on 2026-10-27: "note any design differences between
the website and Clank itself, and make any necessary changes to make clank look as good as possible while also
prioritizing its functionality." The console already took the website's look at the owner's request
([design 0011](0011-the-consoles-look.md) §13, [decision 0125](../decisions/0125-the-console-takes-the-websites-look.md):
"look almost exactly what we have envisioned in the website"); this document does the same for the other surfaces:
VS Code ([design 0021](0021-all-llm-work-in-clank.md)), the iPhone app ([design 0025](0025-clank-for-iphone.md)),
boards ([design 0022](0022-boards.md)) and artifacts. What only brought a surface back to a design already approved, or
repaired what looked broken, is built on the branch `design/one-look` (§10); everything else here waits for the owner.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | How they were compared | Proposed 2026-10-27 |
| 2 | One palette, three grounds, the type | Proposed 2026-10-27; VS Code's one token sheet built on `design/one-look` (§10) |
| 3 | The console | Proposed 2026-10-27; the menu's ground built (design 0011 §7) |
| 4 | VS Code | Proposed 2026-10-27; Clank Night in the readout, the parts by kind and the artifact bar built (design 0021 §3, §5) |
| 5 | Contrast | Proposed 2026-10-27; the phone's quiet words built |
| 6 | The iPhone app | Proposed 2026-10-27; what looked broken and the canvas's look built (design 0025 §2, §3, §5) |
| 7 | Boards and artifacts | Proposed 2026-10-27 |
| 8 | What the website should change | Proposed 2026-10-27, for the website's repository |
| 9 | Proposals not built | Proposed 2026-10-27: the owner decides |
| 10 | What `design/one-look` changed | Recorded 2026-10-27 |

## 1. How they were compared

- **The website**, built (`dist/`) and served on this PC, drawn by headless Chrome at 1,400 pixels: the home page and
  Features, whose screens are `src/components/surfaces/` (VSCodeWindow, PhoneFrame, BoardSurface), `Window.astro`, the
  console's crops (`src/scripts/crops.ts`, from this repository's `tests/console/snapshots/`) and its tokens
  (`src/styles/global.css`).
- **The console**: `clank console --snapshot` against the running service (read only), and Textual's own SVG of test
  frames (Home with a question, board D1's Flow view), which keep the colors that the text snapshots drop.
- **VS Code**: the screenshots the extension's page tests leave in `vscode/out/test/` (the agent panel in a dark, a
  light and Clank Night's colors, a board, the Notion review, the annotator), and the readout and an artifact's bar
  drawn from their templates.
- **The iPhone app**: `clank/components/remote/page/` served by a stand-in PC (example data on its stream), each
  screen drawn 375 pixels wide (an iPhone's width) inside a page of frames: Now, Flows, Work, Files, More, a session and
  its Context sheet, the offline, pairing and launch screens, and the page the app is added from.
- **Contrast**: WCAG 2's ratio, computed for every text color of each surface on each of its grounds (§5).

## 2. One palette, three grounds, the type

Every surface draws from one family, Tokyo Night as the console's style names it (design 0011 §6, decision 0125). The
roles line up:

| Role | Website (`global.css`) | Console (its style) | VS Code, Clank Night | iPhone app |
| --- | --- | --- | --- | --- |
| Page | #16161e `--bg` (the console sits on it as a window) | #1a1b26 `background` | #1a1b26 | #1a1b26 `--bg` |
| Deeper | #101119 `--well` | #16161e `bars`, `inset` | #16161e | #16161e `--deep` |
| Raised | #1a1b26 / #1f2133 `--surface(-2)` | #24283b `surface` | #24283b, #1f2335 | #1f2335 `--raised` |
| Rule, edge | #272b3f / #3b4261 | #414868 `border` | #292e42 / #3b4261 | #292e42 `--line` / #3b4261 `--edge` |
| Strong text | #e6eaff | #e0e5ff `selected-text` | #e0e5ff (was #e0e6ff) | — |
| Text | #c0caf5 | #c0caf5 | #c0caf5 | #c0caf5 |
| Quiet | #a1abd2 `--muted` | #9aa5ce `quiet` | #9aa5ce | #a9b1d6 `--muted` |
| Quieter | #8a93bc `--faint` | #565f89 `dim` (what cannot act) | — | #8a93bc `--dim` (was #646c94) |
| Accent | #7aa2f7 | #7aa2f7 `key` | #7aa2f7 | #7aa2f7 |
| Brand | #ff9e64 | #ff9e64 `brand` | — | #ff9e64 |
| Good, attention, failed | #9ece6a, #e0af68, #f7768e | the same | the same | the same |

- **The drift is small and was in two places.** VS Code's agent panel and boards each kept their own copy of Clank
  Night, already apart (a strong text of #e0e6ff, a board's rule), and the readout had none: now one sheet,
  `vscode/media/tokens.css`, with each value beside the console's role it is (built, §10). The phone's quieter words
  were a color of their own that failed WCAG AA (§5; built).
- **The grounds differ on purpose.** The website's page is the darkest (#16161e) so that a screen of Clank, drawn on
  #1a1b26, stands on it as a window; inside each real surface the page is #1a1b26. Nothing to change.
- **The type follows the host.** The website sets prose in Instrument Sans and code and the console in JetBrains Mono;
  the console is in its terminal's font, VS Code's pages in VS Code's UI and editor fonts, the iPhone app in the system's
  monospace (and a chat in the system's text face: design 0025 §10, which keeps the PC from serving fonts), an
  artifact's page in `system-ui`. Each is right where it is; the website's faces are the website's.
- **Shapes**: the website rounds cards (14 px) and buttons (10 px); VS Code's pages round theirs (10 and 6 px); the
  console is cells (square, or `round` in a style); the phone was square everywhere and is rounded now as its canvas
  draws it (8 and 6 px, built, §6).

## 3. The console

The website's console is drawn from the console's own frames, cell for cell, and decision 0125 gave the console the
website's colors: the header, the panels with their titles in the border, the keys, the Monitor and the Flow view match.
What differs:

1. **The menu's ground.** Design 0011 §7 puts the menu "on `background`", as boards E1 to E18 and the website draw it.
   Textual draws any list on `surface` (#24283b), tinted while it has the focus, and the console starts with the focus
   on the menu: the menu stood on a lighter ground than the page, and the highlighted page (#283457) barely showed on
   it. Fixed: the menu is transparent, like the pages' lists (§10).
2. **The context's parts.** The website's crops color them by their own choice (the system prompt purple, tool
   definitions blue, thinking yellow, results teal); the console colors each kind as design 0011 §6 and design 0012
   §4.2 say (the system prompt blue, tool definitions a deeper blue, your messages yellow, thinking purple, calls teal,
   results green, loop text red). The console is right: each kind keeps one color everywhere, and now VS Code's readout
   takes the same (§4). The website should take the console's (§8).
3. **A flow's kinds of box.** The website's table colors YOU purple, VERIFY green, DECOMPOSE orange and INTEGRATE red;
   the console (design 0011 §6) colors YOU and GATE in attention's yellow (the owner's), PLAN blue, VERIFY purple,
   DECOMPOSE cyan, TASK teal, INTEGRATE in the text's color. The console is right: green and red are its words for
   passed and failed, so a green VERIFY and a red INTEGRATE read as results, not kinds. The website should change (§8).
4. **This folder's words.** The website's crop is an older frame: a panel titled "This folder" with five checked lines
   and `g does every step`. The page today is "Get ready to work here" with seven numbered steps (the sandbox image
   among them), a `Next:` line, and "Then work" with nine keys (`tests/console/snapshots/folder-88.txt`). The console's
   is the newer and fuller; the website should take it.
5. **The "coming" entries**, twelve pages a later milestone brings, in red under the menu. The website leaves the menu out
   of its frames; in the console, red is also "failed", and the issues page already lists these entries as confusing.
   A proposal, not built (§9): it changes nearly every frame's snapshot.

## 4. VS Code

The website draws one VS Code window in Clank's colors: the Explorer, a change beside its file with **✓ Accept**
(filled green) and **✗ Reject** (outlined red) as labeled buttons, OpenCode in a terminal at the right, and a status
bar of `◆ Clank ✓`, `Docker ●`, `Review`, `Completion ✓`. Clank in VS Code:

1. **Accept and Reject** are the icons ✓ and ✗ in the diff's title bar (VS Code's editor title takes icons, with their
   words as tooltips), on a diff titled `Review: src/api/server.py (+3 -1)`. VS Code's way is right for an extension;
   the website should draw the icons and the title as they are (§8).
2. **The status bar** says `Clank` beside a server icon (a question mark and the count while something waits),
   `Docker: running`, `Review` (`Plan`, `Auto`), `Completion` with a check, and the model's readout,
   `61 tok/s · 38K/131K · answering`, which the website leaves out. The website's `◆ Clank` carries the brand better
   than a generic server icon: a proposal (§9); the readout's item belongs in the website's drawing (§8).
3. **The agent panel and the readout**, the largest of Clank's pages in VS Code, are not drawn on the website, though
   its words describe them. The website should draw them (§8); the panel's test screenshots are a faithful start.
4. **Theme.** The website shows VS Code in Clank's colors; the extension follows the window's VS Code theme, and the
   setting `clank.agentPanel.theme: clank-night` gives its pages the console's colors. Following the window's theme by
   default is right (a light theme gets light pages). With Clank Night on, the agent panel and boards took it but the
   readout under the panel stayed in VS Code's gray: it takes it now, from the one token sheet (§2; built). The Notion
   review and the figure annotator follow VS Code's theme only: a proposal to move them onto the sheet (§9).
5. **The readout's context bar** colored its parts by their place in it (sorted by size: the first blue, the second
   orange...), so a part changed color as it grew past another. Each part is now colored by its kind, as the console
   colors it: the theme's chart colors by default, the console's own in Clank Night (design 0021 §3, design 0012 §4.2;
   built, tested).
6. **An artifact's bar** (its title, versions, Comment, Open in browser) was a fixed dark gray over any page; it is now
   a widget of the window's theme, like VS Code's find widget (design 0021 §5; built).
7. **The extension has no icon of its own** (the Extensions view shows the default), and no mark of Clank's anywhere in
   the window. A proposal (§9).

## 5. Contrast

Every text color of each surface on each of its grounds, by WCAG 2's ratio (AA asks 4.5 for text, 3 for large text
and for the edge a control needs to be seen):

| Surface | Lowest text ratios | Verdict |
| --- | --- | --- |
| Website | text 9.8, muted 7.0, faint 5.3, each accent 6.0 or more | AA everywhere |
| Console | text 7.6, quiet 5.0 and failed 4.6 on the selection; dim 2.8 | AA but `dim`, used only for what cannot act now (a dimmed button, a box not yet reached, an undone step): WCAG exempts an inactive control, and `dim` must never color words that inform |
| VS Code, Clank Night | text 9.0, quiet 6.0, link 5.8, failed 5.5 on the raised ground; the accent's text on the accent 6.8 | AA everywhere |
| VS Code, its theme's colors | its theme's (Dark Modern's quiet: 6.1) | the theme's |
| iPhone app, before | quieter words (`--dim` #646c94) 3.1 to 3.5 | **failed**: section titles, sub-lines, times, a key's name, empty states |
| iPhone app, after | `--dim` #8a93bc (the website's faint) 5.2 to 6.0; muted 7.4; the words on a filled button 7.1, on the toast 6.8 | AA everywhere (built, §10) |

- **Edges.** Rules and a control's edge are #272b3f to #414868 on the pages (1.3 to 1.9 to 1), as on the website.
  WCAG 1.4.11 asks 3 to 1 for an edge only where it alone shows the control: Clank's buttons carry their words and its
  fields their placeholder (now AA), so the edges stay quiet, as the website draws them.

## 6. The iPhone app

The website's iPhone is drawn from the app's canvas, which the owner approved for design 0025 ("honestly looking
perfect"): a Now screen with the model, the machine, and two rounded cards waiting with a filled first answer, and five
tabs with the one on screen in blue. The app as built:

1. **What looked broken** (built, tested): the word `null` stood at the top of every tab while the stream was live (an
   absent line handed to the page), and the header's `● live` was a solid green block (it took the class of a session's
   LIVE mark); main took both away the same morning (4538ab2, d716f24), and this branch builds on them: the helper is
   tested, and the header's state has classes of its own, since `offline` would still have taken the offline screen's
   grid. The page the app is added from ran its 12-pixel lines down the whole screen (it had no style of its own and
   took the Flows tab's steps) and named an SVG icon, which iOS does not take for the Home Screen.
2. **Shape and emphasis** (built): square boxes and buttons, the first answer outlined in green, the tab on screen a
   solid blue block, and controls whose edge (#292e42 on #16161e) barely stood apart from the page; now rounded, the
   first answer filled in the accent (as the canvas and VS Code's panel fill it), the tab on screen in blue words under
   a blue line, and an edge of #3b4261 on the raised ground.
3. **Words** (built): its own buttons were lower case (`allow once`, `send the answer`, `close`) beside its own `Build a
   flow`, `Accept`, `Guide` and the service's options; they are capitalized, as design 0025 §5 names them.
4. **What the canvas draws that the app does not do yet** (design 0025 §5, approved): the window used of the whole on
   Now (`24K / 131K` with a bar), a card's age (`3 min`), a change's size (`+6 −2`) and **Diff** in place of the whole
   diff shown in the card, and the asker named first (`◆ OpenCode asks: edit`). Behavior, not looks: for the app's next
   step (§9). The app's four gauges with their numbers say more than the canvas's four bars, and stay.
5. **The icon**: the app's is the console's ◆ in orange over a blue cursor (design 0025 §3); the website's brand page
   chose another mark ("the open gate": an open bracket around the ◆) for the logo, the favicon and its own Home Screen
   icon. A proposal (§9).
6. **The type**: the system's monospace, not the website's JetBrains Mono, as design 0025 §10 decided. It stays.

## 7. Boards and artifacts

1. **A board.** The website draws a frame named inside its dashed border (`Figure 1 · frame`), pins as yellow pills
   with `!`, and a slot with a filled blue **Fill**. The board in VS Code names a frame above its border, shows pins as
   numbered dots in the ink's color with their words beside them, and a slot's **Fill** as a quiet outlined button.
   The board's numbered pins are better (the agent answers them by number); the website's filled Fill is the clearer
   call to act: a proposal (§9). The selection's toolbar covers the name of a frame whose top item is selected (seen in
   the board test's screenshot): a proposal too.
2. **Artifacts.** The website names them and draws none. An HTML artifact is the agent's own page; a Markdown or SVG
   one gets Clank's plain page (`system-ui`, VS Code's colors inside VS Code, black on white once opened in a browser).
   A proposal (§9): the plain page follows the reader's light or dark preference.
3. **A board exported** for a paper is black on white, as a figure must be. It stays.

## 8. What the website should change

For the website's repository (read only from here; another agent edits it):

1. **The Boards drawing on Features collapses to a two-pixel line** (seen at 1,400 pixels): `.board-art` is a flex item
   with `margin-inline: auto` and inline-size containment, so it shrinks to nothing; `width: 100%` on it fixes it.
2. **A flow's kinds** in the console's colors (§3.3), and **the context's parts** in the console's (§3.2), in the
   Flows table and the Monitor's crops.
3. **This folder's crop** from today's frame (§3.4).
4. **The VS Code window**: Accept and Reject as the title bar's icons, the diff's title `Review: … (+3 -1)`, the status
   bar's real items (`Docker: running`, the readout's line), and the agent panel beside the terminal with the readout
   under it (§4).
5. **The board**: numbered pins in the ink's color, the frame's name above it (§7.1).
6. **The iPhone** stays the target while the app catches up (§6.4); its words are behind the app: "Flows, the session,
   notifications and settings come next", while the Flows tab and a session with the Guide and its context are built
   (the changelog says so); notifications and settings come next.

## 9. Proposals not built

For the owner to approve or drop, larger or riskier than a fix:

1. **One source for the palette**: a generator in `tools/` writes `vscode/media/tokens.css`'s Clank Night and the
   phone's `:root` from the console's style (`StyleColors`, `ContextParts`), with a test that they agree, so a color
   changed in Clank's style changes on every surface. Medium; like `tools.tstypes`.
2. **The brand's mark in Clank**: the open gate as the phone's icon (`icon.py` draws it; design 0025 §3 revised), as
   the extension's icon (a 128-pixel PNG, Clank's first binary in the package, or drawn at build), and `◆ Clank` for
   the status bar's server icon.
3. **The Notion review and the annotator on the token sheet**, so Clank Night colors every page in VS Code (their
   sheets name colors in their own words today).
4. **The phone's Context sheet** colored by part, as the console and the readout are (its answer would carry each
   part's kind).
5. **The menu's "coming" entries** quieter than `failed`'s red, or behind a setting (§3.5); every frame's snapshot
   changes with it.
6. **A board's Fill** as the accent's filled button, and the selection's toolbar placed where it hides no frame's name.
7. **The plain artifact pages** (Markdown, SVG) with `color-scheme: light dark` and the tokens for code and tables.
8. **The phone's Now and cards as designed** (§6.4): the window meter, a card's age and size, **Diff**.
9. **The website's list** (§8), for whoever edits it next.

## 10. What `design/one-look` changed

Each change brings a surface back to a design already approved, or repairs what looked broken; tests first where it is
behavior. Every test of each part passed (the phone's Node and Python tests, the console's tests of the menu, the
repository's checks, the extension's `npm run check`), and `tools.check` whole passed (2,874 tests) before the branch
was rebased on main's two phone fixes of the same morning; after it, the phone's, the remote part's, the repository's
and the extension's tests again.

| Commit | Surface | What changed |
| --- | --- | --- |
| d1edf36 | iPhone app | On main's 4538ab2 and d716f24: `fill()` through the tested `present()`, the header's state in classes of its own (`linkBadge`, tested), the page the app is added from laid out and naming the PNG icon (tested) (design 0025 §2, §3, §5) |
| 9ea8525 | iPhone app | The canvas's look: rounded, the first answer filled, the tab in blue, edges that show, quieter words at AA, buttons capitalized |
| 3677fde | Console | The menu on the page's ground (design 0011 §7) |
| 708a71d | VS Code 0.10.4 | One token sheet (`media/tokens.css`), Clank Night in the readout, the context's parts by kind (tested), the artifact bar in the window's theme (design 0021 §3, §5) |
| f9c6c26 | iPhone app | Its offline shell v5, so an installed phone keeps the new look |
| this one | Docs | This design |
