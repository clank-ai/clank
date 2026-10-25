# 0134. The TeX layer: TeX Live from Ubuntu's packages, in an image layer on the sandbox image

- Status: Accepted (with design 0020, approved by the owner on 2026-10-25)
- Date: 2026-10-25
- Decided by: the owner (TeX in the container, LaTeX Workshop for LaTeX), Claude (the packages and the layer)

## Context
- The checks on the LaTeX the agent writes (design 0020 §5-§8) build documents, mark changes and read PDFs; they must
  run where the agent works, in the workspace's container, with the same TeX on every machine, and never need TeX on
  the machine itself.
- Clank adds no dependency without a decision record. TeX Live is large; a workspace that never writes LaTeX should not
  carry it (design 0004 §3: "a second image layer per kind of work, added when first needed").

## Decision
- **Image layers**: a workspace's record names its layers (`layers`); its image is Clank's sandbox image with each layer
  built on it from `clank/components/workspaces/layers/<name>/` (the base's tag as the build argument `BASE`), tagged by
  the base's tag and the layer's files. `clank latex setup` gives a folder's workspace the TeX layer.
- **The TeX layer** installs, from Ubuntu 24.04's packages (TeX Live 2023): `texlive-latex-base`,
  `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-fonts-recommended`, `texlive-science`,
  `texlive-pictures`, `texlive-publishers`, `texlive-bibtex-extra`, `texlive-plain-generic`, `texlive-luatex`,
  `texlive-xetex`, `biber`, `latexmk`, `latexdiff`, `poppler-utils` and `ghostscript` (each under its own free license:
  LPPL, GPL, BSD and others, as Debian lists them), and Clank's build helper.
- The packages are pinned by Ubuntu's release, as the sandbox image's are; a package a document needs beyond them is
  the owner's to add.

## Alternatives considered
- **TeX on the machine** (MiKTeX, TeX Live for Windows): each machine would differ, and the checks could not run where
  the agent works.
- **TeX Live from its own installer (`install-tl`, `tlmgr`)**: newer and pinnable by date, but a larger and slower
  build; Ubuntu's packages are enough for the sets above.
- **`texlive-full`**: about 6 GB, most of it languages and fonts few documents need.
- **TeX in the sandbox image itself**: every workspace would carry about 2 GB more.

## Consequences
- A workspace with the layer runs a larger image (about 2 GB more, measured when first built); it is built once and
  shared by every workspace with the layer.
- A change to the sandbox image or to the layer's folder builds the layer again, as the base is rebuilt.
