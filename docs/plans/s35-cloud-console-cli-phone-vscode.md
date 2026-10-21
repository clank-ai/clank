# Cloud models, part 2: the console, the commands, the phone and VS Code: implementation plan

> Written 2026-10-20 for builders who have not seen the conversation that led to it. Read
> [design 0016](../design/0016-cloud-models.md) first, then this plan. Its partner,
> [plan s34](s34-cloud-service-and-gateway.md), builds the service's and the gateway's part at the same time. **The
> interface between them is plan s34's section "The interface"**: every route, payload, question and event this plan
> uses is there, exactly. Change it only in both plans, in one commit.

**Goal:** design 0016 §11, §13-§17, the clients' part: the console opens on **Add a model** when no model is usable,
and a new user is working after one pass (Cloud: OpenRouter, the agreement, the key pasted hidden, a model from the live
list, its settings, one short request; or Local: today's setup on one screen); the Providers and models page's Cloud
panel; the workspace's question before the agent starts; cost on every page that shows a request, a session or a flow,
and the limits' pause; the commands (`clank model add`, `clank endpoint …`, `clank workspace allow`, `clank mcp local`,
`clank cost`); the phone's model line, cost and pause (left for the phone's redesign, the owner, 2026-10-21: task 16);
VS Code's status bar and model switch.

**Architecture:** Add a model is a page of the runtime component's console (`clank/components/runtime/console/addmodel.py`),
one panel at a time, each screen a small class with its keys; it calls only the routes of the interface. The console's
shared data (`clank/console/data.py`) gains what every page reads: whether a model is usable, the providers, the cost;
the new events refresh them. The key is typed into a hidden field (`clank/console/form.py`'s new `secret` field), sent
once in the body of `PUT /runtime/endpoints/{id}/key`, and dropped from memory. The commands are clients of the same
routes (design 0002 §2.15). The phone's page reads the service's `/api/overview`, which gains the model's provider and
the cost; VS Code reads the same routes as the console.

**Tech stack:** Python 3.12, Textual (the console), click (the commands), pytest; the phone page's plain JavaScript;
TypeScript with Node's runner for VS Code. No new dependency. Console tests drive the console headless against a service
served in the test (`tests/console/conftest.py`) and compare frames with text snapshots (`CLANK_UPDATE_SNAPSHOTS=1`
rewrites them; read the difference before committing).

**Spec:** [design 0016](../design/0016-cloud-models.md) §9, §11 and §13-§17; decisions
[0103](../decisions/0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md),
[0104](../decisions/0104-cloud-cost-is-shown-with-an-optional-limit.md),
[0105](../decisions/0105-with-no-usable-model-the-console-opens-on-add-a-model.md) and
[0112](../decisions/0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md); design 0011 (the
console's panels, windows and style); design 0005 (the phone).

## Global Constraints

- **No network, no real key.** Tests reach only the service served in the test. Until plan s34's routes exist, each
  test mounts task 1's fake of them. The made-up key is `made-up-openrouter-key` (never one that starts with `sk-`).
- **The key is never shown, logged or kept by a client.** The hidden field draws dots, then the last four; a frame, a
  snapshot, the console's log, the command's output and the shell's history never hold it; a test for each.
- **No new dependency.** Tests first, each test file's docstring naming the design sections it verifies, test names
  sentences. Each task is one commit, the generated files regenerated with `uv run python -m tools.check --fix`. The
  owner is the sole author of every commit: no trailer.
- **The console names only the style's colors and marks** (the repository's colors check); every new panel is a
  `Panel` with its title in its border (design 0011); a long line is cut, never wrapped past its panel; the page works
  at 60 columns.
- **Nothing opens a window on the owner's desktop**: console tests run headless, the CLI's tests in-process.

## For the phone app (the owner, 2026-10-21)

The phone is being redesigned as an installed iPhone web app (task 16 is left for it). So that it is as easy as
possible to build, the console, the commands and VS Code here only show what the service gives them: no client works
out a cost, a limit, a consent state or a model's fit, decides what a step of Add a model says or which comes next, or
checks a setting; the service's answers carry the figures and the words, and refuse in words. What the phone reuses:

- **Add a model's steps and words**, made by one client-neutral module of the service's,
  `clank/components/runtime/guide.py`, and served as `GET /runtime/guide[?preset=&folder=]` (every step in order, its
  title and words, where Cloud starts, what the test does and asks, what Ready says) and `GET /runtime/guide/local`
  (the main slot's presets, each with what it still needs here, in order, each step's words, question and call).
- **The models' words**: each model of `GET /runtime/endpoints/{id}/models` carries `said` (its line, itself, what one
  short request costs) and `settings` (its preset's fields, filled); the list carries `said`.
- **Settings and limits taken as typed**: `POST .../presets` and `PUT /gateway/cost/limits` take what was typed and
  refuse in words (400 `invalid`).
- **The cost's words**, made by `clank/components/gateway/costwords.py`: every cost view carries `said` (today, this
  month, the line, the limits, the pause, the warning; `GET /gateway/cost?workspace=` for one workspace), and each
  session's and request's cost its `said`.
