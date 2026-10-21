# Design 0002: the foundation

How the whole of Clank fits together (one service, its components, the processes that carry the traffic, its
clients); the kernel every component is built from; and the order in which the rest is built on it. Started
2026-10-11. Decisions it rests on: [0002](../decisions/0002-design-principles.md) (the principles),
[0003](../decisions/0003-one-terminal-console.md) (one console),
[0006](../decisions/0006-runtime-service-with-adapters.md) (one service with adapters),
[0007](../decisions/0007-settings-in-readable-files.md) (readable files),
[0010](../decisions/0010-serving-setups-are-plug-and-play.md) (plug and play),
[0011](../decisions/0011-agent-programs-are-plugged-in.md) (agent programs are plugged in),
[0012](../decisions/0012-the-phone-page-and-push.md) (the phone page and push alerts),
[0013](../decisions/0013-one-service-control-and-data-planes.md) (one service is the control plane).

## Goal

Clank becomes the whole suite its user works in: real work in VS Code, control from the console, the phone while away.
Every model, serving setup, agent program, tool, skill and mode is plug and play, and the agent is contained: it can
touch and read only what the user gives it. The foundation is built first, and adding a feature later should not need
to change it (the owner: "minimal need to change the foundation"); when it must, the change is a decision, never a
workaround (§3.1). The owner: "it is VITAL we get this right the first time."

