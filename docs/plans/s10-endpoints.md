# Endpoints: implementation plan

> Written 2026-10-18 with [design 0015](../design/0015-endpoints.md), from the researched plan of that day for running
> Clank on a Raspberry Pi 5 with the agent's model on a remote cluster: its lane E, steps E1 to E14b. Revised
> 2026-10-19 after the design's review: 29 steps. Built once the owner approves design 0015, or tells the agents to
> build while reviewing it (as for designs 0003 and 0004), and after the owner's choices in decisions 0073, 0075 and
> 0077. As for the earlier plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0015: the main slot runs a model Clank did not start, reached at a URL or through an SSH tunnel Clank
opens and keeps open, with the endpoint's key and a server that proves it holds it; `clank work` and `clank code` use
it; and each workspace's content goes no farther than its bound.

**Architecture:** the runtime component gains a settings kind `endpoint` and a kind of adapter `endpoint` (the first,
`openai-compatible`), and a preset names an engine or an endpoint. Loading an endpoint preset is the same operation
with other contents in its steps: a connection plan; the tunnel, the owner's `ssh` with a file Clank writes (decision
0072), started by the local host on the slot's own port; health through it, with the key, that also proves whose
server answers. The slot's route gains its provider, its base URL, the model id, the endpoint whose key it needs, and
its reach. The gateway forwards to the base URL with the endpoint's key (decision 0073), checks each request's
workspace, known by its key, against that reach, and gives each of its other routes a rule (decision 0075). The
watcher reopens a dropped tunnel by an operation of its own.

**Tech stack:** Python 3.12; Pydantic kinds (decision 0015); httpx2 (decision 0026); the owner's own OpenSSH (decision
0072); pytest with a fake `ssh` and a fake OpenAI-compatible server that plays HTTP recordings. No new dependency.

**Spec:** [design 0015](../design/0015-endpoints.md) §1-§17; decisions
[0072](../decisions/0072-the-tunnel-is-openssh-with-a-config-clank-writes.md) to
[0077](../decisions/0077-an-endpoint-serves-the-main-slot.md); design 0001 §2-§4, §6, §7.6, §8.2; design 0002
§2.6-§2.8; design 0003 §6; design 0010 §3.

**Status:** not started. It waits for the owner's approval of design 0015 and the choices of decisions 0073, 0075 and
0077.

## Global Constraints

- Tests come first (design 0001 §8.6): each task starts with the failing test it names first, then the code; test
  names are sentences; each new test file's docstring names the sections it verifies ("Design 0015 §5"), so
  `docs/TESTS.md` lists them.
- No test logs in anywhere, reaches a real server or uses the network: the fake `ssh` (`tests/fakes/ssh.py`, run as
  `[python, tests/fakes/ssh.py]`) and the fake server (`tests/fakes/endpoint.py`) stand in. Real tests run only with
  `-m endpoint`, never with `-m real` and never in CI, against the owner's endpoint by its id, with made-up prompts
  only (E14a).
- No task starts an engine or uses the GPU, except E2's recording of `llama-server` on the CPU, with the owner's
  go-ahead.
- Nothing personal: code, tests, fixtures and documents use made-up names (`login.example.org`,
  `bastion.example.org`, `compute-node:8000`, `you`, `123456`, `example-org/example-coder`); the owner's real values
  live only in their `CLANK_HOME`. Recordings have names and keys replaced, and the secrets check reads them.
- No key on a command line, or in a record, an event, an operation's log, a process's log, the tunnel's file or the
  routes the gateway follows; a test proves each place.
- Every commit passes `tools.check`, the repository's own checks included: no kind of adapter is declared without its
  contract test and its recordings (`tests/test_architecture.py:97-105`), and the uses between components form no
  cycle (`tests/test_architecture.py:67`).
- No window and no terminal opens from a test; `ssh` starts without a window (`clank/kernel/processes.py:119-124`).
- No new dependency (AGENTS.md).
- Each task ends in a commit pushed to `origin main`, after `uv run python -m tools.check --fix` passes, with the
  generated files (the schemas, `vscode/src/core/kinds.ts`, `docs/CODEMAP.md`, `docs/TESTS.md`, `docs/EVENTS.md`,
  `docs/API.md`) regenerated in it; the owner's uncommitted `docs/walkthrough.md` is set aside and never committed; the
  owner is the sole author (no trailer).
- At most two agents work on this plan at once. E9a, E11c and E11d change `clank/components/gateway/server.py`, as
  design 0014's L5 does ([plan s9](s9-linux-and-the-pi.md)): no two of the four are built at the same time.

## Review Focus

1. **A server that is not the endpoint's:** one that takes a wrong key fails the load and the slot before the key is
   ever sent; one that refuses the key fails them at once (E7a, E8b).
2. **A tunnel that drops mid-answer:** a request broken off before any token is sent again once the tunnel is back,
   one broken off after part of its answer ends saying so, new requests wait meanwhile, and a switch back to KVMem
   cancels the reopen (E8a).
3. **A workspace bound to this machine while the main slot runs an endpoint:** refused before anything is sent,
   saying how to widen its bound; nothing of it reaches the fake server (E11c).
