# Design 0019: the animation workbench

Part of Clank Code ([design 0018](0018-clank-code.md)); it builds on the figure annotator
([design 0008](0008-annotating-figures.md)) and on jobs ([design 0013 §17](0013-flows.md)). Started 2026-10-23 at the
owner's request: "manim animations that we can make together, in fact this is actually the very first thing that I
would like you to design fully and then build when I approve the design so that I can test this out myself." Drawn in
the owner's design canvas "Clank in VS Code": the boards "Animation workbench" and "Animation: sketch of the opening",
and the row "Animation workbench, in depth" (ten boards, one per part below). Every section is proposed; nothing is
built until the owner approves it.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-23 |
| 2 | The owner's choices | Recorded 2026-10-23 |
| 3 | What other work teaches | Proposed 2026-10-23 |
| 4 | Manim in the container | Proposed 2026-10-23 |
| 5 | Starting a scene | Proposed 2026-10-23 |
| 6 | What Clank records of a run | Proposed 2026-10-23 |
| 7 | Checks before you look | Proposed 2026-10-23 |
| 8 | The sketch of the opening | Proposed 2026-10-23 |
| 9 | The player, the timeline and the frame inspector | Proposed 2026-10-23 |
| 10 | Marks, and marks in words | Proposed 2026-10-23 |
| 11 | Timings Clank changes itself | Proposed 2026-10-23 |
| 12 | The agent's turn | Proposed 2026-10-23 |
| 13 | Mark threads | Proposed 2026-10-23 |
| 14 | Versions, branches and comparing | Proposed 2026-10-23 |
| 15 | Data plots, the first use | Proposed 2026-10-23 |
| 16 | When a render fails | Proposed 2026-10-23 |
| 17 | Export and provenance | Proposed 2026-10-23 |
| 18 | Limits | Proposed 2026-10-23 |
| 19 | Later | Proposed 2026-10-23 |
| 20 | Tests | Proposed 2026-10-23 |
| 21 | Build steps | Proposed 2026-10-23 |

## 1. What the owner gets

A Manim scene file opens in Clank's animation workbench beside its code. The owner starts a scene from data, a
figure, words or a template; the agent writes it; Clank checks it without rendering and shows its opening as a sketch,
one still per animation, in a few seconds. The owner marks the stills (pen, box, arrow, text, comment pins, and direct
marks: move, resize, recolor); the marks go to the agent in words, with the objects under them and the lines that made
them; the agent answers each mark by number; the owner reviews the change, and the sketch comes back. "Animate it"
renders a preview video, where every `self.play` and `self.wait` is a block on a timeline linked to its line of code.
The owner pauses on any frame and marks it the same way, drags a block's edge to change its timing, and compares
versions in step. Final renders export as video, GIF and frames, each with a record of the code and data that made it.

## 2. The owner's choices

- **Manim Community**, not ManimGL.
- **Rendering in the project's container**: Manim and its LaTeX in Clank's sandbox, renders run as jobs.
- **First use: data or a plot** (§15).
- **Straight to code, the opening sketched first**: "it should sketch the beginning out in detail first and provide a
  way for me to annotate different frames" (§8).
- The figure loop's spirit holds here: "a simple annotation setup that will let me draw, add comments, and so on", with
  the user experience "prioritized alongside the usability and reliability of the implementation".

## 3. What other work teaches

- **Layout is where model-written Manim fails.** TheoremExplainAgent (2025) found most of its generated videos had
  layout problems; PhysicsSolutionAgent (arXiv 2601.13453, 2026) found layout problems and misread images in its
  feedback loop.
- **Layout can be checked without pixels.** SGA (Lopez, Hinojosa and Ghanem, arXiv 2607.18116, 2026) runs the
  generated code without rendering, builds a graph of the objects on screen (kind, center, size, variable name, line
  that made it), and flags overlaps at rest, objects past the frame and objects too small to read; it sends the model
  each conflict with the smallest move that removes it, and edits only a few lines around the creating line. One round
  improved its layout score in 7 of 8 setups, and people preferred its videos over those fixed by a vision-model critic
  in 65% of comparisons. Clank's model reads no images, so this is the right shape for Clank (§7).
- **A grid gives a blind model words for places.** Code2Video (arXiv 2510.01174, 2025) places objects on a 6×6 grid of
  named anchors and keeps a table of which object holds which cell; Clank names places the same way (§10).
- **Fix narrow first.** Code2Video's ScopeRefine repairs the failing line, then its block, and only then regenerates
  the section; this saves tokens and time (§16).
- **Timings belong on the timeline.** Motion Canvas lets the author drag a time event in its editor instead of editing
  delays in code, with later events moving along unless Shift is held (§11).
