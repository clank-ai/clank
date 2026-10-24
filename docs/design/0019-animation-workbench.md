# Design 0019: the animation workbench

Part of Clank Code ([design 0018](0018-clank-code.md)); it builds on the figure annotator
([design 0008](0008-annotating-figures.md)) and on jobs ([design 0013 §17](0013-flows.md)). Started 2026-10-23 at the
owner's request: "manim animations that we can make together, in fact this is actually the very first thing that I
would like you to design fully and then build when I approve the design so that I can test this out myself." Drawn in
the owner's design canvas "Clank in VS Code" (boards "Animation workbench" and "Animation: sketch of the opening").
Every section is proposed; nothing is built until the owner approves it.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-23 |
| 2 | The owner's choices | Recorded 2026-10-23 |
| 3 | Manim in the container | Proposed 2026-10-23 |
| 4 | What Clank records of a render | Proposed 2026-10-23 |
| 5 | The sketch of the opening | Proposed 2026-10-23 |
| 6 | The player and the timeline | Proposed 2026-10-23 |
| 7 | Marks, and marks in words | Proposed 2026-10-23 |
| 8 | The agent's turn | Proposed 2026-10-23 |
| 9 | Renders, versions and comparing | Proposed 2026-10-23 |
| 10 | Data plots, the first use | Proposed 2026-10-23 |
| 11 | When a render fails | Proposed 2026-10-23 |
| 12 | Limits | Proposed 2026-10-23 |
| 13 | Tests | Proposed 2026-10-23 |
| 14 | Build steps | Proposed 2026-10-23 |

## 1. What the owner gets

A Manim scene file opens in Clank's animation workbench beside its code. The owner describes an animation; the agent
writes the scene and first sketches its opening as one still per animation, which the owner marks up (pen, box, arrow,
text, numbered comment pins). The marks go to the agent in words; the agent changes the code; the owner reviews each
change, and the sketch or the preview renders again in seconds, since only the animations whose code changed are
rendered anew. When the opening is right, "Animate it" renders the video: a player with a timeline of one block per
`self.play` or `self.wait`, each linked to its line of code both ways, where the owner pauses on any frame and marks it
the same way. Every render is a version that can be compared with another, side by side and in step, kept, or gone
back to. Final renders export as MP4, GIF or a frame for the paper.

## 2. The owner's choices

- **Manim Community** (v0.19 at the time of writing), not ManimGL.
- **Rendering in the project's container**: Manim and its LaTeX in Clank's sandbox image, renders run as jobs.
- **First use: data or a plot** (§10).
- **Straight to code, the opening sketched first**: "it should sketch the beginning out in detail first and provide a
  way for me to annotate different frames" (§5).
- The figure loop's spirit holds here: "a simple annotation setup that will let me draw, add comments, and so on", with
  the user experience "prioritized alongside the usability and reliability of the implementation".

## 3. Manim in the container

Manim comes as a second image layer on Clank's sandbox image (design 0004 §3's "a second image layer per kind of work,
added when first needed"): `clank image add manim`, asked the first time a workspace opens the workbench. The layer
holds Manim Community, pinned, and what it needs to render text and formulas: Cairo and Pango, FFmpeg, and a TeX Live
set for `MathTex` (LaTeX and `dvisvgm`). The exact packages are fixed when the layer is built and checked by rendering
Manim's own example scenes; its size is measured then (expected 1 to 2 GB). A workspace that never uses Manim does not
carry it. Rendering uses the CPU; the GPU stays the model's.

## 4. What Clank records of a render

As with Matplotlib's figures (design 0008 §3), Clank's `sitecustomize` (already on every Python's path in the image)
wraps Manim when Manim is imported, so no scene and no prompt has to know. For each `self.play` and `self.wait` it
records, in `.clank/animations/<scene>/<render>/timeline.json`:

- its number, its kind, the animations it plays (their classes), its run time and so its start and end in the video;
- the line of the scene's file that called it, and the section (`self.next_section`) it is in;
- at its end, each object on screen: its kind, its text (a `Text`'s words, a `MathTex`'s TeX), its color, its box in
  the frame and in Manim's own units, and the names the scene's code gives it (the variables bound to it where the call
  was made);
- the data files the scene read during the render (path, size, checksum).

A render made without the wrapper (Manim run by hand) still plays; its marks are then given in the frame's own terms.

## 5. The sketch of the opening

The agent's first version of a scene is shown as a sketch before any video: Manim runs with animations skipped (each
`self.play` jumps to its end), and the wrapper saves the frame at the end of each one, so a scene's opening becomes a
sheet of stills in a second or two at low resolution. Each still carries its animation's number, its line and its time.
The owner marks any of them (§7) and sends the marks; the agent revises; the sketch renders again. "Animate it" renders
the video once the opening is right. The sketch covers the first section by default, or the whole scene on request.