4. **What a container can read through the edge:** Notion only with a known key bound to this machine, never without
   a key; the live view only with the local token; infill never through a tunnel (E11d).
5. **Widening:** asked first, saying that the workspace's sessions go whole; a new key, so an OpenCode started before
   keeps the old bound (E11e).
6. **A key:** never in the places the constraints list, nor in a record when a server echoes it back (E4, E5b, E9a).
7. **A silent server:** its request ends saying so, and is never sent again (E9b).
8. **A login that wants a second factor, a network that blocks SSH, an agent that is gone:** refused at once or tried
   again as §5's table says, with what to do (E6b, E8a).
9. **KVMem to an endpoint and back:** the engine stops first, the port is reused (WSL's relay on Windows), and the
   endpoint's load never reads the GPU (E7a, E7c).
10. **A restart of the service while a tunnel runs:** the tunnel is adopted, and the gateway's token still known
    (E5b, E8b).

## Order

The steps, their flags (B: needed for the first session on the Pi; R: before relying on it) and what each waits for
are design 0015 §16's table: 20 B steps, 9 R. With two agents: one builds E1, E3a, E6a, E7a, E7b, E9a, E13, E7c, E8a,
then E8b, E6c, E12b, E12c, E3b and E14b; the other E5a, E2, E4, E5b, E12a, E11a, E11b, E11c, E11d, E11e, E10, then
E9b, E6b and E14a. E7a waits for E2 and E4, and E11c for E9a. Every B step is done before T1 (design 0015 §15).

## Tasks

### E1 (B): the endpoint record and its adapter's module

- [ ] **First, failing:** `test_an_endpoint_names_a_url_or_a_tunnel_never_both`
  (`tests/components/runtime/test_endpoints.py`, design 0015 §2).
- **Files:** `clank/components/runtime/kinds.py` (`Endpoint`, KIND `endpoint`, folder `endpoints`; `Tunnel`),
  `clank/components/runtime/adapters/endpoint.py` (the kind's interface),
  `clank/components/runtime/adapters/openai_compatible.py`, `clank/components/runtime/component.py` (the settings
  kind declared; the kind of adapter is not declared until E2, which brings its contract test and recordings);
  generated: `clank/schemas/endpoint.schema.json`, `vscode/src/core/kinds.ts`.
- **Interfaces:** `Endpoint(title, adapter, url, tunnel: Tunnel | None, auth: "none" | "bearer", reach:
  "this-machine" | "my-servers" | "hosted" = "hosted", insecure = False, timeout_seconds = 600, notes)`;
  `Tunnel(login, jump, remote, ends_at: "login" | "node" = "login", job = "", path = "/v1", identity_file = "", ssh =
  "")`; `EndpointAdapter.options()`, `models(answer) -> list[ServedModel(id, context)]`, `translate(body) -> (body,
  notes)`, `headers(key)`, `refusal(status, headers, body) -> Refusal(kind, words)`.
- **Then:** `test_a_tunnels_reach_is_never_this_machine`, `test_a_missing_reach_reads_as_hosted`,
  `test_an_endpoint_beyond_this_machine_needs_a_key_unless_insecure`,
  `test_plain_http_beyond_the_loopback_is_refused_unless_insecure`,
  `test_a_request_passes_through_unchanged_but_its_model`, `test_vllms_max_model_len_is_read_as_the_context` (the field
  as vLLM's documentation shows it; the contract test on recordings comes with E2).
- **After:** design 0015's approval. **Unblocks:** E2, E3a, E4, E6a, E11a, E12a.

### E2 (B): the kind of adapter, its recordings and contract, the fake server

- [ ] **First, failing:** `test_the_fake_server_refuses_a_request_it_has_no_recording_for`
  (`tests/fakes/test_endpoint_fake.py`, design 0015 §14).
- **Files:** `clank/components/runtime/adapters/__init__.py` (`ENDPOINTS`), `clank/components/runtime/component.py`
  (the kind of adapter declared), `tests/test_architecture.py:97-105` and `clank/kernel/adapters.py`'s docstring (an
  endpoint adapter's recordings are `http.json`), `tests/fakes/endpoint.py` (plays an `http.json`; flags to require its
  key on every `/v1` route, as vLLM does, to take any key, to stall, to answer 429 with a `Retry-After`, to stream
  thinking in a named field, to drop its connection after N tokens), `tools/capture_endpoint.py` (its first form:
  Clank's fixed made-up requests to a URL, written as `http.json`),
  `tests/fixtures/openai-compatible/llama-server-b11588/http.json` (recorded from Clank's own CPU build and one of its
  CPU presets on the loopback, with the owner's go-ahead; what that model cannot show, such as thinking, is said in
  the recording's `how`), `tests/fixtures/README.md` (HTTP recordings described), `tests/contract/test_endpoint.py`.
- **Then (the contract, on every recording of every endpoint adapter):**
  `test_its_models_answer_gives_each_models_id_and_context`, `test_a_streamed_answers_text_finish_and_usage_are_read`,
  `test_a_wrong_key_is_named_as_a_refused_key`; and
  `test_every_kind_of_adapter_has_its_contract_tests_and_every_adapter_its_recordings`, passing with `http.json`;
  `test_the_fake_server_with_a_key_refuses_every_v1_route_without_it`.
- **After:** E1. **Unblocks:** E7a, E14a.

### E3a (B): presets name an engine or an endpoint

- [ ] **First, failing:** `test_a_preset_names_an_engine_or_an_endpoint_never_both`
  (`tests/components/runtime/test_presets.py`, design 0015 §4).
- **Files:** `clank/components/runtime/kinds.py` (`Preset.engine` and `engine_version` optional, `endpoint`, one
  validator), `clank/components/runtime/catalog.py:107-119` (problems by provider),
  `clank/components/runtime/service.py:81-108, 155-204, 299-304` (`route`, `needs`, the preset's view with
  `provider`), `clank/components/runtime/launching.py` (until E7a, loading an endpoint preset is refused, saying so);
  every other reader of a preset's engine keeps working with one (`clank/components/runtime/console/presets.py`,
  `console/models.py`, `console/providers.py`, `clank/components/runtime/cli.py`,
  `clank/components/gateway/console/completion.py`).
- **Then:** `test_every_engine_preset_written_before_reads_the_same` (Clank's own in `clank/defaults/presets/` and the
  tests' own, still `preset/1`), `test_the_runtimes_model_name_never_replaces_an_endpoints_model`,
  `test_an_endpoint_preset_is_for_the_main_slot_only`, `test_an_endpoint_preset_needs_nothing_installed_or_downloaded`,
  `test_every_page_and_command_that_shows_a_preset_shows_an_endpoint_preset`.
- **After:** E1. **Unblocks:** E3b, E7a.

### E3b (R): `endpoint <name>` in every client

- [ ] **First, failing:** `test_the_preset_picker_shows_an_endpoint_preset_by_its_endpoint_and_model`
  (`tests/components/runtime/test_console_presets.py`, design 0015 §4, §12).
- **Files:** `clank/console/pick.py:29`, `clank/components/runtime/console/presets.py`,
  `clank/components/runtime/console/models.py`, `clank/components/runtime/cli.py` (`preset list`, `show`),
  `vscode/src/core/controller.ts:429`; snapshots in `tests/console/snapshots/` (their differences read before the
  commit).
- **Then:** the Presets page's snapshot with an endpoint preset; `clank preset list` prints `endpoint hpc`;
  `vscode/test/controller.test.ts`: "an endpoint preset is listed by its endpoint and its model".
- **After:** E3a.

### E4 (B): keys

- [ ] **First, failing:** `test_an_endpoints_key_is_shown_by_its_last_four_characters_only`
  (`tests/components/runtime/test_endpoint_keys.py`, design 0015 §9).
- **Files:** `clank/components/runtime/service.py` (a key set, shown and removed with its endpoint, through
  `clank/kernel/secrets.py`; the runtime's own read of it, `Secrets.value` naming the launch),
  `clank/components/gateway/records.py` and `clank/components/gateway/activity.py` (each key value the gateway holds
  replaced by `…` and its last four characters, in a record and in the live view: the first writer that could see a
  secret's value, as `clank/kernel/secrets.py:8-10` foresees).
- **Then:** `test_a_keys_value_never_reaches_the_records` (a key the fake server echoes back in its error),
  `test_a_keys_value_never_reaches_the_live_view`, `test_removing_an_endpoint_removes_its_key`.
- **After:** E1. **Unblocks:** E5b, E7a, E12a.

### E5a (B): the kernel's `process` access (decision 0073, option (a))

- [ ] **First, failing:** `test_a_process_token_reaches_only_the_routes_declared_for_processes`
  (`tests/kernel/test_access.py`, design 0015 §9, design 0002 §2.7).
- **Files:** `clank/kernel/api.py:55, 71-93, 153` (`Access` gains `process`; its scheme; a component's routes
  mounted by their level), `clank/kernel/access.py` (process tokens registered by their SHA-256 with the process they
  name, kept in the kernel's state, checked), `clank/kernel/migrations/0004_process_tokens.sql`,
  `clank/kernel/components.py` (a component declares its process routes). The kernel makes no token: the process's
  owner makes it and registers its hash (E5b).
- **Then:** `test_the_local_token_cannot_call_a_process_route`, `test_a_process_route_knows_which_process_calls`,
  `test_a_registered_token_is_known_after_a_restart_of_the_service`, `test_registering_again_replaces_the_old_token`;
  `test_every_route_declares_its_access_level` (`tests/kernel/test_api.py`) covers both levels.
- **If the owner chooses (b):** not built; E5b reads the file instead.
- **After:** decision 0073 chosen. **Unblocks:** E5b.

### E5b (B): the gateway gets an endpoint's key

- [ ] **First, failing:** `test_the_gateway_reads_an_endpoints_key_and_a_local_client_cannot`
  (`tests/components/gateway/test_keys.py`, design 0015 §9).
- **Files:** `clank/components/gateway/service.py` (a token made at each start of the gateway, given in its
  environment, its SHA-256 registered with the kernel), `clank/components/gateway/api.py`
  (`GET /gateway/keys/{endpoint}`, for processes only: answered while that endpoint serves a slot, read through
  `Secrets.value` naming the launch), `clank/components/gateway/server.py` (the key got once per launch, kept in
  memory only while that launch is the route, and got again when the routes say it was set since: they carry when it
  was set, never the key).
- **Then:** `test_a_gateway_adopted_after_a_restart_still_gets_the_key`,
  `test_the_key_is_read_once_per_launch_and_each_read_is_recorded`, `test_a_key_set_again_is_read_again`,
  `test_the_routes_never_carry_a_key`, `test_no_key_is_given_for_an_endpoint_no_slot_runs`.
- **If the owner chooses (b):** the gateway reads `secrets/endpoint/<id>/key` itself and reports each read; first,
  failing: `test_the_gateway_reports_each_read_of_an_endpoints_key`.
- **After:** E4, E5a. **Unblocks:** E9a.

### E6a (B): the tunnel

- [ ] **First, failing:** `test_the_tunnels_command_and_config_are_exactly_these_and_listen_on_the_loopback_only`
  (`tests/components/runtime/test_tunnel.py`, design 0015 §5).
- **Files:** `clank/components/runtime/tunnel.py` (`program(endpoint) -> list[str]`, `tunnel_file(endpoint,
  program, path) -> str`, `tunnel_argv(endpoint, program, port, path) -> list[str]`; each jump named by a quoted
  `ProxyCommand`; the file written to `state/tunnels/<id>.conf`, for the owner only), `tests/fakes/ssh.py` (run as
  `[python, tests/fakes/ssh.py]`; keeps its arguments and its file; answers `-V` and `-G`; for `-N -L`, listens on the
  local port and passes each connection to a fake server, or prints a refusal it is told and ends).
- **Then:** `test_the_jump_host_gets_the_same_options_as_the_login_host`,
  `test_paths_with_spaces_are_quoted_in_the_proxy_command`, `test_a_path_that_cannot_be_quoted_is_refused`,
  `test_known_hosts_is_never_updated`, `test_host_key_checking_is_never_turned_off`,
  `test_no_option_is_passed_on_the_command_line`, `test_an_identity_file_is_named_only_when_the_endpoint_names_one`,
  `test_the_tunnels_file_holds_no_key`, `test_the_fake_ssh_runs_as_a_list_on_every_system`.
- **After:** E1. **Unblocks:** E6b, E6c, E7a.

### E6b (R): ssh's refusals become what to do

- [ ] **First, failing:** `test_sshs_refusals_become_what_to_do` (`tests/components/runtime/test_tunnel.py`, design
  0015 §5).
- **Files:** `clank/components/runtime/tunnel.py` (`reading(lines, jump_set, agent) -> Refusal(words, again)`: §5's
  table; `agent_state() -> str`: on Linux and macOS whether `SSH_AUTH_SOCK` names a live socket, on Windows whether
  the OpenSSH Authentication Agent service runs), `tests/fixtures/openssh/<version>/program.json` (Windows' OpenSSH
  and a Linux one: `ssh -V`, and `ssh -G` on a made-up file; each refusal's words from OpenSSH's own source at that
  version, and as T0, T1 and T5 show them, names replaced).
- **Then:** `test_a_refused_login_is_read_by_its_list_of_methods`,
  `test_a_timeout_says_to_add_the_jump_host_only_when_none_is_set`,
  `test_a_network_that_closes_ssh_before_it_begins_is_named`, `test_a_gone_agent_is_named_with_what_to_do`,
  `test_sshs_resolved_configuration_is_read_from_windows_and_linux_alike`,
  `test_the_ssh_agents_socket_reaches_the_tunnel`, `test_an_ssh_older_than_the_oldest_recorded_is_named`.
- **After:** E6a.

### E6c (R): the tunnel that ends at the node; the job confirmed

- [ ] **First, failing:** `test_a_tunnel_that_ends_at_the_node_forwards_to_its_loopback_through_the_login_host`
  (`tests/components/runtime/test_tunnel.py`, design 0015 §5).
- **Files:** `clank/components/runtime/tunnel.py` (the node's block; `job_state(endpoint, program, path) ->
  JobState(running, node, left)` from `squeue --noheader --jobs <job> --format "%T %N %L"` through the login host),
  `clank/components/runtime/slots.py` (the job confirmed before the tunnel opens; a refused connection waits while the
  job runs), `clank/components/runtime/watching.py` (the slot fails when the job's time has run out).
- **Then:** `test_the_job_is_confirmed_before_each_open`, `test_a_job_that_does_not_run_on_the_node_refuses_the_open`,
  `test_the_slot_fails_when_its_jobs_time_runs_out`,
  `test_with_its_job_running_a_refused_connection_waits_for_the_server_to_load`.
- **After:** E6a, E8a.

### E7a (B): a slot loads an endpoint, and its health is checked with the key

- [ ] **First, failing:**
  `test_loading_an_endpoint_preset_opens_its_tunnel_and_is_ready_once_its_server_lists_its_model_and_answers`
  (`tests/components/runtime/test_endpoint_slots.py`, design 0015 §6).
- **Files:** `clank/components/runtime/launching.py` (`Connection`: the endpoint, its adapter, the base URL, the model
  id, the tunnel's command line and file; `prepare` gives one for an endpoint preset),
  `clank/components/runtime/endpoint_health.py` (`healthy(connection, key) -> Health(ok, final, words)`: a wrong key
  refused first, then the preset's model listed and the tiny request answered, with the key; each refusal that waiting
  cannot change is `final`), `clank/components/runtime/slots.py` (load and switch: plan, start, health and measure for
  a connection; only the port is checked before a start; a `final` failure, or ssh's `open failed` in the tunnel's
  log, fails the load at once), `clank/components/runtime/watching.py:103-117, 153-158` (an endpoint slot's periodic
  check is `healthy`, with the key read once per launch), `clank/components/runtime/service.py`.
- **Then:** `test_a_keyed_endpoint_is_ready_only_when_its_health_check_sends_the_key`,
  `test_the_watchers_health_check_of_an_endpoint_sends_its_key`,
  `test_a_server_that_takes_a_wrong_key_fails_the_load_before_the_key_is_sent`,
  `test_a_refused_key_fails_the_load_at_once`,
  `test_a_model_the_server_does_not_list_fails_the_load_naming_those_it_does`,
  `test_sshs_open_failed_fails_the_load_at_once`, `test_an_endpoint_load_never_reads_the_gpu`,
  `test_a_url_endpoint_loads_without_starting_anything`, `test_a_tunnel_waits_for_a_port_wsls_relay_still_holds`,
  `test_an_ssh_that_ends_while_the_tunnel_starts_fails_the_load_with_its_own_words`.
- **After:** E2, E3a, E4, E6a. **Unblocks:** E7b, E8a.

### E7b (B): the route, kept with the launch

- [ ] **First, failing:** `test_the_route_gives_the_base_url_the_model_name_the_auth_and_the_servers_context`
  (`tests/components/runtime/test_endpoint_slots.py`, design 0015 §6).
- **Files:** `clank/components/runtime/migrations/0003_endpoint_launches.sql` (a launch's `endpoint` and `route`),
  `clank/components/runtime/state.py:92-93` (`engine` and `engine_version` may be empty; `endpoint`, `route`),
  `clank/components/runtime/service.py:43-45, 81-108` (an endpoint launch's route from what it kept, its reach read
  from the endpoint's record each time; the route's new fields: `provider`, `base_url`, `endpoint`, `auth`, `reach`,
  `timeout`), `clank/components/gateway/routing.py:29-48, 91-102` (`SlotRoute` gains them; `serving` needs a base URL,
  not an engine), `clank/components/agents/service.py:305-324`.
- **Then:** `test_the_agents_limits_are_the_servers_context`, `test_every_launch_written_before_reads_the_same`,
  `test_a_change_to_the_endpoints_file_applies_at_its_next_start`,
  `test_a_change_to_the_endpoints_reach_applies_at_once`, `test_no_estimate_learns_from_an_endpoints_launch`.
- **After:** E7a. **Unblocks:** E7c, E9a, E12b, E13.

### E7c (B): unload and switch

- [ ] **First, failing:** `test_unloading_closes_the_tunnel_and_never_touches_the_server`
  (`tests/components/runtime/test_endpoint_slots.py`, design 0015 §6).
- **Files:** `clank/components/runtime/slots.py:324-348` (an endpoint's launch stops its tunnel by its identity, or
  nothing for a URL endpoint, and the slot is stopped either way).
- **Then:** `test_switching_from_kvmem_to_an_endpoint_stops_the_engine_first`, `test_a_url_endpoint_unloads`,
  `test_a_failed_switch_to_an_endpoint_goes_back_to_the_engine_that_worked`.
- **After:** E7b. **Unblocks:** going back to local models (T1).

### E8a (B): the watcher reopens a dropped tunnel

- [ ] **First, failing:** `test_a_dropped_tunnel_is_reopened_at_once_and_recorded`
  (`tests/components/runtime/test_tunnel_watch.py`, design 0015 §7).
- **Files:** `clank/components/runtime/watching.py:91-144` (a tunnel's end starts `runtime.reopen`, never the crash
  rule), `clank/components/runtime/slots.py` (the operation `runtime.reopen`, under the slot's lock: its tries, their
  backoff, and the refusals never tried again; a load, switch or unload of the slot cancels it first, then runs),
  `clank/components/runtime/service.py:87` (the route counts `runtime.reopen` among the operations that change a slot,
  so the gateway waits), `clank/components/runtime/kinds.py` (`reopen_seconds`, 300).
- **Then:** `test_requests_wait_while_the_tunnel_is_reopened` (the gateway, the fake `ssh` and the fake server
  together), `test_reopening_backs_off_and_gives_up_after_reopen_seconds`,
  `test_a_request_a_drop_broke_off_before_any_token_is_sent_again`,
  `test_a_refusal_that_waiting_cannot_change_is_never_tried_again`, `test_a_switch_cancels_a_reopen_in_progress`,
  `test_an_unload_cancels_a_reopen_in_progress`.
- **After:** E7a. **Unblocks:** E6c, E8b; T4's dropped network.

### E8b (R): a server not the endpoint's, misses, URL endpoints, adoption

- [ ] **First, failing:** `test_three_missed_health_checks_fail_an_endpoints_slot_without_a_restart`
  (`tests/components/runtime/test_tunnel_watch.py`, design 0015 §7).
- **Files:** `clank/components/runtime/watching.py:61-117` (endpoint slots checked whether or not they have a process;
  a final failure fails the slot at once; three misses fail it, closing a tunnel still running, never through
  `runtime.restart`; adoption of a tunnel).
- **Then:** `test_a_server_that_takes_a_wrong_key_fails_the_slot_at_once`,
  `test_a_url_endpoints_slot_is_health_checked`, `test_a_tunnel_still_running_after_a_service_restart_is_adopted`,
  `test_a_tunnel_that_ended_while_the_service_was_down_is_reopened_once`,
  `test_a_tunnel_the_owner_opened_is_never_reopened_and_says_so`.
- **After:** E8a.

### E9a (B): the gateway forwards to an endpoint

- [ ] **First, failing:** `test_a_request_for_agent_reaches_the_endpoint_with_its_key_and_the_presets_model_name`
  (`tests/components/gateway/test_endpoints.py`, design 0015 §8).
- **Files:** `clank/components/gateway/server.py:181-221` (the base URL, the translation by provider, the key's header,
  the model id), `clank/components/gateway/routing.py`, `clank/components/runtime/service.py:48-51` (`translate_request`
  for an endpoint's adapter).
- **Then:** `test_the_tools_own_authorization_never_reaches_the_endpoint`,
  `test_a_streamed_answer_from_an_endpoint_reaches_the_tool_unchanged`,
  `test_the_record_names_the_endpoint_and_the_model_id_sent`,
  `test_no_client_of_an_endpoint_turns_certificate_checks_off`.
- **After:** E7b, E5b. **Unblocks:** E9b, E11c, E12c.

### E9b (R): refusals and the read timeout

- [ ] **First, failing:** `test_a_401_and_a_429_are_passed_on_and_recorded_as_what_they_are`
  (`tests/components/gateway/test_endpoints.py`, design 0015 §8).
- **Files:** `clank/components/gateway/server.py:107, 196-246, 321-341` (an endpoint's `timeout_seconds` as its
  requests' read timeout; a timeout told apart from the errors that send a request again, and ended as
  `endpoint_silent`), `clank/components/gateway/records.py` (`refused`; `limited`, until when).
- **Then:** `test_a_silent_endpoints_request_is_never_sent_again` (streamed, and whole),
  `test_a_silent_endpoint_times_out_saying_so`, `test_a_whole_answer_waits_at_most_the_timeout`,
  `test_an_engine_keeps_no_read_timeout`, `test_a_refusal_is_never_sent_again`.
- **After:** E9a.

### E10 (B): thinking streamed as `reasoning` (decision 0074)

- [ ] **First, failing:** `test_the_loop_guard_and_the_live_view_read_thinking_streamed_as_reasoning`
  (`tests/components/gateway/test_server.py`, design 0015 §8).
- **Files:** `clank/components/gateway/server.py:431, 435-460` (one reader of a delta's thinking, used by
  `_read_event`, `_guarded` and `_heard`), `tests/fakes/engine.py` (`--fake-thinking-field reasoning`).
- **Then:** `test_a_stream_cut_during_its_thinking_is_not_sent_again`, `test_a_delta_with_both_fields_is_read_once`,
  `test_the_tool_gets_the_thinking_in_the_field_the_server_sent`.
- **After:** decision 0074 approved. **Unblocks:** servers that stream `reasoning` (current vLLM).

### E11a (B): the gateway keeps a key and a bound per workspace

- [ ] **First, failing:** `test_a_new_workspace_may_send_only_to_this_machine`
  (`tests/components/gateway/test_workspace_keys.py`, design 0015 §10).
- **Files:** `clank/components/gateway/migrations/0001_workspace_keys.sql` (the gateway's first: each workspace's key
  hash, bound, and when each was set), `clank/components/gateway/component.py` (`migrations`),
  `clank/components/gateway/service.py` (public: `workspace_key(workspace) -> str`, made once and kept as the secret
  `workspace/<id>/gateway-key`, each read recorded; `bound(workspace, models, actor)`; `forget(workspace, actor)`;
  `routes()` gains `keys`: each hash with its workspace and bound), `clank/components/workspaces/kinds.py`
  (`Workspace.models`, `this-machine` by default), `clank/components/workspaces/service.py` (gives the gateway each
  workspace's bound at the service's start and at each change of its record, a listener of `settings.changed`,
  `clank/kernel/events.py:188`; forgets a removed workspace).
- **Then:** `test_each_workspace_has_a_key_of_its_own`, `test_a_workspaces_key_is_made_once_and_kept`,
  `test_the_routes_carry_each_keys_hash_and_bound_never_a_key`,
  `test_an_edit_of_a_workspaces_file_reaches_the_gateways_bound`,
  `test_every_workspace_written_before_reads_as_bound_to_this_machine`; `test_the_uses_between_components_have_no_cycle`
  (`tests/test_architecture.py:67`) still passes.
- **After:** E1, decision 0075. **Unblocks:** E11b.

### E11b (B): each workspace's OpenCode and Clank's MCP server send its key

- [ ] **First, failing:** `test_a_workspaces_opencode_sends_its_own_key` (`tests/components/agents/test_opencode.py`,
  design 0015 §10).
- **Files:** `clank/components/agents/adapters/opencode.py:142` (`apiKey` is the workspace's key, from
  `Gateway.workspace_key`), `clank/components/agents/service.py:265-272` (Clank's MCP server gets
  `CLANK_GATEWAY_KEY`), `clank/components/workspaces/image/phone_mcp.py:219-223, 305-308` (it sends `Authorization:
  Bearer` with it; the sandbox image changes, so it is built again).
- **Then:** `test_clanks_mcp_server_sends_its_workspaces_key`,
  `test_a_workspaces_key_is_written_only_into_its_own_container`.
- **After:** E11a. **Unblocks:** E11c, E11d, E11e.

### E11c (B): each model request checked against its workspace's bound

- [ ] **First, failing:** `test_a_workspaces_request_is_refused_when_its_slots_server_is_beyond_its_bound`
  (`tests/components/gateway/test_bounds.py`, design 0015 §10).
- **Files:** `clank/components/gateway/routing.py` (each key's hash, workspace and bound, from the routes; a request's
  workspace by its key's SHA-256), `clank/components/gateway/server.py:161-192` (the check before anything is sent; a
  403, `model_send_denied`, whose words say how to widen; the record's `workspace`).
- **Then:** `test_switching_the_agent_role_to_an_endpoint_never_widens_a_workspaces_bound`,
  `test_a_request_with_no_known_key_may_send_only_to_this_machine`, `test_a_narrower_reach_applies_to_the_next_request`,
  `test_a_request_to_a_hosted_endpoint_is_refused_while_the_service_does_not_answer`,
  `test_nothing_of_a_refused_request_reaches_the_server`.
- **After:** E11b (so every workspace's requests already carry its key), E9a. **Unblocks:** E11e.

### E11d (B): the gateway's other routes

- [ ] **First, failing:** `test_notion_is_refused_to_a_request_without_a_known_key`
  (`tests/components/gateway/test_route_rules.py`, design 0015 §10).
- **Files:** `clank/components/gateway/server.py:115-143` (`/notion/...` by a known key, and under the owner's
  answer (i) only one bound to this machine; `/activity` and `/activity/live` by the local token, read as the
  gateway's client already reads it, `clank/components/gateway/server.py:586-600`),
  `clank/components/gateway/completion.py:86-113` (`/completion` by the local token; an infill request for a role
  whose slot runs an endpoint refused), `clank/components/gateway/service.py:87, 279, 294` (the service's calls send the
  local token); `tests/components/gateway/test_server.py` and `test_completion.py` send it too.
- **Then:** `test_a_workspace_key_cannot_read_the_live_view`,
  `test_the_services_own_calls_read_the_activity_with_the_local_token`,
  `test_an_infill_request_never_reaches_an_endpoint`, `test_notion_answers_a_known_key_bound_to_this_machine`; with
  the owner's answer (i) for Notion, `test_notion_is_refused_to_a_workspace_that_may_send_beyond_this_machine`.
- **After:** E11b (so Clank's MCP server already sends its key, and Notion keeps answering it). **Unblocks:** E11e.

### E11e (B): widening a workspace

- [ ] **First, failing:** `test_widening_a_workspace_to_your_servers_lets_its_requests_through_and_is_recorded`
  (`tests/components/workspaces/test_bounds.py`, design 0015 §10).
- **Files:** `clank/components/workspaces/cli.py` (`clank workspace allow FOLDER --models
  this-machine|my-servers|hosted [--yes]`), `clank/components/workspaces/api.py`,
  `clank/components/workspaces/service.py`, `clank/components/agents/console/folder.py` (the bound shown, and widened
  after asking), `clank/components/gateway/service.py` (`bound`: a wider bound makes a new key and forgets the old
  one's hash).
- **Then:** `test_widening_asks_first_saying_that_the_workspaces_sessions_go_whole`,
  `test_widening_gives_a_new_key_so_an_opencode_started_before_keeps_the_old_bound`,
  `test_narrowing_applies_to_the_next_request`, `test_the_folder_page_shows_the_bound_and_widens_it_after_asking`.
- **After:** E11b, E11c, E11d. **Unblocks:** T1, T4.

### E12a (B): `clank endpoint add`, `key`, `list`, `show`, `remove`

- [ ] **First, failing:** `test_endpoint_add_writes_the_record_and_key_asks_without_showing_it`
  (`tests/components/runtime/test_endpoint_commands.py`, design 0015 §12).
- **Files:** `clank/components/runtime/cli.py` (the `endpoint` group, in `COMMANDS`; `--insecure` says what it
  allows), `clank/components/runtime/api.py` (list, read, add, set the key, remove),
  `clank/components/runtime/service.py`.
- **Then:** `test_a_key_is_never_taken_from_an_argument`,
  `test_endpoint_show_prints_the_tunnels_file_and_the_keys_last_four`,
  `test_endpoint_remove_is_refused_while_a_slot_runs_it_or_a_preset_names_it`,
  `test_insecure_says_what_it_allows`.
- **After:** E1, E4. **Unblocks:** E12b, E13.

### E12b (R): `clank endpoint models`, `set`, `preset`

- [ ] **First, failing:** `test_endpoint_models_lists_each_model_with_its_context`
  (`tests/components/runtime/test_endpoint_commands.py`, design 0015 §12).
- **Files:** `clank/components/runtime/cli.py`, `clank/components/runtime/api.py`,
  `clank/components/runtime/service.py` (each connects as the check does, decision 0076).
- **Then:** `test_endpoint_set_gives_a_new_jobs_node_port_and_id_and_reopens_a_running_tunnel`,
  `test_endpoint_preset_writes_a_preset_for_a_model_the_server_lists`.
- **After:** E12a, E7b. **Unblocks:** E12c.

### E12c (R): `clank endpoint check` (decision 0076)

- [ ] **First, failing:** `test_endpoint_check_prints_each_item_with_why`
  (`tests/components/runtime/test_endpoint_check.py`, design 0015 §11).
- **Files:** `clank/components/runtime/launching.py` (the check's items), `clank/components/runtime/slots.py` (the
  operation `runtime.check_endpoint`), `clank/components/runtime/cli.py`, the console's Providers page (`c`).
- **Then:** `test_a_server_refusing_tool_calls_is_named_with_the_flags_it_needs`,
  `test_the_check_says_whether_the_services_ssh_agent_is_alive`,
  `test_the_check_says_whether_the_server_refuses_a_wrong_key`, `test_an_insecure_endpoint_is_flagged_by_every_check`,
  `test_the_check_opens_a_tunnel_of_its_own_and_closes_it`, `test_the_check_uses_the_tunnel_a_slot_already_runs`,
  `test_the_check_reports_which_field_the_server_streams_thinking_in`,
  `test_a_check_that_cannot_connect_still_lists_what_it_verified`.
- **After:** E12b, E9a. **Unblocks:** diagnosis on the cluster's network.

### E13 (B): `clank work`, `clank code` and the folder page with an endpoint

- [ ] **First, failing:** `test_work_uses_a_ready_endpoint_and_never_loads_daily_262k`
  (`tests/components/agents/test_work.py`, design 0015 §13).
- **Files:** `clank/components/runtime/kinds.py` (`fallback_preset`, `daily-262k`),
  `clank/components/agents/cli.py:28, 93-101`, `clank/components/agents/console/folder.py:51, 683, 779`,
  `clank/components/agents/service.py:59` (each prepared workspace's configuration written again when the main slot's
  limits change, applied at OpenCode's next start, and said).
- **Then:** `test_opencodes_limits_follow_a_model_loaded_after_prepare`,
  `test_the_fallback_preset_is_the_one_the_settings_name`,
  `test_a_workspace_bound_to_this_machine_is_told_before_its_agent_starts`.
- **After:** E7b, E12a. **Unblocks:** T1, T4.

### E14a (R): the capture removes names and keys; the real tests

- [ ] **First, failing:** `test_a_capture_holds_no_host_node_or_key` (`tests/tools/test_capture_endpoint.py`, design
  0015 §14).
- **Files:** `tools/capture_endpoint.py` (host names, node names, user names and keys replaced by made-up ones of the
  same form), `tests/real/test_endpoint.py` (marker `endpoint`, run only with `-m endpoint`: the owner's endpoint by
  its id, `CLANK_TEST_ENDPOINT`; its key from `CLANK_TEST_ENDPOINT_KEY`, set for that run only and held in memory, no
  copy of `secrets/`; made-up prompts only), `tests/real/conftest.py` (the `endpoint` marker skipped unless asked;
  `-m real` never selects it), `pyproject.toml` (the marker declared).
- **Then:** `test_the_secrets_check_finds_nothing_in_a_capture`, `test_the_endpoint_tests_run_only_when_asked`; the
  real tests, `test_the_owners_endpoint_lists_its_model`, `test_it_answers_a_short_request`,
  `test_it_accepts_a_tool_call`.
- **After:** E2. **Unblocks:** E14b.

### E14b (R): the cluster server's recording

- [ ] **First, failing:** the contract tests (`tests/contract/test_endpoint.py`) on the new recording, until the
  adapter reads what that server sends.
- **Files:** `tests/fixtures/openai-compatible/<server>-<version>/http.json`, from the owner's capture through the
  tunnel after T1; read whole before it is committed (no name, no key).
- **After:** E14a, T1. **Unblocks:** contract tests on the real server's answers.

## Dry runs, between the tasks

Design 0015 §15 gives each one's commands. T0 runs now, before any task, and its answers come back before E1. T3 runs
beside the code. The owner asks the cluster's help desk about a long-running server before T1. T1 follows the last B
step. T4 follows T1 and design 0014's L steps (plan s9), and T5 follows T4. E14b needs T1's capture.