- **Talks and narration have tools already.** Manim Slides turns sections into click-to-advance slides (HTML or
  PowerPoint); manim-voiceover syncs a voice track to the scene by bookmarks (§19).

## 4. Manim in the container

Manim comes as a second image layer on Clank's sandbox image (design 0004 §3's "a second image layer per kind of work,
added when first needed"): `clank image add manim`, offered the first time a workspace opens the workbench. The layer
holds Manim Community pinned at 0.22.0 (released 2026-10-08; it needs Python 3.11 or newer, and the image has 3.12),
and what it needs to render text and formulas: Cairo and Pango, FFmpeg, and a TeX Live set for `MathTex` (LaTeX and
`dvisvgm`). The exact packages are fixed when the layer is built and checked by rendering Manim's own example scenes;
its size and time are measured then (expected 1 to 2 GB, a few minutes). A workspace that never uses Manim does not
carry it. Rendering uses the CPU; the GPU stays the model's. Moving to a newer Manim is a decision with its own record,
since §7's API check is written against one version.

## 5. Starting a scene

"Clank: New animation", or "Animate this" on a data file or a plotting script, opens the start page. Four starts:

- **From data**: a CSV or JSON file; Clank lists its columns with their ranges, the owner picks what each one is (x,
  a curve) and a shape (a curve drawn over time, a sweep with a parameter, bars that grow); Clank suggests a log scale
  when a column spans more than a decade.
- **From a figure**: a plotting script whose figure Clank already records (design 0008 §3); the agent starts from its
  labels, ranges and colors, so the animation matches the paper's figure.
- **From words**: best for diagrams and equations.
- **From a template**: a title card, an equation built term by term, a data curve, a parameter sweep, a diagram with
  arrows.

