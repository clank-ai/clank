# Recorded programs

What real programs answered, at the versions Clank's adapters are tested against (design 0001 §8.3, design 0002
§2.10). Each adapter has a folder named after it, and in it one folder per recorded version holding `program.json`:

| Field | What it holds |
| --- | --- |
| `program`, `version` | The program and its version, as the program names them |
| `recorded`, `how` | When, on what, and how it was recorded, including what was written by hand and why |
| `initial` | The state a test starts in unless it asks for another |
| `states` | For each state (such as running and stopped), each command with its exit status and its output |
| `transitions` | The commands that move the program to another state |

`tests/fakes/recorded.py` plays a recording back to an adapter, and fails the test on any command that was never
recorded, so an adapter that starts asking something new is caught and the program recorded again. Every kind of
adapter has one contract test file, `tests/contract/test_<kind>.py`, run against every recording of every adapter of
the kind; a test fails when an adapter has no recording.

Nothing personal is kept: names, ids, images, labels and paths are replaced by made-up ones of the same form, and the
secrets check reads these files like every other.

Each recording of a container platform, while it runs, shows one container of each sort the contract checks: one of
Clank's (its `clank.*` labels), one of another tool's (`toolbox.*` labels), one of another program's, and one that is
not running.

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
