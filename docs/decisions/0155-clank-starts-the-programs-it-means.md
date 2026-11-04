# 0155. Clank starts the programs it means: itself with -P, a helper from the PATH alone

- Status: Accepted (the audit of 2026-10-30); revises design 0002 §2.9
- Date: 2026-11-04

## Context

- Clank runs itself again in several places: the service started in the background, the gateway, the docker group's
  run again on Linux, the planning's split pane in Windows Terminal, the model step of `clank setup`, and `clank
  update`'s stop and start. Most of them start in the folder the command was typed in, which is often a project's.
  `python -m clank` puts that folder first on the module path, so a folder named `clank` there would be imported in
  place of the installed package. Only the service's start set a working folder of its own (CLANK_HOME).
- On Windows a program named without its folder (`docker`, `wt`, `nvidia-smi`, `git`, `winget`, `powershell.exe`) is
  looked for in the current folder before the PATH, by Windows itself and by Python's `shutil.which`, unless the
  variable `NoDefaultCurrentDirectoryInExePath` is set.

## Decision

- **Clank runs itself again as `python -P -m clank`** (`clank_command` in `kernel/processes.py`; the gateway with
  `-P` too): `-P` keeps the current folder off the module path. A test fails if any module writes `"-m", "clank"`
  outside that function.
- **The `clank` command sets `NoDefaultCurrentDirectoryInExePath`** on Windows as it starts, unless the person set it,
  so `shutil.which` and every program Clank starts (they inherit it) leave the current folder out of the search.
- **A program named without its folder is found on the PATH alone** on Windows, before it is started, wherever Clank
  starts a program (`resolved`: the kernel's runners, the commands attached to the terminal, the local host's engines,
  the update): one the PATH does not have is missing, as a program that is not installed is.
- **The update's helper is Windows PowerShell from the system's folder**, never one found by name.

## Alternatives considered

- **Start every child in CLANK_HOME**, as the service's start does: right for the background programs, but the split
  pane, the setup's model step and the docker group's run again must start in the person's folder, and the variable
  alone would not cover the module path.
- **Resolve each helper where it is used**: there are dozens of places; one function in the kernel's runners covers
  them, and new code gets it by using the runners.

## Consequences

- A project's folder never changes what Clank runs. A helper installed outside the PATH (Docker Desktop's own folder)
  is still found by its full path, as `find_docker` gives it.
- Windows' own `sudo`, an alias in WindowsApps (`wt`, `winget`) and System32's programs are on the PATH and found there.
