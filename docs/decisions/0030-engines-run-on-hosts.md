# 0030. The service stays on Windows; engines run on hosts, WSL distributions first

- Status: Accepted
- Date: 2026-10-12
- Decided by: proposed by Claude in design 0003 §2, under the owner's instruction to build M1 (2026-10-12); refines
  design 0001 §7.1; the owner can revisit it

## Context
Design 0001 §7.1 put the service and the engines inside WSL on Windows. M0 built the service natively on Windows,
because the console, VS Code, Docker Desktop and the machine's own settings (GPU scheduling, the driver) are Windows
programs and settings; M0.3 left to M1 where the engines run. Engines need a Linux userland with CUDA, and a model
file on the same disk as the engine (loading 16 GB across WSL's bridge to Windows' disks is much slower). On this
machine the two engines need different Linux releases: KVMem is built in Ubuntu 22.04, and NInfer's build needs
packages only Ubuntu 24.04 has.

## Decision
- The service stays where it is started: natively on Windows here, natively on Linux elsewhere.
- An engine runs on a **host**, a kind of adapter (design 0002 §2.10) that can run a command, start a long-running
  process in a session of its own with its output in a log, tell whether it still runs (by process id, start time and
  command line), signal it, and read a file. The first two: `local` (the service's own Linux) and `wsl` (a WSL
  distribution, through `wsl.exe -d <distro>`). SSH to another computer comes later.
- Each host has a Clank folder of its own (`~/.clank` by default) for engines and models; logs and state stay in
  CLANK_HOME.
- WSL forwards each engine's port to Windows' `127.0.0.1`, where the service and the prototype's tools reach it.

## Alternatives considered
- **Move the service into WSL** (design 0001 §7.1 as written). Docker Desktop's and Windows' settings, the console in
  Windows Terminal and VS Code's local side would then cross the boundary instead; and one distribution would have to
  suit every engine.
- **Run engines in Docker containers.** Reproducible and needs no root in a distribution, but every engine would need
  an image and GPU access through Docker Desktop, and KVMem runs in a distribution today. A container host can be a
  third adapter later.

## Consequences
- Engines are reached and stopped through `wsl.exe`; their identity is checked inside the distribution.
- A preset names its engine; its install names its host, so the same engine can be installed on several hosts.
- Design 0001 §7.1's table now reads: on Windows with WSL2, the service runs on Windows and the engines in WSL.
