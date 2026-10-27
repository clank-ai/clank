# Recorded programs

What real programs answered, at the versions Clank's adapters are tested against (design 0001 §8.3, design 0002
§2.10). Each adapter has a folder named after it, and in it one folder per recorded version holding `program.json`:

| Field | What it holds |
| --- | --- |
| `program`, `version` | The program and its version, as the program names them |
| `recorded`, `how` | When, on what, and how it was recorded, including what was written by hand and why |
| `initial` | The state a test starts in unless it asks for another |
| `states` | For each state (such as running and stopped), each command with its exit status, its output, and, when they were recorded, its seconds and its errors |
| `transitions` | The commands that move the program to another state |

An answer is `[status, output]`, `[status, output, seconds]` or `[status, output, seconds, errors]`: an exit status of
null means no answer came, and the errors are what the program wrote to its error output (design 0014 §2: Docker's
words for a user outside the docker group are there). `tests/fakes/recorded.py` plays a recording back to an adapter,
as a command's output or as its whole answer, and fails the test on any command that was never recorded, so an adapter
that starts asking something new is caught and the program recorded again. Every kind of adapter has one contract test
file, `tests/contract/test_<kind>.py`, run against every recording of every adapter of the kind; a test fails when an
adapter has no recording.

Nothing personal is kept: names, ids, images, labels and paths are replaced by made-up ones of the same form, and the
secrets check reads these files like every other.

Each recording of a container platform, while it runs, shows one container of each sort the contract checks: one of
Clank's (its `clank.*` labels), one of another tool's (`toolbox.*` labels), one of another program's, and one that is
not running.

A platform Clank does not start (Docker Engine, a system service: design 0014 §2) has no transitions, and the contract
holds it to that: it refuses a start and a stop with the command its owner runs. Its recording holds three states
instead, each made by the owner of the computer it was recorded on: `running`, `stopped` (both of Docker's units
stopped, so no command woke the engine) and `no access` (as a user outside the docker group). It is made by
`tools/capture_docker_engine.py`, which runs the commands the `docker-engine` adapter sends, as the tool lists them,
keeps each one's status, output, seconds and errors, replaces the containers' ids and the computer's and user's names,
and merges the three states into `program.json`. The hand-run job `.github/workflows/record-docker-engine.yml` does it
all on GitHub's ubuntu-24.04 runner and prints the recording in its log between two marker lines; it becomes
`docker-engine/<version>/program.json` (28.0.4 first, recorded on 2026-10-27).

An endpoint adapter (a provider reached at its URL, design 0016 §18) is recorded over HTTP instead: its folder holds
one folder per recording, named by its date (or `documented`, the shapes its documentation describes, written by hand
before anyone's key was used), each holding `http.json`:

| Field | What it holds |
| --- | --- |
| `adapter` | The adapter it is for |
| `source`, `recorded`, `how` | Where its shapes come from, when, and how it was made, including what was replaced |
| `key` | The made-up key the recording's requests carry (never one that starts with `sk-`) |
| `exchanges` | Each of Clank's fixed made-up requests (its `name`, its `request`: method, path, query, body) and the `response`: its status, its headers, and its `body`, or its `stream` (each line of the event stream) |

`tests/fakes/openrouter.py` plays a recording as OpenRouter, and `tests/contract/test_endpoint.py` runs over every
recording of every endpoint adapter. A recording made with the owner's key (`tools/capture_endpoint.py`) has the key
and the account's label replaced by made-up ones.

`opencode/1.19.0/changes.json` is of another sort: what OpenCode's server says when its agent asks to change a file
(design 0007 §2), recorded with a scripted model and no network. For each change it holds the ask, the tool call's
input, and the file before and after; `tests/components/agents/test_changes.py` works the file out from them.

`opencode/1.19.0/session.json` is written by hand, not recorded (its `_about` says from what): a synthetic planner
session with a subagent, another session, their histories, and bursts of the events OpenCode's server streams while a
session works (design 0012 §6.1). `tests/fakes/opencode.py` serves them as the OpenCode of the bridge's tests;
recording them from OpenCode 1.19.0 in the sandbox image with a scripted model is left to do (plan s14).
