# 0031. NInfer's version follows the CUDA the driver runs: v1.4 with CUDA 13.3.73 on this machine

- Status: Superseded by [0034](0034-ninfer-is-retired.md) (NInfer retired); its compiler deviation was gone since
  [0032](0032-engines-build-in-environments-of-their-own.md)
- Date: 2026-10-12
- Decided by: the owner: "make sure you are implementing ... NInfer (either https://huggingface.co/ninfer-5080 or
  whatever version is perfectly suited for my machine)" (2026-10-12); the version chosen by Claude in design 0003 §5;
  the owner can revisit it, and updating the driver changes the answer

## Context
Decision 0010 asks for NInfer RTX 5080 exactly as published, and records any deviation the machine forces. The current
release, v1.5, is built and qualified with CUDA 13.4.92 on driver 615.71. This machine's Windows driver (610.88) runs
CUDA 13.3 at most. v1.4, the release before, was validated with CUDA 13.3.73 (its reproduction guide at its tag), with
the same model file. Both were built with GCC 15.2; Ubuntu 24.04, where NInfer builds here, has GCC 14.

## Decision
- The NInfer adapter's recipe for a machine is the newest release whose CUDA the driver runs: here v1.4, built with
  the CUDA 13.3.73 toolkit, from the commit its release names (`d5ee1bf`).
- v1.5's recipe is kept beside it; `clank doctor` says that a driver of 615.71 or newer would run it as published.
- Deviations recorded with the install: GCC 14 instead of 15.2. Recorded with the known-good preset: the KV capacity
  that fits beside this machine's desktop instead of 131,072 (design 0003 §5).

## Alternatives considered
- **v1.5 built with CUDA 13.3.** Its retuned kernel was tuned for 13.4; the combination was never qualified by its
  author, so a fault would be ours to find.
- **v1.5 built with CUDA 13.4, run on the 13.3 driver** (CUDA's minor-version compatibility). Works for some programs,
  fails for others at run time; an unknown risk on a 16 GB card with no room to spare.
- **Ask the owner to update the driver first.** A driver update is the owner's to make; M1 should not wait on it.

## Consequences
- After a driver update, installing v1.5 and switching to it is an ordinary upgrade (design 0001 §7.4).
- The fixtures of NInfer's adapter are recorded from v1.4.
