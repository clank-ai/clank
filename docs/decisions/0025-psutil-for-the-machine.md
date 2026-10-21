# 0025. The machine and its processes are read with psutil

- Status: Accepted
- Date: 2026-10-11
- Decided by: proposed by Claude in the M0.3 plan, under the owner's instruction to "plan and build M0.2 and everything
  else we have scheduled" (2026-10-11); the owner can revisit it

## Context
The machine profile needs the memory, the processor's cores and the free disk (design 0001 §2), on Windows and Linux
alike. From M1 the kernel identifies the processes it starts by their id, start time and command line, and reports the
program that holds a port or the GPU instead of touching it (design 0001 §4.6, design 0002 §2.9).

## Decision
psutil reads the machine (memory, cores, disks) and, from M1, its processes. Its type stubs (`types-psutil`) join the
development tools, so the type check covers its use.

## Alternatives considered
- **Each platform's own commands** (PowerShell, `/proc`, `ps`). No dependency, but more code per platform, slower,
  and fragile when a command's output changes.
- **The standard library** (`os.cpu_count`, `shutil.disk_usage`). Covers part of it, but not the memory on every
  platform, nor a process's start time and command line.

## Consequences
- One dependency, with built wheels for Windows, Linux and macOS, serves the machine component now and the runtime in
  M1.
