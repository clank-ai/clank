# 0138. Scientific Python in the sandbox image, from Ubuntu's packages

- Status: Accepted
- Date: 2026-10-26
- Decided by: the owner ("please be sure to install matplotlib and any other package we may need", 2026-10-26),
  Claude (the set and how)

## Context

In the first live test of boards (design 0022), the local model was asked to plot two data files. Matplotlib was not
in the workspace's container, so it wrote the plots as SVG by hand. A workspace's container cannot download anything
(design 0004 §10): a folder's own packages come from its setup, and a folder with no `pyproject.toml` or
`requirements.txt` has none. Research folders are often just data and scripts.

## Decision

- Clank's sandbox image installs, from Ubuntu 24.04's packages: `python3-numpy`, `python3-scipy`, `python3-pandas`,
  `python3-matplotlib` and `python3-sympy` (each under its own free license, as Debian lists them: BSD, PSF-based and
  others), pinned by Ubuntu's release as the image's other packages are.
- A workspace's setup makes its environment with `--system-site-packages`, so it sees these and installs a folder's
  own versions over them where the folder asks for others.
- Matplotlib being there turns on the figure geometry Clank's `sitecustomize` writes for the annotator (design 0008 §3).

## Alternatives considered

- **pip in the image** (newer versions, NumPy 2): needs `--break-system-packages` or a second environment, and its
  own pins; Ubuntu's packages are tested together.
- **A layer** (as TeX is, decision 0134): plotting is wanted in nearly every research folder; a layer would be asked
  for every time, and the set is about 250 MB, not TeX's 2 GB.
- **The folder's setup only**: a folder of data and scripts has nothing to propose, so the agent would have nothing.

## Consequences

- The sandbox image is built again once, about 250 MB larger; the TeX layer is built again on it.
- A folder that needs newer versions lists them (`requirements.txt`, `pyproject.toml`) and its setup installs them in
  its environment, over the image's.
