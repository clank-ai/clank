# 0032. An engine is built in an environment of its own, under the host's Clank folder, without root

- Status: Accepted
- Date: 2026-10-12
- Decided by: Claude while building M1.4 under the owner's instruction to implement NInfer (2026-10-12), instead of
  installing system packages as root as design 0003 §7.1 had said; the owner can revisit it

## Context
NInfer v1.4 needs CMake 3.28 or newer, GCC with C++20, the CUDA 13.3 toolkit, and FFmpeg's and libcurl's development
files. Ubuntu 22.04's packages are too old for most of them; Ubuntu 24.04's are recent enough, which is why design 0003
§7.1 planned to install them as root in the owner's 24.04 distribution after a question. That distribution turned out
to be in daily use (its home holds the owner's tools and about 100 GB of files), and installing packages as root there
can upgrade shared libraries under the owner's other programs. conda-forge publishes every piece, at the exact
versions NInfer v1.4 was validated with: `cuda-nvcc` 13.3.73 and GCC 15.2.0.

## Decision
- A recipe builds its engine in an environment of its own, in the engine's folder on the host
  (`<Clank folder>/engines/<setup>/<version>/env`), made by micromamba (a single static program, pinned, fetched into
  the same folder) from conda-forge, with the compiler, the build tools, the CUDA toolkit and the libraries at the
  versions the recipe pins. The engine finds that environment's libraries through its run path (the environment's
  compiler sets it), and the GPU driver through WSL.
- An install needs no root and writes nothing outside the host's Clank folder; removing the folder removes it. Its
  steps, and the check of the program it made, run with `HOME` in the engine's folder, since tools write into the
  user's home unasked: micromamba registers its environments in `~/.conda/environments.txt` and keeps a cache in
  `~/.mamba`, CUDA keeps one in `~/.nv`. (The first install on the owner's machine wrote there before this rule; what
  it added to `~/.conda` and `~/.mamba` was removed, and CUDA's own cache, shared with the owner's programs, was left.)
- Design 0003 §7.1 changes accordingly; decision 0031's deviation (GCC 14 instead of 15.2) disappears; decision 0030's
  reason for building NInfer in Ubuntu 24.04 rather than 22.04 no longer holds (either would do), and NInfer stays in
  24.04, where its model already is.

## Alternatives considered
- **System packages as root** (design 0003 §7.1 as written). Changes a distribution the owner uses, needs root, and the
  versions are whatever the distribution has (GCC 13 or 14 rather than 15.2).
- **A container image** (CUDA's devel image). Reproducible too, but the engine would then run in Docker, a host Clank
  does not have yet, and Docker Desktop would have to run for the model to run.
- **Building the toolchain from source.** Hours of building for what conda-forge already builds and signs.

## Consequences
- A recipe pins its environment's packages; the build is reproducible on another machine without its administrator.
- The first install of an engine downloads its environment (about 480 MB for NInfer) besides its source.
- A recipe's steps are run by the host one at a time, each with its output in the install's log; a step that has
  already produced what it makes is skipped, so an install that failed goes on from where it stopped.
