# Clank's TeX layer (design 0020 §3, decision 0134): TeX Live, as Ubuntu 24.04 packages it (TeX Live 2023), on Clank's
# sandbox image, for the LaTeX the agent writes: the checks build it here (latexmk, BibTeX and biber, SyncTeX), mark a
# change (latexdiff) and read a PDF's pages and words (Poppler's pdftoppm and pdftotext). The sets cover articles,
# physics and mathematics papers, TikZ and pgfplots, and documents for LuaLaTeX and XeLaTeX. `BASE` is the sandbox
# image's tag, which Clank gives; the tag of this layer's image is the base's and this folder's checksum.
ARG BASE=clank-sandbox
FROM ${BASE}

USER root
RUN apt-get update \
 && apt-get install --yes --no-install-recommends \
      texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-science \
      texlive-pictures texlive-publishers texlive-bibtex-extra texlive-plain-generic texlive-luatex texlive-xetex \
      biber latexmk latexdiff poppler-utils ghostscript \
 && rm -rf /var/lib/apt/lists/*

# Clank's LaTeX helper: builds in a scratch tree, latexdiff, a PDF's pages and words, SyncTeX (design 0020 §8-§10).
COPY latex_build.py /opt/clank/

USER agent
