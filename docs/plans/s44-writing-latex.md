# Plan s44: writing LaTeX with the agent

Builds [design 0020](../design/0020-writing-latex.md), approved by the owner on 2026-10-25 ("begin building everything
for the latex writing and test everything extensively and push all the changes periodically"). Each task starts with a
failing test; each ends with a commit pushed to `main`.

## Tasks

- [x] 1. **Image layers and the TeX layer** (§3). A workspace's record names its layers (`layers`, empty by default);
  its image is the sandbox image, or, with layers, an image built on it from each layer's Dockerfile
  (`clank/components/workspaces/layers/<name>/`, the base's tag as the build argument `BASE`), tagged by the base's
  tag and the layers' files (`sandbox.layered_tag`). Opening a workspace builds what is missing (asked first) and makes
  its container from it; `runs_current_image` and the folder's view compare with it. `clank latex setup` adds the TeX
  layer to the folder's workspace. Decision 0134 records the layer's packages. Tests: the tag, the build argument, the
  container's image, the record; a real build marked `tex`.
- [ ] 2. **The rule for LaTeX files** (§4): `.tex` files that existed before the agent created them, `.bib` files and
  class and style files are always reviewed, in auto mode too; a `.tex` file the agent created follows the mode.
- [ ] 3. **Citations** (§6): every citation command's keys are entries of the bibliographies the document loads; a new
  `.bib` entry has a DOI or an arXiv id that resolves and matches its title, first author and year (Crossref, arXiv;
  the lookup injected in tests, from recorded answers).
- [ ] 4. **Sources** (§7): a changed paragraph that states a value (a decimal, a percentage, a number in scientific
  notation, an integer of three digits or more that is not a year) carries `% source:` naming a file of the folder, a
  bibliography key, a DOI or an arXiv id, or `% UNVERIFIED:`.
- [ ] 5. **Compiling** (§8): the document's root (its `% !TEX root`, the file itself with `\documentclass`, else the
  file that includes it); a build in the container (`latex_build.py`: a scratch tree of links to the folder's files, the
  changed file written in it, `latexmk` with the document's engine, two minutes); the log's errors, undefined references
  and citations, and labels defined twice, compared with the document's build before the change (kept until a TeX file
  of the folder changes).
- [ ] 6. **The checks in the review** (§5): a LaTeX change is checked before it is asked about or answered, off the
  watcher's thread; a refusal rejects it with its reason, and the third refusal of a file in a row asks the owner with
  it; a check that cannot run (no TeX in the container) asks the owner, saying so; each refusal is an event.
- [ ] 7. **The marked-up PDF** (§9): `latexdiff --flatten` between the root before and after, built in the container
  into `.clank/latex/<change>/diff.pdf`; an event the window follows to open it beside the diff.
- [ ] 8. **Annotating the PDF** (§10): "Annotate this PDF" renders its pages in the container (`pdftoppm`) with each
  page's word boxes (`pdftotext -bbox-layout`), opens them in the figure annotator, and the marks on a page go to the
  agent in words: the words under each, and SyncTeX's file and line.
- [ ] 9. **Annotating the source, and the agent's turn** (§11, §12): comment threads on `.tex` files, sent together;
  each mark and comment numbered; every number answered.
- [ ] 10. **What the agent is told** (§13): Clank's LaTeX rules in the build agent's instructions.
- [ ] 11. **LaTeX Workshop builds in the container** (§3): `clank latex build FILE` builds in the workspace's container
  and writes SyncTeX's paths as the machine's; the window's LaTeX Workshop recipe runs it.
- [ ] 12. **Live tests**: the TeX layer built on this machine; real builds, refusals, the marked-up PDF and a PDF's
  marks in words, end to end through the service.

## Progress

Each task's box is ticked in the commit that finishes it.
