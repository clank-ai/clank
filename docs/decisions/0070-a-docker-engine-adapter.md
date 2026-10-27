# 0070. A Docker Engine adapter: Clank reports the engine's state, never wakes or starts it, and never runs sudo

- Status: Accepted at the owner's instruction (2026-10-27), with design 0014's recommended choices: its first recording
  is made by the hand-run job (design 0014 §2); built with plan s9's lane L
- Date: 2026-10-18; accepted 2026-10-27
- Decided by: proposed by Claude from the research of 2026-10-18 for running Clank on a Raspberry Pi 5
  ([design 0014](../design/0014-linux-and-small-machines.md) §2); accepted when the owner told the agents to build
  lane L for Linux x64 (2026-10-27: "I want to begin testing clank by itself on a completely separate linux computer
  that I have where I will only be testing the integration with the API keys from openrouter, so we need to make sure
  that this is completely set up and ready for testing")

## Context
- Clank runs containers through one adapter, Docker Desktop's
  (`clank/components/workspaces/adapters/__init__.py:10-15`). Its setting names no other
  (`clank/components/workspaces/kinds.py:25-28`).
- Docker Desktop for Linux is made for x86-64 only (https://docs.docker.com/desktop/setup/install/linux/). On a
  Raspberry Pi 5 (arm64), containers run in Docker Engine, installed from Docker's packages
  (https://docs.docker.com/engine/install/debian/).
- Without the `docker desktop` command, today's adapter says "unsupported"
  (`clank/components/workspaces/adapters/docker_desktop.py:132-137`), and no workspace opens. The doctor still passes
  "Docker installed", and it tells a user who may not use Docker to start it
  (`clank/components/machine/checks.py:149-159`). The command runner it uses keeps no error text
  (`clank/kernel/processes.py:78-82`).
- Docker Desktop is an application its user runs. Clank starts and stops it with Docker Desktop's own command
  (`clank/components/workspaces/adapters/docker_desktop.py:169-188`). Docker Engine is a system service: starting or
  stopping it takes root's rights (`sudo systemctl start docker`).
- Docker's socket is open to root and to the `docker` group only (https://docs.docker.com/reference/cli/dockerd/). A
  user outside the group gets "permission denied". Joining the group gives root-level rights on that computer
  (https://docs.docker.com/engine/install/linux-postinstall/). A process keeps the groups it started with, so a Clank
  service started before its user joined the group still has no access afterward.
- Under systemd, Docker's packages start the engine through socket activation (`dockerd -H fd://`, the dockerd
  reference above). So any `docker` command sent to a stopped engine can start it again while its socket listens, and
  `sudo systemctl stop docker` stops the service but leaves the socket listening.
- Clank sends `docker` commands from three places. The adapter reads the state every 5 seconds and runs the container
  commands. The machine meters run `docker stats` every 10 seconds while the service runs
  (`clank/components/machine/meters.py:180-197, 214-220`). The doctor runs `docker info`
  (`clank/components/machine/checks.py:155-159`). Only the adapter knows Docker's state.
- The `docker` command talks to the engine that `DOCKER_HOST` names, else to the one its current context names.
  Docker Desktop for Linux makes its own context current while it runs (the install page above).
- Every container command Clank sends is Docker's plain CLI, the same for both programs
  (`clank/components/workspaces/adapters/docker_desktop.py:219-342`).

## Decision
1. **One base for the plain docker CLI.** The container commands move from `DockerDesktop` into a base class that
   both adapters share. Nothing changes in behavior.
2. **A `docker-engine` adapter, for Linux.** It reads the engine's state and never changes it.
   - It asks systemd first, when systemd knows Docker's service (`systemctl show docker.service`, its load and active
     states). Any user may ask, and asking starts nothing. Starting, stopping, stopped and failed come from there.
   - **No command reaches an engine that systemd says is not active.** Every command the adapter sends to the engine
     asks systemd first (a reading from the last second is reused). That covers the commands it runs, those it follows
     (a build, a setup) and those it hands back for another to run (`docker exec`). When the service is not active,
     nothing is sent, and the adapter refuses with the command to start Docker.
   - Only an active engine is asked through `docker` (`docker version`), and Docker's whole answer is kept. Running
     gives the engine's versions and containers. "permission denied" gives the state `no access`. Its detail says to
     join the `docker` group (`sudo usermod -aG docker $USER`), log in again and restart Clank's service, and that the
     group is equivalent to root on that computer. When the account is already in the group (`os.getgrouplist`) but
     Clank's service is not (`os.getgroups`), it says that the service started before the account joined: log in
     again if not done yet, then `clank stop` and `clank work`.
   - Without systemd, the engine is asked directly.
   - **One engine, named.** Every command names the system engine's socket, `-H unix:///var/run/docker.sock`, which
     wins over `DOCKER_HOST` and the current context. On Linux, Docker Desktop's adapter names its own context
     (`--context desktop-linux`); on Windows and macOS its commands do not change.
3. **Clank never starts or stops Docker Engine.** The adapter's start and stop capabilities are false. Each names the
   command the owner runs: `sudo systemctl start docker`, and `sudo systemctl stop docker.socket docker.service`.
   Asked anyway, the adapter refuses in those words.
   - The operations `docker.start` and `docker.stop` refuse at once in the status's words: the docker group for `no
     access`, the command for a start or a stop. A stop is refused before any question about other programs'
     containers.
   - `clank work`, `clank code`, the folder page and `workspaces.open` show the status's detail and stop.
4. **Clank never runs `sudo`.** It never asks for a password, and it never writes a system file or a sudoers or
   polkit rule.
5. **Every docker command that reaches an engine goes through the adapter.** The meters' `docker stats` and the
   doctor's checks ask through the workspaces component's public functions. The meters ask only while Docker's last
   reading is running. `docker --version`, `docker context show` and `docker desktop version` stay outside: they
   reach no engine.
6. **The adapter is chosen by platform and by what answers.** The setting `adapter` becomes `auto` by default, and a
   name set there still wins. `auto` is `docker-desktop` on Windows and macOS. On Linux it is the adapter of the engine
   the `docker` command would use, found without asking any engine:
   - `docker-desktop` when the command's current context is Docker Desktop's (`desktop-linux`, read with `docker
     context show`), which Docker Desktop sets while it runs
     (https://docs.docker.com/desktop/setup/install/linux/);
   - else `docker-engine` when systemd knows Docker's service;
   - else `docker-desktop` when Docker Desktop's own command answers (a stopped Docker Desktop, with no Docker
     Engine beside it);
   - else `docker-engine` when a `docker` command is found. It asks the engine directly, except that Docker from the
     snap (its command under `/snap/`) and rootless Docker (a current context named `rootless`, or `DOCKER_HOST`
     naming a socket in the user's runtime folder) are `unsupported`, saying to install Docker Engine from Docker's
     packages (https://docs.docker.com/engine/install/);
   - else `docker-engine`, which then says Docker is not installed.

   Docker's view says which adapter was chosen, and why.
7. **Recorded and contract-tested** as Docker Desktop is: a recording of a real Docker Engine (running, stopped, no
   access) in `tests/fixtures/docker-engine/<version>/`.
   - A recording keeps each command's errors, where Docker says "permission denied".
   - It is made by a development tool that runs the commands the adapter sends: on a CI runner, by hand, or on the
     Pi, as the owner chooses (design 0014 §2).
   - The contract gains one rule: a platform Clank does not start refuses a start and a stop with the command to run.

## Alternatives considered
- **Run `sudo` for the owner** (or pkexec, or a sudoers or polkit rule that Clank writes). A background service would
  ask for a password, or hold root's rights. Clank never changes the computer's own settings itself: it explains and
  offers ([design 0001](../design/0001-runtime-and-console.md) §4.7). Outside its own folders it touches only what the
  owner approves (design 0001 §7.2). The one folder that design 0014 adds outside `CLANK_HOME`, the gateway's socket
  folder (§3), is the owner's own and needs no root. Rejected.
- **Ask `docker` first, as Docker Desktop's adapter does.** With socket activation, asking a stopped engine can start
  it. Clank's check every 5 seconds would undo the owner's stop.
- **Check systemd only in the 5-second status.** The meters and the doctor would still send their own commands. A
  command sent in the seconds after the owner's stop would start the engine again. One check before every command, in
  the one place that sends them, closes both.
- **Pin `--context default` instead of `-H`.** The default context follows `DOCKER_HOST` when it is set, so it would
  not name one engine.
- **One adapter for both programs, with branches.** An application and a system service live differently. Principle 2
  asks for one adapter per program; what the two share is the base class.
- **Docker Desktop's adapter, tolerating the missing command.** It would still try to start an application that is
  not there.
- **Podman, rootless Docker, or Docker from the snap.** Podman and rootless Docker need no docker group's root-level
  rights, but both change the user ids inside containers and the edge's way to the gateway
  ([decision 0071](0071-how-containers-reach-the-gateway-on-linux.md)). The snap's engine cannot mount the hidden
  folders of the home folder (https://snapcraft.io/docs/home-interface), where the gateway's socket folder is. They
  can be later adapters, if wanted.

## Consequences
- On the Pi, the owner installs Docker Engine, joins the docker group once, and starts or stops the engine with
  systemctl. Clank shows the engine's state everywhere, with the command to run when it does not run.
- A stopped engine stays stopped, even when the owner stops only `docker.service` and its socket still listens.
- `clank work`, `clank code` and the folder page no longer ask a system-run Docker to start; they show the command.
- `clank doctor` reports Docker in the adapter's words: no access, stopped, failed or unsupported, each with what to
  do.
- The console's Docker page and VS Code's Docker item still offer a start. On Docker Engine the operation refuses it,
  with the command.
- On Windows nothing changes: `auto` is `docker-desktop` there, and its commands are the same.
- Each Docker Engine version Clank is tested against needs its own recording. When the adapter's commands and the
  recording's differ, the contract test fails, and the engine is recorded again.
- The machine component uses the workspaces component, for the meters and the doctor.
- Joining the docker group is the owner's choice and risk: anyone in it can act as root on that computer. The detail
  of `no access` says so before the owner joins.
