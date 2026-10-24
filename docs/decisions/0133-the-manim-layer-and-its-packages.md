# 0133. The Manim layer and its packages: Manim, Manim Slides, manim-voiceover and a local Kokoro voice

- Status: Proposed (with design 0019; the owner's choices of 2026-10-23: Manim Community, rendering in the project's
  container, and slides, narration and Beamer in the first build)
- Date: 2026-10-23
- Decided by: the owner (the choices), Claude (the packages)

## Context
- The animation workbench (design 0019) renders Manim scenes in the project's container, makes slides of them, adds a
  narrated voice, and exports frames for a Beamer PDF.
- Clank adds no dependency without a decision record. These packages do not go into Clank's own package: they live in
  an image layer Clank builds on the user's machine only when a workspace first uses the workbench (design 0004 §3).
- A voice must run on the computer, on the CPU (the GPU is the model's), and sound good enough for a talk.

## Decision
The Manim layer (`clank image add manim`) holds, each pinned:
- **Manim Community 0.22.0** (MIT; 2026-10-08), with Cairo, Pango and FFmpeg, and a TeX Live set for `MathTex`
  (LaTeX, `dvisvgm`, and the `animate` package for Beamer).
- **Manim Slides 5.7.0** (MIT; 2026-09-14): a scene's slides from `Slide` and `self.next_slide()`, converted to an HTML
  page (reveal.js) or a PowerPoint file.
- **manim-voiceover 0.4.0** (MIT; 2026-06-14): a scene's narration as `with self.voiceover(text=...)` blocks whose
  audio sets the animations' times, with bookmarks inside the text.
- **kokoro-onnx 0.6.1** (MIT; 2026-08-19) with the **Kokoro-82M** voice model, v1.0 (Apache-2.0; 326 MB at full
  precision, 164 MB in half precision, 114 MB quantized; its voices 28 MB): a natural voice on the CPU through
  onnxruntime, without PyTorch. Which precision is the default is settled by listening and timing in build step 1. Clank supplies the speech service manim-voiceover calls; it
  speaks a block's text piece by piece between bookmarks, so each bookmark's time is exact without a transcription
  model.

## Alternatives considered
- **ManimGL**: the owner chose Manim Community.
- **Piper** for the voice: faster and smaller, but less natural; GPL-3.0. Kept as a fallback if Kokoro is too slow on
  a machine.
- **Kokoro on PyTorch**: the same voice, but PyTorch adds far more to the layer than onnxruntime does.
- **Whisper for bookmark times** (manim-voiceover's own way): a second model and PyTorch; speaking piece by piece
  gives the same times.
- **A cloud voice** (Azure, OpenAI, ElevenLabs): the narration's text would leave the computer.

## Consequences
- The layer grows by onnxruntime, the voice model and Manim Slides' converters; the size is measured when it is first
  built (design 0019 §4). Kokoro uses espeak-ng and phonemizer (GPL-3.0) for pronunciation; they run in the user's own
  container and are not distributed with Clank.
- Each version is pinned; moving to a newer one is a change with its own check (Manim's examples, a voiced scene, a
  slide export).