## 6. The player and the timeline

The workbench is a webview panel of Clank's extension, opened from a CodeLens line ("Open in the animation workbench")
above each scene class, or from the command palette. Its parts: the scenes of the file with their sections and times;
the player (play, frame by frame, loop a section, the time); the timeline, one block per call, labeled with its
animation and line, a block holding marks drawn in the owner's color; the scene's code beside it.

Clicking a block moves the editor's cursor to its line; putting the cursor in a `self.play` call lights its block and
moves the player there. Previews play as WebM, which every VS Code webview can play; exports are MP4 and GIF. While the
workbench is open, saving the scene renders a new preview at low quality (480p, 15 frames a second), as a job;
Manim's own cache renders only the calls whose code or objects changed.

## 7. Marks, and marks in words

The tools are those of the figure annotator (design 0008 §6): pen, box, arrow, text and numbered comment pins with
their bubbles; undo; a free note for the whole send. A mark belongs to the frame it was drawn on (a still of the sketch,
or the paused frame of the player, which Clank extracts from the video as an image) and so to an animation and a time.

The model reads no images, so each mark goes to it as a sentence built from the timeline (§4): its number and kind,
the frame (its time, its animation and line, and how far through the animation it is), its place in Manim's units, the
objects it touches or points at with their names and the lines that made them, and its words. For example: *Mark 1
(arrow), frame 3 at 0:04.0, end of animation 3 (`Create(warm)`, line 24): points at the y axis of `axes` (line 16);
"Log scale, and start it at 1e-1".* When the main slot can see images, the marked frame goes too.

## 8. The agent's turn

"Send marks to the agent" sends one message to the workspace's agent session: the scene and its file, the marks in
words, the note, and the timeline in short (each block with its line), with the instruction to change only what the
marks ask and to say which mark each change answers. In review mode each change is reviewed as any other (design
0007); once the file is saved, the sketch or the preview renders again, as the next version. Nothing is sent while no
agent runs; the workbench says how to start one.

## 9. Renders, versions and comparing

Each render is a version, kept under `.clank/animations/<scene>/v<n>/`: its video or stills, its timeline, the scene's
source as it was, and its marks. Compare plays two versions side by side in step; Keep makes a version the one in use;
Back offers the old version's source as a change to review, so going back is never silent. "Render final" renders
1080p at 60 frames a second, as a job with its log; Export writes MP4, GIF, or the last frame as PNG or PDF for a paper.

## 10. Data plots, the first use

The first animations the owner wants are data and plots. Clank gives the agent two starting scenes it may adapt: a
curve that draws over time from a CSV or JSON file in the folder, and a sweep whose curve moves with a parameter
(`ValueTracker`). Both read their data at render time. Because the wrapper records the data files a render read (§4),
the workbench says when one changed since the version on screen ("the file changed since this sketch: re-sketch"),
and the version keeps the data's checksum, so a figure in a talk can always be traced to the data that made it.

## 11. When a render fails

A failed render shows its error in the workbench, with the traceback's lines linked into the scene's code and, for a
`MathTex` error, the part of the TeX log that says what failed. "Ask the agent to fix it" sends the error with the
scene's code. The last good version stays on screen.

## 12. Limits

Renders run as jobs in the container (design 0013 §17's machinery) with time limits (a sketch or a preview 2 minutes,
a final render 30), and a limit on CPU threads so the model and other jobs keep running. A newer render of the same
scene replaces an older one still running. Versions older than the last 20 of a scene are removed unless kept.

## 13. Tests

Tests come first, as for every part (design 0001 §8.6). Unit tests: the wrapper's records from a scene run against a
small fake of Manim's `Scene`; timeline times; marks in words from recorded objects; versions and going back. The
extension's core (its timeline, its mark geometry) with Node's test runner, as the rest of the extension. Tests marked
`manim` render real scenes in the sandbox image, run on demand and before each release. The owner's own test is the
last step.

## 14. Build steps

1. The image layer: Manim and its LaTeX; Manim's examples render.
2. The wrapper: the timeline and the stills of a sketch.
3. Renders as jobs; versions.
4. The workbench: the sketch sheet with marks, and marks in words.
5. The agent's turn, with review.
6. The player and the timeline, linked to the code; previews on save.
7. Compare, keep, back; final render and export.
8. Data plots: the two starting scenes and the data checks.
9. Failed renders.
10. The owner's test.
