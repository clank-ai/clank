# Design 0020: writing LaTeX with the agent

Part of Clank Code ([design 0018](0018-clank-code.md)). Started 2026-10-25 at the owner's request: "we need to add the
ability for the model to write Latex documents for me as well but we need to be very, very careful with the way that we
allow the model to write latex documents and I also need the ability to very carefully annotate the latex documents
that it may end up making so that we can change certain things." Diagrams come later (§17). Approved by the owner on
2026-10-25 ("begin building everything for the latex writing"); built by [plan s44](../plans/s44-writing-latex.md).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Approved 2026-10-25 |
| 2 | The owner's choices | Recorded 2026-10-25 |
| 3 | TeX in the container | Approved 2026-10-25 |
| 4 | Which files the model may write | Approved 2026-10-25 |
| 5 | The checks on every change | Approved 2026-10-25 |
| 6 | Citations and the bibliography | Approved 2026-10-25 |
| 7 | Claims and their sources | Approved 2026-10-25 |
| 8 | Compiling clean | Approved 2026-10-25 |
| 9 | Seeing a change | Approved 2026-10-25 |
| 10 | Annotating the PDF | Approved 2026-10-25 |
| 11 | Annotating the source | Approved 2026-10-25 |
| 12 | The agent's turn | Approved 2026-10-25 |
| 13 | What the agent is told | Approved 2026-10-25 |
| 14 | Limits | Approved 2026-10-25 |
| 15 | Tests | Approved 2026-10-25 |
| 16 | Build steps | Approved 2026-10-25 |
| 17 | Later: diagrams | Approved 2026-10-25 |

## 1. What the owner gets

The agent writes LaTeX: new documents, and changes to the owner's own, which the owner reviews one by one. Before a
change reaches the owner, Clank checks it: every citation is an entry of the owner's bibliography, every number and
result carries its source, and the document still compiles with no new undefined references or citations. A change
that fails a check never reaches the owner: the agent gets the reason and fixes it. A change that passes shows as the
source's diff beside a PDF with the change marked (removed text struck in red, new text in blue). The owner marks up
the compiled PDF (highlight, strike, insert here, a box around an equation or a figure, comment pins) or comments on
lines of the source; each mark goes to the agent in words, with the text under it and the line of the source it comes
from, and the agent answers each by its number.

## 2. The owner's choices

- **Which files**: the model creates new documents, and proposes changes to the owner's existing `.tex` files, each
  reviewed by the owner before it is written, even when the workspace is in auto mode (§4).
- **Guarantees Clank enforces**: no invented citations (§6); claims tied to sources (§7); it must compile clean (§8).
  ("Only what you asked", limiting a change to the part the owner pointed at, was not chosen; §12 asks it of the agent
  without enforcing it.)
- **Annotating**: on the PDF and on the source, both (§10, §11).
- **Seeing a change**: the source diff and a marked-up PDF, both (§9).
- LaTeX builds on the LaTeX Workshop extension (design 0018 §2).

## 3. TeX in the container

