# 0148. While anything the setup needs is missing, the console opens on Setup

- Status: Accepted (the owner's instruction of 2026-10-27, written into
  [design 0028](../design/0028-setup-plug-and-play.md) §1 and §4); supersedes the opening of decision
  [0105](0105-with-no-usable-model-the-console-opens-on-add-a-model.md), whose Add a model now comes from Setup
- Date: 2026-10-27

## Context

Decision 0105 opens the console on Add a model when no model is usable, so a new user's first step is the model. The
owner then asked for a setup that is "basically just a plug and play", one a new user follows "without using an LLM":
Docker installed, running and usable by the account, the sandbox image built, a model that answered a test request,
and a folder that is a workspace (design 0028 §1). On Linux, Docker Engine stopped or an account outside the docker
group stops everything else, and Add a model says neither. Design 0028 §1's path and §4 put the checklist first: "While
anything is missing, the console opens on **Setup**".

## Decision

- With no page named (a bare `clank`, `clank console`), the console opens on **Setup** in place of This folder or Home
  while a required item of `clank setup`'s checklist is not done that This folder does not put right on its way to
  the agent (design 0028 §4: Docker installed, running and usable by this account, its memory limits where it cannot
  set them, Clank's service, a model, a folder; the checklist's `opens`). Two items do not count, since This folder
  does them before it starts the agent, as it did before Setup: a Docker Desktop that is only stopped (This folder
  starts it) and a sandbox image not built for this Clank (This folder builds it, asked first). Offered items (Docker
  starting with the computer, Clank's VS Code window) do not count either.
- Setup's model item opens Add a model (`m`), and its folder item This folder (`f`); Ready opens This folder (`f`).
- With the setup done and no model usable now (a preset answered once, but none can load), the console opens on Add a
  model, as decision 0105 says.
- A page named on the command line opens as asked.
- The page has no key of its own: the one F-key left, F11, is the terminal's full screen on most terminals. It is the
  last page of the menu, and Ctrl+P finds it.

## Alternatives considered

- **Keep Add a model first, Setup in the menu.** A new user on Linux would add a model, then meet Docker's refusal on
  This folder, with the fix in another place.
- **Setup only on the first start.** Docker Engine stopped after a restart would go unsaid until This folder's step,
  which can only name the command: Setup runs it in the terminal on one key.
- **Setup whenever any required item is not done** (as first built, 2026-10-27). An owner who set Clank up would meet
  Setup after every restart of Windows (Docker Desktop not started yet) and after every update that changes the
  sandbox image, one more page before This folder, whose `a` starts Docker Desktop and builds the image itself and
  says each step as it does it. Narrowed before release (2026-10-28) to what This folder cannot do.
- **F11 for the page.** Windows Terminal, GNOME Terminal and macOS keep it, so the key would do nothing there.

## Consequences

- The console reads the checklist with everything else at its start (`GET /setup`, the console's `setup` topic) and
  again when Docker, a slot, an operation's end or a workspace's record changes.
- A user whose Docker Engine is stopped meets Setup first, where `t` runs the command shown in the terminal, asked
  first; a Docker Desktop only stopped is started by This folder, as before.
- `clank setup --check` still says every item not done, and exits 1 until all are: the checklist is unchanged; only
  where the console opens is.