Each start takes a few lines of what the scene should show, a rough length, a purpose (a talk, the web, a paper's
still: it sets §7's profile) and the scene's name. A workspace's scenes share `animations/style.py`: colors read from
the paper's plotting style when there is one, the paper's TeX preamble for `MathTex`, the frame (16:9, 1920×1080) and
the smallest text size. "Write the scene" sends the request to the workspace's agent; the scene arrives as a change to
review, with a few lines of beats (`animations/<scene>.beats.md`).

## 6. What Clank records of a run

As with Matplotlib's figures (design 0008 §3), Clank's `sitecustomize` (already on every Python's path in the image)
wraps Manim when Manim is imported, so no scene and no prompt has to know. It records, in
`.clank/animations/<scene>/<version>/timeline.json`:

- **Each call** of `self.play` and `self.wait`: its number, the animations it plays (their classes), its run time and
  rate function, its start and end in the video, the line of the scene's file that called it, and its section
  (`self.next_section`).
- **Each object on screen at the end of each call**: its kind, its text (a `Text`'s words, a `MathTex`'s TeX), its
  color, its box in Manim's units and in grid cells (§10), its height in pixels at 1080p, the line that created it, and
  its names. Names come from the local variables of `construct` at that moment, one level of the attributes an object
  exposes (`axes.y_axis`), and, for an object made in a loop, its place in its group (`copies[2]`), the fallback SGA
  uses too.
- **The data files** the scene read (path, size, checksum).

A run that only records (no video) is a **dry run**: animations are skipped, each call jumps to its end. It takes a
few seconds and is what §7 and §8 use. A render made without the wrapper (Manim run by hand) still plays; its marks are
then given in the frame's own terms.

## 7. Checks before you look

After each dry run, before the owner sees anything, Clank checks two things. Neither needs a model or a render.

- **The API check.** Models mix Manim's two dialects and its versions. Clank reads the scene's code for names that
  Manim 0.22 does not have (ManimGL's `ShowCreation`, `TextMobject`, `self.embed`, `CONFIG` dictionaries; names
  renamed or removed) and answers with the line and the right name. A small table in Clank's code, tested against the
  pinned version, holds them.
- **The layout checks**, from §6's records, at rest (the end of each call), never mid-motion:
  overlap (two boxes intersect; high above 30% of the smaller, medium above 10%, low below), objects past the frame,
  text smaller than the profile allows (a talk: 24 px at 1080p), a curve hidden under another, and animations shorter
  than the profile allows (a talk: 0.5 s). Each finding names its objects, their lines, the call it follows, and the
  smallest move that removes it. Overlaps that are meant are skipped: a box around an object, an arrow pointing at one,
  a label placed with `next_to` on its object; the owner can mark any finding intended, and it stays so for that pair.

High findings go to the agent for **one fix round** before the owner sees the sketch (on by default, a setting);
whatever remains reaches the owner as findings on the timeline, each with "Send to the agent" and "Intended".

## 8. The sketch of the opening

The agent's first version of a scene, and every version until "Animate it", is shown as a sketch: the dry run (§6)
also saves the frame at the end of each call, so the opening becomes a sheet of stills in a second or two at low
resolution. Each still shows its call's number, its line and its time. The owner marks any of them (§10) and sends
the marks; the agent revises; the sketch comes back. The sketch covers the first section by default, or the whole
scene on request.

## 9. The player, the timeline and the frame inspector

The workbench is a webview panel of Clank's extension, opened from a CodeLens line ("Open in the animation
workbench") above each scene class, from "Animate this", or from the command palette. Its parts: the scenes of the
file with their sections and times; the sketch or the player; the timeline; the marks and the agent's answers; the
scene's code beside it in the editor.

- **The player** plays WebM previews (which every VS Code webview can play), steps frame by frame, loops a section and
  shows the time. Keys: Space plays, comma and period step a frame, brackets jump to the previous or next call, L loops
  the section, P B A T pick the pen, box, arrow and text, M pins a comment, Ctrl+Enter sends the marks, Ctrl+Z undoes a
  mark.
- **The timeline** shows one block per call, sized by its run time, with its animation, its line, its rate function
  and any findings (§7) or marks on it. Clicking a block moves the editor to its line; putting the cursor in a call
  lights its block and moves the player there.
- **The frame inspector**: on a paused frame or a still, outlines show every object on screen with its name; hovering
  a name lights it; picking one shows its kind, text, the line that made it, the call that showed it, its box in Manim's
  units and grid cells, and its height at 1080p, with "Go to line". A grid overlay shows the 6×6 cells (§10).

While the workbench is open, saving the scene runs the dry run and checks, then a preview at low quality (480p, 15
frames a second) as a job once the owner has animated it; Manim's own cache renders only the calls whose code or
objects changed.

## 10. Marks, and marks in words

The tools are those of the figure annotator (design 0008 §6): pen, box, arrow, text and numbered comment pins with
their bubbles; undo; a free note for the whole send. Three direct marks are added: **move** (drag a picked object),
**resize** and **recolor** (from the style's colors). A direct mark is a request, not an edit: the agent changes the
code, so nothing moves behind the code's back. A mark belongs to the frame it was drawn on (a still, or a paused
frame, which Clank extracts from the video) and so to a call and a time.

Places are named on a 6×6 grid: columns A to F from the left, rows 1 to 6 from the top (Code2Video's anchors).

The model reads no images, so each mark goes to it as words built from §6's records: its number and kind; the frame
(its time, its call and line, and how far through the call); its place in grid cells and in Manim's units; the
objects it touches or points at, with their names and the lines that made them; for a direct mark, the exact change
(move `title`, line 20, down 0.35 units to y = 3.2); and its words. When the main slot can see images, the marked
frame goes too.

## 11. Timings Clank changes itself

Dragging a block's edge changes its run time, or a wait's length; later blocks move along unless Shift is held
(Motion Canvas's rule). A chip under each block sets its rate function, and "+ hold" adds a wait. When the value in
the code is a literal (`run_time=1.5`, `self.wait(0.5)`, `rate_func=smooth`), Clank edits it itself, with no model, as
a change the owner reviews like any other; the preview renders only that call again. When the value is computed
(`run_time=dur * 2`), the drag becomes a timing mark for the agent with the time wanted. "Pace" scales every run time
and wait of the scene by one factor in one change (a scene made for the web, slowed for a talk).

## 12. The agent's turn

"Send marks to the agent" sends one message to the workspace's agent session:

- what to change (the scene and its file, Manim 0.22) and the rule: change only what the marks and checks ask, and
  answer each by its number, with what changed and on which line, or why not;
- the timeline in short (each call with its time and line), the grid's naming, the marks in words, the open findings,
  the owner's note, and the data files with whether they changed.

The scene's code goes once a session, then only its changes. A message is about a thousand tokens for a scene of ten
calls. The reply is checked: each mark and finding must have an answer; a missing one is asked for once more before the
change reaches the owner. In review mode each change is reviewed as any other (design 0007); once saved, the dry run,
the checks and the sketch or preview run again, as the next version. Nothing is sent while no agent runs; the workbench
says how to start one, and keeps the marks.

## 13. Mark threads

Each mark becomes a thread: the owner's mark, the agent's answer with a link to its change, and the same frame in the
new version beside the old one, with the checks' word on it. The owner resolves the thread or reopens it with a note;
the list filters open, answered and resolved threads. A mark finds its frame in the next version by its call's line;
if the line moved, by the call's place among its neighbors; if the call is gone, the thread says so and shows the
nearest frame. Resolved threads stay with their version, so the reason for a choice can be found later.

## 14. Versions, branches and comparing

Each dry run and render is a version, kept under `.clank/animations/<scene>/<version>/`: its stills or video, its
timeline, the scene's source as it was, its marks and threads, and its data checksums. Versions form a tree: "Branch
from" starts a version from an older one (`v3b`), kept aside. Keep makes a version the one in use; Back offers an
older version's source as a change to review, so going back is never silent. Compare has four views: side by side,
playing in step (both stop at the end of the same call, matched by line), with changed calls marked on both
timelines; overlay at half opacity; difference, changed pixels in color; and a frame strip, the end of every call of
both versions in two rows.

## 15. Data plots, the first use

The first animations the owner wants are data and plots. Two starting scenes, which the agent adapts: a curve that
draws over time from a CSV or JSON file in the folder, and a sweep whose curve moves with a parameter
(`ValueTracker`). Both read their data at render time. Because §6 records the data files a run read, the workbench says
when one changed since the version on screen ("the file changed since this sketch: sketch again"), and every version
and export keeps the data's checksum.

## 16. When a render fails

A failed run or render shows its error in the workbench, with the traceback's lines linked into the scene's code and,
for a `MathTex` error, the lines of the TeX log that say what failed. Where Clank knows the cause, it says so and offers
the exact fix: a macro defined in the paper's preamble that the scene's TeX does not load ("Load the paper's preamble
in style.py"). Otherwise "Ask the agent" sends the error narrow first: the failing line with one line on each side;
if that fails, the call's block with the lines that build its objects; only then the section. The last good version
stays on screen.

## 17. Export and provenance

Export renders from the version's own source: MP4 at 1080p60 or 4K, WebM, MOV with transparency, the whole scene or
each section as a clip; a GIF (720p, 15 frames a second, looping) for a README or a slide; PNG frames at 3840×2160,
the last frame of each section or the frame in the player, named by section. Every exported file gets an
`export.json` beside it: the scene, the version, the source's checksum, the Manim version, each data file's checksum
and the command, so a video in a talk traces back to the code and data that made it. A final render that does not
exist yet runs as a job first.

## 18. Limits

Dry runs, sketches, previews and finals run as jobs in the container (design 0013 §17's machinery: command, log and
exit code under the version's folder), with time limits (a dry run, sketch or preview 2 minutes, a final 30) and a
limit on CPU threads (4 by default) so the model and other jobs keep running. A newer render of the same scene replaces
an older one still running. Versions beyond the last 20 of a scene are removed unless kept. The status bar shows a
running render (`▶ v6 6/7`) and a failed one.

## 19. Later

Not built in the first round; each needs its own approval and, for a new dependency, a decision record (all would live
in the Manim layer, not in Clank):

- **Slides**: each section a click-to-advance slide with Manim Slides, as an HTML page or a PowerPoint file.
- **Narration**: a voice track from a script with a local voice, its bookmarks setting the waits (manim-voiceover).
- **Beamer**: the scene's frames for LaTeX's animate package, to play inside a PDF.
- **A vision model** for marks, once one runs beside the main model (design 0017 §18).

## 20. Tests

Tests come first, as for every part (design 0001 §8.6). Unit tests: the recorder's timeline and objects from a scene
run against a small fake of Manim's `Scene` and `Mobject`; names from locals, attributes and groups; each layout check,
including what counts as intended; the API check's table; marks in words; literal timing edits; thread matching across
versions; versions and going back; export's provenance. The extension's core (the timeline, mark geometry, the grid)
with Node's test runner, as the rest of the extension. Tests marked `manim` run real scenes in the image (dry runs,
sketches, a preview, a cached re-render), on demand and before each release; they also measure §21 step 1's times. The
owner's own test is the last step.

## 21. Build steps

1. The Manim layer: Manim 0.22 and its LaTeX; Manim's examples render; times measured (dry run, sketch, preview,
   final).
2. The recorder: the timeline, objects and names, data files, the stills of a sketch.
3. The checks: the API table and the layout checks.
4. Runs and renders as jobs; versions.
5. The workbench: the start page, the sketch sheet, marks and direct marks, marks in words.
6. The agent's turn: the message, the reply check, the one fix round, review.
7. The player, the timeline and the frame inspector, linked to the code; previews on save.
8. Timings Clank changes itself, and pace.
9. Mark threads; compare, keep, back and branches.
10. Data plots: the two starting scenes and the data checks.
11. Failed renders; export and provenance.
12. The owner's test.