**Status:** every section approved on 2026-10-11; §2 and §3 after a revision for an outside review that the owner
shared ([its verdicts](#the-outside-review-of-2026-10-11)). M0 is being built. The parts built on the kernel (workspaces and
containers, network access, agents and modes, tools and skills, the phone, VS Code, and each one's console screens) are
each designed at the start of their own milestone (§3.1), in a design document of their own.

### What the owner asked for

| The owner's words (2026-10-11) | What Clank does | Where |
| --- | --- | --- |
| "connect to MCP servers/download and plug-and-play other MCP servers online", "start and stop other MCP servers" | A catalog of MCP servers (Clank's own list and the official MCP Registry); install; each local server in its own container; start, stop, and choose which tools each workspace and mode may use | M8 |
| "add/remove/edit other skills" | A skills library in the open Agent Skills format (a folder with a `SKILL.md`): install, write, edit, turn on per workspace or mode | M8 |
| "edit things like this directly from the prototype's window that we will be using as the menu and settings and setup" | The console controls every component, not only models; every action is also a command | Every milestone (§3.1) |
| "more explicit examples, and I need to understand how each of these examples are working" | Each milestone's design shows its screens with real examples, and what happens behind each key; M0's console is in §3.2 | Every milestone |
| "VS code to be the main place I do real work" | A Clank extension for VS Code, a client from the skeleton on: status, questions, then sessions, review of changes, mode, completion | M0, M5, M6 |
| "configure the model, load/unload the model, start/stop docker, select the workspace" | The console's Docker controls, then models, then workspaces | M0, M1, M4 |
| "containing the workspace in a container so that the model cannot touch or read anything that I don't want to give it access to" | Every agent runs in a container that sees only its workspace's folders | M4 |
| "very, very specific network access ... look for a certain paper or go onto github and pull or push something" | Offline by default; grants per host, and per repository for git (pulling apart from pushing), for a time or a session; asked for and recorded | M7 |
| "different modes the model can be put in, like a design/plan mode, auto mode" | Modes are readable files saying what the agent may do alone, must ask about, and may not do | M5 |
| "reach me on my phone so I can approve/reject certain commands ... as well as answer questions" | One queue of questions to the user, answerable from any client; the phone page and push alerts (decision 0012) | M0, M9 |
| "monitor the work ... ask the model to do something for me while i am away ... find the figure and to send it to me" | The phone page shows the work live, starts tasks, and receives files the agent sends | M9 |
| "the skeleton of Clank set up before we do any of this ... no technical debt ... minimal need to change the foundation" | §2 defines the foundation against all of the above (checked in §2.17); M0 builds it first, as a skeleton that runs end to end | §2, M0 |

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | The whole system | Approved 2026-10-11; two terms renamed, the `machine` component listed, and two sentences aligned with the outside review after approval (revision log) |
| 2 | The kernel | Approved 2026-10-11, after its revision for the outside review; its choices are decisions 0014-0021 |
| 3 | The skeleton (M0) and the order of milestones | Approved 2026-10-11, after its revision for the outside review |

## 1. The whole system

*Approved 2026-10-11 (decision [0013](../decisions/0013-one-service-control-and-data-planes.md)). Revised after
approval, before any code: "requests" to the user are now called *questions*, and the "reach" component *remote*, so
that neither clashes with a model request or with the verb "reach"; the `machine` component, which §2 and §3 need, is
listed.*

```
 CLIENTS  hold no state; every action is an API call, so every action is also a command
   VS Code extension     console     phone page     clank command     other programs
            \                |            |               |                /
             +----- Clank API: HTTP and one event stream, on this machine; -----+
                    over the tailnet for paired devices while remote access is on
                                          |
 CONTROL PLANE  the Clank service, one process: it decides, records, and serves the API
   kernel       records, events, operations, questions, policy, secrets, processes, adapters (§2)
   components   machine  runtime  gateway  workspaces  network  agents  tools  skills  remote
                                          |  starts, watches and stops
 DATA PLANE  the processes that carry the traffic
   engines      serve the models (design 0001 §2)
   gateway      every model request (design 0001 §6)
   tool hub     every tool call, to MCP servers that each run in their own container (or remotely)
   sandboxes    containers, each holding an agent program (OpenCode first) and only the folders
                its workspace names
   edge         each sandbox's only door: to the gateway, the tool hub and the Clank service,
                and to git or the web only by grant
```

| Component | What it owns | Designed in |
| --- | --- | --- |
| machine | The machine profile and the checks of `clank doctor` | 0001 §2, §7.3; M0 |
| runtime | Which model runs in which slot, and how it is served; switching, checks, trials | 0001 §2-4 |
| gateway | Model requests: roles, sampling, dialects, queues, records | 0001 §6 |
| workspaces | The folders an agent may see, its container, and Docker itself | M0 (Docker), M4 |
| network | What a sandbox may reach: grants, the edge, git with the user's token | M7 |
| agents | Agent programs (one adapter each), sessions, modes | M5 |
| tools | MCP servers: catalog, install, start and stop, the tool hub | M8 |
| skills | The skills library: install, write, edit, turn on and off | M8 |
| remote | The phone page, push alerts, paired devices, whether the user is away; switched on and off | M9 |

Questions to the user (approvals, choices, answers in words) belong to the kernel, because every component asks the
user things. The console, the VS Code extension and the phone page are clients.

- **Control plane and data plane.** The service holds the settings and the state, makes every decision (what runs,
  what is allowed, what to ask the user), and serves the API. It carries no traffic itself: model requests, tool calls
  and network traffic flow through data-plane processes that it starts, watches and stops, and finds again after its
  own restart (as design 0001 §4.6 does for engines). Restarting the service, or closing any client, cuts nothing in
  flight. A data-plane process asks the service when something needs a decision and reports what happened; while the
  service is down, it keeps what was already allowed and refuses anything new.
- **One kernel.** Every component is built from the same parts (§2): records and their schemas, events, long
  operations, questions to the user, policy checks, secrets, process handling and adapters. Because all components
  share them, any client can show any component's state, explain any value and answer any question without knowing
  that component. A new feature is a new component or a new adapter; the kernel should not need to change, and when it
  must, it changes by a decision (§3.1).
- **Clients hold no state.** VS Code for work (sessions, reviewing changes, approvals); the console for control and
  for watching everything; the phone page for approvals, answers, watching and tasks while away; the `clank` command
  for scripts; other programs through the API. Whatever a client can do goes through the API, so the command line can
  do it too (as design 0001 §5.8 promises for the console).
- **Who can reach what.** The API listens on this machine. Paired devices reach it over the tailnet, and only while
  remote access is on (decision 0012). A sandbox reaches nothing but its edge. Every caller is identified (a client, a
  device, an agent's session), and every action is recorded with who did it.
- **Agent programs are plugged in** (decision 0011): OpenCode first, through an adapter, inside the workspace's
  container. What the agent may do is enforced by the container, the edge and the tool hub, not by the agent program.
- **Clank's own traffic is declared.** Each component lists the outside hosts Clank itself contacts for it (model
  downloads, the sources of recipes, the push services). The list is enforced and shown (§2.13).
- **On Windows** (design 0001 §7.1): the service and the engines run in WSL, containers in Docker Desktop, VS Code and
  the console on Windows (through localhost), the phone through the tailnet.

### An example: a push approved from the phone

1. In the workspace `myproject`, the agent (in mode `auto`) runs `git push`.
2. The container has no network, so git's request reaches the edge. The edge reads what the push would change (branch
   `main`, from commit `1a2b3c` to `4d5e6f`: two new commits) and asks the service: may this session make exactly this
   push to `github.com/you/myproject`?
3. Policy (§2.6): the workspace lists that repository as one the agent may push to, and mode `auto` says that a push
   asks first. The service asks the user a question (§2.5) that shows the branch and the two commits.
4. Nobody has used the console or VS Code for ten minutes, so the user counts as away: the question also goes to the
   phone as a push alert.
5. The user taps Approve on the phone. The service tells the edge, which adds the user's token (the agent never sees
   it) and sends exactly the push that was shown; git itself refuses it if `main` is no longer at `1a2b3c`. The edge
   records the branch it changed and GitHub's answer.
6. The agent sees its push succeed. The question, the answer (and from which device) and the push itself are in the
   history, on every client.

### What changed in design 0001

On approval: the runtime service of decision 0006 became the runtime component of the Clank service (decision 0013);
design 0001 §1's diagram is replaced by the one above, while its other points stand; and a sandboxed tool reaches the
gateway through its sandbox's edge (design 0001 §6.6). Both are in design 0001's revision log.

## 2. The kernel

*Approved 2026-10-11, after its revision for the outside review. Its choices (§2.18) are decisions
[0014](../decisions/0014-state-in-sqlite-settings-in-files.md) to
[0021](../decisions/0021-policy-decisions-expire.md).*

The kernel is what every component is built from. It is the one part of Clank that must be right before the rest is
built: a component can be added or rewritten later, but every component depends on these parts. Each part below says
what it is, the rules it keeps, and where it lives. None of it is specific to one feature; §2.17 checks the kernel
against every feature the owner asked for. Its shape is fixed here, but each part is built in the first milestone that
uses it (§3.2), so no part is written before something real needs it.

### 2.1 A component

A component is one package, `clank/components/<name>/`, always with the same files, so a person or a model that has
read one component can find their way in any other:

| File | Holds |
| --- | --- |
| `component.py` | The declaration: what the component owns, the components it uses, its record kinds, event types and permissions (§2.6), its routes, commands, console screens and panels, its doctor checks, the processes it runs, and the outside hosts Clank contacts for it |
| `kinds.py` | Its record kinds, one class each: every field with its type, label, help and default |
| `service.py` | Its logic, and the public functions that are the only way other components use it |
| `api.py`, `cli.py` | Its routes and its commands, both thin: a command calls the API, a route calls the service |
| `console/` | Its screens and panels |
| `adapters/` | Its adapters, when it has a kind of adapter (§2.10) |

A component uses another only through that one's public functions, only if its declaration names it, and never in a
cycle. A test reads every import in the package and fails on anything else, so the parts cannot grow into one another
unnoticed.

### 2.2 Records

Everything Clank manages is a **record** of a **kind**: a preset, a workspace, a mode, a question, a session. Every
record has a `kind`, an `id`, a `title`, its fields and, when it has a life cycle, a `status`. There are two sorts:

- **Settings** are what the user decides. They are readable JSON files (decision 0007): one folder per kind under
  `CLANK_HOME/config/` (`config/presets/daily-262k.json`, `config/modes/auto.json`), or one file for a kind with a
  single record (`config/roles.json`). Clank ships its own in `clank/defaults/`, in the same format; a user file of the
  same name replaces Clank's, and the console shows which one a value comes from (design 0001 §3.5). Every file names
  its schema and version (`"schema": "mode/1"`); an older one is migrated, with the original kept beside it and a test
  for every migration (design 0001 §7.7). The service checks each file against its schema when it reads it, and names
  the file, line and field of any error; reloads a file when it changes on disk; and writes a change made in a client
  back to the file in one fixed format (two-space indents, fields in schema order), so diffs stay small. A change from
  a client carries the version of the file it was based on: if the file changed on disk in between, the change is
  refused and the client shows both versions.
- **State** is what Clank records about what happens: what runs, the last configuration that worked, sessions,
  questions, grants, paired devices, operations, events. It lives in one SQLite database, `CLANK_HOME/state/clank.db`,
  written only by the service, with numbered migrations that are never edited once released. It is read through the
  API, the console and `clank state` commands, or with any SQLite tool. Large streams stay in files, each with a
  retention setting: the gateway's records (`logs/traffic/`, design 0001 §6.5) and each process's output
  (`logs/processes/`).

Each kind is defined once, as a Pydantic class in its component's `kinds.py`. From that one definition Clank produces
the JSON Schema of its files (`clank/schemas/`), the API's description (OpenAPI), and the TypeScript types that the
VS Code extension and the phone page use; a test fails when a generated file is out of date. Every field carries its
label and help, which is what the explain key (design 0001 §5.4) shows for any value of any kind.

Every kind gets the same routes (list and read, and for settings also create, change and delete) and the same console
screens (a list, a detail view, and a form that checks values as they are typed). A new kind is therefore usable from
every client before anyone writes a screen for it; components add their own actions and screens where the generic ones
are not enough. A settings kind declares what a change or a deletion does to a record in use (a preset running in a
slot, the bounds of a workspace whose sandbox runs): it applies at once, applies at the next start, or is refused with
the reason. State changes only through its component's actions (answering a question, revoking a grant, pairing a
device), never through the generic routes.

