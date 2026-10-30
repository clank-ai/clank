# Known issues

Every confirmed problem with Clank: what the owner sees, where it comes from, and what is next. A fixed issue stays
listed for a release, with the commit that fixed it, so a reader can tell what changed. Found by the owner's own use, by
the end-to-end test of a new user's first hour on the owner's PC (2026-10-26), and by the repair work that followed.
Update this page in the same commit as the fix.

## Open

| Issue | What the owner sees | Where | Next |
| --- | --- | --- | --- |
| A flow's box can stay working with nothing behind it | The box says it works, nothing runs, and only Stop then Run from frees it; it follows a failure while the box's try was being settled | `flows/runner.py` (`_settle_anyway`, `_advance`, `_recover`) | Named transitions with a check when a run is saved: a working box has an operation or a question |
| Run from, after a stop, can stop its own first box | "Stopped by you before its session started" | `flows/runner.py` (`stop` leaves its mark until a box's operation ends) | Clear the mark in Run from and when a review checkpoint ends |
| After a job, a box can resume on the orchestrator's model and tools | A try recorded with its own preset ran on another, or failed with "session gone" | `flows/runner.py` (`_wait_on_job`, `_orchestrate`) | Run a job's checkpoint on the box's own preset and server |
| A job or side session goes on after its box fails | Trying the box again starts a second job on the same files | `flows/runner.py` | End them when the box fails or is canceled |
| Retrying a flow's operation from the Operations page goes around the flow | The run's box can be tried twice, or a checkpoint dropped | `kernel/operations.py`, `flows/runner.py` (`_box`) | Flows' operations are not retried there; the flow's own Run from is |
| Some errors read as something else | "Its preset is not there", or "there is no workspace", for any error | `flows/runner.py`, `agents/artifacts.py`, `agents/boards.py`, `agents/jobs.py` | Catch the errors meant |
| CI takes 29 to 35 minutes, and console frame tests fail now and then | A red run after a push that broke nothing; each push cancels the run before it | `tests/console/frames.py` (a frame called steady after 0.1 s, less than the console's 0.25 s update period), one CI job for everything | Wait until the console is quiet (no update queued, no worker); pytest-xdist; a first job of lint, types and generated files |
| The console still says some confusing things | "Nothing runs from here" while OpenCode runs; the Monitor opens on an empty Flow view; Watch for shows another workspace's mark; a dozen "coming" menu entries | `agents/console/folder.py`, the Monitor, `console/app.py` | A pass over the console's words (the menu's entries change every frame's snapshot) |
| pytest is not in the sandbox image | The agent's test runs fail with "No module named pytest" while This folder says nothing needs installing | `workspaces/image/Dockerfile` | Add it at the next change of the image |
| No scriptable way to give the agent a task | `opencode run` rejects every edit under review mode, and Clank does not see its session | `clank work` | `clank work --message`, on the start route Clank already has |
| The phone's chat (design 0025 §12) | Not built yet: a normal chat, the workspaces with the saved ones first, any session picked up, figures and the agent's questions in place | `remote/page/` | Plan s60 (branch `feature/phone-chat`, begun) |

## Fixed on 2026-10-29 and 10-30

| Issue | Cause | Commit |
| --- | --- | --- |
| Backspace went back a step while the owner typed in Add a model | The console gave the page every key a field did not handle itself, and a field takes Backspace through its binding, which Textual checks after the handlers | 3c4dbeb (decision 0151) |
| A cloud model's run stopped with nothing saying why | Its thinking used up the output limit (16,384), the answer was cut, and OpenCode ended the run; nothing changed a preset afterwards, and OpenCode capped an answer at 32,000 | 3c4dbeb (decision 0154), 7cfc7a3 (decision 0153) |
| `git clone` failed in dev mode | Dev mode opened the cloud's providers only; the agent's proxy asked the owner about each host in the console, unseen from OpenCode's window | ded0452 (decision 0152) |
| The workspace's cloud question opened in the console's top left corner | The windows were centered by a list of their kinds that missed the question's | 9f91a72 |

## Fixed on 2026-10-26 and 10-27

| Issue | Cause | Commit |
| --- | --- | --- |
| A new chat waited 10 to 37 s for its first word on the local model | KVMem v0.16 resumes only from its four newest snapshots of the model's state, all past OpenCode's shared system prompt after a few steps ([the measurement](measurements/2026-10-27-a-new-sessions-first-answer.md)) | The patch of decision [0146](decisions/0146-kvmem-keeps-a-snapshot-at-the-end-of-the-system-prompt.md), in frontier 262K's build since 2026-10-27: 0.5 to 1 s |
| KVMem could resume a conversation from another conversation's snapshot (found by the patch's tests) | Restoring a snapshot left the snapshots past it, taken on rows the new prompt does not share | The same patch: a snapshot restored drops the ones past it |
| `getaddrinfo EAI_AGAIN edge`, then OpenCode crashed | The edge container, made again when the proxy's port was added, joined only one workspace's network | 21fbe29 |
| `clank code`, `clank work` and the console waited 22-32 s before anything | Whether a model is usable asked WSL for every model file's size, even with a model loaded | 5d3723c |
| Each start of the agent took 16 s | Nine `docker exec` writes and a `docker info` at every start | 2c855f8 |
| The service stopped answering, and neither `clank stop` nor `clank serve` could help | On Windows, asyncio closed the service's socket when a client dropped a connection being accepted (`WinError 64`) | 886b61d |
| A model switch failed with `PermissionError` on `gateway.json` | Windows refuses to delete or replace a file another process holds open | 2b741e2 (merged in 9fcff1f) |
| A gateway restart started no gateway | The stopped gateway's process held its port a moment longer | 5df48e1 |
| A new chat on a fresh OpenCode server failed with "timed out" | The server's first request, slow while OpenCode readies itself, had only 10 s | f1f7cf2 |
| Every new OpenCode window waited a minute before its first answer | OpenCode's plugin install went to npm, and Clank's proxy held it while asking the owner | d5562fe |
| The phone's tab bar sat higher on short tabs | A bar fixed to the page, which iOS places differently on a page too short to scroll | 93a8273, 4d8a823 |
| The word "null" at the top of every phone tab | The app handed the page an absent line (the pause's, while live), which the browser draws as "null" | 4538ab2; tested on `design/one-look` |
| The phone's header said "● live" as a solid green block, and would have drawn "● offline" as the offline screen's grid | Its state's class was the state's bare name, also the LIVE mark's and the offline screen's | d716f24 (the mark); the header's own classes on `design/one-look` |
| The page the phone app is added from looked broken | Its lines took the Flows tab's step style (12 pixels, stretched over the screen), and it named an SVG icon, which iOS does not take for the Home Screen | On `design/one-look` |
| The phone page did not load | With Funnel on, the PC's name resolves on the internet too, and iCloud Private Relay looked it up there, reaching Tailscale's relay | The iPhone's settings (Private Relay off); the diagnostics are on `fix/phone` |
| The phone's first screen took 12 s | Each workspace's sessions were read one after another | dd6d3f0 |
| A flows test failed on CI only | It checked the last event, which a planning's own status line could follow on a slow machine | dd6d3f0 |
| The service read a closed window's sessions again forever, and waited 10 s per request on a dead OpenCode | A closed window's sessions were retried without end, and the bridge did not answer while OpenCode did not | fix/watcher, merged after 7ab3d4a |
| The phone page did not say why it could not connect | Nothing on the PC said whether the iPhone was on the tailnet, that Funnel made the PC's name public, or that iCloud Private Relay bypassed Tailscale's DNS | 8aadc4b |
| Confusing words: the clients connected, the slots not loaded, the doctor's line, the tool server's path, a refused request's fields, a waiting call's raw input, the network log's UTC times, log lines without times | Words written for Clank's makers | b08023e, a1f54b7, fa7a784, 7010ec0, 0772ff0 |
| A console test failed each evening | It named its log file by UTC's date while the proxy uses this computer's | 7f8dd9d |
| Times in UTC in the phone's commands and page | The device and code times were printed as UTC text | 7f42a2a |
| VS Code did not say when the agent could not reach the model | OpenCode failed in its terminal with network errors; the panel waited on slow routes before OpenCode opened | fix/vscode, merged with 2fef8fc (extension 0.10.3) |
| No update command | Updating meant running the installer again | `clank update` (design 0026, plan s61) |
| Removing a workspace while OpenCode was open in VS Code gave no warning, and tracebacks in the service's log | The watcher and the readout did not expect a workspace gone, and the removal's question did not say its container ran | feeb406 (handled quietly), and the question now says what runs in the container ends |
| CI failed after midnight on 10-27 | Two tests and the network log read the computer's date where the service's clock is the day; a snapshot, a format and the extension's timer test lagged the code | a7eb653, 2fc8720 |
