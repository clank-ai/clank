# Linux and the Pi: implementation plan

> Written 2026-10-18, before any code, from [design 0014](../design/0014-linux-and-small-machines.md), whose sections
> are proposed. It is built once the owner approves the design, or tells the agents to build while the review goes on
> (as for designs 0003 and 0004). L0's recording waits for the owner's choice of where it is made (design 0014 §2),
> and L2, L3, L4, L6 and L7 wait for that recording. L5 and L6 wait for the owner's choice in
> [decision 0071](../decisions/0071-how-containers-reach-the-gateway-on-linux.md). P1 and P2 wait for the owner's OK
> on billed minutes. L8, P4 and P5 are built only if their condition holds. As for the earlier plans: the files,
> interfaces and tests by name and intent; the code is in the commits.

**Goal:** the agent works in a folder on a Raspberry Pi 5 with Docker Engine (lane L), and the Pi's own checks and CI
on arm64 say what holds there (lane P).

**Architecture:** one base class for the plain docker CLI under two adapters, `docker-desktop` and `docker-engine`,
chosen by platform and by what answers ([decision 0070](../decisions/0070-a-docker-engine-adapter.md)). Every docker
command that reaches an engine goes through the adapter, and `docker-engine` sends none while systemd says Docker's
service is not active. On Linux the gateway also listens on a Unix socket in a folder that only the edge mounts
(decision 0071's option (a), recommended; where option (b) differs, its task says so). Workspaces open only with
their memory limited, unless the owner allows otherwise. The machine profile and the doctor learn a Pi's
architecture, programs, page size, model and memory limits. CI gains arm64.

**Tech stack:** Python 3.12; the docker CLI (Docker Engine on Linux, Docker Desktop 4.85 on Windows); `systemctl
show`, read only; Uvicorn 0.54 serving sockets it is handed; pytest with recorded programs (`tests/fakes/recorded.py`);
GitHub Actions' `ubuntu-24.04` and `ubuntu-24.04-arm` runners.

**Spec:** design 0014 §1-§10; decisions 0070 and 0071; design 0004 §3 (the container, the edge, the escape tests),
§6 and §8; design 0002 §1 (the edge), §2.6 (the floor), §2.9 and §2.10; design 0001 §6.6, §7.1-§7.2, §8.2-§8.4.

**Status:** lane L for Linux x64 being built at the owner's instruction (2026-10-27: Clank on a Linux computer of the
owner's, with OpenRouter's models; design 0014's status says so), with the recommended choices: the recording made by
the hand-run job (design 0014 §2), and decision 0071's (a). Done: L0's tool, the errors in recordings and the job (the
recording waits for the job's run); L1. L5 and L6 are built on a branch of their own. The Pi's steps (P1-P6) wait for
the owner. The places below were found at commit e90c51a; the code has moved since, and each task's commit names where
it changed.

A path such as `workspaces/sandbox.py:38` means `clank/components/workspaces/sandbox.py`, line 38, at commit e90c51a;
every other path starts at the repository's root.

## Global Constraints

- Clank never runs `sudo`, never asks for a password, and never writes a system file: `/boot/firmware/*`, `/etc/*`,
  Docker's `daemon.json`, a sudoers or polkit rule. It reads, and says the command the owner runs (decision 0070).
- No docker command reaches an engine that systemd says is not active: every one goes through the adapter (decision
  0070).
- The gateway never listens on `0.0.0.0` (decision 0071). Under option (a) it listens on no new address at all.
- No container but the edge sees the gateway's socket folder: L5's and L6's checks keep it out of every workspace's
  folder, both ways. No container sees `CLANK_HOME` (design 0002 §2.6).
- Nothing personal in a recording or in a test's data. Container ids, names, images, labels, user names, host names
  and a Pi's serial number are made-up values of the same form. Only the fields Clank asks for are recorded: never the
  whole of `docker info`, which holds the host's name and id. The secrets check reads every fixture.
- No new dependency, and no new GitHub action. The workflow tests read the YAML as text.
- Tests first. Each test file's docstring names the design section it verifies ("Design 0014 §2"), and test names are
  sentences. No test opens a window or a terminal.
- No test writes in the real home folder. From L5 on, `tests/conftest.py` points `XDG_CACHE_HOME` at a short
  temporary folder of the session's own on Linux, so no test, old or new, makes `~/.cache/clank/`. A test's socket
  folder is short, from `tempfile.mkdtemp()` rather than deep under `tmp_path`: a Unix socket's path holds 107 bytes.
- Linux-only code sits under `if sys.platform != "win32":`, because `tools.check` also checks the types as on Windows
  (`tools/check.py:34`), and a pytest skip mark does not satisfy the type checker. That covers `os.getuid`,
  `os.getgroups`, `os.getgrouplist`, the `pwd` and `grp` modules, and `asyncio.open_unix_connection`. Tests that need
  Linux are skipped elsewhere, saying so, and run in CI's Linux jobs.
- Docker-marked tests run only with `-m docker`, and only with the owner's OK on the machine they run on: they build
  the sandbox image (about a gigabyte).
- Each task is one commit, after `uv run python -m tools.check --fix` passes, with the generated files regenerated in
  the same commit. The owner is the sole author. The owner's uncommitted files are never committed.
- L5 and the endpoints' gateway steps (design 0015) both change `gateway/server.py`: never in the same slot.
- L6 changes `workspaces/image/edge.py`, and so the sandbox image's tag (`workspaces/sandbox.py:219-226`): every
  machine builds the image again once. Its commit message says so.

## Order

| Task | Flag | After | Unblocks |
| --- | --- | --- | --- |
| L0 | B | The design approved; its recording, the owner's choice in design 0014 §2 | L2 |
| L1 | B | The design approved | L2 |
| L2 | B | L0's recording, L1 | L3, L6, L8 |
| L3 | B | L2 | L4; workspaces on Linux |
| L4 | B | L3 | L7; a doctor and meters that wake no engine |
| L5 | B | The owner's choice in decision 0071 | L6 |
| L6 | B | L2, L5 | The agent reaches a model on Linux; P2 |
| L7 | B | L4 | Bounded containers on the Pi |
| L8 | C | L2; only if `id -u` is not 1000 on the Pi or on CI's runner | P2 on such a runner |
| P1 | R | The owner's OK on minutes, and how often (design 0014 §7) | Checks on arm64 |
| P2 | R | P1's OK; L6, and L8 where needed | The image and the escape tests in CI |
| P3 | R | Nothing | The Pi's profile; the 32-bit and page checks |
| P4 | C | P6; the owner's answer in design 0014 §8 | `clank code` from an SSH shell |
| P5 | C | The owner's answer in design 0014 §8 | VS Code's Remote-SSH |
| P6 | R | Nothing | No window reported that did not open |

**B**: needed before the first session on the Pi. **R**: recommended before relying on it. **C**: only if its
condition holds. Now: L0's tool, L1, P3 and P6.

## Review Focus

1. **No docker command reaches a stopped engine.** Every command Clank sends to an engine goes through the adapter:
   its 5-second check, the container commands, the `docker exec` commands it hands back, the meters' `docker stats`
   and the doctor's checks (L4). `docker-engine` sends none while systemd says Docker's service is not active, read
   again before each command (L2). The meters ask only while Docker's last reading is running (L4). Only `docker
   --version`, `docker context show` and `docker desktop version` stay outside, and none reaches an engine. Docker's
   socket activation would start the engine on any of the others.
2. **The socket and its listeners.** The folder is 0700. The socket is bound inside it and set to 0600 before it
   listens. The process's umask is never changed, and Uvicorn's own option, which leaves 0666, is never used. The TCP
   listener keeps `SO_REUSEADDR` and today's exit on a port that is taken (L5).
3. **Never a new address.** On Linux the gateway's listeners are 127.0.0.1 and the socket, and nothing else (under
   option (b): and the outer bridge's address, with the peer check) (L5).
4. **Only the edge sees the socket's folder**: never inside or holding `CLANK_HOME`, the folder Clank runs from or a
   workspace's folder, both ways (L5, L6).
5. **The host's own address on a workspace's network answers nothing** on Docker Engine, and the probe never listens
   on every address (L6).
6. **A workspace opens only with its memory limited**, or with the owner's allowance shown in every client (L7).
7. **The recordings hold nothing personal** (L0, P3).

## Tasks

### Lane L: Docker Engine on Linux

#### L0. Docker Engine's recording (B)

- [x] **Tests first:**
  - `tests/tools/test_capture_docker_engine.py` (design 0014 §2):
    `test_a_capture_keeps_each_commands_status_output_errors_and_time` (with a fake runner);
    `test_a_capture_replaces_ids_names_and_host_values_alike_everywhere`;
    `test_a_capture_runs_only_its_listed_commands_and_never_sudo` (and keeps only the fields of `docker info` that
    Clank reads); built with two more:
    `test_three_captures_merge_into_the_recording_saying_where_which_version_and_what_was_replaced` and
    `test_a_capture_whose_engine_was_not_in_the_state_it_names_is_refused_saying_so` (so a job whose engine was not
    stopped, or whose user was in the docker group, fails saying so).
  - `tests/fakes/test_recorded.py` (design 0001 §8.3):
    `test_a_recorded_answer_gives_its_errors_to_a_caller_that_asks_for_the_whole_answer`.
  - `tests/tools/test_workflows.py` (design 0014 §2):
    `test_the_recording_job_runs_only_by_hand_and_prints_the_recording_between_markers`.
- [x] **Files:**
  - Create `tools/capture_docker_engine.py` (development only). It uses the standard library only, so a user outside
    the docker group can run it with the system's `python3`. Its commands are exactly those the adapter will send
    (L2), and the contract test catches any that differ later:
    - `systemctl show docker.service --property=LoadState --property=ActiveState`;
    - `docker -H unix:///var/run/docker.sock version --format {{.Server.Version}}`;
    - `… ps --all --no-trunc --format …` (the base's template), and `… container inspect --format …` of the ids it
      lists;
    - `… info --format …`, with only the fields Clank reads: the CPUs and the memory (`{{.NCPU}} {{.MemTotal}}`, as
      today), and `MemoryLimit` with the warnings (`{"limit":{{json .MemoryLimit}},"warnings":{{json .Warnings}}}`,
      L7);
    - as built, also `… stats --no-stream --format {{json .}}`, the meters' command, which goes through the adapter
      from L4.
  - The tool's options: `--state` names the state captured (`running`, `stopped`, `no access`); `--merge` joins three
    captures into `program.json`, whose `how` says where, which version, and what was replaced; `--examples` makes,
    before `running`, four containers from a tiny public image, one of each sort the contract checks
    (`tests/fixtures/README.md`), and removes them after. It changes nothing else: whoever records stops the engine
    (both units, so its docker commands wake nothing), or works as a user outside the docker group, before each
    state.
  - `tests/fakes/recorded.py`: an answer may carry its errors as a fourth value (`[status, output, seconds,
    errors]`), and the shorter forms read as before. `RecordedProgram.answer(arguments, timeout, input) -> Answer`.
  - `tests/contract/test_container_platform.py`: `build()` passes `answer=program.answer`. Docker Desktop's cases pass
    unchanged.
  - `tests/fixtures/README.md`: the errors; a platform Clank does not start, and its states; how a recording is made.
  - Create `.github/workflows/record-docker-engine.yml`: `workflow_dispatch` only, on `ubuntu-24.04`. Its steps
    capture `running` (with `--examples`); then `stopped`, after `sudo systemctl stop docker.socket docker.service`,
    starting Docker again after; then `no access`, the tool run by a user the job makes for it, outside the docker
    group, from a folder that user can read. It merges them and prints `program.json` between two marker lines in its
    log, so no action is added to keep it. The log shows `docker version`, so what was recorded is on record.
- [x] **Done when:** the tool, the fake's errors and the job are committed, and `tools.check` passes.
- [ ] **Then the recording**, made as the owner chose (design 0014 §2):
  - the job, once the owner approves its few x64 minutes: `gh workflow run record-docker-engine.yml`, then the
    recording taken from `gh run view --log`;
  - or the owner on the Pi, during the dry run: `no access` before joining the docker group, then the other two.

  An agent reads it whole; the secrets check reads it too. It becomes
  `tests/fixtures/docker-engine/<version>/program.json` in L2's commit, whose tests it feeds.

#### L1. One base class for the plain docker CLI (B)

- [x] **Test first** (`tests/components/workspaces/test_docker_cli.py`, design 0014 §2):
  `test_every_container_command_is_the_plain_docker_cli_both_adapters_share`. Each container method of the interface
  (`limits` to `exec_argv`, `workspaces/adapters/platform.py:128-215`) is `DockerCli`'s own, not overridden in
  `DockerDesktop`. It fails today: there is no `DockerCli`. Built with
  `test_every_command_starts_with_the_engine_its_adapter_names` (a command handed back, `exec_argv`, too).
- [x] **Files:** create `clank/components/workspaces/adapters/docker_cli.py`. Move into it the container commands
  (`workspaces/adapters/docker_desktop.py:219-342`), the reading of containers and their labels' names
  (`workspaces/adapters/docker_desktop.py:145-167, 389-403`), `find_docker`
  (`workspaces/adapters/docker_desktop.py:71-95`) and the helpers (`_answer`, `_docker`, `_gone_or_done`, `_words`).
  `DockerDesktop` extends `DockerCli` and keeps `docker desktop` and its program
  (`workspaces/adapters/docker_desktop.py:123-143, 169-217, 351-365`). The docstrings of
  `workspaces/adapters/__init__.py` and `workspaces/adapters/platform.py` name the base.
- [x] **Interfaces:** `class DockerCli(ContainerPlatform)`, abstract in `find`, `status`, `request_start` and
  `request_stop`; `DockerCli.containers() -> list[Container]` (the `docker ps` template and the labels' names), used
  by both adapters' `status`; one place where every command's arguments start (`_target()`, empty here), for L2's and
  L3's pins. No public name changes: `TEMPLATE`, `INSPECT`, `PUT_FILES` and `find_docker` stay importable from
  `docker_desktop.py`; as built, Docker's words for a refusal are the base's public `words()`, which L2 reads too.
- [x] **Done when:** the contract test, `tests/components/workspaces/test_docker_containers.py` and every workspace
  test pass unchanged.

#### L2. A `docker-engine` adapter for Linux (B)

- [ ] **Tests first**, on L0's recording, committed with this task:
  - The contract cases on the new recording (`tests/contract/test_container_platform.py`). They fail: there is no
    adapter. The contract gains `test_a_platform_clank_does_not_start_refuses_with_the_command_to_run`, for every
    adapter: where a start or a stop is not supported, its capability is false and names the command, and asking
    raises `PlatformError` in those words, having run nothing. The two cases that assume a start
    (`test_a_start_and_a_stop_are_asked_of_the_program_and_change_its_state`, and the start and stop in
    `test_what_it_supports_is_read_from_the_program`) apply to the adapters that start their platform. Docker
    Desktop's start and stop still run.
  - `tests/components/workspaces/test_docker_engine.py` (design 0014 §2):
    - `test_a_user_outside_the_docker_group_is_told_how_to_join_it` (the state *no access*; its detail names `usermod
      -aG docker`, logging in again, restarting Clank's service, and that the group is equivalent to root);
    - `test_a_service_started_before_the_user_joined_the_docker_group_says_to_restart_it` (the account in the group,
      the process not: `clank stop`, then `clank work`);
    - `test_a_stopped_engine_is_read_from_systemd_and_never_woken` (inactive: no `docker` command is run);
    - `test_no_command_reaches_the_engine_while_systemd_says_it_is_not_active` (a container command, a build, a
      setup and an `exec_argv`: each refused with `sudo systemctl start docker`, nothing run);
    - `test_every_command_goes_to_the_system_engines_socket` (`-H unix:///var/run/docker.sock`, whatever
      `DOCKER_HOST` and the current context say);
    - `test_a_failed_engine_says_where_to_read_why`; `test_without_systemd_the_engine_is_asked_directly`.
  - `tests/components/workspaces/test_docker_containers.py` runs for both adapters.
- [ ] **Files:** create `clank/components/workspaces/adapters/docker_engine.py`. List it in
  `workspaces/adapters/__init__.py:10-15`, and say "Docker Engine on Linux" in the kind's description. Update
  `docs/GLOSSARY.md` (*Container platform*: Docker Engine on Linux now).
- [ ] **Interfaces:** `class DockerEngine(DockerCli)`: `NAME = "docker-engine"`, `LABEL = "Docker Engine"`,
  `PLATFORMS = ("linux",)`. `status()` gives running, starting, stopping, stopped, failed, no access, unsupported or
  not installed. `capabilities()`: status is supported; start and stop are not, each naming its command.
  `request_start()` and `request_stop()` raise `PlatformError` with the command. Every engine command passes one
  guard, `_active()`, which reads systemd (a reading from the last second is reused).

#### L3. The adapter chosen by platform and by what answers (B)

- [ ] **Tests first:**
  - `tests/components/workspaces/test_choosing_a_platform.py` (design 0014 §2):
    - `test_docker_engine_is_used_where_docker_desktop_is_not` (Linux; the docker command's context is not
      `desktop-linux`, and systemd knows Docker's service: `docker-engine`, with its reason);
    - `test_docker_desktop_is_used_on_windows_and_macos_and_where_its_context_is_current_on_linux`;
    - `test_a_stopped_docker_desktop_is_still_chosen_where_no_docker_engine_is_installed`;
    - `test_a_docker_command_without_dockers_system_service_asks_the_engine_directly`;
    - `test_docker_from_the_snap_or_rootless_docker_is_unsupported_saying_how_to_install_docker_engine`;
    - `test_an_adapter_named_in_the_settings_is_used_as_named`;
    - `test_choosing_an_adapter_asks_no_engine` (only `docker context show`, `systemctl show` and `docker desktop
      version` are run, so a stopped engine is not woken);
    - `test_docker_desktop_on_linux_names_its_own_context_and_elsewhere_changes_nothing`.
  - `tests/components/workspaces/test_docker_operations.py`:
    - `test_starting_docker_engine_is_refused_at_once_with_the_command_to_run`;
    - `test_without_access_a_start_names_the_docker_group_not_systemctl`;
    - `test_stopping_docker_engine_is_refused_before_any_question_about_other_containers`.
  - `tests/components/workspaces/test_workspace_operations.py`:
    `test_opening_a_workspace_while_docker_engine_is_stopped_names_the_command_to_start_it`.
  - `tests/components/agents/test_work.py`: `test_work_never_asks_a_docker_the_system_runs_to_start`. Docker's view
    says stopped, and `starts` is false: no `POST docker/start` is sent, the status's detail is printed, and the exit
    status is 1. Also `test_code_never_asks_a_docker_the_system_runs_to_start`.
  - The folder page: `test_the_folder_page_shows_the_command_for_a_docker_clank_does_not_start`.
- [ ] **Files:** `workspaces/kinds.py:25-28` (`adapter`: `auto` by default; its description lists `auto`,
  `docker-desktop` and `docker-engine`); `workspaces/service.py:69-72` (`choose_platform`), `119-125` (the platform
  property uses it), `322-368` (start and stop refused at once, in the status's words), `459-469` (the view gains
  `chosen` and `starts`) and `494-498` (`_require_usable` refuses *no access* too); `workspaces/folders.py:157-160`
  (the status's detail); `workspaces/adapters/docker_desktop.py` (`--context desktop-linux` on Linux);
  `agents/cli.py:67-77`; `agents/console/folder.py:729-732`. Regenerated: `clank/schemas/docker.schema.json`,
  `vscode/src/core/kinds.ts`.
- [ ] **Interfaces:** `choose_platform(setting: str, platform: str = sys.platform, answer: TimedAnswer = run_answer,
  which: Callable[[str], str | None] = shutil.which, environ: Mapping[str, str] = os.environ) -> tuple[str, str]`:
  the adapter's name, and why. `GET /docker` gains `chosen: str` and `starts: bool`.

#### L4. The doctor and the meters ask the platform (B)

B because, until it is built, the meters would start again an engine the owner stopped with `sudo systemctl stop
docker` alone (its socket still listening), within 10 seconds.

- [ ] **Tests first:**
  - `tests/components/machine/test_checks.py` (design 0014 §2, §5):
    `test_docker_checks_report_what_the_container_platform_reports`. A platform that says *no access* gives "Docker
    running" a warning with the docker group, never "start it with `clank docker start`". *not installed* on Linux
    names Docker Engine's install; *stopped* on Docker Engine names `sudo systemctl start docker`. Also
    `test_the_doctor_names_docker_from_the_snap_and_rootless_docker_as_unsupported`.
  - `tests/components/machine/test_meters.py` (design 0014 §2): `test_the_meters_never_wake_a_stopped_engine`. While
    Docker's last reading is not running, no container figures are asked for; while it runs, they come through the
    workspaces component, and the rows are as before.
- [ ] **Files:** `machine/checks.py:149-159` (the two checks read `Facts.docker`, the platform's status);
  `machine/detect.py:84-87` (the profile's `docker` from the platform); `machine/cli.py:23-28` and
  `machine/service.py:123-140` (both build the facts from the platform the settings choose, read without the service
  in the command); `machine/meters.py:160-220` (`Containers` takes the workspaces' function instead of running
  `docker`); `machine/service.py:67`; `machine/component.py` (`uses=("workspaces",)`); `workspaces/service.py` (public
  `read_platform(home)` for the doctor and `container_stats()` for the meters);
  `workspaces/adapters/docker_cli.py` (`stats()`). `tests/components/machine/test_doctor.py`.
- [ ] **Interfaces:** `Facts.docker: PlatformStatus | None`; `read_platform(home: Home) -> PlatformStatus`, from
  `config/docker.json` and `choose_platform`; `Workspaces.container_stats() -> list[dict[str, Any]]`, empty unless
  Docker's last reading is running; `DockerCli.stats() -> str`.
- [ ] **Done when:** `tests/test_architecture.py` passes, with the new use declared and no cycle.

#### L5. The gateway's Linux listener (B)

Option (a), recommended in decision 0071:

- [ ] **Tests first** (Linux only; `tests/components/gateway/test_listeners.py`, design 0014 §3):
  - `test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it`: the gateway's listeners are 127.0.0.1 at
    its port and `gateway.sock`. The socket is 0600, in a 0700 folder outside `CLANK_HOME`, and answers `/health`. No
    other address listens.
  - `test_the_socket_folder_is_never_the_home_folder_nor_inside_or_holding_clank_home_or_the_folder_clank_runs_from`.
  - `test_the_socket_is_set_to_0600_before_it_listens_and_the_umask_is_never_changed`.
  - `test_on_linux_the_gateways_port_is_bound_for_reuse_so_a_restart_finds_it_free`.
  - `test_a_port_another_program_holds_ends_the_gateway_as_before_saying_so` (logged; exit status 3).
  - `test_a_stale_socket_is_replaced_and_any_other_file_is_left_saying_why`.
  - `test_a_socket_path_too_long_for_linux_is_refused_saying_so`.
  - `test_no_test_makes_a_socket_folder_in_the_real_home_folder` (the session's `XDG_CACHE_HOME`).
  - In `tests/components/gateway/test_service.py`: `test_on_linux_the_service_starts_the_gateway_with_its_socket`;
    `test_the_gateways_status_names_its_socket` (`GET /gateway` and `clank gateway status`);
    `test_a_gateway_running_without_its_socket_is_started_again_once_idle` (adopted from before, or its folder
    removed).
  - The console: `test_the_gateway_row_names_the_socket_when_there_is_one`.
- [ ] **Files:** `gateway/kinds.py` (`socket_folder`: empty means `$XDG_CACHE_HOME/clank/<home id>`, else
  `~/.cache/clank/<home id>`; used on Linux only); `gateway/service.py:226-258` (`edge_socket()`, public; `--socket`
  in the gateway's command line on Linux; the status's `socket`; a gateway without its socket started again once
  idle); `gateway/server.py:571-612` (`listeners(port, socket)`, made before Uvicorn runs: the TCP socket with
  `SO_REUSEADDR`, its bind failure logged with exit status 3; the Unix socket bound in its folder, then set to 0600,
  then listening; `uvicorn.Server(...).run(sockets=...)`; the socket removed when the gateway stops; on other systems,
  unchanged); `gateway/cli.py:45`; `clank/console/pages/home.py:168-180`; `tests/conftest.py` (`XDG_CACHE_HOME`).
  Regenerated: `clank/schemas/gateway.schema.json`, `vscode/src/core/kinds.ts`.
- [ ] **Interfaces:** `Gateway.edge_socket() -> Path | None` (None off Linux); `checked_socket_folder(folder: Path,
  clank_home: Path, runs_from: Path) -> Path`, refusing with the reason (`runs_from`: the folder Clank runs from,
  `Path(clank.__file__).resolve().parents[1]`); `listeners(port: int, socket: Path | None) -> list[socket.socket] |
  None`; `GET /gateway` gains `socket: str | None`.

Option (b), if chosen instead: `test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it` (its listeners
are 127.0.0.1 and the outer network's gateway address) and `test_a_peer_outside_clanks_network_is_refused` (a peer from
another subnet, another computer's included, gets no answer, and the refusal is recorded). The service makes the outer
network before it starts the gateway (`workspaces/folders.py:170-175` moves to the service's start), and
`gateway/server.py` gains the peer check.

#### L6. The edge reaches that listener on Docker Engine (B)

- [ ] **Tests first:**
  - `tests/components/workspaces/test_sandbox.py` (design 0014 §3):
    `test_on_docker_engine_the_edge_forwards_to_the_gateways_socket_and_mounts_nothing_else` (one read-only bind of
    the socket's folder at `/run/clank`; the owner's user id; no `--add-host`; the outer network as on Docker
    Desktop); `test_on_docker_desktop_the_edge_still_forwards_to_the_hosts_loopback` (today's arguments, exactly).
  - `tests/components/workspaces/test_edge.py`: `test_the_edge_forwards_to_a_unix_socket` (Linux only).
  - `tests/components/workspaces/test_workspace_operations.py`:
    `test_a_workspace_folder_that_holds_the_socket_folder_is_refused` (and one inside it);
    `test_a_socket_folder_inside_a_workspaces_folder_keeps_every_workspace_from_opening_saying_which`;
    `test_an_edge_that_no_longer_reaches_the_gateway_is_made_again`.
  - Docker-marked, in `tests/docker/test_escape.py` (Linux only): `test_the_edge_reaches_the_gateway_on_linux`;
    `test_on_linux_the_hosts_own_address_on_a_workspaces_network_answers_nothing`. Its probe listens only on the
    workspace network's gateway address, read with `docker network inspect`, never on every address; a host with no
    address there refuses the probe's bind, which passes too. The stand-in gateway (`tests/docker/test_escape.py:43-52`)
    listens where the gateway does on each platform: on Linux, on a socket in a short temporary folder named in the
    test's `config/gateway.json`.
- [ ] **Files:** `workspaces/sandbox.py:92-111` (read-only binds in `ContainerSpec`) and `154-195` (`edge_spec`
  with `socket_folder` and `user`; `run_arguments`); `workspaces/image/edge.py` (a target `unix:<path>`, with
  `asyncio.open_unix_connection`); `workspaces/adapters/platform.py` (`HOST_LOOPBACK`: whether `host-gateway` reaches
  the host's loopback; True for Docker Desktop, False for Docker Engine); `workspaces/folders.py:77-96`
  (`checked_folder` refuses a folder that holds the socket's folder or is inside it) and `150-183` (on Docker Engine:
  the socket's folder checked against every workspace's folder; the edge with that folder; the health probe through
  the edge, and the edge made again when it fails); `workspaces/service.py:281-286` (`gateway_socket()`, from the
  gateway's service). Docs: design 0004 §3 points to design 0014 §3.
- [ ] **If the host's own address answers:** the workspaces' networks are made with
  `com.docker.network.bridge.inhibit_ipv4`, and the docker-marked test proves the address no longer answers. The
  outer network keeps its address: it is the edge's way out.
- [ ] **Interfaces:** `edge_spec(home, image, *, gateway_port, socket_folder: str | None = None, user: str = USER)`;
  `ContainerPlatform.HOST_LOOPBACK: ClassVar[bool]`; `ensure_network(..., options: Mapping[str, str] | None = None)`;
  `checked_folder(given: str, clank_home: Path, socket_folder: Path | None = None) -> str`.

#### L7. A workspace opens only with its memory limited (B)

- [ ] **Tests first** (design 0014 §4, §5):
  - `tests/components/workspaces/test_workspace_operations.py`:
    `test_a_workspace_does_not_open_where_docker_cannot_limit_memory_saying_how_to_fix_it` (Docker's words, and
    `cgroup_enable=memory` in `/boot/firmware/cmdline.txt` on a Raspberry Pi);
    `test_allowing_unlimited_memory_opens_it_and_every_client_is_told` (the workspace's log, and Docker's summary);
    `test_dockers_memory_limits_are_read_when_a_workspace_opens_never_in_the_regular_check`.
  - `tests/components/machine/test_checks.py`:
    `test_the_doctor_fails_when_docker_cannot_limit_memory_and_warns_when_it_is_allowed`.
- [ ] **Files:** `workspaces/adapters/docker_cli.py` (`memory_limits()` and `warnings()`, from `docker info
  --format` with `MemoryLimit` and `Warnings` only); `workspaces/kinds.py` (`allow_unlimited_memory`, false by
  default); `workspaces/folders.py:150-183` (the refusal in the record step; the log line when allowed);
  `workspaces/service.py` (the summary says "memory not limited"); `machine/checks.py` (the check "Docker limits
  memory"). Regenerated: `clank/schemas/docker.schema.json`, `vscode/src/core/kinds.ts`.
- [ ] **Interfaces:** `ContainerPlatform.memory_limits() -> bool | None`; `ContainerPlatform.warnings() -> list[str]`;
  `DockerSettings.allow_unlimited_memory: bool = False`; `GET /docker` gains `memory_limits: bool | None`, the last
  reading.

#### L8. A folder the agent cannot write is refused, saying why (C)

Only if `id -u` on the Pi, or on CI's runner (P2), is not 1000.

- [ ] **Test first** (`tests/components/workspaces/test_workspace_operations.py`, design 0014 §4):
  `test_on_linux_a_folder_the_agent_cannot_write_is_refused_saying_why`. On Docker Engine, a folder that uid 1000 may
  not write is refused. The words say that the agent works as user 1000 in its container, whose folder it is, and how
  to let it write.
- [ ] **Files:** `workspaces/folders.py:150-161` (the record step asks the platform's rule; Docker Desktop's file
  sharing has none); the tests' folders in `tests/docker/` are opened to uid 1000 where the runner's user is not 1000.

### Lane P: the Pi's own checks, and CI on arm64

#### P1. `tools.check` on arm64 (R)

After the owner's OK on billed minutes, and the owner's choice of how often (design 0014 §7).

- [ ] **Test first** (`tests/tools/test_workflows.py`, design 0014 §7): `test_the_checks_run_on_arm64_linux`. A job
  of `.github/workflows/checks.yml` runs the Python 3.12 checks on `ubuntu-24.04-arm`, on the triggers the owner
  chose: nightly, on version tags and by hand (recommended), or on every push. The other jobs' triggers do not change.
  The workflow is read as text.
- [ ] **Files:** `.github/workflows/checks.yml` (the job `arm64`, the same steps as the job at lines 23-39; a
  `schedule` trigger if nightly).

#### P2. The docker-marked tests in CI, on Linux x64 and arm64 (R)

After P1's OK and L6 (and L8 where the runner's user is not 1000).

- [ ] **Test first** (`tests/tools/test_workflows.py`): `test_the_docker_tests_run_in_ci_on_linux_x64_and_arm64`. A
  job runs `uv run pytest -m docker tests/docker` on both runners, on version tags and by hand. Then the docker tests
  themselves, which are skipped today (`tests/docker/conftest.py:19-26`).
- [ ] **Files:** `.github/workflows/checks.yml` (the job `docker`). The job's log shows `id -u`, `getconf PAGESIZE`
  and `docker version`, so what each runner proves is on record.

#### P3. The Pi's profile, the 32-bit check and the 16 KiB page warning (R)

- [ ] **Tests first** (`tests/components/machine/test_detect.py` and `test_checks.py`, design 0014 §5):
  - `test_a_pi_5s_cpuinfo_gives_its_model`: a Pi 5's `/proc/cpuinfo`, with a made-up serial number, gives the model
    "Raspberry Pi 5 Model B Rev 1.0", and `lscpu`'s answer gives the processor "Cortex-A76".
  - `test_the_profile_never_holds_the_boards_serial_number`.
  - `test_a_64_bit_kernel_with_32_bit_programs_fails_saying_to_install_64_bit_raspberry_pi_os`: `platform.machine()`
    says `aarch64`, Python's word is 4 bytes and `dpkg --print-architecture` says `armhf`; the check "64-bit
    programs" fails.
  - `test_the_doctor_warns_on_16k_pages_with_its_fix`: 16,384-byte pages on a Raspberry Pi warn, naming
    `kernel=kernel8.img` in `/boot/firmware/config.txt`; on another Linux computer, a kernel with 4 KiB pages.
  - `test_the_page_check_is_skipped_where_containers_run_in_docker_desktops_own_linux`.
- [ ] **Files:** `machine/kinds.py:23-41` (`architecture`, `programs`, `page_size`, `model`); `machine/detect.py:55-98`
  (the model from cpuinfo's `Model` line; the processor from `lscpu` when there is no `model name` line; the page
  size from `mmap.PAGESIZE`; the architecture from `platform.machine()`; the programs from `struct.calcsize("P")` and,
  on Debian, `dpkg --print-architecture`); `machine/checks.py:171-182` (the checks "64-bit programs" and "Memory pages
  of 4 KiB"); `machine/cli.py:33-37` (the first line). Regenerated: `clank/schemas/machine.schema.json`,
  `vscode/src/core/kinds.ts`.

#### P4. `clank code` from an SSH shell (C)

Only if the owner will run `clank code` from an SSH shell (design 0014 §8). After P6.

- [ ] **Test first** (`tests/components/agents/test_vscode.py`, design 0014 §8):
  `test_on_linux_the_window_opens_on_the_callers_display`. The caller's `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY` and
  `XDG_RUNTIME_DIR` reach VS Code's program, and P6's check counts the caller's display too.
- [ ] **Files:** `agents/cli.py:52-64` (the variables, sent with the request); `agents/api.py:136-144` (the route
  takes them); `agents/vscode.py:193-196` (the launch uses them); `clank/kernel/processes.py:127-143`
  (`launch_program` takes an environment).

#### P5. VS Code's Remote-SSH (C)

Only if the owner will use VS Code's Remote-SSH from a laptop (design 0014 §8).

- [ ] **Test first** (an extension test, `vscode/test/`): "the extension prefers the workspace's side, so over
  Remote-SSH it runs beside the service". The manifest's `extensionKind` is `["workspace", "ui"]`.
- [ ] **Files:** `vscode/package.json:12-15`; `vscode/README.md` (where the extension runs).

#### P6. No window reported that did not open (R)

Whatever the owner answers in design 0014 §8: a service started over SSH has no display, even when `clank code` is
typed on the Pi's desktop.

- [ ] **Test first** (`tests/components/agents/test_vscode.py`, design 0014 §8):
  `test_on_linux_without_a_display_the_window_is_refused_saying_why`. On Linux, when Clank's service has neither
  `DISPLAY` nor `WAYLAND_DISPLAY`, `agents.vscode` fails before VS Code is started. Its words say to run `clank stop`,
  then `clank code` in a terminal on the Pi's desktop; it never says the window opened. On Windows and macOS nothing
  changes.
- [ ] **Files:** `agents/vscode.py:180-196` (the open step checks for a display first).

## The owner's dry runs

Beside the code, as design 0014 §10 lists them, on the Pi at home, before lane L is done:

- the 64-bit system, the page size and memory limits;
- Docker Engine and the docker group, and the recording if the owner makes it (L0): *no access* before joining the
  group;
- `uv sync` and `tools.check`;
- the image's build, and `opencode` kept open for several minutes in it.

After lane L: `uv run pytest -m docker tests/docker` and `uv run clank doctor`. Their results (sizes, times, `free -m`,
`docker stats`) go into a measurement in `docs/measurements/`, with nothing personal.