### 2.3 Events

Everything that happens is an **event**: an `id` (a number that only grows), the `time`, a `type`
(`slot.state_changed`, `question.asked`, `network.denied`), the `subject` (the record it concerns), the `actor` (who
caused it: the user through which client, a paired device, an agent's session, a process, Clank itself), a one-line
`summary` in plain English, and `data` (fields declared per type, kept small: large content such as a diff is
referenced, not copied).

- Events are kept in the state database. They are the history (design 0001 §4.8), shown and filtered on every client
  and kept for a set number of days.
- Clients receive them on one stream, `GET /api/v1/events` (Server-Sent Events), filtered by type and subject. A
  client that reconnects gives the last id it saw: if that event is still kept, the stream resumes after it and the
  client misses nothing; if it is older than anything kept (a phone that was off for weeks), the stream says so, and
  the client reloads the records it shows before following again. Clients never poll (design 0001 §5.7).
- Some events are live only: streamed, never kept, such as the text a model is writing or progress ticks. The record
  they belong to keeps the result.
- Each component declares its event types, their fields and their summary; `docs/EVENTS.md` is generated from the
  declarations.
- A data-plane process sends its events to the service; while the service is down, it keeps them in a spool file and
  sends them when the service is back.
- Components react to one another through events (the remote component sends a push alert when it sees
  `question.asked`). Later features that act on events, such as hooks and schedules, need no change to the kernel.

### 2.4 Operations

Anything that takes more than a moment (a switch, a trial, a build, a download, installing a tool server, starting a
session, a doctor run) is an **operation**: a state record with its status (queued, running, waiting for the user,
done, failed, canceled, interrupted), its steps and progress ("3 of 7: start"), its log, its result, who started it,
and whether it can be canceled. Operations run in the service, never in a client, so closing a client stops nothing,
and every client shows the same progress. An operation locks what it changes (one switch per slot at a time): a
second one is refused with the name of the first and of who started it. Heavy operations, such as builds, run with
limits on cores and priority (principle 6).

- **Steps are recorded** when they start and when they end, and each kind of operation says which of its steps are
  safe to run again (starting Docker is; sending a file to the phone is not).
- **After a restart of the service**, an operation it cut short is marked *interrupted* and then reconciled: its kind
  checks what actually happened (is the engine up? did the file arrive?), records it, and offers to finish. A step
  that is not safe to run again is never repeated without asking the user.
- **Request keys.** A request that starts an operation can carry a key chosen by the client; the same key again
  returns the operation already started, so a phone retrying on a weak connection never starts two.
- **Side effects in the data plane** (a push sent by the edge) are recorded by the process that made them, in its
  spool while the service is down (§2.3), so a restart of the service neither loses nor repeats them.

### 2.5 Questions

The one way any part of Clank asks the user something and waits for the answer. A **question** has:

| Field | Meaning | Example |
| --- | --- | --- |
| `kind` | `approval` (may this happen?), `choice` (one of these), or `text` (an answer in words, with suggested answers) | `approval` |
| `about`, `asked_by` | The record it concerns, and who asks | session `s-12` (the agent, workspace `myproject`) |
| `title`, `detail` | One line; then exactly what: the command, the diff, the host, the agent's reason | "Push 2 commits to github.com/you/myproject" |
| `options` | Each possible answer, and what it does | approve once; approve for this session; always in this workspace; reject; reject and tell the agent why |
| `default`, `expires` | What happens if nobody answers in time | reject after 30 minutes |
| `urgency` | Normal or high | normal |

A question is answered once, from any client (the console, VS Code, the phone, `clank questions answer`), and the
answer records who gave it, from which client, and when. When a question is answered, expires or is withdrawn, an
event says so, and the component that asked acts on that event; a question therefore survives a restart of the
service. An approval covers exactly what the question showed: the part that asked carries out that action and nothing
else (this push of these commits to this branch, this request to this host), and anything different is a new question.
An answer that approves for longer than once creates a grant (§2.6), and its option says in words what the grant will
cover before it is chosen ("pushes to this repository until the session ends"). Design 0001 §4.2's busy check (wait,
switch now, cancel) is a `choice`, so it too can be answered from the phone. Which clients show a question, and
whether it reaches the phone, is up to them and to the remote component; the kernel keeps the queue.

### 2.6 Policy

One function decides whether something may happen: `decide(actor, permission, target)` answers *allow*, *ask* or
*deny*, with the rule that decided and the file and line where that rule is written. It decides for every kind of
actor: an agent's session, a tool server, a paired device, a data-plane process.

- **Permissions** are named and declared by the components that need them: `file.write`, `command.run`,
  `net.connect`, `git.fetch`, `git.push`, `tool.call`, `model.send` (a workspace's content going to a model provider:
  on this machine, on a server of the user's, or a third party's hosted API), `secret.use`, `file.send`,
  `slot.switch`, `session.start`.