- **The key's account in a line**: AccountView's `said`.
- **Questions with a typed answer**: an option may carry `asks` (a number, its unit and its bounds, and what it is), the
  answer's text holding the number; the limit question's `raise` does. Clients show one field for any such option.
- **A workspace's cloud words**, made by `clank/components/workspaces/cloudwords.py`: its question (stronger for a
  workspace that existed before the agreement), its bound in a line (`cloud_said` on its views), what changing it does
  (`cloud_confirm`), and whether its agent may start (`start` on `POST /workspaces/{name}/cloud/ask`); an agent's MCP
  server held back as local only says so (`held`, `held_said` on `GET /agents/servers`).
- **The rest of the cloud's words in the service's views**: a provider's policy (EndpointView's `said.policy`), an MCP
  server's mark (`local_said`), a cloud preset's price (`price_said`), how a request's cost was known (`how_said`), a
  session's cost on its flow's head (`cost.said`), a flow's and each box's (`cost.said` on `GET /flows/view` and the
  flow's view), and the Context window's GPU line for a cloud route (`gpu: {"device": "cloud", "said"}`).
- **How amounts are written**: `clank/money.py`, one module for the service's words and every client.

Each is served by the fake of task 1 until plan s34's routes exist; the report of this plan lists them as requests of
the interface.

## Tasks

### Task 1: The fake of plan s34's routes, for building in parallel

- [x] **Files:** create `tests/fakes/cloud_api.py`: a FastAPI router answering every route of plan s34's interface
  from a small state it keeps (a provider record or none, a key set or not, a list of three made-up models, a cost
  view, workspaces' bounds, the limit), each payload exactly as the interface writes it, with switches for each refusal
  (`key_refused`, `cloud_unreachable`, `no_tools`, `in_use`, `agreement_needed`); a fixture in `tests/console/conftest.py`
  and `tests/cli/conftest.py`, `cloud_api`, that mounts it on the test service's application when the real routes are
  absent (and does nothing once they exist).
- [x] **Tests** (`tests/fakes/test_cloud_api.py`): each route answers the interface's payload; each switch gives its
  refusal in the API's one shape.

### Task 2: What every page reads

- [x] **Files:** `clank/console/data.py` (`usable` from `GET /runtime/usable`; `endpoints` from `GET
  /runtime/endpoints`; `cost` from `GET /gateway/cost`; read at the start and again on the events
  `runtime.endpoint_*`, `runtime.slot`, `secret.set`, `secret.removed`, `gateway.cost`, `gateway.limit_*`,
  `workspaces.cloud_answered`; the names they change: `usable`, `endpoints`, `cost`).
- [x] **Tests** (`tests/console/test_data.py`, design 0016 §11, §14): each is read at the start; each event named
  reads its part again, and only its part.

### Task 3: A hidden field for the key

- [x] **Files:** `clank/console/form.py` (a `secret` field: its value never drawn, dots as it is typed or pasted, then
  `…` and its last four; never in the screen's text, a snapshot or the app's log; cleared on Esc and once sent).
- [x] **Tests** (`tests/console/test_secret_field.py`, design 0016 §4, §14): a pasted key draws as dots and its last
  four; the frame's text and the console's log hold no part of it but the last four; Esc clears it.

### Task 4: Add a model, screens 1 to 3: the choice, the provider, the agreement

- [x] **Files:** create `clank/components/runtime/console/addmodel.py` (`AddModelPage`, in the menu as "Add a model";
  the screens of design 0016 §14 as panels, one at a time; Esc back one screen); `runtime/component.py` (the page).
  Screen 1: `c` Cloud, `l` Local, with this machine's GPU and memory. Screen 2: OpenRouter, where to get a key, Enter.
  Screen 3: what goes, where, what never goes, the MCP servers (`GET /mcp/servers`) each marked local (Space toggles),
  `o` the data policy (`deny`/`allow`), that each workspace asks once, that each request costs money; `y` calls `POST
  /runtime/endpoints` with `agree` and the marks; a provider already added skips to screen 4 (or 5 with its key).
- [x] **Tests** (`tests/console/test_add_model.py`, design 0016 §14, decision 0105): the three screens' frames
  (snapshots); `n` and Esc go back and write nothing; `y` writes the record with the servers marked as shown; an added
  provider starts at screen 4.

### Task 5: Add a model, screens 4 to 6: the key, the model, its settings

- [x] **Files:** `addmodel.py`. Screen 4: the hidden field; Enter calls `PUT /runtime/endpoints/{id}/key`; accepted,
  the account's line (label, the key's limit and what is left, or OpenRouter's advice to set one); refused, the
  service's words and the field cleared. Screen 5: `GET /runtime/endpoints/{id}/models`, the list (name, window, price
  in and out per million, thinking, images), the highlighted model's description, most output and retirement; `/`
  search, `s` sort (most used, price, window, newest), `f` free models with their limits, `↑↓`, Enter. Screen 6: a form
  filled from the model (title, context with its note on cost, output, thinking effort from `efforts`, the day's and the
  month's limits); Enter calls `POST /runtime/endpoints/{id}/presets` and, for the limits, `PUT /gateway/cost/limits`.
- [x] **Tests** (`test_add_model.py`, design 0016 §11, §14): a key accepted shows its account, one refused its words,
  and neither frame holds the key; the list's frame; search, sort and free change it; Enter on a model fills the form
  from it; the form writes the preset and the limits; a model without tools is not offered.

### Task 6: Add a model, screens 7 and 8, and Local

- [x] **Files:** `addmodel.py`. Screen 7: when the main slot runs nothing, `POST /runtime/slots/main/load` and its
  operation followed on the screen, its health's answer, time and cost shown; when a local model runs, `POST
  /runtime/endpoints/{id}/test`, then "load it now? This stops <model> in the main slot" (`y` switches, `n` keeps it);
  a failure's words with `b` (back to the model) and `k` (back to the key). Screen 8: what runs; Docker's state as
  This folder shows it (not installed: where to get Docker Desktop or Docker Engine; stopped: `s` starts it); Enter to
  This folder. Local: the main slot's presets with their fit and needs (`GET /runtime/presets`, `…/plan`, the needs),
  Enter doing what is missing in order through the existing routes (`POST /runtime/installs`, `/runtime/downloads`,
  the load), each asked first and followed.
- [x] **Tests** (`test_add_model.py`, design 0016 §14): a load from an empty slot ends on Ready with the answer and its
  cost; with a local model running, the test, then the question, and `n` leaves it running; each failure code's words;
  Ready's Docker line for each state; Local's screen and its first step.

### Task 7: The console opens on Add a model

- [x] **Files:** `clank/console/app.py` (at the start, when the page asked for is This folder or Home, or none, and
  `usable` is false: Add a model; a page named on the command line opens as asked), `clank/console/header.py` ("no
  model: Add a model" while none is usable).
- [x] **Tests** (`tests/console/test_shell.py`, design 0016 §14, decision 0105): with nothing usable, `clank` opens on
  Add a model; with a model ready, on This folder; `--page models` opens Models, the header saying no model.

### Task 8: The Providers and models page's Cloud panel

- [x] **Files:** `clank/components/runtime/console/providers.py` (the panel **Cloud**: each provider's title, agreement,
  key (last four, label), data policy, OpenRouter's account line, Clank's spending today and this month against the
  limits, the last check, its presets; keys `a` Add a model, `k` the key again (the hidden field in a window), `c` the
  check (its items when it ends), `o` the data policy, `L` the limits (a form), `r` remove (asked first; the refusal's
  words)).
- [x] **Tests** (`tests/console/test_providers_cloud.py`, design 0016 §15): the panel's frame with a provider and
  without; each key calls its route; `r` while in use shows the refusal.

### Task 9: Presets, the picker and Models with a cloud preset

- [x] **Files:** `clank/console/pick.py` (`preset_choices`: the provider `cloud openrouter` and the price),
  `runtime/console/presets.py`, `runtime/console/models.py` (the main slot's cloud model: provider, window, last health,
  "not reached since").
- [x] **Tests** (`tests/console/test_pages.py`, design 0016 §15): a cloud preset's line on each; a switch to it from the
  picker is the switch route as for any preset.

### Task 10: This folder: the workspace's question and its bound

- [x] **Files:** `clank/components/agents/console/folder.py` (`a` first calls `POST /workspaces/{name}/cloud/ask`; when
  a question comes back, a window with it (`y` allow, `n` keep local), then the agent starts or the page says why not;
  the model's line says "cloud"; a line for the workspace's bound with `u` to change it (asked first; `c` stays VS
  Code's); the MCP servers held back as local only; the cost of the workspace's sessions today).
- [x] **Tests** (`tests/console/test_folder.py`, design 0016 §9, §10, §15, decision 0112): with a cloud model and a
  workspace not answered, `a` shows the question and `y` starts the agent; `n` keeps it local and the page says how to
  allow it; a workspace that existed before the agreement shows the stronger words; the held-back servers and the cost
  show.

### Task 11: Cost on Home, the header, Requests, the Monitor and the Flow view

- [x] **Files:** `clank/console/pages/home.py` and `clank/console/header.py` (today and this month; a pause),
  `clank/components/gateway/console/requests.py` (each line's cost, `≈` for an estimate; the details' tokens and how
  the cost was known; a refusal's words), `clank/components/agents/console/monitor.py` and its panels (the session
  line's cost and requests; Now's step cost; the Context window's facts for a cloud model, "On the GPU exactly: does not
  apply: the model runs at OpenRouter's provider", the cache share), `agents/console/flowview.py` and `flowpanels.py`
  (each box's cost, the flow's total, "Models in this flow" with cost so far, a box waiting for the workspace's
  question).
- [x] **Tests** (`tests/console/test_home.py`, `test_requests_page.py`, `test_monitor_page.py`,
  `test_monitor_context.py`, `test_monitor_flow_view.py`, design 0016 §11, §13): each frame with cost from the fake's
  views; an estimate marked `≈`; the GPU panel's words for a cloud route.

### Task 12: The pause, and raising a limit

- [x] **Files:** `header.py` and `home.py` ("cloud paused: today's limit reached · L raise"), `clank/console/app.py`
  (`L` anywhere opens the limits form when paused), `clank/console/pages/questions.py` (the limit question's `raise`
  option asks its amount in words), the Monitor's Now ("held: the cloud spending limit").
- [x] **Tests** (`tests/console/test_cost_pause.py`, design 0016 §11, decision 0104): a `gateway.limit_reached` event
  shows the banner; `L` raises it through `PUT /gateway/cost/limits`; the question's `raise` takes an amount; the banner
  goes on `gateway.limit_raised`.

### Task 13: The commands of the provider

- [x] **Files:** `clank/components/runtime/cli.py` (the group `clank endpoint`: `add openrouter [--agree]` (asks the
  agreement, listing what goes), `key openrouter [--stdin]` (read without echo, or one line of standard input; never an
  argument), `list`, `show`, `models [--search] [--sort] [--free] [--all]`, `preset MODEL [--title] [--context]
  [--output] [--reasoning]` (written, then tested), `check [--model]`, `remove`; each with `--json`).
- [x] **Tests** (`tests/cli/test_endpoint_commands.py`, design 0016 §16): each command's output from the fake's
  answers; `key` with `--stdin` sends the line and prints only the last four; there is no option that takes a key; a
  refused key says why and exits 1; `remove` in use names what uses it.

### Task 14: `clank model add`, and `clank work` with the cloud

- [x] **Files:** `runtime/cli.py` (`clank model add`: the questions of Add a model in the terminal, in its order; the
  key without echo), `clank/components/agents/cli.py` (`clank work` and `clank code`: with no usable model, "No model is
  set up yet: run clank, or clank model add"; with a cloud model and the workspace not answered, the question in the
  terminal before OpenCode starts, answered through `POST /questions/{id}/answer`).
- [x] **Tests** (`tests/cli/test_model_add.py`, `tests/cli/test_work_cloud.py`, design 0016 §9, §14, §16): the whole
  pass with answers on standard input writes the record, keeps the key (never printed), writes the preset and loads it;
  `clank work` asks once, and `n` stops before OpenCode starts, saying how to allow it.

### Task 15: The workspace's bound, local MCP servers, and cost from the command line

- [x] **Files:** `clank/components/workspaces/cli.py` (`clank workspace allow FOLDER --cloud | --local [--yes]`, asked
  first unless `--yes`), `clank/components/tools/cli.py` (`clank mcp local NAME [--off]`; `clank mcp add … --local |
  --cloud-ok`, asked when a provider is agreed and neither is given), `clank/components/gateway/cli.py` and
  `gateway/component.py` (a new group, `clank cost`: `--today`, `--month`, `--sessions`, `--flows`, `--json`; `clank
  cost limit [--day USD|none] [--month USD|none]`).
- [x] **Tests** (`tests/cli/test_cloud_commands.py`, design 0016 §10, §11, §16): each command's output and the route it
  calls; `allow --cloud` without `--yes` asks first.

### Task 16: The phone

**Left for the phone's redesign (the owner, 2026-10-21).** The phone is being redesigned separately; this task, and the
phone's part of every other task here (task 12's question on the phone, task 18's phone tests, the real checks' look
at the phone), is not built by this plan. What it was to build, kept for the redesign:

- [ ] **Files:** `clank/components/remote/app.py` (`/api/overview`: the model's `provider` and `where` (`cloud` or
  `this-machine`); `cost` as `GET /gateway/cost` gives it; each session's `cost`; each flow's `cost`),
  `clank/components/remote/page/app.js` and `style.css` (the model line "cloud · OpenRouter · <title>"; today and this
  month against the limits; the pause's banner; a session's and a flow's cost; the workspace's and the limit's questions
  shown as Clank's questions, the limit's `raise` with an amount).
- [ ] **Tests** (`tests/components/remote/test_overview_cloud.py`, and the page's tests as the phone's are run, design
  0016 §17): the overview's new fields; the page draws them from a made-up overview; the phone sets no key and no
  setting: its only way to raise a limit is the question.

### Task 17: VS Code

- [x] **Files:** `vscode/src/core/controller.ts` and `presenter.ts` (the status bar's model item says "cloud" and the
  pause; its tooltip today's and this month's spending; *Switch model* lists cloud presets as `cloud openrouter ·
  <model>` with their price), `vscode/src/core/kinds.ts` (regenerated).
- [x] **Tests** (`vscode/test/controller.test.ts`, design 0016 §17): the item and the tooltip from made-up answers; the
  pause; the switch's list.

### Task 18: The real routes, the snapshots, the words

- [x] **Files:** the `cloud_api` fixture removed once plan s34's routes exist; every console, command and phone test of
  this plan run against the real service; snapshots rewritten and read; `docs/CODEMAP.md`, `docs/TESTS.md` regenerated;
  this plan's checkboxes; design 0016's status if anything changed.
- [x] **Tests:** `uv run python -m tools.check --fix` passes; `uv run python -m tools.extension --host` is left for
  the owner (it opens a window).
  *Built:* the fake of s34's routes is gone; `cloud_api` is now a bench over the real service (`tests/support/cloud.py`),
  OpenRouter answered by s34's fake and its documented recording. The service gives what the clients read: `GET
  /runtime/guide` (served by the agents' part, which can read the runtime, this computer, the MCP servers, Docker and
  the limits; the runtime writes the words) and `GET /runtime/guide/local`; each listed model's words and settings, the
  list's line, the account's line, a provider's data policy, a cloud preset's `price_said`, a cloud load's `said`, a
  cost row's `how_said`, a cloud model's GPU line, a workspace's `cloud_said` and `cloud_confirm`. The clients read the
  cost view's real shape (`said` a string; `today`, `month`, `limits`, `paused`, `warned` each with its `said`), the
  typed answer's `{kind, unit, min, max, step}`, and send the limits as amounts (`clank.money.dollars`). Its own
  `costwords` and the question words of `cloudwords` went, the service's own being s34's.
  *Left for later (the owner, 2026-10-21, to save rate):* asking whether an MCP server added after the agreement is
  local only (the console's add form, `clank mcp add-json`; the service already defaults it to local only), This
  folder's `c` and VS Code's agent start asking the workspace first (the gateway still holds and asks), a session's cost
  on the Monitor's heading (its head carries none yet), and the MCP views' `local_said`.

## The real checks owed with a key (the owner, 2026-10-21)

After plan s34's real checks: `uv run clank` on a fresh `CLANK_HOME` (a scratch folder, `CLANK_HOME=<scratch>`), the
whole of Add a model with the real key; then a new scratch folder of made-up content, This folder's `a`, the question,
a short task for the agent; then the cost on Home, Requests, the Monitor, the phone and VS Code, and `clank cost`;
then a limit of a few cents to see the pause and its question on the phone. Nothing of the owner's research is used.

## After this plan

The owner's look at the screens (their keys and words are Claude's, design 0016's status says so), then M10's rest
(design 0001 §7.3), and design 0015's endpoints when the owner approves it.