TeX runs in the project's container, never needing TeX on the machine: a second image layer (design 0004 §3), `clank
image add tex`, offered the first time a workspace has a `.tex` file the agent writes, and shared with the Manim layer
(design 0019 §4). It holds a TeX Live set with `latexmk`, `synctex`, `latexdiff`, `biber` and BibTeX, and Poppler's
`pdftoppm` and `pdftotext`; the packages a document needs beyond the set are installed with `tlmgr` into the layer, as
a change the owner approves. Clank's VS Code window sets LaTeX Workshop to build in that container (its Docker
setting), so the owner's own builds and Clank's checks use the same TeX. Each package is pinned to the TeX Live year;
the layer's packages get a decision record before they are built (as decision 0133 did for Manim's).

## 4. Which files the model may write

Clank's review of the agent's changes (design 0007) gains a rule for LaTeX:

- **A `.tex` file that existed before the agent's session** (the owner's): every change is reviewed by the owner, in
  review and in auto mode alike. The rule is Clank's, in the review; the agent cannot turn it off.
- **A `.tex` file the agent created**: it follows the workspace's mode, as any file (review: reviewed; auto: written
  once it passes §5's checks). (Claude's call: the owner chose "new files freely, still reviewed"; in auto mode a new
  document's changes are checked but not each asked about. The owner may say otherwise.)
- **A `.bib` file**: always reviewed, and each new entry checked (§6).
- **Class and style files** (`.cls`, `.sty`, `.bst`) and the TeX layer: always reviewed.

Every `.tex`, `.bib`, `.cls`, `.sty` and `.bst` change, the agent's or proposed, passes §5's checks before it is asked
about or written.

## 5. The checks on every change

When the agent asks to write a LaTeX file (OpenCode's edit or write permission, design 0007), Clank checks the file as
it would be after the change, before asking the owner or answering in auto mode: citations (§6), sources (§7), and
compiling (§8), in that order, the cheapest first. A failed check rejects the permission with its reason, in words the
model can act on, so the model fixes the change and asks again; the owner sees nothing of it but a count in the review's
status ("2 changes refused by the checks: undefined citation; no source"), each refusal kept with the change. After
three refusals of the same file in a row, the owner is asked with the last refusal shown, so a model that cannot get it
right does not loop.

## 6. Citations and the bibliography

Every citation command in the changed file (`\cite` and its natbib and biblatex forms: `\citep`, `\citet`,
`\parencite`, `\textcite`, `\autocite`, `\citeauthor`, `\citeyear`, `\nocite`, with any optional arguments) names keys;
each key must be an entry of a bibliography the document loads (`\bibliography{...}`, `\addbibresource{...}`), read from
its `.bib` files. A missing key refuses the change: "`\cite{smith2021}` on line 142: refs.bib has no entry smith2021;
cite an entry that is there, or propose the entry with its DOI or arXiv id".

The agent may propose a new `.bib` entry only with a DOI or an arXiv id. Clank looks it up (Crossref for a DOI, arXiv for
an id: the query leaves the computer, the document does not, as the owner allowed for literature in design 0018 §2) and
compares the entry's title, first author and year with what it finds; a mismatch, or an identifier that does not
resolve, refuses the entry, saying what the record says. A matching entry is still reviewed by the owner, with what the
lookup found beside it. An entry without either identifier (a book, a talk) is never added by the agent: it asks the
owner to add it.

## 7. Claims and their sources

A paragraph the change adds or alters that states a value carries its source in a comment within the paragraph. A value
is a decimal (`0.104`, `-1.2732(4)`), a percentage, a number in scientific notation (`3.2e-4`, `3.2	imes 10^{-4}`), or
an integer of three digits or more that is not a year; small integers (`$N = 16$`, `$x^2$`, "Section 2") are not, nor
is anything inside a label, a reference or a citation key, nor a comment. (Claude's call when building: "a number" as
the design first said would flag every exponent; the owner may widen it.)

```latex
The ground-state energy is $E_0 = -1.2732(4)$. % source: runs/vmc-l16/summary.json
```

A source is a file of the folder (it must exist), a citation key of the bibliography (it must be an entry), a DOI or
an arXiv id. A paragraph whose claim is not checked is marked `% UNVERIFIED: <what is not checked>` instead (design
0018 §4), so it is never mistaken for a checked one; the marks are counted in the review and shown highlighted in the
marked-up PDF. A paragraph with neither refuses the change, naming it.

## 8. Compiling clean

Clank compiles the document as it would be after the change, in a scratch copy of the folder in the container
(`latexmk` with the document's own engine, non-stop, halting on the first error, at most two minutes), and the document
as it is now, once, for comparison (kept until a file it reads changes). The change is refused when the build fails (the
first error and its lines in the log), or when the log has an undefined reference, an undefined citation, or a label
defined twice that the build before it did not have. Warnings the document had already do not refuse it. The root
document is the one LaTeX Workshop builds (its magic comment `% !TEX root`, else the file with `\documentclass`
including the changed file).

## 9. Seeing a change

A change that passed the checks opens as today's review (design 0007): the source's diff in the files' group, Accept
and Reject. Beside it, once built, the marked-up PDF: Clank runs `latexdiff` (with `--flatten`, so `\input` files are
followed) between the document before and after, compiles the result in the container, and opens it at the first
change's page. The PDF follows the diff: it is built as a job and shows when ready; the review does not wait for it. A
latexdiff that fails (it can on unusual macros) says so, and the source diff stands alone.

## 10. Annotating the PDF

"Annotate this PDF" (a command, and a button beside a compiled document) shows its pages, rendered in the container
(`pdftoppm`), in Clank's annotator (design 0008 §6), page by page, with its tools and four more for text: highlight,
strike, insert here (a caret), and a box. Each mark is mapped to the source:

- **where it comes from**: SyncTeX, from the mark's page and position, gives the source file and line;
- **what is under it**: Poppler's word boxes (`pdftotext -bbox-layout`) give the words the mark covers, or, for a box
  around an equation or a figure, the equation's source lines or the figure's file and caption.

Each mark goes to the agent in words: "Mark 2 (strike) on page 3, §2.1 *Main result*, main.tex lines 142-143: strikes
'which is clearly optimal'; 'not clear: say why'". The marks of a send, the note, and the PDF's version are kept in
`.clank/annotations/`, as figures' are.

## 11. Annotating the source

On a `.tex` file, the owner comments on a line or a selection (VS Code's comment threads); "Send comments to the agent"
sends them, each with its file, its lines and the text it covers, in the same message as any PDF marks. A comment
thread shows the agent's answer when it comes, and is resolved by the owner.

## 12. The agent's turn

Marks and comments go in one message, numbered: each with where it is (page, section, file, lines), the text under
it, and the owner's words, and the rule: change only what the marks ask, answer each by its number with the lines
changed or why not. The answer is checked as in design 0019 §12: each number answered, a missing one asked for once
more. Each change it makes goes through §5 and §9.

## 13. What the agent is told

Clank's instructions to the agent (the build agent's, beside its other instructions) say how Clank treats LaTeX: cite
only entries of the bibliography, propose a new entry only with a DOI or an arXiv id, put `% source:` on each number or
result, `% UNVERIFIED:` on a claim not checked, compile clean, keep the document's macros and style, and change what was
asked. The checks enforce the first four; the instructions save the refusals.

## 14. Limits

A check never edits the document: it refuses with a reason, or passes. Builds run as jobs in the container, two
minutes each, one at a time per workspace. A document whose build needs the network, shell escape (`--shell-escape`) or
a package not in the layer is refused with that reason until the owner allows it (shell escape is never allowed for
the scratch builds). Lookups of DOIs and arXiv ids are cached; with no network, a new `.bib` entry waits for the owner.

## 15. Tests

Tests come first (design 0001 §8.6). Unit tests: the citation reader (every command form, optional arguments, several
keys, comments skipped) and the bibliography reader; the source rule (numbers, labels and references told apart; a
source that exists, one that does not; `% UNVERIFIED`); the compile comparison, from logs recorded from real builds;
the rule of §4 (existing, created, `.bib`, auto mode); the refusal messages and the three-refusal ask; marks in words
from recorded SyncTeX and word-box answers; the lookup against recorded Crossref and arXiv answers (no network in the
tests). Tests marked `tex` run real builds, latexdiff and SyncTeX in the layer, on demand and before each release.

## 16. Build steps

1. The TeX layer and LaTeX Workshop building in it; its packages' decision record.
2. The review's rule for LaTeX files (§4).
3. The citation check and the bibliography lookup (§6).
4. The source check (§7).
5. The compile check (§8).
6. The marked-up PDF beside the diff (§9).
7. Annotating the PDF (§10).
8. Comments on the source, and the agent's turn (§11, §12).
9. The agent's instructions (§13).
10. The owner's test: a short document written with the agent from a few results files, changed by marks on its PDF.

## 17. Later: diagrams

Diagrams made with the agent (TikZ, and others the owner names), with the same checks and the figure annotator, are a
design of their own, after this one.