- **Layers** of rules, each contributed by a component:
  - Clank's safety floor, shipped in `clank/defaults/policy/floor.json`. It can only deny, and no setting changes it:
    no sandbox or tool server sees `CLANK_HOME` or the folder Clank itself runs from, or gets the Docker socket, extra
    privileges or added capabilities; the home folder or a drive root is never mounted; a push never deletes a branch
    or a tag.
  - The workspace's bounds: what its agent has without asking (folders, hosts, repositories, tool servers, and where
    its model requests may go: this machine only, unless the user widens it). Beyond them the agent may ask for
    access if its mode lets it ask; otherwise the answer is *deny*.
  - The workspace's own rules, which can only restrict.
  - The mode's rules (plan, ask, auto, and the user's own modes).
  - Grants.
- **Combining.** Any *deny* wins. Otherwise any *ask* wins, unless a grant covers it. Otherwise the answer is *allow*
  if some layer allows; and if no layer has a rule, *deny*. A stricter layer always wins over a looser one, so
  switching to plan mode restricts the agent, whatever was granted before. A *deny* is a ceiling: no answer and no
  grant passes it. To allow what a rule denies, the user changes the rule itself, a settings change recorded like any
  other.
- **Grants** are state records created by answers: what they allow (a permission and its exact target, such as
  `git.push` to one repository), for whom (a session, a workspace), until when (once, the end of the session, a time),
  who granted it, and through which question. A grant extends the bounds, never past a *deny*, and can be revoked at
  any time. "Always" instead writes a rule into the user's settings file for that mode or workspace, where it can be
  read and removed.

**Enforcement.** Policy decides; the part that can actually stop an action enforces it, so nothing rests on the agent
program behaving well (decision 0011):

| Permission | Enforced by | How |
| --- | --- | --- |
| Seeing files | The container | Only the workspace's folders are mounted |
| `file.write` | The container | In plan mode the workspace is mounted read-only, so no command can change it (entering or leaving plan mode restarts the sandbox); in other modes it is writable, and asking before each edit is the agent program's own prompt |
| `command.run` | The container, then the agent program | A command can touch only what the container holds; asking before each command is the agent program's own prompt |
| `net.connect`, `git.fetch`, `git.push` | The edge | The sandbox has no other way out |
| `tool.call` | The tool hub | Tool servers can be reached only through it |
| `model.send` | The gateway | Each request is checked against the provider serving it at that moment, so switching a role to a hosted model never widens where a workspace's content goes |
| `secret.use` | The kernel and the edge | No sandbox holds a secret: the edge adds it on the way out; a tool server holds only the secrets granted to it (§2.8) |
| `file.send`, `slot.switch`, `session.start` | The service | Nothing else can do them |

Where the only check is the agent program's own prompt, every client says so ("asked by OpenCode; the container allows
this in mode `ask`"). A workspace that needs more can have its agent work on a copy whose changes the user accepts
(§3.4).

**Decisions expire.** Each decision an enforcement point receives carries the policy's revision and an expiry, and is
kept only until either changes: switching a mode, revoking a grant or editing a rule makes a new revision, and the
service tells every enforcement point at once. `git.push`, `file.send`, `secret.use`, and `model.send` to a third
party are decided at the moment of use and never kept. While the service is down, enforcement points finish what is in
flight (an answer the model is writing), keep their unexpired decisions, and refuse whatever must be decided at the
moment of use (§1). Every decision except reading a file is an event, so the history answers "why was this allowed?"
with the rule and the grant.

### 2.7 Callers and access

Every API call is made by an identified caller, with a token and an access level:

| Caller | Token | Access |
| --- | --- | --- |
| Local clients: the console, VS Code, the `clank` command | The local token, `CLANK_HOME/state/local.token`, readable only by the user: being able to read it proves the caller is the user on this machine | `control`: everything |
| Paired devices (decision 0012) | Its own, created by pairing on the computer; only a hash is kept; it expires and can be revoked | `remote`: answer questions, watch, start tasks, receive files, switch remote access off; not settings or policy (the user can widen or narrow this) |
| Data-plane processes | One per process, given when it starts | `process`: report events, ask for policy decisions, read its own configuration |
| Agent sessions | None of their own: their calls come through the edge, which names the session | `session`: Clank's tools for agents (ask the user, ask for access, send a file, report progress) |

The API listens on this machine (`127.0.0.1`; WSL makes it reachable from Windows). Every route needs a token, reads
included. The service answers only requests addressed to its own host names (a defense against DNS rebinding), sends
no CORS headers, and never puts a token in a URL or a record. Local clients find its address in
`CLANK_HOME/state/connection.json`. Every route declares its access level, and a test checks that none is missing.
Clients tell the service when the user is active (a key pressed in the console, typing in VS Code), at most once a
minute; the remote component uses this to decide whether the user is away.

### 2.8 Secrets

Keys and tokens are files in `CLANK_HOME/secrets/`, readable only by the user (design 0001 §2). A component gets one
through the kernel, which records which component used which secret and why, never the value. Clients see a secret's
name, when it was set, and its last four characters. A secret never enters a sandbox: where an agent's traffic needs
one (a git push), the edge adds it on the way out. It enters a tool server's container only if a grant the user
approved names it. Before anything is written (records, events, the gateway's records, process logs), the kernel
removes the value of every secret it holds, wherever it appears.

### 2.9 Processes and containers

The kernel starts, identifies, watches and stops everything Clank runs, by the rules of design 0001 §4.6 made general:
processes by their id, start time and command line; containers by their id and Clank's labels (which `CLANK_HOME`,
which component, which record). Each has its output captured in `logs/processes/` (rotated), a health check, a restart
rule, resource limits, and the host it runs on (this machine; another machine through an adapter later). Clank stops
only what it started; after its own restart, it finds its processes and containers and adopts them; another program's
process on a port or the GPU is reported, never touched. Containers are run through a container-platform adapter
(Docker Desktop first; Docker Engine on Linux).

### 2.10 Adapters

Each kind of adapter (engine, endpoint, dialect, container platform, agent program, channel, registry) has an
interface, a list of its adapters, one contract test file run against every adapter of the kind, fixtures recorded
from the real program at its pinned version, and a statement of what each adapter supports (design 0001 §8.2-8.3, made
general). A component adds a kind of adapter; one module, its recipe or template, and its fixtures add an adapter.

