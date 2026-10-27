# Design 0014: Linux without Docker Desktop, and small machines

Clank on a Raspberry Pi 5: the service, the console and the agent on a small arm64 computer running Linux, with the
model on another computer. This design covers the Pi's side. Containers run without Docker Desktop; the edge reaches
the gateway on Linux; the doctor describes a small machine; OpenCode runs on arm64; CI runs on arm64. The model's side
(endpoints and the tunnel to them, [design 0001 §7.6](0001-runtime-and-console.md#76-endpoints)) is design 0015's,
written beside this one. A download for every system comes after both.

It follows the plan researched on 2026-10-18; its outside sources are cited where they are used. A path such as
`workspaces/sandbox.py:38` means `clank/components/workspaces/sandbox.py`, line 38, at commit e90c51a; every other
path starts at the repository's root. Decisions it rests on: principles 2, 5 and 6
([decision 0002](../decisions/0002-design-principles.md)); [0011](../decisions/0011-agent-programs-are-plugged-in.md)
(agent programs are plugged in); [0019](../decisions/0019-components-use-declared-public-functions.md) (components use
one another's declared public functions); [0020](../decisions/0020-enforce-where-it-can-be-stopped.md) (each permission
is enforced where it can be stopped). It proposes [decision 0070](../decisions/0070-a-docker-engine-adapter.md) (a
Docker Engine adapter) and [decision 0071](../decisions/0071-how-containers-reach-the-gateway-on-linux.md) (how
containers reach the gateway on Linux). Its plan is [s9](../plans/s9-linux-and-the-pi.md).

**Status:** written 2026-10-18, every section *proposed*. The owner approves it, or tells the agents to build while
the review goes on, as for designs 0003 and 0004. **Choice** marks what the owner decides: where Docker Engine's
first recording is made (§2), the gateway's way in on Linux (§3, decision 0071), CI's minutes on arm64 (§7), and where
VS Code runs on the Pi (§8). §1 lists the approved sections this design refines.

*2026-10-27: the owner told the agents to build lane L for Linux x64 while the review goes on, as for designs 0003 and
0004: "I want to begin testing clank by itself on a completely separate linux computer that I have where I will only be
testing the integration with the API keys from openrouter, so we need to make sure that this is completely set up and
ready for testing." It is built with the recommended choices: Docker Engine's first recording is made by the hand-run
job (§2), and decision 0071's (a). Decision 0070 is accepted. Built so far by plan s9: L0's capture tool, the errors in
recordings and the hand-run job, with Docker Engine 28.0.4's recording (run 40578825917); L1, one base for the plain
docker CLI; L2, the docker-engine adapter; L3, the adapter chosen by platform and by what answers (`auto`), with no
start where Clank cannot start; L4, the doctor and the meters asking Docker through it; L7, no workspace opening where
Docker cannot limit memory, unless allowed and said; L8, a folder the agent's user (1000) may not write refused, saying
how to let it. L5 and L6 (§3) are built beside lane L, on a branch of their own. The Pi's steps (P1-P6) wait.*

**The machine.** A Raspberry Pi 5: arm64, four Cortex-A76 cores, and 8 GB of memory, the size this design is checked
against. It runs 64-bit Raspberry Pi OS (Debian 13, kernel 6.18) and Docker Engine from Docker's Debian packages
(https://docs.docker.com/engine/install/debian/). A 32-bit system cannot work: OpenCode ships no 32-bit ARM build, and
`uv.lock` has no 32-bit ARM wheel for psutil. The doctor says so on one (§5).

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What runs on Linux and arm64 today, and what this design refines | Proposed 2026-10-18 |
| 2 | The container platform adapters | Proposed 2026-10-18; built at the owner's instruction, 2026-10-27 (plan s9 L0-L4): the `docker-engine` adapter on Docker Engine 28.0.4's recording, `auto`, the doctor and the meters through the adapter |
| 3 | The edge's way to the gateway on Linux | Proposed 2026-10-18 |
| 4 | A workspace's container on Docker Engine | Proposed 2026-10-18; its memory limits and the agent's user built at the owner's instruction, 2026-10-27 (plan s9 L7, L8); the host's own address comes with §3 (L6) |
| 5 | The doctor and the machine profile on a Raspberry Pi 5 | Proposed 2026-10-18; Docker's checks built with L4 and L7 (2026-10-27); the Pi's profile and checks (P3) wait |
| 6 | OpenCode on arm64 | Proposed 2026-10-18 |
| 7 | CI on arm64 | Proposed 2026-10-18 |
| 8 | A small machine: memory, VS Code and the owner's settings | Proposed 2026-10-18 |
| 9 | What this design does not cover | Proposed 2026-10-18 |
| 10 | Build steps | Proposed 2026-10-18; lane L for Linux x64 built but L5-L6 (2026-10-27); lane P waits |

## 1. What runs on Linux and arm64 today, and what this design refines

| Part | Linux x64 | Linux arm64 (the Pi 5) |
| --- | --- | --- |
| The service, the gateway, the console, `clank` | Tested on every push (`.github/workflows/checks.yml:23-39`) | Should run: every compiled dependency in `uv.lock` has a Linux aarch64 wheel. Never run |
| Local engines | llama.cpp's CPU build for Ubuntu x64 (`clank/recipes/llamacpp/b11588.json:5-6`); engine adapters run on Linux only (`runtime/adapters/engine.py:160`) | None: the only recipe is x64. The Pi's model is on another computer (design 0015) |
| The agent in its container | Docker Desktop for Linux is listed (`workspaces/adapters/docker_desktop.py:103`) but untested; Docker Engine reads as "unsupported" (`workspaces/adapters/docker_desktop.py:136-137`) | Blocked (below) |
| Clank's VS Code window | `code` from the PATH (`agents/vscode.py:86-96`); only CI's activation suite has run | VS Code for arm64 is in Raspberry Pi's archive and meets the extension's `^1.138.0` (`vscode/package.json:9-10`); untested |
| CI | Every push | None |

Three things keep the agent from working on the Pi.

1. **No adapter for Docker Engine.** Clank runs containers through one adapter, Docker Desktop's
   (`workspaces/adapters/__init__.py:10-15`), and its setting names no other (`workspaces/kinds.py:25-28`). Docker
   Desktop for Linux is made for x86-64 only (https://docs.docker.com/desktop/setup/install/linux/). Without the
   `docker desktop` command, the adapter says "unsupported" (`workspaces/adapters/docker_desktop.py:132-137`), and no
   workspace opens. Yet the doctor passes "Docker installed" (`machine/checks.py:149-153`).
2. **No way from the edge to the gateway.** The edge forwards each workspace's requests to `host.docker.internal`,
   which it maps to `host-gateway` (`workspaces/sandbox.py:38, 154-169`). On Docker Desktop that name reaches the host's
   loopback, where the gateway listens (`gateway/server.py:611`). On Docker Engine, `host-gateway` is the default
   bridge's address (https://docs.docker.com/reference/cli/dockerd/), and nothing listens there. OpenCode's requests go
   to `http://edge:<port>/v1` (`agents/service.py:270, 317`) and reach no model.
3. **OpenCode is unproven on the Pi 5's memory pages.** OpenCode 1.19.0 is built with Bun. Bun's support for pages
   other than 4 KiB is an open issue that names the Pi 5 (https://github.com/oven-sh/bun/issues/17627). The Pi 5 boots
   a kernel with 16 KiB pages by default (Raspberry Pi's documentation, `config_txt/boot.adoc`,
   https://github.com/raspberrypi/documentation). A container shares its host's kernel, and so its page size (§6).

The rest of Clank should run on the Pi as it is. CI on arm64 (§7) would check that.

**What this design refines.** Designs 0001 and 0002 are approved. Design 0004's sections are proposed, but they were
built at the owner's instruction, so they are listed too. When this design is approved, each section below is marked
*revised after approval* (0001, 0002) or revised (0004), saying what changed.

| Section | It says | This design | Where |
| --- | --- | --- | --- |
| 0001 §6.6 | The gateway listens on this machine only, unless the user allows other machines, and then only with a token | (a): also on a Unix socket, which no network reaches. (b): also on an address of Clank's bridge, refusing every peer outside Clank's outer network | §3 |
| 0001 §7.1 | Linux means Ubuntu 22.04 and 24.04 | Also 64-bit Raspberry Pi OS (Debian 13) on arm64: the service, the console and the agent, with no local engine | §1, §5, §6 |
| 0001 §7.2 | Clank touches nothing outside `CLANK_HOME`, except what the user approves in the guide | Under (a), one folder outside it: `~/.cache/clank/<home id>/`, the owner's alone (0700), holding only the gateway's socket (0600). The gateway removes the socket when it stops; the empty folder stays until Clank is removed, and removing Clank means removing it too. `clank doctor` names it | §3, §5 |
| 0001 §8.4 | CI runs on Linux on every push | Also on arm64 Linux, as often as the owner chooses; the docker-marked tests in CI for the first time | §7 |
| 0002 §1; 0004 §3 | The edge is each sandbox's only door; it forwards the gateway's port | On Docker Engine, under (a), the edge forwards to the gateway's socket and runs as the owner's user id. Its network still reaches out, as on Docker Desktop, for M7's grants. The service listens on 127.0.0.1 only (`clank/kernel/service_kinds.py:40`), and the tool hub is not built yet: when the edge needs them on Docker Engine (M7, M8), they take the same path, a socket each in the same folder (their designs) | §3 |
| 0002 §2.6 | The floor: no sandbox sees `CLANK_HOME` or the folder Clank itself runs from | The socket's folder is never inside or holding either of them or a workspace's folder, and never the home folder itself; a workspace's folder never holds it. Only the edge sees it | §3 |
| 0002 §2.9; 0004 §3, §6, §8 | Every container has resource limits: CPU and memory, tested as applied | Kept. Where Docker cannot limit memory (a Pi's default kernel), no workspace opens unless `config/docker.json` allows it, and then every client says so | §4 |
| 0002 §2.9, §2.10 | Containers run through a platform adapter: Docker Desktop first, Docker Engine on Linux. One contract per kind of adapter, on recordings of the real program | The `docker-engine` adapter (decision 0070). The contract gains a rule for a platform Clank does not start. A recording keeps each command's errors | §2 |

## 2. The container platform adapters

Containers run through a container platform adapter
([design 0002 §2.9](0002-the-foundation.md#29-processes-and-containers), §2.10). Decision 0070 adds the second one.

- **One base for the plain docker CLI.** Every container command Clank sends is Docker's own CLI, the same whichever
  program runs the engine: `docker info` for the CPUs and memory, `build`, `network`, `run`, `container inspect`,
  `start`, `stop`, `rm`, `volume rm` and `exec` (`workspaces/adapters/docker_desktop.py:219-342`). So is the list of
  containers with their labels (`workspaces/adapters/docker_desktop.py:145-167, 389-403`). They move from
  `DockerDesktop` into a base class, `DockerCli` (`workspaces/adapters/docker_cli.py`), that both adapters extend.
  Nothing changes in behavior: the contract test and every workspace test pass as they are.
- **`docker-desktop`** keeps what is Docker Desktop's own: `docker desktop version|status|start|stop`, its program
  when its command starts nothing, and WSL's handler after a start
  (`workspaces/adapters/docker_desktop.py:123-143, 169-217, 351-365`). On Linux it names its own context on every
  command (`--context desktop-linux`). So it never reads Docker Engine's containers as its own, as it would once
  Docker Desktop has stopped and set the `default` context back. On Windows and macOS its commands do not change.
- **`docker-engine`**, for Linux, reads the engine's state and never changes it.
  - *systemd first.* When systemd knows Docker's service, the adapter reads its state there (`systemctl show
    docker.service`, its load and active states): activating is *starting*, deactivating *stopping*, inactive
    *stopped*, failed *failed* (its detail names `systemctl status docker`, which says why). Any user may ask, and
    asking starts nothing. This matters because Docker's packages start the engine through systemd's socket activation
    (`dockerd -H fd://`, https://docs.docker.com/reference/cli/dockerd/). A `docker` command sent to a stopped engine
    can start it again, and Clank reads Docker's state every 5 seconds (`workspaces/kinds.py:30-32`). Asking `docker`
    first would undo the owner's stop.
  - *No command reaches a stopped engine.* Every command the adapter sends to the engine first asks systemd whether
    Docker's service is active; a reading from the last second is reused. That covers the commands it runs, those it
    follows (a build, a setup), and those it hands back for another to run (`docker exec`, for a terminal or the
    bridge). When the service is not active, nothing is sent, and the adapter refuses with the command to start
    Docker.
  - *Then the engine.* An active engine is asked `docker version`, and its whole answer is kept (`run_answer`,
    `clank/kernel/processes.py:85-116`). Running gives its versions and its containers, through the base. "permission
    denied" on Docker's socket gives the state *no access*, whose detail says what to do:
    - The account is outside the `docker` group: join it (`sudo usermod -aG docker $USER`), log out and in again, then
      restart Clank's service (`clank stop`, then `clank work`). The group is equivalent to root on that computer
      (https://docs.docker.com/engine/install/linux-postinstall/).
    - The account is in the group (`os.getgrouplist`), but Clank's service is not (`os.getgroups`). The service started
      before the account joined, and keeps the groups it started with; `clank work` reuses it. Log out and in again if
      that is not done yet, then `clank stop` and `clank work`.

    Any other refusal gives *stopped*, in Docker's words. Without systemd, the engine is asked directly.
  - *One engine, named.* Every command names the system engine's socket: `docker -H unix:///var/run/docker.sock`. The
    flag wins over `DOCKER_HOST` and over the current context. So Docker Desktop started later, a remote context or a
    `DOCKER_HOST` never sends Clank's commands to another engine, nor the edge's mount (§3).
  - *Never a start or a stop.* Its start and stop capabilities are false, each with the command the owner runs: `sudo
    systemctl start docker`, and `sudo systemctl stop docker.socket docker.service` (the service stopped alone is
    started again by its socket). Asked anyway, the adapter refuses in those words.
  - *Docker from the snap, and rootless Docker, are unsupported.* Where systemd knows no `docker.service` of the
    system's, their state is *unsupported*, saying to install Docker Engine from Docker's packages
    (https://docs.docker.com/engine/install/). The snap's engine cannot mount hidden folders of the home folder, such
    as the gateway's socket folder (snapd's `home` interface reaches only files that are not hidden,
    https://snapcraft.io/docs/home-interface). Rootless Docker maps user ids (decision 0070). The snap's is told by
    its command's place (under `/snap/`). Rootless Docker is told by a current context named `rootless`, or by
    `DOCKER_HOST` naming a socket in the user's runtime folder. Where the system's own service exists too, Clank uses
    that engine, whatever the current context, since every command names its socket.
- **Choosing the adapter.** `config/docker.json`'s `adapter` becomes `auto` by default (`workspaces/kinds.py:25-28`).
  The names stay settable, and a name set there wins. `auto` is:
  - `docker-desktop` on Windows and macOS;
  - on Linux, the adapter of the engine the `docker` command would use, found without asking any engine, so none is
    woken:
    1. `docker-desktop` when the command's current context is Docker Desktop's (`desktop-linux`, read with `docker
       context show`). Docker Desktop sets that context while it runs, and sets `default` back when it stops
       (https://docs.docker.com/desktop/setup/install/linux/).
    2. Else `docker-engine`, when systemd knows Docker's service.
    3. Else `docker-desktop`, when Docker Desktop's own command answers: a stopped Docker Desktop, on a computer
       without Docker Engine.
    4. Else `docker-engine`, when a `docker` command is found. It asks the engine directly, or says *unsupported* for
       the snap's Docker and rootless Docker.
    5. Else `docker-engine`, which says that Docker is not installed, and how to install it.

  It is chosen when the service starts and when the setting changes. Docker's view (`GET /docker`) says which adapter,
  why ("Docker Engine: this is Linux, and systemd knows Docker's service"), and whether Clank starts it (`starts`).
- **No start where Clank cannot start, and no wrong advice.**
  - `clank work` and `clank code` start Docker only when the platform can (`agents/cli.py:69-72`). So does the folder
    page's Docker step (`agents/console/folder.py:729-732`). Otherwise they show the state with its detail, and stop.
  - The operations `docker.start` and `docker.stop` (`workspaces/service.py:322-368`) refuse at once when the
    platform's capability is false, in the status's words. For *no access*, that is the docker group; a start of a
    stopped Docker Engine gets `sudo systemctl start docker`. A stop is refused before any question about other
    programs' containers (`workspaces/service.py:351-359`). Today a start lets *no access* through
    (`workspaces/service.py:494-498`).
  - `workspaces.open` refuses in the status's words too. Today it says "start it with `clank docker start`" whatever
    the state (`workspaces/folders.py:157-160`).
  - The console's Docker page and VS Code's Docker item still offer a start; the operation refuses it, saying why.
- **Every docker command goes through the platform.** Today two parts of the machine component run `docker` from the
  PATH, whatever Docker's state:
  - the meters run `docker stats --no-stream` every 10 seconds while the service runs (`machine/meters.py:180-197,
    214-220`, made and started at `machine/service.py:67, 82-92`);
  - the doctor runs `docker info` (`machine/checks.py:155-159`), through a runner that drops Docker's words
    (`clank/kernel/processes.py:78-82`), so a user outside the docker group is told to start Docker.

  Either one would wake an engine the owner stopped. Both now go through the workspaces component's public functions,
  and so through its adapter. The meters ask only while Docker's last reading is *running*. The doctor reads the
  platform's status, which works without the Clank service, as the doctor must (design 0002 §2.15). The machine
  component then declares that it uses workspaces; there is no cycle (workspaces uses the gateway, which uses the
  runtime). Three commands stay outside, because they reach no engine: `docker --version`, the doctor's profile
  (`machine/detect.py:84-87`), and `docker context show` and `docker desktop version`, the choice above.
- **Recorded and contract-tested** as Docker Desktop is
  ([design 0001 §8.3](0001-runtime-and-console.md#83-fixtures-recorded-from-the-real-engines)). A real Docker Engine is
  recorded in `tests/fixtures/docker-engine/<version>/program.json`, in three states: running, stopped and no access.
  - A recording keeps each command's errors as well as its status and output. Docker's words for *no access* are in
    its errors, and `RecordedProgram` replays only an exit status and output today (`tests/fakes/recorded.py:44-75`).
    The fake gains the whole answer (`answer`), and the contract's `build()` gives it to the adapter.
  - The contract (`tests/contract/test_container_platform.py`) gains one rule: a platform Clank does not start refuses
    a start and a stop with the command to run, and its capabilities say so.
  - Nothing personal is kept: ids, names, images and labels are made up, as in Docker Desktop's recording. Only the
    fields Clank reads are recorded, never the whole of `docker info`, which holds the host's name.
  - A small development tool records it (`tools/capture_docker_engine.py`, plan s9 L0). It runs the commands the
    adapter sends, as the tool lists them. If the two lists ever differ, the contract test fails, since the fake
    refuses any command never recorded, and the engine is recorded again. The tool changes nothing itself: whoever
    records stops the engine, or works as a user outside the docker group, before each state.
  - **Choice: where the first recording is made.** Every step after it waits for it (§10). (1) A job of the
    repository's CI, run only by hand (`workflow_dispatch`), on GitHub's `ubuntu-24.04` runner. That runner has
    Docker Engine 28.0.4 from Docker's own packages
    (https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md, and its
    `scripts/build/install-docker.sh`), and sudo without a password. The job takes a few minutes of the account's x64
    minutes. It prints `program.json` in its log, between two marker lines, for an agent to read and commit, so no
    new action is needed to keep it. (2) The owner, on the Pi, during the dry run (§10). **Recommended: (1)**, so lane
    L need not wait for the Pi. The Pi's own recording joins later as a second version.

## 3. The edge's way to the gateway on Linux

Decision 0071, a **Choice**; (a) is recommended. What must hold:

- The gateway asks no caller for credentials, and it forwards `/notion/...` to the service as the client `agent`
  (`gateway/server.py:134-143, 607`). Whatever reaches it may use the model, and may read the owner's Notion as the
  agent. So it faces nothing but the host's own tools and the edge.
- Never `0.0.0.0`. A Pi joins other networks, such as a shared Wi-Fi.
- No container sees `CLANK_HOME` (the floor, [design 0002 §2.6](0002-the-foundation.md#26-policy)).
- Docker Desktop's path stays as it is: there, `host.docker.internal` reaches the host's loopback (proven on Windows;
  untested on macOS and Linux).
- The gateway keeps listening on 127.0.0.1 for the host's tools
  ([design 0001 §6.6](0001-runtime-and-console.md#66-where-it-runs-and-who-can-reach-it)).

**(a) A Unix socket mounted into the edge only (recommended).**

- **Where.** On Linux, the gateway also listens on a Unix socket, `gateway.sock`, in a folder of its own outside
  `CLANK_HOME`. The folder is `~/.cache/clank/<home id>/` by default (under `$XDG_CACHE_HOME` when that is set), and
  `socket_folder` in `config/gateway.json` can move it.
  - It is not in `/tmp`, which every user shares.
  - It is not in `$XDG_RUNTIME_DIR` either: systemd removes that folder when the user's last session ends, while the
    service, and a flow running unattended, may go on.
  - It is the one folder Clank keeps outside `CLANK_HOME`, a refinement of design 0001 §7.2 (§1). The gateway removes
    its socket when it stops. The empty folder stays until Clank is removed, and removing Clank means removing it too.
    `clank doctor` names it (§5).
- **Who may open it.** The folder is the owner's alone (0700), and so is the socket (0600).
  - The gateway makes its two listeners itself and hands both to Uvicorn (`Server.run(sockets=...)`). Uvicorn's own
    socket option would leave the socket writable by every user (`uds_perms = 0o666`, `uvicorn/server.py:168` in
    Uvicorn 0.54.0).
  - The Unix socket is bound inside its 0700 folder, and its path is set to 0600 before it listens. The process's
    umask is never changed: it is the whole process's, and the routes thread already runs (`gateway/server.py:605`).
  - The gateway keeps what Uvicorn did for it when Uvicorn made the TCP socket itself. The TCP socket reuses its
    address (`SO_REUSEADDR`, as asyncio sets it on Linux), so a restart finds the port free while old connections
    close. A port another program holds ends the gateway as today: logged, with Uvicorn's exit status, 3
    (`uvicorn/server.py:180-192`).
- **Where it may not be.** The folder is checked much as a workspace's folder is (`workspaces/folders.py:77-96`):
  never the home folder itself, and never inside or holding `CLANK_HOME`. It is also never inside or holding the
  folder Clank itself runs from, or a workspace's folder, and opening a workspace refuses a folder that holds it or is
  inside it.
  - The gateway checks what it knows: `CLANK_HOME`, the folder Clank runs from, the home folder.
  - The workspaces component knows every workspace and uses the gateway, so it checks the rest before it gives the
    edge the folder. A socket folder that a workspace's folder holds keeps every workspace from opening on Docker
    Engine, naming that workspace and `socket_folder`.
  - A sandbox that saw the socket would gain nothing the edge does not give it already, since the edge forwards the
    whole gateway. The rule keeps the edge the one door, so what the edge adds later (M7) cannot be gone around.
  - A socket's path holds at most 107 bytes; a longer one is refused, saying so.
- **Who knows where it is.** The gateway's service passes the socket's path to the gateway's process
  (`gateway/service.py:253`). It gives the path to the workspaces component through a public function, as it gives
  the port (`workspaces/service.py:281-286`). The gateway's status shows it: `GET /gateway`, `clank gateway status`
  (`gateway/cli.py:45`) and the console's gateway row (`clank/console/pages/home.py:168-180`).
- **A gateway without its socket is started again** once no request is in flight, and its log says why. It may be
  one started before this change, which the service adopts as it is (`gateway/service.py:242-247`). It may be one
  whose folder was removed while it ran (a cache folder may be cleared).
- **The edge.** On Docker Engine, the edge mounts that folder read-only at `/run/clank`, as its only mount. It forwards
  to `unix:/run/clank/gateway.sock`; `workspaces/image/edge.py` gains that kind of target, with the standard library.
  It runs as the owner's user id, so it may open the socket.
  - Clank's outer network stays as it is, as on Docker Desktop. It is the edge's way out, which M7's grants need
    (`net.connect`, `git.fetch` and `git.push` go out through the edge, design 0002 §2.6).
  - Nothing listens for the gateway on any network.
- **A new socket, the same folder.** The edge mounts the folder, not the socket. A gateway that starts again makes a
  new socket in the same folder, and the edge sees it. If the folder itself is removed and made again while the edge
  runs, the edge keeps the old one. So opening a workspace asks the gateway's health through the edge while the
  gateway runs, and makes the edge again when it does not answer.

**(b) A second listener on the bridge address, refusing peers outside Clank's outer network.**

- The gateway also listens on the host's address on Clank's outer network: the network's gateway address, which Docker
  picks when it makes the network. The edge forwards to that address. The gateway refuses every connection whose peer
  is outside that network's subnet.
- Against it:
  - The address exists only once Docker has made the outer network, after the gateway starts.
  - Every container on the machine can reach a host address, so the peer check is the only guard.
  - Linux answers for any of its addresses on any interface. So a computer on the same network that routes the
    bridge's subnet to the Pi reaches that address too, and the peer check is then also the only guard against other
    computers.
  - A host firewall can drop traffic from a Docker bridge to the host, and only root can allow it.

  Decision 0071 sets out each point.

**Why (a).** Only the owner's processes, root and the edge can open the socket. No network faces it, no firewall is
involved, and nothing waits for Docker's networks. Its costs:

- one folder outside `CLANK_HOME`;
- a mount into the edge, and the edge running as the owner's user id;
- a sandbox image built again once (its tag is its folder's checksum, `workspaces/sandbox.py:219-226`, and `edge.py`
  changes).

Tests:

- `test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it`: the socket, 0600 in a 0700 folder outside
  `CLANK_HOME`, answers `/health`, and no new address listens;
- the edge's `docker run` arguments on each platform;
- with Docker, `test_the_edge_reaches_the_gateway_on_linux`;
- for (b), also `test_a_peer_outside_clanks_network_is_refused`.

The escape tests' stand-in gateway listens on 127.0.0.1 only (`tests/docker/test_escape.py:46`); it moves to where the
gateway listens on each platform.

## 4. A workspace's container on Docker Engine

- **The host's own address.** On Docker Desktop, a workspace's network ends inside Docker's virtual machine. On Docker
  Engine, the host itself may have an address on each bridge network, so a server there that listens on every address
  (an SSH server, say) would answer the agent.
  - Today's escape tests try only `host.docker.internal` (`tests/docker/test_escape.py:122`), which a workspace's
    container on Linux cannot even resolve. They would pass there without proving anything.
  - On Linux they also try the host's own address on the workspace's network. Their probe listens on that address
    only, read with `docker network inspect` (the network's gateway), never on every address: on a shared network a
    probe on every address would face the network while the test runs. A host with no address there refuses the
    probe's bind, which proves the same.
  - If the address answers, Clank makes the workspaces' networks without a host address. Docker's bridge option
    `com.docker.network.bridge.inhibit_ipv4` makes "a network without the IPv4 gateway address being assigned to the
    bridge" (https://docs.docker.com/engine/network/drivers/bridge/), and the test then proves it.
  - The outer network keeps its host address, which is the edge's way out (§3), and (b)'s listener.
- **Memory limits.** Each container has resource limits (design 0002 §2.9), and a workspace's container has CPU and
  memory limits (design 0004 §3, §6). The Pi 5's kernel boots with the memory controller off: its device tree sets
  `cgroup_disable=memory` (raspberrypi/linux, branch rpi-6.18.y, `arch/arm64/boot/dts/broadcom/bcm2712-rpi.dtsi:122`).
  Docker then cannot limit a container's memory: `docker run --memory` warns and runs without the limit, and `docker
  info` warns "No memory limit support". On an 8 GB Pi, an agent's runaway process could then take the machine's
  memory, and the kernel's out-of-memory killer may end the Clank service or the gateway with it.
  - The base adapter reads `docker info`'s `MemoryLimit` and its warnings, in Docker's words. It asks when a workspace
    opens and when the doctor runs, never in the 5-second check; the last reading is kept.
  - When limits are off, no workspace opens. The refusal names the fix: add `cgroup_enable=memory` to the one line of
    `/boot/firmware/cmdline.txt`, then restart. Clank changes neither file. The doctor's check fails, with the same fix
    (§5).
  - The owner may allow it anyway: `allow_unlimited_memory` in `config/docker.json`, false by default. Then a workspace
    opens, its log says that its memory is not limited and why, and Docker's summary (`GET /docker`) says so too.
    Every client shows that summary: the console's home page and Docker page, and VS Code's Docker item.
  - The escape tests read every limit in the container (`tests/docker/test_escape.py:138-151`). On a Pi without the
    memory controller they fail until it is on, as they should.
- **The agent's user.** The agent runs as uid 1000 (`workspaces/sandbox.py:33`). On Docker Engine, a mounted folder
  shows the host's own owners. When the owner's user id is not 1000, the agent cannot write the folder, and cannot even
  read a private one. Opening a workspace then refuses the folder and says why, unless the folder lets uid 1000 write
  (L8). Building the image for the owner's own id is the fuller answer, and a later step. The Pi's first user is
  usually 1000 (`id -u` says). GitHub's runners may use another id, so the docker-marked tests in CI may meet this
  first (§7).
- **The setup's network.** A workspace's setup (design 0004 §10) reaches the internet on Docker's default network
  (`workspaces/sandbox.py:43`). On Docker Engine it goes out through the host. Nothing changes.

## 5. The doctor and the machine profile on a Raspberry Pi 5

The machine profile (`machine/kinds.py:23-41`) gains four facts:

- `architecture`: the kernel's, from Python's `platform.machine()`: `aarch64` on the Pi; `x86_64` or `AMD64`
  elsewhere.
- `programs`: the word size of the system's programs, which can differ from the kernel's. Raspberry Pi OS's 32-bit
  edition runs a 64-bit kernel on a Pi 5, so `platform.machine()` still says `aarch64` there. It is read from Python's
  own word size (`struct.calcsize("P")`: 8 bytes on a 64-bit system), and on Debian from `dpkg
  --print-architecture` (`arm64`, or `armhf` on the 32-bit edition): "64-bit (arm64)".
- `page_size`: the memory page size in bytes (`mmap.PAGESIZE`): 16,384 on the Pi 5's default kernel, 4,096 on
  `kernel8.img`.
- `model`: the computer's model, when the system names one. Raspberry Pi's kernels add a `Model` line to
  `/proc/cpuinfo` ("Raspberry Pi 5 Model B Rev 1.0"). Elsewhere it is empty.

The processor's name: the Pi's `/proc/cpuinfo` has no `model name` line (`machine/detect.py:65-73`), so when that line
is missing, the processor is named by `lscpu`'s "Model name" (Cortex-A76). The board's serial number (cpuinfo's
`Serial` line) identifies the machine. It is never read into the profile, and the tests' copy of a Pi's cpuinfo carries
a made-up one.

The doctor's first line (`machine/cli.py:33-37`) then reads, on the Pi: "Machine: Debian GNU/Linux 13 (trixie) ·
Raspberry Pi 5 Model B Rev 1.0 · Cortex-A76 (4 cores), aarch64, 64-bit programs, 16 KiB pages · 8 GB · no NVIDIA GPU
· Python 3.12".

Its checks (`machine/checks.py:171-182`) on Linux:

| Check | Passed | Not passed, with what to do |
| --- | --- | --- |
| 64-bit programs (new) | "64-bit (arm64)" | Failed: "32-bit programs (armhf), even on a 64-bit kernel: OpenCode has no 32-bit ARM build". On a Raspberry Pi: install 64-bit Raspberry Pi OS |
| Memory pages of 4 KiB (new) | 4,096 bytes | Warning: "OpenCode (built with Bun) is not shown to run on 16 KiB pages". On a Raspberry Pi: add `kernel=kernel8.img` to `/boot/firmware/config.txt` and restart (the Pi's kernel with 4 KiB pages). Elsewhere: boot a kernel with 4 KiB pages |
| Docker installed (§2) | The platform's version | Warning, in the platform's words: on Linux, install Docker Engine (https://docs.docker.com/engine/install/); Docker Desktop for Linux is x86-64 only. Docker from the snap, and rootless Docker: unsupported, with the same page |
| Docker running (§2) | Its state and versions | Warning: its state, with the command (`sudo systemctl start docker`); or *no access*, with the docker group, or with a restart of Clank's service when the account joined after it started |
| Docker limits memory (new, §4) | `MemoryLimit` is true | Failed: "No memory limit support, so no workspace opens": add `cgroup_enable=memory` to `/boot/firmware/cmdline.txt` and restart. A warning instead while `allow_unlimited_memory` is set |
| The gateway's socket folder (new, §3) | Its path, the owner's alone (0700) | Failed: where §3 does not allow it, or open to others: move `socket_folder` in `config/gateway.json` |

- The page check is skipped on Windows and macOS: there, containers run in Docker Desktop's own Linux. The socket
  folder's check is skipped off Linux.
- The GPU check's warning stays (`machine/checks.py:118-126`). A Pi has no NVIDIA GPU, and its model is on another
  computer, as the warning already says.
- The doctor stays read-only (`machine/checks.py:7-8`). Clank never edits `/boot/firmware`; the owner does, then
  restarts.

## 6. OpenCode on arm64

- **The image builds as it is.** Ubuntu 24.04 and NodeSource's Node.js 22 are made for arm64, and `npm install
  --global opencode-ai@1.19.0` installs OpenCode's arm64 Linux build (`workspaces/image/Dockerfile:6-24`). OpenCode's
  install runs `opencode --version`, so a program that cannot run fails the image's build.
- **The page size.** OpenCode 1.19.0 is compiled with Bun, and Bun's support for pages other than 4 KiB is an open
  issue that names the Pi 5 (oven-sh/bun#17627). The Pi 5 boots a 16 KiB kernel unless `config.txt` names
  `kernel8.img`. VS Code once crashed on 16 KiB pages too (https://github.com/microsoft/vscode/issues/242742). So:
  - the doctor warns (§5);
  - the owner boots `kernel=kernel8.img` before the first try;
  - CI cannot catch it: GitHub's arm64 runners boot Ubuntu's generic kernel, with 4 KiB pages as far as is known (not
    verified);
  - the proof is the image's build on the Pi and a session of several minutes in it (the owner's dry run, §10).

  If OpenCode is shown to run on the 16 KiB kernel, by a recorded session on it, the warning becomes a note.
- **Its size.** A full image was 1.44 GB on x64; arm64's is not measured. The first build downloads about a gigabyte.
  It is best built on a home network: Docker Hub limits anonymous pulls per address, and a shared network may put many
  users behind one address.
- **Its tag.** The image's tag is its folder's checksum (`workspaces/sandbox.py:219-226`), the same on every CPU. Each
  machine builds its own image, so nothing clashes. A published image (later) needs the CPU in its tag.

## 7. CI on arm64

Today every push runs `tools.check` on Linux x64 with Python 3.12 (`.github/workflows/checks.yml:23-39`). Python 3.14
on Linux and Windows runs for pull requests, for tags and by hand (`.github/workflows/checks.yml:41-65`). Nothing runs
on ARM. The docker-marked tests run nowhere in CI: they are skipped unless asked for
(`tests/docker/conftest.py:19-26`).

- **P1: `tools.check` on arm64.** The Python 3.12 job also runs on GitHub's `ubuntu-24.04-arm` runner, with the same
  steps.
- **P2: the docker-marked tests on Linux x64 and arm64.** A job runs `uv run pytest -m docker tests/docker`. It builds
  the sandbox image: on arm64 that is the first proof that OpenCode installs and answers. On x64 it is the first run of
  the escape tests in CI. Its runner's user id decides whether the tests' folders must be opened to uid 1000 (§4).
- **What CI cannot prove:** 16 KiB pages (§6), the Pi's memory controller (§4), and the docker group on a real Pi.
  Those stay with the owner's dry runs (§10).
- **What the minutes cost.** In a private repository, a standard arm64 runner has 2 CPUs and 8 GB of memory
  (https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Like the x64 runner, it uses the
  account's included minutes first, and is then charged per minute (the same page).
  - The included minutes are 2,000 a month on GitHub Free and 3,000 on GitHub Pro, for every job together. Beyond them,
    a Linux arm64 minute costs $0.005, and an x64 minute $0.006
    (https://docs.github.com/en/billing/concepts/product-billing/github-actions).
  - The x64 job takes 6 to 8 minutes a run today (runs 39194692105 and 39186970513, 2026-10-19), and each push makes
    a run. `git log` shows 42 commits on 2026-10-12 and 28 on 2026-10-18, and each step is pushed (AGENTS.md).
  - On such days, P1 on every push adds about 170 to 340 arm64 minutes: about as many as the x64 job uses, so CI's
    minutes double. Twenty such days make 3,400 to 6,800 minutes a month. Beyond the included minutes, that is up to
    about $34 a month for P1 alone.
  - The account's plan and its use so far are in GitHub's billing settings; this design does not know them.
- **Choice: how often P1 runs**, and the owner's OK first.
  - *Nightly, on version tags and by hand* (**recommended**). About 30 runs a month, about 200 minutes (about $1 at
    the rate above). A problem found only on ARM shows the next morning, not with the push that made it.
  - *On every push.* It shows with the push, at the cost above.
  - *On pushes that change code.* A paths filter skips pushes that change only `docs/`. Most pushes change code, so
    it saves little.

  P2 runs on version tags and by hand, since each run builds the image on both runners. Its minutes are measured on
  its first run. L0's recording job (§2) runs once, by hand, for a few x64 minutes.

Tests read the workflow as text: Clank has no YAML library, and adding one for a test needs a decision.

## 8. A small machine: memory, VS Code and the owner's settings

- **What Clank takes.** Measured on the owner's PC (research of 2026-10-18): Clank's three processes take about
  290 MB; a workspace's container 648-850 MiB; Clank's VS Code window, with its 12 extensions, 2,176-2,294 MiB. An 8 GB
  Pi has room for all of it, with memory limits on (§4). The dry runs measure the Pi itself (`free -m`, `docker
  stats`, `top`).
- **The owner's settings before the first `clank code` on a Pi.** Each is a readable setting; Clank's defaults stay as
  they are.
  - Trim `extensions` in `config/vscode.json`: the default list installs 12 (`agents/kinds.py:9-22`), and nothing
    removes them later.
  - Turn completion off.
  - Set the vision slot's mode to off: its default, on demand (`gateway/kinds.py:123-128`), would load an x64
    llama.cpp preset.
- **VS Code on the Pi.** It comes from Raspberry Pi's archive (`sudo apt install code`). Microsoft says it is "not
  officially supported" there (https://code.visualstudio.com/docs/setup/raspberry-pi). Clank's extension is copied from
  the PC (`vscode/clank-<version>.vsix`, which git ignores) until a download exists.
- **The terminal first.** `clank work` runs OpenCode with `docker exec -it` in the terminal it was typed in
  (`agents/cli.py:40-49`). The first session on the Pi needs no VS Code at all.
- **Never a window reported that did not open** (P6, whatever the choice below). The service opens the window with its
  own environment (`agents/vscode.py:193-196`). A service started over SSH has no display, so VS Code exits, yet
  `launch_program` reports a start (`clank/kernel/processes.py:127-143`), and Clank says the window opened. That
  happens on the Pi's own desktop too, when an earlier `clank work` over SSH started the service: `clank code` reuses
  it. So on Linux, `agents.vscode` fails when Clank's service has neither `DISPLAY` nor `WAYLAND_DISPLAY` (nor the
  caller, once P4 sends them). It says to restart the service from the desktop (`clank stop`, then `clank code` in a
  terminal there).
- **Choice: where VS Code runs.**
  1. *The Pi's own desktop* (recommended): `clank code` from a terminal there, the service started there too. Nothing
     more to build than P6.
  2. *`clank code` from an SSH shell* (P4). P4 sends the caller's display variables with the request, so the window
     opens on the caller's display.
  3. *VS Code's Remote-SSH, from a laptop* (P5). The extension prefers the laptop's side (`extensionKind` is `["ui",
     "workspace"]`, `vscode/package.json:12-15`), away from the service. P5 turns the order around, so the extension
     runs on the Pi, beside the service.

## 9. What this design does not cover

- The model: endpoints, the tunnel, keys and `model.send`, with their failures (a dropped tunnel, a refused key, a job
  that moved, a network that blocks SSH): design 0015; design 0001 §7.6.
- A download for Windows, macOS and Linux, and installers.
- macOS beyond Docker Desktop's adapter; recipes per CPU (llama.cpp's arm64 archives); removing old sandbox images on
  small disks; published images.
- Rootless Docker, Docker from the snap, and Podman: later adapters, if wanted (decision 0070).
- The meters' cost on four cores. They read every second and every 3 seconds, and `docker stats` every 10
  (`machine/service.py:82-92`, `machine/meters.py:35-37, 197`). Measured on the Pi first; made settings if they cost
  too much.
- Docker's default address pools overlapping the routes of a network the Pi joins (not verified for any). If they do,
  the owner moves them in Docker's own `daemon.json`.
- Found, not changed here: a workspace's folder is not checked against the folder Clank itself runs from, which the
  floor names (design 0002 §2.6; `workspaces/folders.py:77-96`). That is so on every system, and the owner may open
  Clank's own repository as a workspace today, so it is a fix of its own, with the owner's word.

## 10. Build steps

Two lanes, as [plan s9](../plans/s9-linux-and-the-pi.md) sets them out. Each step is one commit that starts with a
failing test (design 0001 §8.6). **B**: needed before the first session on the Pi. **R**: recommended before relying
on it. **C**: only if its condition holds.

| Step | What | Failing test first | After |
| --- | --- | --- | --- |
| L0 B | Docker Engine's recording: the capture tool, errors in recordings, the hand-run job; then the recording, made as the owner chooses (§2) | `test_a_capture_keeps_each_commands_status_output_errors_and_time`; `test_a_recorded_answer_gives_its_errors_to_a_caller_that_asks_for_the_whole_answer` | The design approved |
| L1 B | One base class for the plain docker CLI, shared by both adapters; no change in behavior | `test_every_container_command_is_the_plain_docker_cli_both_adapters_share` | The design approved |
| L2 B | The `docker-engine` adapter: its state from systemd, then `docker version`; no command to a stopped engine; one socket named; *no access* with what to do; never a start or a stop | The contract test on L0's recording; `test_a_user_outside_the_docker_group_is_told_how_to_join_it`; `test_no_command_reaches_the_engine_while_systemd_says_it_is_not_active` | L0's recording, L1 |
| L3 B | The adapter chosen by platform and by what answers; snap and rootless Docker unsupported; no start where Clank cannot start, and refusals in the status's words | `test_docker_engine_is_used_where_docker_desktop_is_not`; `test_work_never_asks_a_docker_the_system_runs_to_start`; `test_starting_docker_engine_is_refused_at_once_with_the_command_to_run` | L2 |
| L4 B | The doctor and the meters ask the platform, keeping Docker's words; the meters ask only while Docker runs | `test_docker_checks_report_what_the_container_platform_reports`; `test_the_meters_never_wake_a_stopped_engine` | L3 |
| L5 B | The gateway's Linux listener, as decision 0071 is chosen | `test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it` (for (b), also `test_a_peer_outside_clanks_network_is_refused`) | Decision 0071 chosen |
| L6 B | The edge forwards to that listener on Docker Engine; Docker Desktop's path unchanged; the socket's folder kept from every workspace; the escape tests on Linux, the host's own address among them | The edge's arguments on each platform; `test_a_workspace_folder_that_holds_the_socket_folder_is_refused`; with Docker, `test_the_edge_reaches_the_gateway_on_linux` and `test_on_linux_the_hosts_own_address_on_a_workspaces_network_answers_nothing` | L2, L5 |
| L7 B | No workspace opens where Docker cannot limit memory, unless allowed and shown; the doctor's check fails with the fix | `test_a_workspace_does_not_open_where_docker_cannot_limit_memory_saying_how_to_fix_it` | L4 |
| L8 C | A folder the agent (uid 1000) cannot write is refused, saying why | `test_on_linux_a_folder_the_agent_cannot_write_is_refused_saying_why` | L2; only if `id -u` is not 1000 where Clank or CI runs |
| P1 R | `tools.check` on `ubuntu-24.04-arm`, as often as the owner chooses | `test_the_checks_run_on_arm64_linux` | The owner's OK on minutes |
| P2 R | The docker-marked tests in CI, on Linux x64 and arm64 | `test_the_docker_tests_run_in_ci_on_linux_x64_and_arm64`, then the docker tests themselves | P1's OK; L6, and L8 where needed |
| P3 R | The profile's architecture, programs, page size and model; the 32-bit check; the 16 KiB page warning naming `kernel=kernel8.img` | `test_a_pi_5s_cpuinfo_gives_its_model`; `test_a_64_bit_kernel_with_32_bit_programs_fails_saying_to_install_64_bit_raspberry_pi_os`; `test_the_doctor_warns_on_16k_pages_with_its_fix` | Nothing |
| P4 C | `clank code` from an SSH shell: the window on the caller's display | `test_on_linux_the_window_opens_on_the_callers_display` | P6; the owner's answer in §8 |
| P5 C | Remote-SSH: `extensionKind` becomes `["workspace", "ui"]` | An extension test of the manifest | The owner's answer in §8 |
| P6 R | On Linux, no window is reported that could not open: without a display, `agents.vscode` fails, saying why | `test_on_linux_without_a_display_the_window_is_refused_saying_why` | Nothing |

- **Order.** L0's tool, L1, P3 and P6 can start now. L0's run waits for the owner's choice in §2 (the job needs the
  owner's OK on its minutes). Then L2, L3, L4 and L7 in turn. L5 once decision 0071 is chosen, then L6 (after L2 too).
  P1 once the owner approves the minutes; P2 after L6. L8, P4 and P5 only if their condition holds.
- **Shared files.** L5 and the endpoints' gateway steps (design 0015) both change `gateway/server.py`. They are never
  built at the same time.
- **The owner's dry run on the Pi** can start now, beside the code:
  1. 64-bit Raspberry Pi OS: `uname -m` says `aarch64` and `dpkg --print-architecture` says `arm64`. `getconf
     PAGESIZE`; if it says 16384, add `kernel=kernel8.img` to `/boot/firmware/config.txt` and restart.
  2. `cgroup_enable=memory` in `/boot/firmware/cmdline.txt`, then restart. Once Docker Engine is in, `docker info` no
     longer warns "No memory limit support".
  3. Docker Engine from Docker's packages. If the owner records it (§2), the *no access* state now, before joining
     the docker group. Then the docker group (`id -u` should say 1000), and the other two states.
  4. `uv sync`, then `uv run python -m tools.check`: the whole suite on ARM.
  5. `docker build -t clank-probe clank/components/workspaces/image`; then `opencode --version` in the image, and
     `opencode` kept open for several minutes.
  6. After lane L: `uv run pytest -m docker tests/docker` and `uv run clank doctor`.

## Decisions to record

- [0070](../decisions/0070-a-docker-engine-adapter.md): a Docker Engine adapter for Linux. Clank reads the engine's
  state from systemd first and sends no command to an engine systemd says is not active, so a stopped engine is never
  woken. It names the system engine's socket on every command, reports *no access* with what to do, and never runs
  `sudo` or starts or stops the engine. The adapter is chosen by platform and by what answers (§2).
- [0071](../decisions/0071-how-containers-reach-the-gateway-on-linux.md): how containers reach the gateway on Linux:
  (a) a Unix socket that only the edge mounts, outside `CLANK_HOME` (recommended), or (b) a second listener on Clank's
  bridge that refuses every other peer; never `0.0.0.0` (§3, the owner's **Choice**).
