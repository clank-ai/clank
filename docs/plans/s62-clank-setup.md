# Plan s62: `clank setup`, the checklist and its fixes

Design 0028 §4 and §5, steps S2, S3 and S4 of §8: `clank setup --check` and the console's Setup page say what Clank
needs on this computer, item by item, and what to do about each one that is not done; `clank setup` offers each fix in
order, asking first; the sandbox image is built in the background during the setup. The owner asked for it on
2026-10-27: a setup that is "basically just a plug and play", "EXTREMELY easy for someone to set up on their own without
using an LLM", for local models, OpenRouter keys, or both.

## What exists

- `clank doctor` reads Docker through the platform's adapter without the service (`read_platform`, design 0014 §2):
  Docker Desktop on Windows and macOS, Docker Engine on Linux, whose states are running, stopped, no access (with the
  docker group's words), unsupported (the snap's, rootless) and not installed; Clank never starts Docker Engine.
- The console opens on Add a model while no model is usable (decision 0105); This folder lists what working in a folder
  needs and does each step (`o` builds the sandbox image the first time, as part of opening the workspace).
- The main slot keeps the configuration that last answered a test request (`last_good`); `clank model add` walks Add a
  model in the terminal; the console hands its terminal to a program and takes it back (`clank.console.terminal`).
- The website's installers end with `clank setup --check` where Clank has it, else `clank doctor` (§3).

## Choices made here

- **One checklist, three readers.** `agents/checklist.py` turns facts into the items (their state, their words, their
  fix), a pure function. The service serves it (`GET /setup`, the agents' part, which reads Docker, the runtime, the
  workspaces and VS Code); without the service, `clank setup` reads Docker itself, as the doctor does, and says that the
  model and the folder are told once the service runs. The console's Setup page draws the service's.
- **The order** is the design's but for one swap: Clank's service comes before the sandbox image, which the service
  builds; both come after Docker, so a service started by the setup never starts before this account may use Docker.
- **What its owner runs comes from the platform.** The adapter says how it is set up (`PlatformSetup`: whether it
  starts with the computer, whether this account is in its group) and the commands its owner runs with administrator
  rights (`sudo systemctl start docker`, `sudo systemctl enable docker`, `sudo usermod -aG docker <account>`); Docker
  Desktop has none, since Clank starts it through its own command.
- **Administrator commands run attached to the terminal** (the command's or the console's), so `sudo` or Windows asks
  for the password itself and nothing is captured; Clank never reads, asks for or keeps a password.
- **The Setup page has no key of its own**: F11, the one left, is the terminal's full screen on most terminals. It is
  the last page of the menu, the console opens on it while anything required is missing (decision 0148), and Ctrl+P
  finds it.
- **The sandbox image's build is an operation of its own** (`workspaces.image`), under the lock `workspaces.image`,
  which opening a workspace holds too: started by the setup, it runs in the background while the model is added.

## Tasks

- [x] 1. The platform's setup: `PlatformSetup` and `setup_state()` (Docker Engine: whether systemd starts it with the
  computer, `systemctl show docker.service --property=UnitFileState`; the account in the docker group; the owner's
  commands), the capture tool asking it too, the recording's answer written by hand and said so; tests first.
- [x] 2. The checklist (`agents/checklist.py`): each item of §4 and each Docker state of §5, its words and its fix;
  tests for every state.
- [x] 3. `GET /setup` (the agents' part) and `clank setup --check`, with and without the service: it changes nothing,
  and exits 0 when everything required is done, else 1.
- [x] 4. The console's Setup page (its rows, `m` Add a model, `f` This folder, `r` read again), the menu without the
  planned "Setup guide", and the console opening on it while anything required is missing (decision 0148); frames.
- [x] 5. The fixes (S3): `clank setup` asks about each item not done, in order, showing the exact command; `--yes` does
  the fixes that need no administrator rights and lists the others; administrator commands in the terminal; after
  joining the docker group, log out and in; Docker Desktop through its own start; the service, Add a model in the
  terminal (cloud, local or both), this folder opened; the console's `s` and `t`.
- [ ] 6. The sandbox image in the background (S4): the operation `workspaces.image` (`POST /workspaces/image`), the
  setup starting it and waiting for it before opening the folder, the console's `b`.
- [ ] 7. Docs: design 0028's statuses, getting started's §2 and §3, the console's page, the changelog, the roadmap, the
  indexes and the generated pages.

## Progress

Written 2026-10-27. S2 (tasks 1-4) built the same day: `clank setup --check`, `GET /setup` and the console's Setup page,
the console opening on it while anything required is missing; the docs of task 7 so far. S3 (task 5) built the same
day: `clank setup` offering each fix in order, administrator commands attached to the terminal, `--yes`, and the
console's `s` and `t`.