What an adapter supports is read for the version and the launch options in use, never assumed for a program. KVMem is
the example: v0.16 answers one request at a time and keeps one conversation's cache, while v0.17, launched to, keeps
several conversations and runs up to four requests at once (its documentation, 2026-10-11).

### 2.11 The library: what the user installs

Skills, MCP servers, modes, and test suites or presets shared by others are **library items**, with one life cycle: a
source (shipped with Clank, written by the user, a URL or a git repository, a registry); installing (download, check
the checksum or commit, show what it contains, scripts first, and ask); turning it on where it applies (everywhere, in
a workspace, in a mode); updating (the difference shown first); removing. Where each came from, and its version, are
recorded. Installed items live in `CLANK_HOME/library/<kind>/<name>/`. Items found in a project's own repository (a
`.clank/` folder) are offered, never trusted: their first use asks, so a cloned repository cannot give itself network
access or a tool server. Installing grants nothing: a tool server runs under its own identity and gets the folders,
hosts and secrets its entry asks for only as the user approves each. A skill is text the model reads, so its text is
shown before it is turned on, and nothing it says can widen what the mode allows. The record kinds and the life cycle
are fixed now; the code is built with the first kind that needs it (§3.3).

### 2.12 Files for the user

A file that Clank or an agent makes for the user (a figure the agent was asked for, a trial's report) is an
**artifact**: copied into `CLANK_HOME/artifacts/<id>/`, with where it came from (which session, which file of the
workspace), its type, size and checksum, and how long it is kept. Every client can list and open artifacts; the
remote component sends them to the phone. An agent can offer only files from its workspace's folders.

### 2.13 Clank's own traffic

Each component declares the outside hosts Clank contacts for it (model downloads, the sources of recipes, the push
services). The kernel's one HTTP client refuses every other host; `docs/NETWORK.md` is generated from the
declarations; the console lists them. This is separate from what an agent may reach (§2.6).

### 2.14 The API

HTTP and JSON under `/api/v1/`, plus the event stream (§2.3), built with FastAPI and Pydantic from each kind's one
definition (§2.2). Errors have one shape: a code, a sentence in plain English, and where the problem is (file, line,
field). Version 1 only grows: a change that would break a client becomes `/api/v2`, served beside v1 for one release.
`docs/API.md` is generated.

### 2.15 Commands and the console

- **Commands.** `clank <component> <verb>`, each one a client of the API, printing readable text by default and JSON
  with `--json` (for scripts and models). Only `clank serve` (which starts the service), `clank doctor` (which must
  work when the service cannot start) and `clank setup` act without the service.
- **The console.** The Textual shell (decision 0005): a header with what runs, the list of screens, the command
  palette, the keys bar, the explain panel, one event subscription shared by every panel, and the generic screens of
  §2.2. Components add their screens and panels by declaring them (design 0001 §5.5-5.6).

### 2.16 Where things are

```
clank/
  kernel/        records, store, events, operations, questions, policy, access, secrets, processes,
                 adapters, library, artifacts, outside traffic, api
  components/    machine  runtime  gateway  workspaces  network  agents  tools  skills  remote
                 each: component.py  kinds.py  service.py  api.py  cli.py  console/  adapters/
  console/       the shell, the generic screens, clank.tcss
  cli/           the clank command
  defaults/      Clank's own settings: roles, modes, the policy floor, test suites
  catalog/       models and tool servers known to work
  schemas/       generated JSON Schemas
vscode/          the VS Code extension (TypeScript)
phone/           the phone page
tests/           unit, contract, fakes, api, console, components, fixtures
tools/           development scripts: the code map, the tests page, documentation and secrets checks
docs/            these documents, and the generated CODEMAP.md, TESTS.md, API.md, EVENTS.md, NETWORK.md
```

`CLANK_HOME` (design 0001 §7.2) gains `state/clank.db`, `state/local.token`, `state/connection.json`, `state/spool/`,
`library/`, `artifacts/` and `logs/processes/`.

### 2.17 The kernel against every feature asked for

| Feature | Kernel parts it uses | What it adds |
| --- | --- | --- |
| Models, serving setups, switching (design 0001 §2-4) | records, operations, processes, adapters, events, questions (the busy check) | the runtime component; engine and endpoint adapters |
| Model requests (design 0001 §6) | records, events, processes | the gateway component and its process; dialect adapters |
| Which model providers may see a workspace's content | policy (`model.send`), access (who is calling) | the gateway's check |
| Containment; choosing the workspace | records, processes (containers), policy (the floor, the bounds) | the workspaces component; container-platform adapters |
| Starting and stopping Docker | adapters, operations, questions, events | the workspaces component |
| Very specific network access | policy (`net.connect`, `git.fetch`, `git.push`), grants, questions, secrets (the git token), events | the network component; the edge |
| Modes | records (mode files), policy (the mode layer) | the agents component |
| Agent programs and sessions | adapters, processes, events, questions (their permission prompts) | the agents component; the OpenCode adapter |
| MCP servers: install, start, stop | the library, processes (containers), policy (`tool.call`), secrets, questions | the tools component; the tool hub; registry adapters |
| Skills: add, remove, edit | the library, records, policy (where each is on) | the skills component |
| Approvals and questions from anywhere | questions, grants, events, access | nothing new: the kernel and the clients |
| The phone: approve, answer, watch, start tasks, receive files | access (devices, presence), events, questions, operations, artifacts | the remote component; channel adapters; the phone page |
| VS Code as the place of work | the API, events, questions, the generated types | the extension, a client |
| Later: schedules, hooks, memory, tasks side by side, packs, other machines | events, operations, policy layers, the library, adapters, process hosts | new components |

No line needs a change to the kernel: that is the test this section has to pass.

### 2.18 Choices this section makes

Each is a decision record, written when this section was approved.

| Decision | Choice | Instead of | Why |
| --- | --- | --- | --- |
| [0014](../decisions/0014-state-in-sqlite-settings-in-files.md) | State in one SQLite database; settings stay in files | State in JSON files | An answer, the grant it creates and the events recording both are written together or not at all; the history needs queries by time and record; SQLite is part of Python |
| [0015](../decisions/0015-kinds-defined-once-in-pydantic.md) | Each kind defined once, in Pydantic; schemas, the API's description and TypeScript types generated from it | Schemas written by hand next to the code | One source of truth; the VS Code extension and the phone page get checked types |
| [0016](../decisions/0016-fastapi-and-uvicorn.md) | FastAPI with Uvicorn | Starlette alone; aiohttp | Built on Pydantic; describes its own API; the best known to people and to models (principle 4); the owner's assistant uses it |
| [0017](../decisions/0017-one-server-sent-events-stream.md) | One Server-Sent Events stream | WebSockets | Clients only need to listen (they act through ordinary requests); works in browsers, VS Code and Python without another library; resumes from an event id |
| [0018](../decisions/0018-deny-wins.md) | Deny wins over ask, ask over allow; no rule means deny | The last matching rule wins (as in OpenCode's permissions) | A stricter layer (the floor, a mode) can never be undone by a looser one |
| [0019](../decisions/0019-components-use-declared-public-functions.md) | Components use one another only through declared public functions, checked by a test | A convention | The parts cannot grow into one another unnoticed |
| [0020](../decisions/0020-enforce-where-it-can-be-stopped.md) | Each permission enforced where it can be stopped (the container's mounts, the edge, the tool hub, the gateway); the agent program's own prompts shown as such | Modes enforced through the agent program's permission settings | A shell command can do whatever its container allows; only the container, the edge and the hub cannot be talked around |
| [0021](../decisions/0021-policy-decisions-expire.md) | Decisions carry the policy's revision and an expiry; pushes, files sent, secrets and third-party model requests are decided at the moment of use | An allowed answer kept until its grant ends | Revoking a grant or switching a mode takes effect at once, and the riskiest actions never run on an old answer |

### What changed in design 0001 when this section was approved

§4.8: the history became the event log in the state database (`clank events export` writes it as JSON lines),
instead of `logs/runtime.jsonl`. §7.2: `CLANK_HOME` gained the folders of §2.16. §3.8 and §4.2: trials and switches
are operations (§2.4), and the busy check is a question (§2.5). §3.7: the example preset names its schema
(`"schema": "preset/1"`). §6.4: "KVMem has one slot" became what the KVMem adapter declares for its version and
launch options (§2.10). Each change is in design 0001's revision log.

## 3. The skeleton (M0) and the order of milestones

*Approved 2026-10-11, after its revision for the outside review.*

### 3.1 How the rest is designed and built

Only the kernel had to be settled before building: every component depends on it, so a mistake there is the expensive
kind. Everything else is designed when its turn comes, informed by what the steps before it taught. Each milestone:

1. starts with a short design of its part, in a document of its own: its records, its console screens, its VS Code
   views (and phone views), each with real examples and what happens behind each key, and the tests that must prove
   it works (§3.3); reviewed like these sections;
2. then a plan of small steps, each starting with a failing test (design 0001 §8.6);
3. then the work, each step committed and pushed;
4. and ends with something the owner can run, a version tag, and the documents brought up to date.

Every milestone brings its own console screens and VS Code views; no part waits for a "user interface" milestone. If
building shows that the kernel needs a change, the change is a decision record and a revision of §2, never a quiet
workaround.

### 3.2 M0: the skeleton

Thin, but through every layer: the kernel, the service and its API, the command line, the console and the VS Code
extension. Six steps, each ending with something that runs:

| Step | What is built | What the owner can run |
| --- | --- | --- |
| M0.1 | The package, the development tools (a decision record), continuous integration (tests, lint, types, the documentation and secrets checks), the generated code map and tests page | `clank --version`; a green check on every push |
| M0.2 | The kernel parts M0 uses: records (settings files, schemas, migrations), the state database, events (resuming, and the gap when a client is too far behind), operations (steps, reconciling after a restart, request keys) and questions, with their tests | The tests, and the generated page saying what each one proves |
| M0.3 | The service and its API (the local token on every route, the event stream, the generic routes), the commands, the `machine` component (the machine profile, the doctor checks) | `clank serve`, `clank doctor`, `clank events --follow`, `clank questions` |
| M0.4 | Adapters (kinds, lists, contract tests); the `workspaces` component's first part, Docker, through the Docker Desktop adapter, which tells Clank's containers from others by their labels | `clank docker status`, `clank docker start`, `clank docker stop` |
| M0.5 | The console shell: home, questions, history, Docker, the generic record screens, explain, snapshots | `clank console` (below) |
| M0.6 | The VS Code extension's shell: it connects, shows Clank and Docker in the status bar, lists and answers questions, starts and stops Docker | The same question answered from VS Code or from the console |

The other kernel parts are built, to the shape §2 fixes, in the first milestone that uses them: process supervision
with the first engine (M1), the client for Clank's own outside traffic with the first download, policy with the first
containers and their escape tests (M4), secrets with the first key or token Clank holds, the library with tool servers
and skills (M8), and artifacts with the phone (M9).

Among M0's tests: an operation cut short by a restart is reconciled, never blindly repeated; the same request key never
starts two operations; a client resuming from an event that is no longer kept is told to reload; every route refuses a
call without the token, and a request addressed to another host name; no Clank action touches a container without
Clank's labels, and stopping Docker itself asks first.

M0's questions are real ones. Stopping Docker while containers that Clank did not start are running (the prototype's,
while the two live side by side) asks first, and the answer can come from the console, VS Code or the command line.
What the console could look like at the end of M0:

```
 CLANK  service: up 2h14m · docker: running · questions: 1 waiting                               11:42
 ─ what runs ──────────────────────────────────────────────────────────────────────────────────────────
  service    v0.1.0 · API on 127.0.0.1:7720 · 2 clients connected (this console, VS Code)
  docker     Docker Desktop · running · 2 containers, none of them Clank's                  s stop
  machine    Windows 11 with WSL2 · RTX 5080 16 GB · 62 GB RAM · doctor: 13 of 14 passed     d doctor
  models     (milestone M1)
 ─ waiting for you ────────────────────────────────────────────────────────────────────────────────────
  > q-7f3a  Stop Docker Desktop? 2 containers that Clank did not start are running:        asked 11:40
            another-model-relay, toolbox-sandbox-017
            y stop them and Docker    n cancel    v details
 ─ history ────────────────────────────────────────────────────────────────────────────────────────────
  11:40:02  you (console) asked to stop Docker Desktop; waiting for your answer
  11:39:30  doctor run by you (VS Code): 13 of 14 passed; Docker Desktop started after WSL (d for details)
  11:38:34  service started (v0.1.0)
 1 home  2 questions  3 history  4 docker  F1 help  ? explain  ctrl+p commands  q quit
```

How it works:

- **Opening.** The console reads `state/connection.json`, connects with the local token, loads the current records
  once, then follows the event stream. It holds nothing of its own, so closing it changes nothing.
- **`s` on Docker.** The console calls `POST /api/v1/docker/stop`, which starts an operation. The workspaces component
  finds two containers that Clank did not start, so instead of stopping them it asks a question (§2.5), and the
  operation waits for the user. The question appears here, in VS Code and in `clank questions` at the same moment,
  because all three follow the same events.
- **`y`.** The answer is recorded (the user, from the console, at 11:41); the workspaces component sees
  `question.answered` and the operation goes on: it stops Docker Desktop through its adapter and reports each step.
  Answered from VS Code instead, the same thing happens, and the console shows who answered, and from where.
- **`?` on any value** shows what it is, where it comes from and where it is written (design 0001 §5.4); on the
  question, it shows the rule behind it (design 0001 §4.6: Clank stops only what it started).

### 3.3 The milestones after M0

| # | Milestone | What the owner can do at the end | What its tests must prove |
| --- | --- | --- | --- |
| M1 | Runtime with KVMem (design 0001's M1) | Load, unload, check and switch KVMem presets from the console, VS Code and `clank` | Clank stops only what it started; a failed switch returns to the last configuration that worked; after a restart of the service the engine is adopted, not restarted; what KVMem supports is read for its version and launch options |
| M2 | NInfer RTX 5080, llama.cpp, trials (design 0001's M2) | Switch between the three serving setups and compare their measured speeds and useful work | Every setup passes the same contract; a trial puts back what ran before, even when it fails; memory is measured at its peak, not only at the start |
| M3 | Gateway, and completion in VS Code (design 0001's M3) | Point OpenCode and other tools at Clank by role name; inline completion in VS Code, served through Clank | A request in the provider's own dialect passes through unchanged but for its sampling and credentials; what a translation does not support fails with a clear error; a canceled request stops generating on the engine; completion meets its latency target while the agent is writing |
| M4 | Workspaces and containers | Choose a workspace; its container sees only its folders; its edge reaches Clank's models and nothing else | The escape tests: no file outside the workspace can be read, through symlinks and subprocesses included; in plan mode no command can change the workspace; from inside, nothing but the edge answers (direct addresses, name lookups, IPv6, the host, other workspaces' sandboxes); a workspace's content never reaches a provider it does not allow, even after its role is switched to a hosted model |
| M5 | Agents, sessions and modes | OpenCode in the workspace's container; plan, ask and auto modes; its questions and approvals in VS Code and the console | Entering plan mode makes the workspace read-only for a running session; the program's own prompts reach every client as questions, labeled as the program's; a session survives a restart of the service |
| M6 | VS Code as the place of work | Sessions, reviewing and accepting the agent's changes, mode and model, all from VS Code | Accepting a change applies exactly the diff that was reviewed; whatever is done in VS Code shows on every other client |
| M7 | Network access | Grants per host and per repository (pull; push with the user's token), asked for and recorded | An approved push sends exactly the branches and commits shown, and git refuses it if a branch has moved; a revoked grant stops new connections at once; a push that needs a decision while the service is down is refused; no sandbox ever holds the token |
| M8 | Tools and skills | MCP servers from the registry, each in its own container, started and stopped; the skills library | A hostile tool server gets no folder, secret or host it was not given; a skill's text is shown before it is turned on |
| M9 | The phone | Remote access on and off, pairing, approvals and answers, watching, tasks started from the phone, files sent to it | With remote access off, nothing listens on the tailnet; a revoked device can do nothing; a file sent once arrives once, even across a restart |
| M10 | Setup guide (design 0001's M5) | Someone else installs Clank with their own model, key or cluster | A fresh machine reaches a working model by the guide alone |

Design 0001's console milestone (its M4) is spread over all of them: M0 builds the shell, and each milestone brings
its screens. The order:

- models first: everything needs one (design 0001 §9.1's reasons hold), and they bring what the prototype lacks (NInfer,
  trials) while the prototype keeps serving as the agent;
- inline completion with the gateway, because a completion that the next keystroke makes obsolete is the hardest case
  for the gateway's queues and cancellation;
- containment before the agent, and the agent before its VS Code work surface;
- then network access, tools and the phone, which need an agent to use them.

Any milestone after M0 can be moved; the owner decides.

### 3.4 Carried into the later milestones' designs

Points of the outside review (below) that concern parts designed later, or approved sections of design 0001 that a
milestone's own design will revise:

- **M1.** Which KVMem version to pin. The owner runs v0.16.0-rc1. v0.17.0 (source only, 2026-09-30) keeps several
  conversations' caches (`--kvmem-conversations`), moves inactive ones to disk, and runs up to four requests at once
  (`--parallel`); v0.18.0 RC3 (2026-10-11) is NInfer-backed and built for Windows. With several conversations kept,
  design 0001 §6.4's reason to keep side requests off the main slot weakens; §4.5's loss of cached context on a switch
  still holds (KVMem's disk snapshots do not survive a restart of the engine).
- **M1, M2.** The fit check also shows the peak memory the last trial measured, and its *tight* threshold (500 MiB)
  becomes a setting (design 0001 §3.6).
- **M2.** Suites that measure useful work, not only speed: a change to a repository that its tests must pass, Lean
  elaboration, matching a statement to its formalization (false accepts counted apart from false rejections), tool
  calls that follow their schema (design 0001 §3.8).
- **M3.** Pass-through first (design 0001 §6.1-6.2): a request to a provider that speaks its dialect goes unchanged but
  for its sampling and credentials; translation between dialects covers only what each translator declares, and
  anything else fails with a clear error. The role's maximum output becomes a ceiling instead of a replacement, and the
  seed, stop sequences, response formats and tools stay the tool's (decision 0004). Requests get deadlines,
  cancellation that reaches the engine, bounded queues, and priorities that cannot starve a role (design 0001 §6.4).
  Recording the content of requests stays on by default (principle 3), and a workspace can turn it off (design 0001
  §6.5). Unknown model names: refusing them unless the user turns the `default` role on for them would catch typos;
  the owner decides (decision 0008).
- **M4, M5.** A workspace can have its agent work on a copy (a git worktree) whose changes the user accepts as a diff,
  as other local coding agents do. Each workspace's sandbox gets a network of its own, so sandboxes
  cannot reach one another (the prototype's share one).
- **M9.** Approving a consequential action from the phone (a push, a file sent, a change of provider) can require
  unlocking the phone (WebAuthn's user verification); a device's access can leave out the content of the work.

### What changed in design 0001 when this section was approved

§9.1's milestones were replaced by these, and §5.3's screens became the console's models screen, built in M1. Both
changes are in design 0001's revision log.

## The outside review of 2026-10-11

The owner shared a review of designs 0001 and 0002 written by another model (ChatGPT), asking that its points be
weighed, not taken as given. Each point was checked against these documents, the prototype's working sandbox and
gateway, and the sources the review cites (KVMem's releases among them).

| The review's point | Verdict | Where |
| --- | --- | --- |
| A shell can write files whatever the mode says, so a mode cannot rest on a permission check | Adopted: each permission is enforced where it can be stopped; plan mode mounts the workspace read-only; the agent program's own prompts are labeled as such | §2.6, §2.18 |
| The edge must be impossible to get around (DNS, IPv6, the host, proxies) | The mechanism belongs to M4's design. The prototype already runs it on this machine: an internal Docker network checked at every start, the gateway container as the only door, a read-only root without capabilities. Adopted as M4's escape tests, with one the review missed: sandboxes of different workspaces cannot reach one another | §3.3 (M4), §3.4 |
| An approved push must be the push that happens | Adopted: an approval covers exactly what it showed. The edge reads each branch update before asking (the prototype's gateway already does), and git refuses an update when the branch has moved | §1 example, §2.5, §3.3 (M7) |
| Switching a role to a hosted model sends a workspace's content to a third party | Adopted: `model.send`, checked by the gateway for every request against the provider serving it | §2.6 |
| Can an answer pass a workspace's boundary? Does revoking stop work already allowed? | Adopted: a deny is a ceiling no answer passes; bounds are what the agent has without asking; decisions expire and carry the policy's revision; the riskiest are decided at the moment of use | §2.6, §2.18 |
| Recovering from a crash needs more than "interrupted" | Adopted: recorded steps, steps declared safe or not to repeat, reconciling after a restart, request keys. The review's example (a push lost when the service crashes) cannot happen here: the edge sends the push and records it in its own spool | §2.4 |
| An expired event history breaks a reconnecting client | Adopted: the stream says so, and the client reloads | §2.3 |
| Generic routes could bypass a kind's rules | Already so for state (only read through them); adopted for settings: a kind declares what a change does to a record in use | §2.2 |
| The local API needs defenses against browsers and leaked tokens | Mostly designed (a token on every route); adopted: a host-name check, no CORS, no token in a URL | §2.7 |
| Installing a tool server or a skill must not grant it anything | Adopted | §2.11, §3.3 (M8) |
| Full request records are a second store of sensitive data; record only metadata by default | Declined as a default: radical transparency is the owner's principle, and the records never leave the machine. Adopted instead: every secret's value is removed before anything is written, and a workspace can turn content recording off | §2.8, §3.4 (M3) |
| The kernel is too broad, and should not be immutable | It never was immutable (§3.1: a kernel change is a decision, never a workaround), and two sentences now say so. Adopted: each kernel part is built in the first milestone that uses it, so M0 is smaller | Goal, §1, §2, §3.2 |
| KVMem has moved past the pinned version | Verified: v0.17.0 keeps several conversations and runs up to four requests at once; v0.18.0 RC3 came out the same day. Adopted: adapters declare what each version and launch option supports; the version is chosen in M1 | §2.10, §3.4 (M1) |
| One translation for every API dialect will lose features | Agreed, for M3's design: pass-through when the dialects match, and a clear error for what a translator does not declare | §3.4 (M3) |
| Unknown model names silently get the role `default` | For the owner to decide at M3 (decision 0008) | §3.4 (M3) |
| The role's sampling overwrites what a tool needs | Partly: stop sequences, formats and tools were never replaced; the maximum output becomes a ceiling | §3.4 (M3) |
| Scheduling needs deadlines and cancellation; do not rely on a CPU model for completion | Adopted for M3; any provider can already serve the `fast` slot | §3.4 (M3) |
| One memory threshold is not enough | Mostly designed: the trial's memory suite measures peaks (design 0001 §3.8). Adopted: the fit check shows the last measured peak, and the threshold is a setting | §3.4 (M1, M2) |
| Measure useful work, not only speed | Adopted for the trials | §3.4 (M2) |
| Completion should not wait for M6 | Adopted: it comes with the gateway (M3) | §3.3 |
| Stopping Docker affects other programs | Already designed: Clank touches only containers with its labels, and stopping Docker asks first and names the others | §3.2 |
| Approvals of consequential actions from the phone need confirming again | Adopted for M9's design | §3.4 (M9) |
| Build a secure workspace before the runtime | Declined: in either order no agent runs before containment exists (M4 comes before M5), and the runtime first brings what the prototype lacks while the prototype keeps serving as the agent | §3.3 |
| Keep the prototype until Clank passes its tests | Already the plan (design 0001 §9.2) | |
| Approved and proposed sections disagree | They are the revisions listed under each section, made when it is approved; the one stale example (a preset without its schema) is now among them | §2 |

## Revision log

Every change to an approved section, with its reason. Approvals themselves are in the status table above.

| Date | Section | Change | Why |
| --- | --- | --- | --- |
| 2026-10-11 | §1 | "Requests" to the user renamed *questions*; the "reach" component renamed *remote*; the `machine` component listed | A model request and the verb "reach" already used those words, and a name must mean one thing (principle 4); §2 and §3 need the `machine` component |
| 2026-10-11 | Sections | The parts built on the kernel (workspaces, network, agents and modes, tools and skills, the phone, VS Code, the console's screens) moved out of this document: each is designed at the start of its milestone (§3.1) | The owner: start building the skeleton soon, and let each built step inform the next design |
| 2026-10-11 | §1 | "The kernel does not change" became "should not need to change, and when it must, it changes by a decision"; the push example shows the exact push that is approved, and git's own check | The outside review: the owner asked for "minimal need to change the foundation", not none; an approval covers exactly what it showed (§2.5) |
