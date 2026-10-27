# Known issues

Every confirmed problem with Clank: what the owner sees, where it comes from, and what is next. A fixed issue stays
listed for a release, with the commit that fixed it, so a reader can tell what changed. Found by the owner's own use, by
the end-to-end test of a new user's first hour on the owner's PC (2026-10-26), and by the repair work that followed.
Update this page in the same commit as the fix.

## Open

| Issue | What the owner sees | Where | Next |
| --- | --- | --- | --- |
| A new session's first answer reads the whole prompt anew | Up to 20-30 s before the first word of a new chat, while the local model reads about 18,000 tokens of OpenCode's tools and instructions (later steps take a second) | The engine's cache across sessions, OpenCode's tool set | Measure the cache across sessions; give the agent fewer tools |
| Removing a workspace while OpenCode is open in VS Code | No warning; tracebacks in the service's log; the readout fails with "there is no workspace" | `agents/watch.py`, `agents/jobs.py` | Treat a workspace that is gone quietly; warn before removing one in use |
| The console still says some confusing things | "Nothing runs from here" while OpenCode runs; the Monitor opens on an empty Flow view; Watch for shows another workspace's mark; a dozen "coming" menu entries | `agents/console/folder.py`, the Monitor, `console/app.py` | A pass over the console's words (the menu's entries change every frame's snapshot) |
| Times in UTC in the phone's commands | `clank remote status` and `clank remote pair`; the Phone page's paired date has no day | `remote/cli.py`, `remote/console/phone.py` | Local times, with the date when it is not today |
| pytest is not in the sandbox image | The agent's test runs fail with "No module named pytest" while This folder says nothing needs installing | `workspaces/image/Dockerfile` | Add it at the next change of the image |
| No scriptable way to give the agent a task | `opencode run` rejects every edit under review mode, and Clank does not see its session | `clank work` | `clank work --message`, on the start route Clank already has |
| The phone's chat (design 0025 §12) | Not built yet: a normal chat, the workspaces with the saved ones first, any session picked up, figures and the agent's questions in place | `remote/page/` | Plan s60 (branch `feature/phone-chat`, begun) |
| VS Code does not say when the agent cannot reach the model | OpenCode fails in its terminal with network errors | `agents/`, `vscode/` | Branch `fix/vscode`: a check of the path to the model, shown in the panel |
| No update command | Updating means running the installer again | `clank/cli/` | The update feature (not begun) |

## Fixed on 2026-10-26

| Issue | Cause | Commit |
| --- | --- | --- |
| `getaddrinfo EAI_AGAIN edge`, then OpenCode crashed | The edge container, made again when the proxy's port was added, joined only one workspace's network | 21fbe29 |
| `clank code`, `clank work` and the console waited 22-32 s before anything | Whether a model is usable asked WSL for every model file's size, even with a model loaded | 5d3723c |
| Each start of the agent took 16 s | Nine `docker exec` writes and a `docker info` at every start | 2c855f8 |
| The service stopped answering, and neither `clank stop` nor `clank serve` could help | On Windows, asyncio closed the service's socket when a client dropped a connection being accepted (`WinError 64`) | 886b61d |
| A model switch failed with `PermissionError` on `gateway.json` | Windows refuses to delete or replace a file another process holds open | 2b741e2 (merged in 9fcff1f) |
| A gateway restart started no gateway | The stopped gateway's process held its port a moment longer | 5df48e1 |
| A new chat on a fresh OpenCode server failed with "timed out" | The server's first request, slow while OpenCode readies itself, had only 10 s | f1f7cf2 |
| Every new OpenCode window waited a minute before its first answer | OpenCode's plugin install went to npm, and Clank's proxy held it while asking the owner | d5562fe |
| The phone's tab bar sat higher on short tabs | A bar fixed to the page, which iOS places differently on a page too short to scroll | 93a8273, 4d8a823 |
| The phone page did not load | With Funnel on, the PC's name resolves on the internet too, and iCloud Private Relay looked it up there, reaching Tailscale's relay | The iPhone's settings (Private Relay off); the diagnostics are on `fix/phone` |
| The phone's first screen took 12 s | Each workspace's sessions were read one after another | dd6d3f0 |
| A flows test failed on CI only | It checked the last event, which a planning's own status line could follow on a slow machine | dd6d3f0 |
| The service read a closed window's sessions again forever, and waited 10 s per request on a dead OpenCode | A closed window's sessions were retried without end, and the bridge did not answer while OpenCode did not | fix/watcher, merged after 7ab3d4a |
| The phone page did not say why it could not connect | Nothing on the PC said whether the iPhone was on the tailnet, that Funnel made the PC's name public, or that iCloud Private Relay bypassed Tailscale's DNS | 8aadc4b |
| Confusing words: the clients connected, the slots not loaded, the doctor's line, the tool server's path, a refused request's fields, a waiting call's raw input, the network log's UTC times, log lines without times | Words written for Clank's makers | b08023e, a1f54b7, fa7a784, 7010ec0, 0772ff0 |
| A console test failed each evening | It named its log file by UTC's date while the proxy uses this computer's | 7f8dd9d |
