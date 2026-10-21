# M0's follow-ups: the deferred items, closed

> As for M0.2-M0.6, this plan gives the files, interfaces and tests by name and intent; the code is in the commits,
> written test-first.

**Goal:** close every item the final reviews of M0.1-M0.6 deferred, and the one found after the 0.1.1 release, before
M1 starts (the owner, 2026-10-12: "complete the small issues that you left for later, this includes the installation of
the VS Code extension and putting uv on my path, as well as everything else you have identified").

**Spec:** the plans' own final reviews ([M0.1](m0.1-the-package-and-its-checks.md#final-review),
[M0.2](m0.2-the-kernel.md#final-review), [M0.3](m0.3-the-service.md#final-review),
[M0.4](m0.4-adapters-and-docker.md#final-review), [M0.5](m0.5-the-console.md#final-review),
[M0.6](m0.6-the-vscode-extension.md#final-review)); design 0001 §8.4 and design 0002 §2 for what each part must do.

## Global Constraints

- Everything of M0.1-M0.6's global constraints holds.
- On the owner's machine (outside this repository), only what the owner asked for: uv on the path, the extension in
  VS Code.

## The items

| # | From | Item | How it closes |
| --- | --- | --- | --- |
| 1 | M0.1 | A skipped Python 3.14 job shows as `${{ matrix.os }}, Python 3.14` | The job's name leaves the matrix to GitHub |
| 2 | M0.1 | The documentation check misses setext headings, links from the repository's root, and fences indented inside lists | It reads them as GitHub does |
| 3 | M0.1 | An index that links `./0001-x.md` reads as not listing it | Links are compared as paths |
| 4 | M0.1 | The code map and the tests page list files git ignores | Both list what git tracks or would track, as the other checks do |
| 5 | M0.1 | The secrets check reports `%USERNAME%`-style placeholders and generic users' home folders | Placeholders and generic names are skipped |
| 6 | M0.1 | Rich's and Textual's color names spelled the British way | Verified: none is used, and the spelling check refuses one |
| 7 | M0.2 | A question's option keys are not checked for being distinct | A question with two options on one key is refused |
| 8 | M0.2 | A settings error's line can miss for nested or repeated keys | The line comes from the exact path of the field |
| 9 | M0.2 | The lock table knows only this service's operations | Closed by item 11: one service per home |
| 10 | M0.2 | `latest()` pages by id | Ruled: id order is the order things were recorded, the truthful order; no change |
| 11 | M0.3 | Two services started at the same moment could both run for one home | A service holds a lock on its home for its whole life |
| 12 | M0.3 | `history` and `operations` accept any `limit` | A limit outside 1-1000 is refused in the API's one error shape |
| 13 | M0.3 | The record routes read only the kernel's state kinds | A component's state kind declares its reader; M1's runtime state is the first |
| 14 | M0.4 | Docker's stopped state and its start and stop are written from its documentation, not recorded | Recorded through a real stop and start (2026-10-13), which found two faults, both fixed (below) |
| 15 | M0.4 | A question that expires has no test of its own | Docker's stop question expiring takes its default: Docker keeps running |
| 16 | M0.4 | A label value holding a comma can add a false label name | Label names are read from Docker's own map of them |
| 17 | M0.5 | A step cut short by a cancel is recorded as failed | Steps can be canceled (kernel migration 0003) |
| 18 | M0.5 | The console's own settings come with the layout page | The layout page is M1's (the menu says so) |
| 19 | M0.5 | The history page's filter box is always shown | It shows on `/` and hides again when left empty |
| 20 | M0.6 | No test runs the extension inside a real VS Code | Decision 0028 leaves it to M6; weighed again at the end of this plan |
| 21 | M0.6 | Questions already waiting when VS Code opens show only in the count | Each is shown once, as a question asked later is |
| 22 | M0.6 | The extension is not installed in the owner's VS Code | Installed, at its new version |
| 23 | 0.1.1 | At 120 columns, home's Docker line splits its hint across two lines | The hint stays whole |
| 24 | Owner | uv is not on the owner's path | Installed by its own installer (0.12.3, as decision 0022 pins) where the path already looks |

- [x] Items 1-24, each test-first where it changes code, each committed and pushed; CI green on every platform at the
  end, then version 0.1.2. Item 14 waited for the owner and was done on 2026-10-13 (below); items 13 and 18 are M1's.

## Rulings made while building

- **Setup.** One plan for every deferred item rather than an M0.7: they are small and unrelated, and the record of
  each is its row above. Work on `main`, a self-review at the end. Cost if wrong: a weaker review.
- **Item 6.** Nothing to change: no color name in the code is spelled the British way, and the spelling check refuses
  one. Cost if wrong: none.
- **Item 9.** Closed by item 11: with one service per home, the operations this service started are all there are.
  Cost if wrong: none.
- **Item 10.** No change: events are numbered in the order they were recorded, so paging by id is paging in the order
  things happened as Clank saw them, even when the clock was changed. Cost if wrong: none.
- **Item 13.** Left to M1, whose runtime brings the first state kinds of a component, each declaring how its records
  are read. Cost if wrong: none until then.
- **Item 14.** Not done on 2026-10-12: recording Docker's stopped state means stopping Docker on the owner's machine,
  which stops the containers running in it; that is the owner's call, asked for when the owner is there. Done on
  2026-10-13, when the owner said to stop Docker: its answers were recorded through one stop and one start (the one
  container running, the prototype's gateway, was started again afterwards). Docker Desktop 4.85.0 did not do what its
  documentation says, in two ways, and each became a test that failed first. Stopped, `docker desktop status` never
  answers, and Clank's time limit did not hold on Windows (the helper it hands the question to keeps the output open,
  and reading the output waits for it), so every reading of a stopped Docker took 16 seconds: a program is now ended
  with every process it started when its time is up, and the adapter asks the engine first and asks
  `docker desktop status` only when the engine does not answer, within 2 seconds. And after `docker desktop stop`,
  `docker desktop start` (with `--detach` or with `--timeout`) answers that Docker Desktop is already running and
  starts nothing, so Clank's start would have waited five minutes and failed: when it says so of a stopped Docker
  Desktop, the adapter now starts Docker Desktop's own program, as the Start menu does (its engine answered 8 seconds
  later). The stop answers only once Docker Desktop has stopped (13 seconds), so a start or a stop request now has a
  minute. Cost if wrong: on a Docker Desktop whose command does start it, a start costs one more reading of its
  state.
- **Item 16.** Label names now come from `docker container inspect`, one more command per reading of Docker's state;
  its answer was added to the recording, its form checked against Docker Desktop 4.85.0 on this machine. Cost if
  wrong: one command per reading.
- **Item 18.** Left to M1, as the console's menu already says (Layout, M1). Cost if wrong: none until then.
- **Item 20.** Done now rather than in M6 (decision 0029 refines 0028): one development tool, and the suite runs only
  in CI and when asked, never in a working copy's ordinary check, because it opens a window. Cost if wrong: a 150 MB
  download per CI run of the job that runs it.
- **Item 24.** uv was installed by its own installer, pinned to 0.12.3 as decision 0022 pins it, into
  `~/.local/bin`, which the owner's path already holds; adding the folder where pip had put it would also have put
  pip, pytest and twenty other programs of one Python on the path. That copy can update itself (`uv self update`).
  Cost if wrong: two copies of uv on the machine, the path's one first.

## Final review

A self-review of every item against the final reviews it came from: each code change has a test that failed first (item
15's test covers behavior that existed, and item 20's suite was made to fail once to show it can), and the whole suite
passes. Checked on the owner's machine: uv answers from a fresh shell, the Docker adapter reads the real Docker's labels
through `docker container inspect`, the host suite passes in VS Code 1.138.0, and the extension installed in the owner's
VS Code (`clank.clank@0.1.1`). No important finding. Waiting for the owner: item 14, done on 2026-10-13 (its ruling
above), then checked on the owner's machine through Clank itself, on the service restarted with the fix: `clank docker
stop --yes` stopped Docker in 21 seconds; `clank docker status` read the stopped Docker in 2.7 seconds (16.6 before the
fix); `clank docker start` started it in 9.7 seconds through Docker Desktop's own program, and put back WSL's handler
for Windows programs, which that start had removed. The prototype's gateway container was started again afterwards.

Deferred minor: stopped, `clank docker status` prints an empty line where a running Docker's summary goes.
